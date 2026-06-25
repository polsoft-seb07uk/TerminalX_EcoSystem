"""Image tools module for TerminalX EcoSystem.

Obsluguje operacje na plikach graficznych bezposrednio z terminala.
Wymaga: Pillow (pip install Pillow)

Komendy:
  img info     <plik>                  - metadane + sha256 + integrity check
  img resize   <plik> <SzxWy>[!]       - zmiana rozmiaru (! = wymus dokladne)
  img crop     <plik> <x> <y> <w> <h> - wycinanie fragmentu
  img convert  <plik> <format>         - konwersja formatu
  img thumb    <plik> [rozmiar]        - miniatura (domyslnie 128)
  img rotate   <plik> <stopnie>        - obrot (canvas rozszerza sie)
  img flip     <plik> <h|v>            - odbicie lustrzane
  img gray     <plik>                  - skala szarosci
  img bright   <plik> <wsp>            - jasnosc (1.0 = oryginalna)
  img contrast <plik> <wsp>            - kontrast (1.0 = oryginalny)
  img blur     <plik> [promien]        - rozmycie gaussowskie
  img sharpen  <plik>                  - wyostrzenie
  img ascii    <plik> [szerokosc]      - podglad ASCII-art w terminalu
  img find     [katalog] [--ext <ext>] - szukaj plikow graficznych (-> search)
  img batch    <op> <wzorzec> [args]   - operacja wsadowa (-> task w tle)

Flagi globalne (dolaczane do dowolnej komendy):
  --replace     przenies oryginalne pliki do .trash po zapisie

Integracje dwukierunkowe:
  defender  <- skan pliku przed przetworzeniem; wykrywa anomalie EXIF
  sha256    <- suma kontrolna kazdego pliku wyjsciowego; pokazywana w info
  notify    <- powiadomienie po zakonczeniu batch lub przy bledzie
  search    <- img find deleguje wyszukiwanie do FileSearcher
  trash     <- --replace przenosi oryginaly do .trash (nie usuwa)
  analyser  -> analyser deleguje pliki graficzne do imgtools.analyse_image
  task      -> img batch moze uruchomic sie jako task w tle (--bg)

polsoft.ITS(TM) Group  *  Sebastian Januchowski
"""

from __future__ import annotations

import os
import glob
import re
import shutil
import time

from ._shared import (
    ROOT_DIR, TRASH_DIR, IS_WIN,
    RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT,
    _w, _pad,
)
from . import _integration

# ---------------------------------------------------------------------------
# Obslugiwane rozszerzenia
# ---------------------------------------------------------------------------

IMG_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif",
    ".tiff", ".tif", ".ico", ".ppm", ".pgm", ".pbm",
}

# ---------------------------------------------------------------------------
# Helpers wewnetrzne
# ---------------------------------------------------------------------------

def _pil_available() -> bool:
    try:
        import importlib
        importlib.import_module("PIL.Image")
        return True
    except ImportError:
        return False


def _load_image(path: str):
    """Laduje obrazek. Zwraca (Image, None) lub (None, str_bledu)."""
    from PIL import Image
    if not os.path.isfile(path):
        return None, f"imgtools: plik nie istnieje: {path}"
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMG_EXTS:
        return None, f"imgtools: nieobslugiwane rozszerzenie: {ext}"
    try:
        img = Image.open(path)
        img.load()
        return img, None
    except Exception as exc:
        return None, f"imgtools: blad odczytu: {exc}"


def _out_path(src: str, suffix: str = "", ext: str = "") -> str:
    """Buduje sciezke wyjsciowa obok oryginalu."""
    base, orig_ext = os.path.splitext(src)
    out_ext = ext if ext else orig_ext
    if out_ext and not out_ext.startswith("."):
        out_ext = "." + out_ext
    return base + suffix + out_ext


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _split_flags(args: list) -> tuple[list, set]:
    """Rozdziela args na czyste argumenty i zbior flag (--xxx)."""
    flags = {a for a in args if a.startswith("--")}
    clean = [a for a in args if not a.startswith("--")]
    return clean, flags


# ---------------------------------------------------------------------------
# Integracja: defender – skan przed przetworzeniem
# ---------------------------------------------------------------------------

