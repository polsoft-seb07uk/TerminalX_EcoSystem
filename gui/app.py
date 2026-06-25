#!/usr/bin/env python3
"""TerminalX GUI — graficzna powłoka dla silnika TerminalX.

polsoft.ITS(TM) Group  *  Sebastian Januchowski

Uruchamianie:
    python gui/app.py          # z katalogu projektu (EcoSystem/)
    python -m gui.app          # alternatywnie

Wymagania:
    Python 3.10+  |  tkinter (wbudowany w standardową instalację Pythona)

Architektura:
    - TerminalXApp      : główne okno (Tk), pasek statusu, panel historii,
                          panel powiadomień
    - OutputRedirector  : przekierowanie stdout silnika → widget Text
    - BackgroundRunner  : wykonywanie komend w osobnym wątku (bez blokowania GUI)

Integracja z ekosystemem:
    - Kolory GUI pobierane z core.colors motyw 'polsoft' (źródło prawdy)
    - Parser ANSI obsługuje 38;2;R;G;B (truecolor) i 38;5;N (256-color)
      → dynamiczne tagi Tkinter generowane on-the-fly
    - Panel powiadomień parsuje notify bubbles z core.notify
    - Startup banner generowany przez core.ansi (gradient + box)
    - Tab-completion wyświetla core.ansi.columns()
    - Pasek statusu z mini sparkline (core.ansi.sparkline)
"""

import os
import sys
import re
import queue
import threading

# ---------------------------------------------------------------------------
# Upewnij się, że katalog projektu (EcoSystem/) jest na sys.path
# ---------------------------------------------------------------------------
_GUI_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_GUI_DIR)
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    sys.exit(
        "BŁĄD: moduł tkinter nie jest dostępny.\n"
        "Na Debianie/Ubuntu zainstaluj: sudo apt install python3-tk\n"
        "Na Windows/macOS tkinter jest wbudowany w standardową instalację Pythona."
    )

# ---------------------------------------------------------------------------
# Kolory z motywu 'polsoft' z core.colors — źródło prawdy dla GUI
# ---------------------------------------------------------------------------

def _load_polsoft_theme() -> dict:
    """Ładuje motyw 'polsoft' z core.colors; fallback do hardcoded."""
    try:
        from core.colors import _THEMES
        t = _THEMES.get("polsoft", {})
        def _hex(rgb): return "#{:02x}{:02x}{:02x}".format(*rgb)
        return {k: _hex(v) for k, v in t.items()}
    except Exception:
        return {}

_PS = _load_polsoft_theme()

def _c(role: str, fallback: str) -> str:
    return _PS.get(role, fallback)


# ---------------------------------------------------------------------------
# ANSI → Tkinter tag mapping
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r'\x1b\[([0-9;]*)m')

# Podstawowe tagi (stałe)
_CODE_TO_TAG: dict[str, str] = {
    "0":  "reset",
    "1":  "bold",
    "2":  "dim",
    "3":  "italic",
    "4":  "underline",
    "9":  "strike",
    "91": "bright_red",
    "92": "bright_green",
    "93": "bright_yellow",
    "94": "bright_blue",
    "95": "bright_magenta",
    "96": "bright_cyan",
    "97": "bright_white",
    "31": "red",
    "32": "green",
    "33": "yellow",
    "34": "blue",
    "35": "magenta",
    "36": "cyan",
    "37": "white",
    "90": "dark_gray",
}

# Cache dynamicznych tagów RGB/256 → nazwa tagu
_dynamic_tag_cache: dict[str, str] = {}
_dynamic_tag_counter = 0
_output_widget_ref = None   # ustawiany po zbudowaniu widgetu


