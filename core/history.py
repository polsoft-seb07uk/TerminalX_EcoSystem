"""History module for TerminalX.

Stores command history across sessions and lets the user recall, search,
and re-execute previous commands.

Author : Sebastian Januchowski
Brand  : polsoft.ITS(TM)
"""

import os
import json

from . import config

from ._shared import ROOT_DIR, RST, DIM, RED, CYN, _w, _atomic_write
HISTORY_FILE = os.path.join(ROOT_DIR, ".cache", "global", "history.json")
_DEFAULT_MAX_ENTRIES = 500


def _max_entries() -> int:
    return config.get("history.max", _DEFAULT_MAX_ENTRIES)


def _load() -> list:
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # tolerate any stray non-string entries from a hand-edited
                # or older-format file instead of crashing later when code
                # calls .lower() / .split() on them
                return [e for e in data if isinstance(e, str)][-_max_entries():]
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, UnicodeDecodeError):
        # corrupted or wrongly-encoded file (e.g. leftover from an
        # interrupted write, or written under a different codepage on an
        # older Windows build) - start fresh rather than blocking startup
        pass
    except OSError as exc:
        # permission errors, locked file, etc. - same idea: don't let a
        # history read failure prevent the whole terminal from starting
        _w(f"  {RED}history: {exc}{RST}\n")
    return []


def _save(entries: list) -> None:
    """Persist history to disk, atomically and without crashing the REPL.

    Two cross-platform concerns matter here:

    1. Atomicity - writing straight to HISTORY_FILE leaves a truncated /
       corrupt JSON file if the process is interrupted mid-write (Ctrl+C,
       kill, power loss, antivirus lock). We write to a temp file in the
       same directory and then atomically swap it into place. os.replace()
       is atomic on POSIX *and* on Windows (unlike os.rename(), which on
       Windows raises FileExistsError if the destination already exists -
       os.replace() is the portable choice for "overwrite in place").
    2. Resilience - on Windows, antivirus or another process can transiently
       hold a lock on a file, causing PermissionError; on any OS the disk
       could be full or read-only. Losing history must never block the
       user's command from completing, so failures here are caught and
       reported softly instead of propagating.
    """
    try:
        directory = os.path.dirname(HISTORY_FILE)
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        _w(f"  {RED}history: {exc}{RST}\n")
        return

    if not _atomic_write(HISTORY_FILE, entries[-_max_entries():]):
        _w(f"  {RED}history: zapis nie powiódł się{RST}\n")


def setup(terminal):
    _t = terminal.t

    # Attach history list to terminal instance
    terminal._history = _load()


    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("history", {
            "get_history": lambda: getattr(terminal, "_history", []),
            "record": getattr(terminal, "_history_record", lambda x: None),
        })
    except Exception:
        pass
    def _record(line: str) -> None:
        """Append line to in-memory history + persist."""
        if not line:
            return
        if config.get("history.ignore_space", False) and line.startswith(" "):
            return
        if config.get("history.dedup", True) and terminal._history and terminal._history[-1] == line:
            return
        terminal._history.append(line)
        _save(terminal._history)

    # expose recorder so __init__.py run() can call it
    terminal._history_record = _record

    # ------------------------------------------------------------------ #
    #  Commands                                                            #
    # ------------------------------------------------------------------ #
    def history(args):
        entries = terminal._history
        if not entries:
            print(_t("history_empty"))
            return

        # sub-commands
        if args and args[0] == "clear":
            terminal._history.clear()
            _save([])
            print(_t("history_cleared"))
            return

        if args and args[0] == "search":
            if len(args) < 2:
                print(_t("history_search_usage"))
                return
            pattern = " ".join(args[1:]).lower()
            hits = [(i, e) for i, e in enumerate(entries, 1)
                    if pattern in e.lower()]
            if not hits:
                print(_t("history_no_match", pattern=pattern))
                return
            for idx, entry in hits:
                print(f"  {DIM}{idx:>4}{RST}  {entry}")
            return

        # default: show last N (default 20)
        try:
            limit = int(args[0]) if args else 20
        except ValueError:
            print(_t("history_usage"))
            return

        start = max(0, len(entries) - limit)
        for i, entry in enumerate(entries[start:], start + 1):
            print(f"  {DIM}{i:>4}{RST}  {entry}")

    def hrun(args):
        """Re-run a history entry by index."""
        if not args:
            print(_t("hrun_usage"))
            return
        try:
            idx = int(args[0])
        except ValueError:
            print(_t("hrun_usage"))
            return
        entries = terminal._history
        if idx < 1 or idx > len(entries):
            print(_t("hrun_out_of_range", idx=idx, total=len(entries)))
            return
        line = entries[idx - 1]
        print(f"  {CYN}>> {line}{RST}")

        # Replay through _run_line so that pipe chains (e.g. "ls | search .py")
        # are handled identically to a freshly typed command - including pipe
        # splitting, capture mode and proper quoting via the shlex tokenizer.
        # The previous direct call to commands[cmd]["func"](parts[1:]) bypassed
        # the pipe machinery and broke any history entry that contained "|".
        # _run_line also calls _history_record internally via __init__.py, so
        # we do NOT call _history_record here to avoid a duplicate entry.
        try:
            terminal._run_line(line)
        except SystemExit:
            raise
        except Exception as exc:
            print(f"{RED}{exc}{RST}")

    terminal.register_command(
        "history", history,
        description=_t("cmd_history"),
        category=_t("cat_history"),
    )
    terminal.register_command(
        "hrun", hrun,
        description=_t("cmd_hrun"),
        category=_t("cat_history"),
    )


def teardown(terminal):
    try:
        from . import _integration as _intg
        _intg.unregister("history")
    except Exception:
        pass
    terminal.commands.pop("history", None)
    terminal.commands.pop("hrun", None)
