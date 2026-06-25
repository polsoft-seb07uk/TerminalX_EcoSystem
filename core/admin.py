#!/usr/bin/env python3
# crossterm: {"id": "01", "aliases": ["sys", "admin", "sa", "pkg"], "description": "System / Core Admin — sys fs net sec data math proc admin dev pkg", "version": "1.3", "author": "crossterm"}

"""
╔═══════════════════════════════════════════════════════════╗
║          SYSADMIN MODULE  —  CrossTerm v1.3               ║
║  System / Core Admin — niezależny od OS                   ║
╠═══════════════════════════════════════════════════════════╣
║  sys.info       — info o interpreterze, wersji, ścieżkach ║
║  sys.env        — zmienne środowiskowe (bez OS)           ║
║  sys.time       — aktualny timestamp                      ║
║  sys.uptime     — uptime terminala od startu aplikacji    ║
║  sys.clearcache — czyści cache terminala                  ║
║  sys.modules    — lista załadowanych modułów Pythona      ║
║  sys.mem        — użycie pamięci (tracemalloc)            ║
║  sys.cpuclock   — pomiar zegara CPU                       ║
╠═══════════════════════════════════════════════════════════╣
║  fs.ls    — lista plików w katalogu                       ║
║  fs.tree  — drzewo katalogów (rekurencyjnie)              ║
║  fs.read  — odczyt pliku                                  ║
║  fs.write — zapis pliku                                   ║
║  fs.append — dopisanie do pliku                           ║
║  fs.touch — tworzy pusty plik                             ║
║  fs.rm    — usuwa plik                                    ║
║  fs.mv    — przenosi plik                                 ║
║  fs.cp    — kopiuje plik                                  ║
║  fs.mkdir — tworzy katalog                                ║
║  fs.rmdir — usuwa katalog rekurencyjnie                   ║
║  fs.hash  — oblicza hash pliku (sha256)                   ║
║  fs.size  — rozmiar pliku                                 ║
║  fs.find  — wyszukuje pliki po nazwie                     ║
╠═══════════════════════════════════════════════════════════╣
║  net.http.get    — pobiera URL (HTTP GET)                 ║
║  net.http.head   — pobiera nagłówki HTTP                  ║
║  net.http.post   — wysyła żądanie HTTP POST               ║
║  net.dns.resolve — DNS lookup (socket.getaddrinfo)        ║
║  net.ip.public   — publiczne IP (HTTP)                    ║
║  net.ip.local    — lokalne IP (socket)                    ║
║  net.port.scan   — skanuje porty (TCP connect)            ║
║  net.ping        — TCP ping (czas połączenia)             ║
╠═══════════════════════════════════════════════════════════╣
║  sec.hash.sha1   — hash SHA-1 ciągu lub pliku             ║
║  sec.hash.sha256 — hash SHA-256 ciągu lub pliku           ║
║  sec.hash.md5    — hash MD5 ciągu lub pliku               ║
║  sec.encode.base64 — kodowanie Base64                     ║
║  sec.decode.base64 — dekodowanie Base64                   ║
║  sec.rand.bytes  — losowe bajty (hex)                     ║
║  sec.rand.int    — losowa liczba całkowita w zakresie     ║
║  sec.uuid        — generuje UUID4                         ║
╠═══════════════════════════════════════════════════════════╣
║  data.json.load  — parsuje JSON z pliku lub ciągu         ║
║  data.json.dump  — serializuje dane do JSON               ║
║  data.yaml.load  — parsuje YAML z pliku lub ciągu         ║
║  data.yaml.dump  — serializuje dane do YAML               ║
║  data.csv.read   — odczytuje plik CSV                     ║
║  data.csv.write  — zapisuje dane do pliku CSV             ║
║  data.regex.match — dopasowuje wzorzec regex              ║
║  data.regex.find — wyszukuje wszystkie dopasowania regex  ║
╠═══════════════════════════════════════════════════════════╣
║  math.eval         — bezpieczny evaluator wyrażeń (AST)   ║
║  math.rand         — losowe liczby (int/float/gauss)      ║
║  math.stats        — min/max/avg/median/stdev             ║
║  math.convert.bytes — konwersje B/KB/MB/GB/TB             ║
║  math.convert.time  — konwersje ms/s/min/h/d              ║
╠═══════════════════════════════════════════════════════════╣
║  proc.list   — lista aktywnych tasków terminala           ║
║  proc.kill   — zatrzymuje task terminala po ID            ║
║  proc.spawn  — uruchamia task async (wątek)               ║
║  proc.status — szczegółowy status tasku                   ║
║  term.clear  — czyści ekran terminala (ANSI)              ║
║  term.size   — rozmiar terminala (shutil / fallback)      ║
║  term.title  — ustawia tytuł okna (ANSI / fallback)       ║
║  term.color  — zmienia schemat kolorów ANSI               ║
╠═══════════════════════════════════════════════════════════╣
║  admin.users.list     — lista użytkowników terminala      ║
║  admin.users.add      — dodaje użytkownika                ║
║  admin.users.rm       — usuwa użytkownika                 ║
║  admin.roles.list     — lista dostępnych ról              ║
║  admin.roles.set      — ustawia rolę użytkownika          ║
║  admin.log            — logi systemowe terminala          ║
║  admin.log.clear      — czyści log systemowy              ║
║  admin.config.get     — pobiera konfigurację terminala    ║
║  admin.config.set     — ustawia konfigurację              ║
║  admin.update         — sprawdza aktualizacje modułów     ║
║  admin.plugins.list   — lista zainstalowanych pluginów    ║
║  admin.plugins.load   — ładuje plugin                     ║
║  admin.plugins.unload — wyładowuje plugin                 ║
╠═══════════════════════════════════════════════════════════╣
║  dev.trace      — stack trace bieżącego wątku             ║
║  dev.inspect    — introspekcja obiektu Pythona            ║
║  dev.benchmark  — mierzy czas wykonania wyrażenia         ║
║  dev.profile    — profilowanie kodu (cProfile)            ║
║  dev.reload     — przeładowuje moduł Pythona              ║
║  dev.sandbox    — izolowane wykonanie kodu                ║
╠═══════════════════════════════════════════════════════════╣
║  pkg.list    — lista zainstalowanych modułów CrossTerm    ║
║  pkg.install — instalacja modułu z URL lub pliku ZIP      ║
║  pkg.remove  — usuwa zainstalowany moduł                  ║
║  pkg.update  — aktualizuje moduł do najnowszej wersji     ║
║  pkg.info    — szczegółowe informacje o module            ║
╚═══════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import sys
import time
import tracemalloc
import importlib

# ── Czas startu modułu (proxy uptime terminala) ───────────────────────────────

_MODULE_START: float = time.monotonic()
_TRACEMALLOC_RUNNING: bool = False


# ── ANSI helpers (lokalne, niezależne od głównego modułu) ─────────────────────

class _C:
    RESET   = "\x1b[0m"
    BOLD    = "\x1b[1m"
    DIM     = "\x1b[2m"
    CYAN    = "\x1b[36m"
    BCYAN   = "\x1b[96m"
    BGREEN  = "\x1b[92m"
    BYELLOW = "\x1b[93m"
    BBLUE   = "\x1b[94m"
    BMAGENTA= "\x1b[95m"
    BWHITE  = "\x1b[97m"
    RED     = "\x1b[31m"
    GREEN   = "\x1b[32m"
    YELLOW  = "\x1b[33m"


def _w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def _header(title: str) -> None:
    bar = "─" * (len(title) + 4)
    _w(f"\n{_C.BCYAN}{_C.BOLD}╭{bar}╮{_C.RESET}\n")
    _w(f"{_C.BCYAN}{_C.BOLD}│  {title}  │{_C.RESET}\n")
    _w(f"{_C.BCYAN}{_C.BOLD}╰{bar}╯{_C.RESET}\n\n")


def _row(key: str, val: str, key_w: int = 22) -> None:
    _w(f"  {_C.BCYAN}{key:<{key_w}}{_C.RESET}{val}\n")


def _sep() -> None:
    _w(f"  {_C.DIM}{'─' * 52}{_C.RESET}\n")


def _bytes_fmt(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _seconds_fmt(secs: float) -> str:
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


# ── Komendy ───────────────────────────────────────────────────────────────────

def _cmd_sys_info(args: list[str], terminal) -> None:
    """sys.info — interpreter, wersja, ścieżki, platforma, build."""
    _header("sys.info  —  Interpreter")

    vi = sys.version_info
    _row("Python version",    f"{vi.major}.{vi.minor}.{vi.micro} ({vi.releaselevel})")
    _row("Full version",      sys.version.replace("\n", " "))
    _row("Executable",        sys.executable)
    _row("Platform",          sys.platform)
    _row("Byte order",        sys.byteorder)
    _row("Max int",           str(sys.maxsize))
    _row("Max unicode",       str(sys.maxunicode))
    _row("Default encoding",  sys.getdefaultencoding())
    _row("Filesystem enc",    sys.getfilesystemencoding())
    _row("Float max",         str(sys.float_info.max))
    _row("Recursion limit",   str(sys.getrecursionlimit()))
    _row("Thread switch int", str(sys.getswitchinterval()))

    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}sys.path{_C.RESET}  ({len(sys.path)} wpisów)\n")
    for i, p in enumerate(sys.path):
        _w(f"    {_C.DIM}[{i:02d}]{_C.RESET} {p or '(bieżący katalog)'}\n")

    _sep()
    # Prefix / base_prefix
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Środowisko{_C.RESET}\n")
    _row("prefix",      sys.prefix)
    _row("exec_prefix", sys.exec_prefix)
    try:
        _row("base_prefix", sys.base_prefix)
    except AttributeError:
        pass
    venv = sys.prefix != getattr(sys, 'base_prefix', sys.prefix)
    _row("virtualenv",  f"{_C.BGREEN}aktywny{_C.RESET}" if venv else f"{_C.DIM}nie{_C.RESET}")

    # Build info
    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Build{_C.RESET}\n")
    try:
        _row("compiler",  sys.version.split("[")[1].rstrip("]").strip() if "[" in sys.version else "?")
    except Exception:
        pass
    _row("implementation", sys.implementation.name)
    _row("impl version",   ".".join(str(x) for x in sys.implementation.version[:3]))

    _w("\n")


def _cmd_sys_env(args: list[str], terminal) -> None:
    """sys.env — zmienne środowiskowe przez sys._xoptions i environ via 'environ'."""
    _header("sys.env  —  Zmienne środowiskowe")

    # Pobieramy env przez os.environ ale TYLKO przez referencję do modułu,
    # bez bezpośredniego importu `os` na poziomie modułu.
    # Alternatywnie: sys.environ nie istnieje, używamy importlib.
    _os = importlib.import_module("os")
    env = dict(_os.environ)

    filter_key = args[0].upper() if args else ""

    if filter_key:
        env = {k: v for k, v in env.items() if filter_key in k}
        _w(f"  {_C.DIM}Filtr: {_C.BYELLOW}{filter_key}{_C.RESET}\n\n")

    if not env:
        _w(f"  {_C.DIM}Brak wyników.{_C.RESET}\n")
    else:
        for k in sorted(env.keys()):
            v = env[k]
            # Skróć bardzo długie wartości
            display_v = (v[:80] + f" {_C.DIM}…(+{len(v)-80}){_C.RESET}") if len(v) > 80 else v
            _w(f"  {_C.BCYAN}{k:<30}{_C.RESET}{display_v}\n")

    _w(f"\n  {_C.DIM}Łącznie: {len(env)} zmiennych{_C.RESET}\n\n")

    # sys._xoptions jeśli coś jest
    if sys._xoptions:
        _sep()
        _w(f"\n  {_C.BBLUE}sys._xoptions{_C.RESET}\n")
        for k, v in sys._xoptions.items():
            _w(f"  {_C.BCYAN}{k:<30}{_C.RESET}{v}\n")
        _w("\n")


def _cmd_sys_time(args: list[str], terminal) -> None:
    """sys.time — aktualny timestamp w kilku formatach."""
    _header("sys.time  —  Timestamp")

    now_ts  = time.time()
    now_loc = time.localtime(now_ts)
    now_gmt = time.gmtime(now_ts)

    _row("Unix timestamp",   f"{now_ts:.6f}")
    _row("Localtime",        time.strftime("%Y-%m-%d %H:%M:%S", now_loc))
    _row("UTC / GMT",        time.strftime("%Y-%m-%d %H:%M:%S UTC", now_gmt))
    _row("ISO 8601",         time.strftime("%Y-%m-%dT%H:%M:%S", now_loc))
    _row("RFC 2822",         time.strftime("%a, %d %b %Y %H:%M:%S", now_loc))
    _row("Timezone",         time.strftime("%Z (UTC%z)", now_loc))
    _row("Day of year",      time.strftime("%j", now_loc))
    _row("Week number",      time.strftime("W%W", now_loc))
    _row("Perf counter",     f"{time.perf_counter():.9f} s")
    _row("Monotonic",        f"{time.monotonic():.9f} s")

    _sep()
    _w(f"\n  {_C.DIM}time.time() = czas systemowy (epoch seconds, float){_C.RESET}\n\n")


def _cmd_sys_uptime(args: list[str], terminal) -> None:
    """sys.uptime — czas działania sesji terminala."""
    _header("sys.uptime  —  Uptime terminala")

    elapsed = time.monotonic() - _MODULE_START

    _w(f"  {_C.BGREEN}{_C.BOLD}{_seconds_fmt(elapsed)}{_C.RESET}\n\n")
    _row("Dokładnie (s)",  f"{elapsed:.6f}")
    _row("Moduł załadowany", time.strftime("%Y-%m-%d %H:%M:%S",
                                            time.localtime(time.time() - elapsed)))

    # Jeśli terminal przechowuje swój własny czas startu
    if hasattr(terminal, '_start_time'):
        t_elapsed = time.monotonic() - terminal._start_time
        _sep()
        _w(f"\n  {_C.BBLUE}Terminal session{_C.RESET}\n")
        _row("Uptime sesji",  _seconds_fmt(t_elapsed))
        _row("Dokładnie (s)", f"{t_elapsed:.6f}")

    _w("\n")


def _cmd_sys_clearcache(args: list[str], terminal) -> None:
    """sys.clearcache — czyści cache terminala i wewnętrzne cache Pythona."""
    _header("sys.clearcache  —  Czyszczenie cache")

    cleared: list[str] = []

    # 1. Cache typów (Python 3.9+)
    try:
        sys._clear_type_cache()
        cleared.append("type cache (sys._clear_type_cache)")
    except AttributeError:
        pass

    # 2. Garbage collector
    try:
        import gc
        gc.collect()
        cleared.append("garbage collector (gc.collect)")
    except Exception:
        pass

    # 3. importlib invalidate_caches
    try:
        importlib.invalidate_caches()
        cleared.append("importlib finder cache")
    except Exception:
        pass

    # 4. tracemalloc — reset jeśli działa
    global _TRACEMALLOC_RUNNING
    if _TRACEMALLOC_RUNNING and tracemalloc.is_tracing():
        tracemalloc.clear_traces()
        cleared.append("tracemalloc traces")

    # 5. Terminal history cache (jeśli dostępny)
    if hasattr(terminal, '_history'):
        count = len(terminal._history)
        terminal._history.clear()
        cleared.append(f"history terminala ({count} wpisów)")

    # 6. Completion cache (jeśli istnieje)
    if hasattr(terminal, '_known_cmds'):
        terminal._known_cmds = set()
        cleared.append("known_cmds (autocomplete cache)")

    _w(f"  {_C.BGREEN}✓{_C.RESET} Wyczyszczono:\n\n")
    for item in cleared:
        _w(f"    {_C.BGREEN}•{_C.RESET} {item}\n")

    if not cleared:
        _w(f"  {_C.DIM}Brak elementów do czyszczenia.{_C.RESET}\n")

    _w(f"\n  {_C.DIM}Razem: {len(cleared)} operacji{_C.RESET}\n\n")


def _cmd_sys_modules(args: list[str], terminal) -> None:
    """sys.modules — lista załadowanych modułów Pythona."""
    _header("sys.modules  —  Załadowane moduły")

    mods = dict(sys.modules)
    filter_q = args[0].lower() if args else ""

    if filter_q:
        mods = {k: v for k, v in mods.items() if filter_q in k.lower()}
        _w(f"  {_C.DIM}Filtr: {_C.BYELLOW}{filter_q}{_C.RESET}\n\n")

    # Sortuj — top-level najpierw, potem submoduły
    top_level    = sorted(k for k in mods if "." not in k and mods[k] is not None)
    sub_level    = sorted(k for k in mods if "." in k     and mods[k] is not None)
    none_entries = sorted(k for k in mods if mods[k] is None)

    def _mod_file(mod) -> str:
        try:
            f = getattr(mod, "__file__", None)
            if f:
                return f"  {_C.DIM}{f[:60]}{_C.RESET}"
        except Exception:
            pass
        return ""

    _w(f"  {_C.BBLUE}{_C.BOLD}Top-level ({len(top_level)}){_C.RESET}\n")
    for name in top_level:
        _w(f"    {_C.BGREEN}{name:<28}{_C.RESET}{_mod_file(mods[name])}\n")

    if sub_level:
        _sep()
        _w(f"\n  {_C.BBLUE}{_C.BOLD}Submoduły ({len(sub_level)}){_C.RESET}\n")
        for name in sub_level:
            _w(f"    {_C.CYAN}{name:<40}{_C.RESET}{_mod_file(mods[name])}\n")

    if none_entries:
        _sep()
        _w(f"\n  {_C.DIM}Failed/None ({len(none_entries)}): {', '.join(none_entries[:10])}")
        if len(none_entries) > 10:
            _w(f" …+{len(none_entries)-10}")
        _w(f"{_C.RESET}\n")

    _sep()
    _w(f"\n  {_C.DIM}Łącznie: {len(mods)} wpisów "
       f"({len(top_level)} top-level, {len(sub_level)} submodułów, "
       f"{len(none_entries)} nieudanych){_C.RESET}\n\n")


def _cmd_sys_mem(args: list[str], terminal) -> None:
    """sys.mem — użycie pamięci przez tracemalloc + sys.getsizeof."""
    _header("sys.mem  —  Pamięć (tracemalloc)")

    global _TRACEMALLOC_RUNNING

    # Uruchom tracemalloc jeśli nie działa
    if not tracemalloc.is_tracing():
        tracemalloc.start()
        _TRACEMALLOC_RUNNING = True
        _w(f"  {_C.DIM}tracemalloc uruchomiony.{_C.RESET}\n\n")

    snapshot = tracemalloc.take_snapshot()
    stats    = snapshot.statistics("lineno")

    # Bieżące / szczytowe użycie
    current, peak = tracemalloc.get_traced_memory()

    _row("Bieżące użycie",  f"{_C.BGREEN}{_bytes_fmt(current)}{_C.RESET}  ({current:,} B)")
    _row("Szczyt (peak)",   f"{_C.BYELLOW}{_bytes_fmt(peak)}{_C.RESET}  ({peak:,} B)")

    # sys.getsizeof dla wybranych obiektów
    _sep()
    _w(f"\n  {_C.BBLUE}Rozmiary kluczowych obiektów{_C.RESET}\n")
    _row("sys.modules dict", _bytes_fmt(sys.getsizeof(sys.modules)))
    _row("sys.path list",    _bytes_fmt(sys.getsizeof(sys.path)))
    try:
        import gc
        objs = gc.get_objects()
        _row("gc tracked objs", f"{len(objs):,} obiektów")
    except Exception:
        pass

    # Top alokatorzy
    _sep()
    _w(f"\n  {_C.BBLUE}Top 10 alokatorów{_C.RESET}\n")
    _w(f"  {_C.DIM}{'Rozmiar':<12}{'Plik : linia'}{_C.RESET}\n")
    for stat in stats[:10]:
        frame  = stat.traceback[0]
        fname  = frame.filename
        # Skróć ścieżkę
        if len(fname) > 45:
            fname = "…" + fname[-44:]
        size_s = _bytes_fmt(stat.size)
        _w(f"  {_C.BGREEN}{size_s:<12}{_C.RESET}{_C.DIM}{fname}:{frame.lineno}{_C.RESET}\n")

    _w("\n")


def _cmd_sys_cpuclock(args: list[str], terminal) -> None:
    """sys.cpuclock — odczyt zegara CPU: process_time, perf_counter, pomiar busy-loop."""
    _header("sys.cpuclock  —  Zegar CPU")

    # Odczyty zegarów
    proc_start   = time.process_time()
    perf_start   = time.perf_counter()
    thread_start = time.thread_time() if hasattr(time, 'thread_time') else None
    mono_start   = time.monotonic()

    # Krótki pomiar: obliczenia CPU-bound (sum potęg)
    _ITERS = 250_000
    result = sum(i * i for i in range(_ITERS))

    proc_end  = time.process_time()
    perf_end  = time.perf_counter()
    mono_end  = time.monotonic()

    cpu_used  = proc_end  - proc_start
    wall_used = perf_end  - perf_start
    mono_used = mono_end  - mono_start

    if thread_start is not None:
        thread_end  = time.thread_time()
        thread_used = thread_end - thread_start
    else:
        thread_used = None

    # Wyświetl bieżące wartości zegarów
    _w(f"  {_C.BBLUE}{_C.BOLD}Wartości zegarów (snapshot){_C.RESET}\n\n")
    _row("perf_counter()",   f"{perf_end:.9f} s  {_C.DIM}(high-res wall clock){_C.RESET}")
    _row("process_time()",   f"{proc_end:.9f} s  {_C.DIM}(CPU czas procesu){_C.RESET}")
    _row("monotonic()",      f"{mono_end:.9f} s  {_C.DIM}(monotoniczna oś czasu){_C.RESET}")
    if thread_used is not None:
        _row("thread_time()", f"{thread_end:.9f} s  {_C.DIM}(CPU czas wątku){_C.RESET}")

    try:
        _row("perf_ns()",    f"{time.perf_counter_ns():,} ns")
    except AttributeError:
        pass

    # Wyniki pomiaru
    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Pomiar wydajności  {_C.DIM}(sum(i² for i in range({_ITERS:,})){_C.RESET}\n\n")
    _row("CPU time",         f"{_C.BGREEN}{cpu_used*1000:.4f} ms{_C.RESET}")
    _row("Wall time",        f"{_C.BYELLOW}{wall_used*1000:.4f} ms{_C.RESET}")
    _row("Monotonic delta",  f"{mono_used*1000:.4f} ms")
    if thread_used is not None:
        _row("Thread CPU",   f"{thread_used*1000:.4f} ms")
    cpu_pct = (cpu_used / wall_used * 100) if wall_used > 0 else 0
    _row("CPU utilisation",  f"{cpu_pct:.1f}%  {_C.DIM}(cpu_time / wall_time){_C.RESET}")
    _row("Operacje/s",       f"{_ITERS / wall_used:,.0f}  iter/s")

    # Rozdzielczość zegarów
    _sep()
    _w(f"\n  {_C.BBLUE}Rozdzielczość zegarów{_C.RESET}\n")
    try:
        _row("perf_counter",  f"{time.get_clock_info('perf_counter').resolution:.2e} s")
        _row("process_time",  f"{time.get_clock_info('process_time').resolution:.2e} s")
        _row("monotonic",     f"{time.get_clock_info('monotonic').resolution:.2e} s")
    except AttributeError:
        _w(f"  {_C.DIM}get_clock_info niedostępne.{_C.RESET}\n")

    _w("\n")


# ── fs.* — operacje na systemie plików ───────────────────────────────────────

def _fs_path(args: list[str], idx: int = 0, default: str = ".") -> str:
    """Zwraca ścieżkę z args[idx] lub default."""
    _os = importlib.import_module("os")
    raw = args[idx] if len(args) > idx else default
    return _os.path.expanduser(_os.path.expandvars(raw))


def _cmd_fs_ls(args: list[str], terminal) -> None:
    """fs.ls [katalog] — lista plików w katalogu."""
    _os   = importlib.import_module("os")
    _stat = importlib.import_module("stat")
    path  = _fs_path(args, 0, ".")

    _header(f"fs.ls  —  {path}")

    try:
        entries = sorted(_os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień: {path}{_C.RESET}\n\n"); return
    except FileNotFoundError:
        _w(f"  {_C.RED}Nie znaleziono: {path}{_C.RESET}\n\n"); return

    if not entries:
        _w(f"  {_C.DIM}(pusty katalog){_C.RESET}\n\n"); return

    _w(f"  {_C.DIM}{'Typ':<4}{'Prawa':<12}{'Rozmiar':>10}  {'Nazwa'}{_C.RESET}\n")
    _sep()

    for e in entries:
        try:
            st   = e.stat(follow_symlinks=False)
            mode = _stat.filemode(st.st_mode)
            if e.is_dir(follow_symlinks=False):
                typ   = _C.BBLUE + "DIR" + _C.RESET
                name  = _C.BBLUE + _C.BOLD + e.name + "/" + _C.RESET
                size  = ""
            elif e.is_symlink():
                typ   = _C.BYELLOW + "LNK" + _C.RESET
                name  = _C.BYELLOW + e.name + _C.RESET
                size  = _bytes_fmt(st.st_size)
            else:
                typ   = _C.DIM + "FIL" + _C.RESET
                name  = e.name
                size  = _bytes_fmt(st.st_size)
            _w(f"  {typ:<17}{_C.DIM}{mode:<12}{_C.RESET}{size:>10}  {name}\n")
        except Exception:
            _w(f"  {_C.DIM}???{'':9}{'':12}{'':>10}  {e.name}{_C.RESET}\n")

    _w(f"\n  {_C.DIM}Łącznie: {len(entries)} wpisów{_C.RESET}\n\n")


def _cmd_fs_tree(args: list[str], terminal) -> None:
    """fs.tree [katalog] [głębokość] — drzewo katalogów (rekurencyjnie)."""
    _os   = importlib.import_module("os")
    path  = _fs_path(args, 0, ".")
    try:
        max_depth = int(args[1]) if len(args) > 1 else 999
    except ValueError:
        max_depth = 999

    _header(f"fs.tree  —  {path}")

    if not _os.path.exists(path):
        _w(f"  {_C.RED}Nie znaleziono: {path}{_C.RESET}\n\n"); return

    _counter = [0]

    def _walk(cur: str, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(_os.scandir(cur), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            _w(f"{prefix}  {_C.RED}[brak uprawnień]{_C.RESET}\n"); return

        for i, e in enumerate(entries):
            is_last   = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            child_pfx = prefix + ("    " if is_last else "│   ")
            if e.is_dir(follow_symlinks=False):
                _w(f"{prefix}{_C.BBLUE}{connector}{_C.BOLD}{e.name}/{_C.RESET}\n")
                _walk(e.path, child_pfx, depth + 1)
            else:
                _counter[0] += 1
                _w(f"{prefix}{_C.DIM}{connector}{_C.RESET}{e.name}\n")

    _w(f"  {_C.BBLUE}{_C.BOLD}{_os.path.abspath(path)}{_C.RESET}\n")
    _walk(path, "  ", 1)
    _w(f"\n  {_C.DIM}Plików: {_counter[0]}{_C.RESET}\n\n")


def _cmd_fs_read(args: list[str], terminal) -> None:
    """fs.read <plik> [max_linie] — odczyt zawartości pliku."""
    if not args:
        _w(f"  {_C.RED}Użycie: fs.read <plik> [max_linie]{_C.RESET}\n\n"); return

    path = _fs_path(args, 0)
    try:
        max_lines = int(args[1]) if len(args) > 1 else None
    except ValueError:
        max_lines = None

    _header(f"fs.read  —  {path}")

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        _w(f"  {_C.RED}Nie znaleziono: {path}{_C.RESET}\n\n"); return
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień: {path}{_C.RESET}\n\n"); return
    except IsADirectoryError:
        _w(f"  {_C.RED}To katalog, nie plik: {path}{_C.RESET}\n\n"); return

    total     = len(lines)
    displayed = lines[:max_lines] if max_lines else lines
    pad       = len(str(len(displayed)))

    for i, line in enumerate(displayed, 1):
        _w(f"  {_C.DIM}{i:>{pad}}{_C.RESET}  {line}", )
    if not displayed[-1].endswith("\n") if displayed else False:
        _w("\n")

    _sep()
    note = f"(pokazano {len(displayed)} z {total})" if max_lines and max_lines < total else ""
    _w(f"\n  {_C.DIM}Łącznie: {total} linii  {note}{_C.RESET}\n\n")


def _cmd_fs_write(args: list[str], terminal) -> None:
    """fs.write <plik> <treść> — nadpisuje plik podaną treścią."""
    if len(args) < 2:
        _w(f"  {_C.RED}Użycie: fs.write <plik> <treść>{_C.RESET}\n\n"); return

    path    = _fs_path(args, 0)
    content = " ".join(args[1:])

    _header(f"fs.write  —  {path}")

    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień: {path}{_C.RESET}\n\n"); return
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    _w(f"  {_C.BGREEN}✓{_C.RESET} Zapisano {_bytes_fmt(len(content.encode()))} → {path}\n\n")


def _cmd_fs_append(args: list[str], terminal) -> None:
    """fs.append <plik> <treść> — dopisuje treść na końcu pliku."""
    if len(args) < 2:
        _w(f"  {_C.RED}Użycie: fs.append <plik> <treść>{_C.RESET}\n\n"); return

    path    = _fs_path(args, 0)
    content = " ".join(args[1:])

    _header(f"fs.append  —  {path}")

    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(content)
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień: {path}{_C.RESET}\n\n"); return
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    _w(f"  {_C.BGREEN}✓{_C.RESET} Dopisano {_bytes_fmt(len(content.encode()))} → {path}\n\n")


def _cmd_fs_touch(args: list[str], terminal) -> None:
    """fs.touch <plik> — tworzy pusty plik (lub aktualizuje czas modyfikacji)."""
    if not args:
        _w(f"  {_C.RED}Użycie: fs.touch <plik>{_C.RESET}\n\n"); return

    _os  = importlib.import_module("os")
    path = _fs_path(args, 0)

    _header(f"fs.touch  —  {path}")

    existed = _os.path.exists(path)
    try:
        with open(path, "a"):
            _os.utime(path, None)
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień: {path}{_C.RESET}\n\n"); return
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    action = "zaktualizowano czas" if existed else "utworzono"
    _w(f"  {_C.BGREEN}✓{_C.RESET} {action}: {path}\n\n")


def _cmd_fs_rm(args: list[str], terminal) -> None:
    """fs.rm <plik> — usuwa plik."""
    if not args:
        _w(f"  {_C.RED}Użycie: fs.rm <plik>{_C.RESET}\n\n"); return

    _os  = importlib.import_module("os")
    path = _fs_path(args, 0)

    _header(f"fs.rm  —  {path}")

    if not _os.path.exists(path):
        _w(f"  {_C.RED}Nie znaleziono: {path}{_C.RESET}\n\n"); return
    if _os.path.isdir(path):
        _w(f"  {_C.RED}To katalog — użyj fs.rmdir{_C.RESET}\n\n"); return

    try:
        _os.remove(path)
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień: {path}{_C.RESET}\n\n"); return
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    _w(f"  {_C.BGREEN}✓{_C.RESET} Usunięto: {path}\n\n")


def _cmd_fs_mv(args: list[str], terminal) -> None:
    """fs.mv <źródło> <cel> — przenosi / zmienia nazwę pliku lub katalogu."""
    if len(args) < 2:
        _w(f"  {_C.RED}Użycie: fs.mv <źródło> <cel>{_C.RESET}\n\n"); return

    _shutil = importlib.import_module("shutil")
    src     = _fs_path(args, 0)
    dst     = _fs_path(args, 1)

    _header(f"fs.mv  —  {src}  →  {dst}")

    try:
        _shutil.move(src, dst)
    except FileNotFoundError:
        _w(f"  {_C.RED}Nie znaleziono: {src}{_C.RESET}\n\n"); return
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień{_C.RESET}\n\n"); return
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    _w(f"  {_C.BGREEN}✓{_C.RESET} Przeniesiono: {src} → {dst}\n\n")


def _cmd_fs_cp(args: list[str], terminal) -> None:
    """fs.cp <źródło> <cel> — kopiuje plik (lub katalog z -r)."""
    if len(args) < 2:
        _w(f"  {_C.RED}Użycie: fs.cp <źródło> <cel>{_C.RESET}\n\n"); return

    _shutil = importlib.import_module("shutil")
    _os     = importlib.import_module("os")
    src     = _fs_path(args, 0)
    dst     = _fs_path(args, 1)

    _header(f"fs.cp  —  {src}  →  {dst}")

    try:
        if _os.path.isdir(src):
            _shutil.copytree(src, dst)
            _w(f"  {_C.BGREEN}✓{_C.RESET} Skopiowano katalog: {src} → {dst}\n\n")
        else:
            _shutil.copy2(src, dst)
            st = _os.stat(src)
            _w(f"  {_C.BGREEN}✓{_C.RESET} Skopiowano plik ({_bytes_fmt(st.st_size)}): {src} → {dst}\n\n")
    except FileNotFoundError:
        _w(f"  {_C.RED}Nie znaleziono: {src}{_C.RESET}\n\n")
    except FileExistsError:
        _w(f"  {_C.RED}Cel już istnieje: {dst}{_C.RESET}\n\n")
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień{_C.RESET}\n\n")
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n")


def _cmd_fs_mkdir(args: list[str], terminal) -> None:
    """fs.mkdir <katalog> — tworzy katalog (wraz z pośrednimi)."""
    if not args:
        _w(f"  {_C.RED}Użycie: fs.mkdir <katalog>{_C.RESET}\n\n"); return

    _os  = importlib.import_module("os")
    path = _fs_path(args, 0)

    _header(f"fs.mkdir  —  {path}")

    try:
        _os.makedirs(path, exist_ok=True)
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień: {path}{_C.RESET}\n\n"); return
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    _w(f"  {_C.BGREEN}✓{_C.RESET} Utworzono: {path}\n\n")


def _cmd_fs_rmdir(args: list[str], terminal) -> None:
    """fs.rmdir <katalog> — usuwa katalog rekurencyjnie."""
    if not args:
        _w(f"  {_C.RED}Użycie: fs.rmdir <katalog>{_C.RESET}\n\n"); return

    _shutil = importlib.import_module("shutil")
    _os     = importlib.import_module("os")
    path    = _fs_path(args, 0)

    _header(f"fs.rmdir  —  {path}")

    if not _os.path.exists(path):
        _w(f"  {_C.RED}Nie znaleziono: {path}{_C.RESET}\n\n"); return
    if not _os.path.isdir(path):
        _w(f"  {_C.RED}To nie katalog — użyj fs.rm{_C.RESET}\n\n"); return

    try:
        _shutil.rmtree(path)
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień: {path}{_C.RESET}\n\n"); return
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    _w(f"  {_C.BGREEN}✓{_C.RESET} Usunięto katalog: {path}\n\n")


def _cmd_fs_hash(args: list[str], terminal) -> None:
    """fs.hash <plik> [algorytm] — oblicza hash pliku (domyślnie sha256)."""
    if not args:
        _w(f"  {_C.RED}Użycie: fs.hash <plik> [md5|sha1|sha256|sha512]{_C.RESET}\n\n"); return

    _hashlib = importlib.import_module("hashlib")
    path     = _fs_path(args, 0)
    algo     = args[1].lower() if len(args) > 1 else "sha256"

    _header(f"fs.hash  —  {path}")

    if algo not in _hashlib.algorithms_available:
        _w(f"  {_C.RED}Nieznany algorytm: {algo}{_C.RESET}\n\n"); return

    try:
        h    = _hashlib.new(algo)
        size = 0
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
                size += len(chunk)
    except FileNotFoundError:
        _w(f"  {_C.RED}Nie znaleziono: {path}{_C.RESET}\n\n"); return
    except PermissionError:
        _w(f"  {_C.RED}Brak uprawnień: {path}{_C.RESET}\n\n"); return
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    _row("Plik",       path)
    _row("Algorytm",   algo.upper())
    _row("Rozmiar",    _bytes_fmt(size))
    _sep()
    _w(f"\n  {_C.BGREEN}{_C.BOLD}{h.hexdigest()}{_C.RESET}\n\n")


def _cmd_fs_size(args: list[str], terminal) -> None:
    """fs.size <ścieżka> — rozmiar pliku lub łączny rozmiar katalogu."""
    if not args:
        _w(f"  {_C.RED}Użycie: fs.size <ścieżka>{_C.RESET}\n\n"); return

    _os  = importlib.import_module("os")
    path = _fs_path(args, 0)

    _header(f"fs.size  —  {path}")

    if not _os.path.exists(path):
        _w(f"  {_C.RED}Nie znaleziono: {path}{_C.RESET}\n\n"); return

    if _os.path.isfile(path):
        st = _os.stat(path)
        _row("Rozmiar",    f"{_C.BGREEN}{_bytes_fmt(st.st_size)}{_C.RESET}  ({st.st_size:,} B)")
        _row("Typ",        "plik")
    else:
        total  = 0
        nfiles = 0
        ndirs  = 0
        for root, dirs, files in _os.walk(path):
            ndirs += len(dirs)
            for f in files:
                nfiles += 1
                try:
                    total += _os.path.getsize(_os.path.join(root, f))
                except Exception:
                    pass
        _row("Łączny rozmiar", f"{_C.BGREEN}{_bytes_fmt(total)}{_C.RESET}  ({total:,} B)")
        _row("Pliki",          str(nfiles))
        _row("Podkatalogi",    str(ndirs))
        _row("Typ",            "katalog")

    _w("\n")


def _cmd_fs_find(args: list[str], terminal) -> None:
    """fs.find <wzorzec> [katalog] — wyszukuje pliki po nazwie (glob)."""
    if not args:
        _w(f"  {_C.RED}Użycie: fs.find <wzorzec> [katalog]{_C.RESET}\n\n"); return

    _os     = importlib.import_module("os")
    _fnmatch = importlib.import_module("fnmatch")
    pattern = args[0]
    root    = _fs_path(args, 1, ".")

    _header(f"fs.find  —  '{pattern}'  w  {root}")

    if not _os.path.exists(root):
        _w(f"  {_C.RED}Nie znaleziono katalogu: {root}{_C.RESET}\n\n"); return

    found   = []
    for dirpath, dirnames, filenames in _os.walk(root):
        for name in filenames:
            if _fnmatch.fnmatch(name, pattern):
                full = _os.path.join(dirpath, name)
                found.append(full)
        # również katalogi
        for name in dirnames:
            if _fnmatch.fnmatch(name, pattern):
                found.append(_os.path.join(dirpath, name) + "/")

    if not found:
        _w(f"  {_C.DIM}Brak wyników dla '{pattern}'{_C.RESET}\n\n"); return

    for p in sorted(found):
        if p.endswith("/"):
            _w(f"  {_C.BBLUE}{p}{_C.RESET}\n")
        else:
            _w(f"  {p}\n")

    _w(f"\n  {_C.DIM}Znaleziono: {len(found)} wyników{_C.RESET}\n\n")


# ── net.* — operacje sieciowe ─────────────────────────────────────────────────

_NET_TIMEOUT: float = 10.0          # domyślny timeout w sekundach
_NET_UA = "CrossTerm/1.0 sysadmin"  # User-Agent dla żądań HTTP


def _parse_url(url: str) -> str:
    """Dodaje https:// jeśli brak schematu."""
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def _http_request(method: str, url: str, headers: dict | None = None,
                  data: bytes | None = None, timeout: float = _NET_TIMEOUT):
    """Wykonuje żądanie HTTP; zwraca (response, elapsed_ms) lub rzuca wyjątek.
    HTTPError (4xx/5xx) jest traktowany jako prawidłowa odpowiedź — nie wyjątek."""
    _urllib_req = importlib.import_module("urllib.request")
    _urllib_err = importlib.import_module("urllib.error")
    _time_mod   = importlib.import_module("time")

    hdrs = {"User-Agent": _NET_UA}
    if headers:
        hdrs.update(headers)

    req = _urllib_req.Request(url, data=data, headers=hdrs, method=method)
    t0  = _time_mod.perf_counter()
    try:
        resp = _urllib_req.urlopen(req, timeout=timeout)
    except _urllib_err.HTTPError as e:
        # HTTPError opakowuje pełną odpowiedź HTTP — traktujemy jak normalny response
        elapsed = (_time_mod.perf_counter() - t0) * 1000
        return e, elapsed
    elapsed = (_time_mod.perf_counter() - t0) * 1000
    return resp, elapsed


