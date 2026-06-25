"""Runner module for TerminalX EcoSystem.

Adapter modulu Script Runner v3.4 do architektury core (setup/teardown).
Udostepnia komendy: run, runner

Funkcje (wzgledem oryginalnego script_runner.py):
  - Wszystkie 30+ komend run/* dzialaja identycznie
  - Poprawki cross-platform:
      * SIGTERM/SIGKILL/SIGSTOP/SIGCONT -> os.kill() z graceful fallback na Windows
      * os.kill() fallback na proc.terminate()/kill() gdy brak signal.SIGTERM (Windows)
      * .html/.hta: webbrowser zamiast mshta gdy mshta niedostepne (Linux/macOS)
      * .reg/.vbs/.hta oznaczone jako Windows-only przy braku interpretera
      * JS Browser-API wrapper (mshta) dziala tylko na Windows
  - Integracja z terminal.t() dla i18n (kluczowe z prefixem runner_)
  - setup(terminal) / teardown(terminal)
"""

import os
import sys
import json
import time
import uuid
import shutil
import subprocess
import threading
import webbrowser
import importlib
from datetime import datetime, timedelta

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, IS_WIN, IS_LIN, IS_MAC, RST, YLW, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad

# --- sygnaly cross-platform --------------------------------------------------

try:
    import signal as _signal
    _SIGTERM = _signal.SIGTERM
    _SIGKILL = getattr(_signal, "SIGKILL", None)  # brak na Windows
    _SIGSTOP = getattr(_signal, "SIGSTOP", None)
    _SIGCONT = getattr(_signal, "SIGCONT", None)
except ImportError:
    _signal  = None
    _SIGTERM = None
    _SIGKILL = None
    _SIGSTOP = None
    _SIGCONT = None


def _kill_proc_tree(pid: int):
    """Wysyla SIGTERM do calego drzewa procesow, potem SIGKILL jesli trzeba.
    Cross-platform: na Windows uzywa proc.terminate()/kill() przez psutil lub Popen."""
    ps = _psutil()
    if ps:
        try:
            parent   = ps.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try: child.terminate()
                except Exception: pass
            parent.terminate()
            gone, alive = ps.wait_procs([parent] + children, timeout=3)
            for p in alive:
                try: p.kill()
                except Exception: pass
            return
        except Exception:
            pass
    # fallback bez psutil
    try:
        if _SIGTERM:
            os.kill(pid, _SIGTERM)
            time.sleep(0.5)
            if _SIGKILL:
                os.kill(pid, _SIGKILL)
        else:
            # Windows bez psutil: TerminateProcess przez subprocess
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(pid)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _suspend_proc(pid: int):
    """SIGSTOP / suspend cross-platform."""
    ps = _psutil()
    if ps:
        try: ps.Process(pid).suspend(); return
        except Exception: pass
    if _SIGSTOP:
        try: os.kill(pid, _SIGSTOP)
        except Exception: pass


def _resume_proc(pid: int):
    """SIGCONT / resume cross-platform."""
    ps = _psutil()
    if ps:
        try: ps.Process(pid).resume(); return
        except Exception: pass
    if _SIGCONT:
        try: os.kill(pid, _SIGCONT)
        except Exception: pass


# --- ANSI --------------------------------------------------------------------

class _C:
    RESET   = "\x1b[0m";  BOLD    = "\x1b[1m";  DIM     = "\x1b[2m"
    BCYAN   = "\x1b[96m"; BYELLOW = "\x1b[93m"; BGREEN  = "\x1b[92m"
    BWHITE  = "\x1b[97m"; RED     = "\x1b[91m"; CYAN    = "\x1b[36m"
    MAGENTA = "\x1b[95m"; YELLOW  = "\x1b[33m"; BLUE    = "\x1b[94m"


# --- zadania w tle ------------------------------------------------------------

_JOBS: dict = {}


class _RunnerStats:
    active_script  = None
    last_result    = None
    error_history  = []
    env_vars       = {}
    active_profile = "default"


# --- system profili env -------------------------------------------------------

_ENV_DIR = os.path.join(os.path.expanduser("~"), ".config", "crossterm", "sr_profiles")


def _env_dir() -> str:
    os.makedirs(_ENV_DIR, exist_ok=True)
    return _ENV_DIR


def _profile_path(name: str) -> str:
    return os.path.join(_env_dir(), f"{name}.json")


def _load_profiles() -> dict:
    profiles = {}
    d = _env_dir()
    for f in os.listdir(d):
        if f.endswith(".json"):
            name = f[:-5]
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    profiles[name] = json.load(fh)
            except Exception:
                profiles[name] = {}
    if "default" not in profiles:
        profiles["default"] = {}
    return profiles


