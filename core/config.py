"""Config module for TerminalX EcoSystem.

Terminal settings manager - persistent, validated, type-safe.

Commands:
    config              - show settings menu
    config list         - list all settings with current values
    config get <key>    - show value of a setting
    config set <key> <value>  - change a setting
    config reset <key>  - reset one setting to default
    config reset --all  - reset all settings to defaults
    config info <key>   - detailed info about a setting (type, range, description)

Settings are saved to .cache/global/config.json and loaded on startup.
Each setting has a type, default value, allowed range/choices, and description key.
"""

import os
import sys
import re
import json

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, RST, BOLD, DIM, YLW, ORG, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad, _atomic_write
CONFIG_FILE = os.path.join(ROOT_DIR, ".cache", "global", "config.json")

# -- SCHEMA --------------------------------------------------------------------
# Each entry: (type, default, constraint, desc_key)
#   type:       "bool" | "int" | "str" | "choice"
#   default:    default value (Python native)
#   constraint: None | (min, max) for int | tuple of strings for choice
#   desc_key:   translation key for description

_SCHEMA: dict[str, tuple] = {
    # -- display --------------------------------------------------------------
    "prompt.symbol":        ("str",    "> ",     None,           "cfg_prompt_symbol"),
    "prompt.color":         ("choice", "yellow", (
                                "black", "red", "green", "yellow",
                                "blue",  "magenta", "cyan", "white",
                                "bright_red", "bright_green", "bright_yellow",
                                "bright_blue", "bright_magenta", "bright_cyan",
                            ),                                   "cfg_prompt_color"),
    "display.color":        ("bool",   True,     None,           "cfg_display_color"),
    "display.unicode":      ("bool",   True,     None,           "cfg_display_unicode"),
    "display.compact":      ("bool",   False,    None,           "cfg_display_compact"),
    "display.timestamp":    ("bool",   False,    None,           "cfg_display_timestamp"),
    "display.date_format":  ("choice", "iso",    ("iso", "eu", "us"),
                                                                 "cfg_display_date_format"),

    # -- history ---------------------------------------------------------------
    "history.enabled":      ("bool",   True,     None,           "cfg_history_enabled"),
    "history.max":          ("int",    500,      (10, 9999),     "cfg_history_max"),
    "history.dedup":        ("bool",   True,     None,           "cfg_history_dedup"),
    "history.ignore_space": ("bool",   False,    None,           "cfg_history_ignore_space"),

    # -- behaviour -------------------------------------------------------------
    "on_startup.show_help": ("bool",   False,    None,           "cfg_startup_help"),
    "on_startup.clear":     ("bool",   False,    None,           "cfg_startup_clear"),
    "on_startup.module_info":("bool",  False,    None,           "cfg_startup_module_info"),
    "error.verbose":        ("bool",   False,    None,           "cfg_error_verbose"),
    "error.beep":           ("bool",   False,    None,           "cfg_error_beep"),
    "confirm.rm":           ("bool",   True,     None,           "cfg_confirm_rm"),
    "confirm.trash_empty":  ("bool",   True,     None,           "cfg_confirm_trash_empty"),
    "confirm.overwrite":    ("bool",   True,     None,           "cfg_confirm_overwrite"),

    # -- network ---------------------------------------------------------------
    "net.timeout":          ("int",    10,       (1, 120),       "cfg_net_timeout"),
    "net.ping_count":       ("int",    4,        (1, 20),        "cfg_net_ping_count"),
    "net.ping_timeout":     ("int",    30,       (5, 120),       "cfg_net_ping_timeout"),
    "net.user_agent":       ("str",    "TerminalX/1.0", None,    "cfg_net_user_agent"),

    # -- tasks -----------------------------------------------------------------
    "task.max_log":         ("int",    200,      (10, 9999),     "cfg_task_max_log"),
    "task.max_output_lines":("int",    1000,     (50, 50000),    "cfg_task_max_output_lines"),
    "task.auto_clear":      ("bool",   False,    None,           "cfg_task_auto_clear"),

    # -- search ----------------------------------------------------------------
    "search.default_limit": ("int",    50,       (5, 9999),      "cfg_search_default_limit"),
    "search.follow_symlinks":("bool",  False,    None,           "cfg_search_follow_symlinks"),
    "search.show_hidden":   ("bool",   False,    None,           "cfg_search_show_hidden"),

    # -- scripts ---------------------------------------------------------------
    "scripts.confirm_run":  ("bool",   False,    None,           "cfg_scripts_confirm_run"),
    "scripts.show_ext":     ("bool",   True,     None,           "cfg_scripts_show_ext"),

    # -- modules ---------------------------------------------------------------
    "defender.enabled":     ("bool",   True,     None,           "cfg_defender_enabled"),
    "defender.block_cmds":  ("bool",   True,     None,           "cfg_defender_block_cmds"),
    "defender.max_events":  ("int",    500,      (10, 9999),     "cfg_defender_max_events"),
    "cache.max_entries":    ("int",    1000,     (10, 99999),    "cfg_cache_max_entries"),
    "pkg.confirm_install":  ("bool",   True,     None,           "cfg_pkg_confirm_install"),
    "pkg.timeout":          ("int",    30,       (5, 300),       "cfg_pkg_timeout"),

    # -- docs & reports ----------------------------------------------------
    "docs.default_format":  ("choice", "md",     ("md", "txt", "html", "json"),
                                                                 "cfg_docs_default_format"),
    "docs.confirm_delete":  ("bool",   True,     None,           "cfg_docs_confirm_delete"),

    # -- syntax highlight --------------------------------------------------
    "syntax.enabled":           ("bool",   True,     None,
                                                                 "cfg_syntax_enabled"),
    "syntax.theme":             ("choice", "default",
                                 ("default", "monokai", "solarized"),
                                                                 "cfg_syntax_theme"),
    "syntax.highlight_paths":   ("bool",   True,     None,
                                                                 "cfg_syntax_paths"),
    "syntax.highlight_numbers": ("bool",   True,     None,
                                                                 "cfg_syntax_numbers"),
    "syntax.highlight_strings": ("bool",   True,     None,
                                                                 "cfg_syntax_strings"),
    "syntax.highlight_comments":("bool",   True,     None,
                                                                 "cfg_syntax_comments"),
    "syntax.highlight_pipes":   ("bool",   True,     None,
                                                                 "cfg_syntax_pipes"),
}

