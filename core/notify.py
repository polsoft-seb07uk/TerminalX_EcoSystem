"""Notification module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski
Module: notify  v2.0.0

Chmurki z powiadomieniami renderowane bezposrednio w terminalu.
Obslugiuje 5 typow, kolejke, historię, auto-dismiss i API dla innych modulow.

Nowość v2.0: tryb POPUP — powiadomienia w prawym dolnym rogu terminala
  wyswietlane bez przerywania biezacej pracy. Uzywaja sekwencji ANSI
  pozycjonowania absolutnego (save/restore cursor) wiec nie wplywaja
  na prompt ani na tresc ekranu.

Komendy:
  notify <tekst>              - powiadomienie informacyjne
  notify ok <tekst>           - sukces  (zielona chmurka)
  notify warn <tekst>         - ostrzezenie (zolta)
  notify err <tekst>          - blad (czerwona)
  notify tip <tekst>          - wskazowka (fioletowa)
  notify list                 - historia powiadomien
  notify clear                - wyczysc historię
  notify demo                 - pokaz wszystkie typy
  notify popup <tekst>        - wyswietl popup w prawym dolnym rogu
  notify popup ok|warn|err|tip <tekst>
  notify config               - pokaz/zmien konfiguracje popupow
  notify config popup on|off  - wlacz/wylacz tryb popup globalnie
  notify config duration <s>  - czas wyswietlania popupa (sekundy, 0=staly)

API dla innych modulow:
  from core.notify import send, popup
  send(terminal, "tekst", kind="ok")    # kind: info|ok|warn|err|tip
  popup(terminal, "tekst", kind="ok")   # popup w prawym dolnym rogu
  popup(terminal, "tekst", duration=5)  # popup znikajacy po 5 sek.
"""

import os
import json
import time
import shutil
import threading
import textwrap

from ._shared import CACHE_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, MGT, WHT, _w, _strip, _pad, _atomic_write
from . import _integration

_VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# Stałe
# ---------------------------------------------------------------------------

_HISTORY_FILE  = os.path.join(CACHE_DIR, "global", "notify_history.json")
_CONFIG_FILE   = os.path.join(CACHE_DIR, "global", "notify_config.json")
_MAX_HISTORY   = 100
_BUBBLE_WIDTH  = 52          # szerokość wewnętrzna chmurki (bez ramki)
_TAIL_OFFSET   = 4           # wcięcie ogonka chmurki od lewej

# Szerokość wewnętrzna popupa (bez ramki) — węższy od bubble, bo jest
# w rogu i nie powinien zasłaniać za dużo ekranu.
_POPUP_WIDTH   = 38

# ---------------------------------------------------------------------------
# Konfiguracja popupów (runtime, ładowana z pliku przy starcie)
# ---------------------------------------------------------------------------

_cfg: dict = {
    "popup_enabled":  True,   # czy tryb popup jest aktywny globalnie
    "popup_duration": 4.0,    # czas wyswietlania popupa (0 = stały, ręczne zamknięcie)
    "popup_margin_r": 2,      # margines od prawej krawędzi terminala (kolumny)
    "popup_margin_b": 1,      # margines od dolnej krawędzi terminala (wiersze)
    "popup_stack":    True,   # stackowanie wielu popupow (jeden nad drugim)
}

# Aktualny stos wyswietlanych popupow (lista offsetów wierszy względem dołu)
_popup_lock   = threading.Lock()
_popup_stack: list[int] = []   # przechowuje numer wiersza dołu każdego aktywnego popupa

# ---------------------------------------------------------------------------
# Typy powiadomień
# ---------------------------------------------------------------------------

# Każdy typ: (ikona, kolor_ramki, kolor_tytulu, kolor_tekstu, etykieta)
_KINDS: dict[str, tuple] = {
    "info": ("ℹ",  CYN,        CYN  + BOLD, WHT,  "INFO"),
    "ok":   ("✔",  GRN,        GRN  + BOLD, WHT,  "OK"),
    "warn": ("⚠",  YLW,        YLW  + BOLD, YLW,  "UWAGA"),
    "err":  ("✖",  RED,        RED  + BOLD, RED,  "BŁĄD"),
    "tip":  ("✦",  MGT,        MGT  + BOLD, MGT,  "WSKAZÓWKA"),
}