def _ansi256_to_hex(n: int) -> str:
    """Konwertuje indeks palety ANSI-256 na kolor hex."""
    if n < 16:
        basic = [
            (0,0,0),(128,0,0),(0,128,0),(128,128,0),
            (0,0,128),(128,0,128),(0,128,128),(192,192,192),
            (128,128,128),(255,0,0),(0,255,0),(255,255,0),
            (0,0,255),(255,0,255),(0,255,255),(255,255,255),
        ]
        r, g, b = basic[n]
    elif n < 232:
        n -= 16
        b = n % 6; g = (n // 6) % 6; r = n // 36
        def cv(v): return 0 if v == 0 else 55 + v * 40
        r, g, b = cv(r), cv(g), cv(b)
    else:
        v = 8 + (n - 232) * 10
        r, g, b = v, v, v
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def _get_or_create_rgb_tag(widget: tk.Text, fg_hex: str | None,
                            bg_hex: str | None = None) -> str:
    """Zwraca nazwę tagu dla podanego fg/bg; tworzy go w widgecie jeśli nowy."""
    global _dynamic_tag_counter
    key = f"{fg_hex or ''}|{bg_hex or ''}"
    if key in _dynamic_tag_cache:
        return _dynamic_tag_cache[key]
    _dynamic_tag_counter += 1
    tag_name = f"dyn_{_dynamic_tag_counter}"
    cfg: dict = {}
    if fg_hex:
        cfg["foreground"] = fg_hex
    if bg_hex:
        cfg["background"] = bg_hex
    if cfg and widget:
        try:
            widget.tag_configure(tag_name, **cfg)
        except Exception:
            pass
    _dynamic_tag_cache[key] = tag_name
    return tag_name


def _parse_ansi(text: str, widget: tk.Text | None = None
               ) -> list[tuple[str, list[str]]]:
    """Parsuje tekst z sekwencjami ANSI → lista (fragment, [tagi]).

    Obsługuje:
      - 16-color codes (30-37, 90-97, bold, dim...)
      - 38;2;R;G;B  — truecolor RGB → dynamiczny tag Tkinter
      - 38;5;N      — 256-color → aproksymacja hex → dynamiczny tag
      - 48;2;R;G;B  — truecolor tło RGB
      - 48;5;N      — 256-color tło
    """
    result: list[tuple[str, list[str]]] = []
    active_tags: list[str] = []
    last_end = 0

    # Aktywny kolor dynamiczny (fg/bg) — osobny od active_tags aby
    # można było je łączyć ze stałymi tagami (bold etc.)
    active_dyn_fg: str | None = None
    active_dyn_bg: str | None = None

    def _flush_text(chunk: str) -> None:
        if not chunk:
            return
        tags = list(active_tags)
        if active_dyn_fg or active_dyn_bg:
            dyn = _get_or_create_rgb_tag(widget, active_dyn_fg, active_dyn_bg)
            tags.append(dyn)
        result.append((chunk, tags))

    for m in _ANSI_RE.finditer(text):
        if m.start() > last_end:
            _flush_text(text[last_end:m.start()])

        raw_codes = m.group(1)
        parts = raw_codes.split(";") if raw_codes else ["0"]
        i = 0
        while i < len(parts):
            code = parts[i]

            # — Extended color sequences —
            if code == "38" and i + 1 < len(parts):
                sub = parts[i + 1]
                if sub == "2" and i + 4 < len(parts):
                    # 38;2;R;G;B — truecolor fg
                    try:
                        r, g, b = int(parts[i+2]), int(parts[i+3]), int(parts[i+4])
                        active_dyn_fg = "#{:02x}{:02x}{:02x}".format(r, g, b)
                    except ValueError:
                        pass
                    i += 5; continue
                elif sub == "5" and i + 2 < len(parts):
                    # 38;5;N — 256-color fg
                    try:
                        active_dyn_fg = _ansi256_to_hex(int(parts[i+2]))
                    except (ValueError, IndexError):
                        pass
                    i += 3; continue

            elif code == "48" and i + 1 < len(parts):
                sub = parts[i + 1]
                if sub == "2" and i + 4 < len(parts):
                    # 48;2;R;G;B — truecolor bg
                    try:
                        r, g, b = int(parts[i+2]), int(parts[i+3]), int(parts[i+4])
                        active_dyn_bg = "#{:02x}{:02x}{:02x}".format(r, g, b)
                    except ValueError:
                        pass
                    i += 5; continue
                elif sub == "5" and i + 2 < len(parts):
                    # 48;5;N — 256-color bg
                    try:
                        active_dyn_bg = _ansi256_to_hex(int(parts[i+2]))
                    except (ValueError, IndexError):
                        pass
                    i += 3; continue

            # — Standard codes —
            tag = _CODE_TO_TAG.get(code)
            if tag == "reset":
                active_tags.clear()
                active_dyn_fg = None
                active_dyn_bg = None
            elif tag:
                if tag not in active_tags:
                    active_tags.append(tag)

            i += 1

        last_end = m.end()

    _flush_text(text[last_end:])
    return result


# ---------------------------------------------------------------------------
# Definicje tagów Tkinter (statyczne)
# ---------------------------------------------------------------------------

_FONT_MONO = ("Consolas", 11)

_TAG_CONFIG: dict[str, dict] = {
    "reset":          {},
    "bold":           {"font": ("Consolas", 11, "bold")},
    "dim":            {"foreground": _c("muted", "#6e6e8c")},
    "italic":         {"font": ("Consolas", 11, "italic")},
    "underline":      {"underline": True},
    "strike":         {"overstrike": True},
    "bright_red":     {"foreground": _c("error",   "#ff6464")},
    "bright_green":   {"foreground": _c("success", "#98e098")},
    "bright_yellow":  {"foreground": _c("warning", "#ffd580")},
    "bright_blue":    {"foreground": _c("primary", "#6495ed")},
    "bright_magenta": {"foreground": _c("accent",  "#b482ff")},
    "bright_cyan":    {"foreground": "#8be9fd"},
    "bright_white":   {"foreground": _c("fg",      "#dcdcf0")},
    "red":            {"foreground": _c("error",   "#ff6464")},
    "green":          {"foreground": _c("success", "#98e098")},
    "yellow":         {"foreground": _c("warning", "#ffd580")},
    "blue":           {"foreground": _c("primary", "#6495ed")},
    "magenta":        {"foreground": _c("accent",  "#b482ff")},
    "cyan":           {"foreground": "#8be9fd"},
    "white":          {"foreground": _c("fg",      "#dcdcf0")},
    "dark_gray":      {"foreground": _c("muted",   "#6e6e8c")},
    # specjalne
    "prompt":         {"foreground": _c("warning", "#ffd580"),
                       "font": ("Consolas", 11, "bold")},
    "input_echo":     {"foreground": _c("primary", "#6495ed")},
    "error_internal": {"foreground": _c("error",   "#ff6464"),
                       "font": ("Consolas", 11, "bold")},
    "notify_ok":      {"foreground": _c("success", "#98e098"),
                       "font": ("Consolas", 10, "bold")},
    "notify_warn":    {"foreground": _c("warning", "#ffd580"),
                       "font": ("Consolas", 10, "bold")},
    "notify_err":     {"foreground": _c("error",   "#ff6464"),
                       "font": ("Consolas", 10, "bold")},
    "notify_info":    {"foreground": _c("primary", "#6495ed"),
                       "font": ("Consolas", 10)},
    "notify_tip":     {"foreground": _c("accent",  "#b482ff"),
                       "font": ("Consolas", 10)},
    "banner":         {"foreground": _c("accent",  "#b482ff"),
                       "font": ("Consolas", 11, "bold")},
}


# ---------------------------------------------------------------------------
# EcoSystem banner — używa core.ansi (force_enable bo nie-TTY)
# ---------------------------------------------------------------------------

def _build_startup_banner() -> str:
    """Generuje startup banner używając core.ansi gradient + box."""
    try:
        from core import ansi as _ansi
        _ansi.force_enable(True)
        _ansi.force_truecolor(True)

        title = _ansi.gradient_multicolor(
            "  TerminalX  EcoSystem  ",
            [(100, 149, 237), (180, 130, 255), (152, 224, 152)],
        )
        sub = _ansi.gradient(
            "  polsoft.ITS™ Group  •  Sebastian Januchowski  ",
            (180, 130, 255), (100, 149, 237),
        )
        lines = [title, sub, _ansi.muted("  gui/app.py  v1.1.0")]
        return _ansi.box(lines, style="rounded",
                         color=_ansi.muted,
                         title_color=_ansi.primary) + "\n"
    except Exception:
        return "TerminalX EcoSystem  GUI v1.1.0\npolsoft.ITS™ Group\n"


# ---------------------------------------------------------------------------
# EcoSystem columns — używa core.ansi do tab-completion
# ---------------------------------------------------------------------------

def _format_completions(matches: list[str]) -> str:
    """Formatuje listę dopasowań tab przez core.ansi.columns()."""
    try:
        from core import ansi as _ansi
        _ansi.force_enable(True)
        return "\n" + _ansi.columns(
            [_ansi.cyan(m) for m in sorted(matches)],
            gap=3,
            width=78,
        ) + "\n"
    except Exception:
        return "\n  " + "  ".join(sorted(matches)) + "\n"


# ---------------------------------------------------------------------------
# EcoSystem sparkline — do paska statusu
# ---------------------------------------------------------------------------

class _SparklineTracker:
    """Śledzi ostatnie N wartości (CPU/mem) dla sparkline w statusie."""

    def __init__(self, maxlen: int = 20):
        self._data: list[float] = []
        self._maxlen = maxlen

    def push(self, val: float) -> None:
        self._data.append(val)
        if len(self._data) > self._maxlen:
            self._data.pop(0)

    def render(self, color_fn=None) -> str:
        if not self._data:
            return ""
        try:
            from core import ansi as _ansi
            _ansi.force_enable(True)
            return _ansi.sparkline(self._data, color_fn=color_fn or _ansi.primary)
        except Exception:
            return ""


_cpu_tracker = _SparklineTracker()
_mem_tracker = _SparklineTracker()


# ---------------------------------------------------------------------------
# OutputRedirector — przechwytuje stdout silnika
# ---------------------------------------------------------------------------

class OutputRedirector:
    """Przekierowuje sys.stdout na kolejkę wiadomości dla GUI.

    Nie dziedziczy z io.TextIOBase — w CPython 'encoding' i 'errors'
    są read-only properties klasy bazowej i nie można ich nadpisać
    w __init__ przez przypisanie, co powoduje AttributeError przy starcie.
    Zamiast tego implementujemy minimalny interfejs file-like wymagany
    przez sys.stdout oraz contextlib.redirect_stdout.
    """

    encoding = "utf-8"
    errors   = "replace"
    softspace = 0

    def __init__(self, msg_queue: queue.Queue):
        self._queue = msg_queue

    def write(self, text: str) -> int:
        if text:
            self._queue.put(("output", text))
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# BackgroundRunner — wykonuje komendy bez blokowania GUI
# ---------------------------------------------------------------------------

class BackgroundRunner:
    """Wrapper na terminal._run_line() uruchamiany w osobnym wątku."""

    def __init__(self, terminal, msg_queue: queue.Queue):
        self._terminal   = terminal
        self._queue      = msg_queue
        self._lock       = threading.Lock()
        self._redirector = OutputRedirector(msg_queue)

    def run(self, line: str) -> None:
        thread = threading.Thread(
            target=self._execute,
            args=(line,),
            daemon=True,
            name=f"tx-cmd-{line[:20]}",
        )
        thread.start()

    def _execute(self, line: str) -> None:
        with self._lock:
            self._queue.put(("busy", True))
            orig_stdout = sys.stdout
            sys.stdout  = self._redirector
            try:
                self._terminal._run_line(line)
            except SystemExit:
                self._queue.put(("exit", None))
            except Exception as exc:
                self._queue.put(("output", f"\x1b[91m[GUI] Błąd wewnętrzny: {exc}\x1b[0m\n"))
            finally:
                sys.stdout = orig_stdout
                self._queue.put(("busy", False))
                self._queue.put(("refresh_history", None))
                self._queue.put(("refresh_status", None))


# ---------------------------------------------------------------------------
# Główna aplikacja
# ---------------------------------------------------------------------------

class TerminalXApp(tk.Tk):
    """Główne okno GUI TerminalX.

    Układ:
        ┌─────────────────────────────────────────┐
        │  pasek menu (File / View / Help)        │
        ├────────────┬────────────────────────────┤
        │  historia  │   output (Text)            │
        │  (Listbox) │                            │
        │            ├────────────────────────────┤
        │            │   prompt + input           │
        ├────────────┴────────────────────────────┤
        │  panel powiadomień (notify bubbles)     │
        ├─────────────────────────────────────────┤
        │  status bar (lang | defender | sparkline│
        └─────────────────────────────────────────┘
    """

    _VERSION  = "1.1.0"
    _TITLE    = "TerminalX GUI"
    _FONT_MONO = ("Consolas", 11)
    _FONT_UI   = ("Segoe UI", 10)
    _POLL_MS   = 40     # polling kolejki
    _STATUS_MS = 3000   # odświeżanie sparkline

    # Kolory z motywu polsoft (źródło prawdy: core.colors)
    _BG        = _c("bg",      "#1e1e2e")
    _BG_PANEL  = _c("surface", "#2a2a3e")
    _BG_INPUT  = "#181825"
    _FG        = _c("fg",      "#dcdcf0")
    _FG_DIM    = _c("muted",   "#6e6e8c")
    _ACCENT    = _c("primary", "#6495ed")
    _ACCENT2   = _c("accent",  "#b482ff")
    _SUCCESS   = _c("success", "#98e098")
    _WARNING   = _c("warning", "#ffd580")
    _ERROR     = _c("error",   "#ff6464")
    _BORDER    = "#3a3a52"
    _SEL_BG    = "#3a3a52"

    def __init__(self):
        super().__init__()

        self._queue: queue.Queue = queue.Queue()
        self._terminal = None
        self._runner:  BackgroundRunner | None = None
        self._cmd_history_nav: int = 0
        self._busy    = False
        self._notify_visible = True

        self._build_ui()
        self._boot_engine()
        self._poll()
        self._schedule_status_update()

    # -----------------------------------------------------------------------
    # Budowa UI
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.title(self._TITLE)
        self.geometry("1150x720")
        self.minsize(700, 420)
        self.configure(bg=self._BG)

        self._build_menu()
        self._build_main_frame()
        self._build_notify_panel()
        self._build_status_bar()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self, bg=self._BG_PANEL, fg=self._FG,
                          activebackground=self._SEL_BG,
                          activeforeground=self._FG,
                          relief="flat", bd=0)
        self.config(menu=menubar)

        m_file = tk.Menu(menubar, tearoff=0, bg=self._BG_PANEL, fg=self._FG,
                         activebackground=self._SEL_BG, activeforeground=self._FG)
        m_file.add_command(label="Wyczyść ekran",  command=self._clear_output,
                           accelerator="Ctrl+L")
        m_file.add_separator()
        m_file.add_command(label="Wyjdź",          command=self._on_close,
                           accelerator="Ctrl+Q")
        menubar.add_cascade(label="Plik", menu=m_file)

        m_view = tk.Menu(menubar, tearoff=0, bg=self._BG_PANEL, fg=self._FG,
                         activebackground=self._SEL_BG, activeforeground=self._FG)
        self._show_history = tk.BooleanVar(value=True)
        self._show_notify  = tk.BooleanVar(value=True)
        m_view.add_checkbutton(label="Panel historii",
                               variable=self._show_history,
                               command=self._toggle_history_panel)
        m_view.add_checkbutton(label="Panel powiadomień",
                               variable=self._show_notify,
                               command=self._toggle_notify_panel)
        m_view.add_separator()
        m_view.add_command(label="Wyczyść powiadomienia",
                           command=self._clear_notify_panel)
        menubar.add_cascade(label="Widok", menu=m_view)

        m_help = tk.Menu(menubar, tearoff=0, bg=self._BG_PANEL, fg=self._FG,
                         activebackground=self._SEL_BG, activeforeground=self._FG)
        m_help.add_command(label="O programie", command=self._show_about)
        menubar.add_cascade(label="Pomoc", menu=m_help)

        self.bind_all("<Control-l>", lambda _e: self._clear_output())
        self.bind_all("<Control-q>", lambda _e: self._on_close())

    def _build_main_frame(self) -> None:
        main = tk.Frame(self, bg=self._BG)
        main.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # --- Panel historii ---
        self._hist_frame = tk.Frame(main, bg=self._BG_PANEL,
                                    highlightbackground=self._BORDER,
                                    highlightthickness=1)
        self._hist_frame.grid(row=0, column=0, sticky="nsew",
                              padx=(0, 4), pady=0)
        self._hist_frame.rowconfigure(1, weight=1)
        self._hist_frame.columnconfigure(0, weight=1)

        hist_lbl = tk.Label(self._hist_frame, text=" Historia",
                            bg=self._BG_PANEL, fg=self._ACCENT,
                            font=self._FONT_UI, anchor="w")
        hist_lbl.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))

        self._hist_listbox = tk.Listbox(
            self._hist_frame,
            bg=self._BG_PANEL, fg=self._FG,
            selectbackground=self._SEL_BG,
            selectforeground=self._FG,
            font=self._FONT_MONO,
            relief="flat", bd=0,
            width=26,
            activestyle="none",
            highlightthickness=0,
        )
        self._hist_listbox.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)
        self._hist_listbox.bind("<Double-Button-1>", self._hist_double_click)
        self._hist_listbox.bind("<Return>",          self._hist_double_click)

        hist_scroll = ttk.Scrollbar(self._hist_frame, orient="vertical",
                                    command=self._hist_listbox.yview)
        hist_scroll.grid(row=1, column=1, sticky="ns")
        self._hist_listbox.config(yscrollcommand=hist_scroll.set)

        self._style_scrollbar()

        # --- Prawa kolumna: output + input ---
        right = tk.Frame(main, bg=self._BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        # Output
        out_frame = tk.Frame(right, bg=self._BG,
                             highlightbackground=self._BORDER,
                             highlightthickness=1)
        out_frame.grid(row=0, column=0, sticky="nsew")
        out_frame.rowconfigure(0, weight=1)
        out_frame.columnconfigure(0, weight=1)

        self._output = tk.Text(
            out_frame,
            bg=self._BG, fg=self._FG,
            font=self._FONT_MONO,
            relief="flat", bd=0,
            wrap="word",
            state="disabled",
            cursor="arrow",
            insertbackground=self._FG,
            selectbackground=self._SEL_BG,
            highlightthickness=0,
            padx=8, pady=6,
        )
        self._output.grid(row=0, column=0, sticky="nsew")

        out_scroll = ttk.Scrollbar(out_frame, orient="vertical",
                                   command=self._output.yview)
        out_scroll.grid(row=0, column=1, sticky="ns")
        self._output.config(yscrollcommand=out_scroll.set)

        self._configure_text_tags()

        # Input bar
        inp_frame = tk.Frame(right, bg=self._BG_INPUT,
                             highlightbackground=self._BORDER,
                             highlightthickness=1)
        inp_frame.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        inp_frame.columnconfigure(1, weight=1)

        self._prompt_lbl = tk.Label(
            inp_frame, text=" > ",
            bg=self._BG_INPUT, fg=self._WARNING,
            font=("Consolas", 11, "bold"),
        )
        self._prompt_lbl.grid(row=0, column=0, padx=(4, 0))

        self._input_var = tk.StringVar()
        self._input_entry = tk.Entry(
            inp_frame,
            textvariable=self._input_var,
            bg=self._BG_INPUT, fg=self._FG,
            font=self._FONT_MONO,
            relief="flat", bd=0,
            insertbackground=self._FG,
            highlightthickness=0,
        )
        self._input_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        self._input_entry.bind("<Return>",   self._on_enter)
        self._input_entry.bind("<Up>",       self._hist_up)
        self._input_entry.bind("<Down>",     self._hist_down)
        self._input_entry.bind("<Tab>",      self._on_tab)
        self._input_entry.focus_set()

        self._busy_lbl = tk.Label(
            inp_frame, text="",
            bg=self._BG_INPUT, fg=self._WARNING,
            font=("Consolas", 11),
        )
        self._busy_lbl.grid(row=0, column=2, padx=(0, 6))

    def _build_notify_panel(self) -> None:
        """Panel powiadomień — renderuje notify bubbles z core.notify."""
        self._notify_frame = tk.Frame(self, bg=self._BG_PANEL,
                                      highlightbackground=self._BORDER,
                                      highlightthickness=1)
        self._notify_frame.pack(fill="x", side="bottom", pady=(2, 0))

        hdr = tk.Frame(self._notify_frame, bg=self._BG_PANEL)
        hdr.pack(fill="x")

        tk.Label(hdr, text=" ✦ Powiadomienia",
                 bg=self._BG_PANEL, fg=self._ACCENT2,
                 font=self._FONT_UI).pack(side="left", padx=6, pady=(2,0))

        tk.Button(hdr, text="✕", command=self._clear_notify_panel,
                  bg=self._BG_PANEL, fg=self._FG_DIM,
                  relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI", 9),
                  activebackground=self._BG_PANEL,
                  activeforeground=self._ERROR,
                  ).pack(side="right", padx=4, pady=(2,0))

        self._notify_text = tk.Text(
            self._notify_frame,
            bg=self._BG_PANEL, fg=self._FG,
            font=("Consolas", 10),
            relief="flat", bd=0,
            wrap="word",
            state="disabled",
            height=3,
            cursor="arrow",
            padx=8, pady=4,
            highlightthickness=0,
        )
        self._notify_text.pack(fill="x")
        self._configure_notify_tags()

    def _configure_notify_tags(self) -> None:
        for tag, cfg in _TAG_CONFIG.items():
            if tag.startswith("notify_"):
                self._notify_text.tag_configure(tag, **cfg)
        # dynamiczne tagi RGB też na notify_text
        self._notify_text.tag_configure("dim", foreground=self._FG_DIM)
        self._notify_text.tag_configure("bold", font=("Consolas", 10, "bold"))

    def _style_scrollbar(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar",
                        background=self._BG_PANEL,
                        troughcolor=self._BG,
                        arrowcolor=self._FG_DIM,
                        bordercolor=self._BG_PANEL,
                        relief="flat")

    def _configure_text_tags(self) -> None:
        global _output_widget_ref
        _output_widget_ref = self._output
        for tag, cfg in _TAG_CONFIG.items():
            kw = {"font": self._FONT_MONO}
            kw.update(cfg)
            self._output.tag_configure(tag, **kw)
        self._output.configure(fg=self._FG)

    def _build_status_bar(self) -> None:
        bar = tk.Frame(self, bg=self._BG_PANEL,
                       highlightbackground=self._BORDER,
                       highlightthickness=1)
        bar.pack(fill="x", side="bottom", pady=(2, 0))

        self._status_lang = tk.Label(bar, text="lang: pl",
                                     bg=self._BG_PANEL, fg=self._ACCENT,
                                     font=self._FONT_UI)
        self._status_lang.pack(side="left", padx=10, pady=2)

        tk.Label(bar, text="│", bg=self._BG_PANEL,
                 fg=self._BORDER).pack(side="left")

        self._status_defender = tk.Label(bar, text="defender: –",
                                         bg=self._BG_PANEL, fg=self._FG_DIM,
                                         font=self._FONT_UI)
        self._status_defender.pack(side="left", padx=10, pady=2)

        tk.Label(bar, text="│", bg=self._BG_PANEL,
                 fg=self._BORDER).pack(side="left")

        self._status_cmd = tk.Label(bar, text="",
                                    bg=self._BG_PANEL, fg=self._FG_DIM,
                                    font=self._FONT_UI)
        self._status_cmd.pack(side="left", padx=10, pady=2)

        # Sparkline CPU po prawej (renderowany jako label z Unicode chars)
        self._status_spark = tk.Label(bar, text="",
                                      bg=self._BG_PANEL, fg=self._ACCENT2,
                                      font=("Consolas", 10))
        self._status_spark.pack(side="right", padx=10, pady=2)

        tk.Label(bar, text="│", bg=self._BG_PANEL,
                 fg=self._BORDER).pack(side="right")

        tk.Label(bar,
                 text=f"polsoft.ITS™  TerminalX GUI v{self._VERSION}",
                 bg=self._BG_PANEL, fg=self._FG_DIM,
                 font=self._FONT_UI).pack(side="right", padx=10, pady=2)

    # -----------------------------------------------------------------------
    # Sparkline statusu — odświeżany co _STATUS_MS
    # -----------------------------------------------------------------------

    def _schedule_status_update(self) -> None:
        self._update_sparkline()
        self.after(self._STATUS_MS, self._schedule_status_update)

    def _update_sparkline(self) -> None:
        """Aktualizuje sparkline CPU w pasku statusu przez core.ansi."""
        try:
            import psutil  # dostępny w libs/pip/psutil
            cpu = psutil.cpu_percent(interval=None)
            _cpu_tracker.push(cpu)
        except Exception:
            try:
                # Brak psutil — generuj dummy
                import math, time
                val = 30 + 20 * math.sin(time.time() * 0.3)
                _cpu_tracker.push(val)
            except Exception:
                return

        spark_str = _cpu_tracker.render()
        # Konwersja ANSI sparkline (Unicode chars) → czysty tekst dla Label
        # (Label nie obsługuje ANSI; strip_ansi + wyświetl Unicode chars)
        try:
            from core.ansi import strip_ansi
            clean = strip_ansi(spark_str)
        except Exception:
            clean = spark_str
        self._status_spark.config(text=f"cpu {clean}")

    # -----------------------------------------------------------------------
    # Panel historii
    # -----------------------------------------------------------------------

    def _toggle_history_panel(self) -> None:
        if self._show_history.get():
            self._hist_frame.grid()
        else:
            self._hist_frame.grid_remove()

    def _toggle_notify_panel(self) -> None:
        if self._show_notify.get():
            self._notify_frame.pack(fill="x", side="bottom", pady=(2, 0),
                                    before=self._notify_frame.master.winfo_children()[0]
                                    if self._notify_frame.master.winfo_children() else None)
        else:
            self._notify_frame.pack_forget()

    def _clear_notify_panel(self) -> None:
        self._notify_text.configure(state="normal")
        self._notify_text.delete("1.0", "end")
        self._notify_text.configure(state="disabled")

    def _refresh_history(self) -> None:
        if self._terminal is None:
            return
        entries: list = getattr(self._terminal, "_history", [])
        self._hist_listbox.delete(0, "end")
        for entry in reversed(entries[-200:]):
            self._hist_listbox.insert("end", f" {entry}")

    def _hist_double_click(self, _event=None) -> None:
        sel = self._hist_listbox.curselection()
        if not sel:
            return
        text = self._hist_listbox.get(sel[0]).strip()
        self._input_var.set(text)
        self._input_entry.icursor("end")
        self._input_entry.focus_set()

    # -----------------------------------------------------------------------
    # Nawigacja historii
    # -----------------------------------------------------------------------

    def _hist_up(self, _event=None) -> str:
        if self._terminal is None:
            return "break"
        entries: list = getattr(self._terminal, "_history", [])
        if not entries:
            return "break"
        self._cmd_history_nav = min(self._cmd_history_nav + 1, len(entries))
        self._input_var.set(entries[-self._cmd_history_nav])
        self._input_entry.icursor("end")
        return "break"

    def _hist_down(self, _event=None) -> str:
        if self._terminal is None:
            return "break"
        entries: list = getattr(self._terminal, "_history", [])
        self._cmd_history_nav = max(self._cmd_history_nav - 1, 0)
        if self._cmd_history_nav == 0:
            self._input_var.set("")
        else:
            self._input_var.set(entries[-self._cmd_history_nav])
        self._input_entry.icursor("end")
        return "break"

    # -----------------------------------------------------------------------
    # Tab — używa core.ansi.columns() do wyświetlania dopasowań
    # -----------------------------------------------------------------------

    def _on_tab(self, _event=None) -> str:
        if self._terminal is None:
            return "break"
        current = self._input_var.get().strip()
        if not current:
            return "break"
        matches = [c for c in self._terminal.commands if c.startswith(current)]
        if len(matches) == 1:
            self._input_var.set(matches[0] + " ")
            self._input_entry.icursor("end")
        elif len(matches) > 1:
            # Użyj core.ansi.columns() zamiast prostego join
            formatted = _format_completions(matches)
            self._append_output(formatted)
        return "break"

    # -----------------------------------------------------------------------
    # Wprowadzanie komend
    # -----------------------------------------------------------------------

    def _on_enter(self, _event=None) -> None:
        if self._busy:
            return
        line = self._input_var.get().strip()
        if not line:
            return
        self._input_var.set("")
        self._cmd_history_nav = 0

        self._append_output(f" > {line}\n", tags=["input_echo"])
        self._status_cmd.config(text=f"cmd: {line[:60]}")

        if self._runner is None:
            self._append_output("[GUI] Silnik nie jest jeszcze gotowy.\n",
                                tags=["error_internal"])
            return

        self._runner.run(line)

    def _clear_output(self) -> None:
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.configure(state="disabled")

    # -----------------------------------------------------------------------
    # Wstawianie tekstu do output (z pełną obsługą ANSI RGB/256)
    # -----------------------------------------------------------------------

    def _append_output(self, text: str, tags: list[str] | None = None) -> None:
        self._output.configure(state="normal")
        if tags:
            self._output.insert("end", text, tags)
        else:
            segments = _parse_ansi(text, widget=self._output)
            for chunk, seg_tags in segments:
                if seg_tags:
                    self._output.insert("end", chunk, seg_tags)
                else:
                    self._output.insert("end", chunk)
        self._output.configure(state="disabled")
        self._output.see("end")

    # -----------------------------------------------------------------------
    # Wstawianie tekstu do panelu powiadomień
    # -----------------------------------------------------------------------

    def _append_notify(self, text: str) -> None:
        """Wstawia tekst notify bubble do panelu (z parsowaniem ANSI)."""
        self._notify_text.configure(state="normal")
        segments = _parse_ansi(text, widget=self._notify_text)
        for chunk, seg_tags in segments:
            # Dobierz tag notify_ jeśli pasuje do kontekstu ikony/koloru
            final_tags = list(seg_tags)
            if seg_tags:
                # Mapuj kolor ekosystemu na tag notify_*
                col_tag = self._guess_notify_tag(seg_tags)
                if col_tag:
                    final_tags = [col_tag] + [t for t in seg_tags
                                              if t not in ("bright_green","bright_red",
                                                           "bright_yellow","bright_cyan",
                                                           "bright_magenta")]
            if final_tags:
                self._notify_text.insert("end", chunk, final_tags)
            else:
                self._notify_text.insert("end", chunk)
        self._notify_text.configure(state="disabled")
        self._notify_text.see("end")

        # Auto-resize panelu (max 6 linii)
        lines = int(self._notify_text.index("end-1c").split(".")[0])
        self._notify_text.configure(height=min(max(2, lines), 6))

    @staticmethod
    def _guess_notify_tag(tags: list[str]) -> str | None:
        """Mapuje kolor ANSI bubble na tag notify_*."""
        mapping = {
            "bright_green": "notify_ok",
            "green":        "notify_ok",
            "bright_red":   "notify_err",
            "red":          "notify_err",
            "bright_yellow":"notify_warn",
            "yellow":       "notify_warn",
            "bright_cyan":  "notify_info",
            "cyan":         "notify_info",
            "bright_magenta":"notify_tip",
            "magenta":      "notify_tip",
        }
        for t in tags:
            if t in mapping:
                return mapping[t]
        return None

    # -----------------------------------------------------------------------
    # Polling kolejki wiadomości
    # -----------------------------------------------------------------------

    def _poll(self) -> None:
        try:
            while True:
                msg_type, payload = self._queue.get_nowait()
                if msg_type == "output":
                    # Sprawdź czy to bubble notify (zawiera ramkę Unicode ╭/╰)
                    if self._is_notify_bubble(payload):
                        self._append_notify(payload)
                    else:
                        self._append_output(payload)
                elif msg_type == "busy":
                    self._busy = payload
                    self._busy_lbl.config(text="  ⏳" if payload else "")
                    self._input_entry.config(
                        state="disabled" if payload else "normal"
                    )
                    if not payload:
                        self._input_entry.focus_set()
                elif msg_type == "refresh_history":
                    self._refresh_history()
                elif msg_type == "refresh_status":
                    self._refresh_status()
                elif msg_type == "exit":
                    self._on_close()
        except queue.Empty:
            pass
        finally:
            self.after(self._POLL_MS, self._poll)

    @staticmethod
    def _is_notify_bubble(text: str) -> bool:
        """Heurystyka: czy tekst to bubble z core.notify."""
        # notify renderuje ramki z ╭ ╰ lub ┌ └ i ikonami ✔ ✖ ⚠ ℹ ✦
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', text)
        has_frame = any(ch in stripped for ch in "╭╰┌└")
        has_icon  = any(ch in stripped for ch in "✔✖⚠ℹ✦")
        return has_frame and has_icon

    # -----------------------------------------------------------------------
    # Pasek statusu
    # -----------------------------------------------------------------------

    def _refresh_status(self) -> None:
        if self._terminal is None:
            return

        lang = getattr(self._terminal, "lang", "?")
        self._status_lang.config(text=f"lang: {lang}")

        try:
            from core import defender as _def_mod
            prot = _def_mod._state.get("protection", False)
            txt  = "defender: ✔ ON" if prot else "defender: ✖ OFF"
            col  = self._SUCCESS if prot else self._ERROR
        except Exception:
            txt = "defender: –"
            col = self._FG_DIM
        self._status_defender.config(text=txt, fg=col)

    # -----------------------------------------------------------------------
    # Bootstrap silnika TerminalX
    # -----------------------------------------------------------------------

    def _boot_engine(self) -> None:
        def _load():
            try:
                import shutil as _sh
                for _pkg in ("core", "lang"):
                    _cache = os.path.join(_PROJECT_DIR, _pkg, "__pycache__")
                    if os.path.isdir(_cache):
                        _sh.rmtree(_cache, ignore_errors=True)

                # Oznacz ten proces jako GUI – switch.py i inne moduły
                # mogą to sprawdzić przez os.environ["TERMINALX_GUI"].
                os.environ["TERMINALX_GUI"] = "1"

                from core import TerminalX
                from core import load_modules

                # Wymuś ANSI w silniku (OutputRedirector nie jest TTY)
                try:
                    from core import ansi as _ansi
                    _ansi.force_enable(True)
                    _ansi.force_truecolor(True)
                except Exception:
                    pass

                redirector = OutputRedirector(self._queue)
                orig = sys.stdout
                sys.stdout = redirector
                try:
                    terminal = TerminalX()
                    terminal.loaded_modules = load_modules(terminal)
                finally:
                    sys.stdout = orig

                self._terminal = terminal
                self._runner   = BackgroundRunner(terminal, self._queue)

                # Emituj startup banner przez core.ansi
                banner = _build_startup_banner()
                self._queue.put(("output", banner))

                self._queue.put(("refresh_history", None))
                self._queue.put(("refresh_status",  None))
                self._queue.put(("busy", False))

            except Exception as exc:
                self._queue.put((
                    "output",
                    f"\x1b[91m[GUI] Błąd ładowania silnika: {exc}\x1b[0m\n"
                ))
                self._queue.put(("busy", False))

        self._queue.put(("busy", True))
        t = threading.Thread(target=_load, daemon=True, name="tx-boot")
        t.start()

    # -----------------------------------------------------------------------
    # Zamykanie
    # -----------------------------------------------------------------------

    def _on_close(self) -> None:
        if self._terminal is not None:
            from core import unload_module
            for name in list(self._terminal.loaded_modules):
                try:
                    unload_module(name, self._terminal.loaded_modules, self._terminal)
                except Exception:
                    pass
        self.destroy()

    def _show_about(self) -> None:
        messagebox.showinfo(
            "O programie",
            f"TerminalX GUI  v{self._VERSION}\n\n"
            "polsoft.ITS™ Group\n"
            "Sebastian Januchowski\n\n"
            "Graficzna powłoka dla silnika TerminalX.\n"
            "Kolory: motyw 'polsoft' (core.colors)\n"
            "ANSI: truecolor RGB + 256-color (core.ansi)\n"
            "Notify: panel powiadomień (core.notify)\n\n"
            "Skróty: Ctrl+L = wyczyść  |  Ctrl+Q = wyjdź",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = TerminalXApp()
    app.mainloop()


if __name__ == "__main__":
    main()