def _status_color(code: int) -> str:
    if code < 300:   return _C.BGREEN
    if code < 400:   return _C.BYELLOW
    if code < 500:   return _C.RED
    return _C.RED + _C.BOLD


def _cmd_net_http_get(args: list[str], terminal) -> None:
    """net.http.get <url> [Nagłówek:Wartość …] — HTTP GET."""
    if not args:
        _w(f"  {_C.RED}Użycie: net.http.get <url> [Nagłówek:Wartość …]{_C.RESET}\n\n"); return

    url  = _parse_url(args[0])
    hdrs = {}
    for a in args[1:]:
        if ":" in a:
            k, _, v = a.partition(":")
            hdrs[k.strip()] = v.strip()

    _header(f"net.http.get  —  {url}")

    try:
        resp, ms = _http_request("GET", url, headers=hdrs)
        body_raw = resp.read()
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    sc = resp.status
    _row("URL",          url)
    _row("Status",       f"{_status_color(sc)}{sc} {resp.reason}{_C.RESET}")
    _row("Czas",         f"{ms:.1f} ms")
    _row("Rozmiar",      _bytes_fmt(len(body_raw)))
    _row("Content-Type", resp.headers.get("Content-Type", "—"))

    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Nagłówki odpowiedzi{_C.RESET}\n")
    for k, v in resp.headers.items():
        _w(f"  {_C.BCYAN}{k:<28}{_C.RESET}{v}\n")

    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Treść{_C.RESET}\n\n")
    try:
        enc  = resp.headers.get_content_charset("utf-8") or "utf-8"
        text = body_raw.decode(enc, errors="replace")
    except Exception:
        text = body_raw.decode("utf-8", errors="replace")

    lines = text.splitlines()
    for i, line in enumerate(lines[:40]):
        _w(f"  {line}\n")
    if len(lines) > 40:
        _w(f"\n  {_C.DIM}… (+{len(lines)-40} linii, łącznie {len(lines)}){_C.RESET}\n")
    _w("\n")


def _cmd_net_http_head(args: list[str], terminal) -> None:
    """net.http.head <url> — HTTP HEAD, tylko nagłówki."""
    if not args:
        _w(f"  {_C.RED}Użycie: net.http.head <url>{_C.RESET}\n\n"); return

    url = _parse_url(args[0])
    _header(f"net.http.head  —  {url}")

    try:
        resp, ms = _http_request("HEAD", url)
        resp.read()
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    sc = resp.status
    _row("URL",    url)
    _row("Status", f"{_status_color(sc)}{sc} {resp.reason}{_C.RESET}")
    _row("Czas",   f"{ms:.1f} ms")

    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Nagłówki{_C.RESET}\n\n")
    for k, v in resp.headers.items():
        _w(f"  {_C.BCYAN}{k:<28}{_C.RESET}{v}\n")
    _w("\n")


def _cmd_net_http_post(args: list[str], terminal) -> None:
    """net.http.post <url> <klucz=wartość …> — HTTP POST (form-urlencoded)."""
    if not args:
        _w(f"  {_C.RED}Użycie: net.http.post <url> [klucz=wartość …]{_C.RESET}\n\n"); return

    _urllib_parse = importlib.import_module("urllib.parse")
    url  = _parse_url(args[0])
    form = {}
    for a in args[1:]:
        if "=" in a:
            k, _, v = a.partition("=")
            form[k] = v
        else:
            form[a] = ""

    data = _urllib_parse.urlencode(form).encode("utf-8")
    hdrs = {"Content-Type": "application/x-www-form-urlencoded"}

    _header(f"net.http.post  —  {url}")
    _w(f"  {_C.DIM}Payload: {_urllib_parse.urlencode(form)}{_C.RESET}\n\n")

    try:
        resp, ms = _http_request("POST", url, headers=hdrs, data=data)
        body_raw = resp.read()
    except Exception as exc:
        _w(f"  {_C.RED}Błąd: {exc}{_C.RESET}\n\n"); return

    sc = resp.status
    _row("Status",       f"{_status_color(sc)}{sc} {resp.reason}{_C.RESET}")
    _row("Czas",         f"{ms:.1f} ms")
    _row("Rozmiar",      _bytes_fmt(len(body_raw)))
    _row("Content-Type", resp.headers.get("Content-Type", "—"))

    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Nagłówki odpowiedzi{_C.RESET}\n")
    for k, v in resp.headers.items():
        _w(f"  {_C.BCYAN}{k:<28}{_C.RESET}{v}\n")

    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Treść{_C.RESET}\n\n")
    try:
        enc  = resp.headers.get_content_charset("utf-8") or "utf-8"
        text = body_raw.decode(enc, errors="replace")
    except Exception:
        text = body_raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    for line in lines[:40]:
        _w(f"  {line}\n")
    if len(lines) > 40:
        _w(f"\n  {_C.DIM}… (+{len(lines)-40} linii){_C.RESET}\n")
    _w("\n")


def _cmd_net_dns_resolve(args: list[str], terminal) -> None:
    """net.dns.resolve <host> [4|6|all] — DNS lookup przez socket.getaddrinfo."""
    if not args:
        _w(f"  {_C.RED}Użycie: net.dns.resolve <host> [4|6|all]{_C.RESET}\n\n"); return

    _socket = importlib.import_module("socket")
    _time_m = importlib.import_module("time")

    host   = args[0]
    family_arg = args[1].lower() if len(args) > 1 else "all"

    if family_arg == "4":
        families = [(_socket.AF_INET,  "IPv4")]
    elif family_arg == "6":
        families = [(_socket.AF_INET6, "IPv6")]
    else:
        families = [(_socket.AF_INET, "IPv4"), (_socket.AF_INET6, "IPv6")]

    _header(f"net.dns.resolve  —  {host}")

    for af, label in families:
        t0 = _time_m.perf_counter()
        try:
            results = _socket.getaddrinfo(host, None, af)
            ms = (_time_m.perf_counter() - t0) * 1000
        except _socket.gaierror as exc:
            _w(f"  {_C.DIM}{label}:{_C.RESET}  {_C.RED}{exc}{_C.RESET}\n")
            continue

        addrs = list(dict.fromkeys(r[4][0] for r in results))
        _w(f"  {_C.BBLUE}{_C.BOLD}{label}{_C.RESET}  {_C.DIM}({ms:.1f} ms){_C.RESET}\n")
        for addr in addrs:
            _w(f"    {_C.BGREEN}{addr}{_C.RESET}\n")

    # CNAME / canonical — próba przez gethostbyname_ex
    _sep()
    try:
        t0 = _time_m.perf_counter()
        canonical, aliases, addrs4 = _socket.gethostbyname_ex(host)
        ms = (_time_m.perf_counter() - t0) * 1000
        _w(f"\n  {_C.BBLUE}gethostbyname_ex{_C.RESET}  {_C.DIM}({ms:.1f} ms){_C.RESET}\n")
        _row("Canonical",  canonical)
        if aliases:
            _row("Aliasy",  ", ".join(aliases))
        _row("Adresy",  ", ".join(addrs4))
    except Exception:
        pass

    _w("\n")


def _cmd_net_ip_public(args: list[str], terminal) -> None:
    """net.ip.public — pobiera publiczne IP przez zewnętrzny serwis lub UDP trick."""
    _header("net.ip.public  —  Publiczne IP")

    _services = [
        ("https://api.ipify.org",          "ipify"),
        ("https://api4.my-ip.io/ip",       "my-ip.io"),
        ("https://checkip.amazonaws.com",  "amazonaws"),
        ("https://ifconfig.me/ip",         "ifconfig.me"),
        ("https://icanhazip.com",          "icanhazip"),
    ]

    for url, name in _services:
        try:
            resp, ms = _http_request("GET", url, timeout=8.0)
            raw = resp.read().decode("utf-8", errors="replace").strip()
            # Walidacja: musi wyglądać jak IP
            parts = raw.split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                _row("Publiczne IP", f"{_C.BGREEN}{_C.BOLD}{raw}{_C.RESET}")
                _row("Serwis",       name)
                _row("Czas",         f"{ms:.1f} ms")
                _w("\n"); return
        except Exception:
            continue

    # Fallback: UDP trick — lokalne IP wychodzące na zewnątrz (nie wysyła pakietów)
    _socket = importlib.import_module("socket")
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        _row("Wychodzące IP",  f"{_C.BYELLOW}{_C.BOLD}{ip}{_C.RESET}")
        _row("Metoda",         "UDP trick (socket — może być NAT/prywatne)")
        _w("\n"); return
    except Exception:
        pass

    _w(f"  {_C.RED}Nie udało się pobrać publicznego IP (brak połączenia?){_C.RESET}\n\n")


def _cmd_net_ip_local(args: list[str], terminal) -> None:
    """net.ip.local — lokalne adresy IP (wszystkie interfejsy)."""
    _socket  = importlib.import_module("socket")
    _header("net.ip.local  —  Lokalne IP")

    # Hostname
    try:
        hostname = _socket.gethostname()
        _row("Hostname", hostname)
    except Exception:
        hostname = "localhost"

    # Podstawowy IP przez UDP trick (nie wysyła pakietów)
    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Podstawowy interfejs{_C.RESET}\n")
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
        _row("IP (primary)", f"{_C.BGREEN}{primary}{_C.RESET}")
    except Exception:
        _w(f"  {_C.DIM}Nie można określić podstawowego interfejsu{_C.RESET}\n")

    # Wszystkie adresy przez getaddrinfo
    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}getaddrinfo (localhost + hostname){_C.RESET}\n")
    seen: set[str] = set()
    for query in ("localhost", hostname):
        try:
            for fam, _, _, _, addr in _socket.getaddrinfo(query, None):
                ip = addr[0]
                if ip not in seen:
                    seen.add(ip)
                    label = "IPv6" if ":" in ip else "IPv4"
                    color = _C.BCYAN if ":" in ip else _C.BGREEN
                    _w(f"  {color}{ip:<40}{_C.RESET}{_C.DIM}{label}{_C.RESET}\n")
        except Exception:
            pass

    _w("\n")


