#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# crossterm: {"id": "01", "aliases": ["dos", "dosbox"], "description": "Uruchamia gry i programy DOSowe przez DOSBox", "version": "1.2.0"}
"""
╔══════════════════════════════════════════════════════════════════╗
║                     DOS Module v1.2.0                            ║
╠══════════════════════════════════════════════════════════════════╣
║  File    : __init__.py                                           ║
║  Author  : Sebastian Januchowski                                 ║
║  Company : polsoft.ITS(TM) Group                                 ║
║  Web     : https://www.polsoft.gt.tc                             ║
║  GitHub  : https://github.com/seb07uk                            ║
║  Email   : polsoft.its@fastservice.com                           ║
╠══════════════════════════════════════════════════════════════════╣
║  Moduł DOS – uruchamianie gier i programów DOSowych przez        ║
║  DOSBox. Integracja z CrossTerm (CML_COMMANDS + on_load).        ║
╠══════════════════════════════════════════════════════════════════╣
║  Komendy:                                                        ║
║    dos           – lista komend (pomoc)                          ║
║    dos run       – uruchamia DOSBox (tryb konsoli)               ║
║    dos list      – lista zapisanych gier/programów               ║
║    dos <nazwa>   – uruchamia zapisaną grę/program                ║
║    dos add <n> <ścieżka> [args...]  – dodaje program do listy    ║
║    dos remove <nazwa>               – usuwa program z listy      ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import json
import subprocess
from pathlib import Path

# ── Metadata modułu ───────────────────────────────────────────────────────────

METADATA = {
    "name"       : "dos",
    "version"    : "1.2.0",
    "author"     : "Sebastian Januchowski",
    "company"    : "polsoft.ITS(TM) Group",
    "web"        : "https://www.polsoft.gt.tc",
    "github"     : "https://github.com/seb07uk",
    "email"      : "polsoft.its@fastservice.com",
    "description": "dos_meta_desc",   # klucz i18n — rozwijany przez terminal.t()
    "type"       : "library",
    "depends"    : [],
    "exports"    : ["CML_COMMANDS", "cml_menu", "on_load", "on_unload"],
    "min_pyterm" : "2.0.0",
}

# ── Ścieżki modułu — STAŁA LOKALIZACJA ───────────────────────────────────────

_MODULE_DIR    = Path(__file__).parent
_DOSBOX_EXE    = _MODULE_DIR / "bin" / "DOSBox.exe"
_PROGRAMS_FILE = _MODULE_DIR / "programs.json"
_DOSBOX_CONF   = _MODULE_DIR / "dosbox.conf"

# ── Cache ─────────────────────────────────────────────────────────────────────

_programs_cache = None
_dosbox_ok      = None
_conf_arg       = []
_terminal       = None   # ustawiany przez setup()


def _t(k, **kw):
    """Tłumaczenie klucza przez terminal (fallback: klucz)."""
    if _terminal is None:
        return k
    return _terminal.t(k, **kw)


# ── ANSI helpers ──────────────────────────────────────────────────────────────

class _C:
    RST    = "\x1b[0m"
    BOLD   = "\x1b[1m"
    DIM    = "\x1b[2m"
    RED    = "\x1b[91m"
    GRN    = "\x1b[92m"
    YEL    = "\x1b[93m"
    CYN    = "\x1b[96m"
    WHT    = "\x1b[97m"
    BG_CYN = "\x1b[46m"    # tło cyjanowe — podświetlenie pickera


def _w(s):
    sys.stdout.write(s)
    sys.stdout.flush()


# ── Lifecycle hooks ───────────────────────────────────────────────────────────

def on_load():
    """Wywoływana przez CrossTerm przy ładowaniu modułu."""
    global _dosbox_ok, _conf_arg
    _dosbox_ok = _DOSBOX_EXE.exists()
    _conf_arg  = ["-conf", str(_DOSBOX_CONF)] if _DOSBOX_CONF.exists() else []


def on_unload():
    """Wywoływana przez CrossTerm przy wyładowaniu modułu."""
    global _programs_cache, _dosbox_ok, _conf_arg
    _programs_cache = None
    _dosbox_ok      = None
    _conf_arg       = []


# ── Menu CML ──────────────────────────────────────────────────────────────────

def cml_menu():
    """Wyświetla menu modułu DOS w CML."""
    status     = f"{_C.GRN}{_t('dos_status_ok')}{_C.RST}" if _check_dosbox() else f"{_C.RED}{_t('dos_status_err')}{_C.RST}"
    status_raw = _t("dos_status_ok") if _check_dosbox() else _t("dos_status_err")
    C1 = 26   # szerokość kolumny komend
    C2 = 30   # szerokość kolumny opisów
    W  = C1 + C2 + 3   # szerokość wewnętrzna całej ramki (bez pionowych krawędzi)

    top    = f"╔{'═' * (C1 + 2)}╤{'═' * (C2 + 2)}╗"
    mid    = f"╠{'═' * (C1 + 2)}╪{'═' * (C2 + 2)}╣"
    div    = f"╟{'─' * (C1 + 2)}┼{'─' * (C2 + 2)}╢"
    bot    = f"╚{'═' * (C1 + 2)}╧{'═' * (C2 + 2)}╝"
    htop   = f"╔{'═' * (W + 2)}╗"
    hmid   = f"╠{'═' * (C1 + 2)}╤{'═' * (C2 + 2)}╣"
    hbot   = f"╟{'─' * (W + 2)}╢"
    fbot   = f"╚{'═' * (W + 2)}╝"

    rows = [
        ("dos",                         _t("dos_row_help")),
        ("dos run",                     _t("dos_row_run")),
        ("dos run <komenda>",            _t("dos_row_run_cmd")),
        ("dos search <fraza>",           _t("dos_row_search")),
        ("dos list",                    _t("dos_row_list")),
        ("dos <nazwa>",                 _t("dos_row_launch")),
        ("dos add <n> <p>",             _t("dos_row_add")),
        ("dos rename <stara> <nowa>",   _t("dos_row_rename")),
        ("dos edit <nazwa> [p] [args]", _t("dos_row_edit")),
        ("dos info <nazwa>",            _t("dos_row_info")),
        ("dos remove <nazwa>",          _t("dos_row_remove")),
        ("dos conf [nazwa]",            _t("dos_row_conf")),
        ("dos export <plik>",           _t("dos_row_export")),
        ("dos import <plik>",           _t("dos_row_import")),
    ]

    _col_cmd  = _t("dos_col_cmd")
    _col_desc = _t("dos_col_desc")
    _title    = f"DOS Module v{METADATA['version']}  –  polsoft.ITS(TM) Group"

    _w(f"\n")
    _w(f"  {_C.BOLD}{_C.CYN}{htop}{_C.RST}\n")
    _w(f"  {_C.BOLD}{_C.CYN}║{_C.RST} {_C.BOLD}{_title:<{W}}{_C.RST} {_C.BOLD}{_C.CYN}║{_C.RST}\n")
    _w(f"  {_C.BOLD}{_C.CYN}{hmid}{_C.RST}\n")
    _w(f"  {_C.BOLD}{_C.CYN}║{_C.RST} {_C.BOLD}{_col_cmd:<{C1}}{_C.RST} {_C.BOLD}{_C.CYN}│{_C.RST} {_C.BOLD}{_col_desc:<{C2}}{_C.RST} {_C.BOLD}{_C.CYN}║{_C.RST}\n")
    _w(f"  {_C.BOLD}{_C.CYN}{mid}{_C.RST}\n")
    for cmd, desc in rows:
        _w(f"  {_C.CYN}║{_C.RST} {_C.YEL}{cmd:<{C1}}{_C.RST} {_C.CYN}│{_C.RST} {desc:<{C2}} {_C.CYN}║{_C.RST}\n")
    _w(f"  {_C.BOLD}{_C.CYN}{hbot}{_C.RST}\n")
    _vis_status_line = f"DOSBox: {status_raw}"
    _w(f"  {_C.CYN}║{_C.RST}  DOSBox: {status}{' ' * max(0, W - len(_vis_status_line) - 1)}{_C.CYN}║{_C.RST}\n")
    _mdir = str(_MODULE_DIR)
    _mdir_disp = _mdir if len(_mdir) <= W - 2 else "…" + _mdir[-(W - 3):]
    _w(f"  {_C.CYN}║{_C.RST}  {_C.DIM}{_mdir_disp:<{W - 2}}{_C.RST} {_C.CYN}║{_C.RST}\n")
    _w(f"  {_C.BOLD}{_C.CYN}{fbot}{_C.RST}\n")
    _w(f"\n")


# ── CML_COMMANDS — rejestracja komend globalnych CrossTerm ───────────────────
#
#  Sygnatura: fn(args: list, terminal) -> None
#  Wynik wypisuje się przez _w() — NIE zwraca stringa.

def _cmd_dos(args, terminal):
    """Dispatcher komendy 'dos'."""
    global _terminal
    # Przy wywołaniu przez CML_COMMANDS (autoexec) setup() może nie być jeszcze
    # uruchomiony — inicjalizujemy stan modułu jeśli potrzeba.
    if _terminal is None and terminal is not None:
        _terminal = terminal
    if _dosbox_ok is None:
        on_load()

    sub = args[0].lower() if args else ""

    if   sub in ("", "help")            : _cmd_help()
    elif sub == "run"                   : _cmd_run(args[1:])
    elif sub in ("list", "ls")          : _cmd_list()
    elif sub in ("search", "find")      : _cmd_search(args[1:])
    elif sub == "add"                   : _cmd_add(args[1:])
    elif sub in ("rename", "mv")        : _cmd_rename(args[1:])
    elif sub == "edit"                  : _cmd_edit(args[1:])
    elif sub in ("info", "show")        : _cmd_info(args[1:])
    elif sub in ("remove", "rm", "del") : _cmd_remove(args[1:])
    elif sub == "conf"                  : _cmd_conf(args[1:])
    elif sub == "export"                : _cmd_export(args[1:])
    elif sub == "import"                : _cmd_import(args[1:])
    else                                : _cmd_launch(sub)


MODULE_CMD            = "dos"
MODULE_DESCRIPTION    = "Emulator DOS — uruchamia gry i programy DOSowe przez DOSBox"
MODULE_DESCRIPTION_EN = "DOS emulator — run DOS games and programs via DOSBox"
MODULE_VERSION        = "1.2.0"

CML_COMMANDS = {
    "dos": _cmd_dos,
}


# ── Implementacje komend ──────────────────────────────────────────────────────

def _cmd_help():
    C1 = 26   # szerokość kolumny komend
    C2 = 30   # szerokość kolumny opisów
    W  = C1 + C2 + 3   # szerokość wewnętrzna całej ramki

    top  = f"╔{'═' * (W + 2)}╗"
    hmid = f"╠{'═' * (C1 + 2)}╤{'═' * (C2 + 2)}╣"
    mid  = f"╠{'═' * (C1 + 2)}╪{'═' * (C2 + 2)}╣"
    bot  = f"╚{'═' * (W + 2)}╝"

    rows = [
        ("dos",                           _t("dos_row_help")),
        ("dos run",                       _t("dos_row_run")),
        ("dos run <komenda>",              _t("dos_row_run_cmd")),
        ("dos search <fraza>",             _t("dos_row_search")),
        ("dos list",                      _t("dos_row_list")),
        ("dos <nazwa>",                   _t("dos_row_launch")),
        ("dos add <n> <path>",            _t("dos_row_add")),
        ("dos rename <stara> <nowa>",     _t("dos_row_rename")),
        ("dos edit <nazwa> [path] [args]",_t("dos_row_edit")),
        ("dos info <nazwa>",              _t("dos_row_info")),
        ("dos remove <nazwa>",            _t("dos_row_remove")),
        ("dos conf [nazwa]",              _t("dos_row_conf")),
        ("dos export <plik>",             _t("dos_row_export")),
        ("dos import <plik>",             _t("dos_row_import")),
    ]
    _col_cmd  = _t("dos_col_cmd")
    _col_desc = _t("dos_col_desc")
    _htitle   = f"{_t('dos_help_title')}  v{METADATA['version']} (c) {METADATA['company']}"

    _w(f"\n")
    _w(f"  {_C.BOLD}{top}{_C.RST}\n")
    _w(f"  {_C.BOLD}║{_C.RST} {_C.CYN}{_C.BOLD}{_t('dos_help_title')}{_C.RST}  {_C.DIM}v{METADATA['version']} (c) {METADATA['company']}{_C.RST}{' ' * max(0, W - len(_htitle))} {_C.BOLD}║{_C.RST}\n")
    _w(f"  {_C.BOLD}{hmid}{_C.RST}\n")
    _w(f"  {_C.BOLD}║{_C.RST} {_C.BOLD}{_col_cmd:<{C1}}{_C.RST} {_C.BOLD}│{_C.RST} {_C.BOLD}{_col_desc:<{C2}}{_C.RST} {_C.BOLD}║{_C.RST}\n")
    _w(f"  {_C.BOLD}{mid}{_C.RST}\n")
    for cmd, desc in rows:
        _w(f"  ║ {_C.YEL}{cmd:<{C1}}{_C.RST} │ {desc:<{C2}} ║\n")
    _w(f"  {_C.BOLD}{bot}{_C.RST}\n")
    _w(f"\n")
    _w(f"  {_C.DIM}{_t('dos_help_example')}{_C.RST}\n")
    _w(f"    {_C.GRN}dos add doom C:\\Games\\DOOM\\DOOM.EXE{_C.RST}\n")
    _w(f"    {_C.GRN}dos doom{_C.RST}\n")
    _w(f"\n")
    _w(f"  {_C.DIM}{_t('dos_help_location')} {_MODULE_DIR}{_C.RST}\n")
    _w(f"\n")


def _cmd_run(argv=None):
    """dos run [komenda] — uruchamia DOSBox; z argumentem przekazuje -c <komenda>."""
    if not _check_dosbox():
        _w(_err_no_dosbox())
        return
    extra = []
    if argv:
        cmd_str = ' '.join(argv)
        extra = ['-c', cmd_str]
    proc = _launch_dosbox([str(_DOSBOX_EXE)] + _conf_arg + extra)
    label = f"'{' '.join(argv)}'" if argv else _t("dos_run_console")
    _w(f"{_C.GRN}[dos]{_C.RST} {_t('dos_run_started')} {_C.DIM}({label}, PID: {proc.pid}){_C.RST}\n")


def _cmd_list():
    """Interaktywny launcher — strzałki ↑↓ wybór, Enter uruchamia, Esc/q wychodzi."""
    programs = _get_programs()
    if not programs:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_list_empty')}\n")
        return

    # #6 — sortuj po last_run (ostatnio używane na górze), reszta alfabetycznie
    items   = sorted(programs.items(),
                     key=lambda kv: kv[1].get("last_run", ""), reverse=True)
    count   = len(items)
    sel     = 0                           # aktualnie podświetlona pozycja

    # ── Rysowanie listy ───────────────────────────────────────────────────────

    # Szerokości kolumn
    COL1 = 20   # nazwa
    COL2 = 42   # sciezka
    W    = COL1 + COL2 + 7   # | sp COL1 sp | sp COL2 sp |

    def _draw(redraw=False):
        """Rysuje liste; redraw=True nadpisuje poprzedni blok."""
        lines = count + 5   # 1 pusty + naglowek + sep + wpisy + dolna ramka
        if redraw:
            _w(f"\x1b[{lines}A")
            for _ in range(lines):
                _w("\x1b[2K\r\n")
            _w(f"\x1b[{lines}A")

        top  = f"╔{'═' * (COL1 + 2)}╤{'═' * (COL2 + 2)}╗"
        htop = f"╔{'═' * (COL1 + COL2 + 5)}╗"
        hmid = f"╠{'═' * (COL1 + COL2 + 5)}╣"
        bot  = f"╚{'═' * (COL1 + 2)}╧{'═' * (COL2 + 2)}╝"

        _w(f"\n")
        _w(f"  {_C.BOLD}{htop}{_C.RST}\n")
        title = _t("dos_list_title")
        _w(f"  {_C.BOLD}║{_C.RST} {_C.BOLD}{title:<{COL1 + COL2 + 3}}{_C.RST} {_C.BOLD}║{_C.RST}\n")
        _w(f"  {_C.BOLD}{top}{_C.RST}\n")

        for idx, (name, entry) in enumerate(items):
            col2_str = entry.get("description") or entry["path"]
            if len(col2_str) > COL2:
                col2_str = col2_str[:COL2-1] + "…"

            if idx == sel:
                marker = "▶"
                n_fmt  = f"{_C.BG_CYN}{_C.BOLD}{_C.WHT}{marker} {name:<{COL1-2}}{_C.RST}"
                p_fmt  = f"{_C.BG_CYN}{_C.WHT}{col2_str:<{COL2}}{_C.RST}"
            else:
                marker = " "
                n_fmt  = f"{_C.YEL}{marker} {name:<{COL1-2}}{_C.RST}"
                p_fmt  = f"{_C.DIM}{col2_str:<{COL2}}{_C.RST}"

            _w(f"  {_C.BOLD}║{_C.RST} {n_fmt} {_C.BOLD}│{_C.RST} {p_fmt} {_C.BOLD}║{_C.RST}\n")

        _w(f"  {_C.BOLD}{bot}{_C.RST}\n")

    # ── Czytanie klawisza (Windows msvcrt / POSIX termios) ────────────────────

    def _read():
        """Zwraca token: 'UP', 'DOWN', 'ENTER', 'ESC', 'Q' lub None."""
        if sys.platform == "win32":
            import msvcrt
            ch = msvcrt.getwch()
            if ch in ('\x00', '\xe0'):
                ch2 = msvcrt.getwch()
                if ch2 == 'H': return 'UP'
                if ch2 == 'P': return 'DOWN'
                return None
            if ch == '\r': return 'ENTER'
            if ch == '\x1b': return 'ESC'
            if ch.lower() == 'q': return 'Q'
            return None
        else:
            import tty, termios, select as _sel
            fd  = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
                if ch == '\x1b':
                    r, _, _ = _sel.select([sys.stdin], [], [], 0.05)
                    if r:
                        seq = sys.stdin.read(2)
                        if seq == '[A': return 'UP'
                        if seq == '[B': return 'DOWN'
                    return 'ESC'
                if ch == '\r' or ch == '\n': return 'ENTER'
                if ch.lower() == 'q': return 'Q'
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            return None

    # ── Pętla pickera ─────────────────────────────────────────────────────────

    _draw()
    chosen = None

    while True:
        key = _read()
        if key == 'UP':
            sel = (sel - 1) % count
            _draw(redraw=True)
        elif key == 'DOWN':
            sel = (sel + 1) % count
            _draw(redraw=True)
        elif key == 'ENTER':
            chosen = items[sel]
            break
        elif key in ('ESC', 'Q'):
            _w(f"{_C.DIM}[dos] {_t('dos_list_cancelled')}{_C.RST}\n")
            return

    # ── Uruchom wybrany program ───────────────────────────────────────────────

    name, entry = chosen
    _cmd_launch(name)


def _cmd_add(argv):
    if len(argv) < 2:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_add_usage')}\n")
        return

    name, exe_path = argv[0], argv[1]

    # Wyłów --desc <opis> z pozostałych argumentów
    rest  = argv[2:]
    desc  = None
    extra = []
    i = 0
    while i < len(rest):
        if rest[i] == "--desc" and i + 1 < len(rest):
            desc = rest[i + 1]
            i += 2
        else:
            extra.append(rest[i])
            i += 1

    programs = _get_programs()
    key = name.lower()

    if key in programs:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_add_exists', key=key)}\n")
        return

    programs[key] = {"path": exe_path}
    if desc:
        programs[key]["description"] = desc
    if extra:
        programs[key]["args"] = extra

    _save_programs(programs)
    desc_label = f"  {_C.DIM}{desc}{_C.RST}" if desc else ""
    _w(f"{_C.GRN}[dos]{_C.RST} {_t('dos_add_ok', key=key, path=exe_path)}{desc_label}\n")

    if not Path(exe_path).exists():
        _w(f"  {_C.YEL}{_t('dos_add_warn_missing', path=exe_path)}{_C.RST}\n")
        _w(f"  {_C.DIM}{_t('dos_add_warn_hint')}{_C.RST}\n")


def _cmd_remove(argv):
    if not argv:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_remove_usage')}\n")
        return

    key = argv[0].lower()
    programs = _get_programs()

    if key not in programs:
        _w(f"{_C.RED}[dos]{_C.RST} {_t('dos_remove_notfound', key=key)}\n")
        return

    del programs[key]
    _save_programs(programs)
    _w(f"{_C.GRN}[dos]{_C.RST} {_t('dos_remove_ok', key=key)}\n")


def _cmd_search(argv):
    """dos search <fraza> — filtruje liste programow po nazwie lub sciezce."""
    if not argv:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_search_usage')}\n")
        return

    fraza    = ' '.join(argv).lower()
    programs = _get_programs()
    hits     = {k: v for k, v in programs.items()
                if fraza in k or fraza in v.get('path', '').lower()}

    if not hits:
        _w(f"  {_C.DIM}{_t('dos_search_nohits', fraza=fraza)}{_C.RST}\n")
        return

    COL1, COL2 = 20, 42
    top = f"╔{'═' * (COL1 + 2)}╤{'═' * (COL2 + 2)}╗"
    htop = f"╔{'═' * (COL1 + COL2 + 5)}╗"
    mid  = f"╠{'═' * (COL1 + 2)}╪{'═' * (COL2 + 2)}╣"
    bot  = f"╚{'═' * (COL1 + 2)}╧{'═' * (COL2 + 2)}╝"
    _w(f"\n  {_C.BOLD}{htop}{_C.RST}\n")
    title = _t("dos_search_hits", fraza=fraza, n=len(hits))
    _w(f"  {_C.BOLD}║{_C.RST} {_C.BOLD}{title:<{COL1+COL2+3}}{_C.RST} {_C.BOLD}║{_C.RST}\n")
    _w(f"  {_C.BOLD}{top}{_C.RST}\n")
    for name, entry in sorted(hits.items()):
        path_str = entry['path']
        if len(path_str) > COL2:
            path_str = '~' + path_str[-(COL2-1):]
        exists = Path(entry['path']).exists()
        ico    = f"{_C.GRN}✓{_C.RST}" if exists else f"{_C.RED}✗{_C.RST}"
        _w(f"  {_C.BOLD}║{_C.RST} {ico} {_C.YEL}{name:<{COL1-2}}{_C.RST} {_C.BOLD}│{_C.RST} {_C.DIM}{path_str:<{COL2}}{_C.RST} {_C.BOLD}║{_C.RST}\n")
    _w(f"  {_C.BOLD}{bot}{_C.RST}\n\n")


def _cmd_info(argv):
    """dos info <nazwa> — szczegoly wpisu: sciezka, argumenty, istnienie pliku."""
    if not argv:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_info_usage')}\n")
        return

    key = argv[0].lower()
    programs = _get_programs()

    if key not in programs:
        _w(f"{_C.RED}[dos]{_C.RST} {_t('dos_info_notfound', key=key)}\n")
        return

    entry    = programs[key]
    exe_path = entry['path']
    exists   = Path(exe_path).exists()
    args_val = entry.get('args', [])

    ok_ico  = f"{_C.GRN}{_t('dos_info_exists')}{_C.RST}"
    bad_ico = f"{_C.RED}{_t('dos_info_missing')}{_C.RST}"

    conf_val  = entry.get('conf', None)
    launches  = entry.get('launches', 0)
    last_run  = entry.get('last_run', None)

    _w(f"\n")
    _w(f"  {_C.BOLD}╔{'═' * 42}╗{_C.RST}\n")
    _w(f"  {_C.BOLD}║{_C.RST} {_C.CYN}{_C.BOLD}{key:<40}{_C.RST} {_C.BOLD}║{_C.RST}\n")
    _w(f"  {_C.BOLD}╠{'═' * 42}╣{_C.RST}\n")
    _w(f"  {_C.BOLD}║{_C.RST} {_C.DIM}{_t('dos_info_path'):<12}{_C.RST} {exe_path[:28]:<28} {_C.BOLD}║{_C.RST}\n")
    _w(f"  {_C.BOLD}║{_C.RST} {_C.DIM}{_t('dos_info_file'):<12}{_C.RST} {ok_ico if exists else bad_ico}{' ' * (28 - len(_t('dos_info_exists') if exists else _t('dos_info_missing')))} {_C.BOLD}║{_C.RST}\n")
    _args_str = ' '.join(args_val) if args_val else _C.DIM + _t('dos_info_none') + _C.RST
    _w(f"  {_C.BOLD}║{_C.RST} {_C.DIM}{_t('dos_info_args'):<12}{_C.RST} {_args_str:<28} {_C.BOLD}║{_C.RST}\n")
    _conf_str = conf_val if conf_val else _C.DIM + _t('dos_info_global') + _C.RST
    _w(f"  {_C.BOLD}║{_C.RST} {_C.DIM}{_t('dos_info_conf'):<12}{_C.RST} {_conf_str:<28} {_C.BOLD}║{_C.RST}\n")
    _w(f"  {_C.BOLD}╟{'─' * 42}╢{_C.RST}\n")
    _last_str = last_run if last_run else _C.DIM + _t('dos_info_never') + _C.RST
    _w(f"  {_C.BOLD}║{_C.RST} {_C.DIM}{_t('dos_info_launches'):<12}{_C.RST} {launches}x   {_C.DIM}{_t('dos_info_lastrun')}{_C.RST} {_last_str}\n")
    _w(f"  {_C.BOLD}╚{'═' * 42}╝{_C.RST}\n")
    _w(f"\n")


def _cmd_edit(argv):
    """dos edit <nazwa> [nowa_sciezka] [args...]

    Bez podania sciezki — pokazuje aktualny wpis.
    Z nowa_sciezka      — aktualizuje sciezke (i opcjonalnie argumenty).
    Argumenty po sciezce zastepuja stare; podaj - aby usunac argumenty.
    """
    if not argv:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_edit_usage')}\n")
        _w(f"      {_C.DIM}{_t('dos_edit_nopath_hint')}{_C.RST}\n")
        return

    key = argv[0].lower()
    programs = _get_programs()

    if key not in programs:
        _w(f"{_C.RED}[dos]{_C.RST} {_t('dos_edit_notfound', key=key)}\n")
        return

    entry = programs[key]

    # Tylko wyswietl
    if len(argv) == 1:
        args_val = entry.get('args', [])
        args_str = ' '.join(args_val) if args_val else _C.DIM + _t('dos_info_none') + _C.RST
        _w(f"\n  {_C.BOLD}{_C.WHT}{key}{_C.RST}\n")
        _w(f"  {_C.DIM}{_t('dos_edit_path')} {_C.RST}{entry['path']}\n")
        _w(f"  {_C.DIM}{_t('dos_info_args')} {_C.RST}{args_str}\n\n")
        _w(f"  {_C.DIM}{_t('dos_edit_show_hint', key=key)}{_C.RST}\n\n")
        return

    # dos edit <nazwa> desc=<opis> — ustawia opis
    if argv[1].startswith("desc="):
        desc_val = argv[1][5:]
        if desc_val == "-":
            entry.pop("description", None)
        else:
            entry["description"] = desc_val
        programs[key] = entry
        _save_programs(programs)
        _w(f"{_C.GRN}[dos]{_C.RST} {_t('dos_edit_desc_ok', key=key, val=desc_val if desc_val != '-' else _t('dos_edit_removed'))}\n")
        return

    # dos edit <nazwa> conf=<sciezka> — ustawia per-program conf
    if argv[1].startswith("conf="):
        conf_path = argv[1][5:]
        entry["conf"] = conf_path if conf_path != "-" else None
        if entry["conf"] is None:
            entry.pop("conf", None)
        programs[key] = entry
        _save_programs(programs)
        label = conf_path if conf_path != "-" else _t("dos_edit_removed")
        _w(f"{_C.GRN}[dos]{_C.RST} {_t('dos_edit_conf_ok', key=key, val=label)}\n")
        return

    new_path = argv[1]
    new_args  = argv[2:] if len(argv) > 2 else None

    old_path = entry['path']
    entry['path'] = new_path

    if new_args is not None:
        if new_args == ['-']:
            entry.pop('args', None)
        else:
            entry['args'] = new_args

    programs[key] = entry
    _save_programs(programs)

    _w(f"{_C.GRN}[dos]{_C.RST} {_t('dos_edit_ok', key=key)}\n")
    _w(f"  {_C.DIM}{_t('dos_edit_path')} {_C.RST}{old_path} {_C.DIM}→{_C.RST} {new_path}\n")
    if new_args is not None:
        if new_args == ['-']:
            _w(f"  {_C.DIM}{_t('dos_edit_args_removed')}{_C.RST}\n")
        else:
            _w(f"  {_C.DIM}{_t('dos_edit_args')} {_C.RST}{' '.join(new_args)}\n")
    _w("\n")

def _cmd_rename(argv):
    if len(argv) < 2:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_rename_usage')}\n")
        return

    old_key = argv[0].lower()
    new_key = argv[1].lower()
    programs = _get_programs()

    if old_key not in programs:
        _w(f"{_C.RED}[dos]{_C.RST} {_t('dos_rename_notfound', key=old_key)}\n")
        return

    if new_key in programs:
        _w(f"{_C.RED}[dos]{_C.RST} {_t('dos_rename_taken', key=new_key)}\n")
        return

    programs[new_key] = programs.pop(old_key)
    _save_programs(programs)
    _w(f"{_C.GRN}[dos]{_C.RST} {_t('dos_rename_ok', old=old_key, new=new_key)}\n")

def _cmd_launch(name):
    if not _check_dosbox():
        _w(_err_no_dosbox())
        return

    programs = _get_programs()
    entry    = programs.get(name.lower())

    if not entry:
        _w(
            f"{_C.RED}[dos]{_C.RST} {_t('dos_launch_notfound', name=name)}\n"
            f"      {_C.DIM}{_t('dos_launch_hint')}{_C.RST}\n"
        )
        return

    # #9 — per-program conf (nadpisuje globalny gdy ustawiony)
    if entry.get("conf") and Path(entry["conf"]).exists():
        prog_conf_arg = ["-conf", entry["conf"]]
    else:
        prog_conf_arg = _conf_arg
    pargs = [str(_DOSBOX_EXE), entry["path"]] + prog_conf_arg + ["-exit"]
    if entry.get("args"):
        pargs += entry["args"]

    proc = _launch_dosbox(pargs)

    # #6 — licznik uruchomień i znacznik czasu
    import datetime
    programs = _get_programs()
    prog_entry = programs.get(name.lower(), entry)
    prog_entry["launches"]  = prog_entry.get("launches", 0) + 1
    prog_entry["last_run"]  = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    programs[name.lower()]  = prog_entry
    _save_programs(programs)

    launches = prog_entry["launches"]
    _w(f"{_C.GRN}[dos]{_C.RST} {_t('dos_launch_ok', name=name, path=entry['path'])}  "
       f"{_C.DIM}{_t('dos_launch_pid', pid=proc.pid, n=launches)}{_C.RST}\n")


# ── conf TUI — parser / serializer ───────────────────────────────────────────

def _conf_parse(path: Path):
    """Parsuje dosbox.conf → lista tokenow: ('section', name) | ('entry', key, val, raw) | ('comment', raw)."""
    tokens = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            tokens.append(("section", stripped[1:-1], raw))
        elif "=" in stripped and not stripped.startswith("#") and not stripped.startswith(";"):
            k, _, v = stripped.partition("=")
            tokens.append(("entry", k.strip(), v.strip(), raw))
        else:
            tokens.append(("comment", raw))
    return tokens


def _conf_serialize(tokens) -> str:
    parts = []
    for t in tokens:
        if t[0] == "section":
            parts.append(f"[{t[1]}]")
        elif t[0] == "entry":
            parts.append(f"{t[1]}={t[2]}")
        else:
            parts.append(t[1])
    return "\n".join(parts) + "\n"


def _conf_sections(tokens):
    """Zwraca listę (section_name, [(key, val), ...])."""
    sections = []
    cur_name = None
    cur_entries = []
    for t in tokens:
        if t[0] == "section":
            if cur_name is not None:
                sections.append((cur_name, cur_entries))
            cur_name = t[1]
            cur_entries = []
        elif t[0] == "entry":
            cur_entries.append((t[1], t[2]))
    if cur_name is not None:
        sections.append((cur_name, cur_entries))
    return sections


# ── conf TUI — wejście klawiatury (wspólne z _cmd_list) ──────────────────────

def _conf_read_key():
    """Zwraca token klawisza: UP/DOWN/LEFT/RIGHT/ENTER/ESC/BACKSPACE/CHAR(c)."""
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            if ch2 == "H": return ("NAV", "UP")
            if ch2 == "P": return ("NAV", "DOWN")
            if ch2 == "K": return ("NAV", "LEFT")
            if ch2 == "M": return ("NAV", "RIGHT")
            return ("NAV", None)
        if ch == "\r":  return ("NAV", "ENTER")
        if ch == "\x1b": return ("NAV", "ESC")
        if ch in ("\x08", "\x7f"): return ("NAV", "BACKSPACE")
        return ("CHAR", ch)
    else:
        import tty, termios, select as _sel
        fd  = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                r, _, _ = _sel.select([sys.stdin], [], [], 0.05)
                if r:
                    seq = sys.stdin.read(2)
                    if seq == "[A": return ("NAV", "UP")
                    if seq == "[B": return ("NAV", "DOWN")
                    if seq == "[D": return ("NAV", "LEFT")
                    if seq == "[C": return ("NAV", "RIGHT")
                return ("NAV", "ESC")
            if ch in ("\r", "\n"): return ("NAV", "ENTER")
            if ch in ("\x08", "\x7f"): return ("NAV", "BACKSPACE")
            return ("CHAR", ch)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── conf TUI — główny edytor ──────────────────────────────────────────────────

def _conf_tui(conf_path: Path):
    """
    Trzypoziomowy TUI edytor dosbox.conf:
      Poziom 1 — lista sekcji
      Poziom 2 — lista kluczy w sekcji
      Poziom 3 — edycja wartości (inline input)
    Nawigacja: ↑↓ wybór, Enter wejście/zatwierdź, Esc cofnij/wyjdź, ←→ jak Esc/Enter.
    """
    W     = 60
    COL1  = 18
    COL2  = W - COL1 - 5

    def _clr():
        _w("\x1b[2J\x1b[H")

    def _hide_cursor():  _w("\x1b[?25l")
    def _show_cursor():  _w("\x1b[?25h")

    def _draw_header(title, path_label):
        sep = "+" + "-" * (W - 2) + "+"
        _w(f"  {_C.BOLD}{_C.CYN}{sep}{_C.RST}\n")
        _w(f"  {_C.BOLD}{_C.CYN}|{_C.RST} {_C.BOLD}DOS conf editor  {_C.DIM}{title:<{W-20}}{_C.RST} {_C.BOLD}{_C.CYN}|{_C.RST}\n")
        _w(f"  {_C.BOLD}{_C.CYN}|{_C.RST} {_C.DIM}{str(path_label):<{W-4}}{_C.RST} {_C.BOLD}{_C.CYN}|{_C.RST}\n")
        _w(f"  {_C.BOLD}{_C.CYN}{sep}{_C.RST}\n")

    def _draw_footer(hint):
        sep = "+" + "-" * (W - 2) + "+"
        _w(f"  {_C.BOLD}{_C.CYN}{sep}{_C.RST}\n")
        _w(f"  {_C.DIM}  {hint:<{W-4}}{_C.RST}\n")
        _w(f"  {_C.BOLD}{_C.CYN}{sep}{_C.RST}\n")

    # ── poziom 1: wybór sekcji ────────────────────────────────────────────────

    def _level_sections():
        tokens   = _conf_parse(conf_path)
        sections = _conf_sections(tokens)
        sel      = 0

        while True:
            _clr()
            _draw_header(_t("dos_tui_sec_hint"), conf_path.name)
            for i, (sname, entries) in enumerate(sections):
                if i == sel:
                    _w(f"  {_C.BG_CYN}{_C.BOLD}{_C.WHT}  > [{sname}]{' ' * max(0, W-8-len(sname))}{_C.RST}\n")
                else:
                    _w(f"  {_C.YEL}    [{sname}]{_C.RST}  {_C.DIM}({_t('dos_tui_keys_count', n=len(entries))}){_C.RST}\n")
            _draw_footer(_t("dos_tui_nav_sections"))

            k = _conf_read_key()
            if k == ("NAV", "UP"):
                sel = (sel - 1) % len(sections)
            elif k == ("NAV", "DOWN"):
                sel = (sel + 1) % len(sections)
            elif k in (("NAV", "ENTER"), ("NAV", "RIGHT")):
                changed = _level_keys(sections[sel][0], conf_path)
                if changed:
                    tokens   = _conf_parse(conf_path)
                    sections = _conf_sections(tokens)
            elif k in (("NAV", "ESC"), ("NAV", "LEFT")):
                _clr()
                return

    # ── poziom 2: wybór klucza w sekcji ──────────────────────────────────────

    def _level_keys(section_name, conf_path):
        """Zwraca True jeśli cokolwiek zmieniono."""
        tokens  = _conf_parse(conf_path)
        changed = False
        sel     = 0

        while True:
            tokens   = _conf_parse(conf_path)
            sections = _conf_sections(tokens)
            entries  = next((e for s, e in sections if s == section_name), [])

            _clr()
            _draw_header(f"[{section_name}]", conf_path.name)
            for i, (k, v) in enumerate(entries):
                v_disp = v if len(v) <= COL2 else v[:COL2-1] + "…"
                if i == sel:
                    row = f"  > {k:<{COL1}} = {v_disp}"
                    _w(f"  {_C.BG_CYN}{_C.BOLD}{_C.WHT}{row:<{W-2}}{_C.RST}\n")
                else:
                    _w(f"  {_C.DIM}    {_C.RST}{_C.YEL}{k:<{COL1}}{_C.RST} {_C.DIM}= {v_disp}{_C.RST}\n")
            _draw_footer(_t("dos_tui_nav_keys"))

            kk = _conf_read_key()
            if kk == ("NAV", "UP"):
                sel = (sel - 1) % max(1, len(entries))
            elif kk == ("NAV", "DOWN"):
                sel = (sel + 1) % max(1, len(entries))
            elif kk in (("NAV", "ENTER"), ("NAV", "RIGHT")):
                if entries:
                    key_name, old_val = entries[sel]
                    new_val = _level_edit(section_name, key_name, old_val, conf_path)
                    if new_val is not None and new_val != old_val:
                        _conf_set(conf_path, section_name, key_name, new_val)
                        changed = True
            elif kk in (("NAV", "ESC"), ("NAV", "LEFT")):
                return changed

    # ── poziom 3: edycja wartości ─────────────────────────────────────────────

    def _level_edit(section_name, key_name, old_val, conf_path):
        """Inline input — zwraca nową wartość lub None (anulowano)."""
        buf = list(old_val)

        while True:
            _clr()
            _draw_header(f"[{section_name}] → {key_name}", conf_path.name)
            _w(f"\n  {_C.DIM}{_t('dos_tui_old_val')}{_C.RST} {old_val}\n")
            _w(f"  {_C.BOLD}{_t('dos_tui_new_val')} {_C.RST}{_C.WHT}{''.join(buf)}{_C.BOLD}▌{_C.RST}\n\n")
            _draw_footer(_t("dos_tui_edit_hint"))

            k = _conf_read_key()
            if k == ("NAV", "ESC"):
                return None
            elif k == ("NAV", "ENTER"):
                return "".join(buf)
            elif k == ("NAV", "BACKSPACE"):
                if buf:
                    buf.pop()
            elif k[0] == "CHAR" and k[1].isprintable():
                buf.append(k[1])

    # ── zapis zmiany do pliku ─────────────────────────────────────────────────

    def _conf_set(conf_path, section_name, key_name, new_val):
        tokens   = _conf_parse(conf_path)
        in_sec   = False
        new_tok  = []
        for t in tokens:
            if t[0] == "section":
                in_sec = (t[1] == section_name)
                new_tok.append(t)
            elif t[0] == "entry" and in_sec and t[1] == key_name:
                new_tok.append(("entry", t[1], new_val, f"{t[1]}={new_val}"))
            else:
                new_tok.append(t)
        conf_path.write_text(_conf_serialize(new_tok), encoding="utf-8")

    _hide_cursor()
    try:
        _level_sections()
    finally:
        _show_cursor()
        _clr()
    _w(f"  {_C.GRN}✓{_C.RST} {_t('dos_tui_done', path=conf_path)}\n")


# ── _cmd_conf — dispatcher ────────────────────────────────────────────────────

def _cmd_conf(argv):
    """dos conf [nazwa] — interaktywny TUI edytor dosbox.conf."""
    if argv:
        key = argv[0].lower()
        programs = _get_programs()
        if key not in programs:
            _w(f"{_C.RED}[dos]{_C.RST} {_t('dos_conf_notfound', key=key)}\n")
            return
        entry     = programs[key]
        conf_path = Path(entry["conf"]) if entry.get("conf") else None
        if not conf_path or not conf_path.exists():
            default = _MODULE_DIR / "conf" / f"{key}.conf"
            _w(f"  {_C.DIM}{_t('dos_conf_no_perconf', key=key)}{_C.RST}\n")
            _w(f"  {_C.DIM}{_t('dos_conf_suggest', path=default)}{_C.RST}\n")
            _w(f"  {_C.DIM}{_t('dos_conf_set_hint', key=key)}{_C.RST}\n")
            return
        target = conf_path
    else:
        target = _DOSBOX_CONF
        if not target.exists():
            _w(f"  {_C.YEL}[dos]{_C.RST} {_t('dos_conf_no_global', path=target)}\n")
            return

    _conf_tui(target)


def _cmd_export(argv):
    """dos export <plik> — zapisuje programs.json do podanego pliku."""
    if not argv:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_export_usage')}\n")
        return
    out = Path(argv[0]).expanduser().resolve()
    try:
        programs = _get_programs()
        out.write_text(
            json.dumps(programs, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        _w(f"  {_C.GRN}✓{_C.RST} {_t('dos_export_ok', n=len(programs), path=out)}\n")
    except Exception as e:
        _w(f"  {_C.RED}{_t('dos_export_err', e=e)}{_C.RST}\n")


def _cmd_import(argv):
    """dos import <plik> — scala programy z JSON do aktualnej listy (bez nadpisywania)."""
    if not argv:
        _w(f"{_C.YEL}[dos]{_C.RST} {_t('dos_import_usage')}\n")
        return
    src       = Path(argv[0]).expanduser().resolve()
    overwrite = "--overwrite" in [a.lower() for a in argv[1:]]
    if not src.exists():
        _w(f"  {_C.RED}{_t('dos_import_nofile', path=src)}{_C.RST}\n")
        return
    try:
        imported = json.loads(src.read_text(encoding="utf-8"))
        if not isinstance(imported, dict):
            _w(f"  {_C.RED}{_t('dos_import_badfmt')}{_C.RST}\n")
            return
        programs = _get_programs()
        added = skipped = updated = 0
        for k, v in imported.items():
            if k.startswith("_"):
                continue
            if k in programs:
                if overwrite:
                    programs[k] = v
                    updated += 1
                else:
                    skipped += 1
            else:
                programs[k] = v
                added += 1
        _save_programs(programs)
        _w(f"  {_C.GRN}{_t('dos_import_added', n=added)}{_C.RST}")
        if updated:  _w(f"  {_C.YEL}{_t('dos_import_updated', n=updated)}{_C.RST}")
        if skipped:  _w(f"  {_C.DIM}{_t('dos_import_skipped', n=skipped)}{_C.RST}")
        _w("\n")
        if skipped and not overwrite:
            _w(f"  {_C.DIM}{_t('dos_import_overwrite_hint')}{_C.RST}\n")
    except Exception as e:
        _w(f"  {_C.RED}{_t('dos_import_err', e=e)}{_C.RST}\n")


# ── Uruchamianie procesu ──────────────────────────────────────────────────────

def _launch_dosbox(args):
    """
    Uruchamia DOSBox jako oddzielny proces — terminal nie blokuje się.

    Na Windows NIE używamy DETACHED_PROCESS — DOSBox (SDL) wymaga
    dostępu do konsoli/środowiska Win32 przy starcie; DETACHED_PROCESS
    odcina ten dostęp i powoduje błąd VC++ Runtime.

    Zamiast tego: CREATE_NEW_CONSOLE (własne okno DOSBox) +
    CREATE_NEW_PROCESS_GROUP (izolacja sygnałów Ctrl+C).
    stdout/stderr → DEVNULL, więc terminal nie blokuje się.
    """
    kwargs = {
        "stdout"   : subprocess.DEVNULL,
        "stderr"   : subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_CONSOLE
            | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        kwargs.pop("close_fds")   # close_fds nieobsługiwane na Windows

    return subprocess.Popen(args, **kwargs)


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _check_dosbox():
    global _dosbox_ok
    if _dosbox_ok is None:
        _dosbox_ok = _DOSBOX_EXE.exists()
    return _dosbox_ok


def _err_no_dosbox():
    return (
        f"{_C.RED}[dos] {_t('dos_err_no_exe', path=_DOSBOX_EXE)}{_C.RST}\n"
        f"      {_C.DIM}{_t('dos_err_no_exe_hint', dir=_MODULE_DIR / 'bin')}{_C.RST}\n"
    )


def _get_programs():
    global _programs_cache
    if _programs_cache is None:
        _programs_cache = _load_programs()
    return _programs_cache


def _load_programs():
    if not _PROGRAMS_FILE.exists():
        return {}
    try:
        data = json.loads(_PROGRAMS_FILE.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        return {}


def _save_programs(programs):
    _PROGRAMS_FILE.write_text(
        json.dumps(programs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    global _programs_cache
    _programs_cache = programs


# ── EcoSystem integration ─────────────────────────────────────────────────────

def setup(terminal):
    """Rejestruje komendę 'dos' w TerminalX EcoSystem."""
    global _terminal
    _terminal = terminal
    on_load()

    cat = terminal.t("cat_tools")

    def _dos(args):
        _cmd_dos(args, terminal)

    terminal.register_command(
        "dos", _dos,
        description=_t("dos_meta_desc"),
        category=cat,
    )


def teardown(terminal):
    """Wyrejestrowuje komendę 'dos' z TerminalX EcoSystem."""
    global _terminal
    on_unload()
    _terminal = None
    terminal.commands.pop("dos", None)
