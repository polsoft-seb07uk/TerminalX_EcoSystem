"""Command module for TerminalX."""

import os
import shutil
from . import config
from .ansi import cls as _ansi_cls
from . import _integration as _integration_cmd

from ._shared import ROOT_DIR, TRASH_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, _w, _pad

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# alias -> (path, desc_key)
_GO_DIRS = {
    "root":          (ROOT_DIR,                                      "dir_root"),
    "home":          (os.path.expanduser("~"),                       "dir_home"),
    "core":          (os.path.join(ROOT_DIR, "core"),                "dir_core"),
    "tools":         (os.path.join(ROOT_DIR, "tools"),               "dir_tools"),
    "scripts":       (os.path.join(ROOT_DIR, "scripts"),             "dir_scripts"),
    "modules":       (os.path.join(ROOT_DIR, "modules"),             "dir_modules"),
    "mod":           (os.path.join(ROOT_DIR, "modules"),             "dir_mod"),
    "plugins":       (os.path.join(ROOT_DIR, "plugins"),             "dir_plugins"),
    "plug":          (os.path.join(ROOT_DIR, "plugins"),             "dir_plug"),
    "libs":          (os.path.join(ROOT_DIR, "libs"),                "dir_libs"),
    "lib":           (os.path.join(ROOT_DIR, "libs"),                "dir_lib"),
    "lang":          (os.path.join(ROOT_DIR, "lang"),                "dir_lang"),
    "gui":           (os.path.join(ROOT_DIR, "gui"),                 "dir_gui"),
    "tests":         (os.path.join(ROOT_DIR, "tests"),               "dir_tests"),
    "docs":          (os.path.join(ROOT_DIR, "docs"),                "dir_docs"),
    "cache":         (os.path.join(ROOT_DIR, ".cache"),              "dir_cache"),
    "cache/scripts": (os.path.join(ROOT_DIR, ".cache", "scripts"),   "dir_cache_scripts"),
    "cache/tools":   (os.path.join(ROOT_DIR, ".cache", "tools"),     "dir_cache_tools"),
    "cache/global":  (os.path.join(ROOT_DIR, ".cache", "global"),    "dir_cache_global"),
    "trash":         (os.path.join(ROOT_DIR, ".trash"),              "dir_trash"),
}

# Directories that belong to the EcoSystem (relative to ROOT_DIR).
# Each entry: (rel_path, desc_key, show_contents)
_STRUCT_DIRS = [
    ("core",    "dir_core",    True),
    ("lang",    "dir_lang",    True),
    ("modules", "dir_modules", True),
    ("plugins", "dir_plugins", True),
    ("libs",    "dir_libs",    True),
    ("scripts", "dir_scripts", True),
    ("tools",   "dir_tools",   True),
    ("gui",     "dir_gui",     True),
    ("tests",   "dir_tests",   False),
    ("docs",    "dir_docs",    False),
    (".cache",  "dir_cache",   False),
    (".trash",  "dir_trash",   False),
]

# File extensions to highlight as code/data
_CODE_EXT = {".py", ".pyw", ".js", ".ts", ".bat", ".ps1",
             ".sh", ".json", ".toml", ".ini", ".cfg", ".md",
             ".txt", ".html", ".css"}

# Per-instance state: last cwd for `cd -`
# Keyed by id(terminal) so multiple instances don't share state.
_CD_STATE: dict = {}

# ---------------------------------------------------------------------------
# Path helpers (module-level, terminal-independent)
# ---------------------------------------------------------------------------

def _normalize_path(raw: str) -> str:
    """Normalize a user-typed path cross-platform.

    - Strips surrounding quotes
    - Converts foreign path separator to native
    - Expands env vars and ~
    """
    p = raw.strip().strip('"').strip("'")
    if not p:
        return p
    foreign = "/" if os.sep == "\\" else "\\"
    p = p.replace(foreign, os.sep)
    p = os.path.expandvars(p)
    p = os.path.expanduser(p)
    return p