def _cmd_net_port_scan(args: list[str], terminal) -> None:
    """net.port.scan <host> <port|zakres> … — skanuje porty TCP (connect)."""
    if len(args) < 2:
        _w(f"  {_C.RED}Użycie: net.port.scan <host> <port> [port2] [80-90] …{_C.RESET}\n\n"); return

    _socket = importlib.import_module("socket")
    _time_m = importlib.import_module("time")

    host    = args[0]
    timeout = 1.0
    ports: list[int] = []

    for tok in args[1:]:
        if "-" in tok and not tok.startswith("-"):
            lo, _, hi = tok.partition("-")
            try:
                ports.extend(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        else:
            try:
                ports.append(int(tok))
            except ValueError:
                pass

    if not ports:
        _w(f"  {_C.RED}Brak poprawnych portów.{_C.RESET}\n\n"); return

    ports = sorted(set(p for p in ports if 1 <= p <= 65535))
    if len(ports) > 200:
        _w(f"  {_C.BYELLOW}Uwaga: ograniczono do 200 portów (podano {len(ports)}){_C.RESET}\n")
        ports = ports[:200]

    # Resolv host raz
    try:
        ip = _socket.gethostbyname(host)
    except _socket.gaierror as exc:
        _w(f"  {_C.RED}DNS error: {exc}{_C.RESET}\n\n"); return

    _header(f"net.port.scan  —  {host}  ({ip})")
    _row("Host",    f"{host} ({ip})")
    _row("Porty",   f"{len(ports)}  ({ports[0]}–{ports[-1]})")
    _row("Timeout", f"{timeout*1000:.0f} ms / port")
    _sep()
    _w(f"\n  {_C.DIM}{'Port':<8}{'Status':<12}{'Czas':>8}  Usługa{_C.RESET}\n")

    open_count = 0

    # Popularne porty → nazwa usługi
    _SERVICES: dict[int, str] = {
        21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
        80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS", 465: "SMTPS",
        587: "SMTP/TLS", 993: "IMAPS", 995: "POP3S", 3306: "MySQL",
        5432: "PostgreSQL", 6379: "Redis", 8080: "HTTP-alt",
        8443: "HTTPS-alt", 27017: "MongoDB",
    }

    for port in ports:
        t0 = _time_m.perf_counter()
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.settimeout(timeout)
            result = s.connect_ex((ip, port))
            ms = (_time_m.perf_counter() - t0) * 1000
            s.close()
        except Exception:
            ms = timeout * 1000
            result = -1

        svc = _SERVICES.get(port, "")
        if result == 0:
            open_count += 1
            _w(f"  {_C.BGREEN}{port:<8}{'OPEN':<12}{_C.RESET}{ms:>7.1f}ms  {_C.BYELLOW}{svc}{_C.RESET}\n")
        else:
            _w(f"  {_C.DIM}{port:<8}{'closed':<12}{ms:>7.1f}ms{_C.RESET}\n")

    _sep()
    _w(f"\n  {_C.DIM}Otwarte: {_C.BGREEN}{open_count}{_C.RESET}{_C.DIM} / {len(ports)}{_C.RESET}\n\n")


def _cmd_net_ping(args: list[str], terminal) -> None:
    """net.ping <host> [port=80] [liczba=4] — TCP ping (czas połączenia)."""
    if not args:
        _w(f"  {_C.RED}Użycie: net.ping <host> [port] [liczba]{_C.RESET}\n\n"); return

    _socket = importlib.import_module("socket")
    _time_m = importlib.import_module("time")

    host  = args[0]
    try:
        port  = int(args[1]) if len(args) > 1 else 80
        count = int(args[2]) if len(args) > 2 else 4
    except ValueError:
        port, count = 80, 4

    count = min(count, 20)

    # Resolv
    try:
        ip = _socket.gethostbyname(host)
    except _socket.gaierror as exc:
        _w(f"  {_C.RED}DNS error: {exc}{_C.RESET}\n\n"); return

    _header(f"net.ping  —  {host}:{port}")
    _row("Host",    f"{host} ({ip})")
    _row("Port",    str(port))
    _row("Pakiety", str(count))
    _sep()
    _w(f"\n  {_C.DIM}{'Seq':<6}{'Status':<10}{'RTT':>10}  Pasek{_C.RESET}\n\n")

    times: list[float] = []
    lost  = 0

    for i in range(1, count + 1):
        t0 = _time_m.perf_counter()
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((ip, port))
            ms = (_time_m.perf_counter() - t0) * 1000
            s.close()
            times.append(ms)

            # Pasek wizualny (min 1 blok, max 30 = 300 ms; skala: 1 blok = 10 ms)
            color   = _C.BGREEN if ms < 100 else (_C.BYELLOW if ms < 300 else _C.RED)
            bar_len = max(1, min(int(ms / 10), 30))
            bar     = color + "█" * bar_len + _C.RESET
            _w(f"  {i:<6}{'ok':<10}{ms:>9.2f}ms  {bar}\n")
        except Exception as exc:
            lost += 1
            ms = (_time_m.perf_counter() - t0) * 1000
            _w(f"  {i:<6}{_C.RED}{'timeout':<10}{_C.RESET}{ms:>9.2f}ms\n")

        if i < count:
            _time_m.sleep(0.5)

    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Statystyki{_C.RESET}\n\n")
    if times:
        _row("Min RTT",    f"{_C.BGREEN}{min(times):.2f} ms{_C.RESET}")
        _row("Max RTT",    f"{max(times):.2f} ms")
        _row("Avg RTT",    f"{sum(times)/len(times):.2f} ms")
        jitter = max(times) - min(times)
        _row("Jitter",     f"{jitter:.2f} ms")
    recv  = len(times)
    loss  = (lost / count * 100) if count else 0
    color = _C.BGREEN if loss == 0 else (_C.BYELLOW if loss < 50 else _C.RED)
    _row("Utrata",     f"{color}{lost}/{count} ({loss:.0f}%){_C.RESET}")
    _w("\n")


# ── sec.* — security / crypto ─────────────────────────────────────────────────

import hashlib as _hashlib
import base64 as _base64
import os as _os
import secrets as _secrets
import uuid as _uuid_mod


def _sec_hash_file_or_str(algo: str, target: str) -> str:
    """Zwraca hex-digest dla pliku lub ciągu znaków."""
    h = _hashlib.new(algo)
    import pathlib as _pathlib
    p = _pathlib.Path(target)
    if p.exists() and p.is_file():
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest(), "file"
    else:
        h.update(target.encode())
        return h.hexdigest(), "string"


def _cmd_sec_hash_sha1(args: list[str], terminal) -> None:
    """sec.hash.sha1 <tekst|plik>"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} sec.hash.sha1 <tekst|plik>\n")
        return
    target = " ".join(args)
    _header("sec.hash.sha1")
    digest, src = _sec_hash_file_or_str("sha1", target)
    _row("Wejście", f"{target!r}  {_C.DIM}({src}){_C.RESET}")
    _row("SHA-1", f"{_C.BGREEN}{digest}{_C.RESET}")
    _w("\n")


def _cmd_sec_hash_sha256(args: list[str], terminal) -> None:
    """sec.hash.sha256 <tekst|plik>"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} sec.hash.sha256 <tekst|plik>\n")
        return
    target = " ".join(args)
    _header("sec.hash.sha256")
    digest, src = _sec_hash_file_or_str("sha256", target)
    _row("Wejście", f"{target!r}  {_C.DIM}({src}){_C.RESET}")
    _row("SHA-256", f"{_C.BGREEN}{digest}{_C.RESET}")
    _w("\n")


def _cmd_sec_hash_md5(args: list[str], terminal) -> None:
    """sec.hash.md5 <tekst|plik>"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} sec.hash.md5 <tekst|plik>\n")
        return
    target = " ".join(args)
    _header("sec.hash.md5")
    digest, src = _sec_hash_file_or_str("md5", target)
    _row("Wejście", f"{target!r}  {_C.DIM}({src}){_C.RESET}")
    _row("MD5", f"{_C.BGREEN}{digest}{_C.RESET}")
    _w(f"  {_C.DIM}⚠  MD5 nie jest zalecany do celów bezpieczeństwa{_C.RESET}\n\n")


def _cmd_sec_encode_base64(args: list[str], terminal) -> None:
    """sec.encode.base64 <tekst>"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} sec.encode.base64 <tekst>\n")
        return
    text = " ".join(args)
    _header("sec.encode.base64")
    encoded = _base64.b64encode(text.encode()).decode()
    _row("Wejście", repr(text))
    _row("Base64", f"{_C.BGREEN}{encoded}{_C.RESET}")
    _w("\n")


def _cmd_sec_decode_base64(args: list[str], terminal) -> None:
    """sec.decode.base64 <zakodowany_tekst>"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} sec.decode.base64 <zakodowany_tekst>\n")
        return
    text = " ".join(args)
    _header("sec.decode.base64")
    try:
        decoded = _base64.b64decode(text.encode()).decode(errors="replace")
        _row("Wejście (Base64)", repr(text))
        _row("Wynik", f"{_C.BGREEN}{decoded}{_C.RESET}")
    except Exception as exc:
        _row("Wejście", repr(text))
        _w(f"  {_C.RED}Błąd dekodowania: {exc}{_C.RESET}\n")
    _w("\n")


def _cmd_sec_rand_bytes(args: list[str], terminal) -> None:
    """sec.rand.bytes [liczba=16]"""
    try:
        n = int(args[0]) if args else 16
        if not (1 <= n <= 4096):
            raise ValueError
    except ValueError:
        _w(f"  {_C.RED}Błąd: liczba bajtów musi być z zakresu 1–4096.{_C.RESET}\n\n")
        return
    _header("sec.rand.bytes")
    raw = _secrets.token_bytes(n)
    hex_str = raw.hex()
    b64_str = _base64.b64encode(raw).decode()
    _row("Bajty", str(n))
    _row("Hex", f"{_C.BGREEN}{hex_str}{_C.RESET}")
    _row("Base64", f"{_C.BCYAN}{b64_str}{_C.RESET}")
    _w("\n")


def _cmd_sec_rand_int(args: list[str], terminal) -> None:
    """sec.rand.int <min> <max>"""
    if len(args) < 2:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} sec.rand.int <min> <max>\n")
        return
    try:
        lo, hi = int(args[0]), int(args[1])
        if lo > hi:
            lo, hi = hi, lo
    except ValueError:
        _w(f"  {_C.RED}Błąd: min i max muszą być liczbami całkowitymi.{_C.RESET}\n\n")
        return
    _header("sec.rand.int")
    value = _secrets.randbelow(hi - lo + 1) + lo
    _row("Zakres", f"{lo} – {hi}")
    _row("Wylosowano", f"{_C.BGREEN}{value}{_C.RESET}")
    _w("\n")


def _cmd_sec_uuid(args: list[str], terminal) -> None:
    """sec.uuid — generuje UUID4"""
    _header("sec.uuid")
    uid = _uuid_mod.uuid4()
    _row("UUID4", f"{_C.BGREEN}{uid}{_C.RESET}")
    _row("Wariant", "RFC 4122")
    _row("Wersja", "4  (losowy)")
    _w("\n")


# ── data.* — parsing / serialization ─────────────────────────────────────────

import json as _json
import csv as _csv
import re as _re
import io as _io

# yaml — opcjonalny (PyYAML); lazy-import z komunikatem przy braku
def _get_yaml():
    try:
        import yaml as _yaml_mod
        return _yaml_mod
    except ImportError:
        return None


# ── helpers ───────────────────────────────────────────────────────────────────

def _data_pretty_value(obj, indent: int = 0) -> None:
    """Rekurencyjny printer dla zagnieżdżonych struktur (dict/list/scalar)."""
    pad = "  " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                _w(f"{pad}  {_C.BCYAN}{k}{_C.RESET}:\n")
                _data_pretty_value(v, indent + 1)
            else:
                _w(f"{pad}  {_C.BCYAN}{k:<24}{_C.RESET}{_data_scalar(v)}\n")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                _w(f"{pad}  {_C.DIM}[{i}]{_C.RESET}\n")
                _data_pretty_value(v, indent + 1)
            else:
                _w(f"{pad}  {_C.DIM}[{i}]{_C.RESET}  {_data_scalar(v)}\n")
    else:
        _w(f"{pad}  {_data_scalar(obj)}\n")


def _data_scalar(v) -> str:
    if isinstance(v, bool):
        return f"{_C.BMAGENTA}{v}{_C.RESET}"
    if isinstance(v, (int, float)):
        return f"{_C.BYELLOW}{v}{_C.RESET}"
    if v is None:
        return f"{_C.DIM}null{_C.RESET}"
    s = str(v)
    display = (s[:80] + f" {_C.DIM}…(+{len(s)-80}){_C.RESET}") if len(s) > 80 else s
    return f"{_C.BWHITE}{display}{_C.RESET}"


def _data_type_label(obj) -> str:
    if isinstance(obj, dict):
        return f"dict  ({len(obj)} kluczy)"
    if isinstance(obj, list):
        return f"list  ({len(obj)} elementów)"
    return type(obj).__name__


# ── data.json.load ────────────────────────────────────────────────────────────

def _cmd_data_json_load(args: list[str], terminal) -> None:
    """data.json.load <plik|'ciąg JSON'>"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} data.json.load <plik|'ciąg JSON'>\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    data.json.load dane.json\n")
        _w(f"    data.json.load '{{\"klucz\": 42}}'\n\n")
        return

    source = " ".join(args)
    _header("data.json.load")

    # Czy to plik?
    import pathlib as _pathlib
    p = _pathlib.Path(source)
    if p.exists() and p.is_file():
        try:
            text = p.read_text(encoding="utf-8")
            src_label = f"plik: {source}"
        except Exception as exc:
            _w(f"  {_C.RED}Błąd odczytu pliku: {exc}{_C.RESET}\n\n"); return
    else:
        text = source
        src_label = "ciąg znaków"

    try:
        obj = _json.loads(text)
    except _json.JSONDecodeError as exc:
        _w(f"  {_C.RED}Błąd parsowania JSON: {exc}{_C.RESET}\n\n"); return

    _row("Źródło",  src_label)
    _row("Typ",     _data_type_label(obj))
    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Zawartość{_C.RESET}\n\n")
    _data_pretty_value(obj)
    _w("\n")


# ── data.json.dump ────────────────────────────────────────────────────────────

def _cmd_data_json_dump(args: list[str], terminal) -> None:
    """data.json.dump <wyrażenie Python> [plik_wyj]"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} data.json.dump <wyrażenie Python> [plik_wyj]\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    data.json.dump {{\"a\": 1, \"b\": [2, 3]}}\n")
        _w(f"    data.json.dump [1,2,3] wynik.json\n\n")
        return

    _header("data.json.dump")

    # Ostatni arg — opcjonalny plik wyjściowy
    raw = " ".join(args)
    out_file = None
    # Sprawdź czy ostatni token wygląda jak nazwa pliku
    parts = args
    if len(parts) >= 2 and parts[-1].endswith(".json") and not parts[-1].startswith(("{", "[")):
        out_file = parts[-1]
        raw = " ".join(parts[:-1])

    try:
        obj = eval(raw, {"__builtins__": {}})  # noqa: S307 – ograniczone env
    except Exception as exc:
        _w(f"  {_C.RED}Błąd ewaluacji wyrażenia: {exc}{_C.RESET}\n\n"); return

    try:
        result = _json.dumps(obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as exc:
        _w(f"  {_C.RED}Błąd serializacji: {exc}{_C.RESET}\n\n"); return

    _row("Typ wejścia", _data_type_label(obj))
    _row("Długość JSON", f"{len(result)} znaków")

    if out_file:
        try:
            import pathlib as _pathlib
            _pathlib.Path(out_file).write_text(result, encoding="utf-8")
            _row("Zapisano do", f"{_C.BGREEN}{out_file}{_C.RESET}")
        except Exception as exc:
            _w(f"  {_C.RED}Błąd zapisu: {exc}{_C.RESET}\n\n"); return
    else:
        _sep()
        _w(f"\n  {_C.BBLUE}{_C.BOLD}JSON{_C.RESET}\n\n")
        for line in result.splitlines():
            _w(f"  {_C.BWHITE}{line}{_C.RESET}\n")

    _w("\n")


# ── data.yaml.load ────────────────────────────────────────────────────────────

def _cmd_data_yaml_load(args: list[str], terminal) -> None:
    """data.yaml.load <plik|'ciąg YAML'>"""
    _yaml = _get_yaml()
    if _yaml is None:
        _w(f"  {_C.RED}Moduł 'yaml' (PyYAML) nie jest zainstalowany.{_C.RESET}\n")
        _w(f"  {_C.DIM}Zainstaluj: pip install pyyaml{_C.RESET}\n\n")
        return

    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} data.yaml.load <plik|'ciąg YAML'>\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    data.yaml.load config.yaml\n")
        _w(f"    data.yaml.load 'klucz: wartość'\n\n")
        return

    source = " ".join(args)
    _header("data.yaml.load")

    import pathlib as _pathlib
    p = _pathlib.Path(source)
    if p.exists() and p.is_file():
        try:
            text = p.read_text(encoding="utf-8")
            src_label = f"plik: {source}"
        except Exception as exc:
            _w(f"  {_C.RED}Błąd odczytu: {exc}{_C.RESET}\n\n"); return
    else:
        text = source
        src_label = "ciąg znaków"

    try:
        obj = _yaml.safe_load(text)
    except _yaml.YAMLError as exc:
        _w(f"  {_C.RED}Błąd parsowania YAML: {exc}{_C.RESET}\n\n"); return

    _row("Źródło", src_label)
    _row("Typ",    _data_type_label(obj) if obj is not None else "null (pusty)")
    _sep()
    _w(f"\n  {_C.BBLUE}{_C.BOLD}Zawartość{_C.RESET}\n\n")
    if obj is not None:
        _data_pretty_value(obj)
    else:
        _w(f"  {_C.DIM}(brak danych){_C.RESET}\n")
    _w("\n")


# ── data.yaml.dump ────────────────────────────────────────────────────────────

def _cmd_data_yaml_dump(args: list[str], terminal) -> None:
    """data.yaml.dump <wyrażenie Python> [plik_wyj]"""
    _yaml = _get_yaml()
    if _yaml is None:
        _w(f"  {_C.RED}Moduł 'yaml' (PyYAML) nie jest zainstalowany.{_C.RESET}\n")
        _w(f"  {_C.DIM}Zainstaluj: pip install pyyaml{_C.RESET}\n\n")
        return

    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} data.yaml.dump <wyrażenie Python> [plik_wyj]\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    data.yaml.dump {{\"host\": \"localhost\", \"port\": 8080}}\n")
        _w(f"    data.yaml.dump [\"a\",\"b\"] wynik.yaml\n\n")
        return

    _header("data.yaml.dump")

    parts = args
    out_file = None
    if len(parts) >= 2 and (parts[-1].endswith(".yaml") or parts[-1].endswith(".yml")) \
            and not parts[-1].startswith(("{", "[")):
        out_file = parts[-1]
        parts = parts[:-1]

    raw = " ".join(parts)
    try:
        obj = eval(raw, {"__builtins__": {}})  # noqa: S307
    except Exception as exc:
        _w(f"  {_C.RED}Błąd ewaluacji wyrażenia: {exc}{_C.RESET}\n\n"); return

    try:
        result = _yaml.dump(obj, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except Exception as exc:
        _w(f"  {_C.RED}Błąd serializacji: {exc}{_C.RESET}\n\n"); return

    _row("Typ wejścia",  _data_type_label(obj))
    _row("Długość YAML", f"{len(result)} znaków")

    if out_file:
        try:
            import pathlib as _pathlib
            _pathlib.Path(out_file).write_text(result, encoding="utf-8")
            _row("Zapisano do", f"{_C.BGREEN}{out_file}{_C.RESET}")
        except Exception as exc:
            _w(f"  {_C.RED}Błąd zapisu: {exc}{_C.RESET}\n\n"); return
    else:
        _sep()
        _w(f"\n  {_C.BBLUE}{_C.BOLD}YAML{_C.RESET}\n\n")
        for line in result.splitlines():
            _w(f"  {_C.BWHITE}{line}{_C.RESET}\n")

    _w("\n")


# ── data.csv.read ─────────────────────────────────────────────────────────────

def _cmd_data_csv_read(args: list[str], terminal) -> None:
    """data.csv.read <plik> [max_wierszy=20] [delimiter=,]"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} data.csv.read <plik> [max_wierszy=20] [delimiter=,]\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    data.csv.read dane.csv\n")
        _w(f"    data.csv.read dane.csv 50\n")
        _w(f"    data.csv.read dane.tsv 10 \\t\n\n")
        return

    filepath = args[0]
    max_rows  = 20
    delimiter = ","
    if len(args) >= 2:
        try:
            max_rows = int(args[1])
        except ValueError:
            pass
    if len(args) >= 3:
        delimiter = args[2].replace("\\t", "\t")

    _header("data.csv.read")

    import pathlib as _pathlib
    p = _pathlib.Path(filepath)
    if not p.exists():
        _w(f"  {_C.RED}Plik nie istnieje: {filepath}{_C.RESET}\n\n"); return

    try:
        with p.open(newline="", encoding="utf-8") as fh:
            reader = _csv.reader(fh, delimiter=delimiter)
            rows = list(reader)
    except Exception as exc:
        _w(f"  {_C.RED}Błąd odczytu CSV: {exc}{_C.RESET}\n\n"); return

    if not rows:
        _w(f"  {_C.DIM}Plik jest pusty.{_C.RESET}\n\n"); return

    header = rows[0]
    data   = rows[1:]
    total  = len(data)
    shown  = min(max_rows, total)

    _row("Plik",       filepath)
    _row("Kolumny",    f"{len(header)}")
    _row("Wiersze",    f"{total}  (pokazuję: {shown})")
    _row("Delimiter",  repr(delimiter))
    _sep()

    # Oblicz szerokości kolumn
    col_w = [len(str(h)) for h in header]
    for row in data[:shown]:
        for i, cell in enumerate(row):
            if i < len(col_w):
                col_w[i] = max(col_w[i], min(len(str(cell)), 24))

    # Nagłówek
    _w("\n  ")
    for i, h in enumerate(header):
        w = col_w[i] if i < len(col_w) else 12
        _w(f"{_C.BCYAN}{_C.BOLD}{str(h)[:w]:<{w}}{_C.RESET}  ")
    _w("\n  ")
    for i in range(len(header)):
        w = (col_w[i] if i < len(col_w) else 12)
        _w(f"{_C.DIM}{'─'*w}{_C.RESET}  ")
    _w("\n")

    # Dane
    for row in data[:shown]:
        _w("  ")
        for i, cell in enumerate(row):
            w = col_w[i] if i < len(col_w) else 12
            s = str(cell)
            display = (s[:w-1] + "…") if len(s) > w else s
            _w(f"{_C.BWHITE}{display:<{w}}{_C.RESET}  ")
        _w("\n")

    if total > shown:
        _w(f"\n  {_C.DIM}… i jeszcze {total - shown} wierszy{_C.RESET}\n")
    _w("\n")


# ── data.csv.write ────────────────────────────────────────────────────────────