_KIND_ALIASES: dict[str, str] = {
    "success": "ok",   "error": "err",  "warning": "warn",
    "hint":    "tip",  "note":  "info", "ok": "ok",
    "info": "info",    "warn": "warn",  "err": "err",
    "tip": "tip",
}

# ---------------------------------------------------------------------------
# Wewnętrzna kolejka + lock
# ---------------------------------------------------------------------------

_queue_lock  = threading.Lock()
_pending:    list[dict] = []          # powiadomienia oczekujące
_history:    list[dict] = []          # załadowana historia
_history_loaded = False

# ---------------------------------------------------------------------------
# Pomocnicze: rozmiar terminala
# ---------------------------------------------------------------------------

def _terminal_size() -> tuple[int, int]:
    """Zwraca (cols, rows) bieżącego terminala. Fallback: (80, 24)."""
    try:
        sz = shutil.get_terminal_size(fallback=(80, 24))
        return sz.columns, sz.lines
    except Exception:
        return 80, 24


# ---------------------------------------------------------------------------
# ANSI pozycjonowanie absolutne (VT100)
# ---------------------------------------------------------------------------

def _ansi_goto(row: int, col: int) -> str:
    """ESC[row;colH — przejdź do pozycji (1-based)."""
    return f"\x1b[{row};{col}H"

def _ansi_save() -> str:
    """ESC[s — zapisz pozycję kursora."""
    return "\x1b[s"

def _ansi_restore() -> str:
    """ESC[u — przywróć pozycję kursora."""
    return "\x1b[u"

def _ansi_erase_line() -> str:
    """ESC[2K — wyczyść cały bieżący wiersz."""
    return "\x1b[2K"

def _ansi_hide_cursor() -> str:
    return "\x1b[?25l"

def _ansi_show_cursor() -> str:
    return "\x1b[?25h"


# ---------------------------------------------------------------------------
# Renderowanie chmurki (inline — oryginalna logika)
# ---------------------------------------------------------------------------

def _render_bubble(message: str, kind: str = "info", title: str = "") -> str:
    """Zwraca gotowy string z chmurką powiadomienia."""
    icon, clr, title_clr, text_clr, default_label = _KINDS.get(kind, _KINDS["info"])
    label = title if title else default_label

    w = _BUBBLE_WIDTH

    # Zawijanie tekstu
    raw_lines = message.splitlines() or [""]
    wrapped: list[str] = []
    for rl in raw_lines:
        wrapped.extend(textwrap.wrap(rl, width=w - 2) or [""])

    # Górna ramka
    top    = f"  {clr}╭{'─' * (w + 2)}╮{RST}\n"

    # Pasek tytułu
    icon_str  = f" {icon} "
    label_str = f"{title_clr}{icon_str}{label}{RST}{clr}"
    pad_title = w + 2 - len(f" {icon} {label}") - 1
    title_row = f"  {clr}│{label_str}{' ' * max(0, pad_title)} {clr}│{RST}\n"

    # Separator
    sep    = f"  {clr}├{'─' * (w + 2)}┤{RST}\n"

    # Wiersze treści
    body_rows = ""
    for line in wrapped:
        visible_len = len(_strip(line))
        padding     = w - visible_len
        body_rows  += f"  {clr}│{RST} {text_clr}{line}{RST}{' ' * max(0, padding)} {clr}│{RST}\n"

    # Dolna ramka
    bottom = f"  {clr}╰{'─' * (w + 2)}╯{RST}\n"

    # Ogonek chmurki
    tail_pad = " " * (_TAIL_OFFSET + 2)
    tail = f"  {tail_pad}{clr}╲_{RST}\n"

    return top + title_row + sep + body_rows + bottom + tail