# Ordered display groups for `config list`
_GROUPS: dict[str, list[str]] = {
    "cfg_group_display":    ["prompt.symbol", "prompt.color",
                             "display.color", "display.unicode", "display.compact",
                             "display.timestamp", "display.date_format"],
    "cfg_group_history":    ["history.enabled", "history.max",
                             "history.dedup", "history.ignore_space"],
    "cfg_group_behaviour":  ["on_startup.show_help", "on_startup.clear",
                             "on_startup.module_info",
                             "error.verbose", "error.beep",
                             "confirm.rm", "confirm.trash_empty", "confirm.overwrite"],
    "cfg_group_network":    ["net.timeout", "net.ping_count",
                             "net.ping_timeout", "net.user_agent"],
    "cfg_group_tasks":      ["task.max_log", "task.max_output_lines",
                             "task.auto_clear"],
    "cfg_group_search":     ["search.default_limit", "search.follow_symlinks",
                             "search.show_hidden"],
    "cfg_group_scripts":    ["scripts.confirm_run", "scripts.show_ext"],
    "cfg_group_modules":    ["defender.enabled", "defender.block_cmds",
                             "defender.max_events",
                             "cache.max_entries",
                             "pkg.confirm_install", "pkg.timeout"],
    "cfg_group_docs":       ["docs.default_format", "docs.confirm_delete"],
    "cfg_group_syntax":     ["syntax.enabled", "syntax.theme",
                             "syntax.highlight_paths", "syntax.highlight_numbers",
                             "syntax.highlight_strings", "syntax.highlight_comments",
                             "syntax.highlight_pipes"],
}

# -- ANSI colour map for prompt.color -----------------------------------------

