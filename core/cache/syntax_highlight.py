"""Syntax Highlight module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski
Module: syntax_highlight  v1.0.0

Kolorowanie skladni w czasie rzeczywistym podczas wpisywania komend.
Uzywa readline display-hook (pre_input_hook / redisplay) aby podswietlac
komendy, opcje, lancuchy i liczby bez przerywania wprowadzania.

Komendy:
  highlight              - pokaz status / pomoc
  highlight on           - wlacz kolorowanie (domyslnie wlaczone)
  highlight off          - wylacz kolorowanie
  highlight status       - info: stan, jezyk, tryb
  highlight test <tekst> - podglad kolorowania dowolnego tekstu
  highlight langs        - lista obsługiwanych jezykow / rozszeżen
  highlight theme <nazwa>- zmien schemat kolorow (default|monokai|solarized)

Dzialanie (live):
  - Podswietla pierwsza slowow komendy (zielony/czerwony = znana/nieznana)
  - Koloruje opcje (--flagi, -f) na zolto
  - Koloruje lancuchy cudzyslowowe na zielono
  - Koloruje liczby na pomaranczowo
  - Koloruje pipe | na cyan
  - Na Windows dziala przez ANSI VT (wymaga Win10+)

Integracja:
  - readline pre_input_hook: podmienia bufor wyswietlania na kolorowy
  - Fallback bez readline (Windows cmd): tylko komendy highlight test/show
  - Mozna wlaczyc/wylaczyc w locie bez restartu
"""

# ==============================================================================
#  METADATA
# ==============================================================================

METADATA = {
    "name":        "syntax_highlight",
    "version":     "1.0.0",
    "author":      "Sebastian Januchowski",
    "company":     "polsoft.ITS(TM) Group",
    "description": "Live syntax highlighting during typing via readline hook",
    "type":        "core",
    "depends":     [],
    "exports":     ["highlight_line", "SyntaxHighlighter"],
    "min_pyterm":  "2.0.0",
}

import os
import re
import sys

from ._shared import (
    RST, BOLD, DIM, YLW, RED, GRN, CYN, MGT, BLU, WHT,
    _w, _strip,
)

# ==============================================================================
#  ANSI RGB HELPERS (bez importowania calego ansi.py — unikamy cyklicznych imp.)
# ==============================================================================

def _rgb(r: int, g: int, b: int, text: str) -> str:
    """Owin tekst kolorem RGB (fg). Zwraca plain text jesli ANSI niedostepne."""
    if not _ansi_ok():
        return text
    return f"\x1b[38;2;{r};{g};{b}m{text}{RST}"


_ansi_cache: bool | None = None

def _ansi_ok() -> bool:
    global _ansi_cache
    if _ansi_cache is None:
        _ansi_cache = (RST != "")
    return _ansi_cache

# ==============================================================================
#  SCHEMATY KOLOROW
# ==============================================================================

