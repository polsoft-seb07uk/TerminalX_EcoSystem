"""Task module for TerminalX.

Multi-task manager: run shell commands / TerminalX commands in background
threads, track status, view output, kill, and persist task log across sessions.

Commands
--------
  task run <cmd...>        - run command in background thread
  task bg  <cmd...>        - alias for `task run`
  task list                - list all tasks (running + finished)
  task info <id>           - full output of a task
  task kill <id>           - kill a running task (SIGTERM -> SIGKILL)
  task clear               - remove all finished tasks from list
  task log [N]             - show last N entries from persistent log

Architecture
------------
  * Each task is a TaskEntry (dataclass) held in terminal._tasks dict.
  * Subprocess tasks run via subprocess.Popen in a daemon thread that
    captures stdout+stderr line-by-line.
  * Internal TerminalX commands (no shell executable) redirect stdout
    through io.StringIO and run synchronously in their thread.
  * Task IDs are sequential integers (T1, T2, ...).
  * Finished tasks are appended to .cache/global/task_log.json.

Author : Sebastian Januchowski
Brand  : polsoft.ITS(TM)
"""

from __future__ import annotations

import io
import json
import os
import shlex
import subprocess
import threading
import time
import contextlib
from dataclasses import dataclass, field
from typing import Optional

from . import config
from . import _integration

from ._shared import ROOT_DIR, IS_WIN, IS_LIN, IS_MAC, RST, BOLD, DIM, YLW, RED, GRN, CYN, _w, _pad, _atomic_write
LOG_FILE  = os.path.join(ROOT_DIR, ".cache", "global", "task_log.json")
MAX_LOG   = 200          # fallback; overridden by config at runtime
MAX_LINES = 1000         # fallback; overridden by config at runtime

def _max_log()   -> int: return config.get("task.max_log",          MAX_LOG)
def _max_lines() -> int: return config.get("task.max_output_lines", MAX_LINES)



# -- Status constants ----------------------------------------------------------

class S:
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"
    KILLED   = "killed"


_STATUS_COLOR = {
    S.RUNNING: CYN  + "*" + RST,
    S.DONE:    GRN  + "[V]" + RST,
    S.FAILED:  RED  + "[X]" + RST,
    S.KILLED:  YLW  + "?" + RST,
}


# -- Task entry ----------------------------------------------------------------

@dataclass
class TaskEntry:
    tid:       str
    label:     str
    status:    str          = S.RUNNING
    started:   float        = field(default_factory=time.time)
    ended:     Optional[float] = None
    exit_code: Optional[int]   = None
    lines:     list[str]    = field(default_factory=list)
    _lock:     threading.Lock = field(default_factory=threading.Lock,
                                     repr=False, compare=False)
    _proc:     Optional[subprocess.Popen] = field(default=None,
                                                  repr=False, compare=False)
    _thread:   Optional[threading.Thread] = field(default=None,
                                                  repr=False, compare=False)

    def append(self, line: str) -> None:
        with self._lock:
            if len(self.lines) < _max_lines():
                self.lines.append(line)

    def get_lines(self) -> list[str]:
        with self._lock:
            return list(self.lines)

    def elapsed(self) -> float:
        end = self.ended or time.time()
        return end - self.started

    def to_log_dict(self) -> dict:
        return {
            "id":        self.tid,
            "label":     self.label,
            "status":    self.status,
            "started":   self.started,
            "ended":     self.ended,
            "exit_code": self.exit_code,
            "lines":     self.lines[-50:],   # keep last 50 lines in log
        }


# -- Persistent log ------------------------------------------------------------

def _load_log() -> list[dict]:
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [e for e in data if isinstance(e, dict)]
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, UnicodeDecodeError):
        # corrupted or wrongly-encoded file (e.g. an interrupted write) -
        # start fresh instead of crashing task list/log on every platform
        pass
    except OSError as exc:
        _w(f"  {RED}task: {exc}{RST}\n")
    return []


