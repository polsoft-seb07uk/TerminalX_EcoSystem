"""Help module for TerminalX.

polsoft.ITS(TM) Group  *  Sebastian Januchowski

Pokazuje wszystkie dostepne komendy pogrupowane wedlug kategorii.
Kazda kategoria renderowana oddzielnie z ikona i podpowiedzia.

Grupy glowne (z _CAT_ORDER):
  EcoSystem  - moduly core (runner, scripts, tools, analyser, ...)
  nawigacja  - cd, ls, cp, mv, cat, ...
  ogolne     - help, lang, ?
  historia   - history, hrun
  aliasy     - alias
  srodowisko - env
  siec       - net.diag
  zadania    - task

Reguly widocznosci EcoSystem:
  ECOSYSTEM_SHOW  - zawsze widoczne (glowne komendy kazdego modulu)
  ECOSYSTEM_ALIAS - pokazywane jako "(alias)" - wyswietlane, ale oznaczone
  reszta          - ukryte (sub-komendy kolorow, cfg-duplikat, itp.)
"""

import sys
import re

# -- Widoczne komendy EcoSystem ------------------------------------------------
# Glowne - wyswietlane normalnie
from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _strip
ECOSYSTEM_SHOW = {
    "analyser",   # analyser.py   - analizator plikow
    "ansi",       # ansi.py       - ANSI / style / kursor
    "cache",      # cache.py      - globalny cache
    "color",      # colors.py     - kolory (menu)
    "config",     # config.py     - ustawienia
    "debug",      # debugger.py   - interaktywny debugger
    "defender",   # defender.py   - ochrona
    "doc",        # docs.py       - menedzer dokumentow
    "img",        # imgtools.py   - narzedzia graficzne
    "python",     # pkg.py        - python package management
    "lang",       # lang.py       - przelaczanie jezyka
    "monitor",    # monitor.py    - monitor systemu (CPU, RAM, dysk, siec)
    "net.diag",   # net_diag.py   - diagnostyka sieci (IP, DNS, porty, routing)
    "notify",    # notify.py     - chmurki powiadomien
    "pkg",        # pkg.py        - package manager
    "report",     # docs.py       - generator raportow
    "run",        # runner.py     - script runner
    "sandbox",    # sandbox.py    - izolowane srodowisko uruchamiania
    "scripts",    # scripts.py    - menedzer skryptow
    "search",     # search.py     - wyszukiwarka plikow
    "sha256",     # sha256.py     - sumy kontrolne SHA-256
    "switch",     # switch.py          - przełącznik CLI ↔ GUI
    "tests",      # tests.py           - testy jednostkowe
    "tools",      # tools.py           - menedzer narzedzi
    "trash",      # trash.py           - smietnik
    "video",      # video_downloader.py - pobieranie wideo (yt-dlp)
    "admin",      # admin.py            - system/core admin (sys fs net sec data math proc)
    "ai",         # ai.py               - asystent AI (30+ modeli, presety, GUI chat)
    "vdrive",     # vdrive.py           - wirtualne dyski ISO/VHD
    "venv",       # virtual_env.py      - wirtualne srodowiska Python
    "math",       # math_engine.py      - silnik obliczen matematycznych
    "update",     # update.py           - aktualizacja terminala z GitHub
}

# Aliasy - widoczne, wyswietlane w osobnej podsekcji lub oznaczone
ECOSYSTEM_ALIAS = {
    "analyse",    # alias -> analyser
    "bin",        # alias -> trash
    "cfg",        # alias -> config
    "dbg",        # alias -> debug (debugger)
    "find",       # alias -> search
    "runner",     # alias -> run (menu)
    "sbx",        # alias -> sandbox
    "mon",        # alias -> monitor
    "sa",         # alias -> admin
    "yt",         # alias -> video (video_downloader)
    "ytdl",       # alias -> video (video_downloader)
    "youtube",    # alias -> video (video_downloader)
    "vimeo",      # alias -> video (video_downloader)
    "dwl",        # alias -> video (video_downloader)
    "chat",       # alias -> ai chat
    "gpt",        # alias -> ai ask (OpenAI)
    "claude",     # alias -> ai ask (Anthropic)
    "gemini",     # alias -> ai ask (Google)
    "iso",        # alias -> vdrive (montowanie ISO)
    "vhd",        # alias -> vdrive (montowanie VHD)
    "ve",         # alias -> venv (virtual env)
    "virtualenv", # alias -> venv (virtual env)
}

