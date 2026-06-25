"""SHA-256 checksum module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski
Module: SHA-256  v1.1.0

Oblicza, weryfikuje i porownuje sumy kontrolne SHA-256 plikow.
Wspiera tryb bezpiecznego zerowania klucza po weryfikacji (wipe key).

Komendy:
  sha256 <plik>                   - oblicz sume SHA-256 pliku
  sha256 check <plik> <hash>      - zweryfikuj hash (OK / FAIL)
  sha256 diff <plik_a> <plik_b>   - porownaj dwa pliki przez hash
  sha256 scan [katalog]           - oblicz hashe wszystkich plikow w katalogu
  sha256 save <plik>              - zapisz hash do <plik>.sha256
  sha256 verify <plik>            - zweryfikuj plik wzgledem <plik>.sha256
  sha256 list                     - pokaz zapisane hashe w biezacym katalogu
  sha256 saveall [katalog]        - zapisz hashe wszystkich plikow do SHA256SUMS
  sha256 verifyall [katalog]      - zweryfikuj wszystkie pliki z SHA256SUMS
  sha256 watch <plik> [sek]       - monitoruj plik, alarmuj gdy hash sie zmieni
  sha256 str <tekst>              - oblicz hash bezposrednio z ciagu tekstu
  sha256 export <plik>            - wypisz hash w formacie gotowym do wklejenia
  sha256                          - menu pomocy
"""

import hashlib
import hmac
import os
import sys
import time

from ._shared import (
    ROOT_DIR, CACHE_DIR,
    RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, WHT,
    _w, _pad,
)
from . import _integration

# ---------------------------------------------------------------------------
# Stale
# ---------------------------------------------------------------------------

_VERSION       = "1.1.0"
_HASH_EXT      = ".sha256"
_SUMS_FILE     = "SHA256SUMS"
_CHUNK_SIZE    = 65536   # 64 KB
_CACHE_SUBDIR  = os.path.join(CACHE_DIR, "sha256")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_cache() -> None:
    os.makedirs(_CACHE_SUBDIR, exist_ok=True)


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _compute_hash(path: str) -> tuple[str, float]:
    """Oblicza SHA-256 pliku. Zwraca (hex_digest, czas_sekundy)."""
    h = hashlib.sha256()
    t0 = time.monotonic()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest(), time.monotonic() - t0


def _compute_hash_str(text: str) -> tuple[str, float]:
    """Oblicza SHA-256 ciagu tekstowego (UTF-8). Zwraca (hex_digest, czas_sekundy)."""
    t0 = time.monotonic()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest, time.monotonic() - t0


def _secure_zero(buf: bytearray) -> None:
    """Nadpisuje bufor zerami (zerowanie klucza w pamieci)."""
    for i in range(len(buf)):
        buf[i] = 0


def _compare_hashes(a: str, b: str) -> bool:
    """Porownanie w stalym czasie (odporne na timing attacks)."""
    return hmac.compare_digest(a.lower(), b.lower())


def _load_hashfile(path: str) -> str | None:
    """Wczytuje hash z pliku .sha256 (pierwszy token pierwszej linii)."""
    try:
        with open(path, encoding="utf-8") as f:
            line = f.readline().strip()
        return line.split()[0] if line else None
    except Exception:
        return None