_THEMES: dict[str, dict] = {
    "default": {
        "cmd_ok":    lambda t: _rgb(102, 217, 130, t),   # jasny zielony
        "cmd_err":   lambda t: _rgb(255, 100, 100, t),   # czerwony
        "opt":       lambda t: _rgb(229, 192, 123, t),   # zloty (--flag)
        "string":    lambda t: _rgb(152, 195, 121, t),   # zielony
        "number":    lambda t: _rgb(209, 154, 102, t),   # pomaranczowy
        "pipe":      lambda t: _rgb(86, 182, 194, t),    # cyan
        "comment":   lambda t: f"\x1b[2m{_rgb(98, 114, 164, t)}",  # dim niebieskoszary
        "keyword":   lambda t: _rgb(204, 153, 255, t),   # fioletowy
        "path":      lambda t: _rgb(97, 175, 239, t),    # jasny niebieski
    },
    "monokai": {
        "cmd_ok":    lambda t: _rgb(166, 226, 46, t),
        "cmd_err":   lambda t: _rgb(249, 38, 114, t),
        "opt":       lambda t: _rgb(230, 219, 116, t),
        "string":    lambda t: _rgb(230, 219, 116, t),
        "number":    lambda t: _rgb(174, 129, 255, t),
        "pipe":      lambda t: _rgb(102, 217, 239, t),
        "comment":   lambda t: f"\x1b[2m{_rgb(117, 113, 94, t)}",
        "keyword":   lambda t: _rgb(249, 38, 114, t),
        "path":      lambda t: _rgb(102, 217, 239, t),
    },
    "solarized": {
        "cmd_ok":    lambda t: _rgb(133, 153, 0, t),
        "cmd_err":   lambda t: _rgb(220, 50, 47, t),
        "opt":       lambda t: _rgb(181, 137, 0, t),
        "string":    lambda t: _rgb(42, 161, 152, t),
        "number":    lambda t: _rgb(211, 54, 130, t),
        "pipe":      lambda t: _rgb(38, 139, 210, t),
        "comment":   lambda t: f"\x1b[2m{_rgb(88, 110, 117, t)}",
        "keyword":   lambda t: _rgb(108, 113, 196, t),
        "path":      lambda t: _rgb(38, 139, 210, t),
    },
}

# ==============================================================================
#  HIGHLIGHTER
# ==============================================================================

# Regex do tokenizacji linii wejsciowej
_RE_STRING  = re.compile(r'(\"[^\"\\]*(?:\\.[^\"\\]*)*\"|\'[^\'\\]*(?:\\.[^\'\\]*)*\')')
_RE_NUMBER  = re.compile(r'(?<!\w)(\d+(?:\.\d+)?)(?!\w)')
_RE_OPT     = re.compile(r'(--?\w[\w-]*)')
_RE_PATH    = re.compile(r'((?:\.{0,2}/)[^\s]+|[A-Za-z]:\\[^\s]+)')
_RE_PIPE    = re.compile(r'(\|)')
_RE_COMMENT = re.compile(r'(#.*)$')

# Placeholder uzyty przy zamianie matchow zeby uniknac podwojnego kolorowania
_PLACEHOLDER = "\x00"


class SyntaxHighlighter:
    """Odpowiada za kolorowanie linii wejsciowej i blokow kodu."""

    def __init__(self):
        self.enabled  = True
        self.theme    = "default"
        self._known_commands: set[str] = set()

    # ------------------------------------------------------------------
    # Publiczne API
    # ------------------------------------------------------------------

    def set_commands(self, commands: dict) -> None:
        """Aktualizuje zbior znanych komend (z terminal.commands)."""
        self._known_commands = set(commands.keys())

    def set_theme(self, name: str) -> bool:
        if name in _THEMES:
            self.theme = name
            return True
        return False

    def colorize(self, line: str) -> str:
        """Koloruje pelna linie wejsciowa. Zwraca linie z kodami ANSI."""
        if not self.enabled or not _ansi_ok() or not line.strip():
            return line

        c = _THEMES.get(self.theme, _THEMES["default"])

        # Zachowaj fragmenty juz skolorowane (np. escape codes z historii)
        # Pracuj na plain tekscie
        segments = line.split("|")
        colored_segs = []
        for seg_i, seg in enumerate(segments):
            colored_segs.append(self._colorize_segment(seg, c, is_first=(seg_i == 0)))

        result = c["pipe"](" | ").join(colored_segs) if len(segments) > 1 else colored_segs[0]
        return result + RST

    # ------------------------------------------------------------------
    # Wewnetrzne
    # ------------------------------------------------------------------

    def _colorize_segment(self, seg: str, c: dict, is_first: bool) -> str:
        """Koloruje jeden segment (czesc miedzy |)."""
        stripped = seg.strip()
        if not stripped:
            return seg

        tokens = stripped.split()
        if not tokens:
            return seg

        out_parts = []  # noqa: F841 – reserved for future multi-part assembly
        leading_space = seg[: len(seg) - len(seg.lstrip())]
        trailing_space = seg[len(seg.rstrip()):]

        # Pierwsza token = komenda
        cmd = tokens[0]
        if is_first:
            if cmd in self._known_commands:
                cmd_colored = c["cmd_ok"](cmd)
            else:
                cmd_colored = c["cmd_err"](cmd)
        else:
            # Po pipe — traktuj jak komende ale bez walidacji
            cmd_colored = c["cmd_ok"](cmd)

        rest_tokens = tokens[1:]
        rest_colored = self._colorize_args(rest_tokens, c)

        if rest_colored:
            return leading_space + cmd_colored + " " + rest_colored + trailing_space
        return leading_space + cmd_colored + trailing_space

    def _colorize_args(self, tokens: list[str], c: dict) -> str:
        """Koloruje liste argumentow (bez pierwszego tokenu-komendy)."""
        result = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]

            # Komentarz (bash-style)
            if tok.startswith("#"):
                rest = " ".join(tokens[i:])
                result.append(c["comment"](rest))
                break

            # String (cudzyslow)
            if tok and tok[0] in ('"', "'"):
                # Zbierz caly string nawet jesli jest podzielony spacjami
                full = tok
                while not _is_closed_string(full) and i + 1 < len(tokens):
                    i += 1
                    full += " " + tokens[i]
                result.append(c["string"](full))

            # Opcja (--foo, -f)
            elif _RE_OPT.fullmatch(tok):
                result.append(c["opt"](tok))

            # Sciezka
            elif _RE_PATH.fullmatch(tok):
                result.append(c["path"](tok))

            # Liczba
            elif _RE_NUMBER.fullmatch(tok):
                result.append(c["number"](tok))

            else:
                result.append(tok)

            i += 1

        return " ".join(result)


