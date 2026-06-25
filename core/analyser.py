"""Analyser module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski
Module: Analyser  v1.1.0

Analizuje pliki skryptow, narzedzi i dowolnych plikow tekstowych.
Pelna integracja z modulami core: scripts, runner, tools, search, cache, lang.

Komendy:
  analyse <plik>              - pelna analiza pliku (typ, rozmiar, linie, tokeny, hash, ...)
  analyse scan [katalog]      - skanuj katalog scripts/ lub wskazany kat. i podsumuj
  analyse diff <a> <b>        - porownaj dwa pliki (linie, rozmiar, hash)
  analyse stats               - statystyki globalne EcoSystem (skrypty, narzedzia, cache)
  analyse lint <plik> [--strict] - linting (10 regul regex + 14 regul AST)
  analyse deps <plik>         - wykryj importy/zaleznosci w pliku Python/JS/Bash
  analyse export [plik]       - eksportuj ostatni raport do JSON
  analyse syntax <plik>       - sprawdz skladnie (.py/.js/.sh/.ps1) — OK/FAIL
  analyse lines <plik>        - linie kodu / komentarze / puste / funkcje / klasy
  analyse imports <plik>      - wyswietl importy z kontekstem (module, alias)
  analyse functions <plik>    - lista funkcji z metrykami (CC, glebokos, doc, async)
  analyse classes <plik>      - lista klas (metody, class_vars, bazy, dekoratory)
  analyse complexity <plik>   - CC + Maintainability Index + bar chart top funkcji
  analyse find <wzorzec> <ext> - szukaj regex w plikach po rozszerzeniu
  analyse report <plik> [--json] - pelny raport tekstowy / eksport JSON
  analyser                    - alias -> menu

Integracja:
  - scripts module  : pobiera liste skryptow z SCRIPTS_DIR
  - runner module   : korzysta z PLUGINS / _EXT_MAP do rozpoznania typu
  - tools module    : uwzglednia narzedzia z TOOLS_DIR
  - search module   : uzywa FileSearcher do skanowania
  - cache module    : zapisuje raporty w .cache/analyser/
  - lang module     : pelna i18n przez terminal.t()
"""

import ast
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- ANSI --------------------------------------------------------------------




from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad, _ansi_re


# --- Sciezki -----------------------------------------------------------------

_CACHE_DIR   = os.path.join(CACHE_DIR, "analyser")
_REPORT_FILE = os.path.join(_CACHE_DIR, "last_report.json")


def _ensure_cache() -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)


# --- Integracja z modulami core ----------------------------------------------

def _get_scripts_dir() -> str:
    """Pobiera scripts_dir z rejestru _integration (core.scripts)."""
    from . import _integration as _intg
    d = _intg.call("scripts", "scripts_dir")
    return d if d else os.path.join(ROOT_DIR, "scripts")


def _get_tools_dir() -> str:
    """Pobiera tools_dir z rejestru _integration (core.tools)."""
    from . import _integration as _intg
    d = _intg.call("tools", "tools_dir")
    return d if d else os.path.join(ROOT_DIR, "tools")


def _get_ext_map() -> dict:
    """Pobiera ext_map z core.runner przez rejestr _integration."""
    from . import _integration as _intg
    svc = _intg.get("runner")
    return svc.get("ext_map", {}) if svc else {}


def _get_file_searcher():
    """Pobiera FileSearcher z core.search przez _integration."""
    from . import _integration as _intg
    svc = _intg.get("search")
    if svc and svc.get("FileSearcher"):
        return svc["FileSearcher"]
    # fallback: bezposredni import
    try:
        from .search import FileSearcher
        return FileSearcher
    except Exception:
        return None


# --- Pomocnicze --------------------------------------------------------------

_SIZE_UNITS = ("B", "KB", "MB", "GB")


def _human_size(n: int) -> str:
    v = float(n)
    for unit in _SIZE_UNITS:
        if v < 1024:
            return f"{v:.0f} {unit}" if unit == "B" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB"


