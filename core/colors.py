#!/usr/bin/env python3
# autor:   Sebastian Januchowski
# company: polsoft.ITS(TM) Group
# web:     www.polsoft.gt.tc
# github:  https://github.com/seb07uk
# email:   polsoft.its@fastservice.com
# license: MIT
# crossterm: {"id": "13", "aliases": ["colors", "clr", "palette"], "description": "Kolory terminala - ANSI, 256, RGB, OKLCH, gradienty, efekty, motywy", "version": "2.1.0", "author": "Sebastian Januchowski"}
"""
+==============================================================================+
|                    TerminalX EcoSystem                                       |
|                      COLORS Module  v2.1.0                                   |
+==============================================================================+
|  Version     : 2.1.0                                                         |
|  Type        : library  (modul komend)                                       |
|  Created     : 2026-04-27                                                    |
|  Updated     : 2026-06-23                                                    |
+==============================================================================+
|  Author      : Sebastian Januchowski                                         |
|  Company     : polsoft.ITS(TM) Group                                         |
|  Web         : www.polsoft.gt.tc                                              |
|  GitHub      : https://github.com/seb07uk                                    |
|  E-mail      : polsoft.its@fastservice.com                                   |
+==============================================================================+
|  Komendy:                                                                    |
|    colors / color / clr    - menu / info                                     |
|    palette [--256] [--rgb] - pelna paleta kolorow                            |
|    rainbow <tekst>         - tekst w kolorach teczy                          |
|    colorize <kol> <tekst>  - koloruj tekst                                   |
|    gradient <s> <e> <txt>  - gradient RGB / OKLCH (--oklch)                  |
|    theme [nazwa]           - motywy (dark/light/solarized/dracula/nord)      |
|    effects [tekst]         - efekty tekstowe z podgladem                     |
|    scheme <nazwa>          - schematy UI / CSS-like                          |
|    converter <val>         - konwersja hex <-> rgb <-> hsl <-> oklch <->     |
|                              ansi256                                          |
|    preview <kolor> [tekst] - podglad z barem kolorow                         |
|    mix <kol1> <kol2> [%]   - mieszaj dwa kolory (--linear gamma-correct)    |
|    strip <tekst>           - usun sekwencje ANSI z tekstu                   |
|    hq                      - diagnostyka koloru + konwersje OKLCH            |
+==============================================================================+
"""

# ==============================================================================
#  MODULE METADATA
# ==============================================================================

METADATA = {
    "name"       : "colors",
    "version"    : "2.1.0",
    "author"     : "Sebastian Januchowski",
    "company"    : "polsoft.ITS(TM) Group",
    "web"        : "www.polsoft.gt.tc",
    "github"     : "https://github.com/seb07uk",
    "email"      : "polsoft.its@fastservice.com",
    "description": "Advanced terminal color system: ANSI, 256, RGB, OKLCH, gamma-correct blending",
    "type"       : "library",
    "depends"    : [],
    "exports"    : ["TerminalColors", "ColorPalette", "ColorUtils"],
    "min_pyterm" : "2.0.0",
}

import os
import re
import sys
import math
import platform
from typing import Optional, Dict, List, Tuple

# ==============================================================================
#  LOW-LEVEL I/O & ANSI HELPERS
# ==============================================================================

_ansi_re = re.compile(r'\x1b\[[0-9;]*[mA-Z]')

def _w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()

def _strip(s: str) -> str:
    return _ansi_re.sub('', s)

def _vis(s: str) -> int:
    return len(_strip(s))

def _pad(s: str, width: int) -> str:
    return s + ' ' * max(0, width - _vis(s))

# ==============================================================================
#  ANSI CODE CONSTANTS
# ==============================================================================

RST   = "\x1b[0m"
BOLD  = "\x1b[1m"
DIM   = "\x1b[2m"
ITAL  = "\x1b[3m"
UNDR  = "\x1b[4m"
BLNK  = "\x1b[5m"
REV   = "\x1b[7m"
HIDD  = "\x1b[8m"
STRK  = "\x1b[9m"

# Standard fg
_BLK  = "\x1b[30m"; _RED  = "\x1b[31m"; _GRN  = "\x1b[32m"; _YLW  = "\x1b[33m"
_BLU  = "\x1b[34m"; _MGT  = "\x1b[35m"; _CYN  = "\x1b[36m"; _WHT  = "\x1b[37m"

# Bright fg
_BBLK = "\x1b[90m"; _BRED = "\x1b[91m"; _BGRN = "\x1b[92m"; _BYLW = "\x1b[93m"
_BBLU = "\x1b[94m"; _BMGT = "\x1b[95m"; _BCYN = "\x1b[96m"; _BWHT = "\x1b[97m"

# Standard bg
_BGBLK = "\x1b[40m"; _BGRED = "\x1b[41m"; _BGGRN = "\x1b[42m"; _BGYLW = "\x1b[43m"
_BGBLU = "\x1b[44m"; _BGMGT = "\x1b[45m"; _BGCYN = "\x1b[46m"; _BGWHT = "\x1b[47m"

def _fg256(n: int) -> str:  return f"\x1b[38;5;{n}m"
def _bg256(n: int) -> str:  return f"\x1b[48;5;{n}m"
def _fgRGB(r,g,b) -> str:   return f"\x1b[38;2;{r};{g};{b}m"
def _bgRGB(r,g,b) -> str:   return f"\x1b[48;2;{r};{g};{b}m"

# ==============================================================================
#  COLOR DEPTH DETECTION
# ==============================================================================

class ColorDepth:
    """Terminal color depth levels."""
    ANSI_8BIT  = "8-bit"    # ANSI-16 colors only
    COLOR_256  = "256-color"
    TRUECOLOR  = "24-bit"   # full RGB / TrueColor
    HDR_AWARE  = "HDR-aware"  # extended dynamic range capable terminals

# VTE version threshold for reliable TrueColor (3602 = VTE 0.36.2)
_VTE_TRUECOLOR_MIN = 3602

def _get_vte_version() -> Optional[int]:
    """Parse VTE_VERSION env var into integer, e.g. '6800' -> 6800."""
    vte = os.getenv("VTE_VERSION", "")
    try:
        return int(vte)
    except ValueError:
        return None