def _save_profile(name: str, data: dict):
    try:
        with open(_profile_path(name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except Exception as e:
        _w(f"  {_C.RED}[!] Blad zapisu profilu: {e}{_C.RESET}\n")


def _active_profile_data() -> dict:
    return _RunnerStats.env_vars


def _sync_active_profile():
    _save_profile(_RunnerStats.active_profile, _RunnerStats.env_vars)


def _switch_profile(name: str) -> bool:
    profiles = _load_profiles()
    if name not in profiles:
        return False
    _RunnerStats.active_profile = name
    _RunnerStats.env_vars = dict(profiles[name])
    return True


def _init_profiles():
    profiles = _load_profiles()
    _RunnerStats.env_vars = dict(profiles.get(_RunnerStats.active_profile, {}))


# --- parsowanie .env ----------------------------------------------------------

def _parse_dotenv(path: str) -> dict:
    import re
    result = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip(); v = v.strip()
                if len(v) >= 2 and v[0] in ('"', "'") and v[-1] == v[0]:
                    v = v[1:-1]
                def _expand(m):
                    var = m.group(1) or m.group(2)
                    return _RunnerStats.env_vars.get(var, os.environ.get(var, ""))
                v = re.sub(r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)', _expand, v)
                if k:
                    result[k] = v
    except FileNotFoundError:
        _w(f"  {_C.RED}[!] Plik nie istnieje: {path}{_C.RESET}\n")
    except Exception as e:
        _w(f"  {_C.RED}[!] Blad parsowania .env: {e}{_C.RESET}\n")
    return result


# --- komendy profili ----------------------------------------------------------

def _do_env_show():
    name = _RunnerStats.active_profile
    data = _RunnerStats.env_vars
    _w(f"\n  {_C.BOLD}{_C.BCYAN}Aktywny profil: {_C.RESET}{_C.BYELLOW}{name}{_C.RESET}\n")
    _w(f"  {_C.DIM}Plik: {_profile_path(name)}{_C.RESET}\n\n")
    if not data:
        _w(f"  {_C.DIM}(brak zmiennych){_C.RESET}\n\n"); return
    _w(f"  {_C.DIM}{'Klucz':<28}Wartosc{_C.RESET}\n")
    _w(f"  {_C.DIM}{'-'*60}{_C.RESET}\n")
    for k, v in sorted(data.items()):
        masked = v if not any(s in k.upper() for s in ("KEY","TOKEN","SECRET","PASS","PWD")) else "*" * min(len(v), 8)
        _w(f"  {_C.BYELLOW}{k:<28}{_C.RESET}{_C.BWHITE}{masked}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Razem: {len(data)} zmiennych.{_C.RESET}\n\n")


def _do_env_load(path: str):
    if not os.path.isfile(path):
        _w(f"\n  {_C.RED}[!] Plik nie istnieje: {path}{_C.RESET}\n\n"); return
    parsed = _parse_dotenv(path)
    if not parsed:
        _w(f"\n  {_C.BYELLOW}[!] Plik pusty lub bez poprawnych wpisow: {path}{_C.RESET}\n\n"); return
    _RunnerStats.env_vars.update(parsed)
    _sync_active_profile()
    _w(f"\n  {_C.BGREEN}[V] Wczytano {len(parsed)} zmiennych z:{_C.RESET} {path}\n")
    _w(f"  {_C.DIM}Profil: {_RunnerStats.active_profile}{_C.RESET}\n\n")


def _do_profile_list():
    profiles = _load_profiles()
    active   = _RunnerStats.active_profile
    _w(f"\n  {_C.BOLD}{_C.BCYAN}Profile srodowiskowe:{_C.RESET}\n\n")
    for name, data in sorted(profiles.items()):
        marker = f"{_C.BGREEN}>{_C.RESET}" if name == active else f"{_C.DIM} {_C.RESET}"
        count  = f"{_C.DIM}({len(data)} zmiennych){_C.RESET}"
        _w(f"  {marker} {_C.BYELLOW}{name:<20}{_C.RESET} {count}\n")
    _w("\n")


def _do_profile_new(name: str):
    if not name.replace("-","").replace("_","").isalnum():
        _w(f"\n  {_C.RED}[!] Niedozwolona nazwa profilu: {name}{_C.RESET}\n\n"); return
    if os.path.exists(_profile_path(name)):
        _w(f"\n  {_C.RED}[!] Profil juz istnieje: {name}{_C.RESET}\n\n"); return
    _save_profile(name, {})
    _w(f"\n  {_C.BGREEN}[V] Profil utworzony:{_C.RESET} {name}\n\n")


def _do_profile_use(name: str):
    if name not in _load_profiles():
        _w(f"\n  {_C.RED}[!] Nie znaleziono profilu: {name}{_C.RESET}\n")
        _w(f"  {_C.DIM}Uzyj 'run profile new {name}' aby go utworzyc.{_C.RESET}\n\n"); return
    _switch_profile(name)
    _w(f"\n  {_C.BGREEN}[V] Przelaczono na profil:{_C.RESET} {_C.BYELLOW}{name}{_C.RESET}")
    _w(f"  {_C.DIM}({len(_RunnerStats.env_vars)} zmiennych){_C.RESET}\n\n")


def _do_profile_del(name: str):
    if name == "default":
        _w(f"\n  {_C.RED}[!] Nie mozna usunac profilu 'default'.{_C.RESET}\n\n"); return
    path = _profile_path(name)
    if not os.path.exists(path):
        _w(f"\n  {_C.RED}[!] Profil nie istnieje: {name}{_C.RESET}\n\n"); return
    if _RunnerStats.active_profile == name:
        _switch_profile("default")
        _w(f"  {_C.DIM}Aktywny profil przelaczony na: default{_C.RESET}\n")
    os.remove(path)
    _w(f"\n  {_C.BGREEN}[V] Profil usuniety:{_C.RESET} {name}\n\n")


def _do_profile_show(name: str):
    profiles = _load_profiles()
    if name not in profiles:
        _w(f"\n  {_C.RED}[!] Profil nie istnieje: {name}{_C.RESET}\n\n"); return
    data   = profiles[name]
    active = _RunnerStats.active_profile
    marker = f" {_C.BGREEN}[aktywny]{_C.RESET}" if name == active else ""
    _w(f"\n  {_C.BOLD}{_C.BCYAN}Profil: {_C.RESET}{_C.BYELLOW}{name}{_C.RESET}{marker}\n\n")
    if not data:
        _w(f"  {_C.DIM}(brak zmiennych){_C.RESET}\n\n"); return
    _w(f"  {_C.DIM}{'Klucz':<28}Wartosc{_C.RESET}\n")
    _w(f"  {_C.DIM}{'-'*60}{_C.RESET}\n")
    for k, v in sorted(data.items()):
        masked = v if not any(s in k.upper() for s in ("KEY","TOKEN","SECRET","PASS","PWD")) else "*" * min(len(v), 8)
        _w(f"  {_C.BYELLOW}{k:<28}{_C.RESET}{_C.BWHITE}{masked}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Razem: {len(data)} zmiennych.{_C.RESET}\n\n")


def _do_profile_export(name: str, dest: str = None):
    profiles = _load_profiles()
    if name not in profiles:
        _w(f"\n  {_C.RED}[!] Profil nie istnieje: {name}{_C.RESET}\n\n"); return
    data = profiles[name]
    if dest is None:
        dest = f"{name}.env"
    lines = [f"# Profil: {name}  |  Wygenerowano: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"]
    for k, v in sorted(data.items()):
        if " " in v or "\t" in v:
            v = f'"{v}"'
        lines.append(f"{k}={v}\n")
    try:
        with open(dest, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        _w(f"\n  {_C.BGREEN}[V] Wyeksportowano {len(data)} zmiennych do:{_C.RESET} {dest}\n\n")
    except Exception as e:
        _w(f"\n  {_C.RED}[!] Blad eksportu: {e}{_C.RESET}\n\n")


def _do_unset(key: str):
    if key in _RunnerStats.env_vars:
        del _RunnerStats.env_vars[key]
        _sync_active_profile()
        _w(f"\n  {_C.BGREEN}[V] Usunieto:{_C.RESET} {key}\n\n")
    else:
        _w(f"\n  {_C.DIM}Zmienna nie istnieje: {key}{_C.RESET}\n\n")


# --- psutil (lazy) ------------------------------------------------------------

def _psutil():
    try:
        import psutil
        return psutil
    except ImportError:
        return None


def _nice_value(priority: str) -> int:
    return {"low": 10, "norm": 0, "high": -10}.get(priority, 0)


def _set_proc_priority(proc, priority: str):
    ps = _psutil()
    if not ps:
        return
    try:
        p = ps.Process(proc.pid)
        if IS_WIN:
            classes = {
                "high": getattr(ps, "HIGH_PRIORITY_CLASS",  None),
                "low":  getattr(ps, "IDLE_PRIORITY_CLASS",  None),
                "norm": getattr(ps, "NORMAL_PRIORITY_CLASS", None),
            }
            cls = classes.get(priority)
            if cls:
                p.nice(cls); return
        p.nice(_nice_value(priority))
    except Exception:
        pass


def _set_proc_priority_pid(pid, priority, ps):
    try:
        p = ps.Process(pid)
        if IS_WIN:
            classes = {
                "high": getattr(ps, "HIGH_PRIORITY_CLASS",  None),
                "low":  getattr(ps, "IDLE_PRIORITY_CLASS",  None),
                "norm": getattr(ps, "NORMAL_PRIORITY_CLASS", None),
            }
            cls = classes.get(priority)
            if cls:
                p.nice(cls); return
        p.nice(_nice_value(priority))
    except Exception:
        pass


def _get_proc_stats(pid: int) -> dict:
    ps = _psutil()
    if not ps:
        return {}
    try:
        p   = ps.Process(pid)
        cpu = p.cpu_percent(interval=0.1)
        mem = p.memory_info().rss / (1024 * 1024)
        return {"cpu": cpu, "mem_mb": mem, "status": p.status()}
    except Exception:
        return {}


def _enforce_limits(job_id: str):
    ps = _psutil()
    if not ps:
        return
    while job_id in _JOBS:
        job = _JOBS.get(job_id)
        if not job:
            break
        pid = job.get("pid")
        if not pid:
            time.sleep(1); continue
        cpu_limit = job.get("cpu_limit")
        mem_limit = job.get("mem_limit_mb")
        try:
            p = ps.Process(pid)
            if mem_limit:
                mem_mb = p.memory_info().rss / (1024 * 1024)
                if mem_mb > mem_limit:
                    _w(f"\n  {_C.RED}[JOB {job_id}] Przekroczono limit RAM ({mem_mb:.0f}MB > {mem_limit}MB) - kill.{_C.RESET}\n")
                    _kill_proc_tree(pid)
                    if job_id in _JOBS:
                        _JOBS[job_id]["status"] = "killed_mem"
                    break
            if cpu_limit:
                cpu = p.cpu_percent(interval=0.5)
                job.setdefault("_cpu_over", 0)
                if cpu > cpu_limit:
                    job["_cpu_over"] += 1
                    if job["_cpu_over"] >= 3:
                        _w(f"\n  {_C.BYELLOW}[JOB {job_id}] CPU {cpu:.0f}% > limit {cpu_limit:.0f}% - throttling...{_C.RESET}\n")
                        try:
                            p.suspend(); time.sleep(0.5); p.resume()
                        except Exception:
                            pass
                        job["_cpu_over"] = 0
                else:
                    job["_cpu_over"] = 0
        except Exception:
            break
        time.sleep(1)


# --- konfiguracja (PLUGINS) ---------------------------------------------------

DEFAULT_TIMEOUT_SEC = 600
DEFAULT_LOG_DIR     = "logs"

PLUGINS = {
    # -- skrypty interpretowane ------------------------------------------------
    "python":      {"extensions": [".py", ".pyw"],          "interpreters": ["python", "python3", "py"],           "run_args": []},
    "powershell":  {"extensions": [".ps1"],                 "interpreters": ["pwsh", "powershell"],                "run_args": ["-ExecutionPolicy", "Bypass", "-File"]},
    "batch":       {"extensions": [".bat", ".cmd"],         "interpreters": ["cmd"],                               "run_args": ["/c"],   "_win_only": True},
    "bash":        {"extensions": [".sh", ".bash"],         "interpreters": ["bash", "sh"],                        "run_args": []},
    "zsh":         {"extensions": [".zsh"],                 "interpreters": ["zsh"],                               "run_args": []},
    "fish":        {"extensions": [".fish"],                "interpreters": ["fish"],                              "run_args": []},
    "reg":         {"extensions": [".reg"],                 "interpreters": ["regedit", "reg"],                    "run_args": ["/s"],   "_win_only": True},
    "vbs":         {"extensions": [".vbs"],                 "interpreters": ["wscript", "cscript"],                "run_args": [],       "_win_only": True},
    "html":        {"extensions": [".html", ".htm"],        "interpreters": ["_webbrowser"],                       "run_args": [],       "_webbrowser": True},
    "hta":         {"extensions": [".hta"],                 "interpreters": ["mshta"],                             "run_args": [],       "_win_only": True},
    "javascript":  {"extensions": [".js", ".mjs", ".cjs"],  "interpreters": ["node"],                              "run_args": []},
    "typescript":  {"extensions": [".ts", ".mts"],          "interpreters": ["ts-node", "npx ts-node", "deno"],    "run_args": []},
    "coffeescript":{"extensions": [".coffee"],              "interpreters": ["coffee", "coffeescript"],             "run_args": []},
    "ruby":        {"extensions": [".rb"],                  "interpreters": ["ruby"],                              "run_args": []},
    "perl":        {"extensions": [".pl", ".pm"],           "interpreters": ["perl"],                              "run_args": []},
    "lua":         {"extensions": [".lua"],                 "interpreters": ["lua", "lua5.4", "lua5.3"],           "run_args": []},
    "php":         {"extensions": [".php", ".phtml"],       "interpreters": ["php"],                               "run_args": []},
    "tcl":         {"extensions": [".tcl", ".tck"],         "interpreters": ["tclsh", "wish"],                     "run_args": []},
    "awk":         {"extensions": [".awk"],                 "interpreters": ["awk", "gawk", "mawk"],               "run_args": ["-f"]},
    "r":           {"extensions": [".r", ".R"],             "interpreters": ["Rscript", "r"],                      "run_args": ["--vanilla"]},
    "julia":       {"extensions": [".jl"],                  "interpreters": ["julia"],                             "run_args": []},
    "octave":      {"extensions": [".m"],                   "interpreters": ["octave", "octave-cli"],              "run_args": ["--no-gui"]},
    "elixir":      {"extensions": [".exs"],                 "interpreters": ["elixir"],                            "run_args": []},
    "clojure":     {"extensions": [".clj", ".cljs"],        "interpreters": ["clojure", "clj"],                    "run_args": []},
    # -- kompilowane -----------------------------------------------------------
    "java":        {"extensions": [".java"],                "interpreters": ["java"],                              "run_args": [], "_compile": True},
    "kotlin":      {"extensions": [".kt", ".kts"],          "interpreters": ["kotlinc", "kotlin"],                 "run_args": [], "_compile": True},
    "groovy":      {"extensions": [".groovy", ".gvy"],      "interpreters": ["groovy"],                            "run_args": []},
    "scala":       {"extensions": [".scala", ".sc"],        "interpreters": ["scala"],                             "run_args": []},
    "go":          {"extensions": [".go"],                  "interpreters": ["go"],                                "run_args": ["run"]},
    "rust":        {"extensions": [".rs"],                  "interpreters": ["rustc"],                             "run_args": [], "_compile": True},
    "nim":         {"extensions": [".nim"],                 "interpreters": ["nim"],                               "run_args": [], "_compile": True},
    "zig":         {"extensions": [".zig"],                 "interpreters": ["zig"],                               "run_args": ["run"]},
    "c":           {"extensions": [".c"],                   "interpreters": ["gcc", "clang", "cl"],                "run_args": [], "_compile": True},
    "cpp":         {"extensions": [".cpp", ".cxx", ".cc"], "interpreters": ["g++", "clang++"],                    "run_args": [], "_compile": True},
    "csharp":      {"extensions": [".cs"],                  "interpreters": ["dotnet-script", "csc", "mcs"],       "run_args": []},
    "swift":       {"extensions": [".swift"],               "interpreters": ["swift"],                             "run_args": []},
    # -- artefakty -------------------------------------------------------------
    "jar":         {"extensions": [".jar"],                 "interpreters": ["java"],                              "run_args": ["-jar"]},
    "pyz":         {"extensions": [".pyz"],                 "interpreters": ["python", "python3"],                 "run_args": []},
}

_EXT_MAP = {}
for _pname, _pdata in PLUGINS.items():
    for _ext in _pdata["extensions"]:
        _EXT_MAP[_ext.lower()] = _pname

_INTERP_CACHE: dict = {}


def _find_interpreter(plugin_name: str):
    """Zwraca sciezke do interpretera lub None.
    Dla _webbrowser (html) zwraca sentinel '_webbrowser'.
    """
    if plugin_name in _INTERP_CACHE:
        return _INTERP_CACHE[plugin_name]
    pdata = PLUGINS.get(plugin_name, {})
    if pdata.get("_webbrowser"):
        _INTERP_CACHE[plugin_name] = "_webbrowser"
        return "_webbrowser"
    for c in pdata.get("interpreters", []):
        path = shutil.which(c)
        if path:
            _INTERP_CACHE[plugin_name] = path
            return path
    return None


# --- menu ---------------------------------------------------------------------

def _cml_menu():
    _w(f"\n{_C.BOLD}{_C.BCYAN}  +----------------------------------+{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  |   Module: Script Runner v3.4     |{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  +----------------------------------+{_C.RESET}\n\n")
    cmds = [
        ("run <plik>",                    "Uruchom skrypt (auto-detekcja)"),
        ("run bg <plik> [opcje]",         "Uruchom w tle  [--prio low|norm|high] [--cpu N] [--mem M]"),
        ("run jobs",                      "Lista jobow (PID, CPU%, RAM, priorytet)"),
        ("run jobs top",                  "Live monitor zasobow jobow"),
        ("run kill <id|all>",             "Zatrzymaj job (SIGTERM -> SIGKILL)"),
        ("run pause <id>",                "Wstrzymaj job (SIGSTOP)"),
        ("run resume <id>",               "Wznow job (SIGCONT)"),
        ("run prio <id> <low|norm|high>", "Zmien priorytet joba"),
        ("run limit <id> --cpu N --mem M","Ustaw limity zasobow joba"),
        ("run env",                       "Pokaz aktywny profil i zmienne"),
        ("run env load <plik.env>",       "Wczytaj plik .env do aktywnego profilu"),
        ("run profile list",              "Lista zapisanych profili"),
        ("run profile new/use/del <n>",   "Zarzadzaj profilami"),
        ("run profile export <n> [plik]", "Eksportuj profil do .env"),
        ("run set KEY=VAL",               "Dodaj/nadpisz zmienna w aktywnym profilu"),
        ("run unset KEY",                 "Usun zmienna z aktywnego profilu"),
        ("run watch <plik>",              "Uruchamiaj ponownie przy zmianach"),
        ("run list",                      "Lista obslugiwanych typow plikow"),
        ("run log [n]",                   "Pokaz n ostatnich logow"),
        ("run log tail",                  "Sledzenie nowych logow na zywo"),
        ("run schedule <HH:MM> <plik>",   "Zaplanuj uruchomienie"),
        ("run retry <n> <plik>",          "Ponawiaj skrypt n razy w razie bledu"),
        ("runner",                        "Alias -> to menu"),
    ]
    for c, d in cmds:
        _w(f"  {_C.BYELLOW}{c:<35}{_C.RESET} {_C.DIM}{d}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Komendy globalne: {_C.RESET}{_C.BYELLOW}run{_C.RESET}  {_C.BYELLOW}runner{_C.RESET}\n\n")


# --- run list -----------------------------------------------------------------

def _do_list():
    _w(f"\n  {_C.BOLD}{_C.BCYAN}Obslugiwane typy skryptow:{_C.RESET}\n\n")
    _w(f"  {_C.DIM}{'Typ':<16}{'Rozszerzenia':<28}{'Interpretery'}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'-'*68}{_C.RESET}\n")
    _categories = [
        ("Skrypty interpretowane",  ["python","powershell","batch","bash","zsh","fish","reg","vbs","html","hta",
                                      "javascript","typescript","coffeescript","ruby","perl","lua","php","tcl",
                                      "awk","r","julia","octave","elixir","clojure"]),
        ("Kompilowane",             ["java","kotlin","groovy","scala","go","rust","nim","zig","c","cpp","csharp","swift"]),
        ("Artefakty uruchamiane",   ["jar","pyz"]),
    ]
    shown = set()
    for cat_name, names in _categories:
        _w(f"\n  {_C.BOLD}{_C.BLUE}{cat_name}:{_C.RESET}\n")
        for pname in names:
            if pname not in PLUGINS:
                continue
            shown.add(pname)
            pdata  = PLUGINS[pname]
            exts   = "  ".join(pdata["extensions"])
            interps = ", ".join(pdata["interpreters"][:3])
            interp  = _find_interpreter(pname)
            if pdata.get("_webbrowser"):
                avail = f"{_C.BGREEN}[V]{_C.RESET}"
            elif pdata.get("_win_only") and not IS_WIN:
                avail = f"{_C.YELLOW}[W]{_C.RESET}"  # Windows-only
            else:
                avail = f"{_C.BGREEN}[V]{_C.RESET}" if interp else f"{_C.RED}[X]{_C.RESET}"
            compile_tag = f" {_C.MAGENTA}(kompilacja){_C.RESET}" if pdata.get("_compile") else ""
            win_tag     = f" {_C.YELLOW}(Win){_C.RESET}" if pdata.get("_win_only") else ""
            _w(f"  {avail} {_C.BYELLOW}{pname:<15}{_C.RESET}"
               f"{_C.BWHITE}{exts:<28}{_C.RESET}"
               f"{_C.DIM}{interps}{_C.RESET}{compile_tag}{win_tag}\n")
    rest = [p for p in PLUGINS if p not in shown]
    if rest:
        _w(f"\n  {_C.BOLD}{_C.BLUE}Inne:{_C.RESET}\n")
        for pname in rest:
            pdata   = PLUGINS[pname]
            exts    = "  ".join(pdata["extensions"])
            interps = ", ".join(pdata["interpreters"][:3])
            interp  = _find_interpreter(pname)
            avail   = f"{_C.BGREEN}[V]{_C.RESET}" if interp else f"{_C.RED}[X]{_C.RESET}"
            _w(f"  {avail} {_C.BYELLOW}{pname:<15}{_C.RESET}"
               f"{_C.BWHITE}{exts:<28}{_C.RESET}{_C.DIM}{interps}{_C.RESET}\n")
    _w("\n")


# --- tlo i monitoring ---------------------------------------------------------

def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    if s < 60:   return f"{s}s"
    if s < 3600: return f"{s//60}m{s%60:02d}s"
    return f"{s//3600}h{(s%3600)//60:02d}m"


def _fmt_mem(mb: float) -> str:
    if mb < 1024: return f"{mb:.0f}MB"
    return f"{mb/1024:.1f}GB"


def _do_bg_run(file_path, args=None, priority="norm", cpu_limit=None, mem_limit_mb=None):
    job_id = str(uuid.uuid4())[:8]

    def _thread_target():
        res = _do_run(file_path, args=args, log_dir=DEFAULT_LOG_DIR, _job_id=job_id)
        if res and res.get("exitcode") != 0:
            if job_id in _JOBS:
                _JOBS[job_id]["status"] = "failed"
            _w(f"\n  {_C.RED}[JOB {job_id}] Skrypt zakonczony bledem ({res.get('exitcode')}).{_C.RESET}\n")
        else:
            if job_id in _JOBS:
                _JOBS[job_id]["status"] = "done"
            _w(f"\n  {_C.BGREEN}[JOB {job_id}] Skrypt zakonczony pomyslnie.{_C.RESET}\n")

    t = threading.Thread(target=_thread_target, daemon=True)
    _JOBS[job_id] = {
        "file":         os.path.basename(file_path),
        "path":         os.path.abspath(file_path),
        "start":        time.time(),
        "thread":       t,
        "pid":          None,
        "proc":         None,
        "priority":     priority,
        "cpu_limit":    cpu_limit,
        "mem_limit_mb": mem_limit_mb,
        "status":       "running",
    }
    t.start()
    if cpu_limit or mem_limit_mb:
        threading.Thread(target=_enforce_limits, args=(job_id,), daemon=True).start()

    _w(f"\n  {_C.BGREEN}[V] Uruchomiono w tle.{_C.RESET} Job ID: {_C.BOLD}{job_id}{_C.RESET}")
    if priority != "norm":
        _w(f"  priorytet: {_C.BYELLOW}{priority}{_C.RESET}")
    if cpu_limit:
        _w(f"  CPU limit: {_C.BYELLOW}{cpu_limit}%{_C.RESET}")
    if mem_limit_mb:
        _w(f"  RAM limit: {_C.BYELLOW}{mem_limit_mb}MB{_C.RESET}")
    _w("\n\n")


def _do_jobs_list():
    if not _JOBS:
        _w(f"\n  {_C.DIM}Brak aktywnych zadan w tle.{_C.RESET}\n\n"); return
    ps = _psutil()
    _w(f"\n  {_C.BOLD}{_C.BCYAN}Aktywne zadania w tle:{_C.RESET}\n\n")
    hdr = f"  {'ID':<10}{'Plik':<22}{'Czas':>7}  {'PID':>7}  {'CPU%':>6}  {'RAM':>8}  {'Prio':<6}  Limity"
    _w(f"{_C.DIM}{hdr}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'-'*80}{_C.RESET}\n")
    for jid, info in list(_JOBS.items()):
        elapsed = _fmt_elapsed(time.time() - info["start"])
        pid     = info.get("pid")
        prio    = info.get("priority", "norm")
        cpu_lim = info.get("cpu_limit")
        mem_lim = info.get("mem_limit_mb")
        status  = info.get("status", "?")
        cpu_s = mem_s = pid_s = "-"
        if pid and ps:
            stats = _get_proc_stats(pid)
            if stats:
                cpu_s = f"{stats['cpu']:5.1f}%"
                mem_s = _fmt_mem(stats['mem_mb'])
                pid_s = str(pid)
        prio_color = {"high": _C.BGREEN, "low": _C.DIM, "norm": _C.BWHITE}.get(prio, _C.BWHITE)
        limits = []
        if cpu_lim: limits.append(f"CPU?{cpu_lim}%")
        if mem_lim: limits.append(f"RAM?{mem_lim}MB")
        limits_s = "  ".join(limits) if limits else ""
        status_icon = {
            "running":    f"{_C.BGREEN}*{_C.RESET}",
            "paused":     f"{_C.BYELLOW}||{_C.RESET}",
            "killed_mem": f"{_C.RED}[X]{_C.RESET}",
            "done":       f"{_C.DIM}[V]{_C.RESET}",
        }.get(status, f"{_C.DIM}?{_C.RESET}")
        _w(f"  {status_icon} {_C.BYELLOW}{jid:<9}{_C.RESET}"
           f"{info['file']:<22}"
           f"{_C.DIM}{elapsed:>7}{_C.RESET}  "
           f"{_C.DIM}{pid_s:>7}{_C.RESET}  "
           f"{_C.BCYAN}{cpu_s:>6}{_C.RESET}  "
           f"{_C.MAGENTA}{mem_s:>8}{_C.RESET}  "
           f"{prio_color}{prio:<6}{_C.RESET}  "
           f"{_C.DIM}{limits_s}{_C.RESET}\n")
    _w("\n")


def _do_jobs_top():
    ps = _psutil()
    if not ps:
        _w(f"\n  {_C.RED}[!] psutil niedostepny - zainstaluj: pip install psutil{_C.RESET}\n\n"); return
    _w(f"\n  {_C.BOLD}{_C.BCYAN}[JOBS TOP]{_C.RESET}  {_C.DIM}Ctrl+C = wyjscie{_C.RESET}\n")
    try:
        while True:
            if not _JOBS:
                _w(f"  {_C.DIM}Brak jobow.{_C.RESET}\n")
                time.sleep(1); continue
            rows  = len(_JOBS)
            lines = []
            for jid, info in list(_JOBS.items()):
                pid     = info.get("pid")
                elapsed = _fmt_elapsed(time.time() - info["start"])
                prio    = info.get("priority", "norm")
                cpu_s = mem_s = "    -"
                if pid:
                    stats = _get_proc_stats(pid)
                    if stats:
                        cpu_s = f"{stats['cpu']:5.1f}%"
                        mem_s = _fmt_mem(stats['mem_mb'])
                lines.append(
                    f"  {_C.BYELLOW}{jid:<10}{_C.RESET}"
                    f"{info['file']:<22}"
                    f"{_C.DIM}{elapsed:>7}{_C.RESET}  "
                    f"{_C.BCYAN}{cpu_s:>6}{_C.RESET}  "
                    f"{_C.MAGENTA}{mem_s:>8}{_C.RESET}  "
                    f"{_C.DIM}{prio}{_C.RESET}"
                )
            header = f"  {_C.DIM}{'ID':<10}{'Plik':<22}{'Czas':>7}  {'CPU%':>6}  {'RAM':>8}  Prio{_C.RESET}"
            _w(f"\x1b[{rows+2}A\x1b[0J")
            _w(header + "\n")
            for l in lines:
                _w(l + "\n")
            _w(f"  {_C.DIM}{time.strftime('%H:%M:%S')}{_C.RESET}\n")
            time.sleep(1)
    except KeyboardInterrupt:
        _w(f"\n  {_C.BYELLOW}Jobs top zatrzymany.{_C.RESET}\n\n")


def _do_job_kill(job_id_or_all):
    if job_id_or_all == "all":
        if not _JOBS:
            _w(f"\n  {_C.DIM}Brak jobow.{_C.RESET}\n\n"); return
        for jid in list(_JOBS.keys()):
            _do_job_kill(jid)
        return
    job_id = job_id_or_all
    if job_id not in _JOBS:
        _w(f"\n  {_C.RED}[!] Nie znaleziono zadania: {job_id}{_C.RESET}\n\n"); return
    info = _JOBS[job_id]
    pid  = info.get("pid")
    if pid:
        _w(f"\n  {_C.BYELLOW}[~] Kill job {job_id} (PID {pid})...{_C.RESET}\n")
        _kill_proc_tree(pid)
        _w(f"  {_C.BGREEN}[V] Proces zatrzymany.{_C.RESET}\n\n")
    else:
        _w(f"\n  {_C.BYELLOW}[~] Job {job_id} nie ma jeszcze PID - usuwam z kolejki.{_C.RESET}\n\n")
    _JOBS.pop(job_id, None)


def _do_job_pause(job_id):
    info = _JOBS.get(job_id)
    if not info:
        _w(f"\n  {_C.RED}[!] Nie znaleziono joba: {job_id}{_C.RESET}\n\n"); return
    pid = info.get("pid")
    if not pid:
        _w(f"\n  {_C.RED}[!] Job {job_id} nie ma PID.{_C.RESET}\n\n"); return
    _suspend_proc(pid)
    _JOBS[job_id]["status"] = "paused"
    _w(f"\n  {_C.BYELLOW}[||] Job {job_id} wstrzymany (PID {pid}).{_C.RESET}\n\n")


def _do_job_resume(job_id):
    info = _JOBS.get(job_id)
    if not info:
        _w(f"\n  {_C.RED}[!] Nie znaleziono joba: {job_id}{_C.RESET}\n\n"); return
    pid = info.get("pid")
    if not pid:
        _w(f"\n  {_C.RED}[!] Job {job_id} nie ma PID.{_C.RESET}\n\n"); return
    _resume_proc(pid)
    _JOBS[job_id]["status"] = "running"
    _w(f"\n  {_C.BGREEN}[>] Job {job_id} wznowiony (PID {pid}).{_C.RESET}\n\n")


def _do_job_prio(job_id, priority):
    if priority not in ("low", "norm", "high"):
        _w(f"\n  {_C.RED}[!] Priorytet musi byc: low | norm | high{_C.RESET}\n\n"); return
    info = _JOBS.get(job_id)
    if not info:
        _w(f"\n  {_C.RED}[!] Nie znaleziono joba: {job_id}{_C.RESET}\n\n"); return
    pid = info.get("pid")
    if pid:
        ps = _psutil()
        if ps:
            try: _set_proc_priority_pid(pid, priority, ps)
            except Exception as e:
                _w(f"\n  {_C.RED}[!] Blad ustawiania priorytetu: {e}{_C.RESET}\n\n"); return
    _JOBS[job_id]["priority"] = priority
    _w(f"\n  {_C.BGREEN}[V] Priorytet joba {job_id} ustawiony na: {priority}{_C.RESET}\n\n")


def _do_job_limit(job_id, cpu_limit=None, mem_limit_mb=None):
    info = _JOBS.get(job_id)
    if not info:
        _w(f"\n  {_C.RED}[!] Nie znaleziono joba: {job_id}{_C.RESET}\n\n"); return
    changed = []
    if cpu_limit is not None:
        _JOBS[job_id]["cpu_limit"] = cpu_limit; changed.append(f"CPU?{cpu_limit}%")
    if mem_limit_mb is not None:
        _JOBS[job_id]["mem_limit_mb"] = mem_limit_mb; changed.append(f"RAM?{mem_limit_mb}MB")
    if not changed:
        _w(f"\n  {_C.DIM}Brak zmian. Uzyj --cpu N i/lub --mem M.{_C.RESET}\n\n"); return
    threading.Thread(target=_enforce_limits, args=(job_id,), daemon=True).start()
    _w(f"\n  {_C.BGREEN}[V] Limity joba {job_id} zaktualizowane:{_C.RESET} {', '.join(changed)}\n\n")


# --- watch mode ---------------------------------------------------------------

def _do_watch(file_path, args=None):
    if not os.path.isfile(file_path):
        _w(f"\n  {_C.RED}[!] Plik nie istnieje: {file_path}{_C.RESET}\n\n"); return
    _w(f"\n  {_C.BOLD}{_C.BCYAN}[WATCH] Tryb aktywny dla: {os.path.basename(file_path)}{_C.RESET}\n")
    _w(f"  {_C.DIM}Nacisnij Ctrl+C aby zatrzymac.{_C.RESET}\n\n")
    last_mtime = os.path.getmtime(file_path)
    _do_run(file_path, args=args)
    try:
        while True:
            time.sleep(1)
            try:
                current_mtime = os.path.getmtime(file_path)
                if current_mtime > last_mtime:
                    _w(f"\n  {_C.MAGENTA}*** Wykryto zmiane! Ponowne uruchamianie...{_C.RESET}\n")
                    _do_run(file_path, args=args)
                    last_mtime = current_mtime
            except FileNotFoundError:
                _w(f"\n  {_C.RED}[!] Plik zniknal!{_C.RESET}\n"); break
    except KeyboardInterrupt:
        _w(f"\n  {_C.BYELLOW}Watch mode zatrzymany.{_C.RESET}\n\n")


# --- uruchamianie skryptu -----------------------------------------------------

def _compile_and_run(file_path, plugin_name, interpreter, args, env, timeout, record):
    import tempfile
    ext     = os.path.splitext(file_path)[1].lower()
    base    = os.path.splitext(os.path.basename(file_path))[0]
    tmp_dir = tempfile.mkdtemp(prefix="sr_build_")
    out_bin = os.path.join(tmp_dir, base)
    start   = time.time()
    try:
        if plugin_name == "java":
            compile_cmd = ["javac", "-d", tmp_dir, file_path]
        elif plugin_name == "kotlin":
            out_jar = out_bin + ".jar"
            compile_cmd = [interpreter, file_path, "-include-runtime", "-d", out_jar]
        elif plugin_name in ("c", "cpp"):
            compile_cmd = [interpreter, file_path, "-o", out_bin]
        elif plugin_name == "rust":
            compile_cmd = [interpreter, file_path, "-o", out_bin]
        elif plugin_name == "nim":
            compile_cmd = [interpreter, "compile", "--outdir:" + tmp_dir, file_path]
        else:
            compile_cmd = [interpreter, file_path, "-o", out_bin]

        _w(f"  {_C.DIM}Kompilacja...{_C.RESET}\n")
        cproc = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=120, env=env)
        if cproc.returncode != 0:
            _w(f"  {_C.RED}[!] Blad kompilacji:{_C.RESET}\n")
            for line in cproc.stderr.strip().splitlines():
                _w(f"  {_C.DIM}{line}{_C.RESET}\n")
            record.update({"status": "compile_error", "exitcode": cproc.returncode,
                           "stderr": cproc.stderr, "time_sec": time.time() - start})
            return record

        if plugin_name == "java":
            run_cmd = ["java", "-cp", tmp_dir, base]
        elif plugin_name == "kotlin":
            run_cmd = ["java", "-jar", out_bin + ".jar"]
        else:
            # Windows: skompilowany plik bez .exe nie zadziala -> dodaj
            if IS_WIN and not out_bin.endswith(".exe"):
                run_cmd = [out_bin + ".exe"]
            else:
                run_cmd = [out_bin]

        if args:
            run_cmd += args

        _w(f"  {_C.DIM}Uruchamianie...{_C.RESET}\n")
        proc = subprocess.Popen(run_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=env)
        try:
            out, err = proc.communicate(timeout=timeout)
            exitcode = proc.returncode; status = "ok"
        except subprocess.TimeoutExpired:
            proc.kill(); out, err = proc.communicate()
            exitcode = -1; status = "timeout"

        record.update({"interpreter": interpreter, "cmd": run_cmd,
                       "stdout": out, "stderr": err, "exitcode": exitcode,
                       "status": status, "time_sec": time.time() - start})
    except Exception as e:
        record.update({"status": "launch_error", "stderr": str(e),
                       "time_sec": time.time() - start})
        _w(f"  {_C.RED}[!] {e}{_C.RESET}\n\n")
    finally:
        try: shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception: pass
    return record


def _do_run(file_path, args=None, timeout=DEFAULT_TIMEOUT_SEC,
            log_dir=DEFAULT_LOG_DIR, _job_id=None):
    if not os.path.isfile(file_path):
        _w(f"\n  {_C.RED}[!] Plik nie istnieje: {file_path}{_C.RESET}\n\n")
        return None

    ext         = os.path.splitext(file_path)[1].lower()
    plugin_name = _EXT_MAP.get(ext)
    if not plugin_name:
        _w(f"\n  {_C.RED}[!] Nieobslugiwany typ pliku: {ext}{_C.RESET}\n")
        _w(f"  {_C.DIM}Sprawdz 'run list' aby zobaczyc obslugiwane typy.{_C.RESET}\n\n")
        return None

    record = {
        "id":          str(uuid.uuid4()),
        "file":        os.path.abspath(file_path),
        "interpreter": "N/A",
        "cmd":         [],
        "stdout":      "",
        "stderr":      "",
        "exitcode":    -1,
        "status":      "error",
        "time_sec":    0.0,
        "timestamp":   time.strftime("%Y-%m-%d %H:%M:%S"),
        "plugin":      plugin_name,
    }

    pdata = PLUGINS.get(plugin_name, {})

    # Windows-only check
    if pdata.get("_win_only") and not IS_WIN:
        _w(f"\n  {_C.RED}[!] Typ '{plugin_name}' jest dostepny tylko na Windows.{_C.RESET}\n\n")
        record["status"] = "platform_unsupported"
        return _finalize_run(record, timeout, log_dir)

    # HTML: webbrowser cross-platform
    if pdata.get("_webbrowser"):
        from pathlib import Path as _Path
        try:
            url = _Path(os.path.abspath(file_path)).as_uri()
            webbrowser.open(url)
            _w(f"\n  {_C.BGREEN}[V] Otwarty w przegladarce:{_C.RESET} {os.path.basename(file_path)}\n\n")
            record.update({"status": "ok", "exitcode": 0, "time_sec": 0.0,
                           "interpreter": "webbrowser"})
        except Exception as e:
            _w(f"\n  {_C.RED}[!] Blad otwarcia przegladarki: {e}{_C.RESET}\n\n")
            record.update({"status": "launch_error", "stderr": str(e)})
        return _finalize_run(record, timeout, log_dir)

    # JS browser-API wrapper (tylko Windows z mshta)
    if ext == ".js":
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if any(x in content for x in ["alert(", "prompt(", "confirm(", "document.", "window."]):
                _w(f"\n  {_C.BYELLOW}[!] Wykryto wywolania Browser API (alert/prompt/document).{_C.RESET}\n")
                mshta = shutil.which("mshta") if IS_WIN else None
                if mshta:
                    _w(f"  {_C.DIM}Uruchamianie przez MSHTA (Windows)...{_C.RESET}\n")
                    hta_content = (
                        f'<script language="JScript">window.resizeTo(0,0);window.moveTo(-100,-100);</script>'
                        f'<script language="JScript" src="{os.path.abspath(file_path)}"></script>'
                        f'<script language="JScript">window.close();</script>'
                    )
                    import tempfile as _tmp
                    tmp_hta = _tmp.NamedTemporaryFile(suffix=".hta", delete=False, mode="w",
                                                      encoding="utf-8")
                    tmp_hta.write(hta_content); tmp_hta.close()
                    start = time.time()
                    proc = subprocess.Popen([mshta, os.path.abspath(tmp_hta.name)])
                    proc.wait()
                    try: os.remove(tmp_hta.name)
                    except OSError: pass
                    record.update({"interpreter": mshta, "status": "ok",
                                   "exitcode": 0, "time_sec": time.time() - start})
                    return _finalize_run(record, timeout, log_dir)
                else:
                    _w(f"  {_C.BYELLOW}[!] mshta niedostepne - uruchamianie przez node (Browser API moze nie dzialac).{_C.RESET}\n")
        except Exception:
            pass

    interpreter = _find_interpreter(plugin_name)
    if not interpreter:
        _w(f"\n  {_C.RED}[!] Interpreter nie znaleziony dla: {plugin_name}{_C.RESET}\n")
        _w(f"  {_C.DIM}Zainstaluj jeden z: {', '.join(pdata['interpreters'])}{_C.RESET}\n\n")
        record["status"] = "interpreter_not_found"
        return _finalize_run(record, timeout, log_dir)

    env = os.environ.copy()
    if _RunnerStats.env_vars:
        env.update(_RunnerStats.env_vars)

    if pdata.get("_compile"):
        _w(f"\n  {_C.BOLD}{_C.BCYAN}RUN:{_C.RESET}  {_C.BWHITE}{os.path.basename(file_path)}{_C.RESET}"
           f"  {_C.DIM}[{plugin_name} / kompilacja]{_C.RESET}\n")
        _w(f"  {_C.DIM}Kompilator: {interpreter}{_C.RESET}\n")
        _w(f"  {_C.DIM}{'-'*52}{_C.RESET}\n\n")
        _RunnerStats.active_script = {"name": os.path.basename(file_path), "start": time.time()}
        record["interpreter"] = interpreter
        result = _compile_and_run(file_path, plugin_name, interpreter, args or [], env, timeout, record)
        _RunnerStats.active_script = None
        return _finalize_run(result, timeout, log_dir)

    run_args = pdata["run_args"]
    cmd      = [interpreter] + run_args + [file_path]
    if args:
        cmd += args

    _w(f"\n  {_C.BOLD}{_C.BCYAN}RUN:{_C.RESET}  {_C.BWHITE}{os.path.basename(file_path)}{_C.RESET}"
       f"  {_C.DIM}[{plugin_name}]{_C.RESET}\n")
    _w(f"  {_C.DIM}Interpreter: {interpreter}{_C.RESET}\n")
    if args:
        _w(f"  {_C.DIM}Argumenty:   {' '.join(args)}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'-'*52}{_C.RESET}\n\n")

    _RunnerStats.active_script = {"name": os.path.basename(file_path), "start": time.time()}
    out = err = ""
    exitcode  = -1
    status    = "error"
    start     = time.time()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=env)
        if _job_id and _job_id in _JOBS:
            _JOBS[_job_id]["pid"]  = proc.pid
            _JOBS[_job_id]["proc"] = proc
            priority = _JOBS[_job_id].get("priority", "norm")
            if priority != "norm":
                _set_proc_priority(proc, priority)
        try:
            out, err = proc.communicate(timeout=timeout)
            exitcode = proc.returncode; status = "ok"
        except subprocess.TimeoutExpired:
            proc.kill(); out, err = proc.communicate()
            exitcode = -1; status = "timeout"
    except Exception as e:
        err = str(e); status = "launch_error"
        _w(f"  {_C.RED}[!] Blad uruchamiania: {e}{_C.RESET}\n\n")
    finally:
        _RunnerStats.active_script = None
        record.update({"interpreter": interpreter, "cmd": cmd,
                       "stdout": out, "stderr": err,
                       "exitcode": exitcode, "status": status,
                       "time_sec": time.time() - start})

    return _finalize_run(record, timeout, log_dir)


def _finalize_run(record, timeout, log_dir):
    if record["stdout"].strip():
        _w(f"  {_C.DIM}[STDOUT]{_C.RESET}\n")
        for line in record["stdout"].rstrip().splitlines():
            _w(f"  {line}{_C.RESET}\n")
        _w("\n")
    _w(f"  {_C.DIM}{'-'*52}{_C.RESET}\n")
    status   = record["status"]
    exitcode = record["exitcode"]
    elapsed  = record["time_sec"]
    if status == "timeout":
        _w(f"  {_C.RED}[!] Timeout po {timeout}s{_C.RESET}\n")
    elif exitcode == 0:
        _w(f"  {_C.BGREEN}[V] OK{_C.RESET}  {_C.DIM}czas: {elapsed:.3f}s{_C.RESET}\n")
    else:
        _w(f"  {_C.RED}[!] Kod wyjscia: {exitcode}{_C.RESET}  {_C.DIM}czas: {elapsed:.3f}s{_C.RESET}\n")
    if record["stderr"].strip():
        _w(f"\n  {_C.BYELLOW}[STDERR]{_C.RESET}\n")
        for line in record["stderr"].rstrip().splitlines():
            _w(f"  {_C.DIM}{line}{_C.RESET}\n")
    _w("\n")
    _RunnerStats.last_result = {
        "name": os.path.basename(record["file"]),
        "exitcode": record["exitcode"],
        "status": record["status"],
        "time": time.time()
    }
    if record["status"] != "ok" or record["exitcode"] != 0:
        _RunnerStats.error_history.insert(0, _RunnerStats.last_result)
        if len(_RunnerStats.error_history) > 5:
            _RunnerStats.error_history.pop()
    _write_log(log_dir, record)
    return record


# --- logi ---------------------------------------------------------------------

def _write_log(log_dir, record):
    try:
        os.makedirs(log_dir, exist_ok=True)
        ts    = time.strftime("%Y%m%d_%H%M%S")
        fname = f"run_{record['id'][:8]}_{ts}.json"
        path  = os.path.join(log_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        record["log_path"] = path
    except Exception:
        pass


def _highlight_json(data):
    import re
    text = json.dumps(data, indent=2, ensure_ascii=False)
    text = re.sub(r'(".*?")\s*:', f'{_C.BCYAN}\\1{_C.RESET}:', text)
    text = re.sub(r':\s*(".*?")',  f': {_C.BYELLOW}\\1{_C.RESET}', text)
    text = re.sub(r':\s*(\d+)',    f': {_C.BGREEN}\\1{_C.RESET}', text)
    return text


def _do_log_view(target, log_dir=DEFAULT_LOG_DIR):
    if not os.path.isdir(log_dir): return
    files = sorted([f for f in os.listdir(log_dir) if f.startswith("run_")])
    found_path = None
    if target.isdigit() and int(target) <= len(files):
        found_path = os.path.join(log_dir, files[int(target)-1])
    else:
        for f in files:
            if target in f:
                found_path = os.path.join(log_dir, f); break
    if found_path and os.path.exists(found_path):
        try:
            with open(found_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            _w(f"  {_C.RED}[!] Nie mozna odczytac logu: {found_path}{_C.RESET}\n")
            return
        _w(f"\n{_C.BOLD}--- Szczegoly logu: {os.path.basename(found_path)} ---{_C.RESET}\n")
        _w(_highlight_json(data) + "\n\n")
    else:
        _w(f"\n  {_C.RED}[!] Nie znaleziono logu: {target}{_C.RESET}\n\n")


def _do_log_tail(log_dir=DEFAULT_LOG_DIR):
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    _w(f"\n  {_C.BOLD}{_C.BCYAN}Sledzenie logow w: {log_dir}...{_C.RESET} (Ctrl+C aby przerwac)\n\n")
    seen_files = set(os.listdir(log_dir))
    try:
        while True:
            time.sleep(1)
            current_files = set(os.listdir(log_dir))
            for fname in sorted(current_files - seen_files):
                if fname.startswith("run_") and fname.endswith(".json"):
                    try:
                        with open(os.path.join(log_dir, fname), encoding="utf-8") as f:
                            r = json.load(f)
                        ok     = r.get("exitcode", -1) == 0
                        status = f"{_C.BGREEN}OK{_C.RESET}" if ok else f"{_C.RED}ERR{_C.RESET}"
                        ts     = r.get("timestamp", "?")
                        fname_ = os.path.basename(r.get("file", "?"))
                        elapsed= f"{r.get('time_sec', 0):.3f}s"
                        _w(f"  {_C.DIM}{ts}{_C.RESET}  {status}  {_C.BYELLOW}{fname_:<20}{_C.RESET}  {_C.DIM}{elapsed}{_C.RESET}\n")
                    except Exception:
                        pass
            seen_files = current_files
    except KeyboardInterrupt:
        _w(f"\n  {_C.BYELLOW}Zatrzymano sledzenie logow.{_C.RESET}\n\n")


def _do_log(args, log_dir=DEFAULT_LOG_DIR):
    sub = args[0].lower() if args else ""
    if sub == "clear":
        if not os.path.isdir(log_dir):
            _w(f"  {_C.DIM}Brak katalogu logow.{_C.RESET}\n"); return
        removed = 0
        for f in os.listdir(log_dir):
            if f.startswith("run_") and f.endswith(".json"):
                try: os.remove(os.path.join(log_dir, f)); removed += 1
                except Exception: pass
        _w(f"\n  {_C.BGREEN}[V] Usunieto {removed} plik(ow) logow.{_C.RESET}\n\n"); return
    if sub == "view":
        if len(args) < 2:
            _w(f"\n  {_C.RED}[!] Uzycie: run log view <id|index>{_C.RESET}\n\n"); return
        _do_log_view(args[1]); return
    if sub == "tail":
        _do_log_tail(log_dir); return
    n = int(sub) if sub.isdigit() else 5
    if not os.path.isdir(log_dir):
        _w(f"\n  {_C.DIM}Brak katalogu logow: {log_dir}{_C.RESET}\n\n"); return
    files = sorted(
        [f for f in os.listdir(log_dir) if f.startswith("run_") and f.endswith(".json")],
        reverse=True
    )[:n]
    if not files:
        _w(f"\n  {_C.DIM}Brak logow w: {log_dir}{_C.RESET}\n\n"); return
    _w(f"\n  {_C.BOLD}{_C.BCYAN}Ostatnie {len(files)} log(ow):{_C.RESET}\n\n")
    for idx, fname in enumerate(files, 1):
        try:
            with open(os.path.join(log_dir, fname), encoding="utf-8") as f:
                r = json.load(f)
            ok     = r.get("exitcode", -1) == 0
            status = f"{_C.BGREEN}OK{_C.RESET}" if ok else f"{_C.RED}ERR({r.get('exitcode')}){_C.RESET}"
            if r.get("status") == "timeout": status = f"{_C.RED}TIMEOUT{_C.RESET}"
            ts      = r.get("timestamp", "?")
            plugin  = r.get("plugin", "?")
            fname_  = os.path.basename(r.get("file", "?"))
            elapsed = f"{r.get('time_sec', 0):.3f}s"
            _w(f"  {_C.BOLD}{idx:02d}.{_C.RESET} {_C.DIM}{ts}{_C.RESET}  "
               f"{status}  "
               f"{_C.BYELLOW}{fname_}{_C.RESET}  "
               f"{_C.DIM}[{plugin}]  {elapsed}{_C.RESET}\n")
        except Exception:
            _w(f"  {_C.DIM}{fname} - blad odczytu{_C.RESET}\n")
    _w("\n")


# --- schedule / retry ---------------------------------------------------------

def _do_schedule(args, terminal=None):
    if len(args) < 2:
        _w(f"\n  {_C.RED}[!] Uzycie: run schedule <HH:MM> <plik> [args...]{_C.RESET}\n\n"); return
    time_str  = args[0]
    file_path = args[1]
    extra     = args[2:] if len(args) > 2 else []
    try:
        target_t  = datetime.strptime(time_str, "%H:%M").time()
        now       = datetime.now()
        target_dt = datetime.combine(now.date(), target_t)
        if target_dt < now:
            target_dt += timedelta(days=1)
        delay = (target_dt - now).total_seconds()
        _w(f"\n  {_C.BGREEN}[V] Zaplanowano:{_C.RESET} {os.path.basename(file_path)} na {target_dt.strftime('%H:%M')}\n")
        _w(f"  {_C.DIM}Oczekiwanie: {int(delay)} sekund...{_C.RESET}\n\n")

        def _wait_and_run():
            time.sleep(delay)
            _do_run(file_path, args=extra)
            _w("\a")

        threading.Thread(target=_wait_and_run, daemon=True).start()
    except ValueError:
        _w(f"\n  {_C.RED}[!] Nieprawidlowy format godziny. Uzyj HH:MM (np. 15:30).{_C.RESET}\n\n")


def _do_retry(args):
    if len(args) < 2:
        _w(f"\n  {_C.RED}[!] Uzycie: run retry <liczba_prob> <plik> [args...]{_C.RESET}\n\n"); return
    try:
        max_tries = int(args[0])
        file_path = args[1]
        extra     = args[2:] if len(args) > 2 else []
        for i in range(1, max_tries + 1):
            _w(f"\n  {_C.BOLD}{_C.BYELLOW}Proba {i} z {max_tries}...{_C.RESET}\n")
            res = _do_run(file_path, args=extra)
            if res and res.get("status") == "ok" and res.get("exitcode") == 0:
                _w(f"\n  {_C.BGREEN}[V] Skrypt zakonczony sukcesem po {i} probie.{_C.RESET}\n\n"); return
            if i < max_tries:
                _w(f"  {_C.RED}[!] Niepowodzenie. Czekam na ponowienie...{_C.RESET}\n")
                time.sleep(2)
    except ValueError:
        _w(f"\n  {_C.RED}[!] Pierwszy argument musi byc liczba (liczba prob).{_C.RESET}\n\n")


# --- glowna komenda -----------------------------------------------------------

def _cmd_run(args, terminal=None):
    """run - zarzadzanie skryptami (Script Runner v3.4)."""
    if not args:
        _cml_menu(); return

    if "--debug" in args:
        args.remove("--debug")
        if not args:
            _w(f"\n  {_C.RED}[!] Uzycie: run --debug <plik>{_C.RESET}\n\n"); return
        if terminal:
            terminal._run_line(f"debug trace {args[0]}")
        return

    sub = args[0].lower()

    if sub == "list":    _do_list(); return
    if sub == "jobs":
        if len(args) > 1 and args[1].lower() == "top": _do_jobs_top()
        else: _do_jobs_list()
        return
    if sub == "kill":
        if len(args) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run kill <id|all>{_C.RESET}\n\n"); return
        _do_job_kill(args[1]); return
    if sub == "pause":
        if len(args) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run pause <id>{_C.RESET}\n\n"); return
        _do_job_pause(args[1]); return
    if sub == "resume":
        if len(args) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run resume <id>{_C.RESET}\n\n"); return
        _do_job_resume(args[1]); return
    if sub == "prio":
        if len(args) < 3: _w(f"\n  {_C.RED}[!] Uzycie: run prio <id> <low|norm|high>{_C.RESET}\n\n"); return
        _do_job_prio(args[1], args[2].lower()); return
    if sub == "limit":
        if len(args) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run limit <id> [--cpu N] [--mem M]{_C.RESET}\n\n"); return
        job_id = args[1]; rest = args[2:]
        cpu_v = mem_v = None
        i = 0
        while i < len(rest):
            if rest[i] == "--cpu" and i + 1 < len(rest):
                try: cpu_v = float(rest[i+1])
                except ValueError: pass
                i += 2
            elif rest[i] == "--mem" and i + 1 < len(rest):
                try: mem_v = int(rest[i+1])
                except ValueError: pass
                i += 2
            else: i += 1
        _do_job_limit(job_id, cpu_limit=cpu_v, mem_limit_mb=mem_v); return
    if sub == "bg":
        if len(args) < 2:
            _w(f"\n  {_C.RED}[!] Uzycie: run bg <plik> [--prio low|norm|high] [--cpu N] [--mem M] [args...]{_C.RESET}\n\n"); return
        bg_args = args[1:]; prio = "norm"; cpu_lim = mem_lim = None; file_arg = None; extra = []
        i = 0
        while i < len(bg_args):
            if bg_args[i] == "--prio" and i + 1 < len(bg_args):
                prio = bg_args[i+1].lower(); i += 2
            elif bg_args[i] == "--cpu" and i + 1 < len(bg_args):
                try: cpu_lim = float(bg_args[i+1])
                except ValueError: pass
                i += 2
            elif bg_args[i] == "--mem" and i + 1 < len(bg_args):
                try: mem_lim = int(bg_args[i+1])
                except ValueError: pass
                i += 2
            elif file_arg is None:
                file_arg = bg_args[i]; i += 1
            else:
                extra.append(bg_args[i]); i += 1
        if not file_arg:
            _w(f"\n  {_C.RED}[!] Uzycie: run bg <plik> [opcje]{_C.RESET}\n\n"); return
        _do_bg_run(file_arg, args=extra, priority=prio, cpu_limit=cpu_lim, mem_limit_mb=mem_lim); return
    if sub == "watch":
        if len(args) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run watch <plik> [args...]{_C.RESET}\n\n"); return
        _do_watch(args[1], args=args[2:]); return
    if sub == "env":
        rest = args[1:]
        if not rest: _do_env_show()
        elif rest[0].lower() == "load":
            if len(rest) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run env load <plik.env>{_C.RESET}\n\n")
            else: _do_env_load(rest[1])
        else: _w(f"\n  {_C.RED}[!] Nieznana komenda env: {rest[0]}{_C.RESET}\n\n")
        return
    if sub == "profile":
        rest = args[1:]
        if not rest or rest[0].lower() == "list": _do_profile_list()
        elif rest[0].lower() == "new":
            if len(rest) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run profile new <nazwa>{_C.RESET}\n\n")
            else: _do_profile_new(rest[1])
        elif rest[0].lower() == "use":
            if len(rest) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run profile use <nazwa>{_C.RESET}\n\n")
            else: _do_profile_use(rest[1])
        elif rest[0].lower() == "del":
            if len(rest) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run profile del <nazwa>{_C.RESET}\n\n")
            else: _do_profile_del(rest[1])
        elif rest[0].lower() == "show":
            if len(rest) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run profile show <nazwa>{_C.RESET}\n\n")
            else: _do_profile_show(rest[1])
        elif rest[0].lower() == "export":
            if len(rest) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run profile export <nazwa> [plik.env]{_C.RESET}\n\n")
            else: _do_profile_export(rest[1], rest[2] if len(rest) > 2 else None)
        else: _w(f"\n  {_C.RED}[!] Nieznana komenda profile: {rest[0]}{_C.RESET}\n\n")
        return
    if sub == "set":
        if len(args) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run set <KLUCZ>=<WARTOSC>{_C.RESET}\n\n"); return
        if "=" in args[1]:
            k, v = args[1].split("=", 1)
            _RunnerStats.env_vars[k.strip()] = v.strip()
            _sync_active_profile()
            _w(f"\n  {_C.BGREEN}[V] Ustawiono:{_C.RESET} {k.strip()}={v.strip()}"
               f"  {_C.DIM}[profil: {_RunnerStats.active_profile}]{_C.RESET}\n\n")
        else:
            _w(f"\n  {_C.RED}[!] Bledny format. Uzyj KLUCZ=WARTOSC{_C.RESET}\n\n")
        return
    if sub == "unset":
        if len(args) < 2: _w(f"\n  {_C.RED}[!] Uzycie: run unset <KLUCZ>{_C.RESET}\n\n"); return
        _do_unset(args[1]); return
    if sub == "schedule":
        _do_schedule(args[1:], terminal); return
    if sub == "retry":
        _do_retry(args[1:]); return
    if sub == "log":
        _do_log(args[1:]); return

    # run <plik> [args...]
    _do_run(args[0], args=args[1:] if len(args) > 1 else [])


def _cmd_runner(args, terminal=None):
    """runner - menu Script Runnera."""
    _cml_menu()


# --- setup / teardown (architektura core) -------------------------------------

def setup(terminal):
    _init_profiles()

    def run_cmd(args):
        _cmd_run(args, terminal)

    def runner_cmd(args):
        _cmd_runner(args, terminal)

    terminal.register_command(
        "run", run_cmd,
        description=terminal.t("cmd_run"),
        category=terminal.t("cat_ecosystem"),
    )
    terminal.register_command(
        "runner", runner_cmd,
        description=terminal.t("cmd_runner"),
        category=terminal.t("cat_ecosystem"),
    )

    # Rejestracja w _integration - sandbox/scripts deleguja wyszukiwanie interpretera
    try:
        from . import _integration

        def _find_interp_for_ext(ext: str) -> tuple[str | None, list[str]]:
            """Zwraca (sciezka_interpretera, extra_args) dla danego rozszerzenia."""
            if ext.lower() == ".py":
                return sys.executable, []
            plugin_name = _EXT_MAP.get(ext.lower())
            if not plugin_name:
                return None, []
            interp = _find_interpreter(plugin_name)
            if not interp or interp == "_webbrowser":
                return None, []
            extra = PLUGINS.get(plugin_name, {}).get("run_args", [])
            return interp, extra

        _integration.register("runner", {
            "find_interpreter": _find_interp_for_ext,
            "ext_map":          _EXT_MAP,
            "plugins":          PLUGINS,
            "active_jobs":      _JOBS,
        })
    except Exception:
        pass


def teardown(terminal):
    terminal.commands.pop("run",    None)
    terminal.commands.pop("runner", None)
    try:
        from . import _integration
        _integration.unregister("runner")
    except Exception:
        pass