_COLOR_CODES: dict[str, str] = {
    "black":          "\x1b[30m", "red":            "\x1b[31m",
    "green":          "\x1b[32m", "yellow":         "\x1b[33m",
    "blue":           "\x1b[34m", "magenta":        "\x1b[35m",
    "cyan":           "\x1b[36m", "white":          "\x1b[37m",
    "bright_red":     "\x1b[91m", "bright_green":   "\x1b[92m",
    "bright_yellow":  "\x1b[93m", "bright_blue":    "\x1b[94m",
    "bright_magenta": "\x1b[95m", "bright_cyan":    "\x1b[96m",
}

# -- persistence ---------------------------------------------------------------

def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

def _read_file() -> dict:
    """Read config.json; return empty dict on any error."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}

def _write_file(data: dict) -> bool:
    """Atomically write config.json. Returns True on success."""
    _ensure_dir()
    return _atomic_write(CONFIG_FILE, data, fsync=False)

# -- in-memory store (initialised in setup) -----------------------------------

_store: dict[str, object] = {}   # key -> current value (Python native)

def _defaults() -> dict:
    return {k: v[1] for k, v in _SCHEMA.items()}

def _load() -> None:
    """Populate _store: defaults <- saved file, validated entry by entry."""
    global _store
    _store = _defaults()
    saved = _read_file()
    for key, raw in saved.items():
        if key not in _SCHEMA:
            continue          # ignore unknown keys silently
        validated = _validate(key, str(raw))
        if validated is not None:
            _store[key] = validated   # only load valid values

def _save() -> bool:
    return _write_file(_store)

# -- validation ----------------------------------------------------------------

def _validate(key: str, raw: str):
    """Parse and validate raw string against schema for key.
    Returns the typed value on success, None on failure.
    Sets _last_error for error messages."""
    global _last_error
    if key not in _SCHEMA:
        _last_error = ("cfg_err_unknown_key", {"name": key})
        return None

    typ, _default, constraint, _desc = _SCHEMA[key]

    if typ == "bool":
        if raw.lower() in ("true", "1", "yes", "on"):
            return True
        if raw.lower() in ("false", "0", "no", "off"):
            return False
        _last_error = ("cfg_err_bool", {"name": key})
        return None

    if typ == "int":
        try:
            val = int(raw)
        except ValueError:
            _last_error = ("cfg_err_int", {"name": key})
            return None
        lo, hi = constraint
        if not (lo <= val <= hi):
            _last_error = ("cfg_err_range", {"name": key, "lo": lo, "hi": hi})
            return None
        return val

    if typ == "str":
        if not raw:
            _last_error = ("cfg_err_empty_str", {"name": key})
            return None
        return raw

    if typ == "choice":
        if raw.lower() in constraint:
            return raw.lower()
        _last_error = ("cfg_err_choice", {"name": key, "choices": ", ".join(constraint)})
        return None

def _fmt_value(key: str, val) -> str:
    """Return coloured display string for a value."""
    typ = _SCHEMA[key][0]
    if typ == "bool":
        return (GRN + "true" + RST) if val else (RED + "false" + RST)
    if key == "prompt.color":
        code = _COLOR_CODES.get(str(val), "")
        return f"{code}{val}{RST}"
    return f"{YLW}{val}{RST}"

def _fmt_type(key: str, _t) -> str:
    """Return human-readable type/constraint string."""
    typ, _def, constraint, _ = _SCHEMA[key]
    if typ == "bool":
        return _t("cfg_type_bool")
    if typ == "int":
        lo, hi = constraint
        return _t("cfg_type_int", lo=lo, hi=hi)
    if typ == "str":
        return _t("cfg_type_str")
    if typ == "choice":
        return _t("cfg_type_choice", choices=", ".join(constraint))
    return typ

# -- public API (used by other modules) ---------------------------------------

def get(key: str, fallback=None):
    """Return current value of a config key, or fallback if unknown."""
    return _store.get(key, fallback)

def get_section(prefix: str) -> dict:
    """Return all config keys starting with prefix as {suffix: value}.

    Przykład: get_section("syntax") → {"enabled": True, "theme": "default", ...}
    """
    result = {}
    p = prefix.rstrip(".") + "."
    for key, val in _store.items():
        if key.startswith(p):
            result[key[len(p):]] = val
    return result

def color_code(name: str) -> str:
    """Return the raw ANSI escape code for a named colour (e.g. prompt.color)."""
    return _COLOR_CODES.get(str(name).lower(), "")

# -- menu ----------------------------------------------------------------------

def _menu(t) -> None:
    _w(f"\n{BOLD}{BCYN}  ╭──────────────────────────────────────╮{RST}\n")
    _w(f"{BOLD}{BCYN}  │   ⚙  {t('cfg_module_title'):<33}│{RST}\n")
    _w(f"{BOLD}{BCYN}  ╰──────────────────────────────────────╯{RST}\n\n")
    cmds = [
        ("config list",             t("cfg_cmd_list")),
        ("config get <key>",        t("cfg_cmd_get")),
        ("config set <key> <val>",  t("cfg_cmd_set")),
        ("config reset <key>",      t("cfg_cmd_reset_one")),
        ("config reset --all",      t("cfg_cmd_reset_all")),
        ("config info <key>",       t("cfg_cmd_info")),
    ]
    for c, d in cmds:
        _w(f"  {YLW}{_pad(c, 28)}{RST} {DIM}{d}{RST}\n")
    _w(f"\n  {DIM}{t('cfg_hint_count', n=len(_SCHEMA))}{RST}\n\n")

# -- sub-commands --------------------------------------------------------------

def _cmd_list(args: list, t) -> None:
    _w(f"\n{BOLD}  {t('cfg_list_header')}{RST}\n\n")
    for group_key, keys in _GROUPS.items():
        _w(f"  {BOLD}{CYN}{t(group_key).upper()}{RST}\n")
        for key in keys:
            if key not in _SCHEMA:
                continue
            val      = _store.get(key, _SCHEMA[key][1])
            default  = _SCHEMA[key][1]
            is_mod   = val != default
            marker   = f" {ORG}*{RST}" if is_mod else "  "
            _w(f"    {_pad(key, 26)}{_fmt_value(key, val)}{marker}\n")
        _w("\n")
    _w(f"  {DIM}{t('cfg_list_legend')}{RST}\n\n")

def _cmd_get(args: list, t) -> None:
    if not args:
        _w(f"  {RED}{t('cfg_err_get_usage')}{RST}\n")
        return
    key = args[0]
    if key not in _SCHEMA:
        _w(f"  {RED}{t('cfg_err_unknown_key', **{'name': key})}{RST}\n")
        return
    val     = _store.get(key, _SCHEMA[key][1])
    default = _SCHEMA[key][1]
    _w(f"\n  {BOLD}{key}{RST}\n")
    _w(f"    {t('cfg_label_value'):<14}{_fmt_value(key, val)}\n")
    _w(f"    {t('cfg_label_default'):<14}{_fmt_value(key, default)}\n")
    _w(f"    {t('cfg_label_type'):<14}{DIM}{_fmt_type(key, t)}{RST}\n\n")

def _cmd_set(args: list, t) -> None:
    if len(args) < 2:
        _w(f"  {RED}{t('cfg_err_set_usage')}{RST}\n")
        return
    key = args[0]
    raw = " ".join(args[1:])
    if key not in _SCHEMA:
        _w(f"  {RED}{t('cfg_err_unknown_key', **{'name': key})}{RST}\n")
        return
    val = _validate(key, raw)
    if val is None:
        err_key, err_kw = _last_error
        _w(f"  {RED}{t(err_key, **err_kw)}{RST}\n")
        return
    old       = _store.get(key, _SCHEMA[key][1])
    _store[key] = val
    if not _save():
        _store[key] = old   # rollback on write failure
        _w(f"  {RED}{t('cfg_err_save')}{RST}\n")
        return
    _w(f"  {GRN}{t('cfg_set_ok', **{'name': key})}{RST} {_fmt_value(key, val)}\n")
    # Odswież syntax_highlight jesli zmieniono ustawienie syntax.*
    if key.startswith("syntax."):
        try:
            from . import _integration as _intg
            hl = (_intg.get("syntax_highlight") or {}).get("apply_config")
            if callable(hl):
                hl(get)
        except Exception:
            pass

def _cmd_reset(args: list, t) -> None:
    if not args:
        _w(f"  {RED}{t('cfg_err_reset_usage')}{RST}\n")
        return
    if args[0] == "--all":
        _store.clear()
        _store.update(_defaults())
        if not _save():
            _w(f"  {RED}{t('cfg_err_save')}{RST}\n")
            return
        _w(f"  {GRN}{t('cfg_reset_all_ok', n=len(_SCHEMA))}{RST}\n")
        return
    key = args[0]
    if key not in _SCHEMA:
        _w(f"  {RED}{t('cfg_err_unknown_key', **{'name': key})}{RST}\n")
        return
    default     = _SCHEMA[key][1]
    _store[key] = default
    if not _save():
        _w(f"  {RED}{t('cfg_err_save')}{RST}\n")
        return
    _w(f"  {GRN}{t('cfg_reset_ok', **{'name': key})}{RST} {_fmt_value(key, default)}\n")

def _cmd_info(args: list, t) -> None:
    if not args:
        _w(f"  {RED}{t('cfg_err_info_usage')}{RST}\n")
        return
    key = args[0]
    if key not in _SCHEMA:
        _w(f"  {RED}{t('cfg_err_unknown_key', **{'name': key})}{RST}\n")
        return
    typ, default, constraint, desc_key = _SCHEMA[key]
    val = _store.get(key, default)
    _w(f"\n  {BOLD}{BCYN}{key}{RST}\n")
    _w(f"  {'-' * 40}\n")
    _w(f"  {t('cfg_label_desc'):<14}{DIM}{t(desc_key)}{RST}\n")
    _w(f"  {t('cfg_label_value'):<14}{_fmt_value(key, val)}\n")
    _w(f"  {t('cfg_label_default'):<14}{_fmt_value(key, default)}\n")
    _w(f"  {t('cfg_label_type'):<14}{DIM}{_fmt_type(key, t)}{RST}\n")
    if typ == "choice":
        _w(f"  {t('cfg_label_choices'):<14}")
        for i, ch in enumerate(constraint):
            code = _COLOR_CODES.get(ch, "")
            mark = f" {GRN}[V]{RST}" if ch == val else ""
            _w(f"{code}{ch}{RST}{mark}")
            _w("  " if i < len(constraint) - 1 else "")
        _w("\n")
    _w("\n")

# -- dispatch table ------------------------------------------------------------

_SUB = {
    "list":  _cmd_list,
    "get":   _cmd_get,
    "set":   _cmd_set,
    "reset": _cmd_reset,
    "info":  _cmd_info,
}

# -- setup / teardown ----------------------------------------------------------

def setup(terminal) -> None:
    _load()

    # Wrap terminal.t to avoid 'key' kwarg clash (terminal.t signature is t(key, **kw))
    def _t(msg_key: str, **kw) -> str:
        return terminal.t(msg_key, **kw)

    def config_cmd(args: list) -> None:
        if not args:
            _menu(_t)
            return
        sub = args[0].lower()
        if sub in _SUB:
            _SUB[sub](args[1:], _t)
        else:
            _w(f"  {RED}{_t('cfg_unknown_sub', sub=sub)}{RST}\n")
            _menu(_t)

    for alias in ("config", "cfg"):
        terminal.register_command(
            alias, config_cmd,
            description=_t("cmd_config"),
            category=_t("cat_ecosystem"),
        )

    # Rejestracja w _integration – inne moduly moga pobierac konfiguracje
    try:
        from . import _integration as _intg
        _intg.register("config", {
            "get":          get,
            "color_code":   color_code,
            "get_section":  get_section,
            "schema":       lambda: dict(_SCHEMA),
        })
    except Exception:
        pass


def teardown(terminal) -> None:
    try:
        from . import _integration as _intg
        _intg.unregister("config")
    except Exception:
        pass
    terminal.commands.pop("config", None)
    terminal.commands.pop("cfg",    None)
