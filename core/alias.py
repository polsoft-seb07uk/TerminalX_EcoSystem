"""Alias module for TerminalX.

Lets users define short aliases for long command sequences.
Aliases are persisted across sessions in .cache/global/aliases.json.

Author : Sebastian Januchowski
Brand  : polsoft.ITS(TM)
"""

import os
import json

from ._shared import ROOT_DIR, RST, BOLD, DIM, YLW, RED, CYN, _w, _atomic_write
ALIAS_FILE  = os.path.join(ROOT_DIR, ".cache", "global", "aliases.json")


def _load() -> dict:
    try:
        with open(ALIAS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                # tolerate stray non-string values from a hand-edited or
                # corrupted file instead of crashing later on .split()
                return {k: v for k, v in data.items() if isinstance(v, str)}
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, UnicodeDecodeError):
        # corrupted or wrongly-encoded file (e.g. leftover from an
        # interrupted write, or an old file written under a different
        # codepage on Windows) - start fresh rather than blocking startup
        pass
    except OSError as exc:
        # permission errors, locked file (common transiently on Windows
        # when antivirus scans a just-written file), etc.
        _w(f"  {RED}alias: {exc}{RST}\n")
    return {}


def _save(aliases: dict) -> None:
    """Persist aliases to disk, atomically and without crashing the REPL.

    Same approach as core/history.py and core/task.py: write to a temp file
    in the same directory, fsync, then os.replace() into place. os.replace()
    is atomic on both POSIX and Windows, so an interrupted write (Ctrl+C,
    kill, power loss, a transient antivirus lock on Windows) never leaves a
    truncated/corrupt aliases.json behind. I/O failures are reported but
    swallowed - losing the alias save must not crash the command the user
    just typed.
    """
    try:
        directory = os.path.dirname(ALIAS_FILE)
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        _w(f"  {RED}alias: {exc}{RST}\n")
        return

    if not _atomic_write(ALIAS_FILE, aliases):
        _w(f"  {RED}alias: zapis nie powiódł się{RST}\n")


# protected names that cannot be aliased
_PROTECTED = {"alias", "exit", "help"}


def setup(terminal):
    _t = terminal.t

    terminal._aliases = _load()

    # Hard ceiling on alias-chain depth. The docstring says "one level of
    # alias chaining" but the recursive implementation had no actual limit,
    # so a cycle (alias a -> b, alias b -> a) would recurse until hitting
    # Python's recursion limit. That's eventually caught as an Exception by
    # the dispatcher in core/__init__.py, but only after burning through
    # ~1000 stack frames first - costly on every OS, and stack-overflow
    # behavior at the C level is less predictable on Windows than on
    # POSIX. A small explicit limit fails fast and cleanly everywhere.
    _MAX_ALIAS_DEPTH = 20


    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("alias", {
            "get_aliases": lambda: getattr(terminal, "_aliases", {}),
        })
    except Exception:
        pass
    def _expand_and_run(name: str, user_args: list, _depth: int = 0) -> None:
        """Expand alias and execute; appends user_args to expanded command.

        Routes the fully-expanded line through terminal._run_line so that
        pipe chains inside an alias expansion (e.g. `alias ll ls | search .py`)
        work identically to a command typed interactively.  The previous
        direct call to commands[cmd]["func"]() bypassed the pipe machinery.

        Alias chaining is resolved before handing off to _run_line: if the
        first token of the expansion is itself an alias, we recurse once more
        (up to _MAX_ALIAS_DEPTH) rather than letting _run_line hit the alias
        command handler (which would re-enter this function from a fresh
        depth=0, silently resetting the cycle counter).
        """
        if _depth >= _MAX_ALIAS_DEPTH:
            print(_t("alias_cycle_detected", name=name))
            return

        expansion = terminal._aliases.get(name, "")
        # Use the same quote-aware tokenizer the REPL uses so that a
        # multi-word quoted argument in the expansion is kept intact.
        from . import _tokenize
        parts = _tokenize(expansion) + user_args
        if not parts:
            return

        cmd = parts[0]
        # Chain: first token is itself an alias -> recurse with depth guard.
        if cmd in terminal._aliases:
            _expand_and_run(cmd, parts[1:], _depth + 1)
            return

        # Rebuild the expanded line and dispatch through _run_line so that
        # pipe segments, quoting and capture mode all work correctly.
        import shlex
        expanded_line = shlex.join(parts) if hasattr(shlex, "join") else " ".join(parts)
        try:
            terminal._run_line(expanded_line)
        except SystemExit:
            raise
        except Exception as exc:
            print(_t("cmd_exec_error", cmd=cmd, exc=exc))

    def _register_alias(name: str) -> None:
        terminal.commands[name] = {
            "func":        lambda args, n=name: _expand_and_run(n, args),
            "description": f'{_t("alias_expands_to")} {terminal._aliases[name]}',
            "category":    _t("cat_alias"),
        }

    def _unregister_alias(name: str) -> None:
        terminal.commands.pop(name, None)

    # register already-persisted aliases as commands
    for name in terminal._aliases:
        _register_alias(name)

    # expose helpers so alias module can manage itself
    terminal._alias_register   = _register_alias
    terminal._alias_unregister = _unregister_alias

    # ------------------------------------------------------------------ #
    def alias(args):
        """alias                      - list all
           alias <name> <cmd...>      - define
           alias remove <name>        - delete"""

        if not args:
            # list
            if not terminal._aliases:
                print(_t("alias_none"))
                return
            print(f"\n  {BOLD}{CYN}{_t('alias_list_header')}{RST}\n")
            for name, expansion in sorted(terminal._aliases.items()):
                print(f"  {YLW}{name:<16}{RST} {DIM}->{RST} {expansion}")
            print()
            return

        if args[0] == "remove":
            if len(args) < 2:
                print(_t("alias_remove_usage"))
                return
            name = args[1]
            if name not in terminal._aliases:
                print(_t("alias_not_found", name=name))
                return
            del terminal._aliases[name]
            _unregister_alias(name)
            _save(terminal._aliases)
            print(_t("alias_removed", name=name))
            return

        # define: alias <name> <expansion...>
        if len(args) < 2:
            print(_t("alias_usage"))
            return

        name = args[0]
        if name in _PROTECTED:
            print(_t("alias_protected", name=name))
            return
        expansion = " ".join(args[1:])
        terminal._aliases[name] = expansion
        _register_alias(name)
        _save(terminal._aliases)
        print(_t("alias_set", name=name, expansion=expansion))

    terminal.register_command(
        "alias", alias,
        description=_t("cmd_alias"),
        category=_t("cat_alias"),
    )


def teardown(terminal):
    try:
        from . import _integration as _intg
        _intg.unregister("alias")
    except Exception:
        pass
    # remove alias command + all dynamically created alias commands
    terminal.commands.pop("alias", None)
    for name in list(getattr(terminal, "_aliases", {}).keys()):
        terminal.commands.pop(name, None)
