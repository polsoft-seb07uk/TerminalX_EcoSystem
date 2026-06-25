"""Tools module for TerminalX EcoSystem.

Zarzadza katalogiem tools/ - metadane, tagi, cache wywolan.

Struktura:
  tools/
    edit.exe
    edit.meta.json       <- metadane narzedzia
  .tools_cache/
    _index.json          <- cache wywolan / wynikow
"""

import os
import sys
import re
import json
import time
import subprocess
import stat

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, IS_WIN, IS_LIN, IS_MAC, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad
TOOLS_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools")
TOOLS_CACHE_DIR = os.path.join(CACHE_DIR, "tools")
CACHE_INDEX = os.path.join(TOOLS_CACHE_DIR, "_index.json")


# -- helpers ------------------------------------------------------------------




def _ensure_dirs():
    os.makedirs(TOOLS_DIR,  exist_ok=True)
    os.makedirs(TOOLS_CACHE_DIR, exist_ok=True)
    if not os.path.exists(CACHE_INDEX):
        _write_cache({})
    # synchronizuj z centralnym cache przez rejestr (bez twardego importu)
    try:
        from . import _integration as _intg
        svc = _intg.get("cache")
        if svc and callable(svc.get("ensure_cache")):
            svc["ensure_cache"]()
    except Exception:
        pass

# -- meta files -----------------------------------------------------------------

def _normalize_tool_name(name: str) -> str:
    """Normalizuje nazwe narzedzia tak, by dzialala na Windows i POSIX."""
    name = name.strip()
    if not name:
        return name
    if IS_WIN:
        return name if name.lower().endswith(".exe") else name + ".exe"

    # POSIX: nie dopisujemy .exe. Jesli user podal foo.exe, a plik jest foo,
    # sprobuj dopasowac.
    if os.path.exists(os.path.join(TOOLS_DIR, name)):
        return name
    if name.lower().endswith(".exe"):
        alt = name[:-4]
        if os.path.exists(os.path.join(TOOLS_DIR, alt)):
            return alt
    return name


def _meta_path(name):
    # meta zapisujemy na bazie "nazwy logicznej" (bez .exe), ale zachowujemy
    # kompatybilnosc z istniejacymi plikami *.meta.json.
    base = name[:-4] if name.lower().endswith(".exe") else os.path.splitext(name)[0]
    return os.path.join(TOOLS_DIR, f"{base}.meta.json")

