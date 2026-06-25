"""Shared constants and helpers for all TerminalX core modules.

Centralizuje stale ANSI, ROOT_DIR, pomocnicze funkcje I/O i regex
ktore byly powielone w kazdym module. Wszystkie moduly core importuja
stad zamiast definiowac lokalne kopie.

Author  : Sebastian Januchowski
Brand   : polsoft.ITS(TM) Group
"""

import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Sciezki
# ---------------------------------------------------------------------------

ROOT_DIR  = os.path.dirname(os.path.dirname(__file__))
CACHE_DIR = os.path.join(ROOT_DIR, ".cache")
TRASH_DIR = os.path.join(ROOT_DIR, ".trash")

# ---------------------------------------------------------------------------
# Platformy
# ---------------------------------------------------------------------------

IS_WIN = sys.platform == "win32"
IS_LIN = sys.platform.startswith("linux")
IS_MAC = sys.platform == "darwin"

# ---------------------------------------------------------------------------
# ANSI VT support detection
# ---------------------------------------------------------------------------

def _detect_ansi() -> bool:
    """Sprawdz czy terminal obsluguje sekwencje ANSI/VT escape codes.

    Na Windows: sprawdzamy czy stdout jest TTY ORAZ czy Virtual Terminal
    Processing jest wlaczone (Windows 10+). Jesli nie - wlaczamy je przez
    SetConsoleMode; jesli brak wsparcia (stary cmd.exe) - zwracamy False.
    Na POSIX: wystarczy sprawdzic czy stdout jest TTY i zmienna TERM nie
    wskazuje na terminal bez kolorow (dumb).
    """
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        # Piszemy do potoku lub pliku - ANSI bylby literalem; wylacz.
        # Wyjatki: FORCE_COLOR / NO_COLOR (de-facto standardy)
        if os.environ.get("FORCE_COLOR"):
            return True
        return False

    if os.environ.get("NO_COLOR"):
        return False

    if sys.platform == "win32":
        try:
            import ctypes
            import ctypes.wintypes
            kernel32 = ctypes.windll.kernel32
            # GetStdHandle(STD_OUTPUT_HANDLE = -11)
            h = kernel32.GetStdHandle(-11)
            mode = ctypes.wintypes.DWORD()
            if not kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                return False
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            if mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
                return True
            # Probuj wlaczyc VTP
            new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            return bool(kernel32.SetConsoleMode(h, new_mode))
        except Exception:
            return False
    else:
        return os.environ.get("TERM", "") != "dumb"


_ANSI_SUPPORTED: bool = _detect_ansi()

# ---------------------------------------------------------------------------
# ANSI escape codes (puste stringi gdy brak wsparcia VT)
# ---------------------------------------------------------------------------

if _ANSI_SUPPORTED:
    RST  = "\x1b[0m"
    BOLD = "\x1b[1m"
    DIM  = "\x1b[2m"
    YLW  = "\x1b[93m"   # bright yellow
    ORG  = "\x1b[33m"   # standard yellow / orange (używany przez defender, config)
    RED  = "\x1b[91m"
    GRN  = "\x1b[92m"
    CYN  = "\x1b[36m"
    BCYN = "\x1b[96m"
    MGT  = "\x1b[95m"
    BLU  = "\x1b[94m"
    WHT  = "\x1b[97m"
else:
    RST = BOLD = DIM = YLW = ORG = RED = GRN = CYN = BCYN = MGT = BLU = WHT = ""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ansi_re = re.compile(r'\x1b\[[0-9;]*[mA-Z]')


def _w(s: str) -> None:
    """Write string to stdout immediately (no trailing newline)."""
    sys.stdout.write(s)
    sys.stdout.flush()


def _strip(s: str) -> str:
    """Remove ANSI escape sequences from string."""
    return _ansi_re.sub('', s)


def _pad(s: str, w: int) -> str:
    """Pad string to visible width w (ignoring ANSI codes)."""
    return s + ' ' * max(0, w - len(_strip(s)))


def _atomic_write(path: str, data: object, *, makedirs: bool = False, fsync: bool = True) -> bool:
    """Zapisz *data* (serializowalne do JSON) atomicznie do *path*.

    Schemat: zapis do <path>.tmp → fsync → os.replace().
    os.replace() jest atomiczne na POSIX i Windows (w przeciwienstwie do
    os.rename(), ktore na Windows zawodzi jesli cel istnieje).

    Parametry
    ----------
    path     : docelowa sciezka do pliku JSON
    data     : obiekt serializowalny (dict / list)
    makedirs : jesli True, tworzy katalogi nadrzedne przed zapisem
    fsync    : jesli True, wywoluje os.fsync() przed replace (domyslnie True)

    Zwraca True przy sukcesie, False przy bledzie OSError.
    """
    tmp = path + ".tmp"
    try:
        if makedirs:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            if fsync:
                os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False