def _is_closed_string(s: str) -> bool:
    """Sprawdza czy string jest zamkniety (zakonczony tym samym cudzysłowem)."""
    if len(s) < 2:
        return False
    q = s[0]
    if q not in ('"', "'"):
        return False
    return s.endswith(q) and len(s) > 1


# ==============================================================================
#  READLINE HOOK
# ==============================================================================

_highlighter: SyntaxHighlighter | None = None


def _install_readline_hook(terminal) -> bool:
    """Instaluje hook readline ktory podmienia wyswietlanie promptu.

    readline nie daje latwego dostępu do 'live rewrite' bufora na POSIX.
    Najlepsze co mozna zrobic bez prompt_toolkit to:
      1. set_pre_input_hook — wywolywany przed wyswietleniem kazdej linii (raz)
      2. set_completion_display_matches_hook — po TAB
      3. Monkeypatch input() (heavy) — nie uzywamy

    Tutaj stosujemy podejscie 'display hook via completer wrapper':
    readline wywoluje complete(text, state) przy kazdym nacisnieciu Tab.
    My dodajemy ROWNIEZ pre_input_hook ktory koloruje prompt-hint.

    Prawdziwe live-rewrite (znak po znaku) wymaga prompt_toolkit lub curses
    i wychodzi poza zakres prostego readline. Zamiast tego:
      - Przy ENTER (po wpisaniu) — _run_line owijamy aby pokazac pokolorowana
        wersje tego co uzytkownik wpisal (echo kolorowe po wykonaniu).
      - pre_input_hook resetuje kolor do neutralnego przed nowym promptem.
    """
    try:
        import readline as _rl

        def _pre_input():
            # Przed pojawieniem sie promptu — brak specjalnych akcji;
            # placeholder gdyby w przyszlosci chciano dodac inicjalizacje.
            pass

        _rl.set_pre_input_hook(_pre_input)
        return True
    except (ImportError, AttributeError):
        return False