def _resolve_path(raw: str) -> str:
    p = _normalize_path(raw)
    if not p:
        return p
    if not os.path.isabs(p):
        p = os.path.join(os.getcwd(), p)
    return os.path.abspath(p)


def _confirm(prompt_text: str) -> bool:
    try:
        answer = input(prompt_text).strip().lower()
    except EOFError:
        answer = ""
    return answer in ("y", "yes")


def _unique_trash_path(name: str) -> str:
    trash_path = os.path.join(TRASH_DIR, name)
    counter = 1
    base, ext = os.path.splitext(name)
    while os.path.exists(trash_path):
        trash_path = os.path.join(TRASH_DIR, f"{base}~{counter}{ext}")
        counter += 1
    return trash_path


def _move_to_trash(path: str, label: str, terminal) -> bool:
    _t = terminal.t
    _trash = _integration_cmd.get("trash")
    if _trash and callable(_trash.get("ensure_trash")):
        _trash["ensure_trash"]()
    else:
        os.makedirs(TRASH_DIR, exist_ok=True)
    if not os.path.exists(path):
        print(_t("rm_not_found", path=path))
        return False
    basename = os.path.basename(path)
    if config.get("confirm.rm", True):
        if not _confirm(_t("rm_confirm_prompt", name=basename)):
            print(_t("rm_cancelled"))
            return False
    trash_path = _unique_trash_path(basename)
    try:
        shutil.move(path, trash_path)
        print(_t("rm_moved", name=basename))
        return True
    except Exception as exc:
        print(f"{label}: {exc}")
        return False