def _render_compact(message: str, kind: str = "info") -> str:
    """Jednolinijkowa mini-chmurka (dla krótkich powiadomień z API)."""
    icon, clr, title_clr, text_clr, label = _KINDS.get(kind, _KINDS["info"])
    short = message if len(message) <= _BUBBLE_WIDTH else message[:_BUBBLE_WIDTH - 3] + "…"
    w     = len(_strip(short)) + 6
    top   = f"  {clr}╭{'─' * w}╮{RST}\n"
    row   = f"  {clr}│{RST} {title_clr}{icon}{RST} {text_clr}{short}{RST} {clr}│{RST}\n"
    bot   = f"  {clr}╰{'─' * w}╯{RST}\n"
    tail_pad = " " * (_TAIL_OFFSET + 2)
    tail  = f"  {tail_pad}{clr}╲_{RST}\n"
    return top + row + bot + tail


# ---------------------------------------------------------------------------
# Renderowanie POPUP (dolny prawy róg)
# ---------------------------------------------------------------------------

def _render_popup_lines(message: str, kind: str = "info", title: str = "") -> list[str]:
    """Zwraca listę wierszy popupa (bez \n na końcu każdego).

    Każdy wiersz ma stałą szerokość _POPUP_WIDTH + 4 (ramka + spacje).
    """
    icon, clr, title_clr, text_clr, default_label = _KINDS.get(kind, _KINDS["info"])
    label = title if title else default_label

    w = _POPUP_WIDTH

    # Zawijanie treści
    raw_lines = message.splitlines() or [""]
    wrapped: list[str] = []
    for rl in raw_lines:
        wrapped.extend(textwrap.wrap(rl, width=w - 2) or [""])

    lines: list[str] = []

    # Górna ramka
    lines.append(f"{clr}╭{'─' * (w + 2)}╮{RST}")

    # Pasek tytułu
    icon_str  = f" {icon} "
    visible_title = f"{icon_str}{label}"
    pad_title = w + 2 - len(visible_title) - 1
    lines.append(f"{clr}│{title_clr}{visible_title}{RST}{clr}{' ' * max(0, pad_title)} │{RST}")

    # Separator
    lines.append(f"{clr}├{'─' * (w + 2)}┤{RST}")

    # Wiersze treści
    for line in wrapped:
        visible_len = len(_strip(line))
        padding     = w - visible_len
        lines.append(f"{clr}│{RST} {text_clr}{line}{RST}{' ' * max(0, padding)} {clr}│{RST}")

    # Dolna ramka
    lines.append(f"{clr}╰{'─' * (w + 2)}╯{RST}")

    return lines


def _popup_box_width() -> int:
    """Widoczna szerokość ramki popupa w kolumnach."""
    return _POPUP_WIDTH + 4   # ╭ + space + content + space + ╮


def _draw_popup(lines: list[str], start_row: int, term_cols: int) -> None:
    """Narysuj popup zaczynając od wiersza start_row.

    Używa save/restore cursor — nie psuje bieżącej pozycji.
    """
    box_w  = _popup_box_width()
    col    = max(1, term_cols - box_w - _cfg["popup_margin_r"] + 1)

    buf = [_ansi_save(), _ansi_hide_cursor()]
    for i, line in enumerate(lines):
        buf.append(_ansi_goto(start_row + i, col))
        buf.append(line)
    buf.append(_ansi_restore())
    buf.append(_ansi_show_cursor())

    _w("".join(buf))


def _erase_popup(num_lines: int, start_row: int, term_cols: int) -> None:
    """Wyczyść obszar popupa (nadpisz spacjami)."""
    box_w  = _popup_box_width()
    col    = max(1, term_cols - box_w - _cfg["popup_margin_r"] + 1)
    blank  = " " * (box_w + 2)

    buf = [_ansi_save(), _ansi_hide_cursor()]
    for i in range(num_lines):
        buf.append(_ansi_goto(start_row + i, col))
        buf.append(blank)
    buf.append(_ansi_restore())
    buf.append(_ansi_show_cursor())

    _w("".join(buf))