def _append_log(entry: TaskEntry) -> None:
    """Persist a finished task to the log, atomically and without raising.

    Same rationale as core/history.py's _save(): write to a temp file in
    the same directory, fsync, then os.replace() into place. os.replace()
    is atomic on both POSIX and Windows, so a crash or kill mid-write never
    leaves a truncated/corrupt task_log.json behind. Any failure here is
    reported but swallowed - losing the persistent log must not crash the
    background task thread that's running the user's command.
    """
    try:
        directory = os.path.dirname(LOG_FILE)
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        _w(f"  {RED}task: {exc}{RST}\n")
        return

    log = _load_log()
    log.append(entry.to_log_dict())

    if not _atomic_write(LOG_FILE, log[-_max_log():]):
        _w(f"  {RED}task: zapis nie powiódł się{RST}\n")


def _build_cmdline(raw_args: list[str]) -> str:
    """Rebuild a shell command line from already-tokenized args.

    raw_args came out of the REPL's quote-aware tokenizer (_tokenize), so an
    argument like a filename with a space has already been merged into a
    single string and lost its surrounding quotes. Naively rejoining with
    " ".join() throws that information away again: `echo "hello world" foo`
    would be handed to the shell as four bare words instead of three.

    The fix has to be platform-specific because cmd.exe and POSIX shells
    quote differently:
      - POSIX (sh/bash, used when shell=True on Linux/macOS): shlex.quote()
        wraps anything with special characters in single quotes.
      - Windows (cmd.exe, used when shell=True on win32): single quotes do
        nothing there - subprocess.list2cmdline() applies the quoting rules
        MSVCRT-based programs (and cmd.exe) actually expect (double quotes).
    """
    if IS_WIN:
        return subprocess.list2cmdline(raw_args)
    return shlex.join(raw_args)


# -- Runner helpers ------------------------------------------------------------

def _notify_finished(terminal, entry: TaskEntry) -> None:
    """Przekaz do modulu notify informacje o zakonczeniu zadania w tle.

    Uzytkownik moze juz nie obserwowac REPL-a w momencie zakonczenia zadania
    `task run ...` - chmurka powiadomienia (i wpis w historii notify)
    informuje go niezaleznie od tego, co aktualnie robi w terminalu.
    """
    if entry.status == S.DONE:
        kind, verb = "ok", "zakonczone"
    elif entry.status == S.KILLED:
        kind, verb = "warn", "przerwane"
    else:
        kind, verb = "err", "nieudane"
    _integration.notify_event(
        terminal,
        f"[{entry.tid}] {entry.label}: zadanie {verb} (exit {entry.exit_code}).",
        kind=kind, title="TASK",
    )


def _run_line_captured(entry: TaskEntry, terminal, cmdline: str) -> None:
    """Run a full TerminalX command line (including pipe chains) in a task thread.

    Unlike _run_internal which calls a single command function directly,
    this routes the entire line through terminal._run_line so that pipe
    segments, capture mode, and the shlex tokenizer all work identically
    to a command typed interactively.  stdout is redirected to a StringIO
    buffer so output is captured into the TaskEntry instead of printed live.

    History recording is suppressed for task-background replays: _run_line
    normally calls terminal._history_record, but we temporarily detach it
    to avoid polluting the history with background task re-executions.
    """
    buf = io.StringIO()
    # Temporarily suppress history recording inside the task thread so that
    # background task replays don't inject duplicate entries into history.
    _orig_recorder = getattr(terminal, "_history_record", None)
    terminal._history_record = None
    try:
        with contextlib.redirect_stdout(buf):
            terminal._run_line(cmdline)
        for line in buf.getvalue().splitlines():
            entry.append(line)
        entry.status    = S.DONE
        entry.exit_code = 0
    except SystemExit:
        entry.status    = S.KILLED
        entry.exit_code = -1
    except Exception as exc:
        entry.append(f"[error] {exc}")
        entry.status    = S.FAILED
        entry.exit_code = 1
    finally:
        terminal._history_record = _orig_recorder
        entry.ended = time.time()
        _append_log(entry)
        _notify_finished(terminal, entry)


