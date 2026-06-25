#!/usr/bin/env python3
# =============================================================================
#  TerminalX core - Modul: ansi
#  Wersja: 1.3.0  |  polsoft.ITS(TM) Group
#
#  Pelna obsluga ANSI: kolory, style, kursor, czyszczenie, ramki, paski,
#  gradienty, hyperlinki, markup skladniowy, sparklines, zawijanie tekstu,
#  drzewo, kolumny, blok kodu, diff, log_line, powiadomienia, tabela flex.
#  Zero zewnetrznych zaleznosci. Graceful fallback bez ANSI.
# =============================================================================

import os
import re
import sys
import math
import time
import platform
import shutil
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

# =============================================================================
# WYKRYWANIE WSPARCIA ANSI
# =============================================================================

def _detect_ansi_support() -> bool:
    """Sprawdza czy terminal obsluguje sekwencje ANSI."""
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle   = kernel32.GetStdHandle(-11)
            mode     = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _detect_truecolor() -> bool:
    """Zwraca True jesli terminal wspiera True Color (24-bit RGB)."""
    ct = os.environ.get("COLORTERM", "").lower()
    if ct in ("truecolor", "24bit"):
        return True
    term = os.environ.get("TERM", "").lower()
    return "256color" not in term and _detect_ansi_support()


_ANSI_SUPPORTED: bool = _detect_ansi_support()
_TRUECOLOR:      bool = _detect_truecolor()


def is_supported()  -> bool: return _ANSI_SUPPORTED
def is_truecolor()  -> bool: return _TRUECOLOR

def force_enable(value: bool = True) -> None:
    global _ANSI_SUPPORTED
    _ANSI_SUPPORTED = value

def force_truecolor(value: bool = True) -> None:
    global _TRUECOLOR
    _TRUECOLOR = value

# =============================================================================
# SEKWENCJE PODSTAWOWE
# =============================================================================

ESC = "\033"
CSI = ESC + "["
OSC = ESC + "]"
ST  = ESC + "\\"          # String Terminator

def _seq(*parts) -> str:
    if not _ANSI_SUPPORTED:
        return ""
    return CSI + ";".join(str(p) for p in parts)

def reset()     -> str: return _seq("0m")
def bold()      -> str: return _seq("1m")
def dim()       -> str: return _seq("2m")
def italic()    -> str: return _seq("3m")
def underline() -> str: return _seq("4m")
def blink()     -> str: return _seq("5m")
def reverse()   -> str: return _seq("7m")
def strike()    -> str: return _seq("9m")
def overline()  -> str: return _seq("53m")

# =============================================================================
# KOLORY STANDARDOWE (16 kolorow)
# =============================================================================

class _ColorCode:
    """Deskryptor koloru — fg / bg / bright_fg / bright_bg."""
    __slots__ = ("fg", "bg", "bright_fg", "bright_bg", "name")

    def __init__(self, name: str, fg: int, bg: int, bfg: int, bbg: int):
        self.name      = name
        self.fg        = fg
        self.bg        = bg
        self.bright_fg = bfg
        self.bright_bg = bbg

    def __call__(self, text: str, *, bright: bool = False, bg: bool = False) -> str:
        code = (self.bright_fg if bright else self.fg) if not bg else \
               (self.bright_bg if bright else self.bg)
        return f"{_seq(f'{code}m')}{text}{reset()}"

    def __str__(self) -> str:
        return _seq(f"{self.fg}m")

BLACK   = _ColorCode("black",   30, 40, 90, 100)
RED     = _ColorCode("red",     31, 41, 91, 101)
GREEN   = _ColorCode("green",   32, 42, 92, 102)
YELLOW  = _ColorCode("yellow",  33, 43, 93, 103)
BLUE    = _ColorCode("blue",    34, 44, 94, 104)
MAGENTA = _ColorCode("magenta", 35, 45, 95, 105)
CYAN    = _ColorCode("cyan",    36, 46, 96, 106)
WHITE   = _ColorCode("white",   37, 47, 97, 107)

def black(t):   return BLACK(t)
def red(t):     return RED(t)
def green(t):   return GREEN(t)
def yellow(t):  return YELLOW(t)
def blue(t):    return BLUE(t)
def magenta(t): return MAGENTA(t)
def cyan(t):    return CYAN(t)
def white(t):   return WHITE(t)

def bright_red(t):     return RED(t,     bright=True)
def bright_green(t):   return GREEN(t,   bright=True)
def bright_yellow(t):  return YELLOW(t,  bright=True)
def bright_blue(t):    return BLUE(t,    bright=True)
def bright_cyan(t):    return CYAN(t,    bright=True)
def bright_white(t):   return WHITE(t,   bright=True)
def bright_magenta(t): return MAGENTA(t, bright=True)

# =============================================================================
# KOLORY 256
# =============================================================================

def fg256(n: int, text: str) -> str:
    if not _ANSI_SUPPORTED: return text
    return f"\033[38;5;{n}m{text}{reset()}"

def bg256(n: int, text: str) -> str:
    if not _ANSI_SUPPORTED: return text
    return f"\033[48;5;{n}m{text}{reset()}"

# =============================================================================
# KOLORY TRUE COLOR (RGB)
# =============================================================================

def fg_rgb(r: int, g: int, b: int, text: str) -> str:
    if not _ANSI_SUPPORTED: return text
    return f"\033[38;2;{r};{g};{b}m{text}{reset()}"

def bg_rgb(r: int, g: int, b: int, text: str) -> str:
    if not _ANSI_SUPPORTED: return text
    return f"\033[48;2;{r};{g};{b}m{text}{reset()}"

def hex_color(hex_str: str, text: str, *, bg: bool = False) -> str:
    """Kolor z kodu HEX (#RRGGBB lub RRGGBB)."""
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return bg_rgb(r, g, b, text) if bg else fg_rgb(r, g, b, text)

# =============================================================================
# GRADIENT RGB
# =============================================================================

