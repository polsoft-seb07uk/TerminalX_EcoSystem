"""Docs & Reports module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski

Menedzer dokumentow i generator raportow zintegrowany z reszta core:
  - doc     - twore, przegladaj, edytuj, taguj i przeszukuj dokumenty (.txt/.md/.html/.json)
  - report  - generuj raporty (system / history / tasks / defender / full)
              na podstawie stanu pozostalych modulow EcoSystem

Architektura
------------
  * Dokumenty trzymane sa w docs/, raporty w docs/reports/ (oba widoczne, jak
    scripts/ czy tools/ w innych modulach).
  * Metadane (utworzono, modyfikacja, typ, format, tagi) w .cache/docs/index.json.
  * doc rm / report rm nie usuwaja trwale - przenosza plik do wspolnego
    .trash/ (TRASH_DIR z trash.py), tak jak rm/del w command.py. Mozna je
    odzyskac przez `trash restore <nazwa>`.
  * report nie importuje innych modulow core - czyta ich wspoldzielony stan
    przez atrybuty terminal (._history, ._tasks) albo pliki cache, ktore te
    moduly juz pisza same (np. .cache/defender/events.json). Brak modulu
    zrodlowego = sekcja po prostu pomijana, nigdy nie crashuje raportu.

Komendy
-------
  doc                          - menu
  doc new <nazwa> [tekst...]   - nowy dokument (.md domyslnie)
  doc list [tag]               - lista dokumentow (opcjonalnie filtr po tagu)
  doc open <nazwa>             - wyswietl zawartosc (alias: cat)
  doc append <nazwa> <tekst>   - dopisz linie do dokumentu
  doc edit <nazwa>             - tryb wieloliniowy, zakoncz linia "."
  doc tag <nazwa> [tagi...]    - ustaw/pokaz tagi
  doc rename <stara> <nowa>    - zmiana nazwy
  doc export <nazwa> <format>  - eksport do md/txt/html/json
  doc search <wzorzec>         - szukaj tekstu we wszystkich dokumentach
  doc info <nazwa>             - metadane dokumentu
  doc rm <nazwa>               - przenies dokument do .trash

  report                        - menu
  report system                  - raport stanu EcoSystem
  report history [N]             - raport z historii polecen
  report tasks                   - raport zadan w tle
  report defender                - raport zdarzen ochrony
  report full                    - wszystkie sekcje w jednym raporcie
  report list                    - lista wygenerowanych raportow
  report open <nazwa>            - wyswietl raport
  report rm <nazwa>              - przenies raport do .trash

Author : Sebastian Januchowski
Brand  : polsoft.ITS(TM)
"""

import json
import os
import platform
import re
import sys
import time
from datetime import datetime

from . import config
from . import _integration

# -- sciezki ---------------------------------------------------------------

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad, _atomic_write
DOCS_DIR    = os.path.join(ROOT_DIR, "docs")
REPORTS_DIR = os.path.join(DOCS_DIR, "reports")
_DOCS_CACHE = os.path.join(CACHE_DIR, "docs")
INDEX_FILE  = os.path.join(_DOCS_CACHE, "index.json")

_EXTS = {"md": ".md", "txt": ".txt", "html": ".html", "json": ".json"}
_FMT_OF_EXT = {v: k for k, v in _EXTS.items()}

# -- ANSI --------------------------------------------------------------------








# -- persistence --------------------------------------------------------------

def _ensure_dirs() -> None:
    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(_DOCS_CACHE, exist_ok=True)


def _load_index() -> dict:
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}


def _save_index(idx: dict) -> bool:
    _ensure_dirs()
    return _atomic_write(INDEX_FILE, idx, fsync=False)


# -- helpers -------------------------------------------------------------------

class DocError(Exception):
    """Bledna nazwa lub operacja na dokumencie - obsluzona miekko w komendach."""


def _safe_name(raw: str) -> str:
    """Zwroc bezpieczna nazwe bazowa (bez katalogow / przejscia '..')."""
    name = os.path.basename(str(raw).strip())
    name = name.replace("\\", "_").replace("/", "_")
    if not name or name in (".", ".."):
        raise DocError("empty")
    return name


