"""Scripts module for TerminalX EcoSystem.

Zarzadza katalogiem scripts/ - metadane, tagi, cache wywolan.
Obsluguje: .bat, .ps1, .js, .html, .py, .sh

Struktura:
  scripts/
    myscript.ps1
    myscript.meta.json   <- metadane skryptu
  .scripts_cache/
    _index.json          <- historia wywolan
"""

import os
import sys
import re
import json
import time
import subprocess
import shutil
import webbrowser
from pathlib import Path

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, IS_WIN, IS_LIN, IS_MAC, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad
SCRIPTS_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
SCRIPTS_CACHE_DIR = os.path.join(CACHE_DIR, "scripts")
CACHE_INDEX  = os.path.join(SCRIPTS_CACHE_DIR, "_index.json")

# Rozszerzenia skryptow obslugiwane przez `scripts run`.
# Wazne: uruchamianie jest dobierane dynamicznie na podstawie OS i tego,
# czy wymagane programy sa dostepne w PATH (np. node, bash, pwsh).
SUPPORTED_EXTS = {".bat", ".ps1", ".js", ".html", ".py", ".sh"}


def _runner_for_ext(ext: str) -> list[str] | None:
    """Zwraca runner (lista argumentow dla subprocess) albo None gdy brak wsparcia.

    Integracja z runner.py: uzywamy _EXT_MAP + _find_interpreter z runner.py
    zamiast duplikowac logike wyszukiwania. Fallback lokalny jesli runner
    niedostepny.

    Zwraca:
      []   -> webbrowser (HTML)
      None -> brak wsparcia / brak interpretera
      list -> pelny runner prefix (np. ["python3"] albo ["pwsh", "-ExecutionPolicy", ...])
    """
    ext = (ext or "").lower()

    # .py: zawsze uruchamiaj tym samym interpreterem co TerminalX
    if ext == ".py":
        return [sys.executable]

    # .html: webbrowser (bez subprocess)
    if ext in (".html", ".htm"):
        return []

    # .bat/.cmd: tylko Windows, bez runnera
    if ext in (".bat", ".cmd"):
        return ["cmd", "/c"] if IS_WIN else None

    # -- delegacja do _integration (runner.py lub fallback) ------------------
    try:
        from . import _integration as _intg
        runner = _intg.get("runner")
        if runner:
            ext_map = runner.get("ext_map", {})
            plugins = runner.get("plugins", {})
            plugin_name = ext_map.get(ext)
            if plugin_name:
                pdata = plugins.get(plugin_name, {})
                if pdata.get("_win_only") and not IS_WIN:
                    return None
                interp, extra = _intg.find_interpreter(ext)
                if interp and interp != "_webbrowser":
                    return [interp] + extra
        else:
            # runner nie zaladowany - uzyj find_interpreter z fallbackiem
            interp, extra = _intg.find_interpreter(ext)
            if interp and interp != "_webbrowser":
                return [interp] + extra
    except Exception:
        pass

    # -- fallback jesli runner niedostepny ------------------------------------
    _FB: dict[str, list[str]] = {
        ".js":  ["node"],
        ".sh":  ["bash"],
        ".ps1": ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"],
    }
    for candidate, prefix in _FB.items():
        if ext == candidate and shutil.which(prefix[0]):
            return prefix
    return None

# -- helpers ------------------------------------------------------------------




def _ensure_dirs():
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    os.makedirs(SCRIPTS_CACHE_DIR, exist_ok=True)
    if not os.path.exists(CACHE_INDEX):
        _write_cache({})
    # synchronizuj z centralnym cache przez rejestr (bez twardego importu)
    try:
        from . import _integration as _intg
        _intg.call("cache", "ensure_cache")
    except Exception:
        pass

def _ext(name):
    return os.path.splitext(name)[1].lower()

def _ext_color(name):
    colors = {
        ".bat":  "\x1b[93m",   # yellow
        ".ps1":  "\x1b[94m",   # blue
        ".js":   "\x1b[33m",   # gold
        ".html": "\x1b[91m",   # red
        ".py":   "\x1b[92m",   # green
        ".sh":   "\x1b[96m",   # cyan
    }
    return colors.get(_ext(name), DIM)

# -- meta ----------------------------------------------------------------------