def _lerp_color(
    c1: Tuple[int,int,int],
    c2: Tuple[int,int,int],
    t:  float,
) -> Tuple[int,int,int]:
    """Interpoluje liniowo dwa kolory RGB. t w [0,1]."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def gradient(
    text:  str,
    start: Tuple[int,int,int],
    end:   Tuple[int,int,int],
    *,
    bg:    bool = False,
) -> str:
    """
    Koloruje kazdy znak tekstu gradientem od start do end (RGB).
    Przyklad:
        print(gradient("Hello!", (255,0,100), (0,180,255)))
    """
    if not _ANSI_SUPPORTED or not text:
        return text
    n   = max(1, len(text) - 1)
    out = []
    for i, ch in enumerate(text):
        t       = i / n if n else 0.0
        r, g, b = _lerp_color(start, end, t)
        esc     = f"\033[48;2;{r};{g};{b}m" if bg else f"\033[38;2;{r};{g};{b}m"
        out.append(f"{esc}{ch}")
    return "".join(out) + reset()


def gradient_multicolor(
    text:  str,
    stops: List[Tuple[int,int,int]],
    *,
    bg:    bool = False,
) -> str:
    """
    Gradient przez wiele kolorow (stops >= 2).
    Przyklad:
        stops = [(255,0,0),(255,255,0),(0,255,0)]
        print(gradient_multicolor("Rainbow!", stops))
    """
    if not _ANSI_SUPPORTED or not text or len(stops) < 2:
        c1 = stops[0]  if stops        else (255,255,255)
        c2 = stops[-1] if len(stops)>1 else (0,0,0)
        return gradient(text, c1, c2, bg=bg)
    n_chars = len(text)
    n_segs  = len(stops) - 1
    out     = []
    for i, ch in enumerate(text):
        pos     = (i / max(1, n_chars - 1)) * n_segs
        seg_idx = min(int(pos), n_segs - 1)
        local_t = pos - seg_idx
        r, g, b = _lerp_color(stops[seg_idx], stops[seg_idx + 1], local_t)
        esc     = f"\033[48;2;{r};{g};{b}m" if bg else f"\033[38;2;{r};{g};{b}m"
        out.append(f"{esc}{ch}")
    return "".join(out) + reset()

# =============================================================================
# HYPERLINK (OSC 8)
# =============================================================================

def hyperlink(url: str, text: str) -> str:
    """
    Klikalny hiperlink OSC 8 (iTunes2, Windows Terminal, GNOME Terminal...).
    W niezgodnych terminalach wyswietla sam tekst.
    Przyklad: print(hyperlink("https://example.com", "kliknij tutaj"))
    """
    if not _ANSI_SUPPORTED:
        return text
    return f"{OSC}8;;{url}{ST}{text}{OSC}8;;{ST}"

# =============================================================================
# MARKUP SKLADNIOWY  paint()
# =============================================================================

_PAINT_TAGS: dict = {}
_PAINT_TAGS_BUILT = False


def _build_paint_tags() -> dict:
    """Buduje slownik tagow markup dla paint()."""
    t = {}
    # styl
    style_map = {
        "bold":      lambda x: f"{_seq('1m')}{x}{reset()}",
        "dim":       lambda x: f"{_seq('2m')}{x}{reset()}",
        "italic":    lambda x: f"{_seq('3m')}{x}{reset()}",
        "underline": lambda x: f"{_seq('4m')}{x}{reset()}",
        "strike":    lambda x: f"{_seq('9m')}{x}{reset()}",
        "reverse":   lambda x: f"{_seq('7m')}{x}{reset()}",
        "blink":     lambda x: f"{_seq('5m')}{x}{reset()}",
        "overline":  lambda x: f"{_seq('53m')}{x}{reset()}",
    }
    style_map["b"] = style_map["bold"]
    style_map["i"] = style_map["italic"]
    style_map["u"] = style_map["underline"]
    style_map["s"] = style_map["strike"]
    t.update(style_map)

    # kolory 16
    for _name, _obj in [
        ("black",BLACK),("red",RED),("green",GREEN),("yellow",YELLOW),
        ("blue",BLUE),("magenta",MAGENTA),("cyan",CYAN),("white",WHITE),
    ]:
        t[_name]             = (lambda o: lambda x: o(x))(_obj)
        t[f"bright_{_name}"] = (lambda o: lambda x: o(x, bright=True))(_obj)
        t[f"bg_{_name}"]     = (lambda o: lambda x: o(x, bg=True))(_obj)

    # motyw
    for _role in ("primary","secondary","success","warning","error","muted","accent"):
        t[_role] = (lambda r: lambda x: _theme.apply(r, x))(_role)
    return t


def paint(markup: str) -> str:
    r"""
    Przetwarza markup skladniowy: [tag]tekst[/tag] lub [tag]tekst[/].
    Tagi moga byc zagniezdzane. Obsluguje rowniez tagi inline:
      [rgb:R,G,B]tekst[/]    — kolor True Color
      [hex:#RRGGBB]tekst[/]  — kolor HEX

    Dostepne tagi:
      Styl:   bold/b, dim, italic/i, underline/u, strike/s, reverse, blink, overline
      Kolory: red, green, yellow, blue, magenta, cyan, white, black
              bright_red ... bg_red ...
      Motyw:  primary, secondary, success, warning, error, muted, accent
      Inline: rgb:R,G,B   hex:#RRGGBB

    Przyklad:
        print(paint("[bold][red]Blad:[/] cos poszlo nie tak[/bold]"))
        print(paint("[rgb:0,200,255]kolor RGB[/] | [hex:#ff6600]HEX[/]"))
    """
    global _PAINT_TAGS_BUILT, _PAINT_TAGS
    if not _PAINT_TAGS_BUILT:
        _PAINT_TAGS = _build_paint_tags()
        _PAINT_TAGS_BUILT = True

    if not _ANSI_SUPPORTED:
        return re.sub(r"\[/?[^\]]+\]", "", markup)

    result  = []
    stack   = []
    buf     = []
    pattern = re.compile(r"\[(/?)([a-zA-Z_0-9:#,]*)\]")
    last    = 0

    def flush_buf():
        if buf:
            result.append("".join(buf))
            buf.clear()

    def _resolve_tag(tag_name: str, content: str) -> str:
        """Przetwarza tag z opcjonalnymi parametrami (rgb:, hex:)."""
        tl = tag_name.lower()
        if tl.startswith("rgb:"):
            try:
                r, g, b = (int(x) for x in tl[4:].split(","))
                return fg_rgb(r, g, b, content)
            except Exception:
                return content
        if tl.startswith("hex:"):
            try:
                return hex_color(tl[4:], content)
            except Exception:
                return content
        fn = _PAINT_TAGS.get(tl)
        return fn(content) if fn else content

    for m in pattern.finditer(markup):
        buf.append(markup[last:m.start()])
        last = m.end()
        closing, tag = m.group(1), m.group(2)

        if closing:
            flush_buf()
            tl = tag.lower()
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0].lower() == tl or tl == "":
                    inner_tag, inner_start = stack.pop(k)
                    inner_content = "".join(result[inner_start:])
                    del result[inner_start:]
                    result.append(_resolve_tag(inner_tag, inner_content))
                    break
        else:
            flush_buf()
            tl = tag.lower()
            known = (tl in _PAINT_TAGS or tl.startswith("rgb:") or tl.startswith("hex:"))
            if known:
                stack.append((tag, len(result)))
            else:
                result.append(f"[{tag}]")

    buf.append(markup[last:])
    flush_buf()
    for tag, start in reversed(stack):
        inner = "".join(result[start:])
        del result[start:]
        result.append(_resolve_tag(tag, inner))
    return "".join(result)

# =============================================================================
# PALETA WLASNA — MOTYW
# =============================================================================

class Theme:
    """Motyw kolorystyczny terminala."""

    def __init__(self,
        primary    = (0,   200, 255),
        secondary  = (180, 100, 255),
        success    = (80,  220, 100),
        warning    = (255, 200, 0  ),
        error      = (255, 70,  70 ),
        muted      = (120, 120, 140),
        accent     = (255, 140, 0  ),
        border     = (60,  60,  80 ),
    ):
        self.primary   = primary
        self.secondary = secondary
        self.success   = success
        self.warning   = warning
        self.error     = error
        self.muted     = muted
        self.accent    = accent
        self.border    = border

    def apply(self, role: str, text: str) -> str:
        color = getattr(self, role, self.muted)
        return fg_rgb(*color, text)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("primary","secondary","success","warning","error","muted","accent","border")}


_theme = Theme()

def get_theme() -> Theme: return _theme

def set_theme(theme: Theme) -> None:
    global _theme, _PAINT_TAGS_BUILT
    _theme = theme
    _PAINT_TAGS_BUILT = False

def t(role: str, text: str) -> str: return _theme.apply(role, text)

def primary(text):   return _theme.apply("primary",   text)
def secondary(text): return _theme.apply("secondary", text)
def success(text):   return _theme.apply("success",   text)
def warning(text):   return _theme.apply("warning",   text)
def error(text):     return _theme.apply("error",     text)
def muted(text):     return _theme.apply("muted",     text)
def accent(text):    return _theme.apply("accent",    text)

# =============================================================================
# FORMATOWANIE TEKSTU
# =============================================================================

def style(text: str, *styles) -> str:
    if not _ANSI_SUPPORTED: return text
    prefix = "".join(str(s) for s in styles)
    return f"{prefix}{text}{reset()}"

def bold_text(text: str)      -> str: return f"{_seq('1m')}{text}{reset()}"
def dim_text(text: str)       -> str: return f"{_seq('2m')}{text}{reset()}"
def italic_text(text: str)    -> str: return f"{_seq('3m')}{text}{reset()}"
def underline_text(text: str) -> str: return f"{_seq('4m')}{text}{reset()}"
def strike_text(text: str)    -> str: return f"{_seq('9m')}{text}{reset()}"
def invert_text(text: str)    -> str: return f"{_seq('7m')}{text}{reset()}"
def overline_text(text: str)  -> str: return f"{_seq('53m')}{text}{reset()}"

def strip_ansi(text: str) -> str:
    """Usuwa wszystkie sekwencje ANSI z tekstu."""
    return re.sub(r"\033\[[0-9;]*[a-zA-Z]|\033][^\033]*(?:\033\\|\007)", "", text)

def visual_len(text: str) -> int:
    """Zwraca widzialna dlugosc tekstu (bez sekwencji ANSI)."""
    return len(strip_ansi(text))

def pad(text: str, width: int, align: str = "left", fill: str = " ") -> str:
    """
    Wyrownuje tekst do podanej szerokosci, uwzgledniajac sekwencje ANSI.
    align: 'left' | 'right' | 'center'
    """
    vlen      = visual_len(text)
    pad_total = max(0, width - vlen)
    if align == "right":
        return fill * pad_total + text
    elif align == "center":
        left  = pad_total // 2
        right = pad_total - left
        return fill * left + text + fill * right
    return text + fill * pad_total


def wrap(text: str, width: int = 0, indent: str = "") -> str:
    """
    Zawija tekst do podanej szerokosci z uwzglednieniem sekwencji ANSI.
    width=0 = szerokosc terminala.
    indent  = wciec kolejnych linii.
    """
    if not width:
        width = shutil.get_terminal_size((80, 24)).columns
    lines_out = []
    for raw_line in text.splitlines():
        words  = raw_line.split(" ")
        line   = ""
        vlen_l = 0
        for word in words:
            vlen_w = visual_len(word)
            if not line:
                line   = word
                vlen_l = vlen_w
            elif vlen_l + 1 + vlen_w <= width:
                line   += " " + word
                vlen_l += 1 + vlen_w
            else:
                lines_out.append(line)
                line   = indent + word
                vlen_l = visual_len(indent) + vlen_w
        lines_out.append(line)
    return "\n".join(lines_out)

# =============================================================================
# KURSOR
# =============================================================================

def cursor_up(n: int = 1)    -> str: return _seq(f"{n}A") if n else ""
def cursor_down(n: int = 1)  -> str: return _seq(f"{n}B") if n else ""
def cursor_right(n: int = 1) -> str: return _seq(f"{n}C") if n else ""
def cursor_left(n: int = 1)  -> str: return _seq(f"{n}D") if n else ""
def cursor_pos(row: int, col: int) -> str: return _seq(f"{row};{col}H")
def cursor_col(col: int)     -> str: return _seq(f"{col}G") if _ANSI_SUPPORTED else ""
def cursor_save()    -> str: return "\033[s" if _ANSI_SUPPORTED else ""
def cursor_restore() -> str: return "\033[u" if _ANSI_SUPPORTED else ""
def cursor_hide()    -> str: return "\033[?25l" if _ANSI_SUPPORTED else ""
def cursor_show()    -> str: return "\033[?25h" if _ANSI_SUPPORTED else ""

def move_cursor(row: int, col: int) -> None:
    sys.stdout.write(cursor_pos(row, col))
    sys.stdout.flush()

# =============================================================================
# CZYSZCZENIE EKRANU
# =============================================================================

def clear_screen()     -> str: return _seq("2J") + _seq("H") if _ANSI_SUPPORTED else ""
def clear_line()       -> str: return _seq("2K") + "\r"      if _ANSI_SUPPORTED else ""
def clear_line_right() -> str: return _seq("0K")             if _ANSI_SUPPORTED else ""
def clear_line_left()  -> str: return _seq("1K")             if _ANSI_SUPPORTED else ""
def clear_to_end()     -> str: return _seq("0J")             if _ANSI_SUPPORTED else ""
def clear_to_start()   -> str: return _seq("1J")             if _ANSI_SUPPORTED else ""

def cls() -> None:
    # Uzywamy sekwencji VT zamiast os.system("cls"/"clear") – eliminuje
    # subprocess i działa identycznie na wszystkich platformach z VT support.
    # Na terminalach bez ANSI sekwencja jest po prostu ignorowana jako
    # niezrozumiany znak, co jest bezpieczniejszym fallbackiem.
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()

# =============================================================================
# RAMKI I SEPARATORY
# =============================================================================

class _BoxChars:
    SINGLE  = dict(
        tl="\u250c", tr="\u2510", bl="\u2514", br="\u2518",
        h="\u2500",  v="\u2502",
        tee_l="\u251c", tee_r="\u2524", tee_t="\u252c", tee_b="\u2534", cross="\u253c",
    )
    DOUBLE  = dict(
        tl="\u2554", tr="\u2557", bl="\u255a", br="\u255d",
        h="\u2550",  v="\u2551",
        tee_l="\u2560", tee_r="\u2563", tee_t="\u2566", tee_b="\u2569", cross="\u256c",
    )
    ROUNDED = dict(
        tl="\u256d", tr="\u256e", bl="\u2570", br="\u256f",
        h="\u2500",  v="\u2502",
        tee_l="\u251c", tee_r="\u2524", tee_t="\u252c", tee_b="\u2534", cross="\u253c",
    )
    BOLD    = dict(
        tl="\u250f", tr="\u2513", bl="\u2517", br="\u251b",
        h="\u2501",  v="\u2503",
        tee_l="\u2523", tee_r="\u252b", tee_t="\u2533", tee_b="\u253b", cross="\u254b",
    )
    DASHED  = dict(
        tl="\u250c", tr="\u2510", bl="\u2514", br="\u2518",
        h="\u254c",  v="\u254e",
        tee_l="\u251c", tee_r="\u2524", tee_t="\u252c", tee_b="\u2534", cross="\u253c",
    )
    ASCII   = dict(
        tl="+", tr="+", bl="+", br="+",
        h="-",  v="|",
        tee_l="+", tee_r="+", tee_t="+", tee_b="+", cross="+",
    )

BOX = _BoxChars()


def box(
    lines:       List[str],
    title:       str  = "",
    style:       str  = "single",
    width:       int  = 0,
    color              = None,
    title_color        = None,
    padding:     int  = 1,
) -> str:
    """
    Rysuje ramke wokol listy linii.
    style:       'single' | 'double' | 'rounded' | 'bold' | 'dashed' | 'ascii'
    padding:     spacje wewnatrz ramki
    title_color: osobna funkcja koloru dla tytulu
    """
    chars       = getattr(BOX, style.upper(), BOX.SINGLE)
    inner_width = width or max((visual_len(l) for l in lines), default=0)
    inner_width = max(inner_width, visual_len(title) + 2)

    c        = color       if color       else lambda x: x
    tc       = title_color if title_color else c
    pad_str  = " " * padding
    full_w   = inner_width + padding * 2

    h_line = chars["h"] * (full_w + 2)

    if title:
        title_str = f"{pad_str}{title}{pad_str}"
        pad_right = full_w + 2 - visual_len(title_str)
        top = c(chars["tl"]) + tc(title_str) + c(chars["h"] * pad_right) + c(chars["tr"])
    else:
        top = c(chars["tl"]) + c(h_line) + c(chars["tr"])

    bottom = c(chars["bl"]) + c(h_line) + c(chars["br"])

    result = [top]
    for line in lines:
        padded = pad(line, inner_width)
        result.append(c(chars["v"]) + pad_str + padded + pad_str + c(chars["v"]))
    result.append(bottom)
    return "\n".join(result)


def separator(
    width: int = 0,
    char:  str = "\u2500",
    label: str = "",
    color       = None,
) -> str:
    """Rysuje poziomy separator (opcjonalnie z etykieta)."""
    term_w = shutil.get_terminal_size((80, 24)).columns
    w      = width or term_w
    c      = color if color else lambda x: x
    if label:
        lv    = visual_len(label)
        left  = (w - lv - 2) // 2
        right = w - lv - 2 - left
        return c(char * left) + " " + label + " " + c(char * right)
    return c(char * w)


def hline(width: int = 0, char: str = "\u2500", color=None) -> str:
    return separator(width=width, char=char, color=color)

# =============================================================================
# DRZEWO  tree()
# =============================================================================

def tree(
    data:        Union[dict, list],
    *,
    title:       str           = "",
    indent:      str           = "  ",
    color_key:   Optional[Callable] = None,
    color_val:   Optional[Callable] = None,
    color_branch: Optional[Callable] = None,
    _prefix:     str           = "",
    _last:       bool          = True,
) -> str:
    """
    Rysuje drzewo z dict/list. Obsluguje zagniezdzanie.

    Przyklad:
        data = {"app": {"src": ["main.py","utils.py"], "tests": ["test_main.py"]}, "README.md": None}
        print(tree(data, title="projekt", color_key=cyan, color_val=muted))
    """
    ck  = color_key    or (lambda x: x)
    cv  = color_val    or (lambda x: x)
    cb  = color_branch or muted
    out = []

    if title and not _prefix:
        out.append(primary(title) if not color_key else ck(title))

    def _render(node, prefix, last):
        connector  = cb("\u2514\u2500\u2500 ") if last else cb("\u251c\u2500\u2500 ")

        if isinstance(node, dict):
            items = list(node.items())
            for idx, (k, v) in enumerate(items):
                is_last = (idx == len(items) - 1)
                conn    = cb("\u2514\u2500\u2500 ") if is_last else cb("\u251c\u2500\u2500 ")
                ext     = "    "                    if is_last else cb("\u2502   ")
                if isinstance(v, (dict, list)) and v:
                    out.append(f"{prefix}{conn}{ck(str(k))}")
                    _render(v, prefix + ext, is_last)
                elif v is None:
                    out.append(f"{prefix}{conn}{ck(str(k))}")
                else:
                    out.append(f"{prefix}{conn}{ck(str(k))}: {cv(str(v))}")
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                is_last = (idx == len(node) - 1)
                conn    = cb("\u2514\u2500\u2500 ") if is_last else cb("\u251c\u2500\u2500 ")
                ext     = "    "                    if is_last else cb("\u2502   ")
                if isinstance(item, (dict, list)):
                    _render(item, prefix + ext, is_last)
                else:
                    out.append(f"{prefix}{conn}{cv(str(item))}")
        else:
            out.append(f"{prefix}{connector}{cv(str(node))}")

    _render(data, _prefix, _last)
    return "\n".join(out)

# =============================================================================
# KOLUMNY  columns()
# =============================================================================

def columns(
    items:   List[str],
    *,
    cols:    int  = 0,
    width:   int  = 0,
    gap:     int  = 2,
    align:   str  = "left",
) -> str:
    """
    Wyswietla liste elementow w wielokolumnowym ukladzie.
    cols=0 — auto (dopasowanie do szerokosci terminala).

    Przyklad:
        cmds = ["help", "exit", "ansi", "lang", "clear", "history"]
        print(columns(cmds, cols=3, gap=4))
    """
    if not items:
        return ""
    term_w  = width or shutil.get_terminal_size((80, 24)).columns
    max_len = max(visual_len(i) for i in items)
    col_w   = max_len + gap

    if not cols:
        cols = max(1, term_w // col_w)

    rows_n  = math.ceil(len(items) / cols)
    out     = []
    for r in range(rows_n):
        row_parts = []
        for c in range(cols):
            idx = r + c * rows_n
            if idx < len(items):
                row_parts.append(pad(items[idx], col_w, align=align))
        out.append("".join(row_parts).rstrip())
    return "\n".join(out)

# =============================================================================
# BLOK KODU  code_block()
# =============================================================================

_SYNTAX_KEYWORDS = {
    "python": {
        "kw":   r"\b(def|class|import|from|return|if|elif|else|for|while|with|as|"
                r"try|except|finally|raise|pass|break|continue|lambda|yield|async|await|"
                r"and|or|not|in|is|True|False|None)\b",
        "str":  r"(\"\"\"[\s\S]*?\"\"\"|\'\'\'[\s\S]*?\'\'\'|\"[^\"\\]*(?:\\.[^\"\\]*)*\"|'[^'\\]*(?:\\.[^'\\]*)*')",
        "num":  r"\b(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b",
        "cmt":  r"(#[^\n]*)",
        "dec":  r"(@\w+)",
    },
    "bash": {
        "kw":   r"\b(if|then|else|elif|fi|for|while|do|done|case|esac|in|function|"
                r"return|exit|echo|export|source|local|readonly)\b",
        "str":  r"(\"[^\"\\]*(?:\\.[^\"\\]*)*\"|'[^']*')",
        "num":  r"\b(\d+)\b",
        "cmt":  r"(#[^\n]*)",
        "var":  r"(\$\w+|\$\{[^}]+\})",
    },
}

_SYNTAX_COLORS = {
    "kw":  lambda x: fg_rgb(204, 153, 255, x),   # fioletowy
    "str": lambda x: fg_rgb(152, 195, 121, x),   # zielony
    "num": lambda x: fg_rgb(229, 192, 123, x),   # pomaranczowy
    "cmt": lambda x: dim_text(fg_rgb(98, 114, 164, x)),  # szary/dim
    "dec": lambda x: fg_rgb(255, 180, 60, x),    # zloty
    "var": lambda x: fg_rgb(86, 182, 194, x),    # cyan
}


def _highlight_syntax(code: str, lang: str) -> str:
    """Prosta koloryzacja skladni (regex, brak pelnego parsera)."""
    if not _ANSI_SUPPORTED:
        return code
    rules = _SYNTAX_KEYWORDS.get(lang.lower(), {})
    if not rules:
        return code

    # buduj mape pozycja -> (koniec, typ, tresc)
    spans: List[Tuple[int,int,str,str]] = []
    for typ, pattern in rules.items():
        for m in re.finditer(pattern, code):
            spans.append((m.start(), m.end(), typ, m.group()))
    # usun nakladajace sie — zachowaj pierwsze
    spans.sort(key=lambda x: x[0])
    filtered = []
    last_end = 0
    for s, e, typ, txt in spans:
        if s >= last_end:
            filtered.append((s, e, typ, txt))
            last_end = e

    out   = []
    pos   = 0
    for s, e, typ, txt in filtered:
        out.append(code[pos:s])
        fn = _SYNTAX_COLORS.get(typ, lambda x: x)
        out.append(fn(txt))
        pos = e
    out.append(code[pos:])
    return "".join(out)


def code_block(
    code:       str,
    lang:       str  = "",
    title:      str  = "",
    *,
    line_nums:  bool = True,
    highlight:  bool = True,
    style:      str  = "rounded",
    width:      int  = 0,
) -> str:
    """
    Wyswietla blok kodu z numeracja linii i opcjonalna koloryzacja skladni.
    lang: 'python' | 'bash' | '' (plain)

    Przyklad:
        src = "def hello():\\n    print('world')"
        print(code_block(src, lang="python", title="hello.py"))
    """
    chars    = getattr(BOX, style.upper(), BOX.ROUNDED)
    lines    = code.splitlines()
    lnum_w   = len(str(len(lines)))
    tw       = width or shutil.get_terminal_size((80, 24)).columns

    processed = []
    for i, ln in enumerate(lines, 1):
        hl_line = _highlight_syntax(ln, lang) if (highlight and lang) else ln
        if line_nums:
            num = muted(str(i).rjust(lnum_w) + "  ")
            processed.append(num + hl_line)
        else:
            processed.append(hl_line)

    inner_w = max((visual_len(ln) for ln in lines), default=0)
    inner_w = max(inner_w, visual_len(title)) + (lnum_w + 2 if line_nums else 0)
    inner_w = min(inner_w, tw - 4)

    header_text = f" {lang}  {title}" if lang and title else (f" {title}" if title else f" {lang}")
    header_text = header_text.strip()

    c  = muted
    tc = primary

    if header_text:
        hs  = f" {header_text} "
        rem = inner_w + 2 - visual_len(hs)
        top = c(chars["tl"]) + tc(hs) + c(chars["h"] * max(0, rem)) + c(chars["tr"])
    else:
        top = c(chars["tl"]) + c(chars["h"] * (inner_w + 2)) + c(chars["tr"])

    bottom = c(chars["bl"]) + c(chars["h"] * (inner_w + 2)) + c(chars["br"])

    out = [top]
    for ln in processed:
        out.append(c(chars["v"]) + " " + ln + c(chars["v"]))
    out.append(bottom)
    return "\n".join(out)

# =============================================================================
# DIFF  diff_line()
# =============================================================================

def diff_line(line: str) -> str:
    """
    Koloruje pojedyncza linie diff/patch:
      '+' — zielony (dodano)
      '-' — czerwony (usunieto)
      '@' — cyan (naglowek hunka)
      '#' — szary (komentarz/info)
    """
    if not line:
        return line
    ch = line[0]
    if ch == "+":
        return fg_rgb(80, 220, 100, line)
    if ch == "-":
        return fg_rgb(255, 100, 100, line)
    if ch == "@":
        return fg_rgb(86, 182, 194, bold_text(line))
    if ch == "#":
        return muted(line)
    return line


def diff(text: str) -> str:
    """Koloruje caly blok diff (wiele linii)."""
    return "\n".join(diff_line(ln) for ln in text.splitlines())

# =============================================================================
# LINIE LOGU  log_line()
# =============================================================================

_LOG_LEVELS: Dict[str, Tuple[str, Callable]] = {
    "debug": ("\u25cf DEBUG  ", muted),
    "info":  ("\u2139 INFO   ", primary),
    "ok":    ("\u2714 OK     ", success),
    "warn":  ("\u26a0 WARN   ", warning),
    "error": ("\u2718 ERROR  ", error),
    "fatal": ("\u2620 FATAL  ", lambda x: bold_text(error(x))),
}


def log_line(
    msg:       str,
    level:     str  = "info",
    *,
    timestamp: bool = True,
    ts_fmt:    str  = "%H:%M:%S",
) -> str:
    """
    Formatuje linie logu z poziomem i opcjonalnym znacznikiem czasu.

    Przyklad:
        print(log_line("serwer uruchomiony", "ok"))
        print(log_line("brakuje pliku konfiguracyjnego", "error"))
    """
    icon, color_fn = _LOG_LEVELS.get(level.lower(), ("\u25cf       ", muted))
    ts = muted(datetime.now().strftime(ts_fmt) + "  ") if timestamp else ""
    return f"{ts}{color_fn(icon)}{msg}"


def print_log(msg: str, level: str = "info", **kw) -> None:
    print(log_line(msg, level, **kw))

# =============================================================================
# POWIADOMIENIE  notification()
# =============================================================================

_NOTIF_ICONS = {
    "info":    "\u2139 ",
    "success": "\u2714 ",
    "warning": "\u26a0 ",
    "error":   "\u2718 ",
    "tip":     "\u2726 ",
}

_NOTIF_COLORS = {
    "info":    primary,
    "success": success,
    "warning": warning,
    "error":   error,
    "tip":     accent,
}


def notification(
    title:    str,
    body:     str  = "",
    kind:     str  = "info",
    *,
    width:    int  = 0,
    ts:       bool = False,
) -> str:
    """
    Eleganckie powiadomienie w ramce z ikona i opcjonalnym znacznikiem czasu.
    kind: 'info' | 'success' | 'warning' | 'error' | 'tip'

    Przyklad:
        print(notification("Zadanie ukonczone", "Plik zapisano poprawnie.", "success"))
    """
    icon     = _NOTIF_ICONS.get(kind, "\u2022 ")
    color_fn = _NOTIF_COLORS.get(kind, muted)
    term_w   = width or min(60, shutil.get_terminal_size((80, 24)).columns - 4)

    header = color_fn(icon + title)
    if ts:
        now    = datetime.now().strftime("%H:%M:%S")
        header = header + muted(f"  [{now}]")

    content = [header]
    if body:
        wrapped = wrap(body, width=term_w - 4, indent="  ")
        for ln in wrapped.splitlines():
            content.append(muted("  " + ln))

    return box(content, style="rounded", color=color_fn, padding=1, width=term_w)

# =============================================================================
# TABELA FLEX  flex_table()
# =============================================================================

def flex_table(
    headers:    List[str],
    rows:       List[List[str]],
    *,
    col_align:  Optional[List[str]] = None,
    header_color                    = None,
    sep:        str                 = "  ",
    show_header: bool               = True,
) -> str:
    """
    Tabela bez ramek, czysty format plaintext z wyrownaniem kolumn.
    Przydatna do list komend, par klucz-wartosc, lekkich danych.

    Przyklad:
        flex_table(["Komenda", "Opis"], [["help","lista pomocy"],["exit","wyjscie"]])
    """
    all_rows = ([headers] if show_header else []) + [[str(c) for c in r] for r in rows]
    n_cols   = max(len(r) for r in all_rows)
    widths   = [0] * n_cols
    for row in all_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], visual_len(cell))
    align_map = col_align or ["left"] * n_cols
    hc        = header_color or bold_text
    out       = []

    for ridx, row in enumerate(all_rows):
        parts = []
        for i in range(n_cols):
            cell   = row[i] if i < len(row) else ""
            a      = align_map[i] if i < len(align_map) else "left"
            padded = pad(cell, widths[i], align=a)
            if ridx == 0 and show_header:
                padded = hc(padded)
            parts.append(padded)
        out.append(sep.join(parts).rstrip())
        if ridx == 0 and show_header:
            out.append(muted("\u2500" * min(sum(widths) + len(sep) * (n_cols - 1), 120)))
    return "\n".join(out)

# =============================================================================
# PASKI POSTEPU
# =============================================================================

_BAR_STYLES = {
    "block":   ("\u2588", "\u2591"),   # full block / light shade
    "shade":   ("\u2593", "\u2591"),   # dark shade / light shade
    "fill":    ("\u25a0", "\u25a1"),   # filled square / empty square
    "arrow":   ("\u2501", "\u254c"),   # heavy dash / light dash
    "classic": ("#", "."),
    "thin":    ("\u25aa", "\u25ab"),   # small filled / empty square
    "grad":    ("grad", " "),          # specjalny tryb sub-character
}


def progress_bar(
    value:    float,
    total:    float = 100.0,
    width:    int   = 30,
    filled:   str   = "",
    empty:    str   = "",
    show_pct: bool  = True,
    style:    str   = "block",
    color_fn          = None,
    bg_color_fn       = None,
) -> str:
    """
    Rysuje pasek postepu.
    style: 'block' | 'shade' | 'fill' | 'arrow' | 'classic' | 'thin' | 'grad'
    """
    pct = max(0.0, min(1.0, value / total if total else 0))

    if not filled and not empty:
        pair   = _BAR_STYLES.get(style, _BAR_STYLES["block"])
        filled = pair[0]
        empty  = pair[1]

    if style == "grad" and _ANSI_SUPPORTED:
        subchars = "\u258f\u258e\u258d\u258c\u258b\u258a\u2589\u2588"
        done_f   = pct * width
        done_i   = int(done_f)
        frac     = done_f - done_i
        sub_idx  = int(frac * 8)
        sub_ch   = subchars[sub_idx] if done_i < width else ""
        bar_str  = "\u2588" * done_i + sub_ch
        bar_str  = bar_str.ljust(width)
    else:
        done    = round(pct * width)
        bar_str = filled * done + empty * (width - done)

    if color_fn:
        bar_str = color_fn(bar_str)

    pct_str = f" {pct*100:5.1f}%" if show_pct else ""
    return f"[{bar_str}]{pct_str}"


def spinner_frame(n: int, style: str = "dots") -> str:
    """Zwraca klatke animacji spinnera dla indeksu n."""
    frames = {
        "dots":    ["\u280b","\u2819","\u2839","\u2838","\u283c","\u2834","\u2826","\u2827","\u2807","\u280f"],
        "dots2":   ["\u28fe","\u28fd","\u28fb","\u28bf","\u287f","\u28df","\u28ef","\u28f7"],
        "line":    ["|","/","-","\\"],
        "arrow":   ["\u2190","\u2196","\u2191","\u2197","\u2192","\u2198","\u2193","\u2199"],
        "bounce":  ["\u2801","\u2802","\u2804","\u2802"],
        "square":  ["\u25f0","\u25f3","\u25f2","\u25f1"],
        "bar":     ["\u2581","\u2582","\u2583","\u2584","\u2585","\u2586","\u2587","\u2588",
                    "\u2587","\u2586","\u2585","\u2584","\u2583","\u2582"],
        "clock":   ["\U0001f55c","\U0001f55d","\U0001f55e","\U0001f55f",
                    "\U0001f560","\U0001f561","\U0001f562","\U0001f563",
                    "\U0001f564","\U0001f565","\U0001f566","\U0001f567"],
        "moon":    ["\U0001f311","\U0001f312","\U0001f313","\U0001f314",
                    "\U0001f315","\U0001f316","\U0001f317","\U0001f318"],
        "weather": ["\u2600","\u26c5","\u2601","\u26c8","\u26a1","\u2614","\u2603","\u26c4"],
        "grow":    ["\u2581","\u2582","\u2584","\u2585","\u2587","\u2588","\u2587","\u2585","\u2584","\u2582"],
    }
    seq = frames.get(style, frames["line"])
    return seq[n % len(seq)]

# =============================================================================
# SPARKLINE
# =============================================================================

_SPARK_CHARS = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def sparkline(
    data:     Sequence[float],
    *,
    min_val:  Optional[float] = None,
    max_val:  Optional[float] = None,
    color_fn               = None,
) -> str:
    """
    Rysuje sparkline (mini wykres slupkowy).
    Przyklad:
        vals = [1, 3, 2, 8, 5, 4, 9, 2, 6]
        print(sparkline(vals, color_fn=cyan))
    """
    if not data:
        return ""
    lo  = min_val if min_val is not None else min(data)
    hi  = max_val if max_val is not None else max(data)
    rng = hi - lo or 1.0
    n   = len(_SPARK_CHARS) - 1
    out = []
    for v in data:
        idx = int((v - lo) / rng * n)
        out.append(_SPARK_CHARS[max(0, min(n, idx))])
    result = "".join(out)
    return color_fn(result) if color_fn else result


def sparkline_labeled(
    data:          Sequence[float],
    label:         str = "",
    unit:          str = "",
    *,
    color_fn           = None,
    label_color_fn     = None,
) -> str:
    """Sparkline z etykieta i wartosciami min/max."""
    lo = min(data) if data else 0
    hi = max(data) if data else 0
    lc = label_color_fn or muted
    sp = sparkline(data, color_fn=color_fn)
    parts = []
    if label:
        parts.append(lc(f"{label}: "))
    parts.append(sp)
    parts.append(lc(f"  {lo:.1f}\u2026{hi:.1f}{unit}"))
    return "".join(parts)

# =============================================================================
# TABELA
# =============================================================================

def table(
    headers:    List[str],
    rows:       List[List[str]],
    style:      str                          = "single",
    col_align:  Optional[List[str]]          = None,
    header_color                             = None,
    row_colors: Optional[List[Optional[Callable]]] = None,
    zebra:      bool                         = False,
    zebra_color                              = None,
) -> str:
    """
    Rysuje sformatowana tabele.
    zebra=True    — naprzemienne tlo wierszy
    row_colors    — lista funkcji kolorow dla poszczegolnych wierszy
    """
    chars    = getattr(BOX, style.upper(), BOX.SINGLE)
    all_rows = [headers] + [[str(c) for c in r] for r in rows]
    n_cols   = max(len(r) for r in all_rows)

    widths = [0] * n_cols
    for row in all_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], visual_len(cell))

    align_map = col_align or ["left"] * n_cols
    zc        = zebra_color or (lambda x: fg_rgb(40, 40, 55, x) if _ANSI_SUPPORTED else x)

    def _row_str(row, color_fn=None, bg_fn=None) -> str:
        cells = []
        for i in range(n_cols):
            cell   = row[i] if i < len(row) else ""
            a      = align_map[i] if i < len(align_map) else "left"
            padded = pad(cell, widths[i], align=a)
            if color_fn:
                padded = color_fn(padded)
            cells.append(padded)
        inner = " " + f" {chars['v']} ".join(cells) + " "
        if bg_fn:
            inner = bg_fn(inner)
        return chars["v"] + inner + chars["v"]

    def _sep_str(left, mid, right) -> str:
        parts = [chars["h"] * (w + 2) for w in widths]
        return left + mid.join(parts) + right

    top    = _sep_str(chars["tl"],    chars["tee_t"], chars["tr"])
    hd_sep = _sep_str(chars["tee_l"], chars["cross"], chars["tee_r"])
    bottom = _sep_str(chars["bl"],    chars["tee_b"], chars["br"])

    out = [top, _row_str(headers, color_fn=header_color), hd_sep]
    for idx, row in enumerate(rows):
        bg = zc if (zebra and idx % 2 == 1) else None
        rc = row_colors[idx] if row_colors and idx < len(row_colors) else None
        out.append(_row_str([str(c) for c in row], color_fn=rc, bg_fn=bg))
    out.append(bottom)
    return "\n".join(out)

# =============================================================================
# BADGE / ETYKIETY
# =============================================================================

def badge(text: str, color_fn=None, style: str = "square") -> str:
    styles_map = {
        "square": f"[{text}]",
        "round":  f"({text})",
        "angle":  f"\u2039{text}\u203a",
        "double": f"\u00ab{text}\u00bb",
        "block":  f"\u2590{text}\u258c",
        "plain":  f" {text} ",
    }
    s = styles_map.get(style, f"[{text}]")
    return color_fn(s) if color_fn else s


def status_badge(text: str, status: str = "ok") -> str:
    role_map = {
        "ok":    "success",
        "warn":  "warning",
        "error": "error",
        "info":  "primary",
        "muted": "muted",
    }
    role = role_map.get(status, "muted")
    return badge(text, color_fn=lambda x: _theme.apply(role, x))


def pill(text: str, color_fn=None) -> str:
    """Etykieta pill z zaokraglonymi koncami."""
    s = f"\u258a {text} \u2590"
    return color_fn(s) if color_fn else s

# =============================================================================
# PRINT WRAPPERS
# =============================================================================

def print_ok(msg: str)      -> None: print(f"  {success('[V]')} {msg}")
def print_err(msg: str)     -> None: print(f"  {error('[X]')} {msg}")
def print_warn(msg: str)    -> None: print(f"  {warning('[!]')} {msg}")
def print_info(msg: str)    -> None: print(f"  {primary('[->]')} {msg}")
def print_muted(msg: str)   -> None: print(f"  {muted(msg)}")
def print_header(msg: str)  -> None: print(f"\n  {bold_text(primary(msg))}\n")
def print_section(msg: str) -> None:
    w = shutil.get_terminal_size((80, 24)).columns - 4
    print(f"  {muted('--')} {accent(msg)} {muted('-' * max(0, w - visual_len(msg) - 4))}")

def print_rule(label: str = "", char: str = "\u2500", color=None) -> None:
    """Drukuje poziomy separator przez cala szerokosc terminala."""
    w = shutil.get_terminal_size((80, 24)).columns
    print(separator(w, char=char, label=label, color=color or muted))

def print_kv(key: str, value: str, key_width: int = 20) -> None:
    """Drukuje pare klucz-wartosc wyrownana do key_width."""
    print(f"  {muted(pad(key, key_width))} {value}")

# =============================================================================
# PODGLAD PALETY (diagnostyka)
# =============================================================================

def _show_palette() -> None:
    """Wyswietla wszystkie dostepne kolory i elementy (demo)."""
    print("\n  -- Kolory standardowe --")
    for name, obj in [("BLACK",BLACK),("RED",RED),("GREEN",GREEN),("YELLOW",YELLOW),
                       ("BLUE",BLUE),("MAGENTA",MAGENTA),("CYAN",CYAN),("WHITE",WHITE)]:
        print(f"  {obj(name):20}  {obj(name, bright=True)} (bright)  {obj('tlo', bg=True)}")

    print("\n  -- Paleta 256 (probka) --")
    row = "  "
    for i in range(16, 232, 14):
        row += fg256(i, f"#{i:<3}")
    print(row + reset())

    print("\n  -- True Color gradient --")
    print("  " + gradient("Czerwony  -->  Niebieski", (255,50,50),(0,100,255)))
    rainbow = [(255,0,0),(255,165,0),(255,255,0),(0,255,0),(0,100,255),(148,0,211)]
    print("  " + gradient_multicolor("Gradient wielokolorowy ROYGBV", rainbow))

    print("\n  -- Motyw aktywny --")
    for role in ("primary","secondary","success","warning","error","muted","accent"):
        print(f"  {t(role, role):30}")

    print("\n  -- Style --")
    for name, fn in [("bold",bold_text),("dim",dim_text),("italic",italic_text),
                     ("underline",underline_text),("strike",strike_text),
                     ("overline",overline_text),("invert",invert_text)]:
        print(f"  {fn(name)}")

    print("\n  -- Paski postepu (style) --")
    for sty in ("block","shade","fill","arrow","classic","grad"):
        bar = progress_bar(66, style=sty, color_fn=yellow)
        print(f"  {muted(f'{sty:<8}')} {bar}")

    print("\n  -- Sparkline --")
    vals = [1,3,2,8,5,4,9,2,6,7,4,3,8,1,5]
    print("  " + sparkline_labeled(vals, "CPU", "%", color_fn=cyan))

    print("\n  -- Ramki --")
    for sty in ("single","double","rounded","bold","dashed"):
        print(box([f"Styl: {sty}"], title=sty.upper(), style=sty,
                  color=muted, title_color=primary))
        print()

    print("\n  -- Markup paint() --")
    print("  " + paint("[bold][primary]TerminalX[/] -- [success]aktywny[/] | [muted]v1.3.0[/bold]"))
    print("  " + paint("[red]Blad:[/] [white]cos poszlo nie tak[/]"))
    print("  " + paint("[rgb:0,200,255]kolor RGB[/] | [hex:#ff6600]kolor HEX[/]"))

    print("\n  -- Badge / pill --")
    for s in ("square","round","angle","double","block"):
        print(f"  {badge('INFO', color_fn=primary, style=s)}  ", end="")
    print()
    print("  " + pill("polsoft.ITS", color_fn=primary))

    print("\n  -- Hyperlink (OSC 8) --")
    print("  " + hyperlink("https://github.com", primary("github.com")))

    print("\n  -- Drzewo --")
    _tree_demo = {"app": {"src": ["main.py","ansi.py"], "lang": ["en.py","pl.py"]}, "README.md": None}
    print(tree(_tree_demo, title="projekt", color_key=cyan, color_val=muted))

    print("\n  -- Kolumny --")
    cmds = ["help","exit","ansi","lang","clear","history","run","debug","watch","analyze","build","test"]
    print(columns(cmds, cols=4, gap=3))

    print("\n  -- Blok kodu --")
    src = "def hello(name):\n    print(f'Hello, {name}!')\n\nhello('TerminalX')"
    print(code_block(src, lang="python", title="hello.py"))

    print("\n  -- Diff --")
    patch = "-stara linia\n+nowa linia\n@@ -1,3 +1,4 @@\n kontekst"
    print(diff(patch))

    print("\n  -- Log lines --")
    for lvl in ("debug","info","ok","warn","error","fatal"):
        print("  " + log_line(f"przykladowy komunikat [{lvl}]", lvl))

    print("\n  -- Powiadomienie --")
    print(notification("Zadanie ukonczone", "Plik zapisano pomyslnie.", "success", ts=True))

    print("\n  -- Flex table --")
    print(flex_table(
        ["Komenda", "Kategoria", "Opis"],
        [["ansi","eco","obsluga ANSI"],["lang","eco","jezyki i18n"],["help","core","pomoc"]],
        header_color=lambda x: bold_text(cyan(x)),
    ))
    print()


# =============================================================================
# INTEGRACJA Z TERMINALX
# =============================================================================

_MODULE_VERSION = "1.3.0"


def setup(terminal) -> None:
    """Rejestruje komendy ANSI w TerminalX."""

    def _cmd_ansi(args: list):
        sub = args[0].lower() if args else "status"

        if sub in ("demo", "colors", "palette"):
            _show_palette()

        elif sub == "status":
            _none   = terminal.t("ansi_status_none")
            state   = success(terminal.t("ansi_status_active"))   if _ANSI_SUPPORTED else error(terminal.t("ansi_status_inactive"))
            tc_info = success(terminal.t("ansi_truecolor_yes"))    if _TRUECOLOR      else muted(terminal.t("ansi_truecolor_no"))
            print(f"  ANSI:       {state}")
            print(f"  True Color: {tc_info}")
            print(f"  {terminal.t('ansi_status_version'):<11} {muted(_MODULE_VERSION)}")
            print(f"  {terminal.t('ansi_status_term'):<11} {muted(os.environ.get('TERM', _none))}")
            print(f"  {terminal.t('ansi_status_colorterm'):<11} {muted(os.environ.get('COLORTERM', _none))}")

        elif sub == "on":
            force_enable(True)
            print(f"  ANSI: {success(terminal.t('ansi_enabled'))}.")
        elif sub == "off":
            force_enable(False)
            print(f"  ANSI: {muted(terminal.t('ansi_disabled'))}.")

        elif sub == "box":
            style_arg = args[1] if len(args) > 1 else "rounded"
            text_arg  = " ".join(args[2:]) if len(args) > 2 else terminal.t("ansi_box_default")
            print(box([text_arg], title="ansi.box", style=style_arg,
                      color=muted, title_color=primary))

        elif sub == "table":
            print(table(
                [terminal.t("ansi_table_module"), terminal.t("ansi_table_status"), terminal.t("ansi_table_version")],
                [["ansi",   success(terminal.t("ansi_table_active")), _MODULE_VERSION],
                 ["colors", success(terminal.t("ansi_table_active")), "1.0.0"]],
                header_color=lambda x: bold_text(cyan(x)),
                zebra=True,
            ))

        elif sub == "progress":
            try:   val = float(args[1]) if len(args) > 1 else 66.0
            except ValueError: val = 66.0
            col = green if val >= 75 else (yellow if val >= 40 else red)
            for sty in ("block","shade","fill","arrow","classic","grad"):
                print(f"  {muted(f'{sty:<8}')} {progress_bar(val, style=sty, color_fn=col)}")

        elif sub == "gradient":
            text = " ".join(args[1:]) if len(args) > 1 else terminal.t("ansi_gradient_default")
            print("  " + gradient(text, (0, 200, 255), (200, 50, 255)))
            rainbow = [(255,0,0),(255,165,0),(255,255,0),(0,255,0),(0,100,255),(148,0,211)]
            print("  " + gradient_multicolor(text, rainbow))

        elif sub == "paint":
            sample = " ".join(args[1:]) if len(args) > 1 else terminal.t("ansi_paint_default")
            print("  " + paint(sample))

        elif sub == "sparkline":
            data = [abs(math.sin(i * 0.4)) * 10 for i in range(30)]
            print("  " + sparkline_labeled(data, "demo", "%", color_fn=cyan))
            print("  " + sparkline(data, color_fn=lambda x:
                "".join(green(c) if ord(c) >= ord(_SPARK_CHARS[6]) else
                        yellow(c) if ord(c) >= ord(_SPARK_CHARS[3]) else
                        muted(c) for c in x)))

        elif sub == "hyperlink":
            url  = args[1] if len(args) > 1 else "https://github.com"
            text = " ".join(args[2:]) if len(args) > 2 else url
            print("  " + hyperlink(url, primary(text)))

        elif sub == "wrap":
            sample = " ".join(args[1:]) if len(args) > 1 else terminal.t("ansi_wrap_default")
            w = shutil.get_terminal_size((80,24)).columns - 6
            print(wrap(sample, width=w, indent="  "))

        elif sub == "spinner":
            style_arg = args[1] if len(args) > 1 else "dots"
            frames = [spinner_frame(i, style_arg) for i in range(12)]
            print("  " + "  ".join(primary(f) for f in frames))

        elif sub == "badge":
            for sty in ("square","round","angle","double","block"):
                print(f"  {badge('STATUS', color_fn=primary, style=sty)}  "
                      f"{badge('OK',     color_fn=success, style=sty)}  "
                      f"{badge(terminal.t('ansi_badge_error'), color_fn=error, style=sty)}")
            print(f"  {pill('polsoft.ITS', color_fn=primary)}")

        elif sub == "tree":
            demo = {
                "TerminalX": {
                    "core": ["ansi.py", "analyser.py"],
                    "lang": ["en.py", "pl.py"],
                },
                "TerminalX.py": None,
            }
            custom = " ".join(args[1:])
            if custom:
                # try parsing JSON if provided
                import json
                try:
                    demo = json.loads(custom)
                except Exception:
                    demo = {custom: None}
            print(tree(demo, title=terminal.t("ansi_tree_title"), color_key=cyan, color_val=muted))

        elif sub == "columns":
            items = args[1:] if len(args) > 1 else \
                ["help","exit","ansi","lang","clear","history","run","debug","watch","build","test","version"]
            print(columns(items, gap=3))

        elif sub == "code":
            lang_arg = args[1] if len(args) > 1 else "python"
            samples = {
                "python": "def hello(name):\n    print(f'Hello, {name}!')\n\nhello('TerminalX')",
                "bash":   "#!/bin/bash\nNAME=\"TerminalX\"\necho \"Hello $NAME\"\nexport PATH=$PATH:/usr/local/bin",
            }
            src = samples.get(lang_arg, terminal.t("ansi_code_no_sample").format(lang=lang_arg))
            print(code_block(src, lang=lang_arg, title=f"demo.{lang_arg}"))

        elif sub == "diff":
            patch = terminal.t("ansi_diff_sample")
            print(diff(patch))

        elif sub in ("log", "logs"):
            for lvl in ("debug","info","ok","warn","error","fatal"):
                print(log_line(terminal.t("ansi_log_sample").format(lvl=lvl), lvl))

        elif sub in ("notify", "notification"):
            kinds = ["info","success","warning","error","tip"]
            k     = args[1] if len(args) > 1 and args[1] in kinds else "info"
            msg   = " ".join(args[2:]) if len(args) > 2 else terminal.t("ansi_notify_default")
            print(notification(k.upper(), msg, k, ts=True))

        elif sub in ("flex", "ftable"):
            _t = terminal.t
            print(flex_table(
                [_t("ansi_flex_cmd"), _t("ansi_flex_short"), _t("ansi_flex_desc")],
                [
                    ["ansi status",   "ansi",   _t("ansi_flex_row_status")],
                    ["ansi demo",     "demo",   _t("ansi_flex_row_demo")],
                    ["ansi tree",     "tree",   _t("ansi_flex_row_tree")],
                    ["ansi code",     "code",   _t("ansi_flex_row_code")],
                    ["ansi log",      "log",    _t("ansi_flex_row_log")],
                    ["ansi notify",   "notify", _t("ansi_flex_row_notify")],
                ],
                header_color=lambda x: bold_text(primary(x)),
            ))

        else:
            _usage()

    def _usage():
        _t = terminal.t
        print(f"  {bold_text(cyan(_t('ansi_usage_header') + ':'))} ansi <{_t('ansi_usage_subcmd')}>")
        cmds = [
            ("status",         _t("ansi_sub_status")),
            ("demo",           _t("ansi_sub_demo")),
            ("on/off",         _t("ansi_usage_on_off")),
            ("box",            "ansi box [styl] [tekst]  (single/double/rounded/bold/dashed)"),
            ("table",          _t("ansi_usage_table")),
            ("progress",       _t("ansi_usage_progress")),
            ("gradient",       _t("ansi_sub_gradient")),
            ("paint",          _t("ansi_sub_paint")),
            ("sparkline",      _t("ansi_sub_sparkline")),
            ("hyperlink",      _t("ansi_sub_hyperlink")),
            ("wrap",           _t("ansi_sub_wrap")),
            ("spinner",        _t("ansi_sub_spinner")),
            ("badge",          _t("ansi_sub_badge")),
            ("tree",           _t("ansi_sub_tree")),
            ("columns",        _t("ansi_sub_columns")),
            ("code",           _t("ansi_sub_code")),
            ("diff",           _t("ansi_sub_diff")),
            ("log",            _t("ansi_sub_log")),
            ("notify",         _t("ansi_sub_notify")),
            ("flex / ftable",  _t("ansi_sub_flex")),
        ]
        for sub, desc in cmds:
            print(f"    {yellow(f'ansi {sub}'):<38} {muted(desc)}")

    terminal.register_command(
        "ansi", _cmd_ansi,
        description=terminal.t("cmd_ansi"),
        category=terminal.t("cat_ecosystem"),
    )

    # Rejestracja w _integration – inne moduly moga korzystac z ANSI API
    try:
        from . import _integration as _intg
        _intg.register("ansi", {
            "is_supported":  is_supported,
            "is_truecolor":  is_truecolor,
            "force_enable":  force_enable,
            "force_truecolor": force_truecolor,
            "gradient":      gradient,
            "gradient_multicolor": gradient_multicolor,
            "paint":         paint,
            "table":         table,
            "box":           box,
            "columns":       columns,
            "tree":          tree,
            "diff":          diff,
            "progress_bar":  progress_bar,
            "spinner_frame": spinner_frame,
            "sparkline":     sparkline,
            "notification":  notification,
            "hyperlink":     hyperlink,
            "badge":         badge,
            "status_badge":  status_badge,
            "fg_rgb":        fg_rgb,
            "bg_rgb":        bg_rgb,
            "hex_color":     hex_color,
            "success":       success,
            "error":         error,
            "warning":       warning,
            "muted":         muted,
            "primary":       primary,
            "bold_text":     bold_text,
        })
    except Exception:
        pass


def teardown(terminal) -> None:
    try:
        from . import _integration as _intg
        _intg.unregister("ansi")
    except Exception:
        pass
    terminal.commands.pop("ansi", None)
