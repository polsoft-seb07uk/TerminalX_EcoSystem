#!/usr/bin/env python3
# autor:   Sebastian Januchowski
# company: polsoft.ITS(TM) Group
# web:     www.polsoft.gt.tc
# github:  https://github.com/seb07uk
# email:   polsoft.its@fastservice.com
# license: MIT
# crossterm: {"id": "10", "aliases": ["dbg", "debugger"], "description": "Narzedzie do sledzenia i profilowania skryptow Python", "version": "2.0", "author": "Sebastian Januchowski"}
"""
Moduł Debugger v2.0
  debug trace <plik.py>          - sledz wykonanie skryptu Python (linia po linii)
  debug profile <plik.py>        - profiluj skrypt Python (czas wykonania funkcji)
  debug sandbox <plik.py>        - uruchom skrypt w sandboxie z tracingiem
  debug break <add|list|clear>   - zarzadzaj punktami przerwania (breakpointami)
  (dbg) set <var>=<val>          - edytuj wartosc zmiennej w trakcie postoju
  (dbg) bt / stack               - wyswietl stos wywolan (backtrace)
  (dbg) list / l                 - wyswietl kod zrodlowy wokol biezacej linii
  dbg                            - alias -> menu
"""

import sys
import os
import time
import subprocess
import threading
import inspect
import cProfile
import pstats
from io import StringIO
from pathlib import Path

_sys = sys

# Prawdziwy stdout zachowany przy załadowaniu modułu.
# _w() zawsze pisze do terminala, nawet gdy sys.stdout
# jest przekierowany na StringIO podczas tracingu skryptu.
_real_stdout = _sys.stdout

def _w(s):
    _real_stdout.write(s)
    _real_stdout.flush()

class _C:
    RESET   = "\x1b[0m";  BOLD    = "\x1b[1m";  DIM     = "\x1b[2m"
    BCYAN   = "\x1b[96m"; BYELLOW = "\x1b[93m"; BGREEN  = "\x1b[92m"
    BWHITE  = "\x1b[97m"; RED     = "\x1b[91m"; CYAN    = "\x1b[36m"
    MAGENTA = "\x1b[95m"; YELLOW  = "\x1b[33m"; BLUE    = "\x1b[94m"
    BG_CYAN = "\x1b[46m"

# ─── Tracing functionality ────────────────────────────────────────────────────

class _DebugStats:
    """Statystyki dla integracji z monitorem."""
    active_script = None # Nazwa pliku
    current_line  = 0
    is_waiting    = False

_trace_indent = 0
_trace_file_path = None
_trace_file_cache = [] # Cache dla linii kodu
_breakpoints = set()
_watchpoints = {}    # {var_name: last_known_value}
_step_mode = False

# ─── Session log & stats ──────────────────────────────────────────────────────
_session_log = []    # Lista stringów (linie logu)
_session_stats = {
    "lines_traced": 0,
    "breakpoints_hit": 0,
    "exceptions_caught": 0,
    "watch_triggers": 0,
    "start_time": None,
}
_cmd_history = []    # Historia komend w shellu interaktywnym

def _log(line: str):
    """Zapisuje linie do session logu i na stdout."""
    _session_log.append(line)
    _w(line)