# Wszystkie widoczne w EcoSystem
ECOSYSTEM_MAIN = ECOSYSTEM_SHOW | ECOSYSTEM_ALIAS


# Sub-komendy kolorow - ukryte (dostepne przez `color`)
COLORS_SUBS = {
    "colorize", "colors", "converter", "effects",
    "gradient", "hq", "mix", "palette", "preview",
    "rainbow", "scheme", "strip", "theme",
}

# Ikony kategorii
_CAT_ICONS = {
    "ecosystem": "⬡",
    "nav":       "◈",
    "general":   "◇",
    "history":   "◎",
    "alias":     "◉",
    "env":       "◆",
    "net.diag":  "◈",
    "task":      "◐",
    "tools":     "◧",
}

# -- ANSI ---------------------------------------------------------------------

_re_ansi = re.compile(r'\x1b\[[0-9;]*[mA-Z]')


def _w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def _wln(s: str = "") -> None:
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def _vw(s: str) -> int:
    """Widoczna szerokosc stringa (bez ANSI)."""
    return len(_re_ansi.sub('', s))


def _pad(s: str, w: int) -> str:
    return s + ' ' * max(0, w - _vw(s))


# Kategorie ukryte - komendy zarejestrowane, ale nie listowane w help
_CAT_HIDDEN_KEYS = {"cat_tools"}

def _visible(name: str, cat: str, cat_ecosystem: str, hidden_cats: set) -> bool:
    """Czy komenda ma byc wyswietlona w help."""
    if name in ("help", "?"):
        return False
    if cat in hidden_cats:
        return False
    if cat == cat_ecosystem:
        return name in ECOSYSTEM_MAIN
    return True


def _is_alias(name: str) -> bool:
    return name in ECOSYSTEM_ALIAS


# ---------------------------------------------------------------------------
# Ramki box-drawing
# ---------------------------------------------------------------------------

# Znaki ramki: ╭ ╮ ╰ ╯ ─ │ ├ ┤
_BOX_TL = "╭"
_BOX_TR = "╮"
_BOX_BL = "╰"
_BOX_BR = "╯"
_BOX_H  = "─"
_BOX_V  = "│"
_BOX_ML = "├"
_BOX_MR = "┤"
_BOX_DOT = "·"

_WIDTH = 62   # wewnetrzna szerokosc ramki (bez pionowych krawedzi)

# Dostepna szerokosc dla zawartosci wewnatrz ramki:
# _WIDTH - 2 (lewa spacja + prawa spacja przed │)
_INNER = _WIDTH - 2


def _hline(left: str, right: str, fill: str = _BOX_H) -> str:
    return f"{DIM}{left}{fill * _WIDTH}{right}{RST}"


def _truncate(text: str, max_vis: int) -> str:
    """Przytnie tekst do max_vis widocznych znakow (bez ANSI). Dodaje … jesli obcieto."""
    if _vw(text) <= max_vis:
        return text
    # Zbieramy znaki az do limitu (pomijamy bajty ANSI w liczniku)
    result = []
    visible = 0
    i = 0
    target = max_vis - 1  # miejsce na …
    while i < len(text):
        # Sprawdz czy tu zaczyna sie sekwencja ANSI
        m = _re_ansi.match(text, i)
        if m:
            result.append(m.group())
            i = m.end()
        else:
            if visible < target:
                result.append(text[i])
                visible += 1
            else:
                result.append("…")
                break
            i += 1
    return "".join(result)


def _box_row(inner_content: str) -> None:
    """Wyrenderuj jeden wiersz wewnatrz ramki z dokladnie _WIDTH znakow wewnetrznymi."""
    # inner_content to tekst juz pokolorowany ANSI; upewnij sie ze miesci sie w _INNER
    vis = _vw(inner_content)
    # +2 bo kazdy wiersz ma 2 spacje wiodace przed zawartoscia
    content_vis = vis + 2
    pad = max(0, _WIDTH - content_vis - 2)
    # format: │ + 2sp + zawartosc + padding + spacja + │
    _wln(f"  {DIM}{_BOX_V}{RST}  {inner_content}{' ' * pad}  {DIM}{_BOX_V}{RST}")