def _defender_check(path: str, _t) -> bool:
    """Sprawdza plik przez defender. Zwraca True = bezpieczny / brak defendera."""
    safe = _integration.defender_scan_file(path)
    if not safe:
        print(f"{RED}{_t('img_defender_blocked', path=os.path.basename(path))}{RST}")
    return safe


# ---------------------------------------------------------------------------
# Integracja: sha256 – suma kontrolna pliku wyjsciowego
# ---------------------------------------------------------------------------

def _sha256_stamp(path: str) -> str | None:
    """Oblicza SHA-256 pliku. Zwraca digest lub None."""
    return _integration.compute_sha256(path)


# ---------------------------------------------------------------------------
# Integracja: notify – powiadomienie
# ---------------------------------------------------------------------------

def _notify(terminal, message: str, kind: str = "ok", title: str = "IMG") -> None:
    _integration.notify_event(terminal, message, kind=kind, title=title, compact=True)


# ---------------------------------------------------------------------------
# Integracja: trash – przenies oryginał do .trash (flaga --replace)
# ---------------------------------------------------------------------------

def _trash_original(path: str, _t) -> bool:
    """Przenosi plik do .trash przez modul trash. Zwraca True przy sukcesie."""
    ok = _integration.trash_move(path)
    if ok:
        print(f"  {DIM}{_t('img_replace_trashed', name=os.path.basename(path))}{RST}")
    else:
        print(f"{RED}{_t('img_replace_trash_err', exc='przeniesienie nie powiodło się')}{RST}")
    return ok


# ---------------------------------------------------------------------------
# Integracja: analyse_image – publiczne API dla analyser.py i defender.py
# ---------------------------------------------------------------------------