def _run_shell(entry: TaskEntry, cmdline: str, terminal=None) -> None:
    """Run *cmdline* as a real subprocess; capture stdout+stderr."""
    try:
        popen_kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if IS_WIN:
            # Run in a new process group so a later terminate()/kill() can
            # reach the whole group rather than only the immediate cmd.exe
            # wrapper process, which otherwise leaves child processes
            # (e.g. a python.exe spawned by a .bat) running as orphans.
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            # POSIX equivalent: detach into a new session so the whole
            # process tree can be signaled via os.killpg in _cmd_kill.
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmdline, shell=True, **popen_kwargs)
        entry._proc = proc
        for line in proc.stdout:
            entry.append(line.rstrip("\n"))
        proc.wait()
        entry.exit_code = proc.returncode
        entry.status    = S.DONE if proc.returncode == 0 else S.FAILED
    except Exception as exc:
        entry.append(f"[error] {exc}")
        entry.status = S.FAILED
    finally:
        entry.ended = time.time()
        _append_log(entry)
        _notify_finished(terminal, entry)


def _run_internal(entry: TaskEntry, terminal, cmd: str, args: list[str]) -> None:
    """Run a TerminalX internal command; capture its stdout."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            terminal.commands[cmd]["func"](args)
        for line in buf.getvalue().splitlines():
            entry.append(line)
        entry.status    = S.DONE
        entry.exit_code = 0
    except Exception as exc:
        entry.append(f"[error] {exc}")
        entry.status    = S.FAILED
        entry.exit_code = 1
    finally:
        entry.ended = time.time()
        _append_log(entry)
        _notify_finished(terminal, entry)


# -- Module setup --------------------------------------------------------------

def setup(terminal) -> None:
    _t = terminal.t

    # shared state
    terminal._tasks   = {}        # tid -> TaskEntry
    terminal._task_seq = 0        # auto-increment counter
    _lock = threading.Lock()


    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("task", {
            "get_tasks": lambda: getattr(terminal, "_tasks", {}),
        })
    except Exception:
        pass
    def _next_tid() -> str:
        with _lock:
            terminal._task_seq += 1
            return f"T{terminal._task_seq}"

    # ------------------------------------------------------------------ #
    def _spawn(label: str, raw_args: list[str]) -> None:
        """Parse args and start task thread."""
        if config.get("task.auto_clear", False):
            done = [tid for tid, e in list(terminal._tasks.items())
                    if e.status in (S.DONE, S.FAILED, S.KILLED)]
            for tid in done:
                terminal._tasks.pop(tid, None)

        tid   = _next_tid()
        entry = TaskEntry(tid=tid, label=label)
        terminal._tasks[tid] = entry

        # decide: internal command / pipe chain  vs  real shell command
        #
        # Three cases are routed through terminal._run_line (captured):
        #   1. Single internal command:  "ls", "analyse stats", …
        #   2. Pipe chain of internals:  "ls | search .py"
        #   3. Mixed pipe starting with internal: "ls | grep foo"
        #      (grep is external, but _run_line handles the handoff)
        #
        # Anything whose first token is NOT a registered TerminalX command
        # AND contains no "|" is handed straight to the real shell via Popen.
        # Using _run_line for everything would also work, but shell commands
        # need Popen for true background streaming; we only use _run_line when
        # at least the first segment is an internal command.
        first     = raw_args[0] if raw_args else ""
        has_pipe  = "|" in raw_args
        is_internal_lead = first in terminal.commands and first != "task"

        if is_internal_lead or has_pipe:
            # Rebuild the original command line (quote-aware) so _run_line's
            # tokenizer re-parses it exactly as the user typed it.
            cmdline = _build_cmdline(raw_args)
            thread  = threading.Thread(
                target=_run_line_captured,
                args=(entry, terminal, cmdline),
                daemon=True,
                name=f"task-{tid}",
            )
        else:
            # shell command - rebuild the command line preserving quoting
            # (platform-specific: POSIX shell vs cmd.exe), instead of a
            # bare " ".join() that would lose any quoted multi-word args
            cmdline = _build_cmdline(raw_args)
            thread  = threading.Thread(
                target=_run_shell,
                args=(entry, cmdline, terminal),
                daemon=True,
                name=f"task-{tid}",
            )

        entry._thread = thread
        thread.start()
        _w(f"  {GRN}[{tid}]{RST} {_t('task_spawned', label=label)}\n")

    # ------------------------------------------------------------------ #
    def task(args: list[str]) -> None:
        if not args:
            _show_help(_t)
            return

        sub  = args[0].lower()
        rest = args[1:]

        if sub in ("run", "bg"):
            if not rest:
                print(_t("task_run_usage"))
                return
            _spawn(" ".join(rest), rest)

        elif sub == "list":
            _cmd_list(terminal, _t)

        elif sub == "info":
            if not rest:
                print(_t("task_info_usage"))
                return
            _cmd_info(terminal, _t, rest[0].upper())

        elif sub == "kill":
            if not rest:
                print(_t("task_kill_usage"))
                return
            _cmd_kill(terminal, _t, rest[0].upper())

        elif sub == "clear":
            _cmd_clear(terminal, _t)

        elif sub == "log":
            limit = 20
            if rest:
                try:
                    limit = int(rest[0])
                except ValueError:
                    pass
            _cmd_log(_t, limit)

        else:
            print(_t("task_unknown_sub", sub=sub))
            _show_help(_t)

    terminal.register_command(
        "task", task,
        description=_t("cmd_task"),
        category=_t("cat_task"),
    )


# -- Sub-command implementations -----------------------------------------------

def _show_help(_t) -> None:
    _w(f"\n  {BOLD}{CYN}task{RST} - {_t('task_module_title')}\n\n")
    rows = [
        ("task run <cmd...>",    _t("task_help_run")),
        ("task bg  <cmd...>",    _t("task_help_bg")),
        ("task list",            _t("task_help_list")),
        ("task info <T#>",       _t("task_help_info")),
        ("task kill <T#>",       _t("task_help_kill")),
        ("task clear",           _t("task_help_clear")),
        ("task log [N]",         _t("task_help_log")),
    ]
    for cmd, desc in rows:
        _w(f"  {YLW}{_pad(cmd, 26)}{RST} {desc}\n")
    _w("\n")


def _elapsed_str(sec: float) -> str:
    if sec < 60:
        return f"{sec:.1f}s"
    m, s = divmod(int(sec), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _cmd_list(terminal, _t) -> None:
    tasks = terminal._tasks
    if not tasks:
        print(_t("task_list_empty"))
        return

    _w(f"\n  {BOLD}{CYN}{_t('task_list_header')}{RST}\n\n")
    _w(f"  {DIM}{'ID':<6} {'ST':<4} {'ELAPSED':<10} {'LABEL'}{RST}\n")
    _w(f"  {DIM}{'-'*6} {'-'*4} {'-'*10} {'-'*34}{RST}\n")

    for tid, entry in sorted(tasks.items()):
        st   = _STATUS_COLOR.get(entry.status, entry.status)
        ela  = _elapsed_str(entry.elapsed())
        lbl  = entry.label if len(entry.label) <= 40 else entry.label[:37] + "..."
        line_count = len(entry.get_lines())
        _w(f"  {YLW}{_pad(tid, 6)}{RST} {st}  {DIM}{_pad(ela, 10)}{RST} {lbl}"
           f"  {DIM}({line_count} ln){RST}\n")

    running = sum(1 for e in tasks.values() if e.status == S.RUNNING)
    _w(f"\n  {DIM}{_t('task_list_total', n=len(tasks), running=running)}{RST}\n\n")


def _cmd_info(terminal, _t, tid: str) -> None:
    entry = terminal._tasks.get(tid)
    if not entry:
        _w(f"  {RED}{_t('task_not_found', tid=tid)}{RST}\n")
        return

    st  = _STATUS_COLOR.get(entry.status, entry.status)
    ela = _elapsed_str(entry.elapsed())
    _w(f"\n  {BOLD}{YLW}[{entry.tid}]{RST}  {entry.label}\n")
    _w(f"  {DIM}Status :{RST}  {st}  {entry.status}\n")
    _w(f"  {DIM}Elapsed:{RST}  {ela}\n")
    if entry.exit_code is not None:
        _w(f"  {DIM}Exit   :{RST}  {entry.exit_code}\n")
    lines = entry.get_lines()
    if not lines:
        _w(f"  {DIM}{_t('task_no_output')}{RST}\n\n")
        return
    _w(f"\n  {DIM}{'-' * 54}{RST}\n")
    for ln in lines:
        _w(f"  {ln}\n")
    _w(f"  {DIM}{'-' * 54}{RST}\n\n")


def _cmd_kill(terminal, _t, tid: str) -> None:
    entry = terminal._tasks.get(tid)
    if not entry:
        _w(f"  {RED}{_t('task_not_found', tid=tid)}{RST}\n")
        return
    if entry.status != S.RUNNING:
        _w(f"  {YLW}{_t('task_not_running', tid=tid, status=entry.status)}{RST}\n")
        return

    proc = entry._proc
    if proc:
        # Kill the whole process group/tree, not just the immediate shell
        # wrapper - otherwise a child process spawned by the command (e.g.
        # a script launching python.exe) survives as an orphan.
        #
        # Platform note: Popen.terminate() sends SIGTERM on POSIX (a
        # process can catch it and exit cleanly) but on Windows there is
        # no SIGTERM - terminate() there just calls TerminateProcess(),
        # which is an immediate hard kill. So the "graceful then forceful"
        # two-step below is meaningful on POSIX and effectively a no-op
        # delay on Windows (the process is already gone after step one).
        try:
            if IS_WIN:
                proc.terminate()  # TerminateProcess - always a hard kill here
            else:
                import signal
                _killpg  = getattr(os, "killpg",  None)
                _getpgid = getattr(os, "getpgid", None)
                if _killpg and _getpgid:
                    try:
                        _killpg(_getpgid(proc.pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    else:
                        time.sleep(0.4)
                        if proc.poll() is None:
                            try:
                                _killpg(_getpgid(proc.pid), signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                else:
                    proc.terminate()
        except Exception as exc:
            _w(f"  {RED}{exc}{RST}\n")
            return

    entry.status = S.KILLED
    entry.ended  = time.time()
    _w(f"  {YLW}?  {_t('task_killed', tid=tid)}{RST}\n")


def _cmd_clear(terminal, _t) -> None:
    finished = [tid for tid, e in terminal._tasks.items()
                if e.status != S.RUNNING]
    for tid in finished:
        del terminal._tasks[tid]
    _w(f"  {GRN}[V]  {_t('task_cleared', n=len(finished))}{RST}\n")


def _format_started(ts) -> str:
    """Format a stored 'started' timestamp defensively.

    time.localtime()/strftime() can raise OSError or OverflowError on
    Windows for timestamps outside the platform's supported range (the
    Windows CRT's time functions are pickier about this than glibc) - a
    single bad/garbled timestamp in an old log file should show a
    placeholder, not crash the whole `task log` listing.
    """
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts or 0))
    except (OSError, OverflowError, ValueError):
        return "????-??-?? ??:??"


def _cmd_log(_t, limit: int) -> None:
    log = _load_log()
    if not log:
        print(_t("task_log_empty"))
        return
    entries = log[-limit:]
    _w(f"\n  {BOLD}{CYN}{_t('task_log_header', n=len(entries))}{RST}\n\n")
    for e in reversed(entries):
        ts  = _format_started(e.get("started", 0))
        st  = _STATUS_COLOR.get(e.get("status", ""), e.get("status", "?"))
        lbl = e.get("label", "?")
        tid = e.get("id", "?")
        _w(f"  {YLW}{_pad(tid, 6)}{RST} {st}  {DIM}{ts}{RST}  {lbl}\n")
    _w("\n")


# -- Teardown ------------------------------------------------------------------

def teardown(terminal) -> None:
    try:
        from . import _integration as _intg
        _intg.unregister("task")
    except Exception:
        pass
    terminal.commands.pop("task", None)
    # kill all running subprocesses (and their children) on exit
    for entry in getattr(terminal, "_tasks", {}).values():
        if entry.status == S.RUNNING and entry._proc:
            try:
                if IS_WIN:
                    entry._proc.terminate()
                else:
                    import signal
                    _killpg  = getattr(os, "killpg",  None)
                    _getpgid = getattr(os, "getpgid", None)
                    if _killpg and _getpgid:
                        try:
                            _killpg(_getpgid(entry._proc.pid), signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    else:
                        entry._proc.terminate()
            except Exception:
                pass