def _meta_path(name):
    return os.path.join(SCRIPTS_DIR, f"{name}.meta.json")

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
        "lang":        _ext(name).lstrip("."),
        "added":       time.strftime("%Y-%m-%d"),
    }

# -- cache -----------------------------------------------------------------------

def _read_cache():
    try:
        with open(CACHE_INDEX, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _write_cache(data):
    with open(CACHE_INDEX, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _cache_record(name, args_str):
    cache = _read_cache()
    entry_id = f"{name}:{int(time.time())}"
    cache[entry_id] = {
        "script": name,
        "args":   args_str,
        "ts":     time.time(),
        "lang":   _ext(name).lstrip("."),
    }
    _write_cache(cache)

def _human_age(ts):
    age = time.time() - ts
    if age < 60:   return f"{int(age)}s"
    if age < 3600: return f"{int(age//60)}m"
    return f"{int(age//3600)}h"

# -- all scripts -------------------------------------------------------------------

def _all_scripts():
    _ensure_dirs()
    return sorted(
        f for f in os.listdir(SCRIPTS_DIR)
        if _ext(f) in SUPPORTED_EXTS
        and os.path.isfile(os.path.join(SCRIPTS_DIR, f))
    )

# -- menu -----------------------------------------------------------------------

def _scripts_menu(_t):
    _w(f"\n{BOLD}{BCYN}  +======================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |   ?  {_t('scripts_menu_title'):<31}|{RST}\n")
    _w(f"{BOLD}{BCYN}  +======================================+{RST}\n\n")
    cmds = [
        ("scripts list",                _t("scripts_help_list")),
        ("scripts info <name>",         _t("scripts_help_info")),
        ("scripts tag <name> <tag>",    _t("scripts_help_tag")),
        ("scripts untag <name> <tag>",  _t("scripts_help_untag")),
        ("scripts set <name> <k> <v>",  _t("scripts_help_set")),
        ("scripts find <tag>",          _t("scripts_help_find")),
        ("scripts find --lang <ext>",   _t("scripts_help_find_lang")),
        ("scripts run <name> [args]",   _t("scripts_help_run")),
        ("scripts cache",               _t("scripts_help_cache")),
        ("scripts cache clear",         _t("scripts_help_cache_clear")),
    ]
    for c, d in cmds:
        _w(f"  {YLW}{_pad(c, 32)}{RST} {DIM}{d}{RST}\n")
    _w("\n")

# -- sub-commands ----------------------------------------------------------------

def _cmd_list(args, _t):
    scripts = _all_scripts()
    if not scripts:
        _w(f"  {DIM}{_t('scripts_list_empty', dir=SCRIPTS_DIR)}{RST}\n"); return
    _w(f"\n{BOLD}  {_t('scripts_col_name'):<26}{_t('scripts_col_tags'):<24}{_t('scripts_col_desc')}{RST}\n")
    _w(f"  {'-'*66}\n")
    for s in scripts:
        meta  = _read_meta(s)
        tags  = ", ".join(meta.get("tags", [])) or DIM + "-" + RST
        desc  = meta.get("description", "") or ""
        ec    = _ext_color(s)
        _w(f"  {ec}{_pad(s, 26)}{RST}{MGT}{_pad(tags, 24)}{RST}{DIM}{desc}{RST}\n")
    _w("\n")

def _cmd_info(args, _t):
    if not args:
        _w(f"  {RED}{_t('scripts_err_info_usage')}{RST}\n"); return
    name = args[0]
    # dopasuj pelna nazwe jesli podano bez rozszerzenia
    if not os.path.splitext(name)[1]:
        for s in _all_scripts():
            if os.path.splitext(s)[0] == name:
                name = s; break
    path = os.path.join(SCRIPTS_DIR, name)
    if not os.path.exists(path):
        _w(f"  {RED}{_t('scripts_not_found', name=name)}{RST}\n"); return
    meta = _read_meta(name) or _default_meta(name)
    size = os.path.getsize(path)
    ec   = _ext_color(name)
    _w(f"\n{BOLD}  {ec}{name}{RST}\n")
    _w(f"  {'-'*40}\n")
    fields = [
        (_t("scripts_field_lang"),    ec + _ext(name).lstrip(".").upper() + RST),
        (_t("scripts_field_desc"),    meta.get("description", "") or DIM + "-" + RST),
        (_t("scripts_field_tags"),    ", ".join(meta.get("tags", [])) or DIM + "-" + RST),
        (_t("scripts_field_author"),  meta.get("author",  "") or DIM + "-" + RST),
        (_t("scripts_field_version"), meta.get("version", "") or DIM + "-" + RST),
        (_t("scripts_field_added"),   meta.get("added",   "") or DIM + "-" + RST),
        (_t("scripts_field_size"),    f"{size:,} B"),
        (_t("scripts_field_path"),    path),
    ]
    for k, v in fields:
        _w(f"  {CYN}{k+':':<12}{RST}{v}\n")
    _w("\n")

def _cmd_tag(args, _t):
    if len(args) < 2:
        _w(f"  {RED}{_t('scripts_err_tag_usage')}{RST}\n"); return
    name, tag = args[0], args[1].lower()
    if not os.path.splitext(name)[1]:
        for s in _all_scripts():
            if os.path.splitext(s)[0] == name: name = s; break
    meta = _read_meta(name) or _default_meta(name)
    if tag in meta.get("tags", []):
        _w(f"  {DIM}{_t('scripts_tag_exists', tag=tag)}{RST}\n"); return
    meta.setdefault("tags", []).append(tag)
    _write_meta(name, meta)
    _w(f"  {GRN}{_t('scripts_tag_added')}{RST} {name} <- {MGT}{tag}{RST}\n")

def _cmd_untag(args, _t):
    if len(args) < 2:
        _w(f"  {RED}{_t('scripts_err_untag_usage')}{RST}\n"); return
    name, tag = args[0], args[1].lower()
    if not os.path.splitext(name)[1]:
        for s in _all_scripts():
            if os.path.splitext(s)[0] == name: name = s; break
    meta = _read_meta(name) or _default_meta(name)
    tags = meta.get("tags", [])
    if tag not in tags:
        _w(f"  {RED}{_t('scripts_tag_missing', tag=tag)}{RST}\n"); return
    tags.remove(tag)
    meta["tags"] = tags
    _write_meta(name, meta)
    _w(f"  {GRN}{_t('scripts_tag_removed')}{RST} {name} ? {MGT}{tag}{RST}\n")

def _cmd_set(args, _t):
    if len(args) < 3:
        _w(f"  {RED}{_t('scripts_err_set_usage')}{RST}\n"); return
    name  = args[0]
    if not os.path.splitext(name)[1]:
        for s in _all_scripts():
            if os.path.splitext(s)[0] == name: name = s; break
    key   = args[1]
    value = " ".join(args[2:])
    allowed = {"description", "author", "version"}
    if key not in allowed:
        _w(f"  {RED}{_t('scripts_set_allowed', fields=', '.join(allowed))}{RST}\n"); return
    meta = _read_meta(name) or _default_meta(name)
    meta[key] = value
    _write_meta(name, meta)
    _w(f"  {GRN}{_t('scripts_set_saved')}{RST} {name} -> {key} = {value}\n")

def _cmd_find(args, _t):
    if not args:
        _w(f"  {RED}{_t('scripts_err_find_usage')}{RST}\n"); return

    scripts = _all_scripts()

    if args[0] == "--lang":
        if len(args) < 2:
            _w(f"  {RED}{_t('scripts_err_find_lang_usage')}{RST}\n"); return
        lang = args[1].lower().lstrip(".")
        found = [s for s in scripts if _ext(s).lstrip(".") == lang]
        label = _t("scripts_find_label_lang", lang=lang)
    else:
        tag   = args[0].lower()
        found = [s for s in scripts if tag in [x.lower() for x in _read_meta(s).get("tags", [])]]
        label = _t("scripts_find_label_tag", tag=f"{MGT}{tag}{RST}")

    if not found:
        _w(f"  {DIM}{_t('scripts_find_none', label=label)}{RST}\n"); return
    _w(f"\n  {BOLD}{_t('scripts_find_header', label=label)}{BOLD}:{RST}\n")
    for s in found:
        meta = _read_meta(s)
        desc = meta.get("description", "")
        ec   = _ext_color(s)
        _w(f"    {ec}{_pad(s, 26)}{RST}{DIM}{desc}{RST}\n")
    _w("\n")

def _cmd_run(args, _t):
    if not args:
        _w(f"  {RED}{_t('scripts_err_run_usage')}{RST}\n"); return
    name = args[0]
    if not os.path.splitext(name)[1]:
        for s in _all_scripts():
            if os.path.splitext(s)[0] == name: name = s; break
    path = os.path.join(SCRIPTS_DIR, name)
    if not os.path.exists(path):
        _w(f"  {RED}{_t('scripts_not_found', name=name)}{RST}\n"); return
    ext      = _ext(name)
    run_args = args[1:]

    # HTML: otwieramy w domyslnej przegladarce (dziala na Windows/Linux/macOS)
    if ext == ".html":
        try:
            url = Path(path).resolve().as_uri()
            webbrowser.open(url)
            _cache_record(name, " ".join(run_args))
            _w(f"  {GRN}{_t('scripts_running')}{RST} {name}\n")
        except Exception as exc:
            _w(f"  {RED}{_t('scripts_run_error', exc=exc)}{RST}\n")
        return

    runner = _runner_for_ext(ext)
    if runner is None:
        # Brak wsparcia na tej platformie albo brak interpretera w PATH.
        _w(f"  {RED}{_t('scripts_unsupported_type', ext=ext)}{RST}\n"); return

    # -- preskan przez Defender (jesli zaladowany) ----------------------------
    try:
        from . import _integration
        if not _integration.defender_scan_file(path):
            _w(f"  {RED}[!!] Defender zablokował uruchomienie skryptu: {name}{RST}\n")
            _integration.notify_event(
                None, f"Defender zablokowal uruchomienie skryptu: {name}",
                kind="err", title="SCRIPTS",
            )
            return
    except Exception:
        pass

    cmd = runner + [path] + run_args
    _w(f"  {GRN}{_t('scripts_running')}{RST} {' '.join(cmd)}\n")
    _cache_record(name, " ".join(run_args))
    try:
        subprocess.Popen(cmd)
    except Exception as exc:
        _w(f"  {RED}{_t('scripts_run_error', exc=exc)}{RST}\n")

def _cmd_cache(args, _t):
    if args and args[0] == "clear":
        _write_cache({})
        _w(f"  {GRN}{_t('scripts_cache_cleared')}{RST}\n"); return
    cache = _read_cache()
    if not cache:
        _w(f"  {DIM}{_t('scripts_cache_empty')}{RST}\n"); return
    _w(f"\n{BOLD}  {_t('scripts_cache_col_script'):<26}{_t('scripts_cache_col_args'):<20}{_t('scripts_cache_col_lang'):<8}{_t('scripts_cache_col_when')}{RST}\n")
    _w(f"  {'-'*62}\n")
    for _, entry in sorted(cache.items(), key=lambda x: x[1].get("ts", 0), reverse=True):
        s    = entry.get("script", "?")
        a    = entry.get("args",   "") or DIM + "-" + RST
        lang = entry.get("lang",   "?")
        age  = _human_age(entry.get("ts", time.time()))
        ec   = _ext_color(s)
        _w(f"  {ec}{_pad(s, 26)}{RST}{_pad(a, 20)}{BLU}{_pad(lang, 8)}{RST}{DIM}{_t('time_ago', age=age)}{RST}\n")
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
        _intg.register("scripts", {
            "list_scripts": _all_scripts,
            "cache_record": _cache_record,
            "scripts_dir":  SCRIPTS_DIR,
        })
    except Exception:
        pass
    def _t(key, **kw):
        return terminal.t(key, **kw)

    def scripts_cmd(args):
        if not args:
            _scripts_menu(_t); return
        sub = args[0]
        if sub in _SUB:
            _SUB[sub](args[1:], _t)
        else:
            _w(f"  {RED}{_t('scripts_unknown_sub', sub=sub)}{RST}\n")
            _scripts_menu(_t)

    terminal.register_command(
        "scripts", scripts_cmd,
        description=_t("cmd_scripts"),
        category=_t("cat_ecosystem"),
    )

def teardown(terminal):
    try:
        from . import _integration as _intg
        _intg.unregister("scripts")
    except Exception:
        pass
    terminal.commands.pop("scripts", None)