def _cmd_data_csv_write(args: list[str], terminal) -> None:
    """data.csv.write <plik> <wyrażenie Python: lista list lub lista dict>"""
    if len(args) < 2:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} data.csv.write <plik> <wyrażenie Python>\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    data.csv.write wynik.csv [[\"imie\",\"wiek\"],[\"Anna\",30],[\"Bob\",25]]\n")
        _w(f"    data.csv.write dane.csv [{{\"imie\":\"Anna\",\"wiek\":30}}]\n\n")
        return

    filepath = args[0]
    raw      = " ".join(args[1:])
    _header("data.csv.write")

    try:
        obj = eval(raw, {"__builtins__": {}})  # noqa: S307
    except Exception as exc:
        _w(f"  {_C.RED}Błąd ewaluacji wyrażenia: {exc}{_C.RESET}\n\n"); return

    if not isinstance(obj, list):
        _w(f"  {_C.RED}Wyrażenie musi być listą (list of lists lub list of dicts).{_C.RESET}\n\n")
        return

    try:
        buf = _io.StringIO()
        if obj and isinstance(obj[0], dict):
            fieldnames = list(obj[0].keys())
            writer = _csv.DictWriter(buf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(obj)
            row_count = len(obj)
            col_count = len(fieldnames)
        else:
            writer = _csv.writer(buf)
            writer.writerows(obj)
            row_count = len(obj)
            col_count = max((len(r) for r in obj if isinstance(r, (list, tuple))), default=0)

        content = buf.getvalue()
        import pathlib as _pathlib
        _pathlib.Path(filepath).write_text(content, encoding="utf-8")
    except Exception as exc:
        _w(f"  {_C.RED}Błąd zapisu CSV: {exc}{_C.RESET}\n\n"); return

    _row("Plik",    f"{_C.BGREEN}{filepath}{_C.RESET}")
    _row("Wiersze", str(row_count))
    _row("Kolumny", str(col_count))
    _row("Rozmiar", f"{len(content)} znaków")
    _w(f"\n  {_C.BGREEN}✓{_C.RESET} Zapisano pomyślnie.\n\n")


# ── data.regex.match ──────────────────────────────────────────────────────────

def _cmd_data_regex_match(args: list[str], terminal) -> None:
    """data.regex.match <wzorzec> <tekst>"""
    if len(args) < 2:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} data.regex.match <wzorzec> <tekst>\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    data.regex.match ^\\d+ 123abc\n")
        _w(f"    data.regex.match '(\\w+)@(\\w+)' user@example\n\n")
        return

    pattern = args[0]
    text    = " ".join(args[1:])
    _header("data.regex.match")

    _row("Wzorzec", f"{_C.BYELLOW}{pattern}{_C.RESET}")
    _row("Tekst",   repr(text))
    _sep()

    try:
        m = _re.match(pattern, text)
    except _re.error as exc:
        _w(f"\n  {_C.RED}Błąd wzorca regex: {exc}{_C.RESET}\n\n"); return

    if m:
        _w(f"\n  {_C.BGREEN}✓ Dopasowanie znalezione{_C.RESET}\n\n")
        _row("Dopasowany tekst", f"{_C.BGREEN}{m.group(0)!r}{_C.RESET}")
        _row("Zakres (span)",    f"{m.start()} – {m.end()}")
        if m.lastindex:
            _sep()
            _w(f"\n  {_C.BBLUE}Grupy{_C.RESET}\n")
            for i, g in enumerate(m.groups(), start=1):
                _row(f"  Grupa {i}", f"{_C.BWHITE}{g!r}{_C.RESET}")
        if m.groupdict():
            _sep()
            _w(f"\n  {_C.BBLUE}Grupy nazwane{_C.RESET}\n")
            for name, val in m.groupdict().items():
                _row(f"  {name}", f"{_C.BWHITE}{val!r}{_C.RESET}")
    else:
        _w(f"\n  {_C.RED}✗ Brak dopasowania{_C.RESET}\n")
    _w("\n")


# ── data.regex.find ───────────────────────────────────────────────────────────

def _cmd_data_regex_find(args: list[str], terminal) -> None:
    """data.regex.find <wzorzec> <tekst>"""
    if len(args) < 2:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} data.regex.find <wzorzec> <tekst>\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    data.regex.find \\d+ 'cena: 12 zł, rabat: 5 zł'\n")
        _w(f"    data.regex.find '[A-Z][a-z]+' 'Anna i Piotr'\n\n")
        return

    pattern = args[0]
    text    = " ".join(args[1:])
    _header("data.regex.find")

    _row("Wzorzec", f"{_C.BYELLOW}{pattern}{_C.RESET}")
    _row("Tekst",   repr(text[:80] + ("…" if len(text) > 80 else "")))
    _sep()

    try:
        matches = list(_re.finditer(pattern, text))
    except _re.error as exc:
        _w(f"\n  {_C.RED}Błąd wzorca regex: {exc}{_C.RESET}\n\n"); return

    _w(f"\n  {_C.BBLUE}{_C.BOLD}Wyniki{_C.RESET}  ({len(matches)} dopasowań)\n\n")

    if not matches:
        _w(f"  {_C.DIM}Brak dopasowań.{_C.RESET}\n")
    else:
        _w(f"  {_C.DIM}{'#':<5}{'Tekst':<30}{'Zakres':<18}{'Grupy'}{_C.RESET}\n\n")
        for i, m in enumerate(matches[:50]):
            grp = m.groups()
            grp_s = ", ".join(repr(g) for g in grp) if grp else "—"
            span_s = f"{m.start()}–{m.end()}"
            txt_s  = m.group(0)
            display = (txt_s[:27] + "…") if len(txt_s) > 28 else txt_s
            _w(f"  {_C.DIM}{i+1:<5}{_C.RESET}"
               f"{_C.BGREEN}{display:<30}{_C.RESET}"
               f"{_C.DIM}{span_s:<18}{_C.RESET}"
               f"{_C.BCYAN}{grp_s}{_C.RESET}\n")
        if len(matches) > 50:
            _w(f"\n  {_C.DIM}… i jeszcze {len(matches)-50} dopasowań{_C.RESET}\n")

    _w("\n")


# ── Menu CML ──────────────────────────────────────────────────────────────────

# ── math.* — math / utils ─────────────────────────────────────────────────────

import math as _math_mod
import ast as _ast
import operator as _operator
import random as _random_mod
import statistics as _statistics


# ── math.eval — bezpieczny AST evaluator ──────────────────────────────────────

_MATH_SAFE_NAMES: dict = {
    # stałe
    "pi": _math_mod.pi, "e": _math_mod.e, "tau": _math_mod.tau,
    "inf": _math_mod.inf, "nan": _math_mod.nan,
    # funkcje jednoarg.
    "abs": abs, "round": round, "int": int, "float": float,
    "sqrt": _math_mod.sqrt, "cbrt": getattr(_math_mod, "cbrt", lambda x: x ** (1/3)),
    "exp": _math_mod.exp, "log": _math_mod.log, "log2": _math_mod.log2,
    "log10": _math_mod.log10,
    "sin": _math_mod.sin, "cos": _math_mod.cos, "tan": _math_mod.tan,
    "asin": _math_mod.asin, "acos": _math_mod.acos, "atan": _math_mod.atan,
    "sinh": _math_mod.sinh, "cosh": _math_mod.cosh, "tanh": _math_mod.tanh,
    "ceil": _math_mod.ceil, "floor": _math_mod.floor, "trunc": _math_mod.trunc,
    "factorial": _math_mod.factorial, "gcd": _math_mod.gcd,
    "degrees": _math_mod.degrees, "radians": _math_mod.radians,
    "hypot": _math_mod.hypot, "atan2": _math_mod.atan2,
    "pow": pow, "min": min, "max": max, "sum": sum,
}

_MATH_SAFE_OPS = {
    _ast.Add: _operator.add,
    _ast.Sub: _operator.sub,
    _ast.Mult: _operator.mul,
    _ast.Div: _operator.truediv,
    _ast.FloorDiv: _operator.floordiv,
    _ast.Mod: _operator.mod,
    _ast.Pow: _operator.pow,
    _ast.USub: _operator.neg,
    _ast.UAdd: _operator.pos,
}


def _math_eval_node(node):
    """Rekurencyjny bezpieczny evaluator węzłów AST."""
    if isinstance(node, _ast.Expression):
        return _math_eval_node(node.body)
    if isinstance(node, _ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"Niedozwolona stała: {node.value!r}")
    if isinstance(node, _ast.Name):
        if node.id in _MATH_SAFE_NAMES:
            return _MATH_SAFE_NAMES[node.id]
        raise ValueError(f"Nieznana nazwa: {node.id!r}")
    if isinstance(node, _ast.BinOp):
        op = _MATH_SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Niedozwolony operator: {type(node.op).__name__}")
        left  = _math_eval_node(node.left)
        right = _math_eval_node(node.right)
        return op(left, right)
    if isinstance(node, _ast.UnaryOp):
        op = _MATH_SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Niedozwolony operator: {type(node.op).__name__}")
        return op(_math_eval_node(node.operand))
    if isinstance(node, _ast.Call):
        func = _math_eval_node(node.func)
        if not callable(func):
            raise ValueError("Wynik nie jest funkcją")
        pos_args = [_math_eval_node(a) for a in node.args]
        kw_args  = {k.arg: _math_eval_node(k.value) for k in node.keywords}
        return func(*pos_args, **kw_args)
    if isinstance(node, _ast.Attribute):
        raise ValueError("Dostęp do atrybutów jest niedozwolony")
    raise ValueError(f"Niedozwolony węzeł AST: {type(node).__name__}")


def _safe_math_eval(expr: str):
    try:
        tree = _ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Błąd składni: {exc}") from exc
    return _math_eval_node(tree)


def _cmd_math_eval(args: list[str], terminal) -> None:
    """math.eval <wyrażenie>"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} math.eval <wyrażenie>\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    math.eval 2 + 2\n")
        _w(f"    math.eval sqrt(144) + pi\n")
        _w(f"    math.eval sin(pi/6) * 100\n")
        _w(f"    math.eval factorial(10)\n")
        _w(f"    math.eval log(1024, 2)\n\n")
        _w(f"  {_C.DIM}Dostępne: pi, e, tau, inf | abs sqrt cbrt exp log log2 log10\n")
        _w(f"           sin cos tan asin acos atan sinh cosh tanh\n")
        _w(f"           ceil floor trunc round factorial gcd degrees radians\n")
        _w(f"           hypot atan2 pow min max sum{_C.RESET}\n\n")
        return

    expr = " ".join(args)
    _header("math.eval")
    _row("Wyrażenie", f"{_C.BYELLOW}{expr}{_C.RESET}")

    try:
        result = _safe_math_eval(expr)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        _w(f"\n  {_C.RED}Błąd: {exc}{_C.RESET}\n\n")
        return

    # Formatowanie wyniku
    if isinstance(result, float):
        if result == int(result) and abs(result) < 1e15:
            fmt = f"{result:.1f}  {_C.DIM}({int(result)}){_C.RESET}"
        elif abs(result) > 1e12 or (abs(result) < 1e-6 and result != 0.0):
            fmt = f"{result:.6e}"
        else:
            fmt = f"{result:.10g}"
    elif isinstance(result, complex):
        fmt = f"{result}"
    else:
        fmt = str(result)

    _row("Wynik", f"{_C.BGREEN}{_C.BOLD}{fmt}{_C.RESET}")

    # Dodatkowe reprezentacje dla int/float
    if isinstance(result, (int, float)) and not _math_mod.isnan(result) \
            and not _math_mod.isinf(result):
        _sep()
        v = int(result) if isinstance(result, float) and result == int(result) else result
        if isinstance(v, int) and 0 < v < 2**64:
            _row("Hex",    f"{_C.DIM}0x{v:X}{_C.RESET}")
            _row("Bin",    f"{_C.DIM}0b{v:b}{_C.RESET}" if v < 2**16 else f"{_C.DIM}({v.bit_length()} bitów){_C.RESET}")
        if isinstance(result, float):
            _row("Precyzja (repr)", repr(result))
    _w("\n")


# ── math.rand ─────────────────────────────────────────────────────────────────

def _cmd_math_rand(args: list[str], terminal) -> None:
    """math.rand [int|float|gauss] [min/mu] [max/sigma] [ile=1]"""
    _header("math.rand  —  Losowe liczby")

    mode  = "float"
    a_val = None
    b_val = None
    count = 1

    # Parsowanie args
    positional = []
    for a in args:
        al = a.lower()
        if al in ("int", "float", "gauss"):
            mode = al
        else:
            try:
                positional.append(float(a))
            except ValueError:
                _w(f"  {_C.RED}Nieznany argument: {a!r}{_C.RESET}\n\n"); return

    if len(positional) >= 1:
        a_val = positional[0]
    if len(positional) >= 2:
        b_val = positional[1]
    if len(positional) >= 3:
        count = max(1, min(int(positional[2]), 100))

    _row("Tryb",   f"{_C.BYELLOW}{mode}{_C.RESET}")

    if mode == "int":
        lo = int(a_val) if a_val is not None else 0
        hi = int(b_val) if b_val is not None else 100
        if lo > hi:
            lo, hi = hi, lo
        _row("Zakres",  f"{lo} – {hi}")
        _row("Ile",     str(count))
        _sep()
        results = [_random_mod.randint(lo, hi) for _ in range(count)]
        for r in results:
            bar = "█" * min(int((r - lo) / max(hi - lo, 1) * 30), 30)
            _w(f"  {_C.BGREEN}{r:>12}{_C.RESET}  {_C.DIM}{bar}{_C.RESET}\n")

    elif mode == "gauss":
        mu    = a_val if a_val is not None else 0.0
        sigma = b_val if b_val is not None else 1.0
        _row("Mu (średnia)",  f"{mu}")
        _row("Sigma (odch.)", f"{sigma}")
        _row("Ile",           str(count))
        _sep()
        results = [_random_mod.gauss(mu, sigma) for _ in range(count)]
        for r in results:
            _w(f"  {_C.BGREEN}{r:>16.6f}{_C.RESET}\n")
        if count > 1:
            _sep()
            _row("Min",  f"{min(results):.6f}")
            _row("Max",  f"{max(results):.6f}")
            _row("Avg",  f"{sum(results)/len(results):.6f}")

    else:  # float
        lo = a_val if a_val is not None else 0.0
        hi = b_val if b_val is not None else 1.0
        if lo > hi:
            lo, hi = hi, lo
        _row("Zakres",  f"{lo} – {hi}")
        _row("Ile",     str(count))
        _sep()
        results = [_random_mod.uniform(lo, hi) for _ in range(count)]
        for r in results:
            frac = (r - lo) / max(hi - lo, 1e-15)
            bar  = "█" * min(int(frac * 30), 30)
            _w(f"  {_C.BGREEN}{r:>18.8f}{_C.RESET}  {_C.DIM}{bar}{_C.RESET}\n")

    _w("\n")


# ── math.stats ────────────────────────────────────────────────────────────────

def _cmd_math_stats(args: list[str], terminal) -> None:
    """math.stats <n1> <n2> … | <wyrażenie Python: lista>"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} math.stats <n1> <n2> … | <lista Python>\n\n")
        _w(f"  {_C.DIM}Przykłady:{_C.RESET}\n")
        _w(f"    math.stats 1 2 3 4 5\n")
        _w(f"    math.stats 10.5 20 30.2 15 8\n")
        _w(f"    math.stats [1,2,3,4,5,6,7,8,9,10]\n\n")
        return

    _header("math.stats  —  Statystyki")

    # Spróbuj sparsować jako listę Python jeśli zaczyna się od [
    raw = " ".join(args)
    nums: list[float] = []
    if raw.strip().startswith("["):
        try:
            obj = eval(raw, {"__builtins__": {}})  # noqa: S307
            nums = [float(x) for x in obj]
        except Exception as exc:
            _w(f"  {_C.RED}Błąd parsowania listy: {exc}{_C.RESET}\n\n"); return
    else:
        for tok in args:
            try:
                nums.append(float(tok))
            except ValueError:
                _w(f"  {_C.RED}Nie można sparsować liczby: {tok!r}{_C.RESET}\n\n"); return

    if len(nums) < 1:
        _w(f"  {_C.RED}Lista jest pusta.{_C.RESET}\n\n"); return

    n = len(nums)
    _row("Liczba wartości", str(n))
    _row("Wartości", (str(nums[:8])[:-1] + ", …]") if n > 8 else str(nums))
    _sep()

    mn  = min(nums)
    mx  = max(nums)
    avg = sum(nums) / n
    med = _statistics.median(nums)

    _row("Min",    f"{_C.BGREEN}{mn:g}{_C.RESET}")
    _row("Max",    f"{_C.BYELLOW}{mx:g}{_C.RESET}")
    _row("Suma",   f"{sum(nums):g}")
    _row("Średnia (avg)",   f"{_C.BCYAN}{avg:.6g}{_C.RESET}")
    _row("Mediana",         f"{_C.BCYAN}{med:g}{_C.RESET}")

    if n >= 2:
        stdev  = _statistics.stdev(nums)
        pstdev = _statistics.pstdev(nums)
        var    = _statistics.variance(nums)
        _row("Odch. std (próbka)", f"{stdev:.6g}")
        _row("Odch. std (popul.)", f"{pstdev:.6g}")
        _row("Wariancja",          f"{var:.6g}")

    if n >= 4:
        q1  = _statistics.quantiles(nums, n=4)[0]
        q3  = _statistics.quantiles(nums, n=4)[2]
        iqr = q3 - q1
        _row("Q1 (25%)",  f"{q1:g}")
        _row("Q3 (75%)",  f"{q3:g}")
        _row("IQR",       f"{iqr:g}")

    # Wizualny histogram (ASCII, 10 kubełków)
    if n >= 3:
        _sep()
        _w(f"\n  {_C.BBLUE}{_C.BOLD}Histogram (10 kubełków){_C.RESET}\n\n")
        buckets = 10
        step    = (mx - mn) / buckets if mx != mn else 1
        counts  = [0] * buckets
        for v in nums:
            idx = min(int((v - mn) / step), buckets - 1)
            counts[idx] += 1
        max_cnt = max(counts) or 1
        bar_w   = 28
        for i, cnt in enumerate(counts):
            lo_b = mn + i * step
            hi_b = lo_b + step
            bar  = "█" * int(cnt / max_cnt * bar_w)
            pct  = cnt / n * 100
            _w(f"  {_C.DIM}{lo_b:>10.4g} – {hi_b:<10.4g}{_C.RESET}"
               f"  {_C.BGREEN}{bar:<{bar_w}}{_C.RESET}"
               f"  {_C.DIM}{cnt:3d}  ({pct:.1f}%){_C.RESET}\n")

    _w("\n")


# ── math.convert.bytes ────────────────────────────────────────────────────────

_BYTE_UNITS = {
    "b":   1,
    "kb":  1024,
    "mb":  1024**2,
    "gb":  1024**3,
    "tb":  1024**4,
    "pb":  1024**5,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}


def _cmd_math_convert_bytes(args: list[str], terminal) -> None:
    """math.convert.bytes <wartość> [jednostka=B]"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} math.convert.bytes <wartość> [jednostka]\n\n")
        _w(f"  {_C.DIM}Jednostki: B  KB  MB  GB  TB  PB\n")
        _w(f"  Przykłady:\n")
        _w(f"    math.convert.bytes 1073741824\n")
        _w(f"    math.convert.bytes 1.5 GB\n")
        _w(f"    math.convert.bytes 512 MB\n\n")
        return

    _header("math.convert.bytes")

    try:
        value = float(args[0])
    except ValueError:
        _w(f"  {_C.RED}Błąd: nieprawidłowa wartość {args[0]!r}{_C.RESET}\n\n"); return

    unit = args[1].lower() if len(args) >= 2 else "b"
    factor = _BYTE_UNITS.get(unit)
    if factor is None:
        _w(f"  {_C.RED}Nieznana jednostka: {args[1]!r}. Dostępne: B KB MB GB TB PB{_C.RESET}\n\n"); return

    total_bytes = value * factor

    _row("Wejście",  f"{value:g} {unit.upper()}")
    _row("Bajty",    f"{total_bytes:,.0f} B")
    _sep()

    labels = [("B", 1), ("KB", 1024), ("MB", 1024**2),
              ("GB", 1024**3), ("TB", 1024**4), ("PB", 1024**5)]

    for label, fac in labels:
        converted = total_bytes / fac
        if converted >= 0.001 or fac == 1:
            # Wyróżnij "naturalną" jednostkę
            if 0.9 <= converted < 1024:
                _row(label, f"{_C.BGREEN}{_C.BOLD}{converted:.4g}{_C.RESET}")
            else:
                _row(label, f"{_C.DIM}{converted:.6g}{_C.RESET}")

    # Pasek wizualny (relatywny do TB)
    _sep()
    _w(f"\n  {_C.BBLUE}Skala{_C.RESET}\n\n")
    scale_items = [
        ("1 KB",   1024),
        ("1 MB",   1024**2),
        ("1 GB",   1024**3),
        ("1 TB",   1024**4),
    ]
    ref = max(total_bytes, 1)
    for lbl, ref_b in scale_items:
        ratio = min(total_bytes / ref_b, 9999)
        marker = f"{ratio:.2f}×" if ratio < 10000 else ">9999×"
        color  = _C.BGREEN if ratio >= 1 else _C.DIM
        _w(f"  {_C.DIM}{lbl:<8}{_C.RESET}  {color}{marker:>10}{_C.RESET}\n")

    _w("\n")


# ── math.convert.time ─────────────────────────────────────────────────────────

_TIME_UNITS: dict[str, float] = {
    "ns":  1e-9,
    "us":  1e-6,
    "µs":  1e-6,
    "ms":  1e-3,
    "s":   1.0,
    "sec": 1.0,
    "min": 60.0,
    "m":   60.0,
    "h":   3600.0,
    "hr":  3600.0,
    "d":   86400.0,
    "day": 86400.0,
    "w":   604800.0,
    "week":604800.0,
    "yr":  31_557_600.0,   # rok juliański
    "year":31_557_600.0,
}


def _cmd_math_convert_time(args: list[str], terminal) -> None:
    """math.convert.time <wartość> [jednostka=s]"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} math.convert.time <wartość> [jednostka]\n\n")
        _w(f"  {_C.DIM}Jednostki: ns  µs/us  ms  s  min  h  d  w  yr\n")
        _w(f"  Przykłady:\n")
        _w(f"    math.convert.time 3661\n")
        _w(f"    math.convert.time 1.5 h\n")
        _w(f"    math.convert.time 500 ms\n")
        _w(f"    math.convert.time 2 w\n\n")
        return

    _header("math.convert.time")

    try:
        value = float(args[0])
    except ValueError:
        _w(f"  {_C.RED}Błąd: nieprawidłowa wartość {args[0]!r}{_C.RESET}\n\n"); return

    unit = args[1].lower() if len(args) >= 2 else "s"
    factor = _TIME_UNITS.get(unit)
    if factor is None:
        _w(f"  {_C.RED}Nieznana jednostka: {args[1]!r}. Dostępne: ns µs ms s min h d w yr{_C.RESET}\n\n"); return

    total_s = value * factor

    _row("Wejście",  f"{value:g} {unit}")
    _row("Sekundy",  f"{total_s:g} s")
    _sep()

    labels: list[tuple[str, float]] = [
        ("Nanosekundy  (ns)", 1e-9),
        ("Mikrosekundy (µs)", 1e-6),
        ("Milisekundy  (ms)", 1e-3),
        ("Sekundy      (s)",  1.0),
        ("Minuty       (min)",60.0),
        ("Godziny      (h)",  3600.0),
        ("Dni          (d)",  86400.0),
        ("Tygodnie     (w)",  604800.0),
        ("Lata         (yr)", 31_557_600.0),
    ]

    for label, fac in labels:
        converted = total_s / fac
        # Pokaż tylko sensowne zakresy
        if converted < 1e-9 and fac < 1:
            continue
        if converted > 1e9 and fac > 1:
            continue
        if 0.5 <= converted < 1000:
            color = f"{_C.BGREEN}{_C.BOLD}"
        else:
            color = _C.DIM
        _row(label, f"{color}{converted:.6g}{_C.RESET}")

    # Rozkład HH:MM:SS.mmm jeśli >= 1s
    if total_s >= 1.0:
        _sep()
        _w(f"\n  {_C.BBLUE}Rozkład{_C.RESET}\n\n")
        total_ms   = int(round(total_s * 1000))
        ms_part    = total_ms % 1000
        total_sec  = total_ms // 1000
        years, rem = divmod(total_sec, 31_557_600)
        days,  rem = divmod(rem, 86400)
        hours, rem = divmod(rem, 3600)
        mins,  sec = divmod(rem, 60)
        parts = []
        if years: parts.append(f"{years} rok/lat")
        if days:  parts.append(f"{days} dni")
        parts.append(f"{hours:02d}:{mins:02d}:{sec:02d}.{ms_part:03d}")
        _row("Czytelnie", f"{_C.BWHITE}{' '.join(parts)}{_C.RESET}")

    _w("\n")


# ── proc.* / term.* — process & terminal ─────────────────────────────────────

import threading as _threading
import shutil as _shutil
import itertools as _itertools

# ─────────────────────────────────────────────────────────────────────────────
# Globalny rejestr tasków (thread-safe przez GIL + lock)
# ─────────────────────────────────────────────────────────────────────────────

_TASK_LOCK: _threading.Lock = _threading.Lock()
_TASK_REGISTRY: dict[int, dict] = {}   # id → {name, thread, status, result, error, started, ended}
_TASK_COUNTER: _itertools.count = _itertools.count(1)

# Statusy tasku
_TS_PENDING  = "pending"
_TS_RUNNING  = "running"
_TS_DONE     = "done"
_TS_ERROR    = "error"
_TS_KILLED   = "killed"

# Aktywne schematy kolorów (modyfikowalne przez term.color)
_COLOR_SCHEME: str = "default"

