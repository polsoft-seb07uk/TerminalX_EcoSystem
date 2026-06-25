"""Cache module for TerminalX EcoSystem."""

import os
import sys
import re
import json
import time

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad, _atomic_write
CACHE_INDEX = os.path.join(CACHE_DIR, "global", "_index.json")

# -- helpers ------------------------------------------------------------------




def _ensure_cache():
    for subdir in ("global", "scripts", "tools"):
        os.makedirs(os.path.join(CACHE_DIR, subdir), exist_ok=True)
    if not os.path.exists(CACHE_INDEX):
        _write_index({})

def _read_index():
    try:
        with open(CACHE_INDEX, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _write_index(data):
    _atomic_write(CACHE_INDEX, data)

def _human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"

def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try: total += os.path.getsize(os.path.join(root, f))
            except OSError: pass
    return total

# -- menu ---------------------------------------------------------------------

def _cache_menu(_t):
    _w(f"\n{BOLD}{BCYN}  +======================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |   ?  {_t('cache_menu_title'):<31}|{RST}\n")
    _w(f"{BOLD}{BCYN}  +======================================+{RST}\n\n")
    cmds = [
        ("cache list",           _t("cache_help_list")),
        ("cache set <k> <v>",    _t("cache_help_set")),
        ("cache get <k>",        _t("cache_help_get")),
        ("cache del <k>",        _t("cache_help_del")),
        ("cache clear",          _t("cache_help_clear")),
        ("cache info",           _t("cache_help_info")),
    ]
    for c, d in cmds:
        _w(f"  {YLW}{_pad(c, 28)}{RST} {DIM}{d}{RST}\n")
    _w("\n")

# -- sub-commands ---------------------------------------------------------------

def _list(args, _t):
    _ensure_cache()
    index = _read_index()
    if not index:
        _w(f"  {DIM}{_t('cache_empty')}{RST}\n")
        return
    _w(f"\n{BOLD}  {_t('cache_col_key'):<24}{_t('cache_col_value'):<30}{_t('cache_col_age')}{RST}\n")
    _w(f"  {'-'*60}\n")
    now = time.time()
    for k, entry in sorted(index.items()):
        val = str(entry.get("value", ""))
        age = now - entry.get("ts", now)
        age_str = f"{int(age)}s" if age < 60 else f"{int(age//60)}m" if age < 3600 else f"{int(age//3600)}h"
        _w(f"  {YLW}{_pad(k, 24)}{RST}{_pad(val[:28], 30)}{DIM}{age_str}{RST}\n")
    _w("\n")

def _set(args, _t):
    if len(args) < 2:
        _w(f"  {RED}{_t('cache_err_set_usage')}{RST}\n"); return
    _ensure_cache()
    index = _read_index()
    key, value = args[0], " ".join(args[1:])
    index[key] = {"value": value, "ts": time.time()}
    _write_index(index)
    _w(f"  {GRN}{_t('cache_set_saved')}{RST} {key} = {value}\n")

def _get(args, _t):
    if not args:
        _w(f"  {RED}{_t('cache_err_get_usage')}{RST}\n"); return
    _ensure_cache()
    index = _read_index()
    key = args[0]
    if key not in index:
        _w(f"  {RED}{_t('cache_key_missing')}{RST} {key}\n"); return
    _w(f"  {YLW}{key}{RST} = {index[key]['value']}\n")

def _del(args, _t):
    if not args:
        _w(f"  {RED}{_t('cache_err_del_usage')}{RST}\n"); return
    _ensure_cache()
    index = _read_index()
    key = args[0]
    if key not in index:
        _w(f"  {RED}{_t('cache_key_missing')}{RST} {key}\n"); return
    del index[key]
    _write_index(index)
    _w(f"  {GRN}{_t('cache_deleted')}{RST} {key}\n")

def _clear(args, _t):
    _ensure_cache()
    index = _read_index()
    count = len(index)
    _write_index({})
    # Delete only files that belong to the cache index (scripts/, tools/ subdirs)
    # Never touch global/ files like history.json, aliases.json, config.json, task_log.json
    for subdir in ("scripts", "tools"):
        subpath = os.path.join(CACHE_DIR, subdir)
        if not os.path.isdir(subpath):
            continue
        for entry in os.listdir(subpath):
            path = os.path.join(subpath, entry)
            try:
                if os.path.isdir(path):
                    import shutil; shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception:
                pass
    _w(f"  {GRN}{_t('cache_cleared', count=count)}{RST}\n")

def _info(args, _t):
    _ensure_cache()
    index = _read_index()
    total_size = _dir_size(CACHE_DIR)
    _w(f"\n{BOLD}  {_t('cache_info_title')}{RST}\n")
    _w(f"  {_t('cache_info_entries_global'):<22}{YLW}{len(index)}{RST}\n")
    _w(f"  {_t('cache_info_size_total'):<22}{YLW}{_human_size(total_size)}{RST}\n")
    _w(f"  {_t('cache_info_location'):<22}{DIM}{CACHE_DIR}{RST}\n\n")
    # per-subdir stats
    _w(f"  {BOLD}{_t('cache_info_subdirs')}{RST}\n")
    for sub in ("global", "scripts", "tools"):
        subdir = os.path.join(CACHE_DIR, sub)
        if os.path.isdir(subdir):
            sz = _dir_size(subdir)
            idx_file = os.path.join(subdir, "_index.json")
            try:
                with open(idx_file, "r", encoding="utf-8") as f:
                    import json as _json
                    entries = len(_json.load(f))
            except Exception:
                entries = 0
            _w(f"    {YLW}{_pad(sub+'/', 14)}{RST}{_pad(_t('cache_subdir_entries', n=entries), 16)}{DIM}{_human_size(sz)}{RST}\n")
    _w("\n")

# -- setup / teardown ---------------------------------------------------------------

_SUB = {
    "list":  _list,
    "set":   _set,
    "get":   _get,
    "del":   _del,
    "clear": _clear,
    "info":  _info,
}

def setup(terminal):
    _ensure_cache()


    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("cache", {
            "read_index": _read_index,
            "write_index": _write_index,
            "ensure_cache": _ensure_cache,
        })
    except Exception:
        pass
    def _t(key, **kw):
        return terminal.t(key, **kw)

    def cache_cmd(args):
        if not args:
            _cache_menu(_t); return
        sub = args[0]
        if sub in _SUB:
            _SUB[sub](args[1:], _t)
        else:
            _w(f"  {RED}{_t('cache_unknown_sub', sub=sub)}{RST}\n")
            _cache_menu(_t)

    terminal.register_command(
        "cache", cache_cmd,
        description=_t("cmd_cache"),
        category=_t("cat_ecosystem"),
    )

def teardown(terminal):
    try:
        from . import _integration as _intg
        _intg.unregister("cache")
    except Exception:
        pass
    terminal.commands.pop("cache", None)
