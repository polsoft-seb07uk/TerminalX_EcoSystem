"""Core package for TerminalX.

TerminalX and its plugin modules work as one integrated organism.
All modules placed in this package are discovered and loaded automatically.
Each module should expose `setup(terminal)` and may expose `teardown(terminal)`.
"""

import importlib
import os
import importlib.util
import pkgutil
import shlex
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from ._shared import IS_WIN, IS_LIN, IS_MAC
from .colors import TerminalColors
from .lang import load_saved_lang
from . import config

PACKAGE_NAME = __name__

# ---------------------------------------------------------------------------
# Kolejnosc ladowania modulow (dependency-aware).
# Moduly wymienione tu laduja sie PIERWSZE w podanej kolejnosci.
# Pozostale moduly (spoza listy) laduja sie alfabetycznie po nich.
# Moduly z prefixem '_' sa zawsze pomijane (infrastruktura, nie komendy).
# ---------------------------------------------------------------------------
_LOAD_ORDER_FIRST: list[str] = [
    # fundamenty - nie zaleza od innych modulow core
    "lang",       # i18n musi byc pierwsze
    "config",     # konfiguracja uzywana przez wiele modulow
    "ansi",       # rendering ANSI (uzywany przez wiele modulow do formatowania)
    "sha256",     # hash engine (uzywany przez defender, analyser, scripts)
    "runner",     # interpreter lookup (uzywany przez sandbox, scripts, analyser)
    "notify",     # powiadomienia (uzywane przez defender, task, pkg, docs, trash)
    # moduly wyzszego rzedu
    "debugger",   # logowanie eventow (opcjonalne, uzywane przez wiele modulow)
    "defender",   # bezpieczenstwo (uzywane przez sandbox, scripts)
    "trash",      # kosz (uzywany przez command, docs, vdrive)
    "vdrive",     # dyski wirtualne ISO/VHD (zalezny od sha256, defender, trash, notify)
    "history",    # historia komend
    "alias",      # aliasy komend
    "cache",      # cache (uzywany przez analyser, pkg)
    "search",     # wyszukiwanie
    "tools",      # narzedzia
    "scripts",    # skrypty (zalezny od runner, defender)
    "sandbox",    # sandbox (zalezny od runner, defender, notify)
    "analyser",   # analiza plikow (zalezny od sha256, runner, scripts, tools)
    "imgtools",   # obrazy
    "math_engine",# obliczenia matematyczne
    "task",       # zadania (zalezny od notify)
    "pkg",        # pakiety (zalezny od notify)
    "virtual_env",# wirtualne srodowisko bibliotek (zalezny od pkg, config, notify)
    "docs",       # dokumentacja (zalezny od trash, notify)
    "net_diag",   # diagnostyka sieci (IP, DNS, porty, routing — zastępuje net)
    "ssh",        # klient SSH/SFTP (wymaga: paramiko)
    "github",     # klient GitHub API (PAT login, repos, issues, gisty)
    "env",        # zmienne srodowiskowe
    "switch",     # przelaczniki trybow
    "syntax_highlight",  # podswietlanie skladni
    "command",    # komendy plikowe (zalezny od trash)
    "colors",     # narzedzia kolorow
    "help",       # pomoc
    "modmenu",    # menu modulow uzytkownika (/modules)
    "tests",      # testy wewnetrzne
    "monitor",    # monitor systemu (CPU, RAM, dysk, siec)
    "admin",      # system/core admin (sys fs net sec data math proc)
    "video_downloader",  # pobieranie wideo (yt-dlp)
    "ai",         # asystent AI (30+ modeli, presety, GUI chat) — po admin
]


def _t(terminal, k, **kwargs):
    """Translate key via terminal._t dict; fallback to key itself."""
    d = getattr(terminal, "_t", {})
    text = d.get(k, k)
    return text.format(**kwargs) if kwargs else text


