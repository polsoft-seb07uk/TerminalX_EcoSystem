"""Env module for TerminalX.

View, set, unset, and search OS environment variables for the current session.

Author : Sebastian Januchowski
Brand  : polsoft.ITS(TM)
"""

import os





from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, IS_WIN, IS_LIN, IS_MAC, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad
def setup(terminal):
    _t = terminal.t

    def env(args):
        if not args:
            _list_all(_t)
            return

        sub = args[0]

        if sub == "get":
            _get(_t, args[1:])
        elif sub == "set":
            _set(_t, args[1:])
        elif sub == "unset":
            _unset(_t, args[1:])
        elif sub == "search":
            _search(_t, args[1:])
        elif sub == "path":
            _path(_t)
        else:
            # treat as `env get <NAME>` shorthand
            _get(_t, [sub])

    terminal.register_command(
        "env", env,
        description=_t("cmd_env"),
        category=_t("cat_env"),
    )


def _list_all(_t):
    pairs = sorted(os.environ.items())
    _w(f"\n  {BOLD}{CYN}{_t('env_list_header')} ({len(pairs)}){RST}\n\n")
    for k, v in pairs:
        short_v = v if len(v) <= 60 else v[:57] + "..."
        _w(f"  {YLW}{k:<30}{RST} {short_v}\n")
    _w("\n")


# Windows environment variable names are case-insensitive (the underlying
# Win32 API folds case), so `env get path` should find PATH just like it
# does in cmd.exe / PowerShell. POSIX keeps variables strictly case-sensitive
# (PATH and path are genuinely different variables there), so this lookup
# only kicks in as a fallback, and only on Windows.
def _find_env_key(name):
    if name in os.environ:
        return name
    if IS_WIN:
        lname = name.lower()
        for k in os.environ:
            if k.lower() == lname:
                return k
    return None


def _get(_t, args):
    if not args:
        print(_t("env_get_usage"))
        return
    name = args[0]
    key  = _find_env_key(name)
    if key is None:
        _w(f"  {RED}{_t('env_not_set', name=name)}{RST}\n")
    else:
        _w(f"  {YLW}{key}{RST} = {GRN}{os.environ[key]}{RST}\n")


def _set(_t, args):
    # env set NAME VALUE
    if len(args) < 2:
        print(_t("env_set_usage"))
        return
    name  = args[0]
    value = " ".join(args[1:])

    # "=" in a variable name is invalid on every OS (Windows' SetEnvironmentVariable
    # and POSIX putenv both reject it) - fail clearly instead of letting the
    # underlying os.environ[name] = value raise a confusing low-level error.
    if not name or "=" in name:
        _w(f"  {RED}{_t('env_invalid_name', name=name)}{RST}\n")
        return

    # Expand references to other variables inside the value, e.g.
    #   env set MYPATH $PATH:/extra        (POSIX style)
    #   env set MYPATH %PATH%;C:\extra      (Windows style)
    # so users can build on existing variables the same way regardless of OS.
    value = os.path.expandvars(value)

    try:
        os.environ[name] = value
    except UnicodeEncodeError:
        # Windows ties os.environ to the process's ANSI codepage for narrow
        # APIs; values with characters outside it can't be stored.
        _w(f"  {RED}{_t('env_set_encoding_error', name=name)}{RST}\n")
        return
    except (ValueError, OSError) as exc:
        _w(f"  {RED}{_t('env_set_failed', name=name, error=exc)}{RST}\n")
        return

    _w(f"  {GRN}[V]  {_t('env_set_ok', name=name, value=value)}{RST}\n")


def _unset(_t, args):
    if not args:
        print(_t("env_unset_usage"))
        return
    name = args[0]
    key  = _find_env_key(name)
    if key is None:
        _w(f"  {RED}{_t('env_not_set', name=name)}{RST}\n")
        return
    del os.environ[key]
    _w(f"  {YLW}[V]  {_t('env_unset_ok', name=key)}{RST}\n")


def _search(_t, args):
    if not args:
        print(_t("env_search_usage"))
        return
    pattern = args[0].lower()
    hits = [(k, v) for k, v in sorted(os.environ.items())
            if pattern in k.lower() or pattern in v.lower()]
    if not hits:
        print(_t("env_search_no_results", pattern=pattern))
        return
    _w(f"\n  {DIM}{_t('env_search_found', n=len(hits), pattern=pattern)}{RST}\n\n")
    for k, v in hits:
        short_v = v if len(v) <= 55 else v[:52] + "..."
        _w(f"  {YLW}{k:<30}{RST} {short_v}\n")
    _w("\n")


def _path(_t):
    """Pretty-print PATH entries one per line."""
    raw = os.environ.get("PATH", "")
    # os.pathsep is the canonical, OS-correct separator (";" on Windows,
    # ":" on POSIX) - more reliable than checking sys.platform manually,
    # since it's what the rest of the stdlib (e.g. shutil.which) relies on.
    entries = raw.split(os.pathsep)
    _w(f"\n  {BOLD}{CYN}PATH{RST} ({len(entries)} {_t('env_path_entries')})\n\n")
    for entry in entries:
        if entry == "":
            # an empty PATH segment means "current directory" on both
            # Windows and POSIX shells - call that out explicitly instead
            # of silently dropping it, since it's a meaningful (and often
            # unintentional / risky) entry.
            _w(f"  [{DIM}.{RST}] {DIM}{_t('env_path_empty_cwd')}{RST}\n")
            continue
        exists = os.path.isdir(entry)
        marker = GRN + "[V]" + RST if exists else RED + "[X]" + RST
        _w(f"  [{marker}] {entry}\n")
    _w("\n")


def teardown(terminal):
    terminal.commands.pop("env", None)