def _file_hash(path: str, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "?"


def _count_lines(path: str) -> tuple[int, int, int]:
    """Zwraca (total_lines, blank_lines, comment_lines) dla pliku tekstowego."""
    total = blank = comment = 0
    ext = os.path.splitext(path)[1].lower()
    comment_markers = {
        ".py": "#", ".sh": "#", ".bash": "#", ".zsh": "#", ".fish": "#",
        ".js": "//", ".ts": "//", ".mjs": "//", ".cjs": "//",
        ".bat": "REM", ".cmd": "REM",
        ".ps1": "#",
        ".rb": "#", ".lua": "--", ".r": "#",
        ".c": "//", ".cpp": "//", ".cs": "//", ".go": "//", ".swift": "//",
    }
    marker = comment_markers.get(ext, "#")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                total += 1
                stripped = line.strip()
                if not stripped:
                    blank += 1
                elif stripped.startswith(marker):
                    comment += 1
    except Exception:
        pass
    return total, blank, comment


def _detect_encoding(path: str) -> str:
    try:
        with open(path, "rb") as f:
            raw = f.read(4096)
        if raw.startswith(b'\xef\xbb\xbf'):
            return "UTF-8 BOM"
        try:
            raw.decode("utf-8")
            return "UTF-8"
        except UnicodeDecodeError:
            pass
        try:
            raw.decode("cp1250")
            return "CP1250 (probable)"
        except UnicodeDecodeError:
            return "Binary / Unknown"
    except Exception:
        return "?"


def _detect_line_endings(path: str) -> str:
    try:
        with open(path, "rb") as f:
            raw = f.read(8192)
        crlf = raw.count(b'\r\n')
        lf   = raw.count(b'\n') - crlf
        cr   = raw.count(b'\r') - crlf
        if crlf and not lf and not cr:
            return "CRLF (Windows)"
        if lf and not crlf and not cr:
            return "LF (Unix)"
        if cr and not crlf and not lf:
            return "CR (old Mac)"
        if crlf or lf or cr:
            return "Mixed"
        return "N/A"
    except Exception:
        return "?"


def _token_count(path: str) -> int:
    """Prosta heurystyka: liczba tokenow (slow rozdzielonych bialymi znakami)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return len(f.read().split())
    except Exception:
        return 0


# --- Analiza pliku -----------------------------------------------------------

def _analyse_file(path: str) -> dict:
    """Zbiera wszystkie metadane analizowanego pliku."""
    path = os.path.abspath(path)
    ext  = os.path.splitext(path)[1].lower()
    ext_map  = _get_ext_map()
    plugin   = ext_map.get(ext, "unknown")

    # -- delegacja do imgtools dla plikow graficznych ----------------------
    _IMG_EXTS = {
        ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif",
        ".tiff", ".tif", ".ico", ".ppm", ".pgm", ".pbm",
    }
    if ext in _IMG_EXTS:
        from . import _integration as _intg
        try:
            img_data = _intg.call("imgtools", "analyse_image", path)
            if img_data:
                stat = os.stat(path)
                size = stat.st_size
                mtime = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)
                )
                return {
                    "path":          path,
                    "name":          os.path.basename(path),
                    "ext":           ext or "(none)",
                    "plugin":        "image",
                    "size_bytes":    size,
                    "size_human":    _human_size(size),
                    "mtime":         mtime,
                    "encoding":      "binary",
                    "line_endings":  "-",
                    "lines_total":   0,
                    "lines_blank":   0,
                    "lines_comment": 0,
                    "lines_code":    0,
                    "tokens":        0,
                    "sha256":        _file_hash(path, "sha256"),
                    "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
                    # dane specyficzne dla obrazu
                    "img_width":     img_data.get("width"),
                    "img_height":    img_data.get("height"),
                    "img_mode":      img_data.get("mode"),
                    "img_format":    img_data.get("format"),
                    "img_exif":      img_data.get("exif", {}),
                }
        except Exception:
            pass  # fallback do normalnej sciezki ponizej
    # -- koniec delegacji imgtools -----------------------------------------

    stat = os.stat(path)
    size = stat.st_size
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))

    lines, blank, comments = _count_lines(path)
    code_lines = max(0, lines - blank - comments)

    report = {
        "path":          path,
        "name":          os.path.basename(path),
        "ext":           ext or "(none)",
        "plugin":        plugin,
        "size_bytes":    size,
        "size_human":    _human_size(size),
        "mtime":         mtime,
        "encoding":      _detect_encoding(path),
        "line_endings":  _detect_line_endings(path),
        "lines_total":   lines,
        "lines_blank":   blank,
        "lines_comment": comments,
        "lines_code":    code_lines,
        "tokens":        _token_count(path),
        "sha256":        _file_hash(path, "sha256"),
        "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return report


def _print_report(report: dict, _t) -> None:
    name = report["name"]
    ext  = report["ext"]
    plugin = report["plugin"]
    _w(f"\n{BOLD}{BCYN}  +==========================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |  ?  {_t('analyser_report_title'):<36}|{RST}\n")
    _w(f"{BOLD}{BCYN}  +==========================================+{RST}\n\n")

    fields = [
        (_t("analyser_field_name"),      f"{YLW}{name}{RST}"),
        (_t("analyser_field_path"),      f"{DIM}{report['path']}{RST}"),
        (_t("analyser_field_ext"),       f"{CYN}{ext}{RST}"),
        (_t("analyser_field_plugin"),    f"{MGT}{plugin}{RST}"),
        (_t("analyser_field_size"),      f"{WHT}{report['size_human']}{RST}  {DIM}({report['size_bytes']:,} B){RST}"),
        (_t("analyser_field_mtime"),     f"{DIM}{report['mtime']}{RST}"),
        (_t("analyser_field_encoding"),  f"{DIM}{report['encoding']}{RST}"),
        (_t("analyser_field_endings"),   f"{DIM}{report['line_endings']}{RST}"),
        (_t("analyser_field_lines"),     f"{WHT}{report['lines_total']}{RST}  {DIM}({_t('analyser_lines_breakdown', code=report['lines_code'], blank=report['lines_blank'], comment=report['lines_comment'])}){RST}"),
        (_t("analyser_field_tokens"),    f"{WHT}{report['tokens']:,}{RST}"),
        (_t("analyser_field_sha256"),    f"{DIM}{report['sha256'][:16]}...{RST}"),
    ]
    for k, v in fields:
        _w(f"  {CYN}{_pad(k+':', 18)}{RST}{v}\n")

    # --- dane specyficzne dla obrazu (delegowane przez imgtools) ----------
    if plugin == "image":
        w2 = report.get("img_width")
        h2 = report.get("img_height")
        if w2 and h2:
            _w(f"\n  {BOLD}{CYN}  --- IMAGE ---{RST}\n")
            _w(f"  {CYN}{_pad('Wymiary:', 18)}{RST}{WHT}{w2} x {h2} px{RST}\n")
            _w(f"  {CYN}{_pad('Tryb:', 18)}{RST}{DIM}{report.get('img_mode','?')}{RST}\n")
            _w(f"  {CYN}{_pad('Format:', 18)}{RST}{DIM}{report.get('img_format','?')}{RST}\n")
            exif = report.get("img_exif", {})
            if exif:
                _w(f"  {CYN}{_pad('EXIF:', 18)}{RST}")
                pairs = ", ".join(f"{k}={v[:20]}" for k, v in list(exif.items())[:4])
                _w(f"{DIM}{pairs}{RST}\n")
        _w(f"\n  {DIM}(uzyj 'img info {report['name']}' aby zobaczyc pelne dane){RST}\n")
    _w("\n")


# --- Analiza skladni (lint) ---------------------------------------------------

def _lint_file(path: str, _t) -> bool:
    """Podstawowe sprawdzenie skladni. Zwraca True gdy OK."""
    ext = os.path.splitext(path)[1].lower()
    _w(f"\n  {BOLD}{CYN}{_t('analyser_lint_checking', name=os.path.basename(path))}{RST}\n\n")

    if ext == ".py":
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                src = f.read()
            ast.parse(src, filename=path)
            _w(f"  {GRN}[V]  {_t('analyser_lint_ok_py')}{RST}\n\n")
            return True
        except SyntaxError as e:
            _w(f"  {RED}[X]  {_t('analyser_lint_syntax_err', line=e.lineno, msg=e.msg)}{RST}\n\n")
            return False
        except Exception as e:
            _w(f"  {RED}[X]  {_t('analyser_lint_err', exc=e)}{RST}\n\n")
            return False

    if ext == ".json":
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                json.load(f)
            _w(f"  {GRN}[V]  {_t('analyser_lint_ok_json')}{RST}\n\n")
            return True
        except json.JSONDecodeError as e:
            _w(f"  {RED}[X]  {_t('analyser_lint_json_err', line=e.lineno, msg=e.msg)}{RST}\n\n")
            return False

    # Heurystyka dla .sh - sprawdz podstawowe problemy
    if ext in (".sh", ".bash"):
        issues = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            for i, line in enumerate(lines, 1):
                if re.search(r'[^\\]\$[A-Za-z_][A-Za-z0-9_]*(?<!["\'])', line):
                    pass  # OK
                if line.rstrip().endswith("\\") and i == len(lines):
                    issues.append(_t("analyser_lint_sh_trailing_bs", line=i))
            if not issues:
                _w(f"  {GRN}[V]  {_t('analyser_lint_ok_sh')}{RST}\n\n")
                return True
            for issue in issues:
                _w(f"  {YLW}[!]  {issue}{RST}\n")
            _w("\n")
            return False
        except Exception as e:
            _w(f"  {RED}[X]  {_t('analyser_lint_err', exc=e)}{RST}\n\n")
            return False

    _w(f"  {DIM}{_t('analyser_lint_no_support', ext=ext)}{RST}\n\n")
    return True


# --- Wykrywanie zaleznosci ----------------------------------------------------

def _deps_python(path: str) -> list[str]:
    imports = []
    src = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
        tree = ast.parse(src, filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
    except Exception:
        # fallback: regex (src moze byc pusty jesli open() rzucil wyjatek)
        if src:
            for m in re.finditer(r'^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_.]*)', src, re.MULTILINE):
                imports.append(m.group(1).split(".")[0])
    return sorted(set(imports))


def _deps_js(path: str) -> list[str]:
    deps = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
        for m in re.finditer(r'''require\s*\(\s*['"]([^'"./][^'"]*)['"]\s*\)''', src):
            deps.append(m.group(1))
        for m in re.finditer(r'''from\s+['"]([^'"./][^'"]*)['"]\s*''', src):
            deps.append(m.group(1))
    except Exception:
        pass
    return sorted(set(deps))


def _deps_bash(path: str) -> list[str]:
    deps = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
        # source / . / command wywolania
        for m in re.finditer(r'^(?:source|\.|exec)\s+([^\s;&#]+)', src, re.MULTILINE):
            deps.append(m.group(1))
        # pierwsze slowo kazdej linii (komendy zewnetrzne) - uproszczone
        for m in re.finditer(r'^([a-z][a-z0-9_-]+)\s', src, re.MULTILINE):
            cmd = m.group(1)
            if cmd not in {"if", "then", "else", "fi", "for", "do", "done",
                           "while", "case", "esac", "echo", "exit", "return",
                           "export", "local", "read", "cd", "set", "unset"}:
                deps.append(cmd)
    except Exception:
        pass
    return sorted(set(deps))


def _analyse_deps(path: str, _t) -> None:
    ext  = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    _w(f"\n  {BOLD}{CYN}{_t('analyser_deps_header', name=name)}{RST}\n\n")

    if ext == ".py":
        deps = _deps_python(path)
        label = "Python imports"
    elif ext in (".js", ".mjs", ".cjs", ".ts"):
        deps = _deps_js(path)
        label = "Node.js requires / imports"
    elif ext in (".sh", ".bash", ".zsh", ".fish"):
        deps = _deps_bash(path)
        label = "Bash dependencies"
    else:
        _w(f"  {DIM}{_t('analyser_deps_no_support', ext=ext)}{RST}\n\n")
        return

    if not deps:
        _w(f"  {DIM}{_t('analyser_deps_none')}{RST}\n\n")
        return

    _w(f"  {DIM}{label} ({len(deps)}):{RST}\n\n")
    for dep in deps:
        _w(f"    {YLW}*{RST} {dep}\n")
    _w("\n")


# --- Diff ---------------------------------------------------------------------

def _analyse_diff(path_a: str, path_b: str, _t) -> None:
    for p in (path_a, path_b):
        if not os.path.isfile(p):
            _w(f"\n  {RED}{_t('analyser_diff_not_found', path=p)}{RST}\n\n")
            return

    ra = _analyse_file(path_a)
    rb = _analyse_file(path_b)

    _w(f"\n  {BOLD}{BCYN}{_t('analyser_diff_title')}{RST}\n\n")
    _w(f"  {DIM}{'A:':<6}{RST}{YLW}{ra['name']}{RST}  {DIM}({ra['size_human']}){RST}\n")
    _w(f"  {DIM}{'B:':<6}{RST}{YLW}{rb['name']}{RST}  {DIM}({rb['size_human']}){RST}\n\n")

    size_diff = rb['size_bytes'] - ra['size_bytes']
    line_diff = rb['lines_total'] - ra['lines_total']
    same_hash = ra['sha256'] == rb['sha256']

    def _delta(v: int) -> str:
        if v > 0:  return f"{GRN}+{v}{RST}"
        if v < 0:  return f"{RED}{v}{RST}"
        return f"{DIM}={RST}"

    rows = [
        (_t("analyser_diff_size"),    ra['size_human'],        rb['size_human'],        _delta(size_diff)),
        (_t("analyser_diff_lines"),   str(ra['lines_total']),  str(rb['lines_total']),  _delta(line_diff)),
        (_t("analyser_diff_code"),    str(ra['lines_code']),   str(rb['lines_code']),   _delta(rb['lines_code'] - ra['lines_code'])),
        (_t("analyser_diff_blank"),   str(ra['lines_blank']),  str(rb['lines_blank']),  _delta(rb['lines_blank'] - ra['lines_blank'])),
        (_t("analyser_diff_comment"), str(ra['lines_comment']),str(rb['lines_comment']),_delta(rb['lines_comment'] - ra['lines_comment'])),
        (_t("analyser_diff_tokens"),  str(ra['tokens']),       str(rb['tokens']),       _delta(rb['tokens'] - ra['tokens'])),
        (_t("analyser_diff_enc"),     ra['encoding'],          rb['encoding'],          ""),
        (_t("analyser_diff_ends"),    ra['line_endings'],      rb['line_endings'],      ""),
    ]

    _w(f"  {BOLD}{DIM}{_t('analyser_diff_col_feat'):<16}{_t('analyser_diff_col_a'):>14}   {_t('analyser_diff_col_b'):>14}   {_t('analyser_diff_col_delta'):>10}{RST}\n")
    _w(f"  {DIM}{'-'*56}{RST}\n")
    for label, va, vb, delta in rows:
        _w(f"  {CYN}{_pad(label, 16)}{RST}{_pad(va, 16)}{_pad(vb, 16)}{delta}\n")

    _w(f"\n  {_t('analyser_diff_identical') if same_hash else _t('analyser_diff_different')}\n\n")


# --- Skan katalogu -----------------------------------------------------------

def _analyse_scan(directory: Optional[str], _t) -> None:
    if directory:
        scan_dir = os.path.abspath(directory)
    else:
        scan_dir = _get_scripts_dir()

    if not os.path.isdir(scan_dir):
        _w(f"\n  {RED}{_t('analyser_scan_not_found', path=scan_dir)}{RST}\n\n")
        return

    FileSearcher = _get_file_searcher()
    ext_map = _get_ext_map()

    _w(f"\n  {BOLD}{BCYN}{_t('analyser_scan_title', path=scan_dir)}{RST}\n\n")

    if FileSearcher:
        files = list(FileSearcher.search(start_dir=scan_dir, pattern="*"))
    else:
        files = []
        for root, _, fnames in os.walk(scan_dir):
            for fname in fnames:
                files.append(os.path.join(root, fname))

    if not files:
        _w(f"  {DIM}{_t('analyser_scan_empty')}{RST}\n\n")
        return

    by_ext: dict[str, list] = {}
    total_size = 0
    total_lines = 0
    for fpath in files:
        ext = os.path.splitext(fpath)[1].lower() or "(none)"
        by_ext.setdefault(ext, []).append(fpath)
        try:
            total_size += os.path.getsize(fpath)
            lines, _, _ = _count_lines(fpath)
            total_lines += lines
        except Exception:
            pass

    _w(f"  {BOLD}{DIM}{_t('analyser_scan_col_ext'):<14}{_t('analyser_scan_col_files'):>8}   {_t('analyser_scan_col_plugin'):<14}{RST}\n")
    _w(f"  {DIM}{'-'*40}{RST}\n")
    for ext in sorted(by_ext, key=lambda x: -len(by_ext[x])):
        count  = len(by_ext[ext])
        plugin = ext_map.get(ext, DIM + "-" + RST)
        _w(f"  {CYN}{_pad(ext, 14)}{RST}{WHT}{count:>8}{RST}   {MGT}{plugin}{RST}\n")

    _w(f"\n  {DIM}{_t('analyser_scan_total', files=len(files), size=_human_size(total_size), lines=total_lines)}{RST}\n\n")


# --- Statystyki globalne ------------------------------------------------------

def _dir_stats(d: str) -> tuple[int, int]:
    """Zlicza pliki i laczny rozmiar katalogu rekurencyjnie."""
    total_f = total_s = 0
    if os.path.isdir(d):
        for root, _, files in os.walk(d):
            for f in files:
                try:
                    total_s += os.path.getsize(os.path.join(root, f))
                    total_f += 1
                except Exception:
                    pass
    return total_f, total_s


def _analyse_stats(_t) -> None:
    scripts_dir = _get_scripts_dir()
    tools_dir   = _get_tools_dir()
    cache_dir   = os.path.join(ROOT_DIR, ".cache")

    sc_f, sc_s = _dir_stats(scripts_dir)
    to_f, to_s = _dir_stats(tools_dir)
    ca_f, ca_s = _dir_stats(cache_dir)
    an_f, an_s = _dir_stats(_CACHE_DIR)

    _w(f"\n  {BOLD}{BCYN}{_t('analyser_stats_title')}{RST}\n\n")
    rows = [
        (_t("analyser_stats_scripts"),  sc_f, _human_size(sc_s), scripts_dir),
        (_t("analyser_stats_tools"),    to_f, _human_size(to_s), tools_dir),
        (_t("analyser_stats_cache"),    ca_f, _human_size(ca_s), cache_dir),
        (_t("analyser_stats_reports"),  an_f, _human_size(an_s), _CACHE_DIR),
    ]
    _w(f"  {BOLD}{DIM}{_t('analyser_stats_col_cat'):<20}{_t('analyser_stats_col_files'):>7}   {_t('analyser_stats_col_size')}{RST}\n")
    _w(f"  {DIM}{'-'*48}{RST}\n")
    for label, cnt, sz, path in rows:
        exists = os.path.isdir(path)
        status = "" if exists else f"  {RED}[missing]{RST}"
        _w(f"  {CYN}{_pad(label, 20)}{RST}{WHT}{cnt:>7}{RST}   {DIM}{sz}{RST}{status}\n")
    _w("\n")


# --- Export raportu ----------------------------------------------------------

def _export_report(dest: Optional[str], _t) -> None:
    _ensure_cache()
    if not os.path.exists(_REPORT_FILE):
        _w(f"\n  {YLW}{_t('analyser_export_no_report')}{RST}\n\n")
        return
    try:
        with open(_REPORT_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if dest is None:
            ts   = time.strftime("%Y%m%d_%H%M%S")
            dest = os.path.join(os.getcwd(), f"analyser_report_{ts}.json")
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _w(f"\n  {GRN}[V]  {_t('analyser_export_done', path=dest)}{RST}\n\n")
    except Exception as e:
        _w(f"\n  {RED}{_t('analyser_export_err', exc=e)}{RST}\n\n")


def _save_report(report: dict) -> None:
    _ensure_cache()
    try:
        with open(_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# --- Menu ---------------------------------------------------------------------

def _menu(_t) -> None:
    _w(f"\n{BOLD}{BCYN}  +==========================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |  ?  {_t('analyser_menu_title'):<36}|{RST}\n")
    _w(f"{BOLD}{BCYN}  +==========================================+{RST}\n\n")
    cmds = [
        ("analyse <plik>",              _t("analyser_help_analyse")),
        ("analyse scan [katalog]",      _t("analyser_help_scan")),
        ("analyse diff <a> <b>",        _t("analyser_help_diff")),
        ("analyse stats",               _t("analyser_help_stats")),
        ("analyse lint <plik>",         _t("analyser_help_lint")),
        ("analyse deps <plik>",         _t("analyser_help_deps")),
        ("analyse export [plik]",       _t("analyser_help_export")),
        ("analyse syntax <plik>",       _t("analyser_help_syntax")),
        ("analyse lines <plik>",        _t("analyser_help_lines")),
        ("analyse imports <plik>",      _t("analyser_help_imports")),
        ("analyse functions <plik>",    _t("analyser_help_functions")),
        ("analyse classes <plik>",      _t("analyser_help_classes")),
        ("analyse complexity <plik>",   _t("analyser_help_complexity")),
        ("analyse find <wzorzec> <ext>",_t("analyser_help_find")),
        ("analyse report <plik>",       _t("analyser_help_report")),
        ("analyser",                    _t("analyser_help_alias")),
    ]
    for c, d in cmds:
        _w(f"  {YLW}{_pad(c, 32)}{RST} {DIM}{d}{RST}\n")
    _w(f"\n  {DIM}{_t('analyser_menu_hint')}{RST}\n\n")


# --- Glowna komenda ----------------------------------------------------------

def _cmd_analyse(args: list, _t) -> None:
    if not args:
        _menu(_t)
        return

    sub = args[0].lower()

    # analyse scan [katalog]
    if sub == "scan":
        _analyse_scan(args[1] if len(args) > 1 else None, _t)
        return

    # analyse diff <a> <b>
    if sub == "diff":
        if len(args) < 3:
            _w(f"\n  {RED}{_t('analyser_diff_usage')}{RST}\n\n")
            return
        _analyse_diff(args[1], args[2], _t)
        return

    # analyse stats
    if sub == "stats":
        _analyse_stats(_t)
        return

    # analyse lint <plik> [--strict]
    if sub == "lint":
        if len(args) < 2:
            _w(f"\n  {RED}{_t('analyser_lint_usage')}{RST}\n\n")
            return
        path = os.path.abspath(args[1])
        if not os.path.isfile(path):
            _w(f"\n  {RED}{_t('analyser_file_not_found', path=path)}{RST}\n\n")
            return
        _lint_file_v2(path, args[2:], _t)
        return

    # analyse syntax <plik>
    if sub == "syntax":
        _cmd_syntax(args[1:], _t)
        return

    # analyse lines <plik>
    if sub == "lines":
        _cmd_lines(args[1:], _t)
        return

    # analyse imports <plik>
    if sub == "imports":
        _cmd_imports(args[1:], _t)
        return

    # analyse functions <plik>
    if sub == "functions":
        _cmd_functions(args[1:], _t)
        return

    # analyse classes <plik>
    if sub == "classes":
        _cmd_classes(args[1:], _t)
        return

    # analyse complexity <plik>
    if sub == "complexity":
        _cmd_complexity(args[1:], _t)
        return

    # analyse find <wzorzec> <ext>
    if sub == "find":
        _cmd_find(args[1:], _t)
        return

    # analyse report <plik> [--json]
    if sub == "report":
        _cmd_report(args[1:], _t)
        return

    # analyse deps <plik>
    if sub == "deps":
        if len(args) < 2:
            _w(f"\n  {RED}{_t('analyser_deps_usage')}{RST}\n\n")
            return
        path = os.path.abspath(args[1])
        if not os.path.isfile(path):
            _w(f"\n  {RED}{_t('analyser_file_not_found', path=path)}{RST}\n\n")
            return
        _analyse_deps(path, _t)
        return

    # analyse export [plik]
    if sub == "export":
        _export_report(args[1] if len(args) > 1 else None, _t)
        return

    # analyse <plik>  <- domyslnie pelna analiza
    path = os.path.abspath(args[0])
    if not os.path.isfile(path):
        # Sprobuj w scripts/
        alt = os.path.join(_get_scripts_dir(), args[0])
        if os.path.isfile(alt):
            path = alt
        else:
            _w(f"\n  {RED}{_t('analyser_file_not_found', path=path)}{RST}\n\n")
            return

    report = _analyse_file(path)
    _save_report(report)
    _print_report(report, _t)


# --- AST CodeAnalyzer (rozbudowany) ------------------------------------------

class _CodeAnalyzer(ast.NodeVisitor):
    """Rozbudowany AST analyzer dla Pythona: metryki per-funkcja, call graph,
    magic numbers/strings, duplikaty sygnatur."""

    def __init__(self):
        self.functions:        List[Dict[str, Any]] = []
        self.classes:          List[Dict[str, Any]] = []
        self.imports:          List[Dict[str, Any]] = []
        self.complexity:       int = 1
        self.raw_lines:        int = 0
        self.comment_lines:    int = 0
        self.blank_lines:      int = 0
        self.magic_numbers:    List[Tuple[int, Any]] = []
        self.magic_strings:    List[Tuple[int, str]] = []
        self.call_graph:       Dict[str, List[str]] = {}
        self._class_stack:     List[str] = []
        self._call_graph_raw:  Dict[str, set] = defaultdict(set)

    @property
    def lines(self) -> int:
        return self.raw_lines - self.comment_lines - self.blank_lines

    def _func_complexity(self, node: ast.FunctionDef) -> int:
        cc = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                  ast.With, ast.Assert)):
                cc += 1
            elif isinstance(child, ast.BoolOp):
                cc += len(child.values) - 1
            elif isinstance(child, ast.comprehension):
                cc += 1
        return cc

    def _func_max_depth(self, node: ast.FunctionDef) -> int:
        def _depth(n: ast.AST, current: int) -> int:
            block_types = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)
            if isinstance(n, block_types):
                return max((_depth(c, current + 1) for c in ast.iter_child_nodes(n)), default=current + 1)
            return max((_depth(c, current) for c in ast.iter_child_nodes(n)), default=current)
        return _depth(node, 0)

    def _func_return_count(self, node: ast.FunctionDef) -> int:
        count = 0
        for child in ast.walk(node):
            if child is not node and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(child, ast.Return):
                count += 1
        return count

    def _func_lines(self, node: ast.FunctionDef) -> int:
        end = getattr(node, 'end_lineno', None)
        return (end - node.lineno + 1) if end else len(node.body)

    def _func_sig_hash(self, node: ast.FunctionDef) -> str:
        import hashlib as _hl
        sig = f"{node.name}:{len(node.args.args)}:{len(node.decorator_list)}"
        return _hl.md5(sig.encode()).hexdigest()[:8]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        cc         = self._func_complexity(node)
        depth      = self._func_max_depth(node)
        returns    = self._func_return_count(node)
        func_lines = self._func_lines(node)
        nested     = sum(1 for c in ast.walk(node)
                         if c is not node and isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)))
        class_ctx  = self._class_stack[-1] if self._class_stack else None
        qname      = f"{class_ctx}.{node.name}" if class_ctx else node.name

        self.functions.append({
            'name':            node.name,
            'qualified_name':  qname,
            'line':            node.lineno,
            'end_line':        getattr(node, 'end_lineno', None),
            'func_lines':      func_lines,
            'args':            len(node.args.args),
            'annotated_args':  sum(1 for a in node.args.args if a.annotation is not None),
            'defaults':        len(node.args.defaults) + len(node.args.kw_defaults),
            'decorators':      [ast.unparse(d) for d in node.decorator_list],
            'docstring':       ast.get_docstring(node) is not None,
            'complexity':      cc,
            'max_depth':       depth,
            'return_count':    returns,
            'has_return_type': node.returns is not None,
            'is_async':        isinstance(node, ast.AsyncFunctionDef),
            'nested_funcs':    nested,
            'sig_hash':        self._func_sig_hash(node),
            'class':           class_ctx,
        })
        self.complexity += cc - 1

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    self._call_graph_raw[qname].add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    self._call_graph_raw[qname].add(child.func.attr)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        methods   = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        class_vars = [n for n in node.body if isinstance(n, (ast.Assign, ast.AnnAssign))]
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append('?')
        self.classes.append({
            'name':       node.name,
            'line':       node.lineno,
            'end_line':   getattr(node, 'end_lineno', None),
            'methods':    len(methods),
            'class_vars': len(class_vars),
            'docstring':  ast.get_docstring(node) is not None,
            'bases':      bases,
            'decorators': [ast.unparse(d) for d in node.decorator_list],
        })
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append({'name': alias.name, 'alias': alias.asname,
                                 'line': node.lineno, 'is_from': False, 'module': None})
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or '<relative>'
        for alias in node.names:
            self.imports.append({'name': alias.name, 'alias': alias.asname,
                                 'line': node.lineno, 'is_from': True, 'module': module})
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        _SKIP_NUMS = {0, 1, -1, 2, 100, 1000, True, False, None}
        _SKIP_RE   = re.compile(
            r'^(__\w+__|utf-?8|ascii|utf-16|w|r|a|rb|wb|ab|\s*|\n|\t|,|\.|;|:|-|_|\|)$',
            re.IGNORECASE,
        )
        if isinstance(node.value, (int, float)) and node.value not in _SKIP_NUMS:
            self.magic_numbers.append((node.lineno, node.value))
        elif isinstance(node.value, str) and len(node.value) > 3:
            if not _SKIP_RE.match(node.value):
                self.magic_strings.append((node.lineno, node.value[:60]))
        self.generic_visit(node)


def _analyze_python(path: str) -> Dict[str, Any]:
    """Pełna analiza AST pliku Python. Zwraca dict z metrykami."""
    try:
        content = Path(path).read_text(encoding='utf-8', errors='replace')
        tree     = ast.parse(content, filename=path)
        analyzer = _CodeAnalyzer()
        analyzer.visit(tree)
        lines = content.splitlines()
        analyzer.raw_lines     = len(lines)
        analyzer.comment_lines = sum(1 for l in lines if l.strip().startswith('#'))
        analyzer.blank_lines   = sum(1 for l in lines if not l.strip())
        # duplikaty sygnatur
        sig_counts: Dict[str, List[str]] = defaultdict(list)
        for f in analyzer.functions:
            sig_counts[f['sig_hash']].append(f['name'])
        dup_sigs = {h: names for h, names in sig_counts.items() if len(names) > 1}
        call_graph = {k: list(v) for k, v in analyzer._call_graph_raw.items()}
        return {
            'status':         'ok',
            'language':       'Python',
            'lines':          analyzer.lines,
            'raw_lines':      analyzer.raw_lines,
            'comment_lines':  analyzer.comment_lines,
            'blank_lines':    analyzer.blank_lines,
            'functions':      analyzer.functions,
            'classes':        analyzer.classes,
            'imports':        analyzer.imports,
            'complexity':     analyzer.complexity,
            'magic_numbers':  analyzer.magic_numbers[:20],
            'magic_strings':  analyzer.magic_strings[:20],
            'call_graph':     call_graph,
            'duplicate_sigs': dup_sigs,
            'errors':         [],
        }
    except SyntaxError as e:
        return {'status': 'error', 'language': 'Python',
                'error': f"Blad skladni L{e.lineno}: {e.msg}", 'errors': [f"L{e.lineno}: {e.msg}"]}
    except Exception as e:
        return {'status': 'error', 'language': 'Python', 'error': str(e), 'errors': [str(e)]}


def _analyze_script(path: str) -> Dict[str, Any]:
    """Analiza skryptu nie-Python (sh, js, ps1, bat, ...)."""
    try:
        content = Path(path).read_text(encoding='utf-8', errors='replace')
        lines   = content.splitlines()
        ext     = os.path.splitext(path)[1].lower()
        if ext == '.js':
            func_pat = re.compile(r'(?:function\s+(\w+)|(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>))')
        elif ext == '.ps1':
            func_pat = re.compile(r'^\s*function\s+(\w+)', re.IGNORECASE)
        else:
            func_pat = re.compile(r'^(?:def|function|::|PROCEDURE)\s+(\w+)', re.MULTILINE)
        functions = []
        for i, line in enumerate(lines):
            m = func_pat.search(line)
            if m:
                name = m.group(1) or (m.lastindex and m.lastindex > 1 and m.group(2)) or None
                if name:
                    functions.append({'name': name, 'line': i + 1})
        import_patterns = [r'^(?:import|require|source|include|\.)\s+', r'^(?:from|use|using)\s+']
        imports_raw = [l.strip() for l in lines if any(re.match(p, l, re.IGNORECASE) for p in import_patterns)]
        complexity = 1
        for line in lines:
            for p in [r'\bif\b', r'\bfor\b', r'\bwhile\b', r'\bcase\b', r'\buntil\b', r'\bcatch\b']:
                complexity += len(re.findall(p, line, re.IGNORECASE))
        blank = sum(1 for l in lines if not l.strip())
        return {
            'status':         'ok',
            'language':       ext.lstrip('.').upper(),
            'lines':          len(lines) - blank,
            'raw_lines':      len(lines),
            'comment_lines':  0,
            'blank_lines':    blank,
            'functions':      functions,
            'classes':        [],
            'imports':        [{'name': i, 'alias': None, 'line': 0, 'is_from': False, 'module': None}
                               for i in imports_raw[:20]],
            'complexity':     complexity,
            'magic_numbers':  [],
            'magic_strings':  [],
            'call_graph':     {},
            'duplicate_sigs': {},
            'errors':         [],
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'errors': [str(e)]}


def _analyze_any(path: str) -> Dict[str, Any]:
    """Dispatch: Python -> _analyze_python, inne -> _analyze_script."""
    if os.path.splitext(path)[1].lower() == '.py':
        return _analyze_python(path)
    return _analyze_script(path)


def _maintainability_index(result: Dict[str, Any]) -> float:
    """Maintainability Index (0-171)."""
    loc = max(1, result.get('lines', 1))
    cc  = max(1, result.get('complexity', 1))
    mi  = 171 - 5.2 * math.log(cc) - 0.23 * cc - 16.2 * math.log(loc)
    return round(max(0.0, min(171.0, mi)), 1)


def _require_file_path(args: list, usage: str) -> Optional[str]:
    """Sprawdz czy args[0] to istniejacy plik; zwroc abspath lub None."""
    if not args:
        _w(f"\n  {RED}Uzycie: {usage}{RST}\n\n")
        return None
    p = os.path.abspath(args[0])
    if not os.path.isfile(p):
        # Sprobuj w scripts/
        alt = os.path.join(_get_scripts_dir(), args[0])
        if os.path.isfile(alt):
            return alt
        _w(f"\n  {RED}Plik nie znaleziony: {args[0]}{RST}\n\n")
        return None
    return p


# --- Reguły lint (regex + AST) ------------------------------------------------

_LINT_RULES_REGEX: List[Tuple] = [
    ('L001', 'info',    'Komentarz TODO/FIXME/HACK',              re.compile(r'\b(TODO|FIXME|HACK|XXX)\b', re.I)),
    ('L002', 'warning', 'Zbedne spacje na koncu linii',           re.compile(r'\s+$')),
    ('L003', 'info',    'Linia > 100 znakow',                     None),
    ('L004', 'info',    'Uzyto print() — rozwaz logging',         re.compile(r'\bprint\s*\(')),
    ('L005', 'warning', 'Porownanie z None (uzyj is)',            re.compile(r'[!=]=\s*None')),
    ('L006', 'warning', 'Porownanie z True/False (uzyj is)',      re.compile(r'[!=]=\s*(True|False)')),
    ('L007', 'info',    'Zakomentowany kod',                      re.compile(r'^\s*#\s*(if|for|while|def|class|import|return)\b')),
    ('L008', 'warning', 'Uzycie eval()',                          re.compile(r'\beval\s*\(')),
    ('L009', 'warning', 'Uzycie exec()',                          re.compile(r'\bexec\s*\(')),
    ('L010', 'warning', 'Mutable default argument ([] lub {})',   re.compile(r'def\s+\w+\([^)]*=\s*[\[\{]')),
]


def _lint_ast_rules(tree: ast.AST, content: str, strict: bool) -> List[Tuple[int, str, str, str]]:
    issues: List[Tuple[int, str, str, str]] = []
    for node in ast.walk(tree):
        ln = getattr(node, 'lineno', 0)
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append((ln, 'L101', 'warning', "Puste 'except:' — lapie wszystkie wyjatki"))
        if isinstance(node, ast.Global):
            issues.append((ln, 'L102', 'warning', f"Slowo kluczowe 'global': {', '.join(node.names)}"))
        if isinstance(node, ast.Nonlocal):
            issues.append((ln, 'L103', 'info', f"Uzycie 'nonlocal': {', '.join(node.names)}"))
        if isinstance(node, ast.Assert) and strict:
            issues.append((ln, 'L104', 'info', "assert w kodzie (pomijane z -O)"))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith('_') and ast.get_docstring(node) is None:
                issues.append((node.lineno, 'L105', 'info', f"Brak docstringa: '{node.name}'"))
            end = getattr(node, 'end_lineno', None)
            func_len = (end - node.lineno + 1) if end else 0
            if func_len > 50:
                issues.append((node.lineno, 'L106', 'warning', f"Bardzo dluga funkcja '{node.name}' ({func_len} linii)"))
            elif func_len > 30:
                issues.append((node.lineno, 'L106', 'info', f"Dluga funkcja '{node.name}' ({func_len} linii)"))
            nargs = len(node.args.args)
            if nargs > 7:
                issues.append((node.lineno, 'L107', 'warning', f"Za duzo argumentow w '{node.name}' ({nargs})"))
            elif nargs > 5 and strict:
                issues.append((node.lineno, 'L107', 'info', f"Duzo argumentow w '{node.name}' ({nargs})"))
            if strict:
                missing_ann = sum(1 for a in node.args.args if a.annotation is None)
                if missing_ann > 0 and not node.name.startswith('_'):
                    issues.append((node.lineno, 'L108', 'info', f"Brak adnotacji typow w '{node.name}' ({missing_ann} arg)"))
                if node.returns is None and not node.name.startswith('_'):
                    issues.append((node.lineno, 'L108', 'info', f"Brak adnotacji zwracanego typu w '{node.name}'"))
            cc = 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                    cc += 1
                elif isinstance(child, ast.BoolOp):
                    cc += len(child.values) - 1
            if cc > 15:
                issues.append((node.lineno, 'L109', 'error', f"Wysoka zlozonosc '{node.name}' (CC={cc})"))
            elif cc > 8:
                issues.append((node.lineno, 'L109', 'warning', f"Podwyzszona zlozonosc '{node.name}' (CC={cc})"))
            nested = sum(1 for c in ast.walk(node)
                         if c is not node and isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)))
            if nested > 2:
                issues.append((node.lineno, 'L110', 'info', f"Wiele zagniezdz. funkcji w '{node.name}' ({nested})"))
        if isinstance(node, ast.ClassDef) and ast.get_docstring(node) is None:
            issues.append((node.lineno, 'L111', 'info', f"Brak docstringa klasy: '{node.name}'"))
        if strict and isinstance(node, ast.ExceptHandler):
            if node.type and isinstance(node.type, ast.Name) and node.type.id == 'Exception':
                issues.append((node.lineno, 'L112', 'info', "Lapiesz 'Exception' — rozwaz wezszy typ"))
    return issues


def _lint_duplicate_strings(content: str, strict: bool) -> List[Tuple[int, str, str, str]]:
    if not strict:
        return []
    issues: List[Tuple[int, str, str, str]] = []
    try:
        tree = ast.parse(content)
        str_map: Dict[str, List[int]] = defaultdict(list)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 5:
                str_map[node.value].append(node.lineno)
        for val, lns in str_map.items():
            if len(lns) >= 3:
                issues.append((lns[0], 'L114', 'info', f"String {val[:30]!r} powtarza sie {len(lns)}x"))
    except Exception:
        pass
    return issues


# --- Nowe komendy -------------------------------------------------------------

def _cmd_syntax(args: list, _t) -> None:
    """analyse syntax <plik> — sprawdz skladnie, wyswietl OK/FAIL."""
    path = _require_file_path(args, "analyse syntax <plik>")
    if not path:
        return
    result = _analyze_any(path)
    name = os.path.basename(path)
    if result['status'] == 'ok':
        _w(f"\n  {GRN}[V]  {name}  — skladnia OK{RST}  {DIM}({result.get('language','?')}){RST}\n\n")
    else:
        _w(f"\n  {RED}[X]  {name}  — blad skladni:{RST}\n")
        for err in result.get('errors', [result.get('error', '?')]):
            _w(f"       {YLW}{err}{RST}\n")
        _w("\n")


def _cmd_lines(args: list, _t) -> None:
    """analyse lines <plik> — statystyki linii, funkcje, klasy."""
    path = _require_file_path(args, "analyse lines <plik>")
    if not path:
        return
    result = _analyze_any(path)
    if result['status'] != 'ok':
        _w(f"\n  {RED}Blad: {result.get('error')}{RST}\n\n")
        return
    name = os.path.basename(path)
    _w(f"\n  {BOLD}{BCYN}{name}{RST}\n\n")
    _w(f"  {CYN}{_pad('Linie kodu:', 18)}{RST}{WHT}{result['lines']}{RST}\n")
    _w(f"  {CYN}{_pad('Komentarze:', 18)}{RST}{DIM}{result.get('comment_lines', 0)}{RST}\n")
    _w(f"  {CYN}{_pad('Puste:', 18)}{RST}{DIM}{result.get('blank_lines', 0)}{RST}\n")
    _w(f"  {CYN}{_pad('Razem:', 18)}{RST}{DIM}{result.get('raw_lines', 0)}{RST}\n")
    _w(f"  {CYN}{_pad('Funkcje:', 18)}{RST}{WHT}{len(result.get('functions', []))}{RST}\n")
    classes = result.get('classes', [])
    if classes:
        _w(f"  {CYN}{_pad('Klasy:', 18)}{RST}{WHT}{len(classes)}{RST}\n")
    _w("\n")


def _cmd_imports(args: list, _t) -> None:
    """analyse imports <plik> — wyswietl importy z modulem i aliasem."""
    path = _require_file_path(args, "analyse imports <plik>")
    if not path:
        return
    result = _analyze_any(path)
    if result['status'] != 'ok':
        _w(f"\n  {RED}Blad: {result.get('error')}{RST}\n\n")
        return
    imports = result.get('imports', [])
    if not imports:
        _w(f"\n  {DIM}(brak importow){RST}\n\n")
        return
    _w(f"\n  {BOLD}{BCYN}Importy ({len(imports)}):{RST}\n\n")
    for imp in imports[:40]:
        if isinstance(imp, dict):
            name   = imp['name']
            mod    = imp.get('module')
            alias  = imp.get('alias')
            prefix = f"{DIM}{mod}.{RST}" if mod else ""
            suffix = f"  {DIM}as {alias}{RST}" if alias else ""
            _w(f"  {GRN}>{RST}  {prefix}{CYN}{name}{RST}{suffix}\n")
        else:
            _w(f"  {GRN}>{RST}  {CYN}{imp}{RST}\n")
    if len(imports) > 40:
        _w(f"  {DIM}... i {len(imports)-40} wiecej{RST}\n")
    _w("\n")


def _cmd_functions(args: list, _t) -> None:
    """analyse functions <plik> — lista funkcji z metrykami."""
    path = _require_file_path(args, "analyse functions <plik>")
    if not path:
        return
    result = _analyze_any(path)
    if result['status'] != 'ok':
        _w(f"\n  {RED}Blad: {result.get('error')}{RST}\n\n")
        return
    functions = result.get('functions', [])
    if not functions:
        _w(f"\n  {DIM}(brak funkcji){RST}\n\n")
        return
    _w(f"\n  {BOLD}{BCYN}Funkcje ({len(functions)}):{RST}\n\n")
    for func in functions:
        if not isinstance(func, dict):
            _w(f"  {YLW}{func}{RST}\n")
            continue
        name       = func.get('qualified_name') or func.get('name', '?')
        line_no    = func.get('line', '?')
        cc         = func.get('complexity', '')
        depth      = func.get('max_depth', '')
        returns    = func.get('return_count', '')
        func_lines = func.get('func_lines', '')
        is_async   = f"{YLW}async{RST} " if func.get('is_async') else ''
        has_doc    = f"{GRN}[doc]{RST}" if func.get('docstring') else f"{DIM}[!doc]{RST}"
        has_type   = f" {CYN}[->T]{RST}" if func.get('has_return_type') else ''
        nargs      = func.get('args', 0)
        decs       = func.get('decorators', [])
        decs_str   = f"  {MGT}@{'  @'.join(decs[:2])}{RST}" if decs else ''
        cc_col     = GRN if (not cc or cc <= 5) else (YLW if cc <= 10 else RED)
        metrics    = f"cc={cc_col}{cc}{RST} d={depth} ret={returns} L={func_lines}"
        _w(f"  {is_async}{YLW}{_pad(name, 28)}{RST}({DIM}{nargs}a{RST})  {metrics}  "
           f"{has_doc}{has_type}{decs_str}  {DIM}@L{line_no}{RST}\n")
    _w("\n")


def _cmd_classes(args: list, _t) -> None:
    """analyse classes <plik> — lista klas z metrykami."""
    path = _require_file_path(args, "analyse classes <plik>")
    if not path:
        return
    result = _analyze_any(path)
    if result['status'] != 'ok':
        _w(f"\n  {RED}Blad: {result.get('error')}{RST}\n\n")
        return
    classes = result.get('classes', [])
    if not classes:
        _w(f"\n  {DIM}(brak klas){RST}\n\n")
        return
    _w(f"\n  {BOLD}{BCYN}Klasy ({len(classes)}):{RST}\n\n")
    for cls in classes:
        name      = cls.get('name', '?')
        methods   = cls.get('methods', 0)
        cvars     = cls.get('class_vars', 0)
        line_no   = cls.get('line', '?')
        bases     = cls.get('bases', [])
        decs      = cls.get('decorators', [])
        has_doc   = f"{GRN}[doc]{RST}" if cls.get('docstring') else f"{DIM}[!doc]{RST}"
        bases_str = f"({', '.join(bases)})" if bases else ''
        decs_str  = f"  {MGT}@{'  @'.join(decs[:2])}{RST}" if decs else ''
        _w(f"  {YLW}{_pad(name+bases_str, 32)}{RST}"
           f"  {WHT}{methods}{RST}m {DIM}{cvars}{RST}cv  {has_doc}{decs_str}  {DIM}@L{line_no}{RST}\n")
    _w("\n")


def _cmd_complexity(args: list, _t) -> None:
    """analyse complexity <plik> — CC + MI + bar chart top funkcji."""
    path = _require_file_path(args, "analyse complexity <plik>")
    if not path:
        return
    result = _analyze_any(path)
    if result['status'] != 'ok':
        _w(f"\n  {RED}Blad: {result.get('error')}{RST}\n\n")
        return
    cc = result.get('complexity', 0)
    mi = _maintainability_index(result)
    cc_label = (f"{GRN}Niska{RST}" if cc <= 7 else f"{YLW}Srednia{RST}" if cc <= 15 else f"{RED}Wysoka{RST}")
    mi_col   = GRN if mi > 80 else (YLW if mi > 50 else RED)
    _w(f"\n  {BOLD}{BCYN}Zlozonosc — {os.path.basename(path)}{RST}\n\n")
    _w(f"  {CYN}{_pad('CC (cyklomatyczna):', 26)}{RST}{cc_label}  {WHT}({cc}){RST}\n")
    _w(f"  {CYN}{_pad('Maintainability Index:', 26)}{RST}{mi_col}{mi}/171{RST}\n")
    funcs = [f for f in result.get('functions', []) if isinstance(f, dict) and 'complexity' in f]
    if funcs:
        top = sorted(funcs, key=lambda f: f['complexity'], reverse=True)[:8]
        max_cc = top[0]['complexity']
        _w(f"\n  {DIM}Top funkcje wg CC:{RST}\n\n")
        for f in top:
            bar_len = int(f['complexity'] / max(max_cc, 1) * 24)
            bar     = '█' * bar_len
            col     = GRN if f['complexity'] <= 5 else (YLW if f['complexity'] <= 10 else RED)
            depth_s = f" d={f.get('max_depth','?')}" if 'max_depth' in f else ''
            _w(f"    {_pad(f['name'], 26)} {col}{bar:<24}{RST} cc={f['complexity']}{depth_s}\n")
    dups = result.get('duplicate_sigs', {})
    if dups:
        _w(f"\n  {YLW}Potencjalne duplikaty (ta sama sygnatura):{RST}\n")
        for names in dups.values():
            _w(f"    {DIM}{', '.join(names)}{RST}\n")
    magic = result.get('magic_numbers', [])
    if magic:
        _w(f"\n  {DIM}Magic numbers ({len(magic)} — rozwaz stale):{RST}\n")
        shown: Dict[Any, int] = {}
        for ln, val in magic[:8]:
            if val not in shown:
                shown[val] = ln
                _w(f"    {DIM}L{ln}: {val}{RST}\n")
    _w("\n")


def _cmd_find(args: list, _t) -> None:
    """analyse find <wzorzec> <ext> — szukaj regex w plikach."""
    if len(args) < 2:
        _w(f"\n  {RED}Uzycie: analyse find <wzorzec> <ext>{RST}\n\n")
        return
    pattern_str = args[0]
    ext = args[1] if args[1].startswith('.') else f".{args[1]}"
    try:
        pattern = re.compile(pattern_str)
    except re.error as e:
        _w(f"\n  {RED}Nieprawidlowy regex: {e}{RST}\n\n")
        return
    _w(f"\n  Szukanie {YLW}{pattern_str!r}{RST} w *{BCYN}{ext}{RST}...\n\n")
    found_count = 0
    match_total = 0
    for p in sorted(Path('.').rglob(f"*{ext}")):
        try:
            file_lines = p.read_text(encoding='utf-8', errors='ignore').splitlines()
            matches = [(i+1, line.strip()) for i, line in enumerate(file_lines) if pattern.search(line)]
            if matches:
                _w(f"  {GRN}{p}{RST}  ({len(matches)} dopasowan)\n")
                for line_no, snippet in matches[:4]:
                    _w(f"    {DIM}L{line_no}:{RST} {snippet[:80]}\n")
                if len(matches) > 4:
                    _w(f"    {DIM}... i {len(matches)-4} wiecej{RST}\n")
                found_count += 1
                match_total += len(matches)
        except Exception:
            pass
    if found_count == 0:
        _w(f"  {DIM}Nie znaleziono dopasowan.{RST}\n")
    else:
        _w(f"\n  {DIM}Lacznie: {match_total} dopasowan w {found_count} plikach{RST}\n")
    _w("\n")


def _cmd_report(args: list, _t) -> None:
    """analyse report <plik> [--json] — pelny raport tekstowy / eksport JSON."""
    path = _require_file_path(args, "analyse report <plik> [--json]")
    if not path:
        return
    is_json = '--json' in args
    result  = _analyze_any(path)
    p = Path(path)
    result['file_info'] = {
        'name':  p.name,
        'size':  p.stat().st_size,
        'mtime': time.ctime(p.stat().st_mtime),
    }
    if result['status'] == 'ok':
        result['maintainability_index'] = _maintainability_index(result)
    if is_json:
        out_name = os.path.join(os.getcwd(), f"report_{p.stem}.json")
        try:
            with open(out_name, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=list)
            _w(f"\n  {GRN}[V]  Raport JSON: {out_name}{RST}\n\n")
        except Exception as e:
            _w(f"\n  {RED}Blad zapisu: {e}{RST}\n\n")
        return
    _w(f"\n  {BOLD}{BCYN}Code Analysis Report — {p.name}{RST}\n")
    _w(f"  {DIM}{'─'*60}{RST}\n\n")
    _w(f"  {CYN}{_pad('Typ:', 14)}{RST}{result.get('language','?')}\n")
    _w(f"  {CYN}{_pad('Rozmiar:', 14)}{RST}{result['file_info']['size']} B\n")
    _w(f"  {CYN}{_pad('Modyfikacja:', 14)}{RST}{result['file_info']['mtime']}\n\n")
    if result['status'] == 'ok':
        _w(f"  {CYN}Linie:{RST}  kod={WHT}{result.get('lines',0)}{RST}"
           f"  koment={DIM}{result.get('comment_lines',0)}{RST}"
           f"  puste={DIM}{result.get('blank_lines',0)}{RST}\n")
        _w(f"  {CYN}{_pad('Funkcje:', 14)}{RST}{GRN}{len(result.get('functions',[]))}{RST}\n")
        _w(f"  {CYN}{_pad('Klasy:', 14)}{RST}{GRN}{len(result.get('classes',[]))}{RST}\n")
        _w(f"  {CYN}{_pad('Importy:', 14)}{RST}{GRN}{len(result.get('imports',[]))}{RST}\n")
        cc     = result.get('complexity', 0)
        cc_col = GRN if cc <= 7 else (YLW if cc <= 15 else RED)
        _w(f"  {CYN}{_pad('CC:', 14)}{RST}{cc_col}{cc}{RST}\n")
        mi     = result.get('maintainability_index', 0)
        mi_col = GRN if mi > 80 else (YLW if mi > 50 else RED)
        _w(f"  {CYN}{_pad('Maint.Index:', 14)}{RST}{mi_col}{mi}/171{RST}\n")
        magic_n = result.get('magic_numbers', [])
        if magic_n:
            _w(f"  {CYN}{_pad('Magic numbers:', 14)}{RST}{DIM}{len(magic_n)} znalezionych{RST}\n")
        dups = result.get('duplicate_sigs', {})
        if dups:
            dup_count = sum(len(v) for v in dups.values())
            _w(f"  {CYN}{_pad('Duplikaty:', 14)}{RST}{YLW}{dup_count} funkcji{RST}\n")
    else:
        _w(f"  {RED}Blad: {result.get('error','?')}{RST}\n")
    _w(f"\n  {DIM}Wskazowka: --json → eksport pelnych danych{RST}\n\n")


# --- Rozbudowany lint (zamienia stary _lint_file) -----------------------------

def _lint_file_v2(path: str, args: list, _t) -> None:
    """Rozbudowany lint: 10 regul regex + 14 regul AST + opcjonalny --strict."""
    strict = '--strict' in args
    name   = os.path.basename(path)
    try:
        content = Path(path).read_text(encoding='utf-8', errors='replace')
        issues: List[Tuple[int, str, str, str]] = []

        # Reguly regexowe per-linia
        ext = os.path.splitext(path)[1].lower()
        for line_no, line in enumerate(content.splitlines(), 1):
            for rule_id, level, desc, pattern in _LINT_RULES_REGEX:
                if rule_id == 'L003':
                    if len(line) > 100:
                        issues.append((line_no, rule_id, level, f"Linia {len(line)} znakow (>100)"))
                    continue
                if rule_id == 'L004' and ext != '.py':
                    continue
                if pattern and pattern.search(line):
                    msg = f"{desc}: {line.strip()[:60]}" if rule_id == 'L001' else desc
                    issues.append((line_no, rule_id, level, msg))

        # Reguly AST (Python only)
        if ext == '.py':
            try:
                tree = ast.parse(content)
                issues.extend(_lint_ast_rules(tree, content, strict))
                issues.extend(_lint_duplicate_strings(content, strict))
            except SyntaxError as e:
                issues.append((e.lineno or 0, 'L000', 'error', f"Blad skladni: {e.msg}"))
        elif ext == '.json':
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                issues.append((e.lineno, 'L000', 'error', f"Blad JSON L{e.lineno}: {e.msg}"))

        if not issues:
            mode_s = " (strict)" if strict else ""
            _w(f"\n  {GRN}[V]  Brak problemow w {name}{mode_s}{RST}\n\n")
            return

        issues.sort(key=lambda x: (x[0], x[1]))
        counts: Dict[str, int] = {'error': 0, 'warning': 0, 'info': 0}
        for _, _, lvl, _ in issues:
            counts[lvl] = counts.get(lvl, 0) + 1

        mode_str = f"  {MGT}[strict]{RST}" if strict else ''
        _w(f"\n  {BOLD}{BCYN}Lint — {name}{RST}{mode_str}  "
           f"{RED}{counts['error']}E{RST}  {YLW}{counts['warning']}W{RST}  {DIM}{counts['info']}I{RST}\n\n")
        limit = 60
        for line_no, rule_id, level, msg in issues[:limit]:
            col = RED if level == 'error' else (YLW if level == 'warning' else DIM)
            _w(f"  {col}{rule_id}{RST} L{line_no:<4} {DIM}[{level[0].upper()}]{RST} {msg}\n")
        if len(issues) > limit:
            _w(f"  {DIM}... i {len(issues)-limit} wiecej{RST}\n")
        _w("\n")
    except Exception as e:
        _w(f"\n  {RED}Blad lint: {e}{RST}\n\n")


# --- setup / teardown ---------------------------------------------------------

def setup(terminal) -> None:
    _ensure_cache()


    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("analyser", {
            "analyse_file": _analyse_file,
            "get_ext_map": _get_ext_map,
        })
    except Exception:
        pass
    def _t(key: str, **kw):
        return terminal.t(key, **kw)

    def analyser_cmd(args):
        _cmd_analyse(args, _t)

    def analyse_cmd(args):
        _menu(_t)

    terminal.register_command(
        "analyser", analyser_cmd,
        description=_t("analyser_cmd_desc"),
        category=_t("cat_ecosystem"),
    )
    terminal.register_command(
        "analyse", analyse_cmd,
        description=_t("analyser_cmd_alias_desc"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal) -> None:
    try:
        from . import _integration as _intg
        _intg.unregister("analyser")
    except Exception:
        pass
    terminal.commands.pop("analyser", None)
    terminal.commands.pop("analyse",  None)