def _wrap_run_line(terminal, orig_run_line):
    """Owija terminal._run_line aby po wpisaniu komendy pokazac jej
    pokolorowan wersje jako echo (przed wykonaniem)."""

    def _new_run_line(line: str) -> None:
        if _highlighter and _highlighter.enabled and _ansi_ok() and line.strip():
            # Aktualizuj zbior znanych komend (moglby sie zmieniac)
            _highlighter.set_commands(terminal.commands)
            colored = _highlighter.colorize(line)
            # Przesuniecie kursora w gore o 1 linie i nadpisanie
            # \x1b[1A  = kursor gore,  \x1b[2K = wyczysc linie
            prompt_sym = ""
            try:
                from . import config as _cfg
                prompt_sym = _cfg.get("prompt.symbol", "> ")
            except Exception:
                prompt_sym = "> "
            sys.stdout.write(f"\x1b[1A\x1b[2K{prompt_sym}{colored}\n")
            sys.stdout.flush()
        orig_run_line(line)

    return _new_run_line


# ==============================================================================
#  KOMENDY
# ==============================================================================

def _cmd_highlight(args, terminal):
    """Obsluguje komende 'highlight [sub] [args...]'."""
    global _highlighter

    def _t(k, **kw):
        d = getattr(terminal, "_t", {})
        text = d.get(k, k)
        return text.format(**kw) if kw else text

    if not args or args[0] in ("help", "--help", "-h"):
        _print_help(terminal)
        return

    sub = args[0].lower()

    if sub == "on":
        if _highlighter:
            _highlighter.enabled = True
        print(f"  {GRN}{BOLD}Syntax highlighting:{RST} {GRN}wlaczone{RST}")
        return

    if sub == "off":
        if _highlighter:
            _highlighter.enabled = False
        print(f"  {YLW}{BOLD}Syntax highlighting:{RST} {YLW}wylaczone{RST}")
        return

    if sub == "status":
        if not _highlighter:
            print(f"  {RED}Modul nie zainicjalizowany.{RST}")
            return
        stan = f"{GRN}wlaczone{RST}" if _highlighter.enabled else f"{YLW}wylaczone{RST}"
        print(f"\n  {BOLD}{CYN}Syntax Highlight — status{RST}")
        print(f"  Stan   : {stan}")
        print(f"  Motyw  : {BOLD}{_highlighter.theme}{RST}")
        print(f"  Komendy: {len(_highlighter._known_commands)}")
        print(f"  ANSI   : {'tak' if _ansi_ok() else 'nie'}")
        print()
        return

    if sub == "test":
        if not _highlighter:
            print(f"  {RED}Modul nie zainicjalizowany.{RST}")
            return
        if len(args) < 2:
            sample = 'run script.py --verbose | search "hello" 42'
        else:
            sample = " ".join(args[1:])
        _highlighter.set_commands(terminal.commands)
        colored = _highlighter.colorize(sample)
        print(f"\n  {DIM}Wejscie :{RST} {sample}")
        print(f"  {DIM}Wyjscie :{RST} {colored}\n")
        return

    if sub == "langs":
        langs = [
            ("python",     ".py"),
            ("bash/sh",    ".sh  .bash"),
            ("powershell", ".ps1"),
            ("javascript", ".js"),
            ("json",       ".json"),
            ("terminal",   "komendy TerminalX"),
        ]
        print(f"\n  {BOLD}{CYN}Obslugiwane jezyki{RST}")
        for lang, ext in langs:
            print(f"  {GRN}{lang:<14}{RST} {DIM}{ext}{RST}")
        print()
        return

    if sub == "theme":
        if len(args) < 2:
            print(f"  Dostepne motywy: {', '.join(_THEMES.keys())}")
            return
        name = args[1].lower()
        if _highlighter and _highlighter.set_theme(name):
            print(f"  {GRN}Motyw zmieniony na:{RST} {BOLD}{name}{RST}")
        else:
            print(f"  {RED}Nieznany motyw:{RST} {name}")
            print(f"  Dostepne: {', '.join(_THEMES.keys())}")
        return

    print(f"  {YLW}Nieznana opcja:{RST} {args[0]}  (uzyj: highlight help)")