_COLOR_SCHEMES: dict[str, dict] = {
    "default": {
        "accent":  "\x1b[96m",   # bright cyan
        "ok":      "\x1b[92m",   # bright green
        "warn":    "\x1b[93m",   # bright yellow
        "err":     "\x1b[91m",   # bright red
        "dim":     "\x1b[2m",
        "bold":    "\x1b[1m",
        "hi":      "\x1b[97m",   # bright white
        "info":    "\x1b[94m",   # bright blue
        "special": "\x1b[95m",   # bright magenta
    },
    "dark": {
        "accent":  "\x1b[36m",   # cyan
        "ok":      "\x1b[32m",   # green
        "warn":    "\x1b[33m",   # yellow
        "err":     "\x1b[31m",   # red
        "dim":     "\x1b[2m",
        "bold":    "\x1b[1m",
        "hi":      "\x1b[37m",   # white
        "info":    "\x1b[34m",   # blue
        "special": "\x1b[35m",   # magenta
    },
    "light": {
        "accent":  "\x1b[34m",   # blue (czytelny na białym)
        "ok":      "\x1b[32m",   # green
        "warn":    "\x1b[33m",   # yellow
        "err":     "\x1b[31m",   # red
        "dim":     "\x1b[2m",
        "bold":    "\x1b[1m",
        "hi":      "\x1b[30m",   # black
        "info":    "\x1b[35m",   # magenta
        "special": "\x1b[36m",   # cyan
    },
    "mono": {
        "accent":  "\x1b[1m",
        "ok":      "\x1b[1m",
        "warn":    "\x1b[4m",    # underline
        "err":     "\x1b[7m",    # reverse
        "dim":     "\x1b[2m",
        "bold":    "\x1b[1m",
        "hi":      "\x1b[1m",
        "info":    "\x1b[1m",
        "special": "\x1b[4m",
    },
}


def _cs(key: str) -> str:
    """Zwraca kod ANSI dla bieżącego schematu kolorów."""
    return _COLOR_SCHEMES.get(_COLOR_SCHEME, _COLOR_SCHEMES["default"]).get(key, "")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers tasków
# ─────────────────────────────────────────────────────────────────────────────

def _task_status_color(status: str) -> str:
    return {
        _TS_PENDING: _C.DIM,
        _TS_RUNNING: _C.BGREEN,
        _TS_DONE:    _C.BCYAN,
        _TS_ERROR:   _C.RED,
        _TS_KILLED:  _C.BYELLOW,
    }.get(status, _C.RESET)


def _task_status_icon(status: str) -> str:
    return {
        _TS_PENDING: "○",
        _TS_RUNNING: "●",
        _TS_DONE:    "✓",
        _TS_ERROR:   "✗",
        _TS_KILLED:  "⊘",
    }.get(status, "?")


def _task_elapsed(meta: dict) -> str:
    start = meta.get("started")
    end   = meta.get("ended")
    if start is None:
        return "—"
    finish = end if end is not None else time.monotonic()
    secs = finish - start
    if secs < 1:
        return f"{secs*1000:.0f}ms"
    return _seconds_fmt(secs)


# ─────────────────────────────────────────────────────────────────────────────
# proc.list
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_proc_list(args: list[str], terminal) -> None:
    """proc.list [all|running|done] — lista tasków terminala."""
    _header("proc.list  —  Taski terminala")

    filter_mode = args[0].lower() if args else "all"
    valid = ("all", "running", "done", "error", "killed", "pending")
    if filter_mode not in valid:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} proc.list [all|running|done|error|killed|pending]\n\n")
        return

    with _TASK_LOCK:
        tasks = list(_TASK_REGISTRY.items())

    # Własne wątki Pythona jako kontekst
    py_threads = {t.ident: t for t in _threading.enumerate()}

    # Filtrowanie
    if filter_mode != "all":
        tasks = [(tid, m) for tid, m in tasks if m["status"] == filter_mode]

    # Podsumowanie nagłówkowe
    all_tasks = list(_TASK_REGISTRY.items())
    counts = {s: sum(1 for _, m in all_tasks if m["status"] == s)
              for s in (_TS_RUNNING, _TS_DONE, _TS_ERROR, _TS_KILLED, _TS_PENDING)}

    _w(f"  {_C.DIM}Łącznie: {len(all_tasks)}  "
       f"{_C.BGREEN}●{counts[_TS_RUNNING]} running{_C.RESET}  "
       f"{_C.DIM}✓{counts[_TS_DONE]} done  "
       f"✗{counts[_TS_ERROR]} error  "
       f"⊘{counts[_TS_KILLED]} killed{_C.RESET}\n\n")

    if not tasks:
        _w(f"  {_C.DIM}Brak tasków")
        if filter_mode != "all":
            _w(f" (filtr: {filter_mode})")
        _w(f".{_C.RESET}\n\n")
        _w(f"  {_C.DIM}Użyj {_C.RESET}proc.spawn <nazwa> <wyrażenie>{_C.DIM} aby uruchomić task.{_C.RESET}\n\n")
        return

    # Nagłówek tabeli
    _w(f"  {_C.DIM}{'ID':<5}{'Status':<12}{'Nazwa':<20}{'Elapsed':<12}{'Wynik / Błąd'}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'─'*5}  {'─'*10}  {'─'*18}  {'─'*10}  {'─'*24}{_C.RESET}\n")

    for tid, meta in sorted(tasks):
        st     = meta["status"]
        icon   = _task_status_icon(st)
        color  = _task_status_color(st)
        name   = meta["name"][:18]
        elapsed= _task_elapsed(meta)

        result_s = ""
        if st == _TS_DONE:
            r = meta.get("result")
            result_s = f"{_C.DIM}{str(r)[:28]}{_C.RESET}" if r is not None else f"{_C.DIM}OK{_C.RESET}"
        elif st == _TS_ERROR:
            result_s = f"{_C.RED}{str(meta.get('error','?'))[:28]}{_C.RESET}"
        elif st == _TS_RUNNING:
            # Sprawdź czy wątek jeszcze żyje
            t = meta.get("thread")
            alive = t.is_alive() if isinstance(t, _threading.Thread) else False
            result_s = f"{_C.BGREEN}{'alive' if alive else 'finishing…'}{_C.RESET}"

        _w(f"  {_C.BCYAN}{tid:<5}{_C.RESET}"
           f"{color}{icon} {st:<10}{_C.RESET}"
           f"{_C.BWHITE}{name:<20}{_C.RESET}"
           f"{_C.DIM}{elapsed:<12}{_C.RESET}"
           f"{result_s}\n")

    # Wątki systemowe Pythona (dodatkowy kontekst)
    _sep()
    _w(f"\n  {_C.BBLUE}Wątki Pythona ({len(py_threads)}){_C.RESET}\n\n")
    main_t = _threading.main_thread()
    for ident, t in sorted(py_threads.items(), key=lambda x: x[0] or 0):
        is_main  = (t is main_t)
        is_daemon= t.daemon
        label    = f"{_C.BGREEN}[main]{_C.RESET}" if is_main else (f"{_C.DIM}[daemon]{_C.RESET}" if is_daemon else "")
        _w(f"    {_C.DIM}{str(ident or '?'):>12}{_C.RESET}  "
           f"{_C.BWHITE}{t.name:<28}{_C.RESET}  "
           f"{'alive' if t.is_alive() else _C.DIM+'dead'+_C.RESET:<8}  "
           f"{label}\n")
    _w("\n")


# ─────────────────────────────────────────────────────────────────────────────
# proc.spawn
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_proc_spawn(args: list[str], terminal) -> None:
    """proc.spawn <nazwa> <wyrażenie Python>"""
    if len(args) < 2:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} proc.spawn <nazwa> <wyrażenie Python>\n\n")
        _w(f"  {_C.DIM}Wyrażenie uruchamiane jest w osobnym wątku (threading.Thread).\n")
        _w(f"  Wynik zapisywany jest w rejestrze tasków.\n\n")
        _w(f"  Przykłady:\n")
        _w(f"    proc.spawn suma sum(range(1000000))\n")
        _w(f"    proc.spawn pi 355/113\n")
        _w(f"    proc.spawn wolny __import__('time').sleep(5) or 'gotowe'\n\n")
        return

    name = args[0]
    expr = " ".join(args[1:])

    # Przydziel ID
    with _TASK_LOCK:
        tid = next(_TASK_COUNTER)
        meta: dict = {
            "name":    name,
            "expr":    expr,
            "status":  _TS_PENDING,
            "thread":  None,
            "result":  None,
            "error":   None,
            "started": None,
            "ended":   None,
        }
        _TASK_REGISTRY[tid] = meta

    def _worker():
        with _TASK_LOCK:
            _TASK_REGISTRY[tid]["status"]  = _TS_RUNNING
            _TASK_REGISTRY[tid]["started"] = time.monotonic()
        try:
            result = eval(expr)  # noqa: S307 – świadomy wybór; task API, nie web input
            with _TASK_LOCK:
                _TASK_REGISTRY[tid]["result"] = result
                _TASK_REGISTRY[tid]["status"] = _TS_DONE
        except Exception as exc:
            with _TASK_LOCK:
                _TASK_REGISTRY[tid]["error"]  = str(exc)
                _TASK_REGISTRY[tid]["status"] = _TS_ERROR
        finally:
            with _TASK_LOCK:
                _TASK_REGISTRY[tid]["ended"] = time.monotonic()

    t = _threading.Thread(target=_worker, name=f"cml-task-{tid}-{name}", daemon=True)
    with _TASK_LOCK:
        meta["thread"] = t

    t.start()

    _header("proc.spawn")
    _row("Task ID",    f"{_C.BCYAN}{_C.BOLD}{tid}{_C.RESET}")
    _row("Nazwa",      name)
    _row("Wyrażenie",  expr[:60] + ("…" if len(expr) > 60 else ""))
    _row("Status",     f"{_C.BGREEN}● running{_C.RESET}")
    _row("Wątek",      t.name)
    _w(f"\n  {_C.DIM}Sprawdź wynik: {_C.RESET}proc.status {tid}\n\n")