def _safe_print(text: str) -> None:
    """Print text to stdout with Unicode-safe fallback for Windows cp1250/cp852.

    On terminals that cannot encode certain characters (e.g. Polish letters on
    Windows with charmap encoding) we re-encode with errors='replace' so that
    no UnicodeEncodeError is ever raised from internal messaging.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        safe = text.encode(enc, errors="replace").decode(enc)
        try:
            print(safe)
        except Exception:
            pass  # absolute last resort - swallow silently


def _build_load_order(discovered: list[str]) -> list[str]:
    """Zbuduj liste modulow w kolejnosci ladowania.

    Najpierw moduly z _LOAD_ORDER_FIRST (zachowujac kolejnosc listy),
    potem pozostale alfabetycznie. Moduly z prefixem '_' sa pomijane.
    """
    known_set = set(_LOAD_ORDER_FIRST)
    ordered = [m for m in _LOAD_ORDER_FIRST if m in set(discovered)]
    extras  = sorted(m for m in discovered if m not in known_set)
    return ordered + extras


# Moduły które MUSZĄ ładować się sekwencyjnie (mają zależności między setup())
# Reszta ładuje się równolegle przez ThreadPoolExecutor
_SEQUENTIAL_MODULES = {
    "lang", "config", "ansi", "sha256", "notify", "debugger",
    "defender", "runner", "cache", "alias", "history",
}

def _load_one_core(name, terminal, lock):
    """Importuje i konfiguruje jeden moduł core. Thread-safe przez lock."""
    try:
        module = importlib.import_module(f"{PACKAGE_NAME}.{name}")
        if hasattr(module, "setup"):
            with lock:
                module.setup(terminal)
            return name, module, None
        else:
            return name, None, "no_setup"
    except Exception as exc:
        return name, None, exc


def load_modules(terminal):
    """Load all modules from the core package dynamically.

    Strategia ładowania:
      1. Moduły z _SEQUENTIAL_MODULES i pierwsze z _LOAD_ORDER_FIRST
         ładują się sekwencyjnie (zachowanie zależności).
      2. Pozostałe moduły core ładują się równolegle (ThreadPoolExecutor).
      3. Moduły użytkownika (/modules) ładują się sekwencyjnie na końcu.
    """
    loaded = {}
    lock   = threading.Lock()
    package = importlib.import_module(PACKAGE_NAME)

    # Odkryj wszystkie moduly core (pomijajac te z prefixem '_')
    discovered = [
        name for _, name, _ in pkgutil.iter_modules(package.__path__)
        if not name.startswith("_")
    ]

    load_order = _build_load_order(discovered)

    # Podziel na sekwencyjne i równoległe
    sequential = [n for n in load_order if n in _SEQUENTIAL_MODULES]
    parallel   = [n for n in load_order if n not in _SEQUENTIAL_MODULES]

    # Faza 1 — sekwencyjne (fundamenty)
    for name in sequential:
        try:
            module = importlib.import_module(f"{PACKAGE_NAME}.{name}")
            if hasattr(module, "setup"):
                module.setup(terminal)
                loaded[name] = module
            else:
                _safe_print(terminal.colors.warning(
                    _t(terminal, "module_no_setup", name=name)
                ))
        except Exception as exc:
            _safe_print(terminal.colors.error(
                _t(terminal, "module_load_error", name=name, exc=exc)
            ))

    # Faza 2 — równoległe (niezależne moduły wyższego rzędu)
    if parallel:
        max_workers = min(len(parallel), os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=max_workers,
                                thread_name_prefix="tx-load") as pool:
            futures = {
                pool.submit(_load_one_core, name, terminal, lock): name
                for name in parallel
            }
            for fut in as_completed(futures):
                name, module, err = fut.result()
                if err == "no_setup":
                    with lock:
                        _safe_print(terminal.colors.warning(
                            _t(terminal, "module_no_setup", name=name)
                        ))
                elif err is not None:
                    with lock:
                        _safe_print(terminal.colors.error(
                            _t(terminal, "module_load_error", name=name, exc=err)
                        ))
                elif module is not None:
                    with lock:
                        loaded[name] = module

    # Faza 3 — moduły użytkownika z /modules (sekwencyjnie)
    root_dir    = os.path.dirname(os.path.dirname(__file__))
    modules_dir = os.path.join(root_dir, "modules")
    if os.path.isdir(modules_dir):
        for fname in sorted(os.listdir(modules_dir)):
            if fname.startswith("_"):
                continue

            # Plik .py
            if fname.endswith(".py"):
                mod_name = fname[:-3]
                mod_path = os.path.join(modules_dir, fname)
            # Folder-paczka (zawiera __init__.py)
            elif os.path.isdir(os.path.join(modules_dir, fname)):
                init_path = os.path.join(modules_dir, fname, "__init__.py")
                if not os.path.isfile(init_path):
                    continue
                mod_name = fname
                mod_path = init_path
            else:
                continue

            key = f"modules/{mod_name}"
            # Pomiń moduły które zostały przeniesione do core/ (uniknij duplikatów)
            if mod_name in loaded:
                continue
            try:
                spec   = importlib.util.spec_from_file_location(
                    f"_user_modules_{mod_name}", mod_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "setup"):
                    module.setup(terminal)
                    loaded[key] = module
                else:
                    _safe_print(terminal.colors.warning(
                        _t(terminal, "module_no_setup", name=key)
                    ))
            except Exception as exc:
                _safe_print(terminal.colors.error(
                    _t(terminal, "module_load_error", name=key, exc=exc)
                ))

    return loaded


def unload_module(name, loaded_modules, terminal):
    """Unload module cleanly if it provides teardown()."""
    module = loaded_modules.get(name)
    if not module:
        _safe_print(terminal.colors.warning(
            _t(terminal, "module_unknown", name=name)
        ))
        return
    if hasattr(module, "teardown"):
        try:
            module.teardown(terminal)
            _safe_print(terminal.colors.info(
                _t(terminal, "module_unloaded", name=name)
            ))
        except Exception as exc:
            _safe_print(terminal.colors.error(
                _t(terminal, "module_unload_error", name=name, exc=exc)
            ))
    loaded_modules.pop(name, None)


def _tokenize(line: str) -> list:
    """Split a line into tokens, honoring single/double quoted substrings.

    On Windows, posix=True causes shlex to treat backslash as an escape
    character, silently mangling paths like C:\\Users\\foo into C:Usersfoo.
    posix=False preserves backslashes; quotes are still stripped by shlex
    on all platforms when whitespace_split=True is combined with the
    default wordchars, so quoted multi-word args still work correctly.

    Falls back to a plain whitespace split if the line contains unbalanced
    quotes, so malformed input never crashes the REPL.
    """
    posix = not IS_WIN
    lexer = shlex.shlex(line, posix=posix)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
        # In non-posix mode shlex keeps surrounding quotes — strip them.
        if not posix:
            stripped = []
            for tok in tokens:
                if (len(tok) >= 2
                        and tok[0] == tok[-1]
                        and tok[0] in ('"', "'")):
                    tok = tok[1:-1]
                stripped.append(tok)
            return stripped
        return tokens
    except ValueError:
        return line.split()


# ── tools/ fallback ────────────────────────────────────────────────────────────

def _find_tool(name: str):
    """Szuka pliku narzędzia w katalogu tools/ pasującego do podanej nazwy.

    Dopasowuje:
      - dokładną nazwę (np. edit.exe)
      - nazwę bez rozszerzenia (np. edit  →  edit.exe)
      - wielkość liter ignorowana na Windows, uwzględniana na POSIX
    Zwraca pełną ścieżkę lub None.
    """
    from ._shared import ROOT_DIR, IS_WIN
    tools_dir = os.path.join(ROOT_DIR, "tools")
    if not os.path.isdir(tools_dir):
        return None

    try:
        entries = os.listdir(tools_dir)
    except OSError:
        return None

    name_lower = name.lower()

    # 1. dokładne dopasowanie
    for entry in entries:
        cmp = entry.lower() if IS_WIN else entry
        ref = name_lower   if IS_WIN else name
        if cmp == ref:
            full = os.path.join(tools_dir, entry)
            if os.path.isfile(full):
                return full

    # 2. dopasowanie bez rozszerzenia (edit → edit.exe, edit.bat, itp.)
    for entry in entries:
        stem = os.path.splitext(entry)[0]
        cmp  = stem.lower() if IS_WIN else stem
        ref  = name_lower   if IS_WIN else name
        if cmp == ref:
            full = os.path.join(tools_dir, entry)
            if os.path.isfile(full):
                return full

    return None


def _run_tool(path: str, args: list) -> None:
    """Uruchamia narzędzie z katalogu tools/ w osobnym, niezależnym procesie."""
    import stat as _stat
    import subprocess
    from ._shared import IS_WIN, GRN, RST, RED, DIM

    name = os.path.basename(path)

    # na POSIX upewnij się, że plik ma bit wykonywalności
    if not IS_WIN:
        try:
            mode = os.stat(path).st_mode
            if not (mode & _stat.S_IXUSR):
                os.chmod(path, mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)
        except OSError:
            pass

    _safe_print(f"  {GRN}[tools]{RST} {DIM}{name}{RST}" + (f" {' '.join(args)}" if args else ""))

    try:
        if IS_WIN:
            # Windows: własna konsola w osobnym oknie.
            # UWAGA: CREATE_NEW_CONSOLE i DETACHED_PROCESS wzajemnie się wykluczają
            # — ich kombinacja powoduje WinError 87. Używamy tylko CREATE_NEW_CONSOLE
            # (otwiera nowe okno terminala) + CREATE_NEW_PROCESS_GROUP (izoluje Ctrl+C).
            subprocess.Popen(
                [path] + list(args),
                creationflags=(
                    subprocess.CREATE_NEW_CONSOLE |
                    subprocess.CREATE_NEW_PROCESS_GROUP
                ),
                close_fds=True,
            )
        else:
            # POSIX: double-fork przez os.posix_spawn lub Popen z start_new_session
            subprocess.Popen(
                [path] + list(args),
                start_new_session=True,   # odłącza od grupy procesów i terminala
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
    except Exception as exc:
        _safe_print(f"  {RED}[tools] błąd uruchamiania {name}: {exc}{RST}")


# ── scripts/ fallback (.\nazwa) ────────────────────────────────────────────────

def _find_script(name: str):
    """Szuka skryptu w katalogu scripts/ pasującego do podanej nazwy.

    Zasada dopasowania:
      - jeśli podano rozszerzenie (np. test.bat) — szukaj dokładnego pliku
      - jeśli bez rozszerzenia (np. test):
          * jeśli istnieje dokładnie jeden plik o tej nazwie → uruchom go
          * jeśli jest więcej niż jeden (test.bat, test.ps1) → błąd: podaj rozszerzenie
    Zwraca pełną ścieżkę lub None (+ opcjonalnie komunikat błędu jako 2. element).
    """
    from ._shared import ROOT_DIR, IS_WIN
    scripts_dir = os.path.join(ROOT_DIR, "scripts")
    if not os.path.isdir(scripts_dir):
        return None, None

    try:
        entries = [e for e in os.listdir(scripts_dir)
                   if os.path.isfile(os.path.join(scripts_dir, e))]
    except OSError:
        return None, None

    has_ext = os.path.splitext(name)[1] != ""

    if has_ext:
        # szukaj dokładnego dopasowania
        for entry in entries:
            cmp = entry.lower() if IS_WIN else entry
            ref = name.lower()  if IS_WIN else name
            if cmp == ref:
                return os.path.join(scripts_dir, entry), None
        return None, None
    else:
        # bez rozszerzenia — zbierz wszystkie pasujące
        name_lower = name.lower()
        matches = []
        for entry in entries:
            stem = os.path.splitext(entry)[0]
            cmp  = stem.lower() if IS_WIN else stem
            ref  = name_lower   if IS_WIN else name
            if cmp == ref:
                matches.append(entry)

        if len(matches) == 1:
            return os.path.join(scripts_dir, matches[0]), None
        elif len(matches) > 1:
            from ._shared import YLW, RST, DIM
            opts = "  ".join(matches)
            return None, (f"  {YLW}[scripts]{RST} Niejednoznaczna nazwa — "
                          f"podaj rozszerzenie:{DIM}  {opts}{RST}")
        return None, None


def _run_script(path: str, args: list) -> None:
    """Uruchamia skrypt z katalogu scripts/ dobierając interpreter automatycznie.

    Priorytet resolucji:
      1. core/runner.py zarejestrowany w _integration (pełny _RUNTIMES z fallbackami)
      2. lokalna mapa _INTERPRETERS (fallback gdy runner niezaładowany)
    """
    import subprocess
    import shutil
    from ._shared import IS_WIN, GRN, RST, RED, DIM

    name = os.path.basename(path)
    ext  = os.path.splitext(name)[1].lower()

    _safe_print(f"  {GRN}[scripts]{RST} {DIM}{name}{RST}" + (f" {' '.join(args)}" if args else ""))

    # ── 1. spróbuj przez runner (_integration) ─────────────────────────────
    interp_path: str | None = None
    extra_args:  list       = []
    shellexec:   bool       = False   # .bat/.cmd/.html — os.startfile / xdg-open

    try:
        from . import _integration as _intg
        svc = _intg.get("runner")
        if svc and callable(svc.get("find_interpreter")):
            interp_path, extra_args = svc["find_interpreter"](ext)
    except Exception:
        pass

    # ── 2. fallback — lokalna mapa ─────────────────────────────────────────
    if interp_path is None:
        _FALLBACK: dict[str, list[str] | None] = {
            ".py":   [sys.executable],
            ".pyw":  [sys.executable],
            ".js":   ["node"],
            ".mjs":  ["node"],
            ".cjs":  ["node"],
            ".ts":   ["ts-node", "npx ts-node", "deno"],
            ".sh":   ["bash", "sh"],
            ".bash": ["bash"],
            ".zsh":  ["zsh"],
            ".fish": ["fish"],
            ".ps1":  ["pwsh", "powershell"],
            ".bat":  None,   # ShellExecute
            ".cmd":  None,
            ".html": None,
            ".htm":  None,
            ".php":  ["php"],
            ".rb":   ["ruby"],
            ".lua":  ["lua", "lua5.4", "lua5.3"],
            ".pl":   ["perl"],
            ".r":    ["Rscript"],
            ".R":    ["Rscript"],
        }
        candidates = _FALLBACK.get(ext, [])
        if candidates is None:
            shellexec = True
        elif candidates:
            # wybierz pierwszy dostępny w PATH
            for c in candidates:
                found = shutil.which(c.split()[0])   # npx ts-node → szukaj "npx"
                if found:
                    # jeśli kandydat to wieloczłonowy string (np. "npx ts-node")
                    parts = c.split()
                    interp_path = found
                    extra_args  = parts[1:] if len(parts) > 1 else []
                    break
        # [] (ext nieznany) → próbuj uruchomić bezpośrednio (interp_path=None, shellexec=False)

    # ── 3. ps1 extra_args (runner może nie dodawać -ExecutionPolicy) ───────
    if ext == ".ps1" and interp_path and not extra_args:
        extra_args = ["-ExecutionPolicy", "Bypass", "-File"]

    # ── 4. uruchomienie ────────────────────────────────────────────────────
    if shellexec:
        # .bat / .cmd / .html — ShellExecute (Windows) lub xdg-open (POSIX)
        try:
            if IS_WIN:
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            _safe_print(f"  {RED}[scripts] błąd: {exc}{RST}")
        return

    # rozszerzenia które WYMAGAJĄ interpretera — nie uruchamiaj bezpośrednio
    # wyjątek: .js bez node → fallback do przeglądarki (browser API)
    _NEEDS_INTERP = {
        ".js", ".mjs", ".cjs", ".ts", ".mts",
        ".py", ".pyw", ".rb", ".lua", ".pl",
        ".php", ".r", ".R", ".coffee",
    }

    if not interp_path and ext in _NEEDS_INTERP:
        if ext in (".js", ".mjs"):
            # brak node → otwórz w przeglądarce (browser API fallback)
            try:
                import webbrowser
                webbrowser.open(path)
            except Exception as exc:
                _safe_print(f"  {RED}[scripts] błąd: {exc}{RST}")
        else:
            _safe_print(f"  {RED}[scripts] brak interpretera dla {ext} — "
                        f"zainstaluj wymagane narzędzie{RST}")
        return

    if interp_path:
        cmd = [interp_path] + extra_args + [path] + list(args)
    else:
        cmd = [path] + list(args)

    try:
        if not IS_WIN:
            import stat as _stat
            mode = os.stat(path).st_mode
            if not (mode & _stat.S_IXUSR):
                os.chmod(path, mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)
        subprocess.Popen(cmd)
    except FileNotFoundError:
        _safe_print(f"  {RED}[scripts] brak interpretera dla {ext} — "
                    f"zainstaluj wymagane narzędzie{RST}")
    except Exception as exc:
        _safe_print(f"  {RED}[scripts] błąd uruchamiania {name}: {exc}{RST}")


class TerminalX:
    def __init__(self, lang: str = "pl"):
        self.commands       = {}
        self.loaded_modules = {}
        self.colors         = TerminalColors()

        # --- i18n bootstrap: saved lang overrides default ---
        self.lang = load_saved_lang() or lang
        try:
            mod    = importlib.import_module(f"lang.{self.lang}")
            self._t = mod.T
        except ModuleNotFoundError:
            self._t = {}

        # default translator shortcut (may be replaced by core/lang.py)
        self.t = lambda k, **kw: _t(self, k, **kw)

    def register_command(self, name, func, description="", category=None):
        if category is None:
            category = self.t("cat_general")
        self.commands[name] = {
            "func":        func,
            "description": description,
            "category":    category,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _dispatch(self, cmd: str, cmd_args: list,
                  input_lines: list | None = None) -> list | None:
        """Execute one command segment.

        If *input_lines* is not None the command runs in 'capture' mode:
        its stdout is intercepted and returned as a list of strings.
        Otherwise output goes straight to the terminal and None is returned.
        """
        import io, contextlib

        if cmd not in self.commands:
            # ── fallback: szukaj narzędzia w tools/ ───────────────────────
            _tool_path = _find_tool(cmd)
            if _tool_path is not None:
                _run_tool(_tool_path, cmd_args)
                return None
            _safe_print(self.colors.warning(_t(self, "unknown_command", cmd=cmd)))
            return None

        # inject piped input as first positional args when provided
        effective_args = list(cmd_args)
        if input_lines is not None:
            # prepend captured lines so commands like `search` can filter them
            effective_args = input_lines + effective_args

        if input_lines is None:
            # normal execution - output to stdout
            try:
                self.commands[cmd]["func"](effective_args)
            except Exception as exc:
                _safe_print(self.colors.error(_t(self, "cmd_exec_error", cmd=cmd, exc=exc)))
            return None
        else:
            # capture mode - redirect stdout
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    self.commands[cmd]["func"](effective_args)
            except Exception as exc:
                _safe_print(self.colors.error(_t(self, "cmd_exec_error", cmd=cmd, exc=exc)))
                return []
            return buf.getvalue().splitlines()

    def _run_line(self, line: str) -> None:
        """Parse and execute one input line, including pipe chains.

        Supports single/double-quoted arguments (e.g. `echo "a | b"`),
        which are kept intact and not treated as pipe separators.
        """
        # record in history if module loaded
        recorder = getattr(self, "_history_record", None)
        if recorder:
            recorder(line)

        # ── obsługa .\nazwa [args] — uruchom skrypt z katalogu scripts/ ──────
        stripped = line.lstrip()
        if stripped.startswith(".\\") or stripped.startswith("./"):
            raw_rest = stripped[2:]                        # odetnij .\
            parts    = _tokenize(raw_rest) if raw_rest.strip() else []
            name     = parts[0] if parts else ""
            s_args   = parts[1:] if len(parts) > 1 else []
            if name:
                path, err = _find_script(name)
                if err:
                    _safe_print(err)
                elif path:
                    _run_script(path, s_args)
                else:
                    from ._shared import RED, RST
                    _safe_print(f"  {RED}[scripts] nie znaleziono: {name}{RST}")
            return

        tokens = _tokenize(line)
        if not tokens:
            return

        # split tokens into pipe segments on standalone '|' tokens
        segments: list = [[]]
        for tok in tokens:
            if tok == "|":
                segments.append([])
            else:
                segments[-1].append(tok)
        segments = [s for s in segments if s]

        if len(segments) == 1:
            parts = segments[0]
            cmd   = parts[0]
            if cmd == "exit":
                raise SystemExit(0)
            self._dispatch(cmd, parts[1:])
            return

        # pipe chain: all but last run in capture mode
        captured: list | None = None
        for i, parts in enumerate(segments):
            cmd = parts[0]
            if cmd == "exit":
                raise SystemExit(0)
            is_last = (i == len(segments) - 1)
            if is_last:
                self._dispatch(cmd, parts[1:], input_lines=captured or [])
            else:
                captured = self._dispatch(cmd, parts[1:],
                                          input_lines=captured if i > 0 else None)
                if captured is None:
                    captured = []

    def run(self):
        self.loaded_modules = load_modules(self)

        if config.get("on_startup.clear", False):
            print("\x1b[2J\x1b[H", end="")

        try:
            from . import ansi as _ansi
            _ansi.force_enable(True)
            _ansi.force_truecolor(True)
            _title = _ansi.gradient_multicolor(
                "  TerminalX  EcoSystem 2026  •  polsoft.ITS™ Group  •  Sebastian Januchowski  ",
                [(100, 149, 237), (180, 130, 255), (152, 224, 152)],
            )
            _safe_print(_title)
        except Exception:
            _safe_print(self.colors.bold(self.colors.cyan(
                "TerminalX  EcoSystem 2026  •  polsoft.ITS™ Group  •  Sebastian Januchowski"
            )))
        print()

        if config.get("on_startup.show_help", False):
            help_cmd = self.commands.get("help")
            if help_cmd:
                help_cmd["func"]([])

        try:
            while True:
                symbol = config.get("prompt.symbol", "> ")
                code   = config.color_code(config.get("prompt.color", "yellow"))
                prompt = f"{code}{symbol}\x1b[0m" if code else symbol
                line = input(prompt).strip()
                if not line:
                    continue
                try:
                    self._run_line(line)
                except SystemExit:
                    break
        except (KeyboardInterrupt, EOFError):
            _safe_print(self.colors.info(_t(self, "shutdown")))
        finally:
            for name in list(self.loaded_modules):
                unload_module(name, self.loaded_modules, self)


__all__ = ["TerminalX", "load_modules", "unload_module", "_tokenize"]