def _save_hashfile(path: str, digest: str, filename: str) -> None:
    """Zapisuje hash w formacie kompatybilnym z sha256sum."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{digest}  {filename}\n")


def _iter_files(directory: str) -> list[str]:
    """Zwraca posortowana liste plikow w katalogu (bez .sha256 i SHA256SUMS)."""
    return sorted(
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and not f.endswith(_HASH_EXT)
        and f != _SUMS_FILE
    )


# ---------------------------------------------------------------------------
# Komendy (istniejace)
# ---------------------------------------------------------------------------

def _cmd_hash(path: str, _t) -> None:
    """sha256 <plik> - oblicz i wyswietl hash."""
    if not os.path.isfile(path):
        _w(f"\n  {RED}{_t('sha256_err_not_found', path=path)}{RST}\n\n")
        return

    name = os.path.basename(path)
    size = os.path.getsize(path)

    _w(f"\n  {BOLD}{BCYN}{_t('sha256_computing', name=name)}{RST}\n\n")
    try:
        digest, elapsed = _compute_hash(path)
    except OSError as exc:
        _w(f"  {RED}{_t('sha256_err_read', exc=exc)}{RST}\n\n")
        return

    _w(f"  {CYN}{_pad(_t('sha256_label_file'),  14)}{RST}{YLW}{name}{RST}\n")
    _w(f"  {CYN}{_pad(_t('sha256_label_size'),  14)}{RST}{DIM}{_human_size(size)}{RST}\n")
    _w(f"  {CYN}{_pad(_t('sha256_label_hash'),  14)}{RST}{WHT}{digest}{RST}\n")
    _w(f"  {CYN}{_pad(_t('sha256_label_time'),  14)}{RST}{DIM}{elapsed*1000:.1f} ms{RST}\n")
    _w("\n")


def _cmd_check(path: str, expected: str, _t) -> None:
    """sha256 check <plik> <hash> - zweryfikuj hash."""
    if not os.path.isfile(path):
        _w(f"\n  {RED}{_t('sha256_err_not_found', path=path)}{RST}\n\n")
        return

    # Bezpieczne zerowanie buforowanego klucza po weryfikacji
    key_buf = bytearray(expected.encode())
    try:
        digest, _ = _compute_hash(path)
        ok = _compare_hashes(digest, expected)
    finally:
        _secure_zero(key_buf)

    name = os.path.basename(path)
    if ok:
        _w(f"\n  {GRN}[V]  {_t('sha256_ok', name=name)}{RST}\n\n")
    else:
        _w(f"\n  {RED}[X]  {_t('sha256_fail', name=name)}{RST}\n")
        _w(f"       {DIM}{_t('sha256_expected')}:{RST} {expected.lower()}\n")
        _w(f"       {DIM}{_t('sha256_computed')}:{RST} {digest}\n\n")
        _integration.notify_event(
            None, f"SHA-256 niezgodny dla pliku: {name}",
            kind="err", title="SHA256",
        )


def _cmd_diff(path_a: str, path_b: str, _t) -> None:
    """sha256 diff <a> <b> - porownaj dwa pliki."""
    for p in (path_a, path_b):
        if not os.path.isfile(p):
            _w(f"\n  {RED}{_t('sha256_err_not_found', path=p)}{RST}\n\n")
            return

    _w(f"\n  {BOLD}{BCYN}{_t('sha256_diff_title')}{RST}\n\n")
    try:
        ha, ta = _compute_hash(path_a)
        hb, tb = _compute_hash(path_b)
    except OSError as exc:
        _w(f"  {RED}{_t('sha256_err_read', exc=exc)}{RST}\n\n")
        return

    sa = os.path.getsize(path_a)
    sb = os.path.getsize(path_b)

    _w(f"  {DIM}A:{RST} {YLW}{os.path.basename(path_a)}{RST}  {DIM}({_human_size(sa)}){RST}\n")
    _w(f"  {DIM}B:{RST} {YLW}{os.path.basename(path_b)}{RST}  {DIM}({_human_size(sb)}){RST}\n\n")
    _w(f"  {CYN}{_pad('A SHA-256:', 12)}{RST}{DIM}{ha}{RST}\n")
    _w(f"  {CYN}{_pad('B SHA-256:', 12)}{RST}{DIM}{hb}{RST}\n\n")

    if _compare_hashes(ha, hb):
        _w(f"  {GRN}[V]  {_t('sha256_diff_identical')}{RST}\n\n")
    else:
        _w(f"  {RED}[X]  {_t('sha256_diff_different')}{RST}\n\n")


def _cmd_scan(directory: str | None, _t) -> None:
    """sha256 scan [katalog] - hashe wszystkich plikow w katalogu."""
    scan_dir = os.path.abspath(directory) if directory else os.getcwd()
    if not os.path.isdir(scan_dir):
        _w(f"\n  {RED}{_t('sha256_err_not_dir', path=scan_dir)}{RST}\n\n")
        return

    _w(f"\n  {BOLD}{BCYN}{_t('sha256_scan_title', path=scan_dir)}{RST}\n\n")

    files = _iter_files(scan_dir)

    if not files:
        _w(f"  {DIM}{_t('sha256_scan_empty')}{RST}\n\n")
        return

    total_size = 0
    for path in files:
        name = os.path.basename(path)
        size = os.path.getsize(path)
        total_size += size
        try:
            digest, _ = _compute_hash(path)
            _w(f"  {DIM}{digest[:16]}...{digest[-8:]}{RST}  {YLW}{_pad(name, 28)}{RST}  {DIM}{_human_size(size)}{RST}\n")
        except OSError:
            _w(f"  {RED}{'?'*16}...{'?'*8}{RST}  {YLW}{_pad(name, 28)}{RST}  {RED}ERR{RST}\n")

    _w(f"\n  {DIM}{_t('sha256_scan_total', files=len(files), size=_human_size(total_size))}{RST}\n\n")


def _cmd_save(path: str, _t) -> None:
    """sha256 save <plik> - zapisz hash do <plik>.sha256."""
    if not os.path.isfile(path):
        _w(f"\n  {RED}{_t('sha256_err_not_found', path=path)}{RST}\n\n")
        return

    try:
        digest, _ = _compute_hash(path)
    except OSError as exc:
        _w(f"\n  {RED}{_t('sha256_err_read', exc=exc)}{RST}\n\n")
        return

    hashfile = path + _HASH_EXT
    try:
        _save_hashfile(hashfile, digest, os.path.basename(path))
        _w(f"\n  {GRN}[V]  {_t('sha256_saved', path=hashfile)}{RST}\n\n")
    except OSError as exc:
        _w(f"\n  {RED}{_t('sha256_err_write', exc=exc)}{RST}\n\n")


def _cmd_verify(path: str, _t) -> None:
    """sha256 verify <plik> - zweryfikuj wzgledem <plik>.sha256."""
    if not os.path.isfile(path):
        _w(f"\n  {RED}{_t('sha256_err_not_found', path=path)}{RST}\n\n")
        return

    hashfile = path + _HASH_EXT
    if not os.path.isfile(hashfile):
        alt = os.path.join(os.path.dirname(path), os.path.basename(path) + _HASH_EXT)
        if os.path.isfile(alt):
            hashfile = alt
        else:
            _w(f"\n  {RED}{_t('sha256_err_no_hashfile', path=hashfile)}{RST}\n\n")
            return

    expected = _load_hashfile(hashfile)
    if not expected:
        _w(f"\n  {RED}{_t('sha256_err_bad_hashfile', path=hashfile)}{RST}\n\n")
        return

    _cmd_check(path, expected, _t)


def _cmd_list(directory: str | None, _t) -> None:
    """sha256 list - pokaz pliki .sha256 w biezacym katalogu."""
    scan_dir = os.path.abspath(directory) if directory else os.getcwd()
    hashfiles = sorted(
        f for f in os.listdir(scan_dir)
        if f.endswith(_HASH_EXT) and os.path.isfile(os.path.join(scan_dir, f))
    )

    if not hashfiles:
        _w(f"\n  {DIM}{_t('sha256_list_empty')}{RST}\n\n")
        return

    _w(f"\n  {BOLD}{BCYN}{_t('sha256_list_title')}{RST}\n\n")
    for hf in hashfiles:
        full = os.path.join(scan_dir, hf)
        digest = _load_hashfile(full) or "?"
        target = hf[:-len(_HASH_EXT)]
        exists = os.path.isfile(os.path.join(scan_dir, target))
        status = f"{GRN}OK{RST}" if exists else f"{RED}??{RST}"
        _w(f"  [{status}] {YLW}{_pad(target, 28)}{RST}  {DIM}{digest[:20]}...{RST}\n")
    _w("\n")


# ---------------------------------------------------------------------------
# Nowe komendy v1.1.0
# ---------------------------------------------------------------------------

def _cmd_saveall(directory: str | None, _t) -> None:
    """sha256 saveall [katalog] - zapisz hashe wszystkich plikow do SHA256SUMS."""
    scan_dir = os.path.abspath(directory) if directory else os.getcwd()
    if not os.path.isdir(scan_dir):
        _w(f"\n  {RED}{_t('sha256_err_not_dir', path=scan_dir)}{RST}\n\n")
        return

    files = _iter_files(scan_dir)
    if not files:
        _w(f"\n  {DIM}{_t('sha256_scan_empty')}{RST}\n\n")
        return

    sums_path = os.path.join(scan_dir, _SUMS_FILE)
    _w(f"\n  {BOLD}{BCYN}{_t('sha256_saveall_title', path=scan_dir)}{RST}\n\n")

    lines = []
    ok_count = 0
    err_count = 0
    for path in files:
        name = os.path.basename(path)
        try:
            digest, _ = _compute_hash(path)
            lines.append(f"{digest}  {name}\n")
            _w(f"  {GRN}+{RST}  {YLW}{_pad(name, 32)}{RST}  {DIM}{digest[:16]}...{RST}\n")
            ok_count += 1
        except OSError as exc:
            _w(f"  {RED}!{RST}  {YLW}{_pad(name, 32)}{RST}  {RED}ERR: {exc}{RST}\n")
            err_count += 1

    try:
        with open(sums_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        _w(f"\n  {GRN}[V]  {_t('sha256_saveall_done', count=ok_count, path=sums_path)}{RST}\n")
        if err_count:
            _w(f"  {YLW}[!]  {_t('sha256_saveall_errors', count=err_count)}{RST}\n")
    except OSError as exc:
        _w(f"\n  {RED}{_t('sha256_err_write', exc=exc)}{RST}\n")
    _w("\n")


def _cmd_verifyall(directory: str | None, _t) -> None:
    """sha256 verifyall [katalog] - zweryfikuj wszystkie pliki z SHA256SUMS."""
    scan_dir = os.path.abspath(directory) if directory else os.getcwd()
    sums_path = os.path.join(scan_dir, _SUMS_FILE)

    if not os.path.isfile(sums_path):
        _w(f"\n  {RED}{_t('sha256_verifyall_no_sums', path=sums_path)}{RST}\n\n")
        return

    _w(f"\n  {BOLD}{BCYN}{_t('sha256_verifyall_title', path=sums_path)}{RST}\n\n")

    ok_count = 0
    fail_count = 0
    miss_count = 0

    try:
        with open(sums_path, encoding="utf-8") as f:
            entries = [line.strip() for line in f if line.strip()]
    except OSError as exc:
        _w(f"  {RED}{_t('sha256_err_read', exc=exc)}{RST}\n\n")
        return

    for entry in entries:
        parts = entry.split(None, 1)
        if len(parts) != 2:
            continue
        expected_hash, name = parts
        # sha256sum moze miec '*' przed nazwa (tryb binarny)
        name = name.lstrip("*").strip()
        filepath = os.path.join(scan_dir, name)

        if not os.path.isfile(filepath):
            _w(f"  {RED}[?]{RST}  {YLW}{_pad(name, 32)}{RST}  {DIM}{_t('sha256_verifyall_missing')}{RST}\n")
            miss_count += 1
            continue

        try:
            digest, _ = _compute_hash(filepath)
        except OSError as exc:
            _w(f"  {RED}[!]{RST}  {YLW}{_pad(name, 32)}{RST}  {RED}ERR{RST}  {DIM}{exc}{RST}\n")
            fail_count += 1
            continue

        if _compare_hashes(digest, expected_hash):
            _w(f"  {GRN}[V]{RST}  {YLW}{_pad(name, 32)}{RST}  {GRN}OK{RST}\n")
            ok_count += 1
        else:
            _w(f"  {RED}[X]{RST}  {YLW}{_pad(name, 32)}{RST}  {RED}FAIL{RST}\n")
            fail_count += 1

    total = ok_count + fail_count + miss_count
    _w(f"\n  {DIM}{'─'*52}{RST}\n")
    _w(f"  {GRN}{_pad(_t('sha256_verifyall_ok'), 20)}{RST}{ok_count}/{total}\n")
    if fail_count:
        _w(f"  {RED}{_pad(_t('sha256_verifyall_fail'), 20)}{RST}{fail_count}\n")
    if miss_count:
        _w(f"  {YLW}{_pad(_t('sha256_verifyall_miss'), 20)}{RST}{miss_count}\n")
    _w("\n")

    if fail_count or miss_count:
        _integration.notify_event(
            None,
            f"verifyall: {ok_count}/{total} OK, {fail_count} niezgodnych, {miss_count} brakuje.",
            kind="err" if fail_count else "warn", title="SHA256",
        )


def _cmd_watch(path: str, interval: int, _t) -> None:
    """sha256 watch <plik> [sek] - monitoruj plik, alarmuj gdy hash sie zmieni."""
    if not os.path.isfile(path):
        _w(f"\n  {RED}{_t('sha256_err_not_found', path=path)}{RST}\n\n")
        return

    name = os.path.basename(path)
    _w(f"\n  {BOLD}{BCYN}{_t('sha256_watch_start', name=name, interval=interval)}{RST}\n")
    _w(f"  {DIM}{_t('sha256_watch_hint')}{RST}\n\n")

    try:
        baseline, _ = _compute_hash(path)
    except OSError as exc:
        _w(f"  {RED}{_t('sha256_err_read', exc=exc)}{RST}\n\n")
        return

    _w(f"  {CYN}{_pad(_t('sha256_watch_baseline'), 16)}{RST}{DIM}{baseline[:32]}...{RST}\n\n")

    check_num = 0
    try:
        while True:
            time.sleep(interval)
            check_num += 1
            ts = time.strftime("%H:%M:%S")
            try:
                current, _ = _compute_hash(path)
            except OSError as exc:
                _w(f"  {RED}[{ts}]  {_t('sha256_err_read', exc=exc)}{RST}\n")
                continue

            if _compare_hashes(current, baseline):
                _w(f"  {GRN}[{ts}] #{check_num:04d}  OK{RST}\n")
            else:
                _w(f"\n  {RED}{BOLD}[{ts}] #{check_num:04d}  {_t('sha256_watch_changed', name=name)}{RST}\n")
                _w(f"  {DIM}{_t('sha256_watch_old')}:{RST} {baseline}\n")
                _w(f"  {DIM}{_t('sha256_watch_new')}:{RST} {current}\n\n")
                _integration.notify_event(
                    None, f"sha256 watch: plik {name} zostal zmodyfikowany!",
                    kind="err", title="SHA256 WATCH",
                )
                baseline = current
    except KeyboardInterrupt:
        _w(f"\n\n  {DIM}{_t('sha256_watch_stopped', checks=check_num)}{RST}\n\n")


def _cmd_str(text: str, _t) -> None:
    """sha256 str <tekst> - oblicz hash z ciagu tekstowego."""
    digest, elapsed = _compute_hash_str(text)

    _w(f"\n  {BOLD}{BCYN}{_t('sha256_str_title')}{RST}\n\n")
    _w(f"  {CYN}{_pad(_t('sha256_str_label_input'), 14)}{RST}{YLW}{text!r}{RST}\n")
    _w(f"  {CYN}{_pad(_t('sha256_label_hash'),      14)}{RST}{WHT}{digest}{RST}\n")
    _w(f"  {CYN}{_pad(_t('sha256_str_label_enc'),   14)}{RST}{DIM}UTF-8{RST}\n")
    _w(f"  {CYN}{_pad(_t('sha256_label_time'),       14)}{RST}{DIM}{elapsed*1000:.3f} ms{RST}\n")
    _w("\n")


def _cmd_export(path: str, _t) -> None:
    """sha256 export <plik> - wypisz hash w formatach gotowych do wklejenia."""
    if not os.path.isfile(path):
        _w(f"\n  {RED}{_t('sha256_err_not_found', path=path)}{RST}\n\n")
        return

    name = os.path.basename(path)
    try:
        digest, _ = _compute_hash(path)
    except OSError as exc:
        _w(f"\n  {RED}{_t('sha256_err_read', exc=exc)}{RST}\n\n")
        return

    _w(f"\n  {BOLD}{BCYN}{_t('sha256_export_title', name=name)}{RST}\n\n")

    # Format sha256sum (Unix standard)
    _w(f"  {DIM}sha256sum:{RST}\n")
    _w(f"  {WHT}{digest}  {name}{RST}\n\n")

    # Format Windows CertUtil
    _w(f"  {DIM}CertUtil / PowerShell:{RST}\n")
    _w(f"  {WHT}{digest.upper()}{RST}\n\n")

    # Sama wartosc hasha (do kopiowania)
    _w(f"  {DIM}hash only:{RST}\n")
    _w(f"  {WHT}{digest}{RST}\n\n")


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

def _menu(_t) -> None:
    _w(f"\n{BOLD}{BCYN}  +==========================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |  #  {_t('sha256_menu_title'):<36}|{RST}\n")
    _w(f"{BOLD}{BCYN}  +==========================================+{RST}\n\n")
    cmds = [
        ("sha256 <plik>",               _t("sha256_help_hash")),
        ("sha256 check <plik> <hash>",  _t("sha256_help_check")),
        ("sha256 diff <a> <b>",         _t("sha256_help_diff")),
        ("sha256 scan [katalog]",        _t("sha256_help_scan")),
        ("sha256 save <plik>",           _t("sha256_help_save")),
        ("sha256 verify <plik>",         _t("sha256_help_verify")),
        ("sha256 list",                  _t("sha256_help_list")),
        ("sha256 saveall [katalog]",     _t("sha256_help_saveall")),
        ("sha256 verifyall [katalog]",   _t("sha256_help_verifyall")),
        ("sha256 watch <plik> [sek]",    _t("sha256_help_watch")),
        ("sha256 str <tekst>",           _t("sha256_help_str")),
        ("sha256 export <plik>",         _t("sha256_help_export")),
    ]
    for cmd, desc in cmds:
        _w(f"  {YLW}{_pad(cmd, 34)}{RST} {DIM}{desc}{RST}\n")
    _w(f"\n  {DIM}v{_VERSION}  |  polsoft.ITS(TM){RST}\n\n")


# ---------------------------------------------------------------------------
# setup / teardown
# ---------------------------------------------------------------------------

def setup(terminal) -> None:
    _ensure_cache()

    # Rejestracja w _integration - inne moduly moga uzyc SHA-256 bez importu
    try:
        from . import _integration
        _integration.register("sha256", {
            "compute":  _compute_hash,
            "compute_str": _compute_hash_str,
            "compare":  _compare_hashes,
            "load":     _load_hashfile,
            "save":     _save_hashfile,
        })
    except Exception:
        pass

    def _t(key: str, **kw):
        return terminal.t(key, **kw)

    def sha256_cmd(args: list) -> None:
        if not args:
            _menu(_t)
            return

        sub = args[0].lower()

        if sub == "check":
            if len(args) < 3:
                _w(f"\n  {RED}{_t('sha256_usage_check')}{RST}\n\n")
                return
            _cmd_check(os.path.abspath(args[1]), args[2], _t)

        elif sub == "diff":
            if len(args) < 3:
                _w(f"\n  {RED}{_t('sha256_usage_diff')}{RST}\n\n")
                return
            _cmd_diff(os.path.abspath(args[1]), os.path.abspath(args[2]), _t)

        elif sub == "scan":
            _cmd_scan(args[1] if len(args) > 1 else None, _t)

        elif sub == "save":
            if len(args) < 2:
                _w(f"\n  {RED}{_t('sha256_usage_save')}{RST}\n\n")
                return
            _cmd_save(os.path.abspath(args[1]), _t)

        elif sub == "verify":
            if len(args) < 2:
                _w(f"\n  {RED}{_t('sha256_usage_verify')}{RST}\n\n")
                return
            _cmd_verify(os.path.abspath(args[1]), _t)

        elif sub == "list":
            _cmd_list(args[1] if len(args) > 1 else None, _t)

        # --- Nowe komendy v1.1.0 ---

        elif sub == "saveall":
            _cmd_saveall(args[1] if len(args) > 1 else None, _t)

        elif sub == "verifyall":
            _cmd_verifyall(args[1] if len(args) > 1 else None, _t)

        elif sub == "watch":
            if len(args) < 2:
                _w(f"\n  {RED}{_t('sha256_usage_watch')}{RST}\n\n")
                return
            try:
                interval = int(args[2]) if len(args) > 2 else 5
                if interval < 1:
                    raise ValueError
            except ValueError:
                _w(f"\n  {RED}{_t('sha256_usage_watch')}{RST}\n\n")
                return
            _cmd_watch(os.path.abspath(args[1]), interval, _t)

        elif sub == "str":
            if len(args) < 2:
                _w(f"\n  {RED}{_t('sha256_usage_str')}{RST}\n\n")
                return
            # Sklej wszystkie tokeny (pozwala na spacje w tekscie)
            _cmd_str(" ".join(args[1:]), _t)

        elif sub == "export":
            if len(args) < 2:
                _w(f"\n  {RED}{_t('sha256_usage_export')}{RST}\n\n")
                return
            _cmd_export(os.path.abspath(args[1]), _t)

        else:
            # Traktuj jako sciezke do pliku
            _cmd_hash(os.path.abspath(args[0]), _t)

    terminal.register_command(
        "sha256", sha256_cmd,
        description=_t("sha256_cmd_desc"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal) -> None:
    terminal.commands.pop("sha256", None)
    try:
        from . import _integration
        _integration.unregister("sha256")
    except Exception:
        pass