def _box_top(label: str, icon: str = "") -> None:
    """Gorny brzeg ramki z tytułem kategorii."""
    prefix = f" {icon} " if icon else " "
    title  = f"{BOLD}{WHT}{prefix}{label}{RST}"
    t_vis  = _vw(title)
    pad_l  = 2
    pad_r  = max(0, _WIDTH - pad_l - t_vis - 2)
    line   = (
        f"{DIM}{_BOX_TL}{_BOX_H * pad_l}{RST}"
        f" {title} "
        f"{DIM}{_BOX_H * pad_r}{_BOX_TR}{RST}"
    )
    _wln(f"  {line}")


def _box_hint(hint: str) -> None:
    """Wiersz podpowiedzi pod naglowkiem."""
    # dostepna szerokosc dla tekstu: _WIDTH - 4 (2 spacje wewn. + 2 spacje marginesu)
    max_desc = _WIDTH - 4
    hint_t   = _truncate(hint, max_desc)
    _box_row(f"{DIM}{hint_t}{RST}")


def _box_sep() -> None:
    """Pozioma linia separujaca wewnatrz ramki (przed aliasami)."""
    _wln(f"  {_hline(_BOX_ML, _BOX_MR)}")


def _box_cmd(cmd: str, desc: str, dim_cmd: bool = False) -> None:
    """Jeden wiersz komendy wewnatrz ramki."""
    cmd_w    = 14          # widoczna szerokosc kolumny nazwy
    sep_w    = 2           # dwie spacje miedzy nazwa a opisem
    # dostepna szerokosc dla opisu: _WIDTH - 2(wiodace) - cmd_w - sep_w - 2(trailing)
    max_desc = _WIDTH - 2 - cmd_w - sep_w - 2
    desc_t   = _truncate(desc, max_desc)
    cmd_col  = f"{DIM if dim_cmd else YLW}{_pad(cmd, cmd_w)}{RST}"
    desc_col = f"{DIM}{desc_t}{RST}"
    _box_row(f"{cmd_col}  {desc_col}")


def _box_alias_cmd(cmd: str, desc: str) -> None:
    """Wiersz aliasu - przygaszone + znacznik ≡ alias."""
    cmd_w    = 14
    tag_vis  = 8           # "≡ alias " = 8 znakow widocznych
    sep_w    = 2
    max_desc = _WIDTH - 2 - cmd_w - sep_w - tag_vis - 2
    desc_t   = _truncate(desc, max_desc)
    tag      = f"{DIM}≡ alias {RST}"
    cmd_col  = f"{DIM}{_pad(cmd, cmd_w)}{RST}"
    desc_col = f"{DIM}{desc_t}{RST}"
    _box_row(f"{cmd_col}  {tag}{desc_col}")


def _box_bottom() -> None:
    """Dolny brzeg ramki."""
    _wln(f"  {_hline(_BOX_BL, _BOX_BR)}")


# ---------------------------------------------------------------------------
# Naglowek calego help
# ---------------------------------------------------------------------------

_TITLE_WIDTH = _WIDTH + 2   # z krawędziami

def _render_header(title: str) -> None:
    """Duzy naglowek help z podwojnymi liniami."""
    _wln()
    top    = f"{DIM}╔{'═' * _TITLE_WIDTH}╗{RST}"
    inner  = f"{DIM}║{RST}{BOLD}{BCYN}{title.center(_TITLE_WIDTH)}{RST}{DIM}║{RST}"
    bot    = f"{DIM}╚{'═' * _TITLE_WIDTH}╝{RST}"
    _wln(f"  {top}")
    _wln(f"  {inner}")
    _wln(f"  {bot}")
    _wln()


# ---------------------------------------------------------------------------
# Stopka
# ---------------------------------------------------------------------------

def _render_footer(total: int, label: str) -> None:
    dot  = f"{DIM}{_BOX_DOT}{RST}"
    msg  = f"  {dot} {DIM}{label}{RST}  {dot}"
    pad  = max(0, _TITLE_WIDTH + 2 - _vw(msg) - 2)
    line = f"{DIM}{'─' * ((_TITLE_WIDTH + 2)  )}{RST}"
    _wln(f"  {line}")
    _wln(f"  {msg}")
    _wln()


# ---------------------------------------------------------------------------
# Ikona kategorii
# ---------------------------------------------------------------------------

