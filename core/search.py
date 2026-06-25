"""Search module for TerminalX - file system search with filters.

polsoft.ITS Group  *  Sebastian Januchowski
Module: Search  v1.0.0
"""

import os
import fnmatch
import sys
import re as _re
from typing import Generator, Optional

from . import config

# ---------------------------------------------------------------------------
# ANSI helpers (no external deps)
# ---------------------------------------------------------------------------

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, IS_WIN, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad
_ansi = _re.compile(r'\x1b\[[0-9;]*[mA-Z]')


# ---------------------------------------------------------------------------
# FileSearcher - core search engine (standalone, stdlib-only)
# ---------------------------------------------------------------------------
class FileSearcher:
    """
    Niezalezny platformowo modul wyszukiwania plikow dla terminala.
    Wykorzystuje wylacznie biblioteke standardowa Pythona.
    """

    @staticmethod
    def search(
        start_dir: str,
        pattern: str = "*",
        extension: Optional[str] = None,
        min_size_bytes: Optional[int] = None,
        max_size_bytes: Optional[int] = None,
        name_only: bool = False,
        ignore_errors: bool = True,
    ) -> Generator[str, None, None]:
        """
        Przeszukuje katalog i zwraca dopasowane sciezki plikow jako generator.

        :param start_dir:      Katalog poczatkowy wyszukiwania.
        :param pattern:        Wzorzec nazwy pliku (np. 'test*', '*.py').
        :param extension:      Opcjonalne rozszerzenie (np. '.json', 'txt').
        :param min_size_bytes: Minimalny rozmiar pliku w bajtach.
        :param max_size_bytes: Maksymalny rozmiar pliku w bajtach.
        :param name_only:      Gdy True, szuka tylko w samej nazwie (nie sciezce).
        :param ignore_errors:  Jesli True, ignoruje PermissionError.
        """
        start_dir = os.path.abspath(os.path.expanduser(start_dir))
        if extension and not extension.startswith('.'):
            extension = f".{extension}"

        for root, dirs, files in os.walk(start_dir, topdown=True):
            if ignore_errors:
                try:
                    os.listdir(root)
                except PermissionError:
                    dirs.clear()
                    continue

            for file in files:
                # 1. Pattern matching (fnmatch + substring fallback)
                if pattern != "*":
                    if not fnmatch.fnmatch(file, pattern) and pattern not in file:
                        continue

                file_path = os.path.join(root, file)

                # 2. Extension filter
                if extension and not file.lower().endswith(extension.lower()):
                    continue

                # 3. Size filters
                if min_size_bytes is not None or max_size_bytes is not None:
                    try:
                        sz = os.path.getsize(file_path)
                        if min_size_bytes is not None and sz < min_size_bytes:
                            continue
                        if max_size_bytes is not None and sz > max_size_bytes:
                            continue
                    except (PermissionError, FileNotFoundError):
                        continue

                yield file_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _human_size(n: int) -> str:
    """Zwraca czytelny rozmiar pliku (B / KB / MB / GB)."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _parse_size(s: str) -> Optional[int]:
    """Parsuje ciag rozmiaru ('512', '10k', '5M') do bajtow lub None przy bledzie."""
    s = s.strip().upper()
    if not s:
        return None
    multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "B": 1}
    if s[-1] in multipliers:
        try:
            return int(float(s[:-1]) * multipliers[s[-1]])
        except ValueError:
            return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_args(args: list) -> dict:
    """
    Parsuje liste argumentow komendy search.

    Obslugiwane flagi:
      -e / --ext <ext>          - rozszerzenie
      -min / --min-size <size>  - minimalny rozmiar
      -max / --max-size <size>  - maksymalny rozmiar
      -l / --limit <n>          - limit wynikow
      -d / --dir <path>         - katalog startowy
      --names-only              - pokazuj tylko nazwy (bez pelnej sciezki)
    Pozostale pozycyjne argumenty sa wzorcem/nazwa.
    """
    result = {
        "pattern": "*",
        "extension": None,
        "min_size": None,
        "max_size": None,
        "limit": None,
        "start_dir": ".",
        "names_only": False,
    }
    positional = []
    i = 0
    flag_map = {
        "-e": "extension",  "--ext": "extension",
        "-min": "min_size", "--min-size": "min_size",
        "-max": "max_size", "--max-size": "max_size",
        "-l": "limit",      "--limit": "limit",
        "-d": "start_dir",  "--dir": "start_dir",
    }
    while i < len(args):
        a = args[i]
        if a in flag_map:
            key = flag_map[a]
            i += 1
            if i < len(args):
                result[key] = args[i]
        elif a in ("--names-only", "-n"):
            result["names_only"] = True
        else:
            positional.append(a)
        i += 1

    if positional:
        result["pattern"] = positional[0]

    # coerce types
    if result["limit"] is not None:
        try:
            result["limit"] = int(result["limit"])
        except ValueError:
            result["limit"] = None
    if result["min_size"] is not None:
        result["min_size"] = _parse_size(str(result["min_size"]))
    if result["max_size"] is not None:
        result["max_size"] = _parse_size(str(result["max_size"]))

    return result


# ---------------------------------------------------------------------------
# setup / teardown - integracja z TerminalX
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Search settings (persistent, ~/.crossterm/search_config.json)
# ---------------------------------------------------------------------------
import json as _json
from datetime import datetime as _dt
from pathlib import Path as _Path

_DEFAULT_SETTINGS = {
    "case_sensitive": False,
    "max_depth": 10,
    "max_results": 1000,
    "exclude_patterns": ["*.pyc", "*.pyo", "__pycache__", ".git", ".svn", ".hg",
                          "node_modules", "*.egg-info", "dist", "build", ".trash"],
    "include_binary": False,
    "show_line_numbers": True,
    "context_lines": 2,
    "max_file_size_mb": 50,
    "follow_symlinks": False,
}
_search_settings = dict(_DEFAULT_SETTINGS)


def _cfg_path() -> _Path:
    p = _Path.home() / ".crossterm"
    p.mkdir(exist_ok=True)
    return p / "search_config.json"


def _load_search_settings():
    try:
        data = _json.loads(_cfg_path().read_text(encoding="utf-8"))
        _search_settings.update(data)
    except Exception:
        pass


def _save_search_settings():
    try:
        _cfg_path().write_text(
            _json.dumps(_search_settings, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass


_load_search_settings()


# ---------------------------------------------------------------------------
# Content search (grep-like)
# ---------------------------------------------------------------------------
import stat as _stat


def _is_binary(path: _Path, sample: int = 8192) -> bool:
    try:
        chunk = path.read_bytes()[:sample]
        if not chunk:
            return False
        if b'\x00' in chunk:
            return True
        text_chars = sum(1 for b in chunk if 32 <= b <= 126 or b in (9, 10, 13))
        return text_chars / len(chunk) < 0.8
    except Exception:
        return True


def _should_exclude_path(path: _Path, patterns: list) -> bool:
    name = path.name
    s = str(path)
    for p in patterns:
        import fnmatch as _fnm
        if _fnm.fnmatch(name, p) or _fnm.fnmatch(s, p) or p in s:
            return True
    return False


def _highlight(text: str, pattern: str, case_sensitive: bool) -> str:
    flags = 0 if case_sensitive else _re.IGNORECASE
    try:
        return _re.compile(_re.escape(pattern), flags).sub(
            f"{YLW}{BOLD}\\g<0>{RST}", text
        )
    except _re.error:
        return text


def _do_content_search(pattern: str, root_path: str, settings: dict):
    """Returns (results_list, files_searched, files_matched)."""
    root = _Path(root_path).resolve()
    if not root.exists():
        return [], 0, 0

    flags = 0 if settings["case_sensitive"] else _re.IGNORECASE
    try:
        regex = _re.compile(pattern, flags)
    except _re.error as e:
        _w(f"\n  {RED}✗ Nieprawidłowy wzorzec regex: {e}{RST}\n\n")
        return [], 0, 0

    max_size = settings["max_file_size_mb"] * 1024 * 1024
    ctx = settings["context_lines"]
    results, files_searched, files_matched = [], 0, 0

    try:
        for p in root.rglob("*"):
            try:
                depth = len(p.relative_to(root).parts)
                if depth > settings["max_depth"]:
                    continue
            except ValueError:
                continue
            if _should_exclude_path(p, settings["exclude_patterns"]):
                continue
            if not p.is_file():
                continue
            try:
                if p.stat().st_size > max_size:
                    continue
            except Exception:
                continue
            if not settings["include_binary"] and _is_binary(p):
                continue

            files_searched += 1
            try:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                matches = []
                for i, line in enumerate(lines, 1):
                    if regex.search(line):
                        matches.append({
                            "line": i,
                            "text": line,
                            "context_before": lines[max(0, i-1-ctx):i-1],
                            "context_after": lines[i:i+ctx],
                        })
                if matches:
                    files_matched += 1
                    results.append({"path": p, "matches": matches})
                    if len(results) >= settings["max_results"]:
                        break
            except Exception:
                pass
    except PermissionError:
        pass

    return results, files_searched, files_matched


def _print_content_results(results, pattern, files_searched, files_matched, settings):
    if not results:
        _w(f"\n  {YLW}⚠ Brak dopasowań — przeszukano {files_searched} plików{RST}\n\n")
        return
    total = sum(len(r["matches"]) for r in results)
    _w(f"\n  {BOLD}{BCYN}Wyniki: {total} dopasowań w {files_matched}/{files_searched} plikach{RST}\n\n")
    for r in results[:20]:
        try:
            rel = str(r["path"].relative_to(_Path.cwd()))
        except ValueError:
            rel = str(r["path"])
        _w(f"  {YLW}📄 {rel}{RST}  {DIM}({len(r['matches'])} dopasowań){RST}\n")
        for m in r["matches"][:5]:
            highlighted = _highlight(m["text"], pattern, settings["case_sensitive"])
            lnum = f"{m['line']:>4}" if settings["show_line_numbers"] else ""
            _w(f"    {BCYN}{lnum}{RST}: {highlighted}\n")
        if len(r["matches"]) > 5:
            _w(f"    {DIM}... i {len(r['matches']) - 5} więcej{RST}\n")
        _w("\n")


# ---------------------------------------------------------------------------
# Command search
# ---------------------------------------------------------------------------

def _do_cmd_search(pattern: str, terminal, settings: dict) -> list:
    flags = 0 if settings["case_sensitive"] else _re.IGNORECASE
    try:
        regex = _re.compile(pattern, flags)
    except _re.error:
        regex = _re.compile(_re.escape(pattern), flags)

    results = []
    if not terminal:
        return results

    # registered commands (core modules registered via register_command)
    for cmd, info in getattr(terminal, "commands", {}).items():
        desc = info.get("description", "") if isinstance(info, dict) else ""
        if regex.search(cmd) or (desc and regex.search(desc)):
            results.append({"type": "command", "command": cmd, "description": desc})

    # legacy CML from loaded modules/plugins
    for store_attr in ("modules", "plugins"):
        store = getattr(terminal, store_attr, None)
        if not store:
            continue
        for name, mod in getattr(store, "_loaded", {}).items():
            for cmd in getattr(mod, "CML_COMMANDS", {}):
                if regex.search(cmd):
                    results.append({"type": store_attr[:-1], "module": name, "command": cmd})

    return results


def _print_cmd_results(results, pattern):
    if not results:
        _w(f"\n  {YLW}⚠ Nie znaleziono komend pasujących do '{pattern}'{RST}\n\n")
        return
    _w(f"\n  {BOLD}{BCYN}Znaleziono {len(results)} komend:{RST}\n\n")
    by_type = {}
    for r in results:
        by_type.setdefault(r["type"], []).append(r)
    labels = {"command": "🔧 Komendy", "module": "📦 Moduły", "plugin": "🔌 Pluginy"}
    for t, items in by_type.items():
        _w(f"  {BOLD}{YLW}{labels.get(t, t)}{RST} ({len(items)})\n")
        for item in items:
            cmd = item["command"]
            desc = item.get("description", "")
            _w(f"    {GRN}→{RST} {BOLD}{cmd}{RST}")
            if desc:
                _w(f"  {DIM}{desc}{RST}")
            _w("\n")
        _w("\n")


# ---------------------------------------------------------------------------
# History search
# ---------------------------------------------------------------------------

def _do_history_search(pattern: str, terminal, settings: dict) -> list:
    flags = 0 if settings["case_sensitive"] else _re.IGNORECASE
    try:
        regex = _re.compile(pattern, flags)
    except _re.error:
        regex = _re.compile(_re.escape(pattern), flags)
    results = []
    history = getattr(terminal, "history", []) if terminal else []
    for i, entry in enumerate(history):
        if regex.search(entry):
            results.append({"index": i, "command": entry})
    return results


def _print_history_results(results, pattern, settings):
    if not results:
        _w(f"\n  {YLW}⚠ Brak wyników w historii poleceń{RST}\n\n")
        return
    _w(f"\n  {BOLD}{BCYN}Historia — {len(results)} dopasowań:{RST}\n\n")
    for r in results[-20:]:
        highlighted = _highlight(r["command"], pattern, settings["case_sensitive"])
        _w(f"  {DIM}[{r['index']:>3}]{RST} {highlighted}\n")
    _w("\n")


# ---------------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------------

def _print_search_settings(tab: str = "general"):
    TABS = [("general", "Ogólne"), ("display", "Wyświetlanie"),
            ("filters", "Filtry"), ("about", "O module")]
    _w(f"\n  {BOLD}{BCYN}⚙️  Ustawienia wyszukiwarki{RST}\n\n  ")
    for key, label in TABS:
        if key == tab:
            _w(f"{BOLD}[{label}]{RST}  ")
        else:
            _w(f"{DIM} {label} {RST}  ")
    _w(f"\n  {DIM}{'─'*56}{RST}\n\n")

    def row(key, desc, hint=""):
        val = _search_settings.get(key)
        if isinstance(val, bool):
            vs = f"{GRN}✓ włączone{RST}" if val else f"{RED}✗ wyłączone{RST}"
        elif isinstance(val, list):
            vs = f"{YLW}[{', '.join(str(v) for v in val[:3])}{'…' if len(val)>3 else ''}]{RST}"
        else:
            vs = f"{YLW}{val}{RST}"
        _w(f"  {BOLD}{key:<24}{RST} {vs}\n")
        _w(f"  {DIM}{'':24} {desc}{RST}\n")
        if hint:
            _w(f"  {DIM}{'':24} → search config {key} {hint}{RST}\n")
        _w("\n")

    if tab == "general":
        row("case_sensitive", "Rozróżnianie wielkości liter.", "true / false")
        row("max_depth",      "Maks. głębokość rekursji.", "<liczba>")
        row("max_results",    "Limit wyników.", "<liczba>")
        row("follow_symlinks","Podążaj za dowiązaniami symbolicznymi.", "true / false")
    elif tab == "display":
        row("show_line_numbers", "Pokazuj numery linii.", "true / false")
        row("context_lines",     "Linie kontekstu wokół dopasowania.", "<liczba>")
    elif tab == "filters":
        row("include_binary",    "Uwzględniaj pliki binarne.", "true / false")
        row("max_file_size_mb",  "Pomijaj pliki większe niż (MB).", "<liczba>")
        row("exclude_patterns",  "Wzorce glob do pominięcia.", "+<wzorzec> / -<wzorzec>")
        patterns = _search_settings.get("exclude_patterns", [])
        if patterns:
            _w(f"  {DIM}Aktywne wykluczenia ({len(patterns)}):\n")
            for i, p in enumerate(patterns):
                _w(f"    [{i:>2}] {p}\n")
            _w(f"{RST}\n")
    elif tab == "about":
        for label, val in [
            ("Moduł", "Search"), ("Wersja", "2.0.0"),
            ("Autor", "Sebastian Januchowski"), ("Firma", "polsoft.ITS™ Group"),
            ("Web", "www.polsoft.gt.tc"), ("Licencja", "MIT"),
        ]:
            _w(f"  {YLW}{label:<12}{RST} {val}\n")
        _w(f"\n  {BOLD}Config:{RST} {DIM}{_cfg_path()}{RST}\n\n")

    _w(f"  {DIM}{'─'*56}\n")
    _w(f"  Zmiana: search config <param> <wartość>   Reset: search config --reset{RST}\n\n")


def _set_search_config(param: str, value: str = "") -> bool:
    if param == "--reset":
        _search_settings.clear()
        _search_settings.update(_DEFAULT_SETTINGS)
        _save_search_settings()
        return True
    bool_keys = {"case_sensitive", "include_binary", "show_line_numbers", "follow_symlinks"}
    int_keys  = {"max_depth", "max_results", "context_lines", "max_file_size_mb"}
    list_keys = {"exclude_patterns"}
    try:
        if param in bool_keys:
            _search_settings[param] = value.lower() in ("true", "1", "yes", "on")
        elif param in int_keys:
            _search_settings[param] = int(value)
        elif param in list_keys:
            if value.startswith("+"):
                _search_settings[param].append(value[1:])
            elif value.startswith("-"):
                _search_settings[param] = [x for x in _search_settings[param] if x != value[1:]]
            else:
                _search_settings[param] = value.split(",")
        else:
            _search_settings[param] = value
        _save_search_settings()
        return True
    except Exception:
        return False

def setup(terminal):

    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("search", {
            "FileSearcher": FileSearcher,
        })
    except Exception:
        pass
    def _t(key, **kw):
        return terminal.t(key, **kw)

    # ------------------------------------------------------------------ #
    #  FILE SEARCH (legacy helper, called by dispatcher)                  #
    # ------------------------------------------------------------------ #
    def _files_search_cmd(args):
        if not args or args[0] in ("-h", "--help", "help"):
            _print_help(_t)
            return

        cfg = _parse_args(args)

        start = os.path.abspath(os.path.expanduser(cfg["start_dir"]))
        if not os.path.isdir(start):
            _w(f"  {RED}{_t('search_dir_not_found', path=start)}{RST}\n")
            return

        pattern   = cfg["pattern"]
        extension = cfg["extension"]
        limit     = cfg["limit"] if cfg["limit"] is not None else config.get("search.default_limit", 50)
        names_only = cfg["names_only"]

        _w(f"\n  {BOLD}{CYN}{_t('search_scanning', path=start)}{RST}\n\n")

        gen = FileSearcher.search(
            start_dir=start,
            pattern=pattern,
            extension=extension,
            min_size_bytes=cfg["min_size"],
            max_size_bytes=cfg["max_size"],
        )

        show_hidden = config.get("search.show_hidden", False)

        count = 0
        try:
            for path in gen:
                # honour search.show_hidden
                if not show_hidden:
                    parts = path.replace("\\", "/").split("/")
                    if any(p.startswith(".") for p in parts if p):
                        continue
                count += 1
                try:
                    sz = _human_size(os.path.getsize(path))
                except OSError:
                    sz = "?"
                name    = os.path.basename(path)
                dirpart = os.path.dirname(path)

                if names_only:
                    _w(f"  {GRN}[V]{RST} {YLW}{name}{RST}  {DIM}({sz}){RST}\n")
                else:
                    _w(f"  {GRN}[V]{RST} {YLW}{name}{RST}  {DIM}{dirpart}  ({sz}){RST}\n")

                if limit is not None and count >= limit:
                    _w(f"\n  {DIM}{_t('search_limit_reached', n=limit)}{RST}\n")
                    break
        except KeyboardInterrupt:
            _w(f"\n  {YLW}{_t('search_interrupted')}{RST}\n")

        _w("\n")
        if count == 0:
            _w(f"  {MGT}{_t('search_no_results')}{RST}\n\n")
        else:
            _w(f"  {DIM}{_t('search_found', n=count)}{RST}\n\n")

    # ------------------------------------------------------------------ #
    #  CONTENT search (grep-like)                                        #
    # ------------------------------------------------------------------ #
    def content_cmd(args):
        if not args:
            _w(f"\n  {RED}✗ Użycie: search content <wzorzec> [ścieżka]{RST}\n\n")
            return
        pattern = args[0]
        path = args[1] if len(args) > 1 else "."
        _w(f"\n  {DIM}Szukanie '{pattern}' w {path}…{RST}\n")
        results, fs, fm = _do_content_search(pattern, path, _search_settings)
        _print_content_results(results, pattern, fs, fm, _search_settings)

    # ------------------------------------------------------------------ #
    #  CMD search                                                         #
    # ------------------------------------------------------------------ #
    def cmd_search_cmd(args):
        if not args:
            _w(f"\n  {RED}✗ Użycie: search cmd <wzorzec>{RST}\n\n")
            return
        results = _do_cmd_search(args[0], terminal, _search_settings)
        _print_cmd_results(results, args[0])

    # ------------------------------------------------------------------ #
    #  HISTORY search                                                     #
    # ------------------------------------------------------------------ #
    def history_cmd(args):
        if not args:
            _w(f"\n  {RED}✗ Użycie: search history <wzorzec>{RST}\n\n")
            return
        results = _do_history_search(args[0], terminal, _search_settings)
        _print_history_results(results, args[0], _search_settings)

    # ------------------------------------------------------------------ #
    #  Extended SEARCH dispatcher                                         #
    # ------------------------------------------------------------------ #
    _SUBCOMMANDS = {
        "files":   ("files", "file"),
        "content": ("content", "grep", "text"),
        "cmd":     ("cmd", "command", "commands"),
        "history": ("history", "hist"),
        "settings":("settings",),
        "config":  ("config", "set"),
    }

    def search_cmd(args):
        if not args or args[0] in ("-h", "--help", "help"):
            _print_help(_t)
            return

        sub = args[0].lower()
        rest = args[1:]

        # --- files ---
        if sub in ("files", "file"):
            cfg = _parse_args(rest)
            start = os.path.abspath(os.path.expanduser(cfg["start_dir"]))
            if not os.path.isdir(start):
                _w(f"  {RED}{_t('search_dir_not_found', path=start)}{RST}\n")
                return
            _w(f"\n  {BOLD}{CYN}{_t('search_scanning', path=start)}{RST}\n\n")
            gen = FileSearcher.search(
                start_dir=start, pattern=cfg["pattern"], extension=cfg["extension"],
                min_size_bytes=cfg["min_size"], max_size_bytes=cfg["max_size"],
            )
            show_hidden = False
            count = 0
            try:
                for path in gen:
                    if not show_hidden:
                        parts = path.replace("\\", "/").split("/")
                        if any(p.startswith(".") for p in parts if p):
                            continue
                    count += 1
                    try:
                        sz = _human_size(os.path.getsize(path))
                    except OSError:
                        sz = "?"
                    name = os.path.basename(path)
                    dirpart = os.path.dirname(path)
                    if cfg["names_only"]:
                        _w(f"  {GRN}[V]{RST} {YLW}{name}{RST}  {DIM}({sz}){RST}\n")
                    else:
                        _w(f"  {GRN}[V]{RST} {YLW}{name}{RST}  {DIM}{dirpart}  ({sz}){RST}\n")
                    limit = cfg["limit"] if cfg["limit"] is not None else 50
                    if count >= limit:
                        _w(f"\n  {DIM}{_t('search_limit_reached', n=limit)}{RST}\n")
                        break
            except KeyboardInterrupt:
                _w(f"\n  {YLW}{_t('search_interrupted')}{RST}\n")
            _w("\n")
            if count == 0:
                _w(f"  {MGT}{_t('search_no_results')}{RST}\n\n")
            else:
                _w(f"  {DIM}{_t('search_found', n=count)}{RST}\n\n")

        # --- content / grep ---
        elif sub in ("content", "grep", "text"):
            content_cmd(rest)

        # --- cmd ---
        elif sub in ("cmd", "command", "commands"):
            cmd_search_cmd(rest)

        # --- history ---
        elif sub in ("history", "hist"):
            history_cmd(rest)

        # --- settings ---
        elif sub == "settings":
            VALID = ("general", "display", "filters", "about")
            tab = rest[0].lower() if rest and rest[0].lower() in VALID else "general"
            _print_search_settings(tab)

        # --- config ---
        elif sub in ("config", "set"):
            if not rest:
                _w(f"\n  {RED}✗ Użycie: search config <param> <wartość>{RST}\n\n")
                return
            param = rest[0]
            if param == "--reset":
                if _set_search_config("--reset"):
                    _w(f"\n  {GRN}✓ Ustawienia przywrócone do domyślnych{RST}\n\n")
                return
            if len(rest) < 2:
                _w(f"\n  {RED}✗ Użycie: search config <param> <wartość>{RST}\n\n")
                return
            if _set_search_config(param, rest[1]):
                _w(f"\n  {GRN}✓ {param} = {rest[1]}{RST}\n\n")
            else:
                _w(f"\n  {RED}✗ Nie można ustawić: {param}{RST}\n\n")

        # --- fallback: treat as files pattern ---
        else:
            cfg = _parse_args(args)
            start = os.path.abspath(os.path.expanduser(cfg["start_dir"]))
            if not os.path.isdir(start):
                _w(f"  {RED}{_t('search_dir_not_found', path=start)}{RST}\n")
                return
            _w(f"\n  {BOLD}{CYN}{_t('search_scanning', path=start)}{RST}\n\n")
            gen = FileSearcher.search(
                start_dir=start, pattern=cfg["pattern"], extension=cfg["extension"],
                min_size_bytes=cfg["min_size"], max_size_bytes=cfg["max_size"],
            )
            count = 0
            try:
                for path in gen:
                    count += 1
                    sz = _human_size(os.path.getsize(path)) if os.path.exists(path) else "?"
                    _w(f"  {GRN}[V]{RST} {YLW}{os.path.basename(path)}{RST}  "
                       f"{DIM}{os.path.dirname(path)}  ({sz}){RST}\n")
                    if count >= 50:
                        break
            except KeyboardInterrupt:
                pass
            _w("\n")
            if count == 0:
                _w(f"  {MGT}{_t('search_no_results')}{RST}\n\n")

    terminal.register_command(
        "search", search_cmd,
        description=_t("cmd_search"),
        category=_t("cat_ecosystem"),
    )

    terminal.register_command(
        "find", search_cmd,
        description=_t("cmd_find_alias"),
        category=_t("cat_ecosystem"),
    )

    def grep_cmd(args):
        """Alias: grep <wzorzec> [ścieżka]."""
        if not args:
            _w(f"\n  {RED}✗ Użycie: grep <wzorzec> [ścieżka]{RST}\n\n")
            return
        pattern = args[0]
        path = args[1] if len(args) > 1 else "."
        _w(f"\n  {DIM}Szukanie '{pattern}' w {path}…{RST}\n")
        results, fs, fm = _do_content_search(pattern, path, _search_settings)
        _print_content_results(results, pattern, fs, fm, _search_settings)

    terminal.register_command(
        "grep", grep_cmd,
        description=_t("cmd_grep") if "cmd_grep" in getattr(terminal, "_t", {})
                    else "grep <wzorzec> [ścieżka] — szukaj w zawartości plików",
        category=_t("cat_ecosystem"),
    )


def teardown(terminal):
    try:
        from . import _integration as _intg
        _intg.unregister("search")
    except Exception:
        pass
    terminal.commands.pop("search", None)
    terminal.commands.pop("find",   None)
    terminal.commands.pop("grep",   None)


# ---------------------------------------------------------------------------
# Internal: help printer
# ---------------------------------------------------------------------------
def _print_help(_t):
    lines = [
        f"\n  {BOLD}{CYN}{_t('search_module_title')}{RST}\n",
        f"  {DIM}{_t('search_usage_line')}{RST}\n\n",
        f"  {BOLD}{_t('search_flags_header')}{RST}\n",
        f"    {YLW}{'-e / --ext <ext>':<26}{RST}  {DIM}{_t('search_flag_ext')}{RST}\n",
        f"    {YLW}{'-d / --dir <path>':<26}{RST}  {DIM}{_t('search_flag_dir')}{RST}\n",
        f"    {YLW}{'-min / --min-size <sz>':<26}{RST}  {DIM}{_t('search_flag_min')}{RST}\n",
        f"    {YLW}{'-max / --max-size <sz>':<26}{RST}  {DIM}{_t('search_flag_max')}{RST}\n",
        f"    {YLW}{'-l / --limit <n>':<26}{RST}  {DIM}{_t('search_flag_limit')}{RST}\n",
        f"    {YLW}{'--names-only / -n':<26}{RST}  {DIM}{_t('search_flag_names')}{RST}\n",
        f"\n  {BOLD}{_t('search_examples_header')}{RST}\n",
        f"    {DIM}{_t('search_ex1')}{RST}\n",
        f"    {DIM}{_t('search_ex2')}{RST}\n",
        f"    {DIM}{_t('search_ex3')}{RST}\n",
        f"    {DIM}{_t('search_ex4')}{RST}\n\n",
    ]
    for l in lines:
        _w(l)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("--- Test modulu wyszukiwarki plikow ---")
    target = os.path.expanduser("~")
    print(f"Szukanie plikow .py w: {target}  (limit 5)\n")
    results = FileSearcher.search(start_dir=target, extension="py", max_size_bytes=1024 * 512)
    for i, m in enumerate(results, 1):
        sz = _human_size(os.path.getsize(m))
        print(f"  [{i}] {os.path.basename(m)}  ({sz})  {os.path.dirname(m)}")
        if i >= 5:
            print("  ...limit 5 wynikow.")
            break