def _with_ext(name: str, default_fmt: str) -> str:
    """Dodaj rozszerzenie domyslnego formatu, jezeli nazwa go nie ma."""
    _, ext = os.path.splitext(name)
    if ext.lower() in _EXTS.values():
        return name
    return name + _EXTS.get(default_fmt, ".md")


def _fmt_of(name: str) -> str:
    _, ext = os.path.splitext(name)
    return _FMT_OF_EXT.get(ext.lower(), "txt")


def _dir_for(kind: str) -> str:
    return REPORTS_DIR if kind == "report" else DOCS_DIR


def _path_for(name: str, kind: str) -> str:
    return os.path.join(_dir_for(kind), name)


def _default_fmt() -> str:
    return config.get("docs.default_format", "md")


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def _human_dt(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "-"


def _touch_entry(idx: dict, name: str, kind: str, fmt: str,
                  tags: list | None = None) -> None:
    now = time.time()
    entry = idx.get(name, {})
    entry.setdefault("created", now)
    entry["modified"] = now
    entry["kind"] = kind
    entry["format"] = fmt
    if tags is not None:
        entry["tags"] = tags
    idx[name] = entry


def _disk_entries(idx: dict, kind: str) -> list:
    """Zlacz index.json ze stanem dysku - pliki istnieja, nawet jesli index
    zgubil wpis (np. dopisane recznie), a wpisy bez plikow sa odfiltrowane."""
    out = []
    folder = _dir_for(kind)
    if not os.path.isdir(folder):
        return out
    for fname in os.listdir(folder):
        full = os.path.join(folder, fname)
        if not os.path.isfile(full):
            continue
        meta = idx.get(fname, {})
        if meta.get("kind", kind) != kind:
            continue
        try:
            stat = os.stat(full)
        except OSError:
            continue
        out.append({
            "name":     fname,
            "size":     stat.st_size,
            "modified": meta.get("modified", stat.st_mtime),
            "created":  meta.get("created", stat.st_ctime),
            "tags":     meta.get("tags", []),
            "format":   meta.get("format", _fmt_of(fname)),
        })
    out.sort(key=lambda e: e["modified"], reverse=True)
    return out


# -- renderowanie raportow -----------------------------------------------------

def _render_report(title: str, sections: list, fmt: str) -> str:
    """sections: lista (naglowek, [linie]) -> tresc pliku w wybranym formacie."""
    if fmt == "json":
        payload = {
            "title":      title,
            "generated":  datetime.now().isoformat(timespec="seconds"),
            "sections":   [{"header": h, "lines": ls} for h, ls in sections],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    if fmt == "html":
        parts = [f"<html><head><meta charset='utf-8'><title>{title}</title></head><body>",
                  f"<h1>{title}</h1>",
                  f"<p><em>{datetime.now().strftime('%Y-%m-%d %H:%M')}</em></p>"]
        for header, lines in sections:
            parts.append(f"<h2>{header}</h2><pre>" +
                         "\n".join(lines) + "</pre>")
        parts.append("</body></html>")
        return "\n".join(parts)

    if fmt == "md":
        parts = [f"# {title}", "", f"_{datetime.now().strftime('%Y-%m-%d %H:%M')}_", ""]
        for header, lines in sections:
            parts.append(f"## {header}")
            parts.append("")
            parts.extend(lines if lines else ["-"])
            parts.append("")
        return "\n".join(parts)

    # txt (fallback)
    parts = [title, "=" * len(title), datetime.now().strftime("%Y-%m-%d %H:%M"), ""]
    for header, lines in sections:
        parts.append(header)
        parts.append("-" * len(header))
        parts.extend(lines if lines else ["-"])
        parts.append("")
    return "\n".join(parts)


def _unique_trash_path(name: str) -> str:
    """Zwroc wolna sciezke w .trash/, dopisujac ~1, ~2, ... przy kolizji
    nazw - tak samo jak rm/del w command.py."""
    trash_path = os.path.join(TRASH_DIR, name)
    if not os.path.exists(trash_path):
        return trash_path
    base, ext = os.path.splitext(name)
    counter = 1
    while os.path.exists(trash_path):
        trash_path = os.path.join(TRASH_DIR, f"{base}~{counter}{ext}")
        counter += 1
    return trash_path


def _move_to_trash(path: str) -> bool:
    """Przenies dokument/raport do wspolnego .trash/ EcoSystemu, zamiast
    trwale go usuwac - ten sam mechanizm co rm/del (command.py) i to co
    pozwala go potem przywrocic przez `trash restore`."""
    return _integration.trash_move(path)


# -- zbieranie danych z innych modulow (przez stan terminal / pliki cache) ----

def _section_system(terminal) -> tuple:
    lines = [
        f"OS:           {platform.system()} {platform.release()}",
        f"Python:       {platform.python_version()}",
        f"Katalog:      {os.getcwd()}",
        f"Jezyk:        {getattr(terminal, 'lang', '-')}",
        f"Moduly:       {len(getattr(terminal, 'loaded_modules', {}))}",
        f"Komendy:      {len(getattr(terminal, 'commands', {}))}",
    ]
    mods = sorted(getattr(terminal, "loaded_modules", {}).keys())
    if mods:
        lines.append("Lista modulow: " + ", ".join(mods))
    return ("System", lines)


def _section_history(terminal, limit: int) -> tuple:
    entries = list(getattr(terminal, "_history", []))
    if not entries:
        return ("Historia polecen", ["modul history nie jest zaladowany lub historia jest pusta"])
    tail = entries[-limit:]
    lines = [f"{i:>4}  {e}" for i, e in enumerate(entries[-len(tail):], len(entries) - len(tail) + 1)]
    lines.insert(0, f"Pokazano {len(tail)} z {len(entries)} wpisow")
    return ("Historia polecen", lines)


def _section_tasks(terminal) -> tuple:
    tasks = getattr(terminal, "_tasks", None)
    if tasks is None:
        return ("Zadania w tle", ["modul task nie jest zaladowany"])
    if not tasks:
        return ("Zadania w tle", ["brak zadan"])
    counts: dict = {}
    lines = []
    for tid, entry in sorted(tasks.items()):
        status = getattr(entry, "status", "?")
        counts[status] = counts.get(status, 0) + 1
        label = getattr(entry, "label", "")
        lines.append(f"{tid:<5} [{status:<7}] {label}")
    summary = "  ".join(f"{k}:{v}" for k, v in counts.items())
    lines.insert(0, f"Podsumowanie: {summary}")
    return ("Zadania w tle", lines)


def _section_defender(terminal) -> tuple:
    events_file = os.path.join(ROOT_DIR, ".cache", "defender", "events.json")
    if not os.path.exists(events_file):
        return ("Ochrona (Defender)", ["modul defender nie jest zaladowany lub brak zdarzen"])
    try:
        with open(events_file, "r", encoding="utf-8") as f:
            events = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ("Ochrona (Defender)", ["nie udalo sie odczytac rejestru zdarzen"])
    if not events:
        return ("Ochrona (Defender)", ["brak zdarzen"])
    counts: dict = {}
    lines = []
    for ev in events[-50:]:
        sev = ev.get("severity", "?")
        counts[sev] = counts.get(sev, 0) + 1
        ts = _human_dt(ev.get("ts", 0))
        lines.append(f"{ts}  [{sev:<10}] {ev.get('source','-')}: {ev.get('detail','')}")
    summary = "  ".join(f"{k}:{v}" for k, v in counts.items())
    lines.insert(0, f"Ostatnie {len(lines)} zdarzen ({len(events)} ogolem) - {summary}")
    return ("Ochrona (Defender)", lines)


_SECTION_BUILDERS = {
    "system":   lambda terminal, args: [_section_system(terminal)],
    "history":  lambda terminal, args: [_section_history(terminal, _history_limit(args))],
    "tasks":    lambda terminal, args: [_section_tasks(terminal)],
    "defender": lambda terminal, args: [_section_defender(terminal)],
    "full":     lambda terminal, args: [_section_system(terminal),
                                         _section_history(terminal, _history_limit(args)),
                                         _section_tasks(terminal),
                                         _section_defender(terminal)],
}

_TITLES = {
    "system":   "Raport systemowy",
    "history":  "Raport historii polecen",
    "tasks":    "Raport zadan w tle",
    "defender": "Raport ochrony",
    "full":     "Raport zbiorczy EcoSystem",
}


def _history_limit(args: list) -> int:
    for a in args:
        if a.isdigit():
            return int(a)
    return 50


def setup(terminal):
    _ensure_dirs()
    idx = _load_index()

    def _t(key, **kw):
        return terminal.t(key, **kw)

    def _persist():
        if not _save_index(idx):
            _w(f"  {RED}{_t('docs_err_index_save')}{RST}\n")

    # ------------------------------------------------------------------ #
    #  doc - menu                                                          #
    # ------------------------------------------------------------------ #

    def doc_menu():
        _w(f"\n{BOLD}{BCYN}  +======================================+{RST}\n")
        _w(f"{BOLD}{BCYN}  |   {_t('docs_module_title')}{RST}\n")
        _w(f"{BOLD}{BCYN}  +======================================+{RST}\n\n")
        cmds = [
            ("doc new <nazwa> [tekst]",   _t("docs_help_new")),
            ("doc list [tag]",            _t("docs_help_list")),
            ("doc open <nazwa>",          _t("docs_help_open")),
            ("doc append <nazwa> <txt>",  _t("docs_help_append")),
            ("doc edit <nazwa>",          _t("docs_help_edit")),
            ("doc tag <nazwa> [tagi]",    _t("docs_help_tag")),
            ("doc rename <a> <b>",        _t("docs_help_rename")),
            ("doc export <nazwa> <fmt>",  _t("docs_help_export")),
            ("doc search <wzorzec>",      _t("docs_help_search")),
            ("doc info <nazwa>",          _t("docs_help_info")),
            ("doc rm <nazwa>",            _t("docs_help_rm")),
        ]
        for c, d in cmds:
            _w(f"  {YLW}{_pad(c, 28)}{RST} {DIM}{d}{RST}\n")
        _w("\n")

    def _resolve_existing(name: str, kind: str) -> str:
        """Zwroc pelna sciezke istniejacego dokumentu lub zglos DocError."""
        candidate = _safe_name(name)
        path = _path_for(candidate, kind)
        if os.path.isfile(path):
            return path
        # spróbuj dopasować po dowolnym znanym rozszerzeniu
        for ext in _EXTS.values():
            alt = _path_for(_safe_name(os.path.splitext(name)[0] + ext), kind)
            if os.path.isfile(alt):
                return alt
        raise DocError("missing")

    def doc_new(args):
        if not args:
            _w(f"  {RED}{_t('docs_usage_new')}{RST}\n")
            return
        try:
            base = _safe_name(args[0])
        except DocError:
            _w(f"  {RED}{_t('docs_err_bad_name')}{RST}\n")
            return
        filename = _with_ext(base, _default_fmt())
        path = _path_for(filename, "document")
        if os.path.exists(path):
            _w(f"  {RED}{_t('docs_err_exists', name=filename)}{RST}\n")
            return
        content = " ".join(args[1:])
        try:
            with open(path, "w", encoding="utf-8") as f:
                if content:
                    f.write(content + "\n")
        except OSError as exc:
            _w(f"  {RED}{_t('docs_err_write', exc=exc)}{RST}\n")
            return
        _touch_entry(idx, filename, "document", _fmt_of(filename), tags=[])
        _persist()
        _w(f"  {GRN}{_t('docs_created', name=filename)}{RST}\n")

    def _print_list(entries: list, empty_key: str):
        if not entries:
            _w(f"  {_t(empty_key)}\n")
            return
        _w(f"\n  {_pad(_t('docs_col_name'), 28)}{_pad(_t('docs_col_size'), 10)}"
           f"{_pad(_t('docs_col_modified'), 18)}{_t('docs_col_tags')}\n")
        for e in entries:
            tags = ",".join(e["tags"]) if e["tags"] else DIM + "-" + RST
            _w(f"  {_pad(e['name'], 28)}{_pad(_human_size(e['size']), 10)}"
               f"{_pad(_human_dt(e['modified']), 18)}{tags}\n")
        _w("\n")

    def doc_list(args):
        entries = _disk_entries(idx, "document")
        if args:
            tag = args[0]
            entries = [e for e in entries if tag in e["tags"]]
        _print_list(entries, "docs_list_empty")

    def doc_open(args):
        if not args:
            _w(f"  {RED}{_t('docs_usage_open')}{RST}\n")
            return
        try:
            path = _resolve_existing(args[0], "document")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                body = f.read()
        except OSError as exc:
            _w(f"  {RED}{_t('docs_err_read', exc=exc)}{RST}\n")
            return
        name = os.path.basename(path)
        _w(f"\n{BOLD}{CYN}--- {name} ---{RST}\n")
        _w(body if body.endswith("\n") else body + "\n")
        _w(f"{BOLD}{CYN}{'-' * (len(name) + 8)}{RST}\n\n")

    def doc_append(args):
        if len(args) < 2:
            _w(f"  {RED}{_t('docs_usage_append')}{RST}\n")
            return
        try:
            path = _resolve_existing(args[0], "document")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        text = " ".join(args[1:])
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError as exc:
            _w(f"  {RED}{_t('docs_err_write', exc=exc)}{RST}\n")
            return
        name = os.path.basename(path)
        _touch_entry(idx, name, "document", idx.get(name, {}).get("format", _fmt_of(name)))
        _persist()
        _w(f"  {GRN}{_t('docs_appended', name=name)}{RST}\n")

    def doc_edit(args):
        if not args:
            _w(f"  {RED}{_t('docs_usage_edit')}{RST}\n")
            return
        try:
            path = _resolve_existing(args[0], "document")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        _w(f"  {DIM}{_t('docs_edit_hint')}{RST}\n")
        lines = []
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                break
            if line == ".":
                break
            lines.append(line)
        try:
            with open(path, "a", encoding="utf-8") as f:
                for line in lines:
                    f.write(line + "\n")
        except OSError as exc:
            _w(f"  {RED}{_t('docs_err_write', exc=exc)}{RST}\n")
            return
        name = os.path.basename(path)
        _touch_entry(idx, name, "document", idx.get(name, {}).get("format", _fmt_of(name)))
        _persist()
        _w(f"  {GRN}{_t('docs_edited', name=name, n=len(lines))}{RST}\n")

    def doc_tag(args):
        if not args:
            _w(f"  {RED}{_t('docs_usage_tag')}{RST}\n")
            return
        try:
            path = _resolve_existing(args[0], "document")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        name = os.path.basename(path)
        entry = idx.setdefault(name, {})
        if len(args) == 1:
            tags = entry.get("tags", [])
            _w(f"  {name}: {', '.join(tags) if tags else _t('docs_no_tags')}\n")
            return
        tags = sorted(set(args[1:]))
        _touch_entry(idx, name, entry.get("kind", "document"),
                     entry.get("format", _fmt_of(name)), tags=tags)
        _persist()
        _w(f"  {GRN}{_t('docs_tagged', name=name, tags=', '.join(tags))}{RST}\n")

    def doc_rename(args):
        if len(args) < 2:
            _w(f"  {RED}{_t('docs_usage_rename')}{RST}\n")
            return
        try:
            old_path = _resolve_existing(args[0], "document")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        old_name = os.path.basename(old_path)
        try:
            new_name = _with_ext(_safe_name(args[1]), _fmt_of(old_name))
        except DocError:
            _w(f"  {RED}{_t('docs_err_bad_name')}{RST}\n")
            return
        new_path = _path_for(new_name, "document")
        if os.path.exists(new_path):
            _w(f"  {RED}{_t('docs_err_exists', name=new_name)}{RST}\n")
            return
        try:
            os.replace(old_path, new_path)
        except OSError as exc:
            _w(f"  {RED}{_t('docs_err_write', exc=exc)}{RST}\n")
            return
        idx[new_name] = idx.pop(old_name, {})
        _touch_entry(idx, new_name, "document", _fmt_of(new_name),
                     tags=idx[new_name].get("tags", []))
        _persist()
        _w(f"  {GRN}{_t('docs_renamed', old=old_name, new=new_name)}{RST}\n")

    def doc_export(args):
        if len(args) < 2:
            _w(f"  {RED}{_t('docs_usage_export')}{RST}\n")
            return
        fmt = args[1].lower()
        if fmt not in _EXTS:
            _w(f"  {RED}{_t('docs_err_bad_format', fmt=fmt)}{RST}\n")
            return
        try:
            src_path = _resolve_existing(args[0], "document")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                body = f.read()
        except OSError as exc:
            _w(f"  {RED}{_t('docs_err_read', exc=exc)}{RST}\n")
            return
        base, _ = os.path.splitext(os.path.basename(src_path))
        out_name = base + _EXTS[fmt]
        out_path = _path_for(out_name, "document")
        content = _render_report(base, [(_t("docs_export_section"), body.splitlines())], fmt) \
            if fmt != "txt" else body
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content if content.endswith("\n") else content + "\n")
        except OSError as exc:
            _w(f"  {RED}{_t('docs_err_write', exc=exc)}{RST}\n")
            return
        _touch_entry(idx, out_name, "document", fmt, tags=[])
        _persist()
        _w(f"  {GRN}{_t('docs_exported', name=out_name)}{RST}\n")

    def doc_search(args):
        if not args:
            _w(f"  {RED}{_t('docs_usage_search')}{RST}\n")
            return
        pattern = " ".join(args).lower()
        hits = 0
        for e in _disk_entries(idx, "document"):
            path = _path_for(e["name"], "document")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        if pattern in line.lower():
                            _w(f"  {CYN}{e['name']}{RST}:{lineno}: {line.strip()}\n")
                            hits += 1
            except OSError:
                continue
        if not hits:
            _w(f"  {_t('docs_search_no_match', pattern=pattern)}\n")

    def doc_info(args):
        if not args:
            _w(f"  {RED}{_t('docs_usage_info')}{RST}\n")
            return
        try:
            path = _resolve_existing(args[0], "document")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        name = os.path.basename(path)
        meta = idx.get(name, {})
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        _w(f"\n  {BOLD}{name}{RST}\n")
        _w(f"    {_t('docs_label_size'):<12}{_human_size(size)}\n")
        _w(f"    {_t('docs_label_created'):<12}{_human_dt(meta.get('created', 0))}\n")
        _w(f"    {_t('docs_label_modified'):<12}{_human_dt(meta.get('modified', 0))}\n")
        _w(f"    {_t('docs_label_format'):<12}{meta.get('format', _fmt_of(name))}\n")
        tags = meta.get("tags", [])
        _w(f"    {_t('docs_label_tags'):<12}{', '.join(tags) if tags else '-'}\n\n")

    def doc_rm(args):
        if not args:
            _w(f"  {RED}{_t('docs_usage_rm')}{RST}\n")
            return
        try:
            path = _resolve_existing(args[0], "document")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        if config.get("docs.confirm_delete", True):
            try:
                answer = input(f"  {YLW}{_t('docs_confirm_rm', name=os.path.basename(path))}{RST} ")
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer.strip().lower() not in ("y", "yes", "t", "tak"):
                _w(f"  {_t('docs_rm_cancelled')}\n")
                return
        name = os.path.basename(path)
        if not _move_to_trash(path):
            _w(f"  {RED}{_t('docs_err_write', exc=_t('docs_err_trash_move'))}{RST}\n")
            return
        idx.pop(name, None)
        _persist()
        _w(f"  {GRN}{_t('docs_removed', name=name)}{RST}\n")

    _DOC_SUB = {
        "new":    doc_new,
        "list":   doc_list,
        "open":   doc_open,
        "cat":    doc_open,
        "append": doc_append,
        "edit":   doc_edit,
        "tag":    doc_tag,
        "rename": doc_rename,
        "export": doc_export,
        "search": doc_search,
        "info":   doc_info,
        "rm":     doc_rm,
        "remove": doc_rm,
    }

    def doc_wrapper(args):
        if not args:
            doc_menu()
            return
        sub, rest = args[0], args[1:]
        handler = _DOC_SUB.get(sub)
        if handler is None:
            _w(f"  {RED}{_t('docs_unknown_sub', sub=sub)}{RST}\n")
            doc_menu()
            return
        handler(rest)

    # ------------------------------------------------------------------ #
    #  report                                                              #
    # ------------------------------------------------------------------ #

    def report_menu():
        _w(f"\n{BOLD}{BCYN}  +======================================+{RST}\n")
        _w(f"{BOLD}{BCYN}  |   {_t('report_module_title')}{RST}\n")
        _w(f"{BOLD}{BCYN}  +======================================+{RST}\n\n")
        cmds = [
            ("report system",            _t("report_help_system")),
            ("report history [N]",       _t("report_help_history")),
            ("report tasks",             _t("report_help_tasks")),
            ("report defender",          _t("report_help_defender")),
            ("report full",              _t("report_help_full")),
            ("report list",              _t("report_help_list")),
            ("report open <nazwa>",      _t("report_help_open")),
            ("report rm <nazwa>",        _t("report_help_rm")),
        ]
        for c, d in cmds:
            _w(f"  {YLW}{_pad(c, 28)}{RST} {DIM}{d}{RST}\n")
        _w(f"\n  {DIM}{_t('report_hint_format')}{RST}\n\n")

    def _parse_report_opts(args: list) -> tuple:
        """Wyciagnij --format/--name z args, zwroc (fmt, name, reszta)."""
        fmt = _default_fmt()
        name = None
        rest = []
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--format" and i + 1 < len(args):
                fmt = args[i + 1].lower()
                i += 2
                continue
            if a == "--name" and i + 1 < len(args):
                name = args[i + 1]
                i += 2
                continue
            rest.append(a)
            i += 1
        if fmt not in _EXTS:
            fmt = _default_fmt()
        return fmt, name, rest

    def report_generate(rtype: str, args: list):
        fmt, name, rest = _parse_report_opts(args)
        builder = _SECTION_BUILDERS[rtype]
        sections = builder(terminal, rest)
        title = _TITLES[rtype]
        content = _render_report(title, sections, fmt)

        if name:
            try:
                base = _safe_name(name)
            except DocError:
                _w(f"  {RED}{_t('docs_err_bad_name')}{RST}\n")
                return
        else:
            base = f"{rtype}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        filename = _with_ext(base, fmt)
        path = _path_for(filename, "report")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content if content.endswith("\n") else content + "\n")
        except OSError as exc:
            _w(f"  {RED}{_t('docs_err_write', exc=exc)}{RST}\n")
            _integration.notify_event(
                terminal, f"Nie udalo sie zapisac raportu: {exc}",
                kind="err", title="REPORT",
            )
            return
        _touch_entry(idx, filename, "report", fmt, tags=[rtype])
        _persist()
        _w(f"  {GRN}{_t('report_generated', name=filename)}{RST}\n")
        _integration.notify_event(
            terminal, f"Raport wygenerowany: {filename}", kind="ok", title="REPORT",
        )

    def report_list(args):
        _print_list(_disk_entries(idx, "report"), "report_list_empty")

    def report_open(args):
        if not args:
            _w(f"  {RED}{_t('docs_usage_open')}{RST}\n")
            return
        try:
            path = _resolve_existing(args[0], "report")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                body = f.read()
        except OSError as exc:
            _w(f"  {RED}{_t('docs_err_read', exc=exc)}{RST}\n")
            return
        name = os.path.basename(path)
        _w(f"\n{BOLD}{CYN}--- {name} ---{RST}\n")
        _w(body if body.endswith("\n") else body + "\n")
        _w(f"{BOLD}{CYN}{'-' * (len(name) + 8)}{RST}\n\n")

    def report_rm(args):
        if not args:
            _w(f"  {RED}{_t('docs_usage_rm')}{RST}\n")
            return
        try:
            path = _resolve_existing(args[0], "report")
        except DocError:
            _w(f"  {RED}{_t('docs_err_not_found', name=args[0])}{RST}\n")
            return
        name = os.path.basename(path)
        if not _move_to_trash(path):
            _w(f"  {RED}{_t('docs_err_write', exc=_t('docs_err_trash_move'))}{RST}\n")
            return
        idx.pop(name, None)
        _persist()
        _w(f"  {GRN}{_t('docs_removed', name=name)}{RST}\n")

    def report_wrapper(args):
        if not args:
            report_menu()
            return
        sub, rest = args[0], args[1:]
        if sub in _SECTION_BUILDERS:
            report_generate(sub, rest)
        elif sub == "list":
            report_list(rest)
        elif sub == "open":
            report_open(rest)
        elif sub in ("rm", "remove"):
            report_rm(rest)
        else:
            _w(f"  {RED}{_t('docs_unknown_sub', sub=sub)}{RST}\n")
            report_menu()

    # ------------------------------------------------------------------ #
    #  rejestracja                                                          #
    # ------------------------------------------------------------------ #

    terminal.register_command(
        "doc", doc_wrapper,
        description=_t("cmd_doc"),
        category=_t("cat_ecosystem"),
    )
    terminal.register_command(
        "report", report_wrapper,
        description=_t("cmd_report"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal):
    terminal.commands.pop("doc", None)
    terminal.commands.pop("report", None)