def _get_image_report(path: str) -> dict:
    """Zwraca slownik metadanych obrazu.

    Uzywane przez:
      - analyser.py: _analyse_file() dla plikow graficznych
      - defender.py: _check_image_anomalies() do skanowania EXIF
    """
    if not _pil_available():
        return {}
    try:
        from PIL import Image
        img = Image.open(path)
        img.load()
        w, h  = img.size
        mode  = img.mode
        fmt   = img.format or os.path.splitext(path)[1].lstrip(".").upper()
        fsize = os.path.getsize(path)

        exif_data: dict = {}
        try:
            exif = img._getexif()
            if exif:
                from PIL.ExifTags import TAGS
                for tid, val in list(exif.items()):
                    name = TAGS.get(tid, str(tid))
                    try:
                        exif_data[name] = str(val)
                    except Exception:
                        pass
        except Exception:
            pass

        img.close()
        return {
            "width":      w,
            "height":     h,
            "mode":       mode,
            "format":     fmt,
            "size_bytes": fsize,
            "exif":       exif_data,
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Operacje
# ---------------------------------------------------------------------------

def _img_info(args: list, _t, terminal=None) -> None:
    if not args:
        print(_t("img_info_usage"))
        return
    path = os.path.abspath(args[0])

    if not _defender_check(path, _t):
        return

    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    w, h  = img.size
    mode  = img.mode
    fmt   = img.format or os.path.splitext(path)[1].lstrip(".").upper()
    fsize = os.path.getsize(path)

    info_lines = [
        (_t("img_info_file"),   os.path.basename(path)),
        (_t("img_info_format"), fmt),
        (_t("img_info_size"),   f"{w} x {h} px"),
        (_t("img_info_mode"),   mode),
        (_t("img_info_fsize"),  _human_size(fsize)),
    ]

    # EXIF
    exif_anomaly = False
    try:
        exif = img._getexif()
        if exif:
            from PIL.ExifTags import TAGS
            _SHOW_TAGS = {"DateTime", "Make", "Model", "Software",
                          "ExifImageWidth", "ExifImageHeight",
                          "GPSInfo", "UserComment"}
            for tag_id, val in list(exif.items()):
                name = TAGS.get(tag_id, str(tag_id))
                if name not in _SHOW_TAGS:
                    continue
                val_str = str(val)
                if name == "UserComment" and any(
                    kw in val_str.lower()
                    for kw in ("exec", "eval", "import", "script",
                               "<?php", "<script", "powershell", "base64")
                ):
                    exif_anomaly = True
                    val_str = f"{RED}[!] {val_str[:60]}{RST}"
                info_lines.append((name, val_str))
    except Exception:
        pass

    img.close()

    # SHA-256 przez _integration -> sha256.py lub fallback wbudowany
    digest = _sha256_stamp(path)
    if digest:
        info_lines.append(("SHA-256", f"{DIM}{digest}{RST}"))

    # Integrity check przez defender
    ok, status, _ = _integration.defender_check_integrity(path)
    if ok is True:
        info_lines.append((_t("img_info_integrity"), f"{GRN}OK{RST}"))
    elif ok is False:
        info_lines.append((_t("img_info_integrity"), f"{RED}NARUSZONA{RST}"))
        _integration.log_debug_event(
            terminal, "WARN", f"imgtools: integralnosc naruszona: {path}"
        )

    _w(f"\n{BOLD}{BCYN}  +================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |   {_t('img_info_header')}          |{RST}\n")
    _w(f"{BOLD}{BCYN}  +================================+{RST}\n\n")
    for label, val in info_lines:
        _w(f"  {YLW}{_pad(label, 20)}{RST} {WHT}{val}{RST}\n")
    _w("\n")

    if exif_anomaly:
        _integration.notify_event(
            terminal,
            _t("img_exif_anomaly", path=os.path.basename(path)),
            kind="warn", title="IMG/EXIF",
        )


def _img_save(out_img, out: str, src: str, _t,
              terminal=None, replace: bool = False,
              msg_key: str = "img_save_done", **msg_kw) -> bool:
    """Wspolna logika zapisu: save -> sha256 -> trash -> notify."""
    try:
        out_img.save(out)
        digest = _sha256_stamp(out)
        digest_str = f"  {DIM}sha256 {digest[:16]}…{RST}" if digest else ""

        ok_msg = _t(msg_key, out=out, src=src, **msg_kw)
        print(f"{GRN}{ok_msg}{RST}")
        if digest_str:
            print(digest_str)

        if replace:
            _trash_original(src, _t)

        return True
    except Exception as exc:
        err_msg = _t("img_save_error", exc=exc)
        print(f"{RED}{err_msg}{RST}")
        _integration.notify_event(terminal, err_msg, kind="err", title="IMG")
        return False


def _img_resize(args: list, _t, terminal=None) -> None:
    if len(args) < 2:
        print(_t("img_resize_usage"))
        return
    clean, flags = _split_flags(args)
    if len(clean) < 2:
        print(_t("img_resize_usage"))
        return
    path, spec = clean[0], clean[1]
    replace = "--replace" in flags

    force = spec.endswith("!")
    spec  = spec.rstrip("!")
    m = re.match(r"^(\d+)[xX](\d+)$", spec)
    if not m:
        print(f"{RED}{_t('img_resize_bad_spec', spec=spec)}{RST}")
        return
    tw, th = int(m.group(1)), int(m.group(2))

    if not _defender_check(path, _t):
        return

    from PIL import Image
    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        if force:
            out_img = img.resize((tw, th), Image.LANCZOS)
        else:
            img.thumbnail((tw, th), Image.LANCZOS)
            out_img = img

        out = _out_path(path, "_resized")
        w2, h2 = out_img.size
        _img_save(out_img, out, path, _t, terminal=terminal, replace=replace,
                  msg_key="img_resize_done", w=w2, h=h2)
    finally:
        img.close()


def _img_crop(args: list, _t, terminal=None) -> None:
    if len(args) < 5:
        print(_t("img_crop_usage"))
        return
    clean, flags = _split_flags(args)
    replace = "--replace" in flags
    path = clean[0]
    try:
        x, y, w, h = int(clean[1]), int(clean[2]), int(clean[3]), int(clean[4])
    except (ValueError, IndexError):
        print(f"{RED}{_t('img_crop_bad_args')}{RST}")
        return

    if not _defender_check(path, _t):
        return

    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        iw, ih  = img.size
        box     = (max(0, x), max(0, y), min(iw, x + w), min(ih, y + h))
        out_img = img.crop(box)
        out     = _out_path(path, "_crop")
        _img_save(out_img, out, path, _t, terminal=terminal, replace=replace,
                  msg_key="img_crop_done")
    finally:
        img.close()


def _img_convert(args: list, _t, terminal=None) -> None:
    if len(args) < 2:
        print(_t("img_convert_usage"))
        return
    clean, flags = _split_flags(args)
    replace = "--replace" in flags
    path = clean[0]
    fmt  = clean[1].lower().lstrip(".")

    if not _defender_check(path, _t):
        return

    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        pil_fmt = fmt.upper()
        if pil_fmt in ("JPG", "JPEG") and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
            pil_fmt = "JPEG"

        out = _out_path(path, "", "." + fmt)
        if os.path.abspath(out) == os.path.abspath(path):
            base, _ = os.path.splitext(path)
            out = base + "_conv." + fmt

        try:
            img.save(out, format=pil_fmt)
        except KeyError:
            print(f"{RED}{_t('img_convert_bad_fmt', fmt=fmt)}{RST}")
            return

        digest = _sha256_stamp(out)
        digest_str = f"  {DIM}sha256 {digest[:16]}…{RST}" if digest else ""
        print(f"{GRN}{_t('img_convert_done', src=path, out=out)}{RST}")
        if digest_str:
            print(digest_str)
        if replace:
            _trash_original(path, _t)
    finally:
        img.close()


def _img_thumb(args: list, _t, terminal=None) -> None:
    if not args:
        print(_t("img_thumb_usage"))
        return
    clean, flags = _split_flags(args)
    path    = clean[0]
    size    = 128
    if len(clean) >= 2:
        try:
            size = int(clean[1])
        except ValueError:
            pass

    if not _defender_check(path, _t):
        return

    from PIL import Image
    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        img.thumbnail((size, size), Image.LANCZOS)
        out = _out_path(path, f"_thumb{size}")
        w2, h2 = img.size
        _img_save(img, out, path, _t, terminal=terminal, replace=False,
                  msg_key="img_thumb_done", w=w2, h=h2)
    finally:
        img.close()


def _img_rotate(args: list, _t, terminal=None) -> None:
    if len(args) < 2:
        print(_t("img_rotate_usage"))
        return
    clean, flags = _split_flags(args)
    replace = "--replace" in flags
    path = clean[0]
    try:
        angle = float(clean[1])
    except (ValueError, IndexError):
        print(f"{RED}{_t('img_rotate_bad_angle')}{RST}")
        return

    if not _defender_check(path, _t):
        return

    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        out_img = img.rotate(-angle, expand=True)
        out     = _out_path(path, f"_rot{int(angle)}")
        _img_save(out_img, out, path, _t, terminal=terminal, replace=replace,
                  msg_key="img_rotate_done", angle=angle)
    finally:
        img.close()


def _img_flip(args: list, _t, terminal=None) -> None:
    if len(args) < 2:
        print(_t("img_flip_usage"))
        return
    clean, flags = _split_flags(args)
    replace   = "--replace" in flags
    path      = clean[0]
    direction = clean[1].lower() if len(clean) > 1 else ""

    if not _defender_check(path, _t):
        return

    from PIL import Image
    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        if direction in ("h", "horizontal"):
            out_img = img.transpose(Image.FLIP_LEFT_RIGHT)
            tag = "h"
        elif direction in ("v", "vertical"):
            out_img = img.transpose(Image.FLIP_TOP_BOTTOM)
            tag = "v"
        else:
            print(f"{RED}{_t('img_flip_bad_dir')}{RST}")
            return
        out = _out_path(path, f"_flip{tag}")
        _img_save(out_img, out, path, _t, terminal=terminal, replace=replace,
                  msg_key="img_flip_done")
    finally:
        img.close()


def _img_gray(args: list, _t, terminal=None) -> None:
    if not args:
        print(_t("img_gray_usage"))
        return
    clean, flags = _split_flags(args)
    replace = "--replace" in flags
    path    = clean[0]

    if not _defender_check(path, _t):
        return

    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        out_img = img.convert("L").convert("RGB")
        out     = _out_path(path, "_gray")
        _img_save(out_img, out, path, _t, terminal=terminal, replace=replace,
                  msg_key="img_gray_done")
    finally:
        img.close()


def _img_bright(args: list, _t, terminal=None) -> None:
    if len(args) < 2:
        print(_t("img_bright_usage"))
        return
    clean, flags = _split_flags(args)
    replace = "--replace" in flags
    path = clean[0]
    try:
        factor = float(clean[1])
    except (ValueError, IndexError):
        print(f"{RED}{_t('img_bright_bad_factor')}{RST}")
        return

    if not _defender_check(path, _t):
        return

    from PIL import ImageEnhance
    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        out_img = ImageEnhance.Brightness(img).enhance(factor)
        out     = _out_path(path, "_bright")
        _img_save(out_img, out, path, _t, terminal=terminal, replace=replace,
                  msg_key="img_bright_done", factor=factor)
    finally:
        img.close()


def _img_contrast(args: list, _t, terminal=None) -> None:
    if len(args) < 2:
        print(_t("img_contrast_usage"))
        return
    clean, flags = _split_flags(args)
    replace = "--replace" in flags
    path = clean[0]
    try:
        factor = float(clean[1])
    except (ValueError, IndexError):
        print(f"{RED}{_t('img_contrast_bad_factor')}{RST}")
        return

    if not _defender_check(path, _t):
        return

    from PIL import ImageEnhance
    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        out_img = ImageEnhance.Contrast(img).enhance(factor)
        out     = _out_path(path, "_contrast")
        _img_save(out_img, out, path, _t, terminal=terminal, replace=replace,
                  msg_key="img_contrast_done", factor=factor)
    finally:
        img.close()


def _img_blur(args: list, _t, terminal=None) -> None:
    if not args:
        print(_t("img_blur_usage"))
        return
    clean, flags = _split_flags(args)
    replace = "--replace" in flags
    path   = clean[0]
    radius = 2.0
    if len(clean) >= 2:
        try:
            radius = float(clean[1])
        except ValueError:
            pass

    if not _defender_check(path, _t):
        return

    from PIL import ImageFilter
    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        out_img = img.filter(ImageFilter.GaussianBlur(radius=radius))
        out     = _out_path(path, "_blur")
        _img_save(out_img, out, path, _t, terminal=terminal, replace=replace,
                  msg_key="img_blur_done", radius=radius)
    finally:
        img.close()


def _img_sharpen(args: list, _t, terminal=None) -> None:
    if not args:
        print(_t("img_sharpen_usage"))
        return
    clean, flags = _split_flags(args)
    replace = "--replace" in flags
    path    = clean[0]

    if not _defender_check(path, _t):
        return

    from PIL import ImageFilter
    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    try:
        out_img = img.filter(ImageFilter.SHARPEN)
        out     = _out_path(path, "_sharp")
        _img_save(out_img, out, path, _t, terminal=terminal, replace=replace,
                  msg_key="img_sharpen_done")
    finally:
        img.close()


def _img_ascii(args: list, _t, terminal=None) -> None:
    if not args:
        print(_t("img_ascii_usage"))
        return
    path  = args[0]
    width = 80
    if len(args) >= 2:
        try:
            width = int(args[1])
        except ValueError:
            pass

    img, err = _load_image(path)
    if err:
        print(f"{RED}{err}{RST}")
        return

    chars = " .,:;i1tfLCG08@#"
    try:
        iw, ih = img.size
        ratio  = ih / iw
        height = max(1, int(width * ratio * 0.45))
        thumb  = img.convert("L").resize((width, height))
        pixels = thumb.load()
        print()
        for y in range(height):
            row = ""
            for x in range(width):
                pv = pixels[x, y]
                row += chars[int(pv / 255 * (len(chars) - 1))]
            print(row)
        print()
    except Exception as exc:
        print(f"{RED}{_t('img_ascii_error', exc=exc)}{RST}")
    finally:
        img.close()


def _img_find(args: list, _t, terminal=None) -> None:
    """Szuka plikow graficznych. Deleguje do search.FileSearcher lub fallback os.walk."""
    start      = "."
    ext_filter = None

    i = 0
    while i < len(args):
        if args[i] in ("--ext", "-e") and i + 1 < len(args):
            ext_filter = args[i + 1]
            i += 2
        elif not args[i].startswith("-"):
            start = args[i]
            i += 1
        else:
            i += 1

    start = os.path.abspath(os.path.expanduser(start))
    if not os.path.isdir(start):
        print(f"{RED}{_t('img_find_no_dir', path=start)}{RST}")
        return

    search_exts = (
        {"." + ext_filter.lstrip(".")} if ext_filter else IMG_EXTS
    )

    results: list[str] = []
    svc = _integration.get("search")

    if svc and "FileSearcher" in svc:
        FS = svc["FileSearcher"]
        seen: set[str] = set()
        for ext in search_exts:
            # FileSearcher.search() to generator zwracajacy str (sciezki)
            for path_str in FS.search(
                start_dir=start,
                extension=ext.lstrip("."),
                ignore_errors=True,
            ):
                if path_str not in seen:
                    seen.add(path_str)
                    results.append(path_str)
    else:
        # fallback stdlib bez modulu search
        for root, _, files in os.walk(start):
            for fname in files:
                if os.path.splitext(fname)[1].lower() in search_exts:
                    results.append(os.path.join(root, fname))

    if not results:
        print(f"{YLW}{_t('img_find_none', dir=start)}{RST}")
        return

    results.sort()
    print(f"\n{BOLD}{CYN}{_t('img_find_header', n=len(results), dir=start)}{RST}\n")
    for p in results:
        size = os.path.getsize(p) if os.path.isfile(p) else 0
        ext  = os.path.splitext(p)[1].upper().lstrip(".")
        _w(f"  {YLW}{_pad(ext, 6)}{RST} {_pad(_human_size(size), 10)} {DIM}{p}{RST}\n")
    print()


def _img_batch(args: list, _t, terminal=None) -> None:
    """img batch <operacja> <wzorzec> [dodatkowe_args] [--replace] [--bg]

    --bg  uruchamia wsadowe przetwarzanie jako zadanie w tle (task module).
    """
    if len(args) < 2:
        print(_t("img_batch_usage"))
        return

    clean, flags = _split_flags(args)
    if len(clean) < 2:
        print(_t("img_batch_usage"))
        return

    op         = clean[0]
    pattern    = clean[1]
    extra      = clean[2:]
    replace    = "--replace" in flags
    run_bg     = "--bg" in flags

    files = glob.glob(pattern)
    img_files = [f for f in files
                 if os.path.splitext(f)[1].lower() in IMG_EXTS]

    if not img_files:
        print(f"{YLW}{_t('img_batch_no_files', pattern=pattern)}{RST}")
        return

    # --bg: oddeleguj do task modulu jako zadanie w tle
    if run_bg:
        task_svc = _integration.get("task")
        if task_svc and callable(task_svc.get("get_tasks")):
            # task modul udostepnia get_tasks; uruchamiamy przez spawn terminala
            bg_args = ["img", "batch", op, pattern] + extra
            if replace:
                bg_args.append("--replace")
            try:
                terminal.commands["task"]["func"](["spawn"] + bg_args)
                print(f"{CYN}{_t('img_batch_bg_started', op=op, n=len(img_files))}{RST}")
                return
            except Exception:
                pass  # fallback do synchronicznego
        print(f"{YLW}{_t('img_batch_bg_fallback')}{RST}")

    # Synchroniczne przetwarzanie
    print(f"{CYN}{_t('img_batch_start', n=len(img_files), op=op)}{RST}\n")
    ok_count  = 0
    err_count = 0
    for f in img_files:
        print(f"  {DIM}→ {f}{RST}")
        try:
            op_args = [f] + extra
            if replace:
                op_args.append("--replace")
            _do_operation(op, op_args, _t, terminal=terminal)
            ok_count += 1
        except Exception as exc:
            print(f"    {RED}[ERR: {exc}]{RST}")
            err_count += 1

    summary = _t("img_batch_done", ok=ok_count, err=err_count)
    print(f"\n{GRN}{summary}{RST}\n")

    kind = "ok" if err_count == 0 else ("warn" if ok_count > 0 else "err")
    _integration.notify_event(terminal, summary, kind=kind, title="IMG BATCH")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _do_operation(op: str, op_args: list, _t, terminal=None) -> None:
    dispatch = {
        "info":     _img_info,
        "resize":   _img_resize,
        "crop":     _img_crop,
        "convert":  _img_convert,
        "thumb":    _img_thumb,
        "rotate":   _img_rotate,
        "flip":     _img_flip,
        "gray":     _img_gray,
        "bright":   _img_bright,
        "contrast": _img_contrast,
        "blur":     _img_blur,
        "sharpen":  _img_sharpen,
        "ascii":    _img_ascii,
        "find":     _img_find,
    }
    fn = dispatch.get(op)
    if fn:
        fn(op_args, _t, terminal=terminal)
    else:
        print(f"{RED}{_t('img_unknown_sub', sub=op)}{RST}")


# ---------------------------------------------------------------------------
# setup / teardown
# ---------------------------------------------------------------------------

def setup(terminal) -> None:

    def _t(key, **kw):
        return terminal.t(key, **kw)

    # --- API rejestrowane w _integration -----------------------------------
    # Uzywane przez: analyser.py (_analyse_file), defender.py (_check_image_anomalies)
    _integration.register("imgtools", {
        # Metadane obrazu (bez terminala, bez drukowania)
        "analyse_image": _get_image_report,
        # Predykaty
        "is_image":      lambda path: (
            os.path.splitext(path)[1].lower() in IMG_EXTS
        ),
        "IMG_EXTS":      IMG_EXTS,
        # Operacje (z drukowaniem, uzywaja aktywnego _t i terminal)
        "info":     lambda path: _img_info([path], _t, terminal=terminal),
        "resize":   lambda path, spec: _img_resize([path, spec], _t, terminal=terminal),
        "convert":  lambda path, fmt: _img_convert([path, fmt], _t, terminal=terminal),
        "thumb":    lambda path, size=128: _img_thumb(
            [path, str(size)], _t, terminal=terminal
        ),
        "gray":     lambda path: _img_gray([path], _t, terminal=terminal),
        "blur":     lambda path, r=2.0: _img_blur(
            [path, str(r)], _t, terminal=terminal
        ),
        "sharpen":  lambda path: _img_sharpen([path], _t, terminal=terminal),
    })

    # --- menu modulu -------------------------------------------------------
    def img_menu(_args: list) -> None:
        _w(f"\n{BOLD}{BCYN}  +============================================+{RST}\n")
        _w(f"{BOLD}{BCYN}  |   >>  {_t('img_module_title')}                  |{RST}\n")
        _w(f"{BOLD}{BCYN}  +============================================+{RST}\n\n")

        if not _pil_available():
            _w(f"  {RED}{_t('img_no_pillow')}{RST}\n\n")
            _w(f"  {YLW}pip install Pillow{RST}\n\n")
            return

        cmds = [
            ("img info     <file>",                _t("img_help_info")),
            ("img resize   <file> <WxH>[!]",       _t("img_help_resize")),
            ("img crop     <file> <x> <y> <w> <h>",_t("img_help_crop")),
            ("img convert  <file> <format>",        _t("img_help_convert")),
            ("img thumb    <file> [size]",           _t("img_help_thumb")),
            ("img rotate   <file> <deg>",            _t("img_help_rotate")),
            ("img flip     <file> <h|v>",            _t("img_help_flip")),
            ("img gray     <file>",                  _t("img_help_gray")),
            ("img bright   <file> <factor>",         _t("img_help_bright")),
            ("img contrast <file> <factor>",         _t("img_help_contrast")),
            ("img blur     <file> [radius]",         _t("img_help_blur")),
            ("img sharpen  <file>",                  _t("img_help_sharpen")),
            ("img ascii    <file> [width]",           _t("img_help_ascii")),
            ("img find     [dir] [--ext <ext>]",     _t("img_help_find")),
            ("img batch    <op> <glob> [--bg]",      _t("img_help_batch")),
        ]
        for c, d in cmds:
            _w(f"  {YLW}{_pad(c, 42)}{RST} {DIM}{d}{RST}\n")

        _w(f"\n  {DIM}{_t('img_flag_replace')}{RST}\n")
        _w(f"  {DIM}{_t('img_flag_bg')}{RST}\n")
        _w(f"\n  {DIM}{_t('img_supported_formats')}{RST}\n")
        _w(f"  {DIM}{', '.join(sorted(e.lstrip('.').upper() for e in IMG_EXTS))}{RST}\n\n")

        # Aktywne integracje
        active = [m for m in
                  ("sha256", "defender", "notify", "search", "trash", "task", "analyser")
                  if _integration.get(m)]
        if active:
            _w(f"  {GRN}{_t('img_integrations_active', mods=', '.join(active))}{RST}\n\n")

    # --- glowna komenda img -----------------------------------------------
    def img_command(args: list) -> None:
        if not args:
            img_menu([])
            return

        if not _pil_available():
            print(f"{RED}{_t('img_no_pillow')}{RST}")
            print("  pip install Pillow")
            return

        sub  = args[0].lower()
        rest = args[1:]

        if sub == "batch":
            _img_batch(rest, _t, terminal=terminal)
        else:
            _do_operation(sub, rest, _t, terminal=terminal)

    terminal.register_command(
        "img", img_command,
        description=_t("cmd_img"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal) -> None:
    terminal.commands.pop("img", None)
    try:
        _integration.unregister("imgtools")
    except Exception:
        pass