def _detect_color_depth() -> str:
    """
    Detect terminal color depth with high fidelity.

    Priority order:
    1. NO_COLOR  → 8-bit (no color at all)
    2. FORCE_COLOR → TrueColor
    3. COLORTERM=truecolor|24bit → TrueColor
    4. WT_SESSION / ConPTY (Windows Terminal) → TrueColor
    5. VTE_VERSION >= 3602 → TrueColor
    6. TERM_PROGRAM checks (iTerm, Hyper, WezTerm…) → TrueColor
    7. TERM contains 256color → 256-color
    8. TERM=xterm,screen,tmux → 256-color (conservative)
    9. Fallback → 8-bit
    """
    if os.getenv("NO_COLOR"):
        return ColorDepth.ANSI_8BIT

    if os.getenv("FORCE_COLOR"):
        return ColorDepth.TRUECOLOR

    colorterm = os.getenv("COLORTERM", "").lower()
    if colorterm in ("truecolor", "24bit"):
        return ColorDepth.TRUECOLOR

    # Windows Terminal (ConPTY) — WT_SESSION is always set inside Windows Terminal
    if os.getenv("WT_SESSION") or os.getenv("WT_PROFILE_ID"):
        return ColorDepth.TRUECOLOR

    # Windows ConPTY fallback (older WT without WT_SESSION)
    if platform.system() == "Windows":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            handle = k32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if k32.GetConsoleMode(handle, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                # ConPTY / VT mode → TrueColor capable
                if mode.value & 0x0004:
                    return ColorDepth.TRUECOLOR
        except Exception:
            pass

    # VTE-based terminals (GNOME Terminal, Tilix, Xfce4-terminal…)
    vte_ver = _get_vte_version()
    if vte_ver is not None:
        if vte_ver >= _VTE_TRUECOLOR_MIN:
            return ColorDepth.TRUECOLOR
        else:
            return ColorDepth.COLOR_256

    # TERM_PROGRAM — common TrueColor-capable multiplexers / emulators
    term_program = os.getenv("TERM_PROGRAM", "").lower()
    if term_program in ("iterm.app", "hyper", "wezterm", "tabby",
                        "ghostty", "alacritty", "kitty", "rio"):
        return ColorDepth.TRUECOLOR

    # Kitty / Alacritty set TERM to "xterm-kitty" / "alacritty"
    term = os.getenv("TERM", "").lower()
    if "kitty" in term or "alacritty" in term or "wezterm" in term:
        return ColorDepth.TRUECOLOR

    if "256color" in term or "256colour" in term:
        return ColorDepth.COLOR_256

    # tmux / screen inherit from host, but at minimum support 256
    if term in ("xterm", "xterm-color", "screen", "tmux", "linux"):
        return ColorDepth.COLOR_256

    return ColorDepth.ANSI_8BIT

def _depth_supports_rgb() -> bool:
    return _detect_color_depth() in (ColorDepth.TRUECOLOR, ColorDepth.HDR_AWARE)

def _depth_supports_256() -> bool:
    return _detect_color_depth() in (ColorDepth.TRUECOLOR, ColorDepth.HDR_AWARE,
                                     ColorDepth.COLOR_256)

# ==============================================================================
#  COLOR MATH UTILITIES
# ==============================================================================

def _hex_to_rgb(hex_str: str) -> Tuple[int,int,int] | None:
    h = hex_str.lstrip('#')
    if len(h) == 3:
        h = ''.join(c*2 for c in h)
    if len(h) != 6:
        return None
    try:
        return int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    except ValueError:
        return None

def _rgb_to_hex(r:int, g:int, b:int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"

def _rgb_to_hsl(r:int, g:int, b:int) -> Tuple[float,float,float]:
    r_, g_, b_ = r/255, g/255, b/255
    cmax, cmin = max(r_,g_,b_), min(r_,g_,b_)
    delta = cmax - cmin
    l = (cmax+cmin)/2
    s = 0 if delta==0 else delta/(1-abs(2*l-1))
    if delta == 0:
        h = 0.0
    elif cmax == r_:
        h = 60*(((g_-b_)/delta)%6)
    elif cmax == g_:
        h = 60*((b_-r_)/delta+2)
    else:
        h = 60*((r_-g_)/delta+4)
    return round(h,1), round(s*100,1), round(l*100,1)

def _hsl_to_rgb(h:float, s:float, l:float) -> Tuple[int,int,int]:
    s_, l_ = s/100, l/100
    c = (1-abs(2*l_-1))*s_
    x = c*(1-abs((h/60)%2-1))
    m = l_-c/2
    if   h < 60:  r_,g_,b_ = c,x,0
    elif h < 120: r_,g_,b_ = x,c,0
    elif h < 180: r_,g_,b_ = 0,c,x
    elif h < 240: r_,g_,b_ = 0,x,c
    elif h < 300: r_,g_,b_ = x,0,c
    else:         r_,g_,b_ = c,0,x
    return int((r_+m)*255), int((g_+m)*255), int((b_+m)*255)

def _rgb_to_ansi256(r:int, g:int, b:int) -> int:
    """Najblizszy kolor w palecie 256."""
    if r == g == b:
        if r < 8:   return 16
        if r > 248: return 231
        return round((r-8)/247*24)+232
    ri = round(r/255*5)
    gi = round(g/255*5)
    bi = round(b/255*5)
    return 16 + 36*ri + 6*gi + bi

def _lerp_rgb(r1,g1,b1, r2,g2,b2, t:float) -> Tuple[int,int,int]:
    """Interpolacja liniowa RGB w przestrzeni sRGB."""
    return (int(r1+(r2-r1)*t), int(g1+(g2-g1)*t), int(b1+(b2-b1)*t))

def _luminance(r:int, g:int, b:int) -> float:
    def _lin(c): c/=255; return c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
    return 0.2126*_lin(r)+0.7152*_lin(g)+0.0722*_lin(b)

def _contrast_ratio(r1,g1,b1,r2,g2,b2) -> float:
    l1,l2 = _luminance(r1,g1,b1), _luminance(r2,g2,b2)
    if l1 < l2: l1,l2 = l2,l1
    return round((l1+0.05)/(l2+0.05),2)

# ==============================================================================
#  GAMMA-CORRECT (LINEAR) BLENDING
# ==============================================================================

def _srgb_to_linear(c: int) -> float:
    """Konwersja kanalu sRGB (0-255) do przestrzeni liniowej."""
    v = c / 255.0
    if v <= 0.04045:
        return v / 12.92
    return ((v + 0.055) / 1.055) ** 2.4

def _linear_to_srgb(v: float) -> int:
    """Konwersja kanalu liniowego z powrotem do sRGB (0-255)."""
    v = max(0.0, min(1.0, v))
    if v <= 0.0031308:
        out = v * 12.92
    else:
        out = 1.055 * (v ** (1.0 / 2.4)) - 0.055
    return int(round(out * 255))

def _lerp_linear(r1,g1,b1, r2,g2,b2, t:float) -> Tuple[int,int,int]:
    """
    Gamma-correct blending: mieszanie w przestrzeni liniowej.
    Daje perceptualnie poprawne wyniki bez efektu 'ciemnej smug' w srodku gradientu.
    """
    lr1, lg1, lb1 = _srgb_to_linear(r1), _srgb_to_linear(g1), _srgb_to_linear(b1)
    lr2, lg2, lb2 = _srgb_to_linear(r2), _srgb_to_linear(g2), _srgb_to_linear(b2)
    lrm = lr1 + (lr2 - lr1) * t
    lgm = lg1 + (lg2 - lg1) * t
    lbm = lb1 + (lb2 - lb1) * t
    return (_linear_to_srgb(lrm), _linear_to_srgb(lgm), _linear_to_srgb(lbm))

# ==============================================================================
#  OKLCH COLOR SPACE
# ==============================================================================
# OKLCH = Lightness, Chroma, Hue w przestrzeni perceptualnie jednorodnej OK Lab.
# Interpolacja gradientow w OKLCH daje bardziej rownomierne przejscia niz sRGB.
#
# Pipeline: sRGB -> Linear sRGB -> XYZ D65 -> OKLab -> OKLCH
# Reference: https://bottosson.github.io/posts/oklab/

def _rgb_to_oklab(r:int, g:int, b:int) -> Tuple[float,float,float]:
    """sRGB -> OKLab (L, a, b)."""
    # sRGB -> linear
    lr = _srgb_to_linear(r)
    lg = _srgb_to_linear(g)
    lb = _srgb_to_linear(b)

    # Linear sRGB -> LMS (Oklab's cone space matrix)
    l = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
    m = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
    s = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb

    # Cube root
    l_ = l ** (1/3) if l >= 0 else -((-l) ** (1/3))
    m_ = m ** (1/3) if m >= 0 else -((-m) ** (1/3))
    s_ = s ** (1/3) if s >= 0 else -((-s) ** (1/3))

    # LMS' -> OKLab
    L =  0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a =  1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_ = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, a, b_

def _oklab_to_rgb(L:float, a:float, b:float) -> Tuple[int,int,int]:
    """OKLab -> sRGB (clipped to 0-255)."""
    # OKLab -> LMS'
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    # LMS' -> LMS (cube)
    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3

    # LMS -> Linear sRGB
    lr =  4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    lb_ = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    return (_linear_to_srgb(lr), _linear_to_srgb(lg), _linear_to_srgb(lb_))

def _rgb_to_oklch(r:int, g:int, b:int) -> Tuple[float,float,float]:
    """sRGB -> OKLCH (L, C, H)."""
    L, a, b_ = _rgb_to_oklab(r, g, b)
    C = math.sqrt(a*a + b_*b_)
    H = math.degrees(math.atan2(b_, a)) % 360
    return round(L, 4), round(C, 4), round(H, 2)

def _oklch_to_rgb(L:float, C:float, H:float) -> Tuple[int,int,int]:
    """OKLCH -> sRGB."""
    H_rad = math.radians(H)
    a = C * math.cos(H_rad)
    b = C * math.sin(H_rad)
    return _oklab_to_rgb(L, a, b)

def _lerp_oklch(r1,g1,b1, r2,g2,b2, t:float) -> Tuple[int,int,int]:
    """
    Perceptualnie jednorodna interpolacja gradientow przez OKLCH.
    Zapobiega szarej smudze w srodku gradientu (np. czerwony -> niebieski).
    Uzywa krotkiej sciezki dla odcienia (max 180 stopni).
    """
    L1, C1, H1 = _rgb_to_oklch(r1, g1, b1)
    L2, C2, H2 = _rgb_to_oklch(r2, g2, b2)

    # Krotka sciezka po kole barw
    dH = H2 - H1
    if dH > 180:  dH -= 360
    if dH < -180: dH += 360

    Lm = L1 + (L2 - L1) * t
    Cm = C1 + (C2 - C1) * t
    Hm = (H1 + dH * t) % 360

    return _oklch_to_rgb(Lm, Cm, Hm)

# ==============================================================================
#  NAMED COLORS REGISTRY
# ==============================================================================

_NAMED: Dict[str, Tuple[int,int,int]] = {
    # podstawowe
    "black":(0,0,0), "white":(255,255,255), "red":(255,0,0),
    "green":(0,128,0), "lime":(0,255,0), "blue":(0,0,255),
    "yellow":(255,255,0), "cyan":(0,255,255), "magenta":(255,0,255),
    # rozszerzone
    "orange":(255,165,0), "orangered":(255,69,0), "darkorange":(255,140,0),
    "gold":(255,215,0), "goldenrod":(218,165,32), "wheat":(245,222,179),
    "pink":(255,192,203), "hotpink":(255,105,180), "deeppink":(255,20,147),
    "crimson":(220,20,60), "firebrick":(178,34,34), "darkred":(139,0,0),
    "salmon":(250,128,114), "coral":(255,127,80), "tomato":(255,99,71),
    "lightcoral":(240,128,128), "indianred":(205,92,92),
    "darkgreen":(0,100,0), "forestgreen":(34,139,34), "seagreen":(46,139,87),
    "mediumseagreen":(60,179,113), "springgreen":(0,255,127),
    "lawngreen":(124,252,0), "chartreuse":(127,255,0), "greenyellow":(173,255,47),
    "olive":(128,128,0), "olivedrab":(107,142,35), "yellowgreen":(154,205,50),
    "darkblue":(0,0,139), "mediumblue":(0,0,205), "royalblue":(65,105,225),
    "cornflowerblue":(100,149,237), "dodgerblue":(30,144,255),
    "deepskyblue":(0,191,255), "skyblue":(135,206,235),
    "lightblue":(173,216,230), "powderblue":(176,224,230),
    "steelblue":(70,130,180), "cadetblue":(95,158,160),
    "navy":(0,0,128), "teal":(0,128,128),
    "purple":(128,0,128), "violet":(238,130,238), "plum":(221,160,221),
    "orchid":(218,112,214), "mediumorchid":(186,85,211),
    "mediumpurple":(147,112,219), "blueviolet":(138,43,226),
    "darkviolet":(148,0,211), "darkorchid":(153,50,204),
    "darkmagenta":(139,0,139), "indigo":(75,0,130), "slateblue":(106,90,205),
    "brown":(165,42,42), "saddlebrown":(139,69,19), "sienna":(160,82,45),
    "chocolate":(210,105,30), "peru":(205,133,63), "tan":(210,180,140),
    "maroon":(128,0,0), "rosybrown":(188,143,143),
    "silver":(192,192,192), "gray":(128,128,128), "darkgray":(169,169,169),
    "lightgray":(211,211,211), "gainsboro":(220,220,220), "dimgray":(105,105,105),
    "lavender":(230,230,250), "lavenderblush":(255,240,245),
    "mistyrose":(255,228,225), "snow":(255,250,250),
    "mintcream":(245,255,250), "honeydew":(240,255,240),
    "azure":(240,255,255), "aliceblue":(240,248,255),
    "peachpuff":(255,218,185), "moccasin":(255,228,181),
    "bisque":(255,228,196), "antiquewhite":(250,235,215),
    "linen":(250,240,230), "oldlace":(253,245,230),
    "beige":(245,245,220), "ivory":(255,255,240),
    "turquoise":(64,224,208), "mediumturquoise":(72,209,204),
    "darkturquoise":(0,206,209), "aquamarine":(127,255,212),
    # polsoft theme
    "psdark":(30,30,46), "psmid":(42,42,62), "psaccent":(100,149,237),
}

def _resolve_color(s: str) -> Tuple[int,int,int] | None:
    """Rozwiaz kolor z nazwy / #hex / rgb(r,g,b) / r,g,b / oklch(L,C,H). Zwraca (r,g,b) lub None."""
    s = s.strip()

    # oklch(L, C, H) — np. oklch(0.7, 0.15, 200)
    m = re.match(r'oklch\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)', s, re.I)
    if m:
        return _oklch_to_rgb(float(m[1]), float(m[2]), float(m[3]))

    # hex
    if s.startswith('#') or (len(s)==6 and all(c in '0123456789abcdefABCDEF' for c in s)):
        return _hex_to_rgb(s)

    # rgb(r,g,b)
    m = re.match(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', s, re.I)
    if m:
        return int(m[1]), int(m[2]), int(m[3])

    # r,g,b
    parts = s.split(',')
    if len(parts)==3:
        try:
            return tuple(int(p.strip()) for p in parts)
        except ValueError:
            pass

    # ansi256 index
    if re.fullmatch(r'\d+', s) and 0 <= int(s) <= 255:
        return None

    # nazwa
    return _NAMED.get(s.lower())

# ==============================================================================
#  THEMES
# ==============================================================================

_THEMES: Dict[str, Dict[str, Tuple[int,int,int]]] = {
    "dark": {
        "bg":      (30, 30, 46),
        "surface": (42, 42, 62),
        "fg":      (205, 214, 244),
        "primary": (137, 180, 250),
        "success": (166, 227, 161),
        "warning": (249, 226, 175),
        "error":   (243, 139, 168),
        "accent":  (203, 166, 247),
        "muted":   (108, 112, 134),
    },
    "light": {
        "bg":      (255, 255, 255),
        "surface": (242, 244, 248),
        "fg":      (30, 30, 46),
        "primary": (30, 100, 200),
        "success": (34, 139, 34),
        "warning": (200, 130, 0),
        "error":   (185, 28, 28),
        "accent":  (109, 40, 217),
        "muted":   (107, 114, 128),
    },
    "solarized": {
        "bg":      (0, 43, 54),
        "surface": (7, 54, 66),
        "fg":      (131, 148, 150),
        "primary": (38, 139, 210),
        "success": (133, 153, 0),
        "warning": (181, 137, 0),
        "error":   (220, 50, 47),
        "accent":  (108, 113, 196),
        "muted":   (88, 110, 117),
    },
    "dracula": {
        "bg":      (40, 42, 54),
        "surface": (68, 71, 90),
        "fg":      (248, 248, 242),
        "primary": (139, 233, 253),
        "success": (80, 250, 123),
        "warning": (241, 250, 140),
        "error":   (255, 85, 85),
        "accent":  (255, 121, 198),
        "muted":   (98, 114, 164),
    },
    "nord": {
        "bg":      (46, 52, 64),
        "surface": (59, 66, 82),
        "fg":      (236, 239, 244),
        "primary": (129, 161, 193),
        "success": (163, 190, 140),
        "warning": (235, 203, 139),
        "error":   (191, 97, 106),
        "accent":  (180, 142, 173),
        "muted":   (76, 86, 106),
    },
    "monokai": {
        "bg":      (39, 40, 34),
        "surface": (60, 63, 52),
        "fg":      (248, 248, 242),
        "primary": (102, 217, 239),
        "success": (166, 226, 46),
        "warning": (230, 219, 116),
        "error":   (249, 38, 114),
        "accent":  (174, 129, 255),
        "muted":   (117, 113, 94),
    },
    "polsoft": {
        "bg":      (30, 30, 46),
        "surface": (42, 42, 62),
        "fg":      (220, 220, 240),
        "primary": (100, 149, 237),
        "success": (152, 224, 152),
        "warning": (255, 213, 128),
        "error":   (255, 100, 100),
        "accent":  (180, 130, 255),
        "muted":   (110, 110, 140),
    },
}

_CURRENT_THEME = "dark"

# ==============================================================================
#  COLOR SCHEMES (UI / CSS-like)
# ==============================================================================

_SCHEMES: Dict[str, Dict] = {
    "default": {
        "desc": "Domyslny schemat TerminalX",
        "roles": {
            "header":  ("Naglowek",    (100,149,237), (30,30,46)),
            "success": ("Sukces",      (80,200,80),   (20,40,20)),
            "warning": ("Ostrzezenie", (240,180,0),   (50,40,0)),
            "error":   ("Blad",        (220,60,60),   (50,10,10)),
            "info":    ("Informacja",  (80,180,220),  (10,30,50)),
            "muted":   ("Przygaszony", (130,130,150), (30,30,46)),
            "code":    ("Kod",         (200,160,255), (35,30,50)),
        },
    },
    "pastel": {
        "desc": "Delikatne kolory pastelowe",
        "roles": {
            "header":  ("Naglowek",    (179,157,219), (250,245,255)),
            "success": ("Sukces",      (129,199,132), (241,248,233)),
            "warning": ("Ostrzezenie", (255,213,79),  (255,253,231)),
            "error":   ("Blad",        (229,115,115), (255,243,243)),
            "info":    ("Informacja",  (100,181,246), (227,242,253)),
            "muted":   ("Przygaszony", (158,158,158), (245,245,245)),
            "code":    ("Kod",         (149,117,205), (243,240,255)),
        },
    },
    "neon": {
        "desc": "Intensywne kolory neonowe",
        "roles": {
            "header":  ("Naglowek",    (0,255,255),   (0,0,30)),
            "success": ("Sukces",      (0,255,65),    (0,20,5)),
            "warning": ("Ostrzezenie", (255,210,0),   (30,25,0)),
            "error":   ("Blad",        (255,0,80),    (30,0,10)),
            "info":    ("Informacja",  (0,180,255),   (0,15,30)),
            "muted":   ("Przygaszony", (150,150,200), (10,10,30)),
            "code":    ("Kod",         (180,0,255),   (20,0,30)),
        },
    },
    "terminal": {
        "desc": "Klasyczny styl terminala lat 80.",
        "roles": {
            "header":  ("Naglowek",    (0,255,0),     (0,0,0)),
            "success": ("Sukces",      (0,200,0),     (0,0,0)),
            "warning": ("Ostrzezenie", (255,255,0),   (0,0,0)),
            "error":   ("Blad",        (255,0,0),     (0,0,0)),
            "info":    ("Informacja",  (0,255,255),   (0,0,0)),
            "muted":   ("Przygaszony", (100,100,100), (0,0,0)),
            "code":    ("Kod",         (255,165,0),   (0,0,0)),
        },
    },
    "github": {
        "desc": "Schemat inspirowany GitHubem",
        "roles": {
            "header":  ("Naglowek",    (36,41,47),    (255,255,255)),
            "success": ("Sukces",      (26,127,55),   (218,251,225)),
            "warning": ("Ostrzezenie", (154,103,0),   (255,248,197)),
            "error":   ("Blad",        (164,14,38),   (255,235,233)),
            "info":    ("Informacja",  (9,105,218),   (221,244,255)),
            "muted":   ("Przygaszony", (110,119,129), (246,248,250)),
            "code":    ("Kod",         (80,70,228),   (248,248,255)),
        },
    },
}

# ==============================================================================
#  TERMINALX MODULE-LEVEL TRANSLATOR (placeholder)
# ==============================================================================

def _colors_t(key: str, **kw) -> str:
    return key

# ==============================================================================
#  COMMAND IMPLEMENTATIONS
# ==============================================================================

# --- colors (menu) ------------------------------------------------------------

def _colors_command(args: List[str]) -> None:
    depth = _detect_color_depth()
    depth_color = {
        ColorDepth.ANSI_8BIT:  _RED,
        ColorDepth.COLOR_256:  _BYLW,
        ColorDepth.TRUECOLOR:  _BGRN,
        ColorDepth.HDR_AWARE:  _BCYN,
    }.get(depth, _WHT)

    _w(f"\n{BOLD}{_BCYN}  +============================================+{RST}\n")
    _w(f"{BOLD}{_BCYN}  |   #  Colors Module  v2.1.0                 |{RST}\n")
    _w(f"{BOLD}{_BCYN}  |      polsoft.ITS(TM) Group                 |{RST}\n")
    _w(f"{BOLD}{_BCYN}  +============================================+{RST}\n\n")

    rows = [
        (_colors_t("colors_row_system"),  platform.system()),
        (_colors_t("colors_row_color"),   f"{_BGRN}TAK{RST}" if _check_color_support() else f"{_RED}NIE{RST}"),
        (_colors_t("colors_row_depth"),   f"{depth_color}{depth}{RST}"),
        (_colors_t("colors_row_theme"),   f"{_BYLW}{_CURRENT_THEME}{RST}"),
        (_colors_t("colors_row_named"),   f"{_BCYN}{len(_NAMED)}{RST}"),
        (_colors_t("colors_row_themes"),  f"{_BCYN}{len(_THEMES)}{RST}"),
        (_colors_t("colors_row_schemes"), f"{_BCYN}{len(_SCHEMES)}{RST}"),
    ]
    for k, v in rows:
        _w(f"  {DIM}{_pad(k,18)}{RST}{v}\n")

    _w(f"\n  {_BYLW}" + _colors_t("colors_section_cmds") + f"{RST}\n")
    cmds = [
        ("palette",              _colors_t("colors_cmd_palette")),
        ("rainbow <tekst>",      _colors_t("colors_cmd_rainbow")),
        ("colorize <kol> <t>",   _colors_t("colors_cmd_colorize")),
        ("gradient <s> <e> <t>", _colors_t("colors_cmd_gradient")),
        ("theme [nazwa]",        _colors_t("colors_cmd_theme")),
        ("effects [tekst]",      _colors_t("colors_cmd_effects")),
        ("scheme [nazwa]",       _colors_t("colors_cmd_scheme")),
        ("converter <wart>",     _colors_t("colors_cmd_converter")),
        ("preview <kolor>",      _colors_t("colors_cmd_preview")),
        ("mix <kol1> <kol2>",    _colors_t("colors_cmd_mix")),
        ("strip <tekst>",        _colors_t("colors_cmd_strip")),
        ("hq",                   _colors_t("colors_cmd_hq")),
    ]
    for c, d in cmds:
        _w(f"  {_BYLW}{_pad(c,28)}{RST}{DIM}{d}{RST}\n")
    _w("\n")

# --- palette ------------------------------------------------------------------

def _palette_command(args: List[str]) -> None:
    show_256 = "--256" in args
    show_rgb  = "--rgb" in args

    _w(f"\n{BOLD}  ANSI-16 (standardowe kolory terminala){RST}\n")
    _w(f"  {'─'*52}\n")
    names16 = ["Black","Red","Green","Yellow","Blue","Magenta","Cyan","White"]
    codes16 = [_BLK,_RED,_GRN,_YLW,_BLU,_MGT,_CYN,_WHT]
    bright16= [_BBLK,_BRED,_BGRN,_BYLW,_BBLU,_BMGT,_BCYN,_BWHT]
    _w("  ")
    for c, name in zip(codes16, names16):
        _w(f"{_bgRGB(*_NAMED.get(name.lower(),(128,128,128)))}  {RST}")
    _w(f"  {DIM}dim{RST}\n  ")
    for c, name in zip(bright16, names16):
        _w(f"{_bgRGB(*(int(x*1.4) if x<182 else 255 for x in _NAMED.get(name.lower(),(200,200,200))))}  {RST}")
    _w(f"  {DIM}bright{RST}\n\n")
    for c, bc, name in zip(codes16, bright16, names16):
        _w(f"  {c}██{RST} {bc}██{RST}  {DIM}{name:<10}{RST}")
        if name in ("Yellow","White"):
            _w("\n  ")
    _w("\n\n")

    if show_256:
        _w(f"{BOLD}  Paleta 256 kolorow{RST}\n  {'─'*52}\n")
        _w(f"  {DIM}0-15 (ANSI-16):{RST}\n  ")
        for i in range(16):
            _w(f"{_fg256(i)}█{RST}")
            if i == 7: _w(" ")
        _w("\n\n")
        _w(f"  {DIM}16-231 (kostka 6x6x6):{RST}\n")
        for g_idx in range(6):
            _w("  ")
            for r_idx in range(6):
                for b_idx in range(6):
                    _w(f"{_fg256(16+36*r_idx+6*g_idx+b_idx)}█{RST}")
                _w(" ")
            _w("\n")
        _w("\n")
        _w(f"  {DIM}232-255 (skala szarosci):{RST}\n  ")
        for i in range(232, 256):
            _w(f"{_fg256(i)}█{RST}")
        _w("\n\n")

    if show_rgb:
        _w(f"{BOLD}  Wybrane kolory RGB (named colors){RST}\n  {'─'*52}\n")
        items = list(_NAMED.items())
        for i in range(0, min(60, len(items)), 4):
            row = items[i:i+4]
            for name, (r,g,b) in row:
                bar = f"{_fgRGB(r,g,b)}██{RST}"
                _w(f"  {bar} {_pad(name,16)}")
            _w("\n")
        _w(f"\n  {DIM}Lacznie {len(_NAMED)} named colors. Uzyj: preview <nazwa>{RST}\n\n")

    if not show_256 and not show_rgb:
        _w(f"  {DIM}Opcje: palette --256  (256-color)   palette --rgb  (named RGB){RST}\n\n")

# --- rainbow ------------------------------------------------------------------

def _rainbow_command(args: List[str]) -> None:
    if not args:
        _w(f"  {DIM}Uzycie: rainbow <tekst>{RST}\n")
        return
    text = " ".join(args)
    n = max(len(text), 1)
    result = []
    for i, ch in enumerate(text):
        h = (i / n) * 360
        r, g, b = _hsl_to_rgb(h, 100, 55)
        result.append(f"{_fgRGB(r,g,b)}{ch}")
    _w(f"\n  {''.join(result)}{RST}\n\n")

# --- colorize -----------------------------------------------------------------

def _colorize_command(args: List[str]) -> None:
    if not args:
        _w(f"  {DIM}Uzycie: colorize <kolor> [--bg <kolor2>] [--bold] <tekst>{RST}\n")
        return

    fmt = ""
    bg_code = ""
    fg_code = ""
    text_parts = []
    i = 0

    while i < len(args):
        a = args[i]
        if a == "--bold":    fmt += BOLD; i+=1
        elif a == "--dim":   fmt += DIM;  i+=1
        elif a == "--italic":  fmt += ITAL; i+=1
        elif a == "--underline": fmt += UNDR; i+=1
        elif a == "--blink":  fmt += BLNK; i+=1
        elif a == "--bg" and i+1 < len(args):
            rgb = _resolve_color(args[i+1])
            if rgb: bg_code = _bgRGB(*rgb)
            i+=2
        elif fg_code == "":
            rgb = _resolve_color(a)
            if rgb:
                fg_code = _fgRGB(*rgb)
            else:
                text_parts.append(a)
            i+=1
        else:
            text_parts.append(a); i+=1

    text = " ".join(text_parts) if text_parts else "Sample Text"
    colored = f"{fmt}{bg_code}{fg_code}{text}{RST}"
    _w(f"\n  {colored}\n\n")

# --- gradient -----------------------------------------------------------------

def _gradient_command(args: List[str]) -> None:
    """Uzycie: gradient <kolor_start> <kolor_end> <tekst>
    Flagi:
      --hsl    interpolacja przez HSL
      --oklch  perceptualnie jednorodna interpolacja OKLCH (wysoka jakosc)
      --linear interpolacja gamma-correct w przestrzeni liniowej
    """
    use_hsl    = "--hsl"    in args
    use_oklch  = "--oklch"  in args
    use_linear = "--linear" in args
    args = [a for a in args if a not in ("--hsl", "--oklch", "--linear")]

    if len(args) < 3:
        _w(f"  {DIM}Uzycie: gradient <start> <end> <tekst>  [--oklch | --hsl | --linear]{RST}\n")
        _w(f"  {DIM}  --oklch   perceptualnie jednorodna interpolacja (OKLCH){RST}\n")
        _w(f"  {DIM}  --linear  gamma-correct blending (przestrzen liniowa){RST}\n")
        _w(f"  {DIM}  --hsl     interpolacja przez HSL{RST}\n")
        _w(f"  {DIM}Przyklad: gradient red blue 'Hello World' --oklch{RST}\n\n")
        return

    c1 = _resolve_color(args[0])
    c2 = _resolve_color(args[1])
    if not c1 or not c2:
        _w(f"  {_RED}Nie rozpoznano kolorow: {args[0]} / {args[1]}{RST}\n\n")
        return

    text = " ".join(args[2:]) or "Gradient Text"
    n = max(len(text), 1)
    result = []
    r1,g1,b1 = c1
    r2,g2,b2 = c2

    if use_oklch:
        mode_label = f"{_BCYN}OKLCH{RST}"
        for i, ch in enumerate(text):
            t = i / (n-1) if n > 1 else 0
            r,g,b = _lerp_oklch(r1,g1,b1, r2,g2,b2, t)
            result.append(f"{_fgRGB(r,g,b)}{ch}")
    elif use_linear:
        mode_label = f"{_BYLW}Linear (gamma-correct){RST}"
        for i, ch in enumerate(text):
            t = i / (n-1) if n > 1 else 0
            r,g,b = _lerp_linear(r1,g1,b1, r2,g2,b2, t)
            result.append(f"{_fgRGB(r,g,b)}{ch}")
    elif use_hsl:
        mode_label = f"{_BMGT}HSL{RST}"
        h1_,s1_,l1_ = _rgb_to_hsl(r1,g1,b1)
        h2_,s2_,l2_ = _rgb_to_hsl(r2,g2,b2)
        dh = h2_ - h1_
        if dh > 180: dh -= 360
        if dh < -180: dh += 360
        for i, ch in enumerate(text):
            t = i / (n-1) if n > 1 else 0
            r,g,b = _hsl_to_rgb((h1_+dh*t)%360, s1_+(s2_-s1_)*t, l1_+(l2_-l1_)*t)
            result.append(f"{_fgRGB(r,g,b)}{ch}")
    else:
        mode_label = f"{DIM}sRGB{RST}"
        for i, ch in enumerate(text):
            t = i / (n-1) if n > 1 else 0
            r,g,b = _lerp_rgb(r1,g1,b1, r2,g2,b2, t)
            result.append(f"{_fgRGB(r,g,b)}{ch}")

    hex1, hex2 = _rgb_to_hex(*c1), _rgb_to_hex(*c2)
    _w(f"\n  {''.join(result)}{RST}\n")
    _w(f"  {DIM}{hex1} → {hex2}  ({n} znakow)  tryb: {RST}{mode_label}\n\n")

# --- theme --------------------------------------------------------------------

def _theme_command(args: List[str]) -> None:
    global _CURRENT_THEME

    if not args:
        _w(f"\n{BOLD}  Dostepne motywy:{RST}\n  {'─'*48}\n")
        for name, data in _THEMES.items():
            active = f" {_BGRN}[aktywny]{RST}" if name == _CURRENT_THEME else ""
            _w(f"\n  {_BYLW}{BOLD}{name}{RST}{active}\n")
            for role, rgb in data.items():
                bar = f"{_fgRGB(*rgb)}████{RST}"
                _w(f"    {bar} {DIM}{_pad(role,10)}{RST}  rgb{rgb}  {_rgb_to_hex(*rgb)}\n")
        _w(f"\n  {DIM}Uzycie: theme <nazwa>   np. theme dracula{RST}\n\n")
        return

    name = args[0].lower()
    if name not in _THEMES:
        _w(f"  {_RED}Nieznany motyw: {name}{RST}\n")
        _w(f"  {DIM}Dostepne: {', '.join(_THEMES)}{RST}\n\n")
        return

    _CURRENT_THEME = name
    theme = _THEMES[name]
    _w(f"\n  {_BGRN}[V]{RST} Motyw zmieniony na: {BOLD}{_BYLW}{name}{RST}\n\n")
    for role, rgb in theme.items():
        bar = f"{_fgRGB(*rgb)}████████{RST}"
        _w(f"  {bar}  {_pad(role,10)}  {_rgb_to_hex(*rgb)}  rgb{rgb}\n")
    _w("\n")

# --- effects ------------------------------------------------------------------

def _effects_command(args: List[str]) -> None:
    sample = " ".join(args) if args else "polsoft.ITS TerminalX"

    _w(f"\n{BOLD}  Efekty tekstowe ANSI:{RST}\n  {'─'*52}\n\n")

    effects = [
        ("bold",          BOLD,            "Pogrubiony"),
        ("dim",           DIM,             "Przygaszony"),
        ("italic",        ITAL,            "Kursywa"),
        ("underline",     UNDR,            "Podkreslony"),
        ("blink",         BLNK,            "Migajacy (terminale)"),
        ("reverse",       REV,             "Odwrocone kolory"),
        ("strikethrough", STRK,            "Przekreslony"),
        ("bold+underline",BOLD+UNDR,       "Bold + podkreslenie"),
        ("bold+italic",   BOLD+ITAL,       "Bold + kursywa"),
        ("dim+italic",    DIM+ITAL,        "Dim + kursywa"),
    ]
    for name, code, desc in effects:
        _w(f"  {_pad(_BYLW+name+RST, 30)}  {code}{sample}{RST}  {DIM}({desc}){RST}\n")

    _w(f"\n{BOLD}  Kolory + efekty:{RST}\n\n")
    combos = [
        (_BRED+BOLD,   "bright red + bold"),
        (_BGRN+UNDR,   "bright green + underline"),
        (_BYLW+STRK,   "yellow + strikethrough"),
        (_BCYN+ITAL,   "cyan + italic"),
        (_BMGT+BOLD+UNDR, "magenta + bold + underline"),
        (_fgRGB(255,165,0)+BOLD, "RGB orange + bold"),
        (_fgRGB(100,149,237)+ITAL, "cornflowerblue + italic"),
    ]
    for code, desc in combos:
        _w(f"  {code}{sample}{RST}  {DIM}({desc}){RST}\n")

    _w(f"\n  {DIM}Podaj tekst: effects <tekst>  np. effects 'Hello World'{RST}\n\n")

# --- scheme -------------------------------------------------------------------

def _scheme_command(args: List[str]) -> None:
    if not args:
        _w(f"\n{BOLD}  Dostepne schematy kolorow:{RST}\n  {'─'*52}\n\n")
        for name, data in _SCHEMES.items():
            _w(f"  {_BYLW}{BOLD}{_pad(name,12)}{RST}  {DIM}{data['desc']}{RST}\n")
            roles = data["roles"]
            samples = list(roles.items())[:3]
            for role, (label, fg, bg) in samples:
                swatch = f"{_fgRGB(*fg)}{_bgRGB(*bg)} {label} {RST}"
                _w(f"               {swatch}  ")
            _w("\n\n")
        _w(f"  {DIM}Uzycie: scheme <nazwa>   np. scheme neon{RST}\n\n")
        return

    name = args[0].lower()
    if name not in _SCHEMES:
        _w(f"  {_RED}Nieznany schemat: {name}{RST}\n")
        _w(f"  {DIM}Dostepne: {', '.join(_SCHEMES)}{RST}\n\n")
        return

    scheme = _SCHEMES[name]
    _w(f"\n{BOLD}  Schemat: {_BYLW}{name}{RST}  {DIM}{scheme['desc']}{RST}\n")
    _w(f"  {'─'*60}\n\n")

    for role, (label, fg, bg) in scheme["roles"].items():
        block   = f"{_fgRGB(*fg)}{_bgRGB(*bg)}  {_pad(label,14)}{RST}"
        fg_info = f"fg:{_rgb_to_hex(*fg)}  rgb{fg}"
        bg_info = f"bg:{_rgb_to_hex(*bg)}  rgb{bg}"
        cr      = _contrast_ratio(*fg, *bg)
        wcag    = "AAA" if cr >= 7 else ("AA" if cr >= 4.5 else ("A?" if cr >= 3 else "FAIL"))
        wcag_c  = _BGRN if wcag=="AAA" else (_BYLW if wcag in ("AA","A?") else _RED)
        _w(f"  {block}  {DIM}{_pad(fg_info,30)}{_pad(bg_info,30)}{RST}  kontrast: {cr:.1f}  {wcag_c}[{wcag}]{RST}\n")

    _w("\n")

# --- converter ----------------------------------------------------------------

def _converter_command(args: List[str]) -> None:
    if not args:
        _w(f"\n  {DIM}Uzycie: converter <kolor>{RST}\n")
        _w(f"  {DIM}Przyklady:{RST}\n")
        _w("    converter #FF6600\n")
        _w("    converter 255,102,0\n")
        _w("    converter orange\n")
        _w("    converter rgb(255,102,0)\n")
        _w("    converter oklch(0.7,0.15,50)\n")
        _w("    converter ansi256:208\n\n")
        return

    raw = " ".join(args)

    m = re.match(r'ansi256:(\d+)', raw, re.I)
    if m:
        n = int(m[1])
        if not 0 <= n <= 255:
            _w(f"  {_RED}Zakres ANSI256: 0-255{RST}\n\n"); return
        _w(f"\n  {_fg256(n)}████████{RST}  ANSI-256: {BOLD}{n}{RST}\n")
        _w(f"  {DIM}(Dla dokladnych wartosci RGB uzywana paleta terminala){RST}\n\n")
        return

    rgb = _resolve_color(raw)
    if not rgb:
        _w(f"  {_RED}Nie rozpoznano koloru: {raw!r}{RST}\n")
        _w(f"  {DIM}Uzyj: #hex / rgb(r,g,b) / r,g,b / oklch(L,C,H) / nazwa{RST}\n\n")
        return

    r, g, b = rgb
    if not all(0<=x<=255 for x in (r,g,b)):
        _w(f"  {_RED}Wartosci RGB poza zakresem (0-255){RST}\n\n"); return

    h, s, l       = _rgb_to_hsl(r, g, b)
    ok_L, ok_C, ok_H = _rgb_to_oklch(r, g, b)
    hex_str       = _rgb_to_hex(r, g, b)
    ansi256_n     = _rgb_to_ansi256(r, g, b)
    lum           = _luminance(r, g, b)
    cr_white      = _contrast_ratio(r,g,b, 255,255,255)
    cr_black      = _contrast_ratio(r,g,b, 0,0,0)
    fg_dark       = _contrast_ratio(0,0,0, r,g,b) > _contrast_ratio(255,255,255, r,g,b)
    fg_demo       = _fgRGB(0,0,0) if fg_dark else _fgRGB(255,255,255)

    _w(f"\n  {_fgRGB(r,g,b)}████████████{RST}  {_bgRGB(r,g,b)}{fg_demo}  {hex_str}  {RST}\n\n")

    rows = [
        ("HEX",        f"{hex_str}"),
        ("RGB",        f"rgb({r}, {g}, {b})"),
        ("HSL",        f"hsl({h}°, {s}%, {l}%)"),
        ("OKLCH",      f"oklch({ok_L:.4f}, {ok_C:.4f}, {ok_H:.1f}°)  {DIM}L={ok_L:.2%} C={ok_C:.4f} H={ok_H:.1f}°{RST}"),
        ("ANSI 256",   f"\x1b[38;5;{ansi256_n}m▐▌ {ansi256_n}{RST}   (\x1b[38;5;{ansi256_n}mpreview{RST})"),
        ("ANSI seq",   f"\\x1b[38;2;{r};{g};{b}m"),
        ("Luminancja", f"{lum:.4f}"),
        ("Kontrast/W", f"{cr_white:.2f}  {'WCAG AA ✓' if cr_white>=4.5 else 'ponizej AA'}"),
        ("Kontrast/B", f"{cr_black:.2f}  {'WCAG AA ✓' if cr_black>=4.5 else 'ponizej AA'}"),
    ]
    for k, v in rows:
        _w(f"  {_BCYN}{_pad(k,14)}{RST}{v}\n")

    hc = (h + 180) % 360
    rc, gc, bc = _hsl_to_rgb(hc, s, l)
    _w(f"\n  {DIM}Komplementarny:{RST}  {_fgRGB(rc,gc,bc)}████{RST}  {_rgb_to_hex(rc,gc,bc)}  hsl({hc}°,{s}%,{l}%)\n")

    ha1, ha2 = (h+30)%360, (h-30)%360
    ra1,ga1,ba1 = _hsl_to_rgb(ha1, s, l)
    ra2,ga2,ba2 = _hsl_to_rgb(ha2, s, l)
    _w(f"  {DIM}Analogiczne:  {RST}  {_fgRGB(ra1,ga1,ba1)}████{RST} {_rgb_to_hex(ra1,ga1,ba1)}  "
       f"{_fgRGB(ra2,ga2,ba2)}████{RST} {_rgb_to_hex(ra2,ga2,ba2)}\n\n")

# --- preview ------------------------------------------------------------------

def _preview_command(args: List[str]) -> None:
    if not args:
        _w(f"  {DIM}Uzycie: preview <kolor> [tekst]{RST}\n\n")
        return

    raw = args[0]
    sample = " ".join(args[1:]) if len(args)>1 else f"  {raw}  "

    rgb = _resolve_color(raw)
    if not rgb:
        _w(f"  {_RED}Nie rozpoznano koloru: {raw!r}{RST}\n\n")
        return

    r, g, b = rgb
    h, s, l = _rgb_to_hsl(r, g, b)

    bar_width = 40
    _w("\n  ")
    for i in range(bar_width):
        t = i / (bar_width-1)
        lr, lg, lb = _hsl_to_rgb(h, s, t*100)
        _w(f"{_bgRGB(lr,lg,lb)} {RST}")
    _w(f"  {DIM}lightness{RST}\n  ")

    for i in range(bar_width):
        t = i / (bar_width-1)
        sr, sg, sb = _hsl_to_rgb(h, t*100, l)
        _w(f"{_bgRGB(sr,sg,sb)} {RST}")
    _w(f"  {DIM}saturation{RST}\n\n")

    fg_demo = _fgRGB(0,0,0) if _luminance(r,g,b)>0.4 else _fgRGB(255,255,255)
    _w(f"  {_bgRGB(r,g,b)}{fg_demo}  {sample}  {RST}\n")
    _w(f"  {_fgRGB(r,g,b)}{'█'*30}{RST}\n\n")

    ok_L, ok_C, ok_H = _rgb_to_oklch(r, g, b)
    rows = [
        ("Kolor:",   f"{BOLD}{raw}{RST}"),
        ("HEX:",     _rgb_to_hex(r,g,b)),
        ("RGB:",     f"({r}, {g}, {b})"),
        ("HSL:",     f"({h}°, {s}%, {l}%)"),
        ("OKLCH:",   f"({ok_L:.4f}, {ok_C:.4f}, {ok_H:.1f}°)"),
        ("ANSI256:", str(_rgb_to_ansi256(r,g,b))),
    ]
    for k, v in rows:
        _w(f"  {_BCYN}{_pad(k,10)}{RST}{v}\n")
    _w("\n")

# --- mix ----------------------------------------------------------------------

def _mix_command(args: List[str]) -> None:
    """Uzycie: mix <kolor1> <kolor2> [procent] [--linear]
    --linear  mieszanie gamma-correct w przestrzeni liniowej
    """
    use_linear = "--linear" in args
    args = [a for a in args if a != "--linear"]

    if len(args) < 2:
        _w(f"  {DIM}Uzycie: mix <kolor1> <kolor2> [%] [--linear]{RST}\n")
        _w(f"  {DIM}  --linear  gamma-correct blending (unika ciemnej smugi){RST}\n")
        _w(f"  {DIM}Przyklad: mix red blue 30 --linear{RST}\n\n")
        return

    c1 = _resolve_color(args[0])
    c2 = _resolve_color(args[1])
    if not c1 or not c2:
        _w(f"  {_RED}Nie rozpoznano kolorow{RST}\n\n"); return

    try:
        pct = float(args[2]) if len(args)>2 else 50.0
        pct = max(0.0, min(100.0, pct))
    except ValueError:
        pct = 50.0

    t = pct / 100

    if use_linear:
        rm, gm, bm = _lerp_linear(*c1, *c2, t)
        mode_label = f"{_BYLW}linear (gamma-correct){RST}"
    else:
        rm, gm, bm = _lerp_rgb(*c1, *c2, t)
        mode_label = f"{DIM}sRGB{RST}"

    width = 40
    _w("\n  ")
    for i in range(width):
        ti = i / (width-1)
        if use_linear:
            rr, gg, bb = _lerp_linear(*c1, *c2, ti)
        else:
            rr, gg, bb = _lerp_rgb(*c1, *c2, ti)
        _w(f"{_bgRGB(rr,gg,bb)} {RST}")
    pos = int(pct/100*(width-1))
    _w("\n  " + " "*pos + "▲\n\n")

    _w(f"  {_fgRGB(*c1)}████{RST} {_rgb_to_hex(*c1)}  +  "
       f"{_fgRGB(*c2)}████{RST} {_rgb_to_hex(*c2)}\n\n")
    _w(f"  {_fgRGB(rm,gm,bm)}{'█'*8}{RST}  {BOLD}{_rgb_to_hex(rm,gm,bm)}{RST}  "
       f"rgb({rm},{gm},{bm})  {DIM}({pct:.0f}% drugiego)  tryb: {RST}{mode_label}\n\n")

# --- strip --------------------------------------------------------------------

def _strip_command(args: List[str]) -> None:
    if not args:
        _w(f"  {DIM}Uzycie: strip <tekst z ANSI>{RST}\n\n"); return
    text = " ".join(args)
    clean = _strip(text)
    _w(f"\n  Wejscie ({len(text)} bajtow):  {text}{RST}\n")
    _w(f"  Wyjscie ({len(clean)} bajtow):  {clean}\n\n")

# --- hq -----------------------------------------------------------------------

def _hq_command(args: List[str]) -> None:
    """
    Komenda diagnostyczna HQ (High Quality Color).
    Bez argumentow: pelna diagnostyka koloru + opis przestrzeni.
    Z argumentem: konwersja podanego koloru do OKLCH.

    Uzycie:
      hq                    — diagnostyka terminala
      hq <kolor>            — konwersja do OKLCH + porownanie gradientow
    """
    if args:
        _hq_convert(args)
        return

    _w(f"\n{BOLD}{_BCYN}  ╭──────────────────────────────────────────╮{RST}\n")
    _w(f"{BOLD}{_BCYN}  │   HQ Color Diagnostics  v2.1.0           │{RST}\n")
    _w(f"{BOLD}{_BCYN}  ╰──────────────────────────────────────────╯{RST}\n\n")

    # --- Detekcja glebokosci ---
    depth      = _detect_color_depth()
    colorterm  = os.getenv("COLORTERM", "—")
    term       = os.getenv("TERM", "—")
    term_prog  = os.getenv("TERM_PROGRAM", "—")
    vte_ver    = _get_vte_version()
    wt_session = bool(os.getenv("WT_SESSION"))
    conpty     = bool(os.getenv("WT_SESSION") or os.getenv("WT_PROFILE_ID"))

    depth_sym = {
        ColorDepth.ANSI_8BIT: f"{_RED}■{RST}",
        ColorDepth.COLOR_256:  f"{_BYLW}■{RST}",
        ColorDepth.TRUECOLOR:  f"{_BGRN}■{RST}",
        ColorDepth.HDR_AWARE:  f"{_BCYN}■{RST}",
    }.get(depth, "?")

    _w(f"  {BOLD}Detekcja glebokosci koloru:{RST}\n")
    _w(f"  {'─'*50}\n")

    rows = [
        ("$COLORTERM",     colorterm),
        ("$TERM",          term),
        ("$TERM_PROGRAM",  term_prog),
        ("VTE_VERSION",    str(vte_ver) if vte_ver else "—"),
        ("Windows ConPTY", f"{_BGRN}TAK{RST}" if conpty else "NIE"),
        ("$WT_SESSION",    f"{_BGRN}TAK{RST}" if wt_session else "NIE"),
    ]
    for k, v in rows:
        _w(f"  {DIM}{_pad(k,18)}{RST}{v}\n")

    _w(f"\n  {depth_sym} Wykryta glebokosc: {BOLD}{depth}{RST}\n\n")

    # Vizualizacja glebokosci
    _w(f"  {DIM}8-bit  {RST}")
    for i in [1,2,3,4,5,6,7]:
        _w(f"{_fg256(i)}█{RST}")
    _w(f"  {DIM}256-color  {RST}")
    for i in range(196, 214, 3):
        _w(f"{_fg256(i)}█{RST}")
    _w(f"  {DIM}24-bit  {RST}")
    for i in range(8):
        t = i / 7
        r = int(255*t); g = int(80*(1-t)+200*t); b = int(255*(1-t))
        _w(f"{_fgRGB(r,g,b)}█{RST}")
    _w("\n\n")

    # --- OKLCH demo ---
    _w(f"  {BOLD}Przestrzen OKLCH (perceptualnie jednorodna):{RST}\n")
    _w(f"  {'─'*50}\n")
    _w(f"  {DIM}Gradient czerwony → niebieski: 3 metody interpolacji{RST}\n\n")

    r1,g1,b1 = 220,50,50
    r2,g2,b2 = 50,80,220
    n = 36

    _w(f"  {DIM}sRGB     {RST}  ")
    for i in range(n):
        t = i/(n-1)
        r,g,b = _lerp_rgb(r1,g1,b1, r2,g2,b2, t)
        _w(f"{_bgRGB(r,g,b)} {RST}")
    _w(f"  {DIM}← szara smuga{RST}\n")

    _w(f"  {_BYLW}Linear   {RST}  ")
    for i in range(n):
        t = i/(n-1)
        r,g,b = _lerp_linear(r1,g1,b1, r2,g2,b2, t)
        _w(f"{_bgRGB(r,g,b)} {RST}")
    _w(f"  {DIM}← gamma-correct{RST}\n")

    _w(f"  {_BCYN}OKLCH    {RST}  ")
    for i in range(n):
        t = i/(n-1)
        r,g,b = _lerp_oklch(r1,g1,b1, r2,g2,b2, t)
        _w(f"{_bgRGB(r,g,b)} {RST}")
    _w(f"  {_BCYN}← perceptualnie jednorodny{RST}\n\n")

    # --- Opis przestrzeni ---
    _w(f"  {BOLD}Opis przestrzeni kolorow:{RST}\n")
    _w(f"  {'─'*50}\n")
    spaces = [
        ("sRGB",    "Standard, nieliniowa gamma 2.2. Interpolacja daje ciemne smugi."),
        ("Linear",  "Przestrzen liniowa (bez gamma). Gamma-correct blending."),
        ("HSL",     "Odcien/Nasycenie/Jasnosc. Interpolacja kreci sie po kole barw."),
        ("OKLab",   "Perceptualnie jednorodna przestrzen kartezjanska (Bjorn Ottosson)."),
        ("OKLCH",   "Polarny zapis OKLab: L=jasnosc C=chroma H=odcien. Najlepsza do gradientow."),
    ]
    for name, desc in spaces:
        _w(f"  {_BCYN}{_pad(name,10)}{RST}{DIM}{desc}{RST}\n")

    _w(f"\n  {DIM}Uzycie: hq <kolor>   np. hq orange   hq '#FF6600'{RST}\n\n")


def _hq_convert(args: List[str]) -> None:
    """Konwersja podanego koloru do OKLCH + porownanie gradientow."""
    raw = " ".join(args)
    rgb = _resolve_color(raw)
    if not rgb:
        _w(f"  {_RED}Nie rozpoznano koloru: {raw!r}{RST}\n")
        _w(f"  {DIM}Uzyj: #hex / rgb(r,g,b) / r,g,b / oklch(L,C,H) / nazwa{RST}\n\n")
        return

    r, g, b = rgb
    ok_L, ok_C, ok_H = _rgb_to_oklch(r, g, b)
    h, s, l           = _rgb_to_hsl(r, g, b)

    _w(f"\n  {_fgRGB(r,g,b)}{'█'*12}{RST}  {BOLD}{_rgb_to_hex(r,g,b)}{RST}  rgb({r},{g},{b})\n\n")

    rows = [
        ("HEX",    _rgb_to_hex(r,g,b)),
        ("RGB",    f"rgb({r}, {g}, {b})"),
        ("HSL",    f"hsl({h}°, {s}%, {l}%)"),
        ("OKLCH",  f"{_BCYN}oklch({ok_L:.4f}, {ok_C:.4f}, {ok_H:.1f}°){RST}"),
        ("L",      f"{ok_L:.4f}  {DIM}({ok_L:.1%} jasnosci){RST}"),
        ("C",      f"{ok_C:.4f}  {DIM}(chroma / nasycenie){RST}"),
        ("H",      f"{ok_H:.1f}°  {DIM}(odcien){RST}"),
    ]
    for k, v in rows:
        _w(f"  {_BCYN}{_pad(k,8)}{RST}{v}\n")

    # Gradient do bialego i do czarnego przez OKLCH
    _w(f"\n  {DIM}Gradient → white (OKLCH):{RST}\n  ")
    for i in range(32):
        t = i/31
        r2,g2,b2 = _lerp_oklch(r,g,b, 255,255,255, t)
        _w(f"{_bgRGB(r2,g2,b2)} {RST}")
    _w(f"\n  {DIM}Gradient → black (OKLCH):{RST}\n  ")
    for i in range(32):
        t = i/31
        r2,g2,b2 = _lerp_oklch(r,g,b, 0,0,0, t)
        _w(f"{_bgRGB(r2,g2,b2)} {RST}")
    _w(f"\n\n  {DIM}Uzyj w gradiencie: gradient <kolor1> <kolor2> <tekst> --oklch{RST}\n\n")

# ==============================================================================
#  SUPPORT HELPERS
# ==============================================================================

def _check_color_support() -> bool:
    if os.getenv('NO_COLOR'):    return False
    if os.getenv('FORCE_COLOR'): return True
    return _detect_color_depth() != ColorDepth.ANSI_8BIT

# ==============================================================================
#  COMPAT: TerminalColors / ColorPalette / ColorUtils (stary interfejs API)
# ==============================================================================

class TerminalColors:
    """Kompatybilnosc z poprzednia wersja modulu."""
    class ANSI:
        BLACK=_BLK;RED=_RED;GREEN=_GRN;YELLOW=_YLW;BLUE=_BLU
        MAGENTA=_MGT;CYAN=_CYN;WHITE=_WHT
        BRIGHT_BLACK=_BBLK;BRIGHT_RED=_BRED;BRIGHT_GREEN=_BGRN
        BRIGHT_YELLOW=_BYLW;BRIGHT_BLUE=_BBLU;BRIGHT_MAGENTA=_BMGT
        BRIGHT_CYAN=_BCYN;BRIGHT_WHITE=_BWHT
        BG_BLACK=_BGBLK;BG_RED=_BGRED;BG_GREEN=_BGGRN;BG_YELLOW=_BGYLW
        BG_BLUE=_BGBLU;BG_MAGENTA=_BGMGT;BG_CYAN=_BGCYN;BG_WHITE=_BGWHT
        BOLD=BOLD;DIM=DIM;ITALIC=ITAL;UNDERLINE=UNDR
        BLINK=BLNK;REVERSE=REV;HIDDEN=HIDD;STRIKETHROUGH=STRK;RESET=RST

    # Alias klasy ANSI pod prywatną nazwą (kompatybilność z older API)
    class _ColorANSI:
        """ANSI color codes — alias dla TerminalColors.ANSI (kompatybilność wsteczna)."""
        BLACK=_BLK; RED=_RED; GREEN=_GRN; YELLOW=_YLW; BLUE=_BLU
        MAGENTA=_MGT; CYAN=_CYN; WHITE=_WHT
        BRIGHT_BLACK=_BBLK; BRIGHT_RED=_BRED; BRIGHT_GREEN=_BGRN
        BRIGHT_YELLOW=_BYLW; BRIGHT_BLUE=_BBLU; BRIGHT_MAGENTA=_BMGT
        BRIGHT_CYAN=_BCYN; BRIGHT_WHITE=_BWHT
        BG_BLACK=_BGBLK; BG_RED=_BGRED; BG_GREEN=_BGGRN; BG_YELLOW=_BGYLW
        BG_BLUE=_BGBLU; BG_MAGENTA=_BGMGT; BG_CYAN=_BGCYN; BG_WHITE=_BGWHT
        BOLD=BOLD; DIM=DIM; ITALIC=ITAL; UNDERLINE=UNDR
        BLINK=BLNK; REVERSE=REV; HIDDEN=HIDD; STRIKETHROUGH=STRK; RESET=RST
        RESET_BOLD='\x1b[22m'; RESET_ITALIC='\x1b[23m'; RESET_UNDERLINE='\x1b[24m'
        RESET_BLINK='\x1b[25m'; RESET_REVERSE='\x1b[27m'; RESET_HIDDEN='\x1b[28m'
        RESET_STRIKETHROUGH='\x1b[29m'

    def __init__(self):
        self.system=platform.system(); self.supports_color=_check_color_support()
        self.is_windows=self.system=='Windows'; self.RESET=RST
        # Włącz VT processing na Windows (jeśli jeszcze nie włączone)
        if self.is_windows:
            self._init_windows_console()
        for attr in ('BLACK','RED','GREEN','YELLOW','BLUE','MAGENTA','CYAN','WHITE',
                     'BRIGHT_BLACK','BRIGHT_RED','BRIGHT_GREEN','BRIGHT_YELLOW',
                     'BRIGHT_BLUE','BRIGHT_MAGENTA','BRIGHT_CYAN','BRIGHT_WHITE'):
            setattr(self, attr, getattr(self.ANSI, attr))

    def _init_windows_console(self) -> None:
        """Włącz ANSI/VT processing w konsoli Windows (Windows 10+)."""
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            STD_OUTPUT_HANDLE = -11
            mode = wintypes.DWORD()
            handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        except Exception:
            pass  # Brak uprawnień lub stara wersja Windows — milczące pominiecie

    def get_256_color(self,n):  return _fg256(n) if 0<=n<=255 else RST
    def get_256_bg_color(self,n): return _bg256(n) if 0<=n<=255 else RST
    def get_rgb_color(self,r,g,b): return _fgRGB(r,g,b)
    def get_rgb_bg_color(self,r,g,b): return _bgRGB(r,g,b)
    def colorize(self,text,color,bg_color=None,formatting=None):
        if not self.supports_color: return text
        codes=''.join(filter(None,[color,bg_color,formatting]))
        return f"{codes}{text}{RST}" if codes else text
    def reset(self,text=""): return f"{RST}{text}{RST}" if text else RST
    def red(self,t):    return self.colorize(t,self.ANSI.RED)
    def green(self,t):  return self.colorize(t,self.ANSI.GREEN)
    def blue(self,t):   return self.colorize(t,self.ANSI.BLUE)
    def yellow(self,t): return self.colorize(t,self.ANSI.YELLOW)
    def cyan(self,t):   return self.colorize(t,self.ANSI.CYAN)
    def magenta(self,t):return self.colorize(t,self.ANSI.MAGENTA)
    def white(self,t):  return self.colorize(t,self.ANSI.WHITE)
    def bold(self,t):   return self.colorize(t,BOLD)
    def dim(self,t):    return self.colorize(t,DIM)
    def italic(self,t): return self.colorize(t,ITAL)
    def underline(self,t): return self.colorize(t,UNDR)
    def strikethrough(self,t): return self.colorize(t,STRK)
    def bright_red(self,t):    return self.colorize(t,self.ANSI.BRIGHT_RED)
    def bright_green(self,t):  return self.colorize(t,self.ANSI.BRIGHT_GREEN)
    def bright_blue(self,t):   return self.colorize(t,self.ANSI.BRIGHT_BLUE)
    def bright_yellow(self,t): return self.colorize(t,self.ANSI.BRIGHT_YELLOW)
    def bright_cyan(self,t):   return self.colorize(t,self.ANSI.BRIGHT_CYAN)
    def bright_magenta(self,t):return self.colorize(t,self.ANSI.BRIGHT_MAGENTA)
    def error(self,t):   return self.colorize(t,self.ANSI.BRIGHT_RED+BOLD)
    def success(self,t): return self.colorize(t,self.ANSI.BRIGHT_GREEN)
    def warning(self,t): return self.colorize(t,self.ANSI.YELLOW)
    def info(self,t):    return self.colorize(t,self.ANSI.CYAN)


class ColorPalette:
    def __init__(self, colors: TerminalColors):
        self.colors = colors
        for attr in ('BLACK','RED','GREEN','YELLOW','BLUE','MAGENTA','CYAN','WHITE',
                     'BRIGHT_BLACK','BRIGHT_RED','BRIGHT_GREEN','BRIGHT_YELLOW',
                     'BRIGHT_BLUE','BRIGHT_MAGENTA','BRIGHT_CYAN','BRIGHT_WHITE'):
            setattr(self, attr, getattr(colors.ANSI, attr))
        self.SYSTEM_COLORS = {n: _fg256(_rgb_to_ansi256(*rgb)) for n,rgb in _NAMED.items()}
        self.RGB_COLORS = {n: _fgRGB(*rgb) for n,rgb in _NAMED.items()}

    def get_color(self,name):     return self.SYSTEM_COLORS.get(name.lower(), RST)
    def get_rgb_color(self,name): return self.RGB_COLORS.get(name.lower(), RST)
    def get_all_colors(self):
        d={}; d.update(self.SYSTEM_COLORS); d.update(self.RGB_COLORS); return d


class ColorUtils:
    def __init__(self, colors: TerminalColors, palette: ColorPalette):
        self.colors=colors; self.palette=palette
    def rainbow_text(self,text):
        if not self.colors.supports_color: return text
        n=max(len(text),1); out=[]
        for i,ch in enumerate(text):
            r,g,b=_hsl_to_rgb((i/n)*360, 100, 55)
            out.append(f"{_fgRGB(r,g,b)}{ch}")
        return ''.join(out)+RST
    def gradient_text(self,text,start_color,end_color):
        if not self.colors.supports_color: return text
        out=[]
        for i,ch in enumerate(text):
            out.append(f"{start_color if i%2==0 else end_color}{ch}")
        return ''.join(out)+RST
    def show_color_palette(self): return "Uzyj komendy: palette"
    def oklch_gradient_text(self, text: str, start_rgb: Tuple[int,int,int],
                            end_rgb: Tuple[int,int,int]) -> str:
        """Gradient tekstu przez przestrzen OKLCH."""
        if not self.colors.supports_color: return text
        n = max(len(text),1)
        out = []
        for i, ch in enumerate(text):
            t = i / (n-1) if n > 1 else 0
            r,g,b = _lerp_oklch(*start_rgb, *end_rgb, t)
            out.append(f"{_fgRGB(r,g,b)}{ch}")
        return ''.join(out) + RST


# Global compat instances
terminal_colors = TerminalColors()
color_palette   = ColorPalette(terminal_colors)
color_utils     = ColorUtils(terminal_colors, color_palette)

# ==============================================================================
#  PYTERM MODULE INTERFACE
# ==============================================================================

def init(terminal) -> None:
    terminal.ok(f"[colors] v{METADATA['version']} zaladowany")

def teardown_module(terminal) -> None:
    pass

# ==============================================================================
#  CML_COMMANDS (legacy CML dispatcher)
# ==============================================================================

def _cml(fn):
    def wrapper(args, terminal):
        fn(args)
    return wrapper


# --- Jawne CML wrappers (cmd_*) — zgodne z nowym API CrossTerm ---------------
# Sygn.: (args: list, terminal) — pozwalają na future użycie terminal.t()

def _cml_wrap(fn):
    """Wrap PyTerm execute-style fn(args) → CML fn(args, terminal)."""
    def wrapper(args, terminal):
        result = fn(args)
        if result:
            _w(result + "\n")
    return wrapper

def cmd_colors(args, terminal):
    """Pokaż informacje o kolorach terminala."""
    _colors_command(args)

def cmd_palette(args, terminal):
    """Wyświetl paletę kolorów."""
    _palette_command(args)

def cmd_rainbow(args, terminal):
    """Generuj tekst rainbow."""
    _rainbow_command(args)

def cmd_colorize(args, terminal):
    """Koloruj tekst: colorize <kolor> <tekst>."""
    _colorize_command(args)

def cmd_gradient(args, terminal):
    """Generuj gradient kolorów: gradient <start> <end> <tekst>."""
    _gradient_command(args)

def cmd_theme(args, terminal):
    """Zarządzaj motywami kolorów."""
    _theme_command(args)

def cmd_effects(args, terminal):
    """Efekty kolorów (bold, dim, italic, underline...)."""
    _effects_command(args)

def cmd_scheme(args, terminal):
    """Schematy kolorów."""
    _scheme_command(args)

def cmd_converter(args, terminal):
    """Konwertuj między formatami kolorów (hex ↔ rgb ↔ ANSI)."""
    _converter_command(args)

def cmd_preview(args, terminal):
    """Podgląd koloru z przykładowym tekstem: preview <kolor> [tekst]."""
    _preview_command(args)

def cmd_clr(args, terminal):
    """Alias → colors (menu modułu)."""
    _colors_command(args)


# --- PyTerm ModuleManager interface ------------------------------------------

def list_commands() -> Dict[str, Dict[str, str]]:
    """Zwraca mapę komend rejestrowanych automatycznie przez ModuleManager."""
    group = "Colors & Themes"
    return {
        "colors":    {"category": group, "description": "Pokaż informacje o kolorach terminala"},
        "palette":   {"category": group, "description": "Wyświetl paletę kolorów"},
        "rainbow":   {"category": group, "description": "Generuj tekst rainbow"},
        "colorize":  {"category": group, "description": "Koloruj tekst"},
        "gradient":  {"category": group, "description": "Generuj gradient kolorów"},
        "theme":     {"category": group, "description": "Zarządzaj motywami kolorów"},
        "effects":   {"category": group, "description": "Efekty kolorów"},
        "scheme":    {"category": group, "description": "Schematy kolorów"},
        "converter": {"category": group, "description": "Konwertuj formaty kolorów"},
        "preview":   {"category": group, "description": "Podgląd kolorów"},
        "mix":       {"category": group, "description": "Mieszaj kolory"},
        "strip":     {"category": group, "description": "Usuń sekwencje ANSI z tekstu"},
        "hq":        {"category": group, "description": "High-quality color rendering"},
        "clr":       {"category": group, "description": "Alias → colors"},
    }


def execute(command: str, args: List[str]) -> Optional[str]:
    """Dispatcher wywoływany przez ModuleManager dla każdej komendy."""
    import io, sys as _sys2
    _command_map = {
        "colors":    _colors_command,
        "clr":       _colors_command,
        "palette":   _palette_command,
        "rainbow":   _rainbow_command,
        "colorize":  _colorize_command,
        "gradient":  _gradient_command,
        "theme":     _theme_command,
        "effects":   _effects_command,
        "scheme":    _scheme_command,
        "converter": _converter_command,
        "preview":   _preview_command,
        "mix":       _mix_command,
        "strip":     _strip_command,
        "hq":        _hq_command,
    }
    handler = _command_map.get(command)
    if handler:
        # Przechwytujemy stdout żeby zwrócić jako string (ModuleManager tego oczekuje)
        buf = io.StringIO()
        old_stdout = _sys2.stdout
        try:
            _sys2.stdout = buf
            handler(args)
        finally:
            _sys2.stdout = old_stdout
        output = buf.getvalue()
        return output if output else None
    return f"[colors] Nieznana komenda: {command}"


CML_COMMANDS = {
    "colors":    _cml(_colors_command),
    "clr":       _cml(_colors_command),
    "palette":   _cml(_palette_command),
    "rainbow":   _cml(_rainbow_command),
    "colorize":  _cml(_colorize_command),
    "gradient":  _cml(_gradient_command),
    "theme":     _cml(_theme_command),
    "effects":   _cml(_effects_command),
    "scheme":    _cml(_scheme_command),
    "converter": _cml(_converter_command),
    "preview":   _cml(_preview_command),
    "mix":       _cml(_mix_command),
    "strip":     _cml(_strip_command),
    "hq":        _cml(_hq_command),
}

def cml_menu():
    _colors_command([])

def on_load():
    pass

# ==============================================================================
#  TERMINALX MODULE INTERFACE  (setup / teardown)
# ==============================================================================

def setup(terminal):
    """Register color commands with TerminalX."""
    global _colors_t
    _colors_t = terminal.t

    _subs = {
        "palette":   (terminal.t("colors_cmd_palette"),   _palette_command),
        "rainbow":   (terminal.t("colors_cmd_rainbow"),   _rainbow_command),
        "colorize":  (terminal.t("colors_cmd_colorize"),  _colorize_command),
        "gradient":  (terminal.t("colors_cmd_gradient"),  _gradient_command),
        "theme":     (terminal.t("colors_cmd_theme"),     _theme_command),
        "effects":   (terminal.t("colors_cmd_effects"),   _effects_command),
        "scheme":    (terminal.t("colors_cmd_scheme"),    _scheme_command),
        "converter": (terminal.t("colors_cmd_converter"), _converter_command),
        "preview":   (terminal.t("colors_cmd_preview"),   _preview_command),
        "mix":       (terminal.t("colors_cmd_mix"),       _mix_command),
        "strip":     (terminal.t("colors_cmd_strip"),     _strip_command),
        "hq":        (terminal.t("colors_cmd_hq"),        _hq_command),
    }

    def color_cmd(args):  _colors_command(args)
    def colors_cmd(args):
        _w(f"\n{BOLD}{_BYLW}COLORS v2.1.0:{RST}\n")
        entries = [("color", _colors_t("colors_menu_module")),("colors", _colors_t("colors_menu_list"))] + \
                  [(n, desc) for n,(desc,_) in _subs.items()]
        for name, desc in entries:
            _w(f"  {_BCYN}{name:<14}{RST}{DIM}{desc}{RST}\n")
        _w("\n")

    terminal.register_command("color",  color_cmd,  description=terminal.t("cmd_color"),  category=terminal.t("cat_ecosystem"))
    terminal.register_command("colors", colors_cmd, description=terminal.t("cmd_colors"), category=terminal.t("cat_ecosystem"))

    def _make(fn):
        def h(args): fn(args)
        return h

    for cmd_name, (desc, fn) in _subs.items():
        terminal.register_command(cmd_name, _make(fn), description=desc, category=terminal.t("cat_ecosystem"))


def teardown(terminal):
    for cmd in ["color","colors","palette","rainbow","colorize","gradient",
                "theme","effects","scheme","converter","preview","mix","strip","hq"]:
        terminal.commands.pop(cmd, None)


# ==============================================================================
#  CONVENIENCE MODULE-LEVEL FUNCTIONS
# ==============================================================================

def colorize(text: str, color: str, bg_color: Optional[str] = None,
             formatting: Optional[str] = None) -> str:
    return terminal_colors.colorize(text, color, bg_color, formatting)

def rainbow(text: str) -> str:
    return color_utils.rainbow_text(text)

def show_palette() -> str:
    return "Uzyj komendy: palette"

def reset() -> str:
    return RST