def _next_popup_row(num_lines: int, term_rows: int) -> int:
    """Wyznacz wiersz startowy dla nowego popupa (stackowanie).

    Zwraca numer wiersza (1-based) od góry terminala.
    Gdy stos jest pusty — popup trafia przy dolnej krawędzi.
    Gdy są już aktywne popupy — nowy popup pojawia się nad nimi.
    """
    margin_b = _cfg["popup_margin_b"]

    if not _popup_stack or not _cfg["popup_stack"]:
        # Pierwszy popup / stackowanie wyłączone: tuż przy dole
        return max(1, term_rows - num_lines - margin_b)

    # Stos: powyżej najwyżej umieszczonego aktywnego popupa
    topmost_start = min(_popup_stack)
    # 1 wiersz odstępu między popupami
    return max(1, topmost_start - num_lines - 1)


# ---------------------------------------------------------------------------
# Publiczna funkcja popup
# ---------------------------------------------------------------------------

def popup(terminal,
          message:  str,
          kind:     str   = "info",
          title:    str   = "",
          duration: float | None = None) -> None:
    """Wyświetl powiadomienie popup w prawym dolnym rogu terminala.

    Parametry:
        terminal  - instancja TerminalX (może być None)
        message   - treść powiadomienia
        kind      - info | ok | warn | err | tip
        title     - opcjonalny nadpis (domyślnie: etykieta typu)
        duration  - czas wyswietlania w sek. (None = z konfiguracji)
                    0 = popup stały (nie znika automatycznie)
    """
    kind = _KIND_ALIASES.get(kind.lower(), "info")
    if duration is None:
        duration = _cfg["popup_duration"]

    _add_to_history(message, kind, title)

    lines        = _render_popup_lines(message, kind, title)
    num_lines    = len(lines)
    term_cols, term_rows = _terminal_size()

    with _popup_lock:
        start_row = _next_popup_row(num_lines, term_rows)
        _popup_stack.append(start_row)

    _draw_popup(lines, start_row, term_cols)

    if duration and duration > 0:
        def _dismiss():
            time.sleep(duration)
            # Odśwież rozmiar terminala (mógł się zmienić)
            cols, _ = _terminal_size()
            _erase_popup(num_lines, start_row, cols)
            with _popup_lock:
                try:
                    _popup_stack.remove(start_row)
                except ValueError:
                    pass

        t = threading.Thread(target=_dismiss, daemon=True)
        t.start()


# ---------------------------------------------------------------------------
# Historia
# ---------------------------------------------------------------------------