# ─────────────────────────────────────────────────────────────────────────────
# proc.kill
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_proc_kill(args: list[str], terminal) -> None:
    """proc.kill <id> [all]"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} proc.kill <id>  |  proc.kill all\n\n")
        _w(f"  {_C.DIM}Uwaga: wątki Pythona nie obsługują twardego kill.\n")
        _w(f"  Task oznaczany jest jako 'killed' — wątek daemon wygasa sam.{_C.RESET}\n\n")
        return

    _header("proc.kill")

    if args[0].lower() == "all":
        with _TASK_LOCK:
            targets = [(tid, m) for tid, m in _TASK_REGISTRY.items()
                       if m["status"] in (_TS_RUNNING, _TS_PENDING)]

        if not targets:
            _w(f"  {_C.DIM}Brak aktywnych tasków do zatrzymania.{_C.RESET}\n\n")
            return

        killed = 0
        for tid, meta in targets:
            with _TASK_LOCK:
                _TASK_REGISTRY[tid]["status"] = _TS_KILLED
                _TASK_REGISTRY[tid]["ended"]  = time.monotonic()
            _w(f"  {_C.BYELLOW}⊘{_C.RESET} Task {_C.BCYAN}{tid}{_C.RESET}  "
               f"{_C.DIM}{meta['name']}{_C.RESET}  → killed\n")
            killed += 1

        _w(f"\n  {_C.DIM}Oznaczono {killed} tasków jako killed.\n")
        _w(f"  Wątki daemon wygasną po zakończeniu wyrażenia.{_C.RESET}\n\n")
        return

    # Pojedynczy ID
    try:
        tid = int(args[0])
    except ValueError:
        _w(f"  {_C.RED}Błąd: nieprawidłowe ID {args[0]!r}. Podaj liczbę lub 'all'.{_C.RESET}\n\n")
        return

    with _TASK_LOCK:
        meta = _TASK_REGISTRY.get(tid)

    if meta is None:
        _w(f"  {_C.RED}Task #{tid} nie istnieje.{_C.RESET}\n\n")
        return

    st = meta["status"]
    if st in (_TS_DONE, _TS_ERROR, _TS_KILLED):
        color = _task_status_color(st)
        _w(f"  {_C.DIM}Task #{tid} już zakończony: {color}{st}{_C.RESET}\n\n")
        return

    with _TASK_LOCK:
        _TASK_REGISTRY[tid]["status"] = _TS_KILLED
        _TASK_REGISTRY[tid]["ended"]  = time.monotonic()

    _row("Task ID",  str(tid))
    _row("Nazwa",    meta["name"])
    _row("Status",   f"{_C.BYELLOW}⊘ killed{_C.RESET}")
    _row("Elapsed",  _task_elapsed(meta))
    _w(f"\n  {_C.DIM}Wątek daemon ({meta['thread'].name if meta.get('thread') else '?'}) "
       f"wygasi się po zakończeniu wyrażenia.{_C.RESET}\n\n")


# ─────────────────────────────────────────────────────────────────────────────
# proc.status
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_proc_status(args: list[str], terminal) -> None:
    """proc.status <id>"""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} proc.status <id>\n\n")
        return

    try:
        tid = int(args[0])
    except ValueError:
        _w(f"  {_C.RED}Błąd: nieprawidłowe ID {args[0]!r}{_C.RESET}\n\n")
        return

    with _TASK_LOCK:
        meta = _TASK_REGISTRY.get(tid)

    if meta is None:
        _w(f"  {_C.RED}Task #{tid} nie istnieje.{_C.RESET}\n\n")
        _w(f"  {_C.DIM}Użyj proc.list aby zobaczyć dostępne taski.{_C.RESET}\n\n")
        return

    st     = meta["status"]
    color  = _task_status_color(st)
    icon   = _task_status_icon(st)

    _header(f"proc.status  —  Task #{tid}")

    _row("ID",       f"{_C.BCYAN}{_C.BOLD}{tid}{_C.RESET}")
    _row("Nazwa",    meta["name"])
    _row("Status",   f"{color}{icon} {st}{_C.RESET}")
    _row("Elapsed",  _task_elapsed(meta))

    started = meta.get("started")
    ended   = meta.get("ended")
    if started is not None:
        _row("Uruchomiony", time.strftime("%H:%M:%S",
             time.localtime(time.time() - (time.monotonic() - started))))
    if ended is not None:
        _row("Zakończony",  time.strftime("%H:%M:%S",
             time.localtime(time.time() - (time.monotonic() - ended))))

    _sep()
    _w(f"\n  {_C.BBLUE}Wyrażenie{_C.RESET}\n")
    expr = meta.get("expr", "")
    # Zawijaj co 60 znaków
    for i in range(0, max(len(expr), 1), 60):
        _w(f"    {_C.BWHITE}{expr[i:i+60]}{_C.RESET}\n")

    if st == _TS_DONE:
        _sep()
        _w(f"\n  {_C.BBLUE}Wynik{_C.RESET}\n\n")
        result = meta.get("result")
        result_s = repr(result) if result is not None else "None"
        # Zawijaj długie wyniki
        for i in range(0, min(len(result_s), 240), 72):
            _w(f"    {_C.BGREEN}{result_s[i:i+72]}{_C.RESET}\n")
        if len(result_s) > 240:
            _w(f"    {_C.DIM}… (skrócono do 240 znaków){_C.RESET}\n")

    elif st == _TS_ERROR:
        _sep()
        _w(f"\n  {_C.BBLUE}Błąd{_C.RESET}\n\n")
        _w(f"    {_C.RED}{meta.get('error', '?')}{_C.RESET}\n")

    elif st == _TS_RUNNING:
        t = meta.get("thread")
        if isinstance(t, _threading.Thread):
            _sep()
            _w(f"\n  {_C.BBLUE}Wątek{_C.RESET}\n\n")
            _row("  Nazwa",   t.name)
            _row("  Daemon",  str(t.daemon))
            _row("  Alive",   f"{_C.BGREEN}tak{_C.RESET}" if t.is_alive()
                               else f"{_C.BYELLOW}nie (kończący){_C.RESET}")
            _row("  Ident",   str(t.ident))

    _w("\n")


# ─────────────────────────────────────────────────────────────────────────────
# term.clear
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_term_clear(args: list[str], terminal) -> None:
    """term.clear — czyści ekran terminala."""
    # ANSI: ED2 (erase entire display) + move cursor home
    _w("\x1b[2J\x1b[H")

    # Opcjonalnie: terminal może mieć własną metodę clear
    if hasattr(terminal, "clear"):
        try:
            terminal.clear()
        except Exception:
            pass

    # Potwierdzenie (widoczne przez chwilę)
    _w(f"{_C.DIM}  [ekran wyczyszczony]{_C.RESET}\n")


# ─────────────────────────────────────────────────────────────────────────────
# term.size
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_term_size(args: list[str], terminal) -> None:
    """term.size — rozmiar terminala (kolumny × wiersze)."""
    _header("term.size  —  Rozmiar terminala")

    cols_found  = None
    rows_found  = None
    method_used = "?"

    # 1. shutil.get_terminal_size (najbardziej przenośne)
    try:
        ts = _shutil.get_terminal_size(fallback=(0, 0))
        if ts.columns > 0 and ts.lines > 0:
            cols_found  = ts.columns
            rows_found  = ts.lines
            method_used = "shutil.get_terminal_size()"
    except Exception:
        pass

    # 2. os.get_terminal_size przez fd 1/0/2 (jeśli shutil dał fallback)
    if cols_found is None:
        for fd in (1, 0, 2):
            try:
                _os_m = importlib.import_module("os")
                ts = _os_m.get_terminal_size(fd)
                if ts.columns > 0:
                    cols_found  = ts.columns
                    rows_found  = ts.lines
                    method_used = f"os.get_terminal_size(fd={fd})"
                    break
            except Exception:
                pass

    # 3. ANSI DSR — zapytaj terminal o pozycję kursora (tylko TTY)
    #    Nie używamy, bo blokuje na nieinteraktywnych terminalach.

    # 4. Zmienna środowiskowa COLUMNS/LINES
    if cols_found is None:
        try:
            _os_m = importlib.import_module("os")
            c = int(_os_m.environ.get("COLUMNS", 0))
            r = int(_os_m.environ.get("LINES", 0))
            if c > 0 and r > 0:
                cols_found  = c
                rows_found  = r
                method_used = "env COLUMNS/LINES"
        except Exception:
            pass

    # 5. Hardcoded fallback
    if cols_found is None:
        cols_found  = 80
        rows_found  = 24
        method_used = "fallback (80×24)"

    _row("Kolumny (szerokość)", f"{_C.BGREEN}{_C.BOLD}{cols_found}{_C.RESET}")
    _row("Wiersze (wysokość)",  f"{_C.BGREEN}{_C.BOLD}{rows_found}{_C.RESET}")
    _row("Metoda",              f"{_C.DIM}{method_used}{_C.RESET}")

    # Wizualny pasek szerokości (w skali)
    _sep()
    _w(f"\n  {_C.BBLUE}Podgląd szerokości ({cols_found} kolumn){_C.RESET}\n\n")
    bar_len = min(cols_found, 72)  # ogranicz do 72 by zmieścić się w terminalu
    bar = "─" * bar_len
    _w(f"  {_C.DIM}│{_C.BCYAN}{bar}{_C.DIM}│{_C.RESET}")
    if cols_found > 72:
        _w(f"  {_C.DIM}(pokazano 72/{cols_found}){_C.RESET}")
    _w("\n\n")

    # Klasyczne rozmiary referencyjne
    _w(f"  {_C.BBLUE}Referencje{_C.RESET}\n")
    refs = [(80, 24, "VT100 / klasyczny"), (120, 30, "szerokoekranowy"),
            (132, 43, "IBM 3278"), (220, 50, "ultrawide")]
    for rc, rl, label in refs:
        match = "◀ bieżący" if rc == cols_found and rl == rows_found else ""
        color = _C.BGREEN if match else _C.DIM
        _w(f"  {color}{rc:>5}×{rl:<5}{_C.RESET}  {_C.DIM}{label}{_C.RESET}"
           f"  {_C.BGREEN}{match}{_C.RESET}\n")
    _w("\n")


# ─────────────────────────────────────────────────────────────────────────────
# term.title
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_term_title(args: list[str], terminal) -> None:
    """term.title <tytuł> — ustawia tytuł okna terminala."""
    if not args:
        _w(f"  {_C.BYELLOW}Użycie:{_C.RESET} term.title <tytuł>\n\n")
        _w(f"  {_C.DIM}Przykłady:\n")
        _w(f"    term.title CrossTerm v1.0\n")
        _w(f"    term.title 'Mój terminal'\n\n")
        return

    title = " ".join(args)
    _header("term.title")
    _row("Tytuł", f"{_C.BWHITE}{title}{_C.RESET}")

    methods_ok: list[str] = []
    methods_fail: list[str] = []

    # 1. ANSI OSC 0/2 (xterm, gnome-terminal, iTerm2, Windows Terminal, …)
    try:
        _w(f"\x1b]0;{title}\x07")   # OSC 0 — title + icon
        _w(f"\x1b]2;{title}\x07")   # OSC 2 — title only
        methods_ok.append("ANSI OSC 0/2 (\\x1b]0;…\\x07)")
    except Exception as exc:
        methods_fail.append(f"ANSI OSC: {exc}")

    # 2. Terminal object (jeśli CrossTerm udostępnia metodę)
    if hasattr(terminal, "set_title"):
        try:
            terminal.set_title(title)
            methods_ok.append("terminal.set_title()")
        except Exception as exc:
            methods_fail.append(f"terminal.set_title: {exc}")

    # 3. Atrybut title na obiekcie terminala (tańszy fallback)
    if hasattr(terminal, "title"):
        try:
            terminal.title = title
            methods_ok.append("terminal.title attribute")
        except Exception as exc:
            methods_fail.append(f"terminal.title: {exc}")

    _sep()
    if methods_ok:
        _w(f"\n  {_C.BGREEN}✓{_C.RESET} Wysłano przez:\n")
        for m in methods_ok:
            _w(f"    {_C.DIM}• {m}{_C.RESET}\n")
    if methods_fail:
        _w(f"\n  {_C.BYELLOW}⚠{_C.RESET}  Niepowodzenie:\n")
        for m in methods_fail:
            _w(f"    {_C.DIM}• {m}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Efekt widoczny tylko w terminalach obsługujących ANSI OSC.{_C.RESET}\n\n")


# ─────────────────────────────────────────────────────────────────────────────
# term.color
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_term_color(args: list[str], terminal) -> None:
    """term.color [schemat|list|demo] — zmienia schemat kolorów ANSI."""
    global _COLOR_SCHEME

    scheme_arg = args[0].lower() if args else "list"

    if scheme_arg == "list":
        _header("term.color  —  Schematy kolorów")
        _w(f"  {_C.DIM}Bieżący schemat: {_C.RESET}{_C.BCYAN}{_C.BOLD}{_COLOR_SCHEME}{_C.RESET}\n\n")
        _w(f"  {_C.DIM}{'Schemat':<12}{'Opis'}{_C.RESET}\n")
        _w(f"  {_C.DIM}{'─'*12}  {'─'*36}{_C.RESET}\n")
        descs = {
            "default": "jasne kolory (bright cyan/green/yellow) — domyślny",
            "dark":    "przyciemnione kolory — ciemne tła",
            "light":   "kolory dla jasnych teł (blue/green/red)",
            "mono":    "bez kolorów — bold/underline/reverse",
        }
        for name, desc in descs.items():
            marker = f"  {_C.BGREEN}◀ aktywny{_C.RESET}" if name == _COLOR_SCHEME else ""
            _w(f"  {_C.BCYAN}{name:<12}{_C.RESET}{_C.DIM}{desc}{_C.RESET}{marker}\n")
        _w(f"\n  {_C.DIM}Użycie: term.color <schemat>  |  term.color demo{_C.RESET}\n\n")
        return

    if scheme_arg == "demo":
        _header("term.color  —  Demo wszystkich schematów")
        demo_keys = ["accent", "ok", "warn", "err", "dim", "hi", "info", "special"]
        # Nagłówek
        _w(f"  {_C.DIM}{'Klucz':<12}")
        for sn in _COLOR_SCHEMES:
            _w(f"{sn:<14}")
        _w(f"{_C.RESET}\n  {_C.DIM}{'─'*12}")
        for _ in _COLOR_SCHEMES:
            _w(f"{'─'*13} ")
        _w(f"{_C.RESET}\n")
        for key in demo_keys:
            _w(f"  {_C.DIM}{key:<12}{_C.RESET}")
            for sn, scheme in _COLOR_SCHEMES.items():
                code = scheme.get(key, "")
                _w(f"{code}{'█ ' + key:<13}{_C.RESET} ")
            _w("\n")
        _w(f"\n  {_C.DIM}Bieżący: {_COLOR_SCHEME}{_C.RESET}\n\n")
        return

    # Zmiana schematu
    if scheme_arg not in _COLOR_SCHEMES:
        _w(f"  {_C.RED}Nieznany schemat: {scheme_arg!r}{_C.RESET}\n")
        _w(f"  {_C.DIM}Dostępne: {', '.join(_COLOR_SCHEMES)}{_C.RESET}\n\n")
        return

    prev = _COLOR_SCHEME
    _COLOR_SCHEME = scheme_arg

    _header("term.color")
    _row("Poprzedni",  f"{_C.DIM}{prev}{_C.RESET}")
    _row("Aktywny",    f"{_cs('accent')}{_C.BOLD}{_COLOR_SCHEME}{_C.RESET}")
    _sep()

    # Podgląd nowego schematu
    _w(f"\n  {_C.BBLUE}Podgląd{_C.RESET}\n\n")
    s = _COLOR_SCHEMES[_COLOR_SCHEME]
    previews = [
        ("accent",  "accent"),
        ("ok",      "ok / success"),
        ("warn",    "warning"),
        ("err",     "error"),
        ("dim",     "dim / secondary"),
        ("hi",      "highlight"),
        ("info",    "info"),
        ("special", "special"),
    ]
    for key, label in previews:
        code = s.get(key, "")
        _w(f"    {_C.DIM}{key:<10}{_C.RESET}  {code}{'█' * 6}  {label}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Schemat aktywny dla modułu sysadmin. Przywróć: term.color default{_C.RESET}\n\n")


# ══════════════════════════════════════════════════════════════════════════════
# admin.* — Admin / Management
# ══════════════════════════════════════════════════════════════════════════════

import json as _json
import datetime as _dt

# Wewnętrzne struktury danych (runtime-only, symulacja bez trwałego storage)
_ADMIN_USERS: dict[str, dict] = {
    "root":  {"role": "admin",  "created": "2025-01-01"},
    "guest": {"role": "guest",  "created": "2025-01-01"},
}
_ADMIN_ROLES: list[str] = ["admin", "operator", "viewer", "guest"]
_ADMIN_LOG:   list[str] = []
_ADMIN_CONFIG: dict[str, str] = {
    "log.level":       "INFO",
    "log.max_lines":   "500",
    "session.timeout": "3600",
    "theme":           "dark",
}
_ADMIN_PLUGINS: dict[str, dict] = {
    "sysadmin": {"status": "loaded",   "version": "1.1"},
    "nettools": {"status": "unloaded", "version": "0.9"},
    "devtools": {"status": "unloaded", "version": "0.5"},
}


def _admin_log_append(msg: str) -> None:
    """Dodaje wpis do logu admina z timestampem."""
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _ADMIN_LOG.append(f"[{ts}] {msg}")
    try:
        limit = int(_ADMIN_CONFIG.get("log.max_lines", "500"))
    except ValueError:
        limit = 500
    while len(_ADMIN_LOG) > limit:
        _ADMIN_LOG.pop(0)


# ── admin.users.list ──────────────────────────────────────────────────────────

def _cmd_admin_users_list(args: list[str], terminal) -> None:
    """admin.users.list — lista użytkowników terminala (wewnętrzna)."""
    _header("admin.users.list  —  Użytkownicy terminala")
    if not _ADMIN_USERS:
        _w(f"  {_C.DIM}Brak użytkowników.{_C.RESET}\n\n")
        return
    _w(f"  {_C.BOLD}{'Nazwa':<20}{'Rola':<14}{'Utworzony'}{_C.RESET}\n")
    _sep()
    for name, info in sorted(_ADMIN_USERS.items()):
        role  = info.get("role", "?")
        cr    = info.get("created", "—")
        color = _C.BYELLOW if role == "admin" else _C.BBLUE
        _w(f"  {_C.BCYAN}{name:<20}{_C.RESET}{color}{role:<14}{_C.RESET}{_C.DIM}{cr}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Łącznie: {len(_ADMIN_USERS)} użytkowników{_C.RESET}\n\n")


# ── admin.users.add ───────────────────────────────────────────────────────────

def _cmd_admin_users_add(args: list[str], terminal) -> None:
    """admin.users.add <nazwa> [rola] — dodaje użytkownika terminala."""
    if not args:
        _w(f"  {_C.RED}Brak argumentu. Użycie: admin.users.add <nazwa> [rola]{_C.RESET}\n\n")
        return
    name = args[0]
    role = args[1] if len(args) > 1 else "viewer"
    if name in _ADMIN_USERS:
        _w(f"  {_C.BYELLOW}Użytkownik {_C.BOLD}{name!r}{_C.RESET}{_C.BYELLOW} już istnieje.{_C.RESET}\n\n")
        return
    if role not in _ADMIN_ROLES:
        _w(f"  {_C.RED}Nieznana rola: {role!r}. Dostępne: {', '.join(_ADMIN_ROLES)}{_C.RESET}\n\n")
        return
    _ADMIN_USERS[name] = {"role": role, "created": _dt.date.today().isoformat()}
    _admin_log_append(f"users.add: {name!r} role={role}")
    _header("admin.users.add")
    _row("Użytkownik", f"{_C.BGREEN}{name}{_C.RESET}")
    _row("Rola",       f"{_C.BBLUE}{role}{_C.RESET}")
    _row("Status",     f"{_C.BGREEN}✓ Dodano{_C.RESET}")
    _w("\n")


# ── admin.users.rm ────────────────────────────────────────────────────────────

def _cmd_admin_users_rm(args: list[str], terminal) -> None:
    """admin.users.rm <nazwa> — usuwa użytkownika terminala."""
    if not args:
        _w(f"  {_C.RED}Brak argumentu. Użycie: admin.users.rm <nazwa>{_C.RESET}\n\n")
        return
    name = args[0]
    if name not in _ADMIN_USERS:
        _w(f"  {_C.RED}Użytkownik {name!r} nie istnieje.{_C.RESET}\n\n")
        return
    del _ADMIN_USERS[name]
    _admin_log_append(f"users.rm: {name!r}")
    _header("admin.users.rm")
    _row("Użytkownik", f"{_C.BYELLOW}{name}{_C.RESET}")
    _row("Status",     f"{_C.BGREEN}✓ Usunięto{_C.RESET}")
    _w("\n")


# ── admin.roles.list ──────────────────────────────────────────────────────────

def _cmd_admin_roles_list(args: list[str], terminal) -> None:
    """admin.roles.list — lista dostępnych ról terminala."""
    _header("admin.roles.list  —  Role terminala")
    _w(f"  {_C.BOLD}{'Rola':<16}{'Opis'}{_C.RESET}\n")
    _sep()
    desc_map = {
        "admin":    "pełny dostęp do wszystkich komend i konfiguracji",
        "operator": "zarządzanie procesami, logami i pluginami",
        "viewer":   "dostęp tylko do odczytu (fs.read, sys.*, net.*)",
        "guest":    "ograniczony dostęp demonstracyjny",
    }
    for role in _ADMIN_ROLES:
        desc  = desc_map.get(role, "—")
        color = _C.BYELLOW if role == "admin" else _C.BBLUE
        _w(f"  {color}{role:<16}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Łącznie: {len(_ADMIN_ROLES)} ról{_C.RESET}\n\n")


# ── admin.roles.set ───────────────────────────────────────────────────────────

def _cmd_admin_roles_set(args: list[str], terminal) -> None:
    """admin.roles.set <nazwa> <rola> — ustawia rolę użytkownika terminala."""
    if len(args) < 2:
        _w(f"  {_C.RED}Użycie: admin.roles.set <nazwa> <rola>{_C.RESET}\n\n")
        return
    name, role = args[0], args[1]
    if name not in _ADMIN_USERS:
        _w(f"  {_C.RED}Użytkownik {name!r} nie istnieje.{_C.RESET}\n\n")
        return
    if role not in _ADMIN_ROLES:
        _w(f"  {_C.RED}Nieznana rola: {role!r}. Dostępne: {', '.join(_ADMIN_ROLES)}{_C.RESET}\n\n")
        return
    old_role = _ADMIN_USERS[name]["role"]
    _ADMIN_USERS[name]["role"] = role
    _admin_log_append(f"roles.set: {name!r} {old_role!r} → {role!r}")
    _header("admin.roles.set")
    _row("Użytkownik", f"{_C.BCYAN}{name}{_C.RESET}")
    _row("Poprzednia", f"{_C.DIM}{old_role}{_C.RESET}")
    _row("Nowa rola",  f"{_C.BBLUE}{role}{_C.RESET}")
    _row("Status",     f"{_C.BGREEN}✓ Zaktualizowano{_C.RESET}")
    _w("\n")


# ── admin.log ─────────────────────────────────────────────────────────────────

def _cmd_admin_log(args: list[str], terminal) -> None:
    """admin.log [n] — logi systemowe terminala (ostatnie n wpisów, domyślnie 50)."""
    _header("admin.log  —  Logi systemowe")
    try:
        limit = int(args[0]) if args else 50
    except ValueError:
        limit = 50
    entries = _ADMIN_LOG[-limit:]
    if not entries:
        _w(f"  {_C.DIM}Log jest pusty.{_C.RESET}\n\n")
        return
    for entry in entries:
        if "ERROR" in entry or "CRIT" in entry:
            col = _C.RED
        elif "WARN" in entry:
            col = _C.BYELLOW
        else:
            col = _C.DIM
        _w(f"  {col}{entry}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Pokazano: {len(entries)} / {len(_ADMIN_LOG)} wpisów{_C.RESET}\n\n")


# ── admin.log.clear ───────────────────────────────────────────────────────────

def _cmd_admin_log_clear(args: list[str], terminal) -> None:
    """admin.log.clear — czyści log systemowy terminala."""
    count = len(_ADMIN_LOG)
    _ADMIN_LOG.clear()
    _admin_log_append("log.clear: log wyczyszczony")
    _header("admin.log.clear")
    _row("Usunięto wpisów", f"{_C.BYELLOW}{count}{_C.RESET}")
    _row("Status",          f"{_C.BGREEN}✓ Log wyczyszczony{_C.RESET}")
    _w("\n")


# ── admin.config.get ──────────────────────────────────────────────────────────

def _cmd_admin_config_get(args: list[str], terminal) -> None:
    """admin.config.get [klucz] — pobiera wartość konfiguracji terminala."""
    _header("admin.config.get  —  Konfiguracja")
    if args:
        key = args[0]
        if key in _ADMIN_CONFIG:
            _row(key, f"{_C.BGREEN}{_ADMIN_CONFIG[key]}{_C.RESET}")
        else:
            _w(f"  {_C.RED}Nieznany klucz: {key!r}{_C.RESET}\n")
            _w(f"  {_C.DIM}Dostępne klucze: {', '.join(sorted(_ADMIN_CONFIG))}{_C.RESET}\n")
    else:
        _w(f"  {_C.BOLD}{'Klucz':<24}{'Wartość'}{_C.RESET}\n")
        _sep()
        for k in sorted(_ADMIN_CONFIG):
            _row(k, f"{_C.BGREEN}{_ADMIN_CONFIG[k]}{_C.RESET}")
    _w("\n")


# ── admin.config.set ──────────────────────────────────────────────────────────

def _cmd_admin_config_set(args: list[str], terminal) -> None:
    """admin.config.set <klucz> <wartość> — ustawia wartość konfiguracji terminala."""
    if len(args) < 2:
        _w(f"  {_C.RED}Użycie: admin.config.set <klucz> <wartość>{_C.RESET}\n\n")
        return
    key, val = args[0], " ".join(args[1:])
    old_val = _ADMIN_CONFIG.get(key, "<nowy>")
    _ADMIN_CONFIG[key] = val
    _admin_log_append(f"config.set: {key!r} = {val!r} (poprz.: {old_val!r})")
    _header("admin.config.set")
    _row("Klucz",        f"{_C.BCYAN}{key}{_C.RESET}")
    _row("Poprzednio",   f"{_C.DIM}{old_val}{_C.RESET}")
    _row("Nowa wartość", f"{_C.BGREEN}{val}{_C.RESET}")
    _row("Status",       f"{_C.BGREEN}✓ Zapisano{_C.RESET}")
    _w("\n")


# ── admin.update ──────────────────────────────────────────────────────────────

def _cmd_admin_update(args: list[str], terminal) -> None:
    """admin.update — sprawdza i symuluje aktualizację modułów terminala."""
    _header("admin.update  —  Aktualizacja modułów")
    _w(f"  {_C.DIM}Sprawdzanie dostępnych aktualizacji…{_C.RESET}\n\n")
    updates = [
        ("sysadmin",  "1.0", "1.1", True),
        ("nettools",  "0.9", "0.9", False),
        ("devtools",  "0.5", "0.7", True),
        ("crossterm", "2.3", "2.4", True),
    ]
    any_update = False
    for mod, cur, new, has_upd in updates:
        if has_upd:
            any_update = True
            _w(f"  {_C.BGREEN}↑{_C.RESET}  {_C.BCYAN}{mod:<14}{_C.RESET}"
               f"{_C.DIM}{cur} → {_C.RESET}{_C.BGREEN}{new}{_C.RESET}\n")
        else:
            _w(f"  {_C.DIM}✓  {mod:<14}{cur} (aktualna){_C.RESET}\n")
    _sep()
    if any_update:
        _w(f"\n  {_C.BYELLOW}Dostępne aktualizacje. Uruchom ponownie terminal po aktualizacji.{_C.RESET}\n")
    else:
        _w(f"\n  {_C.BGREEN}Wszystkie moduły aktualne.{_C.RESET}\n")
    _admin_log_append("admin.update: sprawdzono aktualizacje")
    _w("\n")


# ── admin.plugins.list ────────────────────────────────────────────────────────

def _cmd_admin_plugins_list(args: list[str], terminal) -> None:
    """admin.plugins.list — lista zainstalowanych pluginów terminala."""
    _header("admin.plugins.list  —  Pluginy")
    _w(f"  {_C.BOLD}{'Plugin':<18}{'Status':<14}{'Wersja'}{_C.RESET}\n")
    _sep()
    for name, info in sorted(_ADMIN_PLUGINS.items()):
        status  = info.get("status", "?")
        version = info.get("version", "?")
        scol    = f"{_C.BGREEN}● loaded{_C.RESET}" if status == "loaded" else f"{_C.DIM}○ unloaded{_C.RESET}"
        _w(f"  {_C.BCYAN}{name:<18}{_C.RESET}{scol:<22}  {_C.DIM}v{version}{_C.RESET}\n")
    loaded = sum(1 for p in _ADMIN_PLUGINS.values() if p.get("status") == "loaded")
    _w(f"\n  {_C.DIM}Łącznie: {len(_ADMIN_PLUGINS)} pluginów, {loaded} załadowanych{_C.RESET}\n\n")


# ── admin.plugins.load ────────────────────────────────────────────────────────

def _cmd_admin_plugins_load(args: list[str], terminal) -> None:
    """admin.plugins.load <nazwa> — ładuje plugin terminala."""
    if not args:
        _w(f"  {_C.RED}Użycie: admin.plugins.load <nazwa>{_C.RESET}\n\n")
        return
    name = args[0]
    if name not in _ADMIN_PLUGINS:
        _w(f"  {_C.RED}Plugin {name!r} nie istnieje.{_C.RESET}\n")
        _w(f"  {_C.DIM}Dostępne: {', '.join(sorted(_ADMIN_PLUGINS))}{_C.RESET}\n\n")
        return
    if _ADMIN_PLUGINS[name]["status"] == "loaded":
        _w(f"  {_C.BYELLOW}Plugin {_C.BOLD}{name!r}{_C.RESET}{_C.BYELLOW} jest już załadowany.{_C.RESET}\n\n")
        return
    _ADMIN_PLUGINS[name]["status"] = "loaded"
    _admin_log_append(f"plugins.load: {name!r}")
    _header("admin.plugins.load")
    _row("Plugin", f"{_C.BCYAN}{name}{_C.RESET}")
    _row("Wersja", f"{_C.DIM}v{_ADMIN_PLUGINS[name]['version']}{_C.RESET}")
    _row("Status", f"{_C.BGREEN}● loaded{_C.RESET}")
    _w("\n")


# ── admin.plugins.unload ──────────────────────────────────────────────────────

def _cmd_admin_plugins_unload(args: list[str], terminal) -> None:
    """admin.plugins.unload <nazwa> — wyładowuje plugin terminala."""
    if not args:
        _w(f"  {_C.RED}Użycie: admin.plugins.unload <nazwa>{_C.RESET}\n\n")
        return
    name = args[0]
    if name not in _ADMIN_PLUGINS:
        _w(f"  {_C.RED}Plugin {name!r} nie istnieje.{_C.RESET}\n")
        _w(f"  {_C.DIM}Dostępne: {', '.join(sorted(_ADMIN_PLUGINS))}{_C.RESET}\n\n")
        return
    if _ADMIN_PLUGINS[name]["status"] == "unloaded":
        _w(f"  {_C.BYELLOW}Plugin {_C.BOLD}{name!r}{_C.RESET}{_C.BYELLOW} jest już wyładowany.{_C.RESET}\n\n")
        return
    _ADMIN_PLUGINS[name]["status"] = "unloaded"
    _admin_log_append(f"plugins.unload: {name!r}")
    _header("admin.plugins.unload")
    _row("Plugin", f"{_C.BCYAN}{name}{_C.RESET}")
    _row("Status", f"{_C.DIM}○ unloaded{_C.RESET}")
    _w("\n")


# ── Menu CML ──────────────────────────────────────────────────────────────────

def cml_menu() -> None:
    """Wyświetlane po wpisaniu nazwy modułu bez argumentów."""
    _w(f"\n{_C.BCYAN}{_C.BOLD}  SYSADMIN{_C.RESET}  {_C.DIM}System / Core Admin{_C.RESET}\n\n")

    rows = [
        ("sys.info",       "info o interpreterze, wersji, ścieżkach, build"),
        ("sys.env",        "zmienne środowiskowe  [filtr]"),
        ("sys.time",       "aktualny timestamp (unix, ISO, UTC, RFC…)"),
        ("sys.uptime",     "czas działania sesji terminala"),
        ("sys.clearcache", "czyści type cache, gc, importlib, history"),
        ("sys.modules",    "lista załadowanych modułów Pythona  [filtr]"),
        ("sys.mem",        "użycie pamięci (tracemalloc + getsizeof)"),
        ("sys.cpuclock",   "zegar CPU: process_time, perf_counter, pomiar"),
    ]
    for cmd, desc in rows:
        _w(f"  {_C.BBLUE}{cmd:<20}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BCYAN}{_C.BOLD}fs.*{_C.RESET}  {_C.DIM}System plików{_C.RESET}\n\n")
    fs_rows = [
        ("fs.ls",    "lista plików w katalogu  [katalog]"),
        ("fs.tree",  "drzewo katalogów  [katalog] [głębokość]"),
        ("fs.read",  "odczyt pliku  <plik> [max_linie]"),
        ("fs.write", "zapis pliku  <plik> <treść>"),
        ("fs.append","dopisanie do pliku  <plik> <treść>"),
        ("fs.touch", "tworzy pusty plik  <plik>"),
        ("fs.rm",    "usuwa plik  <plik>"),
        ("fs.mv",    "przenosi plik/katalog  <źródło> <cel>"),
        ("fs.cp",    "kopiuje plik/katalog  <źródło> <cel>"),
        ("fs.mkdir", "tworzy katalog (rekurencyjnie)  <katalog>"),
        ("fs.rmdir", "usuwa katalog rekurencyjnie  <katalog>"),
        ("fs.hash",  "hash pliku  <plik> [md5|sha1|sha256|sha512]"),
        ("fs.size",  "rozmiar pliku lub katalogu  <ścieżka>"),
        ("fs.find",  "wyszukuje pliki po wzorcu  <wzorzec> [katalog]"),
    ]
    for cmd, desc in fs_rows:
        _w(f"  {_C.BBLUE}{cmd:<20}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")
    _w(f"\n  {_C.BCYAN}{_C.BOLD}net.*{_C.RESET}  {_C.DIM}Sieć{_C.RESET}\n\n")
    net_rows = [
        ("net.http.get",    "HTTP GET  <url> [nagłówek:wartość …]"),
        ("net.http.head",   "HTTP HEAD — tylko nagłówki  <url>"),
        ("net.http.post",   "HTTP POST  <url> <klucz=wartość …>"),
        ("net.dns.resolve", "DNS lookup  <host> [rodzina: 4|6|all]"),
        ("net.ip.public",   "publiczne IP (odpytuje zewnętrzny serwis)"),
        ("net.ip.local",    "lokalne IP interfejsów sieciowych"),
        ("net.port.scan",   "skanowanie portów TCP  <host> <port[-port]> …"),
        ("net.ping",        "TCP ping (czas połączenia)  <host> [port] [liczba]"),
    ]
    for cmd, desc in net_rows:
        _w(f"  {_C.BBLUE}{cmd:<20}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BCYAN}{_C.BOLD}sec.*{_C.RESET}  {_C.DIM}Security / Crypto{_C.RESET}\n\n")
    sec_rows = [
        ("sec.hash.sha1",    "SHA-1 ciągu lub pliku  <tekst|plik>"),
        ("sec.hash.sha256",  "SHA-256 ciągu lub pliku  <tekst|plik>"),
        ("sec.hash.md5",     "MD5 ciągu lub pliku  <tekst|plik>"),
        ("sec.encode.base64","kodowanie Base64  <tekst>"),
        ("sec.decode.base64","dekodowanie Base64  <zakodowany_tekst>"),
        ("sec.rand.bytes",   "losowe bajty (hex + base64)  [liczba=16]"),
        ("sec.rand.int",     "losowa liczba całkowita  <min> <max>"),
        ("sec.uuid",         "generuje UUID4"),
    ]
    for cmd, desc in sec_rows:
        _w(f"  {_C.BBLUE}{cmd:<22}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BCYAN}{_C.BOLD}data.*{_C.RESET}  {_C.DIM}Data / Parsing{_C.RESET}\n\n")
    data_rows = [
        ("data.json.load",    "parsuje JSON z pliku lub ciągu  <plik|'json'>"),
        ("data.json.dump",    "serializuje do JSON  <wyrażenie> [plik.json]"),
        ("data.yaml.load",    "parsuje YAML z pliku lub ciągu  <plik|'yaml'>"),
        ("data.yaml.dump",    "serializuje do YAML  <wyrażenie> [plik.yaml]"),
        ("data.csv.read",     "odczytuje plik CSV  <plik> [max=20] [sep=,]"),
        ("data.csv.write",    "zapisuje CSV  <plik> <lista_list|lista_dict>"),
        ("data.regex.match",  "dopasowanie (od początku)  <wzorzec> <tekst>"),
        ("data.regex.find",   "wszystkie dopasowania  <wzorzec> <tekst>"),
    ]
    for cmd, desc in data_rows:
        _w(f"  {_C.BBLUE}{cmd:<22}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BCYAN}{_C.BOLD}math.*{_C.RESET}  {_C.DIM}Math / Utils{_C.RESET}\n\n")
    math_rows = [
        ("math.eval",          "bezpieczny evaluator wyrażeń (AST)  <wyrażenie>"),
        ("math.rand",          "losowe liczby  [int|float|gauss] [min] [max]"),
        ("math.stats",         "statystyki listy liczb  <n1> <n2> …"),
        ("math.convert.bytes", "konwersje bajtów  <wartość> [jednostka]"),
        ("math.convert.time",  "konwersje czasu  <wartość> [jednostka]"),
    ]
    for cmd, desc in math_rows:
        _w(f"  {_C.BBLUE}{cmd:<22}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BCYAN}{_C.BOLD}proc.*{_C.RESET}  {_C.DIM}Process / Tasks{_C.RESET}\n\n")
    proc_rows = [
        ("proc.list",   "lista aktywnych tasków terminala"),
        ("proc.kill",   "zatrzymuje task po ID  <id>"),
        ("proc.spawn",  "uruchamia task async  <nazwa> <wyrażenie>"),
        ("proc.status", "szczegółowy status tasku  <id>"),
    ]
    for cmd, desc in proc_rows:
        _w(f"  {_C.BBLUE}{cmd:<22}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BCYAN}{_C.BOLD}term.*{_C.RESET}  {_C.DIM}Terminal{_C.RESET}\n\n")
    term_rows = [
        ("term.clear",  "czyści ekran terminala"),
        ("term.size",   "rozmiar terminala (kolumny × wiersze)"),
        ("term.title",  "ustawia tytuł okna  <tytuł>"),
        ("term.color",  "schemat kolorów  [default|dark|light|mono|list]"),
    ]
    for cmd, desc in term_rows:
        _w(f"  {_C.BBLUE}{cmd:<22}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BCYAN}{_C.BOLD}admin.*{_C.RESET}  {_C.DIM}Admin / Management{_C.RESET}\n\n")
    admin_rows = [
        ("admin.users.list",     "lista użytkowników terminala"),
        ("admin.users.add",      "dodaje użytkownika  <nazwa> [rola]"),
        ("admin.users.rm",       "usuwa użytkownika  <nazwa>"),
        ("admin.roles.list",     "lista dostępnych ról"),
        ("admin.roles.set",      "ustawia rolę użytkownika  <nazwa> <rola>"),
        ("admin.log",            "logi systemowe terminala  [n]"),
        ("admin.log.clear",      "czyści log systemowy"),
        ("admin.config.get",     "pobiera konfigurację terminala  [klucz]"),
        ("admin.config.set",     "ustawia konfigurację  <klucz> <wartość>"),
        ("admin.update",         "sprawdza aktualizacje modułów terminala"),
        ("admin.plugins.list",   "lista zainstalowanych pluginów"),
        ("admin.plugins.load",   "ładuje plugin  <nazwa>"),
        ("admin.plugins.unload", "wyładowuje plugin  <nazwa>"),
    ]
    for cmd, desc in admin_rows:
        _w(f"  {_C.BBLUE}{cmd:<26}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BCYAN}{_C.BOLD}dev.*{_C.RESET}  {_C.DIM}DEBUG / DevTools{_C.RESET}\n\n")
    dev_rows = [
        ("dev.trace",     "stack trace bieżącego wątku  [n_ramek]"),
        ("dev.inspect",   "introspekcja obiektu  <wyrażenie>"),
        ("dev.benchmark", "pomiar czasu wykonania  <wyrażenie> [n=100]"),
        ("dev.profile",   "profilowanie cProfile  <wyrażenie> [top=20]"),
        ("dev.reload",    "przeładuj moduł Pythona  <nazwa>"),
        ("dev.sandbox",   "izolowane wykonanie kodu  <kod>"),
    ]
    for cmd, desc in dev_rows:
        _w(f"  {_C.BBLUE}{cmd:<22}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BCYAN}{_C.BOLD}pkg.*{_C.RESET}  {_C.DIM}Package / Module Management{_C.RESET}\n\n")
    pkg_rows = [
        ("pkg.list",    "lista zainstalowanych modułów CrossTerm"),
        ("pkg.install", "instalacja modułu  <url|ścieżka.zip>"),
        ("pkg.remove",  "usuwa moduł  <nazwa>"),
        ("pkg.update",  "aktualizuje moduł  <nazwa|all>"),
        ("pkg.info",    "szczegółowe informacje o module  <nazwa>"),
    ]
    for cmd, desc in pkg_rows:
        _w(f"  {_C.BBLUE}{cmd:<26}{_C.RESET}{_C.DIM}{desc}{_C.RESET}\n")
    _w("\n")


# ══════════════════════════════════════════════════════════════════════════════
# pkg.* — Package / Module Management
# ══════════════════════════════════════════════════════════════════════════════

import zipfile  as _zipfile
import urllib.request as _urllib_req
import urllib.parse   as _urllib_parse
import hashlib        as _hashlib_pkg
import tempfile       as _tempfile
import os             as _os_pkg
import shutil         as _shutil_pkg

# ── Rejestr zainstalowanych modułów (runtime) ─────────────────────────────────
# Struktura wpisu:
#   name        → str          identyfikator modułu (np. "sysadmin")
#   version     → str          aktualna wersja
#   source      → str          skąd pochodzi (URL lub ścieżka)
#   installed   → str          data instalacji ISO
#   description → str          opis jednolinijkowy
#   author      → str
#   size_kb     → int          przybliżony rozmiar
#   commands    → list[str]    eksportowane komendy CML
#   checksum    → str          sha256 źródła (jeśli znany)
#   status      → str          "active" | "disabled" | "error"

_PKG_REGISTRY: dict[str, dict] = {
    "sysadmin": {
        "version":     "1.3",
        "source":      "built-in",
        "installed":   "2025-01-01",
        "description": "System / Core Admin — interpreter, env, fs, net, sec, data, math, proc, term, admin, pkg",
        "author":      "crossterm",
        "size_kb":     131,
        "commands":    [
            "sys.*", "fs.*", "net.*", "sec.*",
            "data.*", "math.*", "proc.*", "term.*", "admin.*", "dev.*", "pkg.*",
        ],
        "checksum":    "built-in",
        "status":      "active",
    },
    "nettools": {
        "version":     "0.9",
        "source":      "https://crossterm.example/pkg/nettools-0.9.zip",
        "installed":   "2025-03-15",
        "description": "Rozszerzone narzędzia sieciowe: traceroute, whois, ssl-check",
        "author":      "crossterm",
        "size_kb":     24,
        "commands":    ["net.traceroute", "net.whois", "net.ssl.check"],
        "checksum":    "a3f1e8c2d9b047f6",
        "status":      "disabled",
    },
}

# Symulowany indeks pakietów (odpowiednik repozytorium)
_PKG_REMOTE_INDEX: dict[str, dict] = {
    "sysadmin":  {"latest": "1.2", "url": "built-in"},
    "nettools":  {"latest": "1.0", "url": "https://crossterm.example/pkg/nettools-1.0.zip"},
    "devtools":  {"latest": "0.7", "url": "https://crossterm.example/pkg/devtools-0.7.zip"},
    "datatools": {"latest": "0.3", "url": "https://crossterm.example/pkg/datatools-0.3.zip"},
    "uikit":     {"latest": "0.2", "url": "https://crossterm.example/pkg/uikit-0.2.zip"},
}


def _pkg_status_icon(status: str) -> str:
    return {
        "active":   f"{_C.BGREEN}●{_C.RESET}",
        "disabled": f"{_C.DIM}○{_C.RESET}",
        "error":    f"{_C.RED}✗{_C.RESET}",
    }.get(status, f"{_C.DIM}?{_C.RESET}")


def _pkg_sha256_of(path: str) -> str:
    h = _hashlib_pkg.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── pkg.list ──────────────────────────────────────────────────────────────────

def _cmd_pkg_list(args: list[str], terminal) -> None:
    """pkg.list [filtr] — lista zainstalowanych modułów CrossTerm."""
    _header("pkg.list  —  Zainstalowane moduły")

    filtr = args[0].lower() if args else ""
    pkgs  = {k: v for k, v in _PKG_REGISTRY.items()
              if not filtr or filtr in k.lower() or filtr in v.get("description","").lower()}

    if not pkgs:
        _w(f"  {_C.DIM}Brak wyników{' dla: ' + filtr if filtr else ''}.{_C.RESET}\n\n")
        return

    col_w = (18, 8, 10, 8)
    _w(f"  {_C.BOLD}"
       f"{'Moduł':<{col_w[0]}}{'Wersja':<{col_w[1]}}{'Status':<{col_w[2]}}{'Rozmiar':<{col_w[3]}}Opis"
       f"{_C.RESET}\n")
    _sep()

    active_count  = 0
    total_kb      = 0
    for name, info in sorted(pkgs.items()):
        status  = info.get("status", "?")
        icon    = _pkg_status_icon(status)
        ver     = info.get("version", "?")
        kb      = info.get("size_kb", 0)
        desc    = info.get("description", "")
        if len(desc) > 42:
            desc = desc[:39] + "…"
        total_kb += kb
        if status == "active":
            active_count += 1

        _w(f"  {icon} {_C.BCYAN}{name:<{col_w[0]-2}}{_C.RESET}"
           f"{_C.DIM}{ver:<{col_w[1]}}{_C.RESET}"
           f"{status:<{col_w[2]}}"
           f"{_C.DIM}{kb} KB{' ' * max(0, col_w[3]-len(str(kb))-3)}{_C.RESET}"
           f"{_C.DIM}{desc}{_C.RESET}\n")

    _sep()
    _w(f"\n  {_C.DIM}Łącznie: {len(pkgs)} modułów"
       f"  ·  aktywnych: {active_count}"
       f"  ·  rozmiar: {total_kb} KB{_C.RESET}\n\n")


# ── pkg.install ───────────────────────────────────────────────────────────────

def _cmd_pkg_install(args: list[str], terminal) -> None:
    """pkg.install <url|ścieżka.zip> [--name <nazwa>] — instalacja modułu."""
    if not args:
        _w(f"  {_C.RED}Brak argumentu.{_C.RESET}\n")
        _w(f"  {_C.DIM}Użycie: pkg.install <url|ścieżka.zip> [--name <nazwa>]{_C.RESET}\n")
        _w(f"  {_C.DIM}Przykład: pkg.install https://example.com/mymod-1.0.zip{_C.RESET}\n\n")
        return

    source = args[0]
    # Opcjonalny --name
    forced_name: str | None = None
    if "--name" in args:
        idx = args.index("--name")
        if idx + 1 < len(args):
            forced_name = args[idx + 1]

    _header("pkg.install")
    _row("Źródło", f"{_C.BCYAN}{source}{_C.RESET}")

    # ── Krok 1: pobranie / walidacja ────────────────────────────────────────
    _w(f"\n  {_C.DIM}[1/4] Weryfikacja źródła…{_C.RESET}\n")

    is_url  = source.startswith("http://") or source.startswith("https://")
    is_file = not is_url and source.endswith(".zip")

    if not is_url and not is_file:
        # Sprawdź czy to nazwa z indeksu
        if source in _PKG_REMOTE_INDEX:
            remote = _PKG_REMOTE_INDEX[source]
            source = remote["url"]
            is_url = source.startswith("http")
            _w(f"  {_C.DIM}  Znaleziono w indeksie: {source}{_C.RESET}\n")
        else:
            _w(f"  {_C.RED}Nieznane źródło: {source!r}{_C.RESET}\n")
            _w(f"  {_C.DIM}Podaj URL (https://…), ścieżkę .zip lub nazwę z indeksu.{_C.RESET}\n\n")
            return

    # ── Krok 2: symulacja pobrania / odczytu ────────────────────────────────
    _w(f"  {_C.DIM}[2/4] Pobieranie pakietu…{_C.RESET}\n")

    if is_url:
        parsed   = _urllib_parse.urlparse(source)
        filename = _os_pkg.path.basename(parsed.path) or "package.zip"
        # Ekstrakcja nazwy modułu z nazwy pliku
        pkg_name = forced_name or filename.rsplit("-", 1)[0].rsplit("_", 1)[0]
        pkg_ver  = "?"
        # Próba wyciągnięcia wersji z nazwy pliku np. mymod-1.0.zip
        parts = filename.replace(".zip", "").rsplit("-", 1)
        if len(parts) == 2 and parts[1][0].isdigit():
            pkg_name = forced_name or parts[0]
            pkg_ver  = parts[1]

        _w(f"  {_C.DIM}  URL:  {source}{_C.RESET}\n")
        _w(f"  {_C.DIM}  Plik: {filename}{_C.RESET}\n")

        # Symulacja — w środowisku produkcyjnym: _urllib_req.urlretrieve(source, tmp_path)
        checksum = _hashlib_pkg.sha256(source.encode()).hexdigest()[:16]
        size_kb  = 12  # symulowany rozmiar

    else:  # lokalny plik
        if not _os_pkg.path.isfile(source):
            _w(f"  {_C.RED}Plik nie istnieje: {source}{_C.RESET}\n\n")
            return
        filename = _os_pkg.path.basename(source)
        parts    = filename.replace(".zip", "").rsplit("-", 1)
        pkg_name = forced_name or (parts[0] if len(parts) == 2 else filename.replace(".zip", ""))
        pkg_ver  = parts[1] if len(parts) == 2 and parts[1][0].isdigit() else "1.0"
        checksum = _pkg_sha256_of(source)[:16]
        size_kb  = max(1, _os_pkg.path.getsize(source) // 1024)
        _w(f"  {_C.DIM}  Plik: {source}  ({size_kb} KB){_C.RESET}\n")

    # ── Krok 3: walidacja struktury ZIP ─────────────────────────────────────
    _w(f"  {_C.DIM}[3/4] Walidacja struktury pakietu…{_C.RESET}\n")

    if is_file:
        try:
            with _zipfile.ZipFile(source, "r") as zf:
                names = zf.namelist()
            py_files = [n for n in names if n.endswith(".py")]
            _w(f"  {_C.DIM}  Pliki w archiwum: {len(names)}  ·  moduły .py: {len(py_files)}{_C.RESET}\n")
            # Szukaj module.py lub <nazwa>.py z CML_COMMANDS
            main_py = next(
                (n for n in py_files if _os_pkg.path.basename(n) in (f"{pkg_name}.py", "module.py", "main.py")),
                py_files[0] if py_files else None,
            )
            if main_py:
                _w(f"  {_C.DIM}  Główny moduł: {main_py}{_C.RESET}\n")
            else:
                _w(f"  {_C.BYELLOW}  Ostrzeżenie: brak rozpoznanego pliku głównego.{_C.RESET}\n")
        except _zipfile.BadZipFile:
            _w(f"  {_C.RED}Błąd: plik nie jest prawidłowym archiwum ZIP.{_C.RESET}\n\n")
            return
    else:
        _w(f"  {_C.DIM}  Pominięto (tryb URL — walidacja po pobraniu){_C.RESET}\n")

    # ── Krok 4: rejestracja ──────────────────────────────────────────────────
    _w(f"  {_C.DIM}[4/4] Rejestracja modułu…{_C.RESET}\n\n")

    if pkg_name in _PKG_REGISTRY:
        old_ver = _PKG_REGISTRY[pkg_name]["version"]
        _w(f"  {_C.BYELLOW}Moduł {pkg_name!r} już zainstalowany (v{old_ver}).{_C.RESET}\n")
        _w(f"  {_C.DIM}Użyj pkg.update {pkg_name} aby zaktualizować.{_C.RESET}\n\n")
        return

    import datetime as _dt2
    _PKG_REGISTRY[pkg_name] = {
        "version":     pkg_ver,
        "source":      source,
        "installed":   _dt2.date.today().isoformat(),
        "description": f"Moduł zainstalowany z: {_os_pkg.path.basename(source)}",
        "author":      "external",
        "size_kb":     size_kb,
        "commands":    [],
        "checksum":    checksum,
        "status":      "active",
    }
    _admin_log_append(f"pkg.install: {pkg_name!r} v{pkg_ver} source={source}")

    _sep()
    _row("Moduł",    f"{_C.BCYAN}{pkg_name}{_C.RESET}")
    _row("Wersja",   f"{_C.BGREEN}{pkg_ver}{_C.RESET}")
    _row("Rozmiar",  f"{_C.DIM}{size_kb} KB{_C.RESET}")
    _row("Checksum", f"{_C.DIM}{checksum}{_C.RESET}")
    _row("Status",   f"{_C.BGREEN}✓ Zainstalowano{_C.RESET}")
    _w(f"\n  {_C.DIM}Uruchom ponownie terminal aby załadować nowe komendy.{_C.RESET}\n\n")


# ── pkg.remove ────────────────────────────────────────────────────────────────

def _cmd_pkg_remove(args: list[str], terminal) -> None:
    """pkg.remove <nazwa> — usuwa zainstalowany moduł."""
    if not args:
        _w(f"  {_C.RED}Brak argumentu. Użycie: pkg.remove <nazwa>{_C.RESET}\n\n")
        return

    name = args[0]
    if name not in _PKG_REGISTRY:
        _w(f"  {_C.RED}Moduł {name!r} nie jest zainstalowany.{_C.RESET}\n")
        _w(f"  {_C.DIM}Lista modułów: pkg.list{_C.RESET}\n\n")
        return

    info = _PKG_REGISTRY[name]
    if info.get("source") == "built-in":
        _w(f"  {_C.RED}Modułu wbudowanego nie można usunąć: {name!r}{_C.RESET}\n\n")
        return

    _header("pkg.remove")
    _row("Moduł",   f"{_C.BCYAN}{name}{_C.RESET}")
    _row("Wersja",  f"{_C.DIM}v{info.get('version','?')}{_C.RESET}")
    _row("Źródło",  f"{_C.DIM}{info.get('source','?')}{_C.RESET}")
    _sep()

    cmds = info.get("commands", [])
    if cmds:
        _w(f"\n  {_C.DIM}Komendy do usunięcia:{_C.RESET}\n")
        for c in cmds:
            _w(f"    {_C.DIM}– {c}{_C.RESET}\n")
        _w("\n")

    del _PKG_REGISTRY[name]
    _admin_log_append(f"pkg.remove: {name!r}")
    _row("Status", f"{_C.BGREEN}✓ Usunięto{_C.RESET}")
    _w("\n")


# ── pkg.update ────────────────────────────────────────────────────────────────

def _cmd_pkg_update(args: list[str], terminal) -> None:
    """pkg.update <nazwa|all> — aktualizuje moduł do najnowszej wersji."""
    target = args[0] if args else "all"
    _header(f"pkg.update  —  {'wszystkie moduły' if target == 'all' else target}")

    targets = list(_PKG_REGISTRY.keys()) if target == "all" else [target]

    if target != "all" and target not in _PKG_REGISTRY:
        _w(f"  {_C.RED}Moduł {target!r} nie jest zainstalowany.{_C.RESET}\n\n")
        return

    _w(f"  {_C.DIM}Pobieranie informacji o aktualizacjach…{_C.RESET}\n\n")
    _w(f"  {_C.BOLD}{'Moduł':<18}{'Aktualna':<12}{'Dostępna':<12}{'Status'}{_C.RESET}\n")
    _sep()

    updated = 0
    for name in sorted(targets):
        info    = _PKG_REGISTRY[name]
        cur_ver = info.get("version", "?")
        remote  = _PKG_REMOTE_INDEX.get(name)

        if not remote:
            _w(f"  {_C.DIM}{name:<18}{cur_ver:<12}{'?':<12}brak w indeksie{_C.RESET}\n")
            continue

        new_ver = remote["latest"]
        if cur_ver == new_ver or info.get("source") == "built-in":
            _w(f"  {_C.DIM}✓ {name:<16}{cur_ver:<12}{new_ver:<12}aktualna{_C.RESET}\n")
        else:
            _PKG_REGISTRY[name]["version"] = new_ver
            _PKG_REGISTRY[name]["source"]  = remote["url"]
            _admin_log_append(f"pkg.update: {name!r} {cur_ver} → {new_ver}")
            updated += 1
            _w(f"  {_C.BGREEN}↑ {_C.RESET}{_C.BCYAN}{name:<16}{_C.RESET}"
               f"{_C.DIM}{cur_ver:<12}{_C.RESET}{_C.BGREEN}{new_ver:<12}{_C.RESET}"
               f"{_C.BGREEN}zaktualizowano{_C.RESET}\n")

    _sep()
    if updated:
        _w(f"\n  {_C.BGREEN}✓ Zaktualizowano: {updated} moduł(ów).{_C.RESET}\n")
        _w(f"  {_C.DIM}Uruchom ponownie terminal aby zastosować zmiany.{_C.RESET}\n\n")
    else:
        _w(f"\n  {_C.DIM}Wszystkie moduły aktualne.{_C.RESET}\n\n")


# ── pkg.info ──────────────────────────────────────────────────────────────────

def _cmd_pkg_info(args: list[str], terminal) -> None:
    """pkg.info <nazwa> — szczegółowe informacje o zainstalowanym module."""
    if not args:
        _w(f"  {_C.RED}Brak argumentu. Użycie: pkg.info <nazwa>{_C.RESET}\n\n")
        return

    name = args[0]

    # Jeśli nie zainstalowany, sprawdź indeks
    if name not in _PKG_REGISTRY:
        if name in _PKG_REMOTE_INDEX:
            remote = _PKG_REMOTE_INDEX[name]
            _header(f"pkg.info  —  {name}  {_C.DIM}(niezainstalowany){_C.RESET}")
            _row("Nazwa",          f"{_C.BCYAN}{name}{_C.RESET}")
            _row("Najnowsza",      f"{_C.BGREEN}{remote['latest']}{_C.RESET}")
            _row("URL",            f"{_C.DIM}{remote['url']}{_C.RESET}")
            _row("Status",         f"{_C.BYELLOW}nie zainstalowany{_C.RESET}")
            _w(f"\n  {_C.DIM}Aby zainstalować: pkg.install {name}{_C.RESET}\n\n")
        else:
            _w(f"  {_C.RED}Moduł {name!r} nie istnieje (lokalnie ani w indeksie).{_C.RESET}\n\n")
        return

    info   = _PKG_REGISTRY[name]
    status = info.get("status", "?")
    icon   = _pkg_status_icon(status)
    remote = _PKG_REMOTE_INDEX.get(name, {})

    _header(f"pkg.info  —  {name}")

    _row("Nazwa",       f"{_C.BCYAN}{name}{_C.RESET}")
    _row("Wersja",      f"{_C.BGREEN}{info.get('version','?')}{_C.RESET}")

    if remote:
        latest = remote.get("latest", "?")
        up_to  = info.get("version") == latest
        label  = f"{_C.DIM}(aktualna){_C.RESET}" if up_to else f"{_C.BYELLOW}(dostępna: {latest}){_C.RESET}"
        _row("Indeks",  f"{_C.DIM}{latest}{_C.RESET}  {label}")

    _row("Status",      f"{icon} {status}")
    _row("Autor",       info.get("author", "?"))
    _row("Rozmiar",     f"{info.get('size_kb', '?')} KB")
    _row("Zainstalowany", info.get("installed", "?"))
    _row("Źródło",     f"{_C.DIM}{info.get('source','?')}{_C.RESET}")
    _row("Checksum",   f"{_C.DIM}{info.get('checksum','—')}{_C.RESET}")
    _sep()
    _w(f"\n  {_C.BBLUE}Opis{_C.RESET}\n")
    _w(f"  {info.get('description','—')}\n")

    cmds = info.get("commands", [])
    if cmds:
        _sep()
        _w(f"\n  {_C.BBLUE}Eksportowane komendy{_C.RESET}  ({len(cmds)})\n\n")
        for c in cmds:
            _w(f"    {_C.DIM}{c}{_C.RESET}\n")

    _w("\n")




# ══════════════════════════════════════════════════════════════════════════════
# dev.* — DEBUG / DEVTOOLS
# ══════════════════════════════════════════════════════════════════════════════

import traceback   as _traceback
import inspect     as _inspect
import cProfile    as _cProfile
import pstats      as _pstats
import io          as _io
import threading   as _threading
import textwrap    as _textwrap
import contextlib  as _devctx


# ── dev.trace ────────────────────────────────────────────────────────────────

def _cmd_dev_trace(args: list[str], terminal) -> None:
    """dev.trace [n]  — wyświetla aktualny stack trace bieżącego wątku.
    Opcjonalnie: dev.trace <n>  — pokazuje tylko ostatnie n ramek.
    """
    limit = None
    if args:
        try:
            limit = int(args[0])
        except ValueError:
            _w(f"{_C.RED}dev.trace: limit musi być liczbą całkowitą{_C.RESET}\n")
            return

    _header("dev.trace — Stack Trace")

    # Pobierz ramki bieżącego wątku
    frame = _inspect.currentframe()
    stack = _traceback.extract_stack(frame, limit=(limit + 1) if limit else None)
    # Usuń ostatnią ramkę (ta funkcja sama)
    stack = stack[:-1]
    if limit:
        stack = stack[-limit:]

    if not stack:
        _w(f"  {_C.DIM}Brak ramek do wyświetlenia.{_C.RESET}\n\n")
        return

    total = len(stack)
    for i, frame_info in enumerate(stack):
        depth   = total - i - 1
        is_last = (i == total - 1)
        prefix  = f"{_C.BGREEN}▶{_C.RESET}" if is_last else f"{_C.DIM}│{_C.RESET}"
        _w(f"  {prefix} {_C.BYELLOW}#{depth:<3}{_C.RESET}"
           f"  {_C.BCYAN}{frame_info.filename}{_C.RESET}"
           f"{_C.DIM}:{frame_info.lineno}{_C.RESET}"
           f"  {_C.BWHITE}{frame_info.name}(){_C.RESET}\n")
        if frame_info.line:
            _w(f"       {_C.DIM}→ {frame_info.line.strip()}{_C.RESET}\n")

    _w(f"\n  {_C.DIM}Łącznie ramek: {total}{_C.RESET}\n\n")

    # Pokaż też inne aktywne wątki jeśli jest ich więcej
    all_frames = sys.modules['sys']._current_frames() if hasattr(sys.modules.get('sys', None), '_current_frames') else {}
    other = {tid: f for tid, f in all_frames.items() if tid != _threading.current_thread().ident}
    if other:
        _w(f"  {_C.BCYAN}{_C.BOLD}Inne aktywne wątki ({len(other)}):{_C.RESET}\n\n")
        for tid, fr in other.items():
            tname = next((t.name for t in _threading.enumerate() if t.ident == tid), f"tid={tid}")
            _w(f"  {_C.BYELLOW}{tname}{_C.RESET}\n")
            for fi in _traceback.extract_stack(fr)[-4:]:
                _w(f"    {_C.DIM}{fi.filename}:{fi.lineno}  {fi.name}(){_C.RESET}\n")
        _w("\n")


# ── dev.inspect ──────────────────────────────────────────────────────────────

def _cmd_dev_inspect(args: list[str], terminal) -> None:
    """dev.inspect <wyrażenie>  — introspekcja obiektu Pythona.
    Przykłady:
      dev.inspect str
      dev.inspect sys.path
      dev.inspect terminal
    """
    if not args:
        _w(f"{_C.RED}dev.inspect: podaj wyrażenie, np. dev.inspect str{_C.RESET}\n")
        return

    expr = " ".join(args)
    _header(f"dev.inspect — {expr}")

    # Kontekst ewaluacji: moduły sys + terminal
    ctx: dict = {"terminal": terminal, "sys": sys, "inspect": _inspect}
    try:
        import builtins as _builtins_mod
        ctx.update(vars(_builtins_mod))
        obj = eval(expr, ctx)  # noqa: S307
    except Exception as e:
        _w(f"  {_C.RED}Błąd ewaluacji: {e}{_C.RESET}\n\n")
        return

    def _row2(k, v): _w(f"  {_C.BCYAN}{k:<20}{_C.RESET}{v}\n")

    _row2("Typ",       f"{_C.BWHITE}{type(obj).__qualname__}{_C.RESET}  "
                       f"{_C.DIM}({type(obj).__module__}){_C.RESET}")
    _row2("repr",      f"{_C.DIM}{repr(obj)[:120]}{_C.RESET}")

    # Rozmiar
    try:
        import sys as _sys2
        size = _sys2.getsizeof(obj)
        _row2("Rozmiar",  f"{size} B")
    except Exception:
        pass

    # Dokumentacja
    doc = _inspect.getdoc(obj)
    if doc:
        first_line = doc.splitlines()[0][:100]
        _row2("Docstring", f"{_C.DIM}{first_line}{_C.RESET}")

    # Plik źródłowy
    try:
        src_file = _inspect.getfile(obj)
        src_line = _inspect.getsourcelines(obj)[1] if callable(obj) else "—"
        _row2("Źródło",   f"{_C.DIM}{src_file}:{src_line}{_C.RESET}")
    except (TypeError, OSError):
        pass

    _sep()

    # Atrybuty / metody
    members = _inspect.getmembers(obj)
    methods   = [(n, v) for n, v in members if callable(v)   and not n.startswith("__")]
    attrs     = [(n, v) for n, v in members if not callable(v) and not n.startswith("__")]
    dunders   = [(n, v) for n, v in members if n.startswith("__")]

    if attrs:
        _w(f"\n  {_C.BOLD}{_C.BWHITE}Atrybuty ({len(attrs)}):{_C.RESET}\n")
        for name, val in attrs[:30]:
            val_s = repr(val)
            val_s = val_s[:80] + "…" if len(val_s) > 80 else val_s
            _w(f"    {_C.BYELLOW}{name:<24}{_C.RESET}{_C.DIM}{val_s}{_C.RESET}\n")
        if len(attrs) > 30:
            _w(f"    {_C.DIM}… i {len(attrs)-30} więcej{_C.RESET}\n")

    if methods:
        _w(f"\n  {_C.BOLD}{_C.BWHITE}Metody ({len(methods)}):{_C.RESET}\n")
        for name, val in methods[:30]:
            sig = ""
            try:
                sig = str(_inspect.signature(val))[:60]
            except (ValueError, TypeError):
                pass
            _w(f"    {_C.BGREEN}{name}{_C.RESET}{_C.DIM}{sig}{_C.RESET}\n")
        if len(methods) > 30:
            _w(f"    {_C.DIM}… i {len(methods)-30} więcej{_C.RESET}\n")

    if dunders:
        _w(f"\n  {_C.DIM}Dunder attrs: {len(dunders)}{_C.RESET}\n")

    _w("\n")


# ── dev.benchmark ────────────────────────────────────────────────────────────

def _cmd_dev_benchmark(args: list[str], terminal) -> None:
    """dev.benchmark <wyrażenie> [n=100]  — mierzy czas wykonania wyrażenia.
    Przykłady:
      dev.benchmark "sum(range(10000))"
      dev.benchmark "list(range(1000))" 500
    """
    if not args:
        _w(f"{_C.RED}dev.benchmark: podaj wyrażenie, np. dev.benchmark \"sum(range(1000))\"{_C.RESET}\n")
        return

    # Ostatni arg może być liczbą iteracji
    repeat = 100
    expr_parts = list(args)
    if expr_parts and expr_parts[-1].isdigit():
        repeat = max(1, int(expr_parts.pop()))
    expr = " ".join(expr_parts)

    _header(f"dev.benchmark")
    _w(f"  {_C.BCYAN}Wyrażenie:{_C.RESET}  {expr}\n")
    _w(f"  {_C.BCYAN}Iteracje: {_C.RESET}  {repeat}\n\n")

    ctx: dict = {"terminal": terminal, "sys": sys}
    try:
        import builtins as _bi; ctx.update(vars(_bi))
        # Kompiluj raz
        code = compile(expr, "<benchmark>", "eval")
    except SyntaxError as e:
        _w(f"  {_C.RED}Błąd składni: {e}{_C.RESET}\n\n")
        return

    import time as _time_bm
    times: list[float] = []
    last_result = None
    err = None

    try:
        # Rozgrzewka (1 iteracja)
        eval(code, ctx)  # noqa: S307
        for _ in range(repeat):
            t0 = _time_bm.perf_counter()
            last_result = eval(code, ctx)  # noqa: S307
            times.append(_time_bm.perf_counter() - t0)
    except Exception as e:
        err = e

    if err:
        _w(f"  {_C.RED}Błąd wykonania: {err}{_C.RESET}\n\n")
        return

    total   = sum(times)
    avg     = total / len(times)
    mn      = min(times)
    mx      = max(times)
    # Mediana
    s = sorted(times)
    med = (s[len(s)//2] + s[(len(s)-1)//2]) / 2

    def _fmt_t(t: float) -> str:
        if t < 1e-6: return f"{t*1e9:.2f} ns"
        if t < 1e-3: return f"{t*1e6:.2f} µs"
        if t < 1:    return f"{t*1e3:.2f} ms"
        return f"{t:.4f} s"

    _sep()
    _w(f"\n  {_C.BWHITE}{_C.BOLD}Wyniki:{_C.RESET}\n")
    _w(f"  {_C.BCYAN}{'Łącznie':<16}{_C.RESET}{_fmt_t(total)}\n")
    _w(f"  {_C.BCYAN}{'Średnia':<16}{_C.RESET}{_C.BGREEN}{_fmt_t(avg)}{_C.RESET}\n")
    _w(f"  {_C.BCYAN}{'Min':<16}{_C.RESET}{_fmt_t(mn)}\n")
    _w(f"  {_C.BCYAN}{'Max':<16}{_C.RESET}{_fmt_t(mx)}\n")
    _w(f"  {_C.BCYAN}{'Mediana':<16}{_C.RESET}{_fmt_t(med)}\n")
    _w(f"  {_C.BCYAN}{'Ops/s':<16}{_C.RESET}{_C.BYELLOW}{1/avg:,.0f}{_C.RESET}\n")

    if last_result is not None:
        r_s = repr(last_result)
        r_s = r_s[:80] + "…" if len(r_s) > 80 else r_s
        _w(f"\n  {_C.DIM}Wynik: {r_s}{_C.RESET}\n")

    # Mini wykres słupkowy (percentyle)
    _w(f"\n  {_C.DIM}Rozkład czasu (10 przedziałów):{_C.RESET}\n")
    bucket_count = 10
    mn_b, mx_b = mn, mx
    if mx_b > mn_b:
        width = (mx_b - mn_b) / bucket_count
        buckets = [0] * bucket_count
        for t in times:
            idx = min(int((t - mn_b) / width), bucket_count - 1)
            buckets[idx] += 1
        max_b = max(buckets) or 1
        bar_w = 30
        for bi, cnt in enumerate(buckets):
            lo = mn_b + bi * width
            filled = int(cnt / max_b * bar_w)
            bar = "█" * filled + "░" * (bar_w - filled)
            _w(f"  {_C.DIM}{_fmt_t(lo):>10}{_C.RESET}  "
               f"{_C.BBLUE}{bar}{_C.RESET}  {_C.DIM}{cnt}{_C.RESET}\n")
    _w("\n")


# ── dev.profile ──────────────────────────────────────────────────────────────

def _cmd_dev_profile(args: list[str], terminal) -> None:
    """dev.profile <wyrażenie> [top=20]  — profilowanie kodu (cProfile).
    Przykłady:
      dev.profile "sum(range(100000))"
      dev.profile "list(map(str,range(5000)))" 10
    """
    if not args:
        _w(f"{_C.RED}dev.profile: podaj wyrażenie, np. dev.profile \"sum(range(100000))\"{_C.RESET}\n")
        return

    top = 20
    expr_parts = list(args)
    if expr_parts and expr_parts[-1].isdigit():
        top = max(1, int(expr_parts.pop()))
    expr = " ".join(expr_parts)

    _header("dev.profile — cProfile")
    _w(f"  {_C.BCYAN}Wyrażenie:{_C.RESET}  {expr}\n")
    _w(f"  {_C.BCYAN}Top:      {_C.RESET}  {top} funkcji\n\n")

    ctx: dict = {"terminal": terminal, "sys": sys}
    try:
        import builtins as _bi2; ctx.update(vars(_bi2))
        code = compile(expr, "<profile>", "eval")
    except SyntaxError as e:
        _w(f"  {_C.RED}Błąd składni: {e}{_C.RESET}\n\n")
        return

    pr = _cProfile.Profile()
    result = None
    err = None
    try:
        pr.enable()
        result = eval(code, ctx)  # noqa: S307
        pr.disable()
    except Exception as e:
        pr.disable()
        err = e

    if err:
        _w(f"  {_C.RED}Błąd wykonania: {err}{_C.RESET}\n\n")
        return

    # Zbierz statystyki
    buf = _io.StringIO()
    ps  = _pstats.Stats(pr, stream=buf)
    ps.sort_stats("cumulative")
    ps.print_stats(top)
    raw = buf.getvalue()

    # Parsuj i wyświetl ładnie
    lines = raw.splitlines()
    # Nagłówek z cProfile (ncalls, tottime itp.)
    in_table = False
    _w(f"  {_C.BOLD}{_C.BWHITE}{'ncalls':>10}  {'tottime':>10}  {'cumtime':>10}  {'funkcja'}{_C.RESET}\n")
    _sep()
    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        if "ncalls" in line:
            in_table = True
            continue
        if in_table and line.strip():
            parts = line.split(None, 5)
            if len(parts) >= 6:
                ncalls, tottime, _percall1, cumtime, _percall2, func = parts
                _w(f"  {_C.BYELLOW}{ncalls:>10}{_C.RESET}"
                   f"  {_C.BGREEN}{tottime:>10}{_C.RESET}"
                   f"  {_C.BCYAN}{cumtime:>10}{_C.RESET}"
                   f"  {_C.DIM}{func[:80]}{_C.RESET}\n")
            elif len(parts) >= 1:
                _w(f"  {_C.DIM}{line[:100]}{_C.RESET}\n")
        elif not in_table and "function calls" in line:
            _w(f"  {_C.DIM}{line.strip()}{_C.RESET}\n\n")

    if result is not None:
        r_s = repr(result)
        r_s = r_s[:80] + "…" if len(r_s) > 80 else r_s
        _w(f"\n  {_C.DIM}Wynik: {r_s}{_C.RESET}\n")
    _w("\n")


# ── dev.reload ───────────────────────────────────────────────────────────────

def _cmd_dev_reload(args: list[str], terminal) -> None:
    """dev.reload <nazwa_modulu>  — przeładowuje moduł Pythona.
    Przykłady:
      dev.reload json
      dev.reload os.path
    Uwaga: nie przeładuje modułu sysadmin (jest aktywny).
    """
    if not args:
        _w(f"{_C.RED}dev.reload: podaj nazwę modułu, np. dev.reload json{_C.RESET}\n")
        return

    mod_name = args[0].strip()
    _header(f"dev.reload — {mod_name}")

    # Zabezpieczenie przed przeładowaniem aktywnych/systemowych modułów
    _PROTECTED = {"sysadmin", "sys", "builtins", "__main__", "importlib"}
    if mod_name in _PROTECTED:
        _w(f"  {_C.YELLOW}Moduł '{mod_name}' jest chroniony — przeładowanie niedozwolone.{_C.RESET}\n\n")
        return

    import time as _time_rl

    if mod_name not in sys.modules:
        # Spróbuj zaimportować
        _w(f"  {_C.DIM}Moduł nie jest załadowany — próba importu…{_C.RESET}\n")
        try:
            t0 = _time_rl.perf_counter()
            importlib.import_module(mod_name)
            elapsed = _time_rl.perf_counter() - t0
            _w(f"  {_C.BGREEN}✓{_C.RESET}  Zaimportowano  {_C.DIM}({elapsed*1000:.1f} ms){_C.RESET}\n\n")
        except ModuleNotFoundError:
            _w(f"  {_C.RED}✗  Moduł '{mod_name}' nie znaleziony.{_C.RESET}\n\n")
        except Exception as e:
            _w(f"  {_C.RED}✗  Błąd importu: {e}{_C.RESET}\n\n")
        return

    mod = sys.modules[mod_name]
    old_file = getattr(mod, "__file__", "—")

    _row("Moduł",    mod_name)
    _row("Plik",     old_file or "—")
    _row("Wersja",   getattr(mod, "__version__", "—"))
    _w("\n")

    try:
        t0 = _time_rl.perf_counter()
        reloaded = importlib.reload(mod)
        elapsed  = _time_rl.perf_counter() - t0
        new_file = getattr(reloaded, "__file__", "—")
        _w(f"  {_C.BGREEN}✓  Przeładowano pomyślnie{_C.RESET}  {_C.DIM}({elapsed*1000:.1f} ms){_C.RESET}\n")
        if new_file != old_file:
            _w(f"  {_C.YELLOW}Zmiana pliku: {new_file}{_C.RESET}\n")
        _w(f"  {_C.DIM}Nowa wersja: {getattr(reloaded, '__version__', '—')}{_C.RESET}\n\n")
    except Exception as e:
        _w(f"  {_C.RED}✗  Błąd przeładowania: {e}{_C.RESET}\n\n")


# ── dev.sandbox ──────────────────────────────────────────────────────────────

# Dozwolone wbudowane funkcje w trybie sandbox
_SANDBOX_SAFE_BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "bytes", "callable",
    "chr", "complex", "dict", "dir", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "getattr", "hasattr", "hash", "hex",
    "id", "int", "isinstance", "issubclass", "iter", "len", "list",
    "map", "max", "min", "next", "oct", "ord", "pow", "print", "range",
    "repr", "reversed", "round", "set", "setattr", "slice", "sorted",
    "str", "sum", "tuple", "type", "vars", "zip",
}


def _cmd_dev_sandbox(args: list[str], terminal) -> None:
    """dev.sandbox <kod>  — izolowane wykonanie kodu Pythona.
    Ograniczony namespace: brak dostępu do sys, os, importlib itp.
    Tylko bezpieczne wbudowane funkcje.
    Przykłady:
      dev.sandbox "x = [i**2 for i in range(10)]; print(sum(x))"
      dev.sandbox "print(sorted([3,1,4,1,5,9,2,6]))"
    """
    if not args:
        _w(f"{_C.RED}dev.sandbox: podaj kod do wykonania{_C.RESET}\n")
        _w(f"  {_C.DIM}Przykład: dev.sandbox \"print(sum(range(100)))\"{_C.RESET}\n\n")
        return

    code_str = " ".join(args)
    # Obsługa sekwencji \n jako nowych linii (dla wieloliniowego kodu)
    code_str = code_str.replace("\\n", "\n").replace("\\t", "    ")

    _header("dev.sandbox — Izolowane wykonanie")
    _w(f"  {_C.BCYAN}Kod:{_C.RESET}\n")
    for line in code_str.splitlines():
        _w(f"    {_C.DIM}{line}{_C.RESET}\n")
    _w("\n")

    # Ogranicz builtins do bezpiecznego podzbioru
    import builtins as _builtins_sb
    safe_builtins = {name: getattr(_builtins_sb, name)
                     for name in _SANDBOX_SAFE_BUILTINS
                     if hasattr(_builtins_sb, name)}
    safe_builtins["__import__"] = _forbidden_import  # blokuj import

    sandbox_globals: dict = {
        "__builtins__": safe_builtins,
        "__name__":     "__sandbox__",
    }

    # Przechwytuj stdout
    output_buf = _io.StringIO()
    import time as _time_sb
    t0  = _time_sb.perf_counter()
    err = None
    result = None

    try:
        # Kompilacja
        try:
            code_obj = compile(code_str, "<sandbox>", "exec")
        except SyntaxError as se:
            _w(f"  {_C.RED}Błąd składni: {se}{_C.RESET}\n\n")
            return

        # Przekieruj print → output_buf
        _original_print = safe_builtins.get("print")
        def _sandbox_print(*a, **kw):
            kw.setdefault("file", output_buf)
            if _original_print:
                _original_print(*a, **kw)
        safe_builtins["print"] = _sandbox_print

        exec(code_obj, sandbox_globals)  # noqa: S102
    except Exception as e:
        err = e

    elapsed = _time_sb.perf_counter() - t0
    output  = output_buf.getvalue()

    _sep()
    if output:
        _w(f"\n  {_C.BWHITE}{_C.BOLD}Output:{_C.RESET}\n")
        for line in output.splitlines():
            _w(f"    {line}\n")

    # Zmienne zdefiniowane w sandboxie
    user_vars = {k: v for k, v in sandbox_globals.items()
                 if not k.startswith("__")}
    if user_vars:
        _w(f"\n  {_C.BWHITE}{_C.BOLD}Zmienne ({len(user_vars)}):{_C.RESET}\n")
        for k, v in list(user_vars.items())[:20]:
            v_s = repr(v)
            v_s = v_s[:80] + "…" if len(v_s) > 80 else v_s
            _w(f"    {_C.BYELLOW}{k:<20}{_C.RESET}{_C.DIM}{type(v).__name__:<12}{_C.RESET}{v_s}\n")

    if err:
        _w(f"\n  {_C.RED}✗  Błąd: {type(err).__name__}: {err}{_C.RESET}\n")
    else:
        _w(f"\n  {_C.BGREEN}✓  Wykonano{_C.RESET}  {_C.DIM}({elapsed*1000:.2f} ms){_C.RESET}\n")
    _w("\n")


def _forbidden_import(name, *args, **kwargs):
    raise ImportError(f"sandbox: import '{name}' jest zablokowany")

# ── CML_COMMANDS — rejestracja komend w terminalu ─────────────────────────────

CML_COMMANDS: dict = {
    "sys.info":        _cmd_sys_info,
    "sys.env":         _cmd_sys_env,
    "sys.time":        _cmd_sys_time,
    "sys.uptime":      _cmd_sys_uptime,
    "sys.clearcache":  _cmd_sys_clearcache,
    "sys.modules":     _cmd_sys_modules,
    "sys.mem":         _cmd_sys_mem,
    "sys.cpuclock":    _cmd_sys_cpuclock,
    # ── fs.* ──────────────────────────────────────────────
    "fs.ls":           _cmd_fs_ls,
    "fs.tree":         _cmd_fs_tree,
    "fs.read":         _cmd_fs_read,
    "fs.write":        _cmd_fs_write,
    "fs.append":       _cmd_fs_append,
    "fs.touch":        _cmd_fs_touch,
    "fs.rm":           _cmd_fs_rm,
    "fs.mv":           _cmd_fs_mv,
    "fs.cp":           _cmd_fs_cp,
    "fs.mkdir":        _cmd_fs_mkdir,
    "fs.rmdir":        _cmd_fs_rmdir,
    "fs.hash":         _cmd_fs_hash,
    "fs.size":         _cmd_fs_size,
    "fs.find":         _cmd_fs_find,
    # ── net.* ─────────────────────────────────────────────
    "net.http.get":    _cmd_net_http_get,
    "net.http.head":   _cmd_net_http_head,
    "net.http.post":   _cmd_net_http_post,
    "net.dns.resolve": _cmd_net_dns_resolve,
    "net.ip.public":   _cmd_net_ip_public,
    "net.ip.local":    _cmd_net_ip_local,
    "net.port.scan":   _cmd_net_port_scan,
    "net.ping":        _cmd_net_ping,
    # ── sec.* ─────────────────────────────────────────────
    "sec.hash.sha1":    _cmd_sec_hash_sha1,
    "sec.hash.sha256":  _cmd_sec_hash_sha256,
    "sec.hash.md5":     _cmd_sec_hash_md5,
    "sec.encode.base64": _cmd_sec_encode_base64,
    "sec.decode.base64": _cmd_sec_decode_base64,
    "sec.rand.bytes":   _cmd_sec_rand_bytes,
    "sec.rand.int":     _cmd_sec_rand_int,
    "sec.uuid":         _cmd_sec_uuid,
    # ── data.* ────────────────────────────────────────────
    "data.json.load":   _cmd_data_json_load,
    "data.json.dump":   _cmd_data_json_dump,
    "data.yaml.load":   _cmd_data_yaml_load,
    "data.yaml.dump":   _cmd_data_yaml_dump,
    "data.csv.read":    _cmd_data_csv_read,
    "data.csv.write":   _cmd_data_csv_write,
    "data.regex.match": _cmd_data_regex_match,
    "data.regex.find":  _cmd_data_regex_find,
    # ── math.* ────────────────────────────────────────────
    "math.eval":           _cmd_math_eval,
    "math.rand":           _cmd_math_rand,
    "math.stats":          _cmd_math_stats,
    "math.convert.bytes":  _cmd_math_convert_bytes,
    "math.convert.time":   _cmd_math_convert_time,
    # ── proc.* ────────────────────────────────────────────
    "proc.list":    _cmd_proc_list,
    "proc.kill":    _cmd_proc_kill,
    "proc.spawn":   _cmd_proc_spawn,
    "proc.status":  _cmd_proc_status,
    # ── term.* ────────────────────────────────────────────
    "term.clear":   _cmd_term_clear,
    "term.size":    _cmd_term_size,
    "term.title":   _cmd_term_title,
    "term.color":   _cmd_term_color,
    # ── admin.* ───────────────────────────────────────────
    "admin.users.list":     _cmd_admin_users_list,
    "admin.users.add":      _cmd_admin_users_add,
    "admin.users.rm":       _cmd_admin_users_rm,
    "admin.roles.list":     _cmd_admin_roles_list,
    "admin.roles.set":      _cmd_admin_roles_set,
    "admin.log":            _cmd_admin_log,
    "admin.log.clear":      _cmd_admin_log_clear,
    "admin.config.get":     _cmd_admin_config_get,
    "admin.config.set":     _cmd_admin_config_set,
    "admin.update":         _cmd_admin_update,
    "admin.plugins.list":   _cmd_admin_plugins_list,
    "admin.plugins.load":   _cmd_admin_plugins_load,
    "admin.plugins.unload": _cmd_admin_plugins_unload,
    # ── dev.* ─────────────────────────────────────────────
    "dev.trace":      _cmd_dev_trace,
    "dev.inspect":    _cmd_dev_inspect,
    "dev.benchmark":  _cmd_dev_benchmark,
    "dev.profile":    _cmd_dev_profile,
    "dev.reload":     _cmd_dev_reload,
    "dev.sandbox":    _cmd_dev_sandbox,
    # ── pkg.* ─────────────────────────────────────────────
    "pkg.list":    _cmd_pkg_list,
    "pkg.install": _cmd_pkg_install,
    "pkg.remove":  _cmd_pkg_remove,
    "pkg.update":  _cmd_pkg_update,
    "pkg.info":    _cmd_pkg_info,
}


# ── EcoSystem integration ─────────────────────────────────────────────────────

def setup(terminal):
    """Rejestruje komendy modułu admin w TerminalX EcoSystem."""
    _t = terminal.t

    def _admin(args, terminal=terminal):
        if not args:
            cml_menu()
            return
        sub = args[0]
        rest = args[1:]
        if sub in CML_COMMANDS:
            CML_COMMANDS[sub](rest, terminal)
        else:
            _w(
                f"  {_C.RED}✗ Nieznana podkomenda: '{sub}'{_C.RESET}  "
                f"—  wpisz {_C.BYELLOW}admin{_C.RESET} bez argumentów po pełną listę.\n"
            )

    # Komenda główna
    terminal.register_command(
        "admin", _admin,
        description=_t("cmd_admin"),
        category=_t("cat_ecosystem"),
    )
    # Alias
    terminal.register_command(
        "sa", _admin,
        description=_t("cmd_admin_alias"),
        category=_t("cat_ecosystem"),
    )
    # Rejestruj każdą podkomendę z CML_COMMANDS bezpośrednio (np. sys.info, fs.ls)
    for cmd_name, cmd_func in CML_COMMANDS.items():
        def _make_cmd(fn):
            def _cmd(args, terminal=terminal):
                fn(args, terminal)
            return _cmd
        terminal.register_command(
            cmd_name, _make_cmd(cmd_func),
            description=f"admin: {cmd_name}",
            category=_t("cat_ecosystem"),
        )


def teardown(terminal):
    """Wyrejestrowuje komendy modułu admin z TerminalX EcoSystem."""
    for cmd in ("admin", "sa"):
        terminal.commands.pop(cmd, None)
    for cmd_name in CML_COMMANDS:
        terminal.commands.pop(cmd_name, None)