def _interactive_shell(frame):
    """Interaktywny prompt wewnatrz punktu przerwania."""
    global _step_mode, _trace_file_cache, _cmd_history
    _DebugStats.is_waiting = True
    line_no = frame.f_lineno
    
    # Nagłówek wizualny
    _w(f"\n{_C.BG_CYAN}{_C.BWHITE} BREAKPOINT {_C.RESET} at line {line_no}\n")
    
    while True:
        _real_stdout.write(f"{_C.BCYAN}(dbg){_C.RESET} ")
        _real_stdout.flush()
        raw = _sys.__stdin__.readline().strip()
        cmd = raw.lower()
        if not cmd: continue
        
        # Historia komend
        if raw and (not _cmd_history or _cmd_history[-1] != raw):
            _cmd_history.append(raw)
        
        # Skrot !! - powtorz ostatnia komende
        if cmd == '!!':
            if len(_cmd_history) >= 2:
                raw = _cmd_history[-2]
                cmd = raw.lower()
                _w(f"  {_C.DIM}>> {raw}{_C.RESET}\n")
            else:
                _w(f"  {_C.DIM}(brak poprzedniej komendy){_C.RESET}\n")
                continue
        
        # Historia komend: 'history'
        if cmd in ('history', 'hist'):
            _w(f"\n  {_C.BOLD}Historia komend:{_C.RESET}\n")
            for i, h in enumerate(_cmd_history[-20:], 1):
                _w(f"  {_C.DIM}{i:3d}.{_C.RESET} {h}\n")
            _w("\n")
            continue
        
        if cmd in ('c', 'cont', 'continue'):
            _step_mode = False
            break
        elif cmd in ('s', 'step', 'next'):
            _step_mode = True
            break
        elif cmd in ('v', 'vars', 'locals'):
            _w(f"\n  {_C.BOLD}Zmienne lokalne:{_C.RESET}\n")
            for k, v in frame.f_locals.items():
                if not k.startswith('__'):
                    # Dodano typ zmiennej dla lepszej czytelności
                    v_type = type(v).__name__
                    _w(f"  {_C.BYELLOW}{k:<12}{_C.RESET} ({_C.DIM}{v_type}{_C.RESET}) = {v}\n")
            _w("\n")
        elif cmd.startswith('set '):
            try:
                expr = cmd[4:].strip()
                if '=' in expr:
                    exec(expr, frame.f_globals, frame.f_locals)
                    _w(f"  {_C.BGREEN}[V] Zaktualizowano zmienna.{_C.RESET}\n")
                else:
                    _w(f"  {_C.RED}[!] Uzycie: set var=val{_C.RESET}\n")
            except Exception as e:
                _w(f"  {_C.RED}[!] Blad: {e}{_C.RESET}\n")
        elif cmd in ('l', 'list'):
            try:
                lines = _trace_file_cache
                if not lines:
                    with open(_trace_file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        _trace_file_cache = lines
                
                # Ulepszona wizualizacja kodu
                start = max(0, line_no - 6)
                end = min(len(lines), line_no + 5)
                _w(f"\n  {_C.BOLD}{_C.BCYAN}--- Source: {os.path.basename(_trace_file_path)} ---{_C.RESET}\n")
                for i in range(start, end):
                    ln = i + 1
                    if ln == line_no:
                        _w(f"{_C.BG_CYAN}{_C.BWHITE} > {ln:3d}: {lines[i].rstrip():<40} {_C.RESET}\n")
                    else:
                        _w(f"     {ln:3d}: {lines[i].rstrip()}\n")
                _w("\n")
            except Exception as e:
                _w(f"  {_C.RED}[!] Blad odczytu pliku: {e}{_C.RESET}\n")
        elif cmd in ('bt', 'backtrace', 'stack'):
            stack = inspect.stack()
            _w(f"\n  {_C.BOLD}Call Stack (most recent call last):{_C.RESET}\n")
            depth = 0
            for frame_info in reversed(stack):
                fname = os.path.basename(frame_info.filename)
                if fname == 'debugger.py' and frame_info.function in ('_interactive_shell', '_trace_function'):
                    continue
                display_name = fname if fname != '<string>' else '[Dynamic Code]'
                _w(f"    {_C.DIM}#{depth:02d}{_C.RESET} {display_name}:{frame_info.lineno} in {_C.BCYAN}{frame_info.function}{_C.RESET}\n")
                depth += 1
            _w("\n")
        elif cmd.startswith('p ') or cmd.startswith('eval '):
            expr = cmd.split(' ', 1)[1]
            try:
                res = eval(expr, frame.f_globals, frame.f_locals)
                _w(f"  {_C.BGREEN}res:{_C.RESET} {res}\n")
            except Exception as e:
                _w(f"  {_C.RED}err:{_C.RESET} {e}\n")
        elif cmd.startswith('watch '):
            var_name = raw.split(' ', 1)[1].strip()
            _watchpoints[var_name] = frame.f_locals.get(var_name, '__UNDEFINED__')
            _w(f"  {_C.BGREEN}[V] Watchpoint dodany: {_C.BYELLOW}{var_name}{_C.RESET}\n")
        elif cmd == 'watch':
            if not _watchpoints:
                _w(f"  {_C.DIM}(brak watchpointow){_C.RESET}\n")
            else:
                _w(f"\n  {_C.BOLD}Aktywne watchpointy:{_C.RESET}\n")
                for wv, wval in _watchpoints.items():
                    cur = frame.f_locals.get(wv, '__UNDEFINED__')
                    changed = cur != wval
                    flag = f" {_C.RED}[ZMIENIONA]{_C.RESET}" if changed else ""
                    _w(f"  {_C.BYELLOW}{wv:<14}{_C.RESET} = {cur}{flag}\n")
                _w("\n")
        elif cmd.startswith('unwatch '):
            var_name = raw.split(' ', 1)[1].strip()
            if var_name in _watchpoints:
                del _watchpoints[var_name]
                _w(f"  {_C.BGREEN}[V] Watchpoint usuniety: {var_name}{_C.RESET}\n")
            else:
                _w(f"  {_C.RED}[!] Nie znaleziono watchpointu: {var_name}{_C.RESET}\n")
        elif cmd.startswith('break remove ') or cmd.startswith('br remove '):
            try:
                ln = int(cmd.split()[-1])
                if ln in _breakpoints:
                    _breakpoints.discard(ln)
                    _w(f"  {_C.BGREEN}[V] Usunięto breakpoint z linii {ln}.{_C.RESET}\n")
                else:
                    _w(f"  {_C.RED}[!] Brak breakpointu na linii {ln}.{_C.RESET}\n")
            except ValueError:
                _w(f"  {_C.RED}[!] Podaj numer linii.{_C.RESET}\n")
        elif cmd in ('h', 'help', '?'):
            _w(f"\n  {_C.BOLD}Dostepne komendy (dbg):{_C.RESET}\n")
            _w(f"  {_C.BYELLOW}c / cont{_C.RESET}         - Kontynuuj do nastepnego breakpointu\n")
            _w(f"  {_C.BYELLOW}s / step{_C.RESET}         - Wykonaj jedna linie kodu\n")
            _w(f"  {_C.BYELLOW}l / list{_C.RESET}         - Pokaz kod zrodlowy wokol biezacej linii\n")
            _w(f"  {_C.BYELLOW}v / vars{_C.RESET}         - Pokaz zmienne lokalne i ich typy\n")
            _w(f"  {_C.BYELLOW}bt / stack{_C.RESET}       - Wyswietl stos wywolan\n")
            _w(f"  {_C.BYELLOW}set x=1{_C.RESET}          - Zmien wartosc zmiennej w locie\n")
            _w(f"  {_C.BYELLOW}p <expr>{_C.RESET}         - Ewaluuj dowolne wyrazenie Python\n")
            _w(f"  {_C.BYELLOW}watch <var>{_C.RESET}      - Dodaj watchpoint na zmiennej\n")
            _w(f"  {_C.BYELLOW}unwatch <var>{_C.RESET}    - Usun watchpoint\n")
            _w(f"  {_C.BYELLOW}watch{_C.RESET}            - Pokaz watchpointy i ich wartosci\n")
            _w(f"  {_C.BYELLOW}break remove <n>{_C.RESET} - Usun breakpoint z linii n\n")
            _w(f"  {_C.BYELLOW}history{_C.RESET}          - Pokaz historie komend\n")
            _w(f"  {_C.BYELLOW}!! {_C.RESET}              - Powtorz ostatnia komende\n")
            _w(f"  {_C.BYELLOW}q / quit{_C.RESET}         - Przerwij debugowanie\n\n")
        elif cmd in ('q', 'quit'):
            raise KeyboardInterrupt

def _trace_function(frame, event, arg):
    global _trace_indent, _trace_file_path, _step_mode, _trace_file_cache
    if event == 'call':
        _trace_indent += 1
    elif event == 'return':
        _trace_indent -= 1
    elif event == 'exception':
        _session_stats["exceptions_caught"] += 1
    elif event == 'line':
        if frame.f_code.co_filename == _trace_file_path:
            line_no = frame.f_lineno
            _DebugStats.current_line = line_no
            _DebugStats.active_script = os.path.basename(_trace_file_path)
            _session_stats["lines_traced"] += 1

            is_break = line_no in _breakpoints
            if is_break:
                _session_stats["breakpoints_hit"] += 1
            
            try:
                # Get source line from the cache
                if not _trace_file_cache:
                    with open(_trace_file_path, 'r', encoding='utf-8') as f:
                        _trace_file_cache = f.readlines()
                line_content = _trace_file_cache[line_no - 1].strip()
            except (IndexError, FileNotFoundError):
                line_content = "<unavailable>"

            prefix = f"{_C.RED}[!] {_C.RESET}" if is_break else "    "
            entry = f"{prefix}{_C.DIM}L{line_no:03d}: {line_content}{_C.RESET}\n"
            _session_log.append(f"L{line_no:03d}: {line_content}")
            _w(entry)
            
            # Sprawdz watchpointy
            for wvar in list(_watchpoints.keys()):
                cur_val = frame.f_locals.get(wvar, '__UNDEFINED__')
                old_val = _watchpoints[wvar]
                if cur_val != old_val:
                    _session_stats["watch_triggers"] += 1
                    _watchpoints[wvar] = cur_val
                    _w(f"  {_C.MAGENTA}[WATCH]{_C.RESET} {_C.BYELLOW}{wvar}{_C.RESET}: "
                       f"{_C.DIM}{old_val!r}{_C.RESET} → {_C.BGREEN}{cur_val!r}{_C.RESET}\n")
            
            if is_break or _step_mode:
                _interactive_shell(frame)
                
    return _trace_function

def _run_with_trace(script_path: Path, env: dict = None, _t=None):
    global _trace_file_path, _step_mode, _trace_file_cache
    _t = _t or (lambda k, **kw: k)
    _trace_file_path = str(script_path.resolve())
    _step_mode = False
    _trace_file_cache = []
    _session_log.clear()
    _session_stats.update({"lines_traced": 0, "breakpoints_hit": 0,
                           "exceptions_caught": 0, "watch_triggers": 0,
                           "start_time": time.time()})

    _w(f"\n  {_C.BOLD}{_C.BCYAN}RUN:{_C.RESET} {_C.BWHITE}{script_path.name}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'-'*52}{_C.RESET}\n\n")

    original_stdout = sys.stdout
    original_trace = sys.gettrace()

    try:
        sys.settrace(_trace_function)
        sys.stdout = StringIO()

        original_env = os.environ.copy()
        if env:
            os.environ.update(env)

        script_globals = {'__name__': '__main__', '__file__': str(script_path)}

        with open(script_path, 'r', encoding='utf-8') as f:
            code = compile(f.read(), script_path.name, 'exec')
            exec(code, script_globals, script_globals)

        script_output = sys.stdout.getvalue()
        if script_output:
            _w(f"\n  {_C.DIM}{'-'*52}{_C.RESET}\n")
            _w(f"  {_C.DIM}[{_t('dbg_script_output')}]{_C.RESET}\n")
            _w(script_output)
            if not script_output.endswith("\n"): _w("\n")

        _w(f"\n  {_C.BGREEN}[V] {_t('dbg_trace_done')}{_C.RESET}\n\n")

    except KeyboardInterrupt:
        _w(f"\n  {_C.BYELLOW}{_t('dbg_trace_interrupted')}{_C.RESET}\n\n")
    except Exception as e:
        _w(f"\n  {_C.RED}[!] {_t('dbg_exec_error', err=e)}{_C.RESET}\n\n")
    finally:
        sys.settrace(original_trace)
        sys.stdout = original_stdout
        if env:
            os.environ.clear()
            os.environ.update(original_env)
        _trace_file_path = None
        _DebugStats.active_script = None
        _DebugStats.is_waiting = False

# ─── Profiling functionality ──────────────────────────────────────────────────

def _run_with_profile(script_path: Path, env: dict = None, _t=None):
    _t = _t or (lambda k, **kw: k)
    _w(f"\n  {_C.BOLD}{_C.BCYAN}PROFILE:{_C.RESET} {_C.BWHITE}{script_path.name}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'-'*52}{_C.RESET}\n\n")

    original_stdout = sys.stdout
    try:
        sys.stdout = StringIO()

        original_env = os.environ.copy()
        if env:
            os.environ.update(env)

        profiler = cProfile.Profile()
        profiler.enable()

        script_globals = {'__name__': '__main__', '__file__': str(script_path)}

        with open(script_path, 'r', encoding='utf-8') as f:
            code = compile(f.read(), script_path.name, 'exec')
            exec(code, script_globals, script_globals)

        profiler.disable()

        script_output = sys.stdout.getvalue()
        if script_output:
            _w(f"\n  {_C.DIM}{'-'*52}{_C.RESET}\n")
            _w(f"  {_C.DIM}[{_t('dbg_script_output')}]{_C.RESET}\n")
            _w(script_output)
            if not script_output.endswith("\n"): _w("\n")

        _w(f"\n  {_C.BOLD}{_C.BCYAN}{_t('dbg_profile_report')}{_C.RESET}\n")
        s = pstats.Stats(profiler, stream=original_stdout)
        s.strip_dirs().sort_stats('cumulative').print_stats(15)

        _w(f"\n  {_C.BGREEN}[V] {_t('dbg_profile_done')}{_C.RESET}\n\n")

    except KeyboardInterrupt:
        _w(f"\n  {_C.BYELLOW}{_t('dbg_profile_interrupted')}{_C.RESET}\n\n")
    except Exception as e:
        _w(f"\n  {_C.RED}[!] {_t('dbg_exec_error', err=e)}{_C.RESET}\n\n")
    finally:
        sys.stdout = original_stdout
        if env:
            os.environ.clear()
            os.environ.update(original_env)

# ─── CML Commands ─────────────────────────────────────────────────────────────

def _resolve_script_path(args, _t=None) -> Path | None:
    _t = _t or (lambda k, **kw: k)
    if not args:
        _w(f"\n  {_C.RED}[!] {_t('dbg_no_script')}{_C.RESET}\n\n")
        return None

    script_name = args[0]
    script_path = Path(script_name)
    if not script_path.is_absolute():
        script_path = Path(os.getcwd()) / script_path

    if not script_path.exists():
        _w(f"\n  {_C.RED}[!] {_t('dbg_script_not_found', path=script_path)}{_C.RESET}\n\n")
        return None
    if not script_path.is_file():
        _w(f"\n  {_C.RED}[!] {_t('dbg_script_not_file', path=script_path)}{_C.RESET}\n\n")
        return None
    if script_path.suffix.lower() != '.py':
        _w(f"\n  {_C.RED}[!] {_t('dbg_script_not_py')}{_C.RESET}\n\n")
        return None

    return script_path

def cmd_debug_trace(args, terminal, _t=None):
    script_path = _resolve_script_path(args, _t)
    if script_path:
        _run_with_trace(script_path, _t=_t)

def cmd_debug_profile(args, terminal, _t=None):
    script_path = _resolve_script_path(args, _t)
    if script_path:
        _run_with_profile(script_path, _t=_t)

def cmd_debug_sandbox(args, terminal, _t=None):
    _t = _t or (lambda k, **kw: k)
    script_path = _resolve_script_path(args, _t)
    if not script_path:
        return

    sb_mod = terminal.loaded_modules.get('sandbox')
    if not (sb_mod and hasattr(sb_mod, 'SANDBOX_ENV')):
        _w(f"\n  {_C.RED}[!] {_t('dbg_sandbox_not_loaded')}{_C.RESET}\n")
        _w(f"  {_C.DIM}{_t('dbg_sandbox_load_hint')}{_C.RESET}\n\n")
        return

    sandbox_env_vars = sb_mod.SANDBOX_ENV._env_vars
    _w(f"\n  {_C.BOLD}{_C.BCYAN}SANDBOX:{_C.RESET} {_C.BWHITE}{script_path.name}{_C.RESET}\n")
    _w(f"  {_C.DIM}{_t('dbg_sandbox_env_vars')}: {sandbox_env_vars}{_C.RESET}\n")
    _run_with_trace(script_path, env=sandbox_env_vars, _t=_t)

def cmd_debug_break(args, _t=None):
    _t = _t or (lambda k, **kw: k)
    if not args or args[0] == "list":
        _w(f"\n  {_C.BOLD}{_t('dbg_break_active')}{_C.RESET}\n")
        if not _breakpoints:
            _w(f"  {_C.DIM}{_t('dbg_none')}{_C.RESET}\n\n")
        else:
            for bp in sorted(_breakpoints):
                _w(f"  {_C.RED}[!] {_C.RESET}{_t('dbg_break_line')} {_C.BYELLOW}{bp}{_C.RESET}\n")
            _w("\n")
        return

    sub = args[0].lower()
    if sub == "add" and len(args) > 1:
        try:
            line = int(args[1])
            _breakpoints.add(line)
            _w(f"  {_C.BGREEN}[V] {_t('dbg_break_added', line=line)}{_C.RESET}\n")
        except ValueError:
            _w(f"  {_C.RED}[!] {_t('dbg_provide_line')}{_C.RESET}\n")
    elif sub == "remove" and len(args) > 1:
        try:
            line = int(args[1])
            if line in _breakpoints:
                _breakpoints.discard(line)
                _w(f"  {_C.BGREEN}[V] {_t('dbg_break_removed', line=line)}{_C.RESET}\n")
            else:
                _w(f"  {_C.RED}[!] {_t('dbg_break_not_found', line=line)}{_C.RESET}\n")
        except ValueError:
            _w(f"  {_C.RED}[!] {_t('dbg_provide_line')}{_C.RESET}\n")
    elif sub == "clear":
        _breakpoints.clear()
        _w(f"  {_C.BGREEN}[V] {_t('dbg_break_cleared')}{_C.RESET}\n")
    else:
        _w(f"  {_C.DIM}{_t('dbg_break_usage')}{_C.RESET}\n")

def cmd_debug_stats(args, terminal, _t=None):
    _t = _t or (lambda k, **kw: k)
    st = _session_stats
    if st["start_time"]:
        elapsed = f"{time.time() - st['start_time']:.1f}s"
    else:
        elapsed = "n/a"
    none_label = _t('dbg_none_short')
    _w(f"\n  {_C.BOLD}{_C.BCYAN}{_t('dbg_stats_title')}{_C.RESET}\n")
    _w(f"  {_C.BYELLOW}{_t('dbg_stats_lines'):<22}{_C.RESET}{st['lines_traced']}\n")
    _w(f"  {_C.BYELLOW}{_t('dbg_stats_breaks'):<22}{_C.RESET}{st['breakpoints_hit']}\n")
    _w(f"  {_C.BYELLOW}{_t('dbg_stats_exceptions'):<22}{_C.RESET}{st['exceptions_caught']}\n")
    _w(f"  {_C.BYELLOW}{_t('dbg_stats_watches'):<22}{_C.RESET}{st['watch_triggers']}\n")
    _w(f"  {_C.BYELLOW}{_t('dbg_stats_time'):<22}{_C.RESET}{elapsed}\n")
    _w(f"  {_C.BYELLOW}{_t('dbg_stats_active_breaks'):<22}{_C.RESET}{sorted(_breakpoints) or none_label}\n")
    _w(f"  {_C.BYELLOW}{_t('dbg_stats_active_watches'):<22}{_C.RESET}{list(_watchpoints.keys()) or none_label}\n\n")

def cmd_debug_export(args, terminal, _t=None):
    _t = _t or (lambda k, **kw: k)
    filename = args[0] if args else "debug_session.log"
    if not filename.endswith(".log"):
        filename += ".log"
    out_path = Path(os.getcwd()) / filename
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("# Debug Session Log\n")
            f.write(f"# Exported: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Lines traced: {_session_stats['lines_traced']}\n")
            f.write(f"# Breakpoints hit: {_session_stats['breakpoints_hit']}\n")
            f.write(f"# Exceptions: {_session_stats['exceptions_caught']}\n\n")
            for line in _session_log:
                f.write(line + "\n")
        _w(f"  {_C.BGREEN}[V] {_t('dbg_export_saved', path=out_path)}{_C.RESET}\n\n")
    except Exception as e:
        _w(f"  {_C.RED}[!] {_t('dbg_export_error', err=e)}{_C.RESET}\n\n")

def cmd_debug_watch(args, terminal, _t=None):
    _t = _t or (lambda k, **kw: k)
    if not args or args[0] == "list":
        _w(f"\n  {_C.BOLD}{_t('dbg_watch_active')}{_C.RESET}\n")
        if not _watchpoints:
            _w(f"  {_C.DIM}{_t('dbg_none')}{_C.RESET}\n\n")
        else:
            for wv, wval in _watchpoints.items():
                _w(f"  {_C.MAGENTA}[W]{_C.RESET} {_C.BYELLOW}{wv:<16}{_C.RESET} {_t('dbg_watch_last_val')}: {wval!r}\n")
            _w("\n")
        return

    sub = args[0].lower()
    if sub == "add" and len(args) > 1:
        var_name = args[1]
        _watchpoints[var_name] = '__UNDEFINED__'
        _w(f"  {_C.BGREEN}[V] {_t('dbg_watch_added', var=var_name)}{_C.RESET}\n")
    elif sub == "remove" and len(args) > 1:
        var_name = args[1]
        if var_name in _watchpoints:
            del _watchpoints[var_name]
            _w(f"  {_C.BGREEN}[V] {_t('dbg_watch_removed', var=var_name)}{_C.RESET}\n")
        else:
            _w(f"  {_C.RED}[!] {_t('dbg_watch_not_found', var=var_name)}{_C.RESET}\n")
    elif sub == "clear":
        _watchpoints.clear()
        _w(f"  {_C.BGREEN}[V] {_t('dbg_watch_cleared')}{_C.RESET}\n")
    else:
        _w(f"  {_C.DIM}{_t('dbg_watch_usage')}{_C.RESET}\n")

# ─── Menu ─────────────────────────────────────────────────────────────────────

def cml_menu(_t=None):
    _t = _t or (lambda k, **kw: k)
    _w(f"\n{_C.BOLD}{_C.BCYAN}  +------------------------------------------+{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  |   Module: Debugger v2.0                  |{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  +------------------------------------------+{_C.RESET}\n\n")
    cmds = [
        ("debug trace <script.py>",    _t("dbg_menu_trace")),
        ("debug profile <script.py>",  _t("dbg_menu_profile")),
        ("debug sandbox <script.py>",  _t("dbg_menu_sandbox")),
        ("debug break add <n>",        _t("dbg_menu_break_add")),
        ("debug break remove <n>",     _t("dbg_menu_break_remove")),
        ("debug break list",           _t("dbg_menu_break_list")),
        ("debug break clear",          _t("dbg_menu_break_clear")),
        ("debug watch add <var>",      _t("dbg_menu_watch_add")),
        ("debug watch remove <var>",   _t("dbg_menu_watch_remove")),
        ("debug watch list",           _t("dbg_menu_watch_list")),
        ("debug stats",                _t("dbg_menu_stats")),
        ("debug export [file.log]",    _t("dbg_menu_export")),
        ("dbg",                        _t("dbg_menu_alias")),
    ]
    for c, d in cmds:
        _w(f"  {_C.BYELLOW}{c:<32}{_C.RESET} {_C.DIM}{d}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}{_t('dbg_menu_global')}: {_C.RESET}"
       f"{_C.BYELLOW}debug{_C.RESET}  {_C.BYELLOW}dbg{_C.RESET}\n\n")

# ─── Rejestr ──────────────────────────────────────────────────────────────────

def cmd_debug_dispatcher(args, terminal, _t=None):
    _t = _t or (lambda k, **kw: k)
    if not args:
        cml_menu(_t)
        return

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "trace":
        cmd_debug_trace(sub_args, terminal, _t)
    elif subcommand == "profile":
        cmd_debug_profile(sub_args, terminal, _t)
    elif subcommand == "sandbox":
        cmd_debug_sandbox(sub_args, terminal, _t)
    elif subcommand == "break":
        cmd_debug_break(sub_args, _t)
    elif subcommand == "watch":
        cmd_debug_watch(sub_args, terminal, _t)
    elif subcommand == "stats":
        cmd_debug_stats(sub_args, terminal, _t)
    elif subcommand == "export":
        cmd_debug_export(sub_args, terminal, _t)
    else:
        _w(f"\n  {_C.RED}[!] {_t('debug_unknown_sub', sub=subcommand)}{_C.RESET}\n")
        cml_menu(_t)

CML_COMMANDS = {
    "debug":   cmd_debug_dispatcher,
    "dbg":     lambda args, term: cml_menu(),
}


# ─── EcoSystem integration ────────────────────────────────────────────────────

def setup(terminal) -> None:
    """Rejestruje komendy debuggera i API w _integration."""
    def _t(key, **kw):
        return terminal.t(key, **kw)

    # Rejestracja w _integration – inne moduly moga logowac zdarzenia bez
    # bezposredniego importu debugger.py (eliminuje cykliczne zaleznosci).
    try:
        from . import _integration as _intg
        _intg.register("debugger", {
            "log_event":        _log,
            "get_stats":        lambda: dict(_session_stats),
            "get_log":          lambda: list(_session_log),
            "get_breakpoints":  lambda: set(_breakpoints),
            "get_watchpoints":  lambda: dict(_watchpoints),
            "add_breakpoint":   lambda n: _breakpoints.add(int(n)),
            "clear_breakpoints": _breakpoints.clear,
            "DebugStats":       _DebugStats,
        })
    except Exception:
        pass

    def debug_command(args: list) -> None:
        cmd_debug_dispatcher(args, terminal, _t)

    def dbg_alias(args: list) -> None:
        cml_menu(_t)

    terminal.register_command(
        "debug", debug_command,
        description=_t("cmd_debug"),
        category=_t("cat_ecosystem"),
    )
    terminal.register_command(
        "dbg", dbg_alias,
        description=_t("cmd_dbg"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal) -> None:
    """Wyrejestrowuje debugger z _integration i usuwa komendy."""
    global _step_mode, _trace_file_path, _trace_file_cache
    # Resetuj stan sesji
    _breakpoints.clear()
    _watchpoints.clear()
    _session_log.clear()
    _session_stats.update({
        "lines_traced": 0, "breakpoints_hit": 0,
        "exceptions_caught": 0, "watch_triggers": 0,
        "start_time": None,
    })
    _step_mode = False
    _trace_file_path = None
    _trace_file_cache = []
    _DebugStats.active_script = None
    _DebugStats.is_waiting = False

    try:
        from . import _integration as _intg
        _intg.unregister("debugger")
    except Exception:
        pass

    terminal.commands.pop("debug", None)
    terminal.commands.pop("dbg",   None)