_KEY_TO_ICON_KEY = {
    # dopasowanie po fragmencie klucza tlumaczenia lub nazwie kategorii
}

def _cat_icon(cat_key: str) -> str:
    """Zwroc ikone dla kategorii na podstawie klucza (cat_ecosystem, cat_nav ...)."""
    for k, icon in _CAT_ICONS.items():
        if k in cat_key:
            return icon
    return "◇"


def setup(terminal):
    def _t(key, **kw):
        return terminal.t(key, **kw)

    def help_list_command(args):
        # help ai → przekaż do modułu ai (pełna lista komend)
        if args and args[0].lower() == "ai":
            try:
                from . import ai as _ai_mod
                _ai_mod._cmd_ai_menu([], terminal)
            except Exception:
                _wln(_t("help_no_commands"))
            return

        cat_ecosystem = _t("cat_ecosystem")
        cat_nav       = _t("cat_nav")
        cat_general   = _t("cat_general")
        cat_history   = _t("cat_history")
        cat_alias     = _t("cat_alias")
        cat_env       = _t("cat_env")
        cat_net       = _t("cat_net")
        cat_task      = _t("cat_task")
        cat_tools     = _t("cat_tools")

        # Ukryte kategorie (komendy dzialaja, ale nie sa listowane w help)
        hidden_cats = {_t(k) for k in _CAT_HIDDEN_KEYS}

        # Kolejnosc kategorii w output
        _CAT_ORDER = [
            cat_ecosystem,
            cat_nav,
            cat_general,
            cat_history,
            cat_alias,
            cat_env,
            cat_net,
            cat_task,
            cat_tools,
        ]

        # Podpowiedz + klucz ikony dla kazdej kategorii
        _CAT_META = {
            cat_ecosystem: (_t("cat_ecosystem_hint"), "ecosystem"),
            cat_nav:       (_t("cat_nav_hint"),       "nav"),
            cat_general:   (_t("cat_general_hint"),   "general"),
            cat_history:   (_t("cat_history_hint"),   "history"),
            cat_alias:     (_t("cat_alias_hint"),     "alias"),
            cat_env:       (_t("cat_env_hint"),       "env"),
            cat_net:       (_t("cat_net_hint"),       "net"),
            cat_tools:     (_t("cat_tools_hint"),     "tools"),
            cat_task:      (_t("cat_task_hint"),      "task"),
        }

        # Grupowanie: main + aliasy w EcoSystem osobno
        grouped_main:  dict[str, list] = {}
        grouped_alias: dict[str, list] = {}

        for name, info in sorted(terminal.commands.items()):
            cat = info.get("category", cat_general)
            if not _visible(name, cat, cat_ecosystem, hidden_cats):
                continue
            desc = info.get("description", "")
            if cat == cat_ecosystem and _is_alias(name):
                grouped_alias.setdefault(cat, []).append((name, desc))
            else:
                grouped_main.setdefault(cat, []).append((name, desc))

        all_cats = set(grouped_main) | set(grouped_alias)
        if not all_cats:
            _wln(_t("help_no_commands"))
            return

        _render_header(_t("help_title"))

        ordered  = [c for c in _CAT_ORDER if c in all_cats]
        ordered += sorted(c for c in all_cats if c not in _CAT_ORDER)

        total = 0
        for cat in ordered:
            hint, icon_key = _CAT_META.get(cat, ("", "general"))
            icon = _CAT_ICONS.get(icon_key, "◇")

            _box_top(cat.upper(), icon)
            if hint:
                _box_hint(hint)

            # glowne komendy
            for cmd, desc in grouped_main.get(cat, []):
                _box_cmd(cmd, desc)
                total += 1

            # aliasy w tej samej kategorii
            aliases = grouped_alias.get(cat, [])
            if aliases:
                _box_sep()
                for cmd, desc in aliases:
                    _box_alias_cmd(cmd, desc)
                    total += 1

            _box_bottom()
            _wln()

        _render_footer(total, _t("help_total", n=total))

    terminal.register_command(
        "help", help_list_command,
        description=_t("cmd_help"),
        category=_t("cat_general"),
    )
    terminal.register_command(
        "?", help_list_command,
        description=_t("cmd_help"),
        category=_t("cat_general"),
    )


def teardown(terminal):
    terminal.commands.pop("help", None)
    terminal.commands.pop("?",    None)