def _load_history() -> None:
    global _history, _history_loaded
    if _history_loaded:
        return
    try:
        os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
        with open(_HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        _history = data if isinstance(data, list) else []
    except FileNotFoundError:
        _history = []
    except (json.JSONDecodeError, OSError):
        _history = []
    _history_loaded = True


def _save_history() -> None:
    _atomic_write(_HISTORY_FILE, _history[-_MAX_HISTORY:], makedirs=True, fsync=False)


def _add_to_history(message: str, kind: str, title: str) -> None:
    _load_history()
    _history.append({
        "ts":      time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind":    kind,
        "title":   title,
        "message": message,
    })
    if len(_history) > _MAX_HISTORY:
        _history[:] = _history[-_MAX_HISTORY:]
    _save_history()


# ---------------------------------------------------------------------------
# Konfiguracja popupów — zapis / odczyt
# ---------------------------------------------------------------------------

def _load_config() -> None:
    try:
        os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        _cfg.update({k: v for k, v in saved.items() if k in _cfg})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass


def _save_config() -> None:
    _atomic_write(_CONFIG_FILE, _cfg, makedirs=True, fsync=False)


# ---------------------------------------------------------------------------
# Publiczne API dla innych modułów
# ---------------------------------------------------------------------------

def send(terminal, message: str, kind: str = "info",
         title: str = "", compact: bool = False) -> None:
    """Wyświetl powiadomienie i zapisz do historii.

    Jeśli tryb popup jest globalnie włączony (cfg popup_enabled),
    wiadomość trafia jako popup w rogu; w przeciwnym razie jako
    inline bubble pod bieżącym wierszem.

    Parametry:
        terminal  - instancja TerminalX (może być None — wtedy brak tłumaczeń)
        message   - treść powiadomienia
        kind      - info | ok | warn | err | tip
        title     - opcjonalny nadpis (domyślnie: etykieta typu)
        compact   - jednolinijkowy styl inline (ignorowany w trybie popup)
    """
    kind = _KIND_ALIASES.get(kind.lower(), "info")

    if _cfg.get("popup_enabled"):
        popup(terminal, message, kind=kind, title=title)
        return

    # Fallback: tryb inline
    _add_to_history(message, kind, title)
    _w("\n")
    if compact:
        _w(_render_compact(message, kind))
    else:
        _w(_render_bubble(message, kind, title))
    _w("\n")


def send_later(terminal, message: str, delay: float,
               kind: str = "info", title: str = "") -> None:
    """Wyświetl powiadomienie po delay sekundach (w tle, nie blokuje REPL)."""
    kind = _KIND_ALIASES.get(kind.lower(), "info")

    def _fire():
        time.sleep(delay)
        if _cfg.get("popup_enabled"):
            popup(terminal, message, kind=kind, title=title)
        else:
            _w("\n")
            _w(_render_bubble(message, kind, title))
            _w("\n")
            _add_to_history(message, kind, title)

    t = threading.Thread(target=_fire, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Komendy
# ---------------------------------------------------------------------------

def _cmd_show(args: list, _t) -> None:
    """notify [kind] <tekst>"""
    if not args:
        _w(f"\n  {RED}{_t('notify_usage')}{RST}\n\n")
        return

    first = args[0].lower()
    if first in _KIND_ALIASES:
        kind  = _KIND_ALIASES[first]
        parts = args[1:]
    else:
        kind  = "info"
        parts = args

    if not parts:
        _w(f"\n  {RED}{_t('notify_no_message')}{RST}\n\n")
        return

    message = " ".join(parts)
    _w("\n")
    _w(_render_bubble(message, kind))
    _w("\n")
    _add_to_history(message, kind, "")


def _cmd_popup(args: list, _t) -> None:
    """notify popup [kind] <tekst>"""
    if not args:
        _w(f"\n  {RED}{_t('notify_usage')}{RST}\n\n")
        return

    first = args[0].lower()
    if first in _KIND_ALIASES:
        kind  = _KIND_ALIASES[first]
        parts = args[1:]
    else:
        kind  = "info"
        parts = args

    if not parts:
        _w(f"\n  {RED}{_t('notify_no_message')}{RST}\n\n")
        return

    message = " ".join(parts)
    # Popup z domyślnym czasem z konfiguracji
    popup(None, message, kind=kind)


def _cmd_config(args: list, _t) -> None:
    """notify config [klucz wartość]"""
    if not args:
        # Pokaż bieżącą konfigurację
        _w(f"\n  {BOLD}{CYN}{_t('notify_config_title')}{RST}\n\n")
        rows = [
            ("popup_enabled",  str(_cfg["popup_enabled"])),
            ("popup_duration", f"{_cfg['popup_duration']} s  (0 = stały)"),
            ("popup_margin_r", f"{_cfg['popup_margin_r']} kol."),
            ("popup_margin_b", f"{_cfg['popup_margin_b']} wier."),
            ("popup_stack",    str(_cfg["popup_stack"])),
        ]
        for key, val in rows:
            _w(f"    {YLW}{_pad(key, 20)}{RST}  {WHT}{val}{RST}\n")
        _w(f"\n  {DIM}{_t('notify_config_hint')}{RST}\n\n")
        return

    sub = args[0].lower()

    if sub == "popup" and len(args) >= 2:
        val = args[1].lower()
        if val in ("on", "1", "true"):
            _cfg["popup_enabled"] = True
            _save_config()
            _w(f"\n  {GRN}✔ Tryb popup: WŁĄCZONY{RST}\n\n")
        elif val in ("off", "0", "false"):
            _cfg["popup_enabled"] = False
            _save_config()
            _w(f"\n  {YLW}⚠ Tryb popup: WYŁĄCZONY{RST}\n\n")
        else:
            _w(f"\n  {RED}Użycie: notify config popup on|off{RST}\n\n")
        return

    if sub == "duration" and len(args) >= 2:
        try:
            secs = float(args[1])
            if secs < 0:
                raise ValueError
            _cfg["popup_duration"] = secs
            _save_config()
            label = f"{secs} s" if secs > 0 else "stały (nie znika)"
            _w(f"\n  {GRN}✔ Czas popupa: {label}{RST}\n\n")
        except ValueError:
            _w(f"\n  {RED}Użycie: notify config duration <sekundy>{RST}\n\n")
        return

    if sub == "stack" and len(args) >= 2:
        val = args[1].lower()
        if val in ("on", "1", "true"):
            _cfg["popup_stack"] = True
            _save_config()
            _w(f"\n  {GRN}✔ Stackowanie popupów: WŁĄCZONE{RST}\n\n")
        elif val in ("off", "0", "false"):
            _cfg["popup_stack"] = False
            _save_config()
            _w(f"\n  {YLW}⚠ Stackowanie popupów: WYŁĄCZONE{RST}\n\n")
        else:
            _w(f"\n  {RED}Użycie: notify config stack on|off{RST}\n\n")
        return

    _w(f"\n  {RED}Nieznana opcja: {sub}{RST}\n")
    _w(f"  {DIM}Dostępne: popup on|off, duration <s>, stack on|off{RST}\n\n")


def _cmd_list(_t) -> None:
    """notify list — historia powiadomień."""
    _load_history()
    if not _history:
        _w(f"\n  {DIM}{_t('notify_history_empty')}{RST}\n\n")
        return

    _w(f"\n  {BOLD}{CYN}{_t('notify_history_title')}{RST}\n\n")
    for entry in reversed(_history[-20:]):   # ostatnie 20
        kind  = entry.get("kind", "info")
        icon, clr, *_ = _KINDS.get(kind, _KINDS["info"])
        ts    = entry.get("ts", "")
        msg   = entry.get("message", "")
        short = msg if len(msg) <= 48 else msg[:45] + "…"
        _w(f"  {clr}{icon}{RST}  {DIM}{ts}{RST}  {short}\n")
    _w(f"\n  {DIM}{_t('notify_history_hint', n=len(_history))}{RST}\n\n")


def _cmd_clear(_t) -> None:
    """notify clear — wyczyść historię."""
    global _history, _history_loaded
    _history = []
    _history_loaded = True
    _save_history()
    _w(f"\n  {GRN}{_t('notify_cleared')}{RST}\n\n")


def _cmd_demo(_t) -> None:
    """notify demo — pokaż wszystkie typy: inline + popup."""
    _w(f"\n  {BOLD}{CYN}{_t('notify_demo_title')}{RST}\n\n")
    _w(f"  {DIM}── Inline bubbles ─────────────────────────────────{RST}\n\n")
    samples = [
        ("info", _t("notify_demo_info")),
        ("ok",   _t("notify_demo_ok")),
        ("warn", _t("notify_demo_warn")),
        ("err",  _t("notify_demo_err")),
        ("tip",  _t("notify_demo_tip")),
    ]
    for kind, msg in samples:
        _w(_render_bubble(msg, kind))
        _w("\n")

    _w(f"  {DIM}── Popupy w prawym dolnym rogu (stackowane) ────────{RST}\n\n")
    for i, (kind, msg) in enumerate(samples):
        popup(None, msg, kind=kind, duration=3.0 + i * 0.5)
        time.sleep(0.25)   # małe opóźnienie aby stos był widoczny


def _cmd_help(_t) -> None:
    _w(f"\n  {BOLD}{CYN}notify  v{_VERSION}{RST}  {DIM}—  {_t('notify_module_desc')}{RST}\n\n")
    rows = [
        ("notify <tekst>",              _t("notify_help_info")),
        ("notify ok <tekst>",           _t("notify_help_ok")),
        ("notify warn <tekst>",         _t("notify_help_warn")),
        ("notify err <tekst>",          _t("notify_help_err")),
        ("notify tip <tekst>",          _t("notify_help_tip")),
        ("notify popup <tekst>",        "Popup w prawym dolnym rogu"),
        ("notify popup ok|warn|… <t>",  "Popup z typem"),
        ("notify config",               "Pokaż konfigurację popupów"),
        ("notify config popup on|off",  "Włącz/wyłącz tryb popup globalnie"),
        ("notify config duration <s>",  "Czas wyswietlania popupa (0=stały)"),
        ("notify config stack on|off",  "Stackowanie wielu popupów"),
        ("notify list",                 _t("notify_help_list")),
        ("notify clear",                _t("notify_help_clear")),
        ("notify demo",                 _t("notify_help_demo")),
    ]
    for cmd, desc in rows:
        _w(f"    {YLW}{_pad(cmd, 32)}{RST}  {DIM}{desc}{RST}\n")
    _w("\n")
    _w(f"  {DIM}{_t('notify_api_hint')}{RST}\n")
    _w(f"  {DIM}API popup:  from core.notify import popup{RST}\n")
    _w(f"  {DIM}            popup(terminal, 'tekst', kind='ok', duration=5){RST}\n\n")


# ---------------------------------------------------------------------------
# setup / teardown
# ---------------------------------------------------------------------------

def setup(terminal) -> None:
    _load_history()
    _load_config()

    def _t(key: str, **kw) -> str:
        return terminal.t(key, **kw)

    _SUB_MAP = {
        "list":   lambda a: _cmd_list(_t),
        "clear":  lambda a: _cmd_clear(_t),
        "demo":   lambda a: _cmd_demo(_t),
        "help":   lambda a: _cmd_help(_t),
        "--help": lambda a: _cmd_help(_t),
        "-h":     lambda a: _cmd_help(_t),
        "popup":  lambda a: _cmd_popup(a, _t),
        "config": lambda a: _cmd_config(a, _t),
    }

    def notify_cmd(args: list) -> None:
        if not args:
            _cmd_help(_t)
            return
        sub = args[0].lower()
        if sub in _SUB_MAP:
            _SUB_MAP[sub](args[1:])
        else:
            _cmd_show(args, _t)

    terminal.register_command(
        "notify", notify_cmd,
        description=_t("cmd_notify"),
        category=_t("cat_ecosystem"),
    )

    # Udostępnij API innym modułom przez terminal.notify
    terminal.notify = lambda msg, kind="info", title="", compact=False: \
        send(terminal, msg, kind=kind, title=title, compact=compact)
    terminal.notify_later = lambda msg, delay=0.0, kind="info", title="": \
        send_later(terminal, msg, delay, kind=kind, title=title)
    terminal.notify_popup = lambda msg, kind="info", title="", duration=None: \
        popup(terminal, msg, kind=kind, title=title, duration=duration)

    # Udostępnij API w globalnym rejestrze _integration, aby moduly w tle
    # (np. watki demonow defendera/task) mogly wyslac powiadomienie nawet
    # bez bezposredniej referencji do obiektu terminal.
    _integration.register("notify", {
        "send":       send,
        "send_later": send_later,
        "popup":      popup,
    })


def teardown(terminal) -> None:
    terminal.commands.pop("notify", None)
    for attr in ("notify", "notify_later", "notify_popup"):
        if hasattr(terminal, attr):
            delattr(terminal, attr)
    _integration.unregister("notify")