def _remove_existing(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def _struct_file_color(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext == ".py":                    return YLW
    if ext in (".bat", ".ps1", ".sh"): return CYN
    if ext == ".json":                  return "\x1b[96m"  # bright cyan
    if ext in (".md", ".txt"):          return DIM
    if ext in _CODE_EXT:                return GRN
    return RST


# ---------------------------------------------------------------------------
# Command implementations (module-level, terminal passed explicitly)
# ---------------------------------------------------------------------------

def _cmd_cd(args, terminal):
    _t = terminal.t
    if len(args) > 1:
        print(_t("cd_usage"))
        return
    state = _CD_STATE.setdefault(id(terminal), {"last_cwd": None})
    prev = os.getcwd()
    if not args:
        target = os.path.expanduser("~")
    elif args[0] == "-":
        target = state["last_cwd"] or prev
    else:
        target = _normalize_path(args[0])
    try:
        os.chdir(target)
        state["last_cwd"] = prev
    except Exception as exc:
        print(f"cd: {exc}")


def _cmd_pwd(args, terminal):
    print(os.getcwd())


def _cmd_ls(args, terminal):
    """List directory contents.

    Flags (may be combined, e.g. -la or -al):
      -a   show hidden entries (dotfiles / entries starting with '.')
      -l   long format: permissions, size, modification date
    """
    import stat
    from datetime import datetime

    # --- parse flags and path -----------------------------------------------
    show_hidden = False
    long_fmt    = False
    path_arg    = None

    for tok in args:
        if tok.startswith("-") and len(tok) > 1 and all(c in "alAL" for c in tok[1:]):
            flags = tok[1:].lower()
            if "a" in flags:
                show_hidden = True
            if "l" in flags:
                long_fmt = True
        else:
            path_arg = tok

    path = _normalize_path(path_arg) if path_arg else "."

    # --- read directory ------------------------------------------------------
    try:
        raw = sorted(os.listdir(path), key=str.lower)
    except Exception as exc:
        print(f"ls: {exc}")
        return

    if not show_hidden:
        raw = [e for e in raw if not e.startswith(".")]

    dirs  = [e for e in raw if os.path.isdir(os.path.join(path, e))]
    files = [e for e in raw if not os.path.isdir(os.path.join(path, e))]
    entries = dirs + files

    if not entries:
        return

    if not long_fmt:
        for e in dirs:
            print(f"[DIR]  {e}")
        for e in files:
            print(f"[FILE] {e}")
        return

    # --- long format ---------------------------------------------------------
    def _human(n: int) -> str:
        for unit in ("B", "K", "M", "G", "T"):
            if n < 1024:
                return f"{n:>4}{unit}"
            n //= 1024
        return f"{n:>4}P"

    def _perms(st) -> str:
        is_dir = stat.S_ISDIR(st.st_mode)
        bits   = stat.S_IMODE(st.st_mode)
        chars  = "d" if is_dir else "-"
        for shift in (6, 3, 0):
            b = (bits >> shift) & 0o7
            chars += "r" if b & 4 else "-"
            chars += "w" if b & 2 else "-"
            chars += "x" if b & 1 else "-"
        return chars

    now = datetime.now()
    rows = []
    for e in entries:
        full = os.path.join(path, e)
        try:
            st   = os.stat(full)
            mtime = datetime.fromtimestamp(st.st_mtime)
            # same-year: show month+day+time; older: show month+day+year
            if mtime.year == now.year:
                date_str = mtime.strftime("%b %d %H:%M")
            else:
                date_str = mtime.strftime("%b %d  %Y")
            size_str = _human(st.st_size)
            perm_str = _perms(st)
        except OSError:
            size_str = "   ?"
            date_str = "??? ?? ?????'"
            perm_str = "??????????"
        label = e + "/" if os.path.isdir(full) else e
        rows.append((perm_str, size_str, date_str, label))

    for perm, size, date, label in rows:
        print(f"{perm}  {size}  {date}  {label}")


def _cmd_rm(args, terminal):
    _t = terminal.t
    if not args:
        print(_t("rm_usage"))
        return
    path = _resolve_path(args[0])
    _move_to_trash(path, label="rm", terminal=terminal)


def _cmd_del(args, terminal):
    _t = terminal.t
    if not args:
        print(_t("del_usage"))
        return
    path = _resolve_path(args[0])
    _move_to_trash(path, label="del", terminal=terminal)


def _cmd_mkdir(args, terminal):
    _t = terminal.t
    if not args:
        print(_t("mkdir_usage"))
        return
    path = _resolve_path(args[0])
    try:
        os.makedirs(path, exist_ok=True)
        print(_t("mkdir_created", path=path))
    except Exception as exc:
        print(f"mkdir: {exc}")


def _cmd_touch(args, terminal):
    _t = terminal.t
    if not args:
        print(_t("touch_usage"))
        return
    path = _resolve_path(args[0])
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        print(_t("file_parent_missing", path=parent))
        return
    try:
        with open(path, "a", encoding="utf-8"):
            pass
        os.utime(path, None)
        print(_t("touch_created", path=path))
    except Exception as exc:
        print(f"touch: {exc}")


def _cmd_cp(args, terminal):
    _t = terminal.t
    if len(args) != 2:
        print(_t("cp_usage"))
        return
    src = _resolve_path(args[0])
    dst = _resolve_path(args[1])
    if not os.path.exists(src):
        print(_t("file_not_found", path=src))
        return
    if os.path.exists(dst) and config.get("confirm.overwrite", True):
        if not _confirm(_t("overwrite_confirm_prompt", path=dst)):
            print(_t("overwrite_cancelled"))
            return
    try:
        if os.path.exists(dst):
            _remove_existing(dst)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            parent = os.path.dirname(dst)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(src, dst)
        print(_t("cp_done", src=src, dst=dst))
    except Exception as exc:
        print(f"cp: {exc}")


def _cmd_mv(args, terminal):
    _t = terminal.t
    if len(args) != 2:
        print(_t("mv_usage"))
        return
    src = _resolve_path(args[0])
    dst = _resolve_path(args[1])
    if not os.path.exists(src):
        print(_t("file_not_found", path=src))
        return
    if os.path.exists(dst) and config.get("confirm.overwrite", True):
        if not _confirm(_t("overwrite_confirm_prompt", path=dst)):
            print(_t("overwrite_cancelled"))
            return
    try:
        if os.path.exists(dst):
            _remove_existing(dst)
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.move(src, dst)
        print(_t("mv_done", src=src, dst=dst))
    except Exception as exc:
        print(f"mv: {exc}")


def _cmd_cat(args, terminal):
    _t = terminal.t
    if not args:
        print(_t("cat_usage"))
        return
    path = _resolve_path(args[0])
    if not os.path.exists(path):
        print(_t("file_not_found", path=path))
        return
    if not os.path.isfile(path):
        print(_t("cat_not_file", path=path))
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            print(f.read(), end="")
    except Exception as exc:
        print(f"cat: {exc}")


def _cmd_go(args, terminal):
    _t = terminal.t
    if not args:
        _w(f"\n{BOLD}{CYN}  +======================================+{RST}\n")
        _w(f"{BOLD}{CYN}  |   {_t('go_header'):<36}|{RST}\n")
        _w(f"{BOLD}{CYN}  +======================================+{RST}\n\n")
        _w(f"  {DIM}{_t('go_available')}{RST}\n\n")
        seen = {}
        for name, (path, desc_key) in _GO_DIRS.items():
            exists = os.path.isdir(path)
            status = GRN + "OK" + RST if exists else RED + "--" + RST
            if path in seen:
                alias_of = seen[path]
                desc = DIM + _t("go_alias", target=alias_of) + RST
            else:
                seen[path] = name
                desc = _t(desc_key)
            _w(f"  [{status}] {YLW}{_pad(name, 12)}{RST} {_pad(desc, 34)}{DIM}{path}{RST}\n")
        _w("\n")
        return

    dest = args[0].lower()
    if dest in _GO_DIRS:
        path = _GO_DIRS[dest][0]
    else:
        path = os.path.join(ROOT_DIR, _normalize_path(args[0]))

    if not os.path.isdir(path):
        _w(f"  {RED}{_t('go_not_exist', path=path)}{RST}\n")
        return
    try:
        os.chdir(path)
        _w(f"  {GRN}->{RST} {path}\n")
    except Exception as exc:
        _w(f"  {RED}{_t('go_error', exc=exc)}{RST}\n")


def _cmd_clear(args, terminal):
    """Clear terminal screen (cross-platform)."""
    _ansi_cls()


def _cmd_echo(args, terminal):
    """Print arguments to stdout.

    Flags:
      -n   suppress trailing newline
      -e   interpret escape sequences (\\n \\t \\r \\\\ \\a \\b)

    Examples:
      echo hello world
      echo -n no newline
      echo -e line1\\\\nline2
      ls | echo          # prints piped lines, then nothing extra
    """
    no_newline = False
    interpret  = False
    rest       = list(args)

    # parse leading flags (stop at first non-flag token)
    while rest and rest[0] in ("-n", "-e", "-ne", "-en"):
        flag = rest.pop(0)
        if "n" in flag:
            no_newline = True
        if "e" in flag:
            interpret = True

    text = " ".join(rest)
    if interpret:
        text = (
            text
            .replace("\\n",  "\n")
            .replace("\\t",  "\t")
            .replace("\\r",  "\r")
            .replace("\\a",  "\a")
            .replace("\\b",  "\b")
            .replace("\\\\", "\\")
        )
    print(text, end="" if no_newline else "\n")


def _cmd_struktura(args, terminal):
    _t = terminal.t
    unicode_ok = config.get("display.unicode", True)
    I  = "|  "
    T  = "+- "
    L  = "+- " if unicode_ok else "\\- "
    HR = "-" * 38

    _w(f"\n{BOLD}{BCYN}  +======================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |  >>  {_t('struct_title'):<32}|{RST}\n")
    _w(f"{BOLD}{BCYN}  +======================================+{RST}\n\n")

    root_name = os.path.basename(ROOT_DIR) or "TerminalX"
    _w(f"  {BOLD}{YLW}{root_name}/{RST}  {DIM}{ROOT_DIR}{RST}\n")

    try:
        root_files = sorted(
            f for f in os.listdir(ROOT_DIR)
            if os.path.isfile(os.path.join(ROOT_DIR, f))
            and not f.startswith(".")
        )
    except OSError:
        root_files = []

    all_items = root_files + [d[0] for d in _STRUCT_DIRS]
    last_root_idx = len(all_items) - 1

    for idx, fname in enumerate(root_files):
        is_last = (idx == last_root_idx)
        branch = L if is_last else T
        col = _struct_file_color(fname)
        _w(f"  {DIM}{branch}{RST}{col}{fname}{RST}\n")

    for dir_idx, (rel, desc_key, show_contents) in enumerate(_STRUCT_DIRS):
        abs_path   = os.path.join(ROOT_DIR, rel)
        global_idx = len(root_files) + dir_idx
        is_last_dir = (global_idx == last_root_idx)
        branch = L if is_last_dir else T
        vert   = "   " if is_last_dir else I
        exists = os.path.isdir(abs_path)
        status = "" if exists else f" {RED}[{_t('struct_missing')}]{RST}"

        _w(f"  {DIM}{branch}{RST}{BOLD}{CYN}{rel}/{RST}"
           f"  {DIM}{_t(desc_key)}{status}{RST}\n")

        if not show_contents or not exists:
            continue

        try:
            entries = sorted(os.listdir(abs_path))
        except OSError:
            continue

        entries = [e for e in entries
                   if e != "__pycache__" and not e.startswith(".")]

        if not entries:
            _w(f"  {vert}  {DIM}{_t('struct_empty')}{RST}\n")
            continue

        for eidx, entry in enumerate(entries):
            is_last_entry = (eidx == len(entries) - 1)
            eb = L if is_last_entry else T
            full = os.path.join(abs_path, entry)
            if os.path.isdir(full):
                _w(f"  {vert}{DIM}{eb}{RST}{BOLD}{entry}/{RST}\n")
            else:
                col = _struct_file_color(entry)
                _w(f"  {vert}{DIM}{eb}{RST}{col}{entry}{RST}\n")

    def _count_files(d):
        try:
            return len([f for f in os.listdir(d)
                        if os.path.isfile(os.path.join(d, f))])
        except OSError:
            return 0

    total_files = sum(
        _count_files(os.path.join(ROOT_DIR, d[0]))
        for d in _STRUCT_DIRS
        if os.path.isdir(os.path.join(ROOT_DIR, d[0]))
    )
    total_dirs = sum(
        1 for d in _STRUCT_DIRS
        if os.path.isdir(os.path.join(ROOT_DIR, d[0]))
    )
    _w(f"\n  {DIM}{HR}{RST}\n")
    _w(f"  {DIM}{_t('struct_summary', dirs=total_dirs, files=total_files)}{RST}\n\n")


# ---------------------------------------------------------------------------
# setup / teardown
# ---------------------------------------------------------------------------

_COMMANDS = [
    ("cd",        _cmd_cd,        "cmd_cd"),
    ("pwd",       _cmd_pwd,       "cmd_pwd"),
    ("ls",        _cmd_ls,        "cmd_ls"),
    ("rm",        _cmd_rm,        "cmd_rm"),
    ("del",       _cmd_del,       "cmd_del"),
    ("mkdir",     _cmd_mkdir,     "cmd_mkdir"),
    ("touch",     _cmd_touch,     "cmd_touch"),
    ("cp",        _cmd_cp,        "cmd_cp"),
    ("mv",        _cmd_mv,        "cmd_mv"),
    ("cat",       _cmd_cat,       "cmd_cat"),
    ("go",        _cmd_go,        "cmd_go"),
    ("clear",     _cmd_clear,     "cmd_clear"),
    ("cls",       _cmd_clear,     "cmd_cls"),
    ("struktura", _cmd_struktura, "cmd_struktura"),
    ("echo",      _cmd_echo,      "cmd_echo"),
]


def setup(terminal):
    _t = terminal.t
    cat = _t("cat_nav")
    for name, fn, desc_key in _COMMANDS:
        # Bind terminal via default argument to avoid late-binding closure issues.
        terminal.register_command(
            name,
            (lambda f, term=terminal: lambda args: f(args, term))(fn),
            description=_t(desc_key),
            category=cat,
        )

    # Komenda 'ecosystem' - inspekcja rejestru _integration
    def _cmd_ecosystem(args: list) -> None:
        sub = args[0].lower() if args else "status"

        if sub in ("status", "st"):
            _ecosystem_status(terminal)
        elif sub in ("list", "ls"):
            _ecosystem_list(terminal)
        elif sub in ("info",) and len(args) >= 2:
            _ecosystem_info(terminal, args[1])
        else:
            _ecosystem_status(terminal)

    terminal.register_command(
        "ecosystem", _cmd_ecosystem,
        description=_t("cmd_ecosystem") if "cmd_ecosystem" in terminal._t else "EcoSystem – status integracji modulow",
        category=_t("cat_ecosystem"),
    )
    terminal.register_command(
        "eco", _cmd_ecosystem,
        description=_t("cmd_eco") if "cmd_eco" in terminal._t else "Alias: ecosystem",
        category=_t("cat_ecosystem"),
    )


def _ecosystem_status(terminal) -> None:
    """Wyswietl status rejestru _integration."""
    try:
        from . import ansi as _a
        RST   = _a.reset()
        BOLD  = _a.bold()
        CYN   = _a.cyan
        GRN   = _a.success
        YLW   = _a.warning
        DIM   = _a.muted
    except Exception:
        RST = BOLD = ""; CYN = GRN = YLW = DIM = lambda x: x

    try:
        from . import _integration as _intg
        services = _intg.status()
        loaded   = terminal.loaded_modules
    except Exception:
        print("  [blad] Nie mozna pobrac statusu _integration")
        return

    all_modules = sorted(set(list(loaded.keys()) + list(services.keys())))

    print(f"\n  {BOLD}EcoSystem – Status modulow{RST}\n")
    print(f"  {'Modul':<20} {'Zaladowany':<14} {'Rejestr'}")
    print(f"  {'─'*20} {'─'*14} {'─'*20}")

    for name in all_modules:
        is_loaded   = "✓" if name in loaded  else "–"
        is_reg      = "✓ rejestr" if name in services else "–"
        loaded_col  = GRN(is_loaded) if name in loaded else DIM(is_loaded)
        reg_col     = GRN(is_reg) if name in services else DIM(is_reg)
        print(f"  {CYN(name):<20} {loaded_col:<14} {reg_col}")

    n_loaded = len(loaded)
    n_reg    = len(services)
    print(f"\n  {DIM(f'Zaladowane: {n_loaded}   Zarejestrowane: {n_reg}')}\n")


def _ecosystem_list(terminal) -> None:
    """Wyswietl liste zarejestrowanych serwisow."""
    try:
        from . import _integration as _intg
        services = _intg.status()
    except Exception:
        print("  [blad] Brak rejestru _integration")
        return

    if not services:
        print("  (brak zarejestrowanych serwisow)")
        return

    for name in sorted(services):
        print(f"  {name}")


def _ecosystem_info(terminal, service_name: str) -> None:
    """Wyswietl szczegoly serwisu z rejestru _integration."""
    try:
        from . import _integration as _intg
        svc = _intg.get(service_name)
    except Exception:
        svc = None

    if svc is None:
        print(f"  Serwis '{service_name}' nie jest zarejestrowany.")
        return

    print(f"\n  Serwis: {service_name}")
    print("  Dostepne metody:")
    for key in sorted(svc.keys()):
        val = svc[key]
        kind = "callable" if callable(val) else type(val).__name__
        print(f"    {key:<30} {kind}")
    print()


def teardown(terminal):
    _CD_STATE.pop(id(terminal), None)
    for name, _, __ in _COMMANDS:
        terminal.commands.pop(name, None)
    terminal.commands.pop("ecosystem", None)
    terminal.commands.pop("eco",       None)