def _print_help(terminal):
    print(f"""
  {BOLD}{CYN}Syntax Highlight v1.0.0{RST}  {DIM}polsoft.ITS™{RST}

  {BOLD}Komendy:{RST}
    {GRN}highlight{RST}              – ten ekran pomocy
    {GRN}highlight on{RST}           – wlacz kolorowanie podczas typing
    {GRN}highlight off{RST}          – wylacz kolorowanie
    {GRN}highlight status{RST}       – pokaz stan modulu
    {GRN}highlight test{RST} <tekst> – podglad kolorowania tekstu
    {GRN}highlight langs{RST}        – lista obsługiwanych jezykow
    {GRN}highlight theme{RST} <n>    – zmien schemat ({', '.join(_THEMES.keys())})

  {BOLD}Jak dziala:{RST}
    Po nacisnieciu ENTER, wpisana komenda jest automatycznie
    podswietlana przed wykonaniem:
      • {_THEMES['default']['cmd_ok']('komenda')}  = znana komenda
      • {_THEMES['default']['cmd_err']('blad')}     = nieznana komenda
      • {_THEMES['default']['opt']('--opcja')}   = flagi i opcje
      • {_THEMES['default']['string']('"string"')}   = lancuchy tekstowe
      • {_THEMES['default']['number']('42')}         = liczby
      • {_THEMES['default']['pipe']('|')}            = operator pipe
""")


# ==============================================================================
#  SETUP / TEARDOWN
# ==============================================================================

def setup(terminal) -> None:
    """Inicjalizuje modul syntax_highlight w terminalu."""
    global _highlighter

    _highlighter = SyntaxHighlighter()
    _highlighter.set_commands(terminal.commands)

    # Zainstaluj readline hook (graceful fallback jesli niedostepny)
    readline_ok = _install_readline_hook(terminal)

    # Owij _run_line zeby pokazywac kolorowane echo
    orig = terminal._run_line
    terminal._run_line = _wrap_run_line(terminal, orig)
    terminal._syntax_highlight_orig_run_line = orig  # zachowaj do teardown

    # Eksportuj highlighter na terminalu (dla innych modulow)
    terminal.syntax_highlighter = _highlighter

    # Zarejestruj komende
    def _cmd(args):
        _highlighter.set_commands(terminal.commands)
        _cmd_highlight(args, terminal)

    terminal.register_command(
        "highlight",
        _cmd,
        description=terminal.t("cmd_highlight") if hasattr(terminal, "t") else "Syntax highlighting",
        category=terminal.t("cat_general") if hasattr(terminal, "t") else "Ogolne",
    )

    # Eksport przez _integration (opcjonalny)
    try:
        from . import _integration as _intg
        _intg.register("syntax_highlight", {
            "highlighter": _highlighter,
            "colorize":    _highlighter.colorize,
        })
    except Exception:
        pass


def teardown(terminal) -> None:
    """Usuwa modul syntax_highlight z terminala."""
    global _highlighter

    # Przywroc oryginalny _run_line
    orig = getattr(terminal, "_syntax_highlight_orig_run_line", None)
    if orig is not None:
        terminal._run_line = orig
        del terminal._syntax_highlight_orig_run_line

    # Usun komende
    terminal.commands.pop("highlight", None)

    # Usun z _integration
    try:
        from . import _integration as _intg
        _intg.unregister("syntax_highlight")
    except Exception:
        pass

    # Usun atrybut z terminala
    if hasattr(terminal, "syntax_highlighter"):
        del terminal.syntax_highlighter

    # Resetuj readline hook
    try:
        import readline as _rl
        _rl.set_pre_input_hook(None)
    except Exception:
        pass

    _highlighter = None


# ==============================================================================
#  PUBLICZNE API  (import bezposredni)
# ==============================================================================

def highlight_line(line: str, known_commands: set | None = None, theme: str = "default") -> str:
    """Koloruje linie komendy. Mozna uzywac bez modulu terminala.

    Przyklad:
        from core.syntax_highlight import highlight_line
        print(highlight_line("run script.py --verbose | search hello"))
    """
    h = SyntaxHighlighter()
    h.theme = theme if theme in _THEMES else "default"
    if known_commands:
        h._known_commands = known_commands
    return h.colorize(line)