def _read_meta(name):
    path = _meta_path(name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _write_meta(name, data):
    with open(_meta_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _default_meta(name):
    return {
        "name":        name,
        "description": "",
        "tags":        [],
        "author":      "",
        "version":     "",
        "added":       time.strftime("%Y-%m-%d"),
    }

# -- cache ----------------------------------------------------------------------

def _read_cache():
    try:
        with open(CACHE_INDEX, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _write_cache(data):
    with open(CACHE_INDEX, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _cache_record(tool_name, args_str, note=""):
    cache = _read_cache()
    entry_id = f"{tool_name}:{int(time.time())}"
    cache[entry_id] = {
        "tool":  tool_name,
        "args":  args_str,
        "ts":    time.time(),
        "note":  note,
    }
    _write_cache(cache)

def _human_age(ts):
    age = time.time() - ts
    if age < 60:   return f"{int(age)}s"
    if age < 3600: return f"{int(age//60)}m"
    return f"{int(age//3600)}h"

# -- list all tools ---------------------------------------------------------------

def _all_tools():
    """Return list of tools in tools/ (cross-platform).

    Windows: domyslnie .exe
    POSIX: dowolny plik (zalecane: wykonywalny), z pominieciem *.meta.json
    """
    _ensure_dirs()
    out = []
    for f in os.listdir(TOOLS_DIR):
        if f.endswith(".meta.json"):
            continue
        p = os.path.join(TOOLS_DIR, f)
        if not os.path.isfile(p):
            continue
        if IS_WIN:
            if f.lower().endswith(".exe"):
                out.append(f)
        else:
            out.append(f)
    return sorted(out)

# -- menu -------------------------------------------------------------------------

def _tools_menu(_t):
    _w(f"\n{BOLD}{BCYN}  +======================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |   ?  {_t('tools_menu_title'):<31}|{RST}\n")
    _w(f"{BOLD}{BCYN}  +======================================+{RST}\n\n")
    cmds = [
        ("tools list",               _t("tools_help_list")),
        ("tools info <name>",        _t("tools_help_info")),
        ("tools tag <name> <tag>",   _t("tools_help_tag")),
        ("tools untag <name> <tag>", _t("tools_help_untag")),
        ("tools set <name> <k> <v>", _t("tools_help_set")),
        ("tools find <tag>",         _t("tools_help_find")),
        ("tools run <name> [args]",  _t("tools_help_run")),
        ("tools cache",              _t("tools_help_cache")),
        ("tools cache clear",        _t("tools_help_cache_clear")),
    ]
    for c, d in cmds:
        _w(f"  {YLW}{_pad(c, 30)}{RST} {DIM}{d}{RST}\n")
    _w("\n")

# -- sub-commands ------------------------------------------------------------------

def _cmd_list(args, _t):
    tools = _all_tools()
    if not tools:
        _w(f"  {DIM}{_t('tools_list_empty', dir=TOOLS_DIR)}{RST}\n"); return
    _w(f"\n{BOLD}  {_t('tools_col_name'):<22}{_t('tools_col_tags'):<28}{_t('tools_col_desc')}{RST}\n")
    _w(f"  {'-'*64}\n")
    for t in tools:
        meta = _read_meta(t)
        tags = ", ".join(meta.get("tags", [])) or DIM + "-" + RST
        desc = meta.get("description", "") or ""
        _w(f"  {YLW}{_pad(t, 22)}{RST}{MGT}{_pad(tags, 28)}{RST}{DIM}{desc}{RST}\n")
    _w("\n")

def _cmd_info(args, _t):
    if not args:
        _w(f"  {RED}{_t('tools_err_info_usage')}{RST}\n"); return
    name = _normalize_tool_name(args[0])
    path = os.path.join(TOOLS_DIR, name)
    if not os.path.exists(path):
        _w(f"  {RED}{_t('tools_not_found', name=name)}{RST}\n"); return
    meta = _read_meta(name) or _default_meta(name)
    size = os.path.getsize(path)
    _w(f"\n{BOLD}  {name}{RST}\n")
    _w(f"  {'-'*40}\n")
    fields = [
        (_t("tools_field_desc"),    meta.get("description", DIM + "-" + RST)),
        (_t("tools_field_tags"),    ", ".join(meta.get("tags", [])) or DIM + "-" + RST),
        (_t("tools_field_author"),  meta.get("author",  "") or DIM + "-" + RST),
        (_t("tools_field_version"), meta.get("version", "") or DIM + "-" + RST),
        (_t("tools_field_added"),   meta.get("added",   "") or DIM + "-" + RST),
        (_t("tools_field_size"),    f"{size:,} B ({size//1024} KB)"),
        (_t("tools_field_path"),    path),
    ]
    for k, v in fields:
        _w(f"  {CYN}{k+':':<12}{RST}{v}\n")
    _w("\n")

def _cmd_tag(args, _t):
    if len(args) < 2:
        _w(f"  {RED}{_t('tools_err_tag_usage')}{RST}\n"); return
    name = _normalize_tool_name(args[0])
    tag  = args[1].lower()
    meta = _read_meta(name) or _default_meta(name)
    if tag in meta.get("tags", []):
        _w(f"  {DIM}{_t('tools_tag_exists', tag=tag)}{RST}\n"); return
    meta.setdefault("tags", []).append(tag)
    _write_meta(name, meta)
    _w(f"  {GRN}{_t('tools_tag_added')}{RST} {name} <- {MGT}{tag}{RST}\n")

def _cmd_untag(args, _t):
    if len(args) < 2:
        _w(f"  {RED}{_t('tools_err_untag_usage')}{RST}\n"); return
    name = _normalize_tool_name(args[0])
    tag  = args[1].lower()
    meta = _read_meta(name) or _default_meta(name)
    tags = meta.get("tags", [])
    if tag not in tags:
        _w(f"  {RED}{_t('tools_tag_missing', tag=tag)}{RST}\n"); return
    tags.remove(tag)
    meta["tags"] = tags
    _write_meta(name, meta)
    _w(f"  {GRN}{_t('tools_tag_removed')}{RST} {name} ? {MGT}{tag}{RST}\n")

def _cmd_set(args, _t):
    if len(args) < 3:
        _w(f"  {RED}{_t('tools_err_set_usage')}{RST}\n"); return
    name  = _normalize_tool_name(args[0])
    key   = args[1]
    value = " ".join(args[2:])
    allowed = {"description", "author", "version"}
    if key not in allowed:
        _w(f"  {RED}{_t('tools_set_allowed', fields=', '.join(allowed))}{RST}\n"); return
    meta = _read_meta(name) or _default_meta(name)
    meta[key] = value
    _write_meta(name, meta)
    _w(f"  {GRN}{_t('tools_set_saved')}{RST} {name} -> {key} = {value}\n")

def _cmd_find(args, _t):
    if not args:
        _w(f"  {RED}{_t('tools_err_find_usage')}{RST}\n"); return
    tag   = args[0].lower()
    tools = _all_tools()
    found = [t for t in tools if tag in [x.lower() for x in _read_meta(t).get("tags", [])]]
    if not found:
        _w(f"  {DIM}{_t('tools_find_none')}{RST} {MGT}{tag}{RST}\n"); return
    _w(f"\n  {BOLD}{_t('tools_find_header')} {MGT}{tag}{RST}{BOLD}:{RST}\n")
    for t in found:
        meta = _read_meta(t)
        desc = meta.get("description", "")
        _w(f"    {YLW}{t:<22}{RST}{DIM}{desc}{RST}\n")
    _w("\n")

def _cmd_run(args, _t):
    if not args:
        _w(f"  {RED}{_t('tools_err_run_usage')}{RST}\n"); return
    name = _normalize_tool_name(args[0])
    path = os.path.join(TOOLS_DIR, name)
    if not os.path.exists(path):
        _w(f"  {RED}{_t('tools_not_found', name=name)}{RST}\n"); return
    run_args = args[1:]
    _w(f"  {GRN}{_t('tools_running')}{RST} {name} {' '.join(run_args)}\n")
    _cache_record(name, " ".join(run_args))
    try:
        if IS_WIN:
            # Windows: osobny proces konsolowy — wymagane dla aplikacji .exe
            # CREATE_NEW_CONSOLE (0x10) otwiera nowe okno terminala
            # CREATE_NEW_PROCESS_GROUP (0x200) izoluje sygnal Ctrl+C od rodzica
            _FLAGS = 0x00000010 | 0x00000200  # CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                [path] + run_args,
                creationflags=_FLAGS,
                close_fds=True,
            )
        else:
            # POSIX: dopilnuj prawa wykonywania (jesli to mozliwe).
            if not os.access(path, os.X_OK):
                try:
                    mode = os.stat(path).st_mode
                    os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except OSError:
                    pass
            # Detached: start_new_session odlacza od grupy procesow rodzica
            subprocess.Popen(
                [path] + run_args,
                close_fds=True,
                start_new_session=True,
            )
    except Exception as exc:
        _w(f"  {RED}{_t('tools_run_error', exc=exc)}{RST}\n")

def _cmd_cache(args, _t):
    if args and args[0] == "clear":
        _write_cache({})
        _w(f"  {GRN}{_t('tools_cache_cleared')}{RST}\n"); return
    cache = _read_cache()
    if not cache:
        _w(f"  {DIM}{_t('tools_cache_empty')}{RST}\n"); return
    _w(f"\n{BOLD}  {_t('tools_cache_col_tool'):<22}{_t('tools_cache_col_args'):<24}{_t('tools_cache_col_when')}{RST}\n")
    _w(f"  {'-'*56}\n")
    for _, entry in sorted(cache.items(), key=lambda x: x[1].get("ts", 0), reverse=True):
        tool = entry.get("tool", "?")
        a    = entry.get("args", "") or DIM + "-" + RST
        age  = _human_age(entry.get("ts", time.time()))
        _w(f"  {YLW}{_pad(tool, 22)}{RST}{_pad(a, 24)}{DIM}{_t('time_ago', age=age)}{RST}\n")
    _w("\n")

# -- setup / teardown ---------------------------------------------------------------

_SUB = {
    "list":  _cmd_list,
    "info":  _cmd_info,
    "tag":   _cmd_tag,
    "untag": _cmd_untag,
    "set":   _cmd_set,
    "find":  _cmd_find,
    "run":   _cmd_run,
    "cache": _cmd_cache,
}

def setup(terminal):
    _ensure_dirs()


    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("tools", {
            "list_tools": _all_tools,
            "cache_record": _cache_record,
            "tools_dir":    TOOLS_DIR,
        })
    except Exception:
        pass
    def _t(key, **kw):
        return terminal.t(key, **kw)

    def tools_cmd(args):
        if not args:
            _tools_menu(_t); return
        sub = args[0]
        if sub in _SUB:
            _SUB[sub](args[1:], _t)
        else:
            _w(f"  {RED}{_t('tools_unknown_sub', sub=sub)}{RST}\n")
            _tools_menu(_t)

    terminal.register_command(
        "tools", tools_cmd,
        description=_t("cmd_tools"),
        category=_t("cat_ecosystem"),
    )

def teardown(terminal):
    try:
        from . import _integration as _intg
        _intg.unregister("tools")
    except Exception:
        pass
    terminal.commands.pop("tools", None)
