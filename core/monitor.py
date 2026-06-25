#!/usr/bin/env python3
# autor:   Sebastian Januchowski
# company: polsoft.ITS(TM) Group
# web:     www.polsoft.gt.tc
# github:  https://github.com/seb07uk
# email:   polsoft.its@fastservice.com
# license: MIT
# crossterm: {"id": "05", "aliases": ["mon", "monitor"], "description": "Monitor systemu - CPU, RAM, dysk, siec, procesy, sprzet", "version": "1.5", "author": "Sebastian Januchowski"}
"""
Modul Monitor v1.5
  mon                       - dashboard systemu (CPU, GPU, RAM, dysk, siec)
  mon cpu                   - szczegoly CPU (kazdy rdzen osobno)
  mon cpu hist              - historia obciazenia CPU (ostatnie 30 probek)
  mon ram                   - szczegoly pamieci RAM i swap
  mon disk [sciezka]        - uzycie dyskow / partycji
  mon disk clean <kat> [n]  - analiza katalogu: top N największych (domyslnie 15)
  mon net                   - statystyki interfejsow sieciowych
  mon netspeed [s]          - predkosc sieci live (RX/TX MB/s) [domyslnie 1s]
  mon top [n]               - top N procesow wg CPU [domyslnie 10]
  mon top ram [n]           - top N procesow wg RAM
  mon top disk [n]          - top N procesow wg I/O dysku
  mon watch [s]             - live dashboard, odswiezanie co s sekund [domyslnie 2]
  mon gpu                   - karta graficzna (obciazenie, temp, VRAM)
  mon temp                  - wszystkie czujniki temperatur (CPU, dysk, plyta)
  mon load                  - load average systemu (1/5/15 min)
  mon env [filtr]           - zmienne srodowiskowe systemu (opcjonalny filtr)
  mon sched                 - zaplanowane zadania (cron / Task Scheduler)
  mon proc <nazwa|pid>      - szczegoly konkretnego procesu
  mon runner                - status ostatnio uruchomionych skryptow (modul sr)
  mon kill <pid>            - zakoncz proces (SIGTERM)
  mon kill9 <pid>           - wymus zakonczenie procesu (SIGKILL)
  mon battery               - status baterii (jesli dostepna)
  mon uptime                - czas od uruchomienia systemu
  mon serial                - lista dostepnych portow szeregowych (COM)
  mon serial term <port>    - prosty terminal szeregowy (baud 9600)
  mon usb                   - lista podlaczonych urzadzen USB
  mon audio                 - lista urzadzen dzwiekowych
  mon info                  - szczegolowe dane o sprzecie (BIOS, CPU, OS)
  mon ports [filtr]         - otwarte porty sieciowe (opcjonalny filtr portu/nazwy)
  mon export [plik]         - eksport snapshotu systemu do JSON
  mon diff <A.json> <B.json>- porownanie dwoch snapshotow (delta CPU/RAM/dysk/siec)
  mon alert                 - sprawdz system vs progi i wyswietl raport
  mon alert set <k> <v>     - ustaw prog (np. mon alert set cpu 90)
  mon alert show            - pokaz aktualne progi
  mon alert reset           - przywroc domyslne progi
  monitor                   - alias -> mon
"""

import sys
import os
import re as _re
import time
import json
import platform
import shutil
import subprocess
from pathlib import Path

_sys = sys

# ─── stałe i cache ────────────────────────────────────────────────────────────

_NVIDIA_SMI_CMD = (
    "nvidia-smi --query-gpu=name,utilization.gpu,temperature.gpu,"
    "memory.used,memory.total --format=csv,noheader,nounits"
)
_SUBPROCESS_TIMEOUT = 5   # sekund — limit dla każdego wywołania zewnętrznego

_CPU_NAME_CACHE: str = ""   # wypełniany przy pierwszym wywołaniu _get_cpu_info


def _run_cmd(cmd, *, shell: bool = False, encoding: str = "utf-8",
             errors: str = "replace") -> str:
    """Uruchamia subprocess z timeoutem; zwraca stdout lub '' przy błędzie."""
    try:
        return subprocess.check_output(
            cmd, shell=shell, stderr=subprocess.DEVNULL,
            timeout=_SUBPROCESS_TIMEOUT,
        ).decode(encoding, errors=errors)
    except (subprocess.SubprocessError, OSError, FileNotFoundError,
            subprocess.TimeoutExpired, ValueError):
        return ""


def _parse_nvidia_smi(out: str) -> list:
    """Parsuje wyjście nvidia-smi CSV → lista słowników GPU. DRY helper."""
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        def _nv(v: str):
            return None if v in ("[N/A]", "N/A", "") else v
        nv_name, nv_load, nv_temp, nv_used, nv_total = (
            parts[0], _nv(parts[1]), _nv(parts[2]), _nv(parts[3]), _nv(parts[4])
        )
        try:
            gpus.append({
                "name":     nv_name,
                "type":     "NVIDIA",
                "ram":      float(nv_total) / 1024 if nv_total else 0.0,
                "load":     float(nv_load)          if nv_load  else None,
                "temp":     float(nv_temp)          if nv_temp  else None,
                "mem_used": float(nv_used) / 1024   if nv_used  else None,
            })
        except ValueError:
            pass
    return gpus


def _w(s: str):
    _sys.stdout.write(s)
    _sys.stdout.flush()


# ─── kolory ───────────────────────────────────────────────────────────────────

class _C:
    RESET   = "\x1b[0m";  BOLD    = "\x1b[1m";  DIM     = "\x1b[2m"
    BCYAN   = "\x1b[96m"; BYELLOW = "\x1b[93m"; BGREEN  = "\x1b[92m"
    BWHITE  = "\x1b[97m"; RED     = "\x1b[91m"; CYAN    = "\x1b[36m"
    MAGENTA = "\x1b[95m"; YELLOW  = "\x1b[33m"; BLUE    = "\x1b[94m"
    BRED    = "\x1b[91m"; ORANGE  = "\x1b[33m"


# ─── psutil — lazy import (wykonywany przy pierwszym użyciu, nie przy starcie) ──

_psutil     = None
_HAS_PSUTIL = None   # None = nie sprawdzono jeszcze

def _ensure_psutil() -> bool:
    """Importuje psutil przy pierwszym wywołaniu. Zwraca True jeśli dostępny."""
    global _psutil, _HAS_PSUTIL
    if _HAS_PSUTIL is not None:
        return _HAS_PSUTIL
    try:
        import psutil as _ps
        _psutil     = _ps
        _HAS_PSUTIL = True
    except ImportError:
        _HAS_PSUTIL = False
    return _HAS_PSUTIL


# ─── fallback — odczyt z /proc (Linux bez psutil) ────────────────────────────

def _proc_cpu_percent() -> float:
    try:
        def _read():
            with open("/proc/stat") as f:
                line = f.readline()
            parts = line.split()
            total = sum(int(x) for x in parts[1:])
            idle  = int(parts[4])
            return total, idle
        t1, i1 = _read(); time.sleep(0.3); t2, i2 = _read()
        dt = t2 - t1; di = i2 - i1
        return round((1.0 - di / dt) * 100, 1) if dt else 0.0
    except Exception:
        return -1.0


def _proc_mem() -> dict:
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k.strip()] = int(v.split()[0])
    except Exception:
        pass
    return info


def _disk_usage(path: str = "/") -> dict:
    try:
        total, used, free = shutil.disk_usage(path)
        pct = used / total * 100 if total else 0
        return {"total": total, "used": used, "free": free, "percent": pct}
    except Exception:
        return {}


# ─── formatowanie ─────────────────────────────────────────────────────────────

def _ansi_pad(text: str, width: int) -> str:
    visible_len = len(_re.sub(r'\x1b\[[0-9;]*m', '', text))
    return text + ' ' * max(0, width - visible_len)


_POLISH_MAP = {
    'ą':'a','ć':'c','ę':'e','ł':'l','ń':'n','ó':'o','ś':'s','ź':'z','ż':'z',
    'Ą':'A','Ć':'C','Ę':'E','Ł':'L','Ń':'N','Ó':'O','Ś':'S','Ź':'Z','Ż':'Z',
}

def _clean_iface(name: str) -> str:
    return "".join(_POLISH_MAP.get(c, c) if ord(c) < 128 or c in _POLISH_MAP else "?" for c in name)


def _fmt_bytes(n: float, precision: int = 1) -> str:
    if n < 0:
        return "?"
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    for unit in units[:-1]:
        if abs(n) < 1024.0:
            return f"{n:.{precision}f} {unit}"
        n /= 1024.0
    return f"{n:.{precision}f} {units[-1]}"


def _bar(pct: float, width: int = 20) -> str:
    filled = max(0, min(int(round(pct / 100 * width)), width))
    empty  = width - filled
    color  = _C.BGREEN if pct < 60 else (_C.BYELLOW if pct < 85 else _C.BRED)
    bar    = f"{color}{'▓' * filled}{_C.DIM}{'░' * empty}{_C.RESET}"
    return f"[{bar}] {color}{pct:5.1f}%{_C.RESET}"


def _sparkline(history: list, width: int = 30) -> str:
    """Miniaturowy wykres z historii wartości (0-100) używając znaków blokowych."""
    blocks = " ▁▂▃▄▅▆▇█"
    if not history:
        return ""
    # weź ostatnie `width` próbek
    data = history[-width:]
    result = ""
    for v in data:
        v = max(0.0, min(100.0, float(v)))
        idx = int(v / 100 * (len(blocks) - 1))
        result += blocks[idx]
    return result


def _cols() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def _sep(char: str = "─", label: str = "") -> str:
    w = _cols()
    if label:
        return (f"  {_C.BCYAN}{'┌' + '─' * (w - 6) + '┐'}{_C.RESET}\n"
                f"  {_C.BCYAN}│{_C.RESET}  {_C.BOLD}{_C.BWHITE}{label.center(w - 6)}{_C.RESET}{_C.BCYAN}│{_C.RESET}\n"
                f"  {_C.BCYAN}{'└' + '─' * (w - 6) + '┘'}{_C.RESET}\n\n")
    return f"  {_C.DIM}{char * (w - 4)}{_C.RESET}\n"


# ─── historia CPU (sparkline) ─────────────────────────────────────────────────

_cpu_history: list = []   # maks. 60 próbek


# ─── zbieranie danych ─────────────────────────────────────────────────────────

def _get_cpu_info() -> dict:
    global _CPU_NAME_CACHE
    result: dict = {
        "per_core": [], "total": -1.0, "count_log": os.cpu_count() or 1,
        "count_phy": None, "freq_cur": None, "freq_max": None,
    }

    if _ensure_psutil():
        try:
            per_core = _psutil.cpu_percent(interval=0.4, percpu=True)
            result["per_core"]  = per_core
            result["total"]     = sum(per_core) / len(per_core) if per_core else 0.0
            result["count_log"] = _psutil.cpu_count(logical=True) or 1
            result["count_phy"] = _psutil.cpu_count(logical=False)
        except Exception:
            pass
        try:
            freq = _psutil.cpu_freq()
            result["freq_cur"] = freq.current if freq else None
            result["freq_max"] = freq.max     if freq else None
        except Exception:
            pass
        try:
            temps = _psutil.sensors_temperatures() or {}
            for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
                if key in temps and temps[key]:
                    result["temp"] = temps[key][0].current
                    break
        except Exception:
            pass
    else:
        result["total"] = _proc_cpu_percent()

    # Nazwa CPU — z cache po pierwszym odczycie
    if _CPU_NAME_CACHE:
        result["name"] = _CPU_NAME_CACHE
    else:
        name = ""
        sys_name = platform.system()
        if sys_name == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if line.startswith("model name"):
                            name = line.split(":", 1)[1].strip()
                            break
            except OSError:
                pass
        elif sys_name == "Windows":
            out = _run_cmd(["wmic", "cpu", "get", "name"], shell=False,
                           encoding="cp1250")
            lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
            name = lines[-1] if lines else ""
        elif sys_name == "Darwin":
            name = _run_cmd(
                ["sysctl", "-n", "machdep.cpu.brand_string"]
            ).strip()
        if not name:
            name = platform.processor() or "?"
        _CPU_NAME_CACHE = name
        result["name"] = name

    return result


def _get_ram_info() -> dict:
    if _ensure_psutil():
        vm = _psutil.virtual_memory()
        sw = _psutil.swap_memory()
        return {
            "total":    vm.total,
            "used":     vm.used,
            "free":     vm.available,
            "percent":  vm.percent,
            "sw_total": sw.total,
            "sw_used":  sw.used,
            "sw_pct":   sw.percent,
        }
    else:
        info = _proc_mem()
        if not info:
            return {}
        total = info.get("MemTotal", 0) * 1024
        free  = info.get("MemAvailable", info.get("MemFree", 0)) * 1024
        used  = total - free
        pct   = used / total * 100 if total else 0
        sw_t  = info.get("SwapTotal", 0) * 1024
        sw_f  = info.get("SwapFree",  0) * 1024
        sw_u  = sw_t - sw_f
        sw_p  = sw_u / sw_t * 100 if sw_t else 0
        return {
            "total": total, "used": used, "free": free, "percent": pct,
            "sw_total": sw_t, "sw_used": sw_u, "sw_pct": sw_p,
        }


def _get_disk_info() -> list:
    parts = []
    if _ensure_psutil():
        for p in _psutil.disk_partitions(all=False):
            try:
                u = _psutil.disk_usage(p.mountpoint)
                parts.append({
                    "device":     p.device,
                    "mountpoint": p.mountpoint,
                    "fstype":     p.fstype,
                    "total":      u.total,
                    "used":       u.used,
                    "free":       u.free,
                    "percent":    u.percent,
                })
            except OSError:
                pass
    else:
        du = _disk_usage("/")
        if du:
            parts.append({"device": "?", "mountpoint": "/", "fstype": "?", **du})
    return parts


def _get_net_info() -> dict:
    if not _ensure_psutil():
        return {}
    try:
        nets = {}
        counters = _psutil.net_io_counters(pernic=True)
        for iface, cnt in counters.items():
            if iface in ("lo", "Loopback Pseudo-Interface 1"):
                continue
            nets[iface] = {
                "bytes_sent": cnt.bytes_sent,
                "bytes_recv": cnt.bytes_recv,
                "pkts_sent":  cnt.packets_sent,
                "pkts_recv":  cnt.packets_recv,
            }
        return nets
    except Exception:
        return {}


def _get_gpu_info() -> list:
    gpus: list = []
    sys_name = platform.system()

    if sys_name == "Windows":
        # WMIC — podstawowe info (zawsze dostępne)
        out = _run_cmd(
            'wmic path win32_VideoController get Name,AdapterRAM /value',
            shell=True, encoding="cp1250"
        )
        current_gpu: dict = {}
        for line in out.splitlines():
            line = line.strip()
            if not line:
                if current_gpu.get("name"):
                    gpus.append(current_gpu)
                current_gpu = {}
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip().lower(); v = v.strip()
            if k == "name" and v:
                current_gpu["name"] = v
            elif k == "adapterram":
                try:
                    current_gpu["ram"] = int(v) / (1024 ** 3)
                except (ValueError, TypeError):
                    current_gpu["ram"] = 0.0
        if current_gpu.get("name"):
            gpus.append(current_gpu)
        for g in gpus:
            g.setdefault("type", "N/A");  g.setdefault("load", None)
            g.setdefault("temp", None);   g.setdefault("mem_used", None)

        # nvidia-smi — nadpisz/wzbogać wpisy WMIC
        nv_out = _run_cmd(_NVIDIA_SMI_CMD, shell=True)
        if nv_out.strip():
            for nv in _parse_nvidia_smi(nv_out):
                matched = False
                for g in gpus:
                    if nv["name"] in g.get("name", "") or g.get("name", "") in nv["name"]:
                        g.update({k: v for k, v in nv.items() if v is not None})
                        matched = True
                        break
                if not matched:
                    gpus.append(nv)

    elif sys_name in ("Linux", "Darwin"):
        # nvidia-smi
        nv_out = _run_cmd(_NVIDIA_SMI_CMD, shell=True)
        if nv_out.strip():
            gpus.extend(_parse_nvidia_smi(nv_out))

        # AMD / Intel przez /sys (Linux only)
        if sys_name == "Linux" and not gpus:
            _vendor_map = {"0x10de": "NVIDIA", "0x1002": "AMD", "0x8086": "Intel"}
            seen: set = set()
            for drm in Path("/sys/class/drm").glob("card*/device"):
                try:
                    vendor = (drm / "vendor").read_text().strip()
                    vname  = _vendor_map.get(vendor, vendor)
                    if vname not in seen:
                        seen.add(vname)
                        gpus.append({
                            "name": f"{vname} GPU", "type": vname,
                            "ram": 0.0, "load": None, "temp": None, "mem_used": None,
                        })
                except OSError:
                    pass

    return gpus


def _get_top_processes(n: int = 10, sort_by: str = "cpu") -> list:
    if not _ensure_psutil():
        return []

    # Pierwsze wywołanie cpu_percent rejestruje punkt startowy — wymagane przez psutil
    attrs = ["pid", "name", "cpu_percent", "memory_percent", "memory_info", "status", "username"]
    for p in _psutil.process_iter(["pid", "cpu_percent"]):
        try:
            p.cpu_percent()
        except (_psutil.NoSuchProcess, _psutil.AccessDenied):
            pass

    time.sleep(0.5)

    result = []
    for p in _psutil.process_iter(attrs):
        try:
            info  = p.info
            minfo = info.get("memory_info")
            ram_b = minfo.rss if minfo else 0
            try:
                user = (info.get("username") or "?").split("\\")[-1][:14]
            except Exception:
                user = "?"
            result.append({
                "pid":    info["pid"],
                "name":   (info["name"] or "?")[:28],
                "cpu":    info.get("cpu_percent") or 0.0,
                "ram":    info.get("memory_percent") or 0.0,
                "ram_mb": ram_b,
                "status": info.get("status", "?"),
                "user":   user,
            })
        except (_psutil.NoSuchProcess, _psutil.AccessDenied):
            pass

    key = "ram" if sort_by == "ram" else "cpu"
    return sorted(result, key=lambda x: x[key], reverse=True)[:n]


def _get_top_disk_io(n: int = 10) -> list:
    """Top procesów wg I/O dysku (wymaga uprawnień root/admin)."""
    if not _ensure_psutil():
        return []
    result = []
    for p in _psutil.process_iter(["pid", "name", "io_counters"]):
        try:
            io = p.info.get("io_counters")
            if io:
                total = io.read_bytes + io.write_bytes
                result.append({
                    "pid":         p.info["pid"],
                    "name":        (p.info["name"] or "?")[:28],
                    "read_bytes":  io.read_bytes,
                    "write_bytes": io.write_bytes,
                    "total":       total,
                })
        except (_psutil.NoSuchProcess, _psutil.AccessDenied):
            pass
    result = sorted(result, key=lambda x: x["total"], reverse=True)[:n]
    grand_total = sum(r["total"] for r in result) or 1
    for r in result:
        r["pct"] = r["total"] / grand_total * 100
    return result


# ─── widoki ───────────────────────────────────────────────────────────────────

def _view_cpu(detailed: bool = False):
    info = _get_cpu_info()
    _w("\n")
    _w(_sep(label="  CPU  "))

    name = info.get("name", "?")
    _w(f"  {_C.DIM}Procesor   {_C.RESET}{_C.BWHITE}{name}{_C.RESET}\n")

    lc = info.get("count_log", "?")
    pc = info.get("count_phy", "?")
    _w(f"  {_C.DIM}Rdzenie    {_C.RESET}{_C.BCYAN}{pc} fizyczne{_C.RESET}  /  {_C.BCYAN}{lc} logiczne{_C.RESET}\n")

    fc = info.get("freq_cur")
    fm = info.get("freq_max")
    if fc:
        _w(f"  {_C.DIM}Taktowanie {_C.RESET}{_C.BYELLOW}{fc:.0f} MHz{_C.RESET}"
           + (f"  {_C.DIM}(max {fm:.0f} MHz){_C.RESET}" if fm else "") + "\n")

    temp = info.get("temp")
    if temp is not None:
        tc = _C.BGREEN if temp < 65 else (_C.BYELLOW if temp < 80 else _C.BRED)
        _w(f"  {_C.DIM}Temperatura{_C.RESET} {tc}{temp:.1f} °C{_C.RESET}\n")

    _w("\n")
    total = info.get("total", -1)
    if total >= 0:
        _cpu_history.append(total)
        if len(_cpu_history) > 60:
            del _cpu_history[:-60]
        _w(f"  Ogolem     {_C.BOLD}{_bar(total)}{_C.RESET}\n")

    if detailed and info.get("per_core"):
        _w("\n")
        for i, pct in enumerate(info["per_core"]):
            label = f"  Rdzen {i:2d}  "
            _w(f"{label}{_C.RESET} {_bar(pct, width=16)}\n")

    _w("\n")


def _view_cpu_hist():
    """Historia obciążenia CPU — sparkline ostatnich 60 próbek."""
    _w("\n")
    _w(_sep(label="  Historia CPU  "))
    if not _cpu_history:
        # pobierz kilka próbek jeśli brak historii
        _w(f"  {_C.DIM}Zbieranie probek...{_C.RESET}\n")
        for _ in range(5):
            if _ensure_psutil():
                _cpu_history.append(_psutil.cpu_percent(interval=0.4))
            else:
                _cpu_history.append(_proc_cpu_percent())

    spark = _sparkline(_cpu_history)
    avg   = sum(_cpu_history) / len(_cpu_history)
    peak  = max(_cpu_history)
    _w(f"  {_C.DIM}Próbki: {len(_cpu_history):<5} Śr: {avg:.1f}%   Max: {peak:.1f}%{_C.RESET}\n\n")
    _w(f"  {_C.BCYAN}{spark}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'0%':<15}{'50%':^15}{'100%':>14}{_C.RESET}\n\n")


def _view_gpu():
    gpus = _get_gpu_info()
    _w("\n")
    _w(_sep(label="  GPU  "))
    if not gpus:
        _w(f"  {_C.DIM}Nie wykryto aktywnej karty graficznej.{_C.RESET}\n\n")
        return
    for g in gpus:
        _w(f"  {_C.BOLD}{g['name']}{_C.RESET}\n")
        if g.get('ram', 0) > 0:
            _w(f"  {_C.DIM}VRAM:      {_C.RESET}{_C.BCYAN}{g['ram']:.1f} GB{_C.RESET}\n")
        if g['load'] is not None:
            _w(f"  {_C.BOLD}Obciazenie {_C.RESET} {_bar(g['load'])}\n")
        if g['temp'] is not None and g['temp'] > 0:
            tc = _C.BGREEN if g['temp'] < 65 else (_C.BYELLOW if g['temp'] < 80 else _C.BRED)
            _w(f"  {_C.DIM}Temperatura{_C.RESET} {tc}{g['temp']:.1f} °C{_C.RESET}\n")
        if g['mem_used'] is not None:
            ram = g.get('ram', 0)
            mem_pct = (g['mem_used'] / ram) * 100 if ram > 0 else 0
            _w(f"  {_C.DIM}Pamiec     {_C.RESET} {_bar(mem_pct, width=16)}  {_C.DIM}{g['mem_used']:.1f} / {ram:.1f} GB{_C.RESET}\n")
        _w("\n")


def _view_ram():
    info = _get_ram_info()
    if not info:
        _w(f"  {_C.RED}Brak danych o RAM.{_C.RESET}\n")
        return
    _w("\n")
    _w(_sep(label="  RAM  "))

    _w(f"  {_C.BOLD}RAM       {_C.RESET} {_bar(info['percent'])}"
       f"  {_C.DIM}{_fmt_bytes(info['used'])} / {_fmt_bytes(info['total'])}{_C.RESET}\n")
    _w(f"  {_C.DIM}Wolne      {_C.RESET}{_C.BGREEN}{_fmt_bytes(info['free'])}{_C.RESET}\n")

    if info.get("sw_total", 0) > 0:
        _w(f"\n  {_C.BOLD}Swap      {_C.RESET} {_bar(info['sw_pct'], width=16)}"
           f"  {_C.DIM}{_fmt_bytes(info['sw_used'])} / {_fmt_bytes(info['sw_total'])}{_C.RESET}\n")
    _w("\n")


def _view_disk(path: str = None):
    if path:
        p = path.strip().rstrip("\\/")
        if len(p) == 1 and p.isalpha():
            path = p.upper() + ":\\"
        elif len(p) == 2 and p[1] == ":" and p[0].isalpha():
            path = p.upper() + "\\"

    parts = _get_disk_info() if not path else None
    _w("\n")
    _w(_sep(label="  Dysk  "))

    if path:
        du = _disk_usage(path)
        if not du:
            _w(f"  {_C.RED}Nie mozna odczytac: {path}{_C.RESET}\n\n")
            return
        _w(f"  {_C.BWHITE}{path}{_C.RESET}\n")
        _w(f"  {_bar(du['percent'])}  {_C.DIM}{_fmt_bytes(du['used'])} / {_fmt_bytes(du['total'])}{_C.RESET}\n")
        _w(f"  {_C.DIM}Wolne  {_C.RESET}{_C.BGREEN}{_fmt_bytes(du['free'])}{_C.RESET}\n")
    else:
        if not parts:
            _w(f"  {_C.DIM}Brak danych. Zainstaluj psutil: {_C.RESET}{_C.BYELLOW}pip install psutil{_C.RESET}\n")
        else:
            for p in parts:
                mp  = p["mountpoint"]
                dev = Path(p["device"]).name if p["device"] != "?" else "?"
                fs  = p.get("fstype", "?") or "?"
                _w(f"  {_C.BWHITE}{mp:<18}{_C.RESET} {_C.DIM}{dev:<12} {fs:<8}{_C.RESET} "
                   f"{_bar(p['percent'], width=14)}  "
                   f"{_C.DIM}{_fmt_bytes(p['used'])} / {_fmt_bytes(p['total'])}{_C.RESET}\n")
    _w("\n")


def _view_disk_clean(path: str = ".", top_n: int = 15):
    """Analiza katalogu — największe pliki i podkatalogi z rozszerzeniem, datą modyfikacji."""
    _w("\n")
    target = Path(path).resolve()
    _w(_sep(label=f"  Analiza: {str(target)[:60]}  "))
    if not target.exists():
        _w(f"  {_C.RED}[!] Sciezka nie istnieje: {path}{_C.RESET}\n\n")
        return
    if not target.is_dir():
        _w(f"  {_C.RED}[!] Podana sciezka nie jest katalogiem: {path}{_C.RESET}\n\n")
        return

    _w(f"  {_C.DIM}Skanowanie...{_C.RESET}\r")

    entries = []
    skipped = 0
    hidden  = 0
    try:
        for item in target.iterdir():
            try:
                is_hidden = item.name.startswith(".")
                if is_hidden:
                    hidden += 1
                st = item.stat()
                if item.is_file():
                    sz   = st.st_size
                    mtime = st.st_mtime
                    ext  = item.suffix.lower() or "(brak)"
                    ro   = not os.access(item, os.W_OK)
                    entries.append({
                        "typ":    "plik",
                        "name":   item.name,
                        "sz":     sz,
                        "mtime":  mtime,
                        "ext":    ext,
                        "ro":     ro,
                        "hidden": is_hidden,
                    })
                elif item.is_dir():
                    sz = 0
                    fc = 0
                    for f in item.rglob("*"):
                        try:
                            if f.is_file():
                                sz += f.stat().st_size
                                fc += 1
                        except OSError:
                            pass
                    mtime = st.st_mtime
                    entries.append({
                        "typ":    "dir",
                        "name":   item.name,
                        "sz":     sz,
                        "mtime":  mtime,
                        "ext":    f"({fc} pl.)",
                        "ro":     False,
                        "hidden": is_hidden,
                    })
            except (PermissionError, OSError):
                skipped += 1
    except PermissionError:
        _w(f"  {_C.RED}[!] Brak uprawnien do: {path}{_C.RESET}\n\n")
        return

    entries.sort(key=lambda x: x["sz"], reverse=True)
    total_sz   = sum(e["sz"] for e in entries)
    total_dirs = sum(1 for e in entries if e["typ"] == "dir")
    total_files= sum(1 for e in entries if e["typ"] == "plik")

    # Statystyki według rozszerzenia (top 5)
    ext_sizes: dict = {}
    for e in entries:
        if e["typ"] == "plik":
            ext_sizes[e["ext"]] = ext_sizes.get(e["ext"], 0) + e["sz"]
    top_exts = sorted(ext_sizes.items(), key=lambda x: x[1], reverse=True)[:5]

    _w(f"  {_C.DIM}Lacznie: {_fmt_bytes(total_sz)}"
       f"  ·  {total_files} plikow"
       f"  ·  {total_dirs} katalogow"
       f"  ·  {hidden} ukrytych"
       + (f"  ·  {skipped} pominieto (brak dostepu)" if skipped else "")
       + f"{_C.RESET}\n\n")

    # Tabela główna
    C_TYP, C_NAME, C_EXT, C_SZ, C_PCT, C_DATE = 4, 36, 10, 12, 8, 17
    _w(f"  {_C.BOLD}{_C.BWHITE}"
       f"{'Typ':<{C_TYP}}  "
       f"{'Nazwa':<{C_NAME}}"
       f"{'Ext/Info':<{C_EXT}}"
       f"{'Rozmiar':>{C_SZ}}  "
       f"{'Udział':>{C_PCT}}  "
       f"{'Modyfikacja':<{C_DATE}}"
       f"{'RO'}"
       f"{_C.RESET}\n")
    _w(f"  {_C.BCYAN}{'─' * (_cols() - 6)}{_C.RESET}\n")

    for e in entries[:top_n]:
        pct    = e["sz"] / total_sz * 100 if total_sz else 0
        mdate  = time.strftime("%Y-%m-%d %H:%M", time.localtime(e["mtime"]))
        ro_s   = f"  {_C.RED}RO{_C.RESET}" if e.get("ro") else ""
        hid_s  = f"{_C.DIM}·{_C.RESET}" if e["hidden"] else " "

        if e["typ"] == "dir":
            typ_c  = _C.BYELLOW
            typ_s  = "DIR"
            name_c = _C.BYELLOW
        else:
            typ_c  = _C.DIM
            typ_s  = "FILE"
            name_c = _C.BWHITE

        bar_w  = max(1, int(pct / 100 * 8))
        bar_s  = f"{_C.BGREEN}{'█' * bar_w}{'░' * (8 - bar_w)}{_C.RESET}"

        col_typ  = _ansi_pad(f"{typ_c}{typ_s}{_C.RESET}", C_TYP)
        col_name = _ansi_pad(f"{hid_s}{name_c}{e['name'][:C_NAME - 1]}{_C.RESET}", C_NAME + 1)
        col_ext  = _ansi_pad(f"{_C.DIM}{e['ext'][:C_EXT - 1]}{_C.RESET}", C_EXT)
        col_sz   = _ansi_pad(f"{_C.BGREEN}{_fmt_bytes(e['sz'])}{_C.RESET}", C_SZ)
        col_pct  = _ansi_pad(f"{bar_s} {_C.DIM}{pct:4.1f}%{_C.RESET}", C_PCT + 14)

        _w(f"  {col_typ}  {col_name}{col_ext}{col_sz}  {col_pct}  "
           f"{_C.DIM}{mdate}{_C.RESET}{ro_s}\n")

    if len(entries) > top_n:
        _w(f"  {_C.DIM}... i {len(entries) - top_n} wiecej elementow{_C.RESET}\n")

    # Podsumowanie wg rozszerzenia
    if top_exts:
        _w(f"\n  {_C.BOLD}{_C.BCYAN}Top rozszerzen wg rozmiaru:{_C.RESET}\n")
        for ext, sz in top_exts:
            bar_w = max(1, int(sz / total_sz * 20)) if total_sz else 0
            _w(f"  {_C.DIM}{ext:<10}{_C.RESET}"
               f" {_C.BCYAN}{'▓' * bar_w}{'░' * (20 - bar_w)}{_C.RESET}"
               f"  {_C.BGREEN}{_fmt_bytes(sz):>10}{_C.RESET}"
               f"  {_C.DIM}{sz / total_sz * 100:.1f}%{_C.RESET}\n")

    _w("\n")


def _view_net():
    nets = _get_net_info()
    _w("\n")
    _w(_sep(label="  Siec  "))

    if not nets:
        _w(f"  {_C.DIM}Brak danych. Zainstaluj psutil: {_C.RESET}{_C.BYELLOW}pip install psutil{_C.RESET}\n\n")
        return

    # Pobierz adresy IP i status interfejsów
    iface_addrs: dict = {}
    iface_stats: dict = {}
    try:
        for iface, addrs in _psutil.net_if_addrs().items():
            ipv4 = [a.address for a in addrs if a.family == 2]   # AF_INET
            ipv6 = [a.address.split("%")[0] for a in addrs if a.family == 10]  # AF_INET6
            iface_addrs[iface] = {"ipv4": ipv4, "ipv6": ipv6}
    except Exception:
        pass
    try:
        for iface, stat in _psutil.net_if_stats().items():
            iface_stats[iface] = {"up": stat.isup, "speed": stat.speed, "mtu": stat.mtu}
    except Exception:
        pass

    nets_clean = {_clean_iface(k): (k, v) for k, v in nets.items()}
    COL_IFACE = max((len(name) for name in nets_clean), default=14) + 2
    COL_RX    = 14
    COL_TX    = 14
    COL_PKT   = 12

    hdr_iface = f"{'Interfejs':<{COL_IFACE}}"
    _w(f"  {_C.BOLD}{_C.BWHITE}{hdr_iface}{'RX':<{COL_RX}}{'TX':<{COL_TX}}{'Pkt RX':<{COL_PKT}}Pkt TX{_C.RESET}\n")
    _w(f"  {_C.BCYAN}{'─' * (_cols() - 6)}{_C.RESET}\n")

    for clean_name, (raw_name, cnt) in nets_clean.items():
        stat  = iface_stats.get(raw_name, {})
        addrs = iface_addrs.get(raw_name, {})
        is_up = stat.get("up", True)
        speed = stat.get("speed", 0)
        mtu   = stat.get("mtu", 0)

        up_c  = _C.BGREEN if is_up else _C.DIM
        up_s  = "↑UP" if is_up else "↓DN"
        speed_s = f"  {_C.DIM}{speed} Mb/s{_C.RESET}" if speed else ""
        mtu_s   = f"  {_C.DIM}MTU {mtu}{_C.RESET}" if mtu else ""

        rx_str  = _fmt_bytes(cnt["bytes_recv"])
        tx_str  = _fmt_bytes(cnt["bytes_sent"])
        prx_str = str(cnt["pkts_recv"])
        ptx_str = str(cnt["pkts_sent"])

        c_iface = _ansi_pad(f"{up_c}{clean_name}{_C.RESET}", COL_IFACE)
        c_rx    = _ansi_pad(f"{_C.BGREEN}{rx_str}{_C.RESET}", COL_RX)
        c_tx    = _ansi_pad(f"{_C.BYELLOW}{tx_str}{_C.RESET}", COL_TX)
        c_prx   = _ansi_pad(f"{_C.DIM}{prx_str}{_C.RESET}", COL_PKT)

        # Linia główna
        _w(f"  {c_iface}{c_rx}{c_tx}{c_prx}{_C.DIM}{ptx_str}{_C.RESET}\n")

        # Linia pomocnicza: status + IP
        status_pad = " " * (COL_IFACE + 2)
        ip4_s = f"  {_C.BCYAN}{', '.join(addrs.get('ipv4', []))}{_C.RESET}" if addrs.get("ipv4") else ""
        ip6_s = f"  {_C.DIM}{addrs.get('ipv6', [''])[0]}{_C.RESET}" if addrs.get("ipv6") else ""
        _w(f"  {status_pad}{up_c}{up_s}{_C.RESET}{speed_s}{mtu_s}{ip4_s}{ip6_s}\n\n")


def _view_netspeed(interval: float = 1.0):
    """Prędkość sieci w czasie rzeczywistym (RX/TX MB/s). Ctrl+C = wyjście."""
    if not _ensure_psutil():
        _w(f"\n  {_C.RED}[!] Wymaga psutil: pip install psutil{_C.RESET}\n\n")
        return

    def _snapshot():
        c = _psutil.net_io_counters(pernic=True)
        return {k: (v.bytes_recv, v.bytes_sent)
                for k, v in c.items()
                if k not in ("lo", "Loopback Pseudo-Interface 1")}

    _w(f"\n{_sep(label='  Predkosc Sieci (live)  ')}")
    _w(f"  {_C.DIM}Pomiar co {interval}s  ·  Ctrl+C aby wyjsc{_C.RESET}\n\n")

    prev = _snapshot()
    _w("\x1b[?25l")
    try:
        count = 0
        while True:
            time.sleep(interval)
            curr = _snapshot()
            lines = []
            for iface in sorted(curr):
                if iface not in prev:
                    continue
                rx_d = max(0.0, (curr[iface][0] - prev[iface][0]) / interval)
                tx_d = max(0.0, (curr[iface][1] - prev[iface][1]) / interval)
                rx_str = _fmt_bytes(rx_d) + "/s"
                tx_str = _fmt_bytes(tx_d) + "/s"
                iface_c = _ansi_pad(f"{_C.BCYAN}{_clean_iface(iface)}{_C.RESET}", 18)
                lines.append(
                    f"  {iface_c}"
                    f"  {_C.DIM}⬇ RX{_C.RESET} {_C.BGREEN}{rx_str:<14}{_C.RESET}"
                    f"  {_C.DIM}⬆ TX{_C.RESET} {_C.BYELLOW}{tx_str}{_C.RESET}\n"
                )
            prev = curr
            if count > 0:
                _w(f"\x1b[{len(lines) + 1}A")
            _w(f"  {_C.DIM}{time.strftime('%H:%M:%S')}{_C.RESET}\n")
            for ln in lines:
                _w(ln)
            count += 1
    except KeyboardInterrupt:
        _w(f"\n\n  {_C.DIM}■  Zatrzymano.{_C.RESET}\n\n")
    finally:
        _w("\x1b[?25h")


def _view_top(n: int = 10, sort_by: str = "cpu"):
    label = "RAM" if sort_by == "ram" else "CPU"
    _w("\n")
    _w(_sep(label=f"  Top {n} procesow wg {label}  "))

    if not _ensure_psutil():
        _w(f"  {_C.DIM}Wymaga psutil: {_C.RESET}{_C.BYELLOW}pip install psutil{_C.RESET}\n\n")
        return

    _w(f"  {_C.DIM}Pobieranie probki CPU...{_C.RESET}\r")
    procs = _get_top_processes(n, sort_by)
    _w(f"  {' ' * 30}\r")  # wyczyść linię statusu

    # Szerokości kolumn
    C_PID, C_NAME, C_CPU, C_RAM, C_RAMMB, C_USER, C_STAT = 7, 28, 8, 8, 12, 14, 10

    hdr = (f"  {_C.BOLD}{_C.BWHITE}"
           f"{'PID':>{C_PID}}  "
           f"{'Nazwa':<{C_NAME}}"
           f"{'CPU %':>{C_CPU}}"
           f"{'RAM %':>{C_RAM}}  "
           f"{'RAM':>{C_RAMMB}}  "
           f"{'Uzytkownik':<{C_USER}}"
           f"{'Status':<{C_STAT}}"
           f"{_C.RESET}\n")
    sep_len = C_PID + C_NAME + C_CPU + C_RAM + C_RAMMB + C_USER + C_STAT + 10
    _w(hdr)
    _w(f"  {_C.BCYAN}{'─' * sep_len}{_C.RESET}\n")

    for p in procs:
        cpu_c  = _C.BGREEN if p["cpu"] < 30  else (_C.BYELLOW if p["cpu"] < 70  else _C.BRED)
        ram_c  = _C.BGREEN if p["ram"] < 10  else (_C.BYELLOW if p["ram"] < 30  else _C.BRED)
        # Wyróżnij kolumnę sortowania
        cpu_b  = _C.BOLD if sort_by == "cpu" else ""
        ram_b  = _C.BOLD if sort_by == "ram" else ""
        stat_c = _C.BGREEN if p["status"] == "running" else _C.DIM

        _w(f"  {_C.DIM}{p['pid']:>{C_PID}}{_C.RESET}  "
           f"{_C.BWHITE}{p['name']:<{C_NAME}}{_C.RESET}"
           f"{cpu_b}{cpu_c}{p['cpu']:>{C_CPU}.1f}{_C.RESET}"
           f"{ram_b}{ram_c}{p['ram']:>{C_RAM}.2f}{_C.RESET}  "
           f"{_C.DIM}{_fmt_bytes(p['ram_mb']):>{C_RAMMB}}{_C.RESET}  "
           f"{_C.DIM}{p['user']:<{C_USER}}{_C.RESET}"
           f"{stat_c}{p['status']:<{C_STAT}}{_C.RESET}\n")

    total_cpu = sum(p["cpu"] for p in procs)
    total_ram = sum(p["ram_mb"] for p in procs)
    _w(f"  {_C.BCYAN}{'─' * sep_len}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'':>{C_PID}}  {'SUMA top ' + str(len(procs)):<{C_NAME}}"
       f"{total_cpu:>{C_CPU}.1f}"
       f"{'':>{C_RAM}}  "
       f"{_fmt_bytes(total_ram):>{C_RAMMB}}{_C.RESET}\n\n")


def _view_top_disk(n: int = 10):
    _w("\n")
    _w(_sep(label=f"  Top {n} procesow wg I/O Dysku  "))
    if not _ensure_psutil():
        _w(f"  {_C.DIM}Wymaga psutil.{_C.RESET}\n\n")
        return

    procs = _get_top_disk_io(n)
    if not procs:
        _w(f"  {_C.DIM}Brak danych I/O (moze wymagac uprawnien root/admin).{_C.RESET}\n\n")
        return

    C_PID, C_NAME, C_RD, C_WR, C_TOT = 7, 28, 14, 14, 14
    _w(f"  {_C.BOLD}{_C.BWHITE}"
       f"{'PID':>{C_PID}}  "
       f"{'Nazwa':<{C_NAME}}"
       f"{'Odczyt':>{C_RD}}  "
       f"{'Zapis':>{C_WR}}  "
       f"{'Razem':>{C_TOT}}  "
       f"{'Udzial'}"
       f"{_C.RESET}\n")
    sep_len = C_PID + C_NAME + C_RD + C_WR + C_TOT + 24
    _w(f"  {_C.BCYAN}{'─' * sep_len}{_C.RESET}\n")

    total_rd = total_wr = 0
    for p in procs:
        total_rd += p["read_bytes"]
        total_wr += p["write_bytes"]
        bar = _bar(p["pct"], width=10)
        _w(f"  {_C.DIM}{p['pid']:>{C_PID}}{_C.RESET}  "
           f"{_C.BWHITE}{p['name']:<{C_NAME}}{_C.RESET}"
           f"{_C.BGREEN}{_fmt_bytes(p['read_bytes']):>{C_RD}}{_C.RESET}  "
           f"{_C.BYELLOW}{_fmt_bytes(p['write_bytes']):>{C_WR}}{_C.RESET}  "
           f"{_C.BCYAN}{_fmt_bytes(p['total']):>{C_TOT}}{_C.RESET}  "
           f"{bar}\n")

    _w(f"  {_C.BCYAN}{'─' * sep_len}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'':>{C_PID}}  {'SUMA top ' + str(len(procs)):<{C_NAME}}"
       f"{_fmt_bytes(total_rd):>{C_RD}}  "
       f"{_fmt_bytes(total_wr):>{C_WR}}  "
       f"{_fmt_bytes(total_rd + total_wr):>{C_TOT}}{_C.RESET}\n\n")


def _view_proc(query: str):
    """Szczegóły konkretnego procesu (nazwa lub PID)."""
    if not _ensure_psutil():
        _w(f"\n  {_C.RED}[!] Wymaga psutil.{_C.RESET}\n\n")
        return

    _w("\n")
    proc = None
    matches = []
    try:
        pid = int(query)
        proc = _psutil.Process(pid)
    except ValueError:
        for p in _psutil.process_iter(["pid", "name"]):
            try:
                if query.lower() in (p.info["name"] or "").lower():
                    matches.append(p.info["pid"])
            except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                pass
        if len(matches) == 1:
            try:
                proc = _psutil.Process(matches[0])
            except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                pass
        elif len(matches) > 1:
            _w(f"  {_C.BYELLOW}Znaleziono {len(matches)} procesow pasujacych do '{query}':{_C.RESET}\n\n")
            for m_pid in matches[:20]:
                try:
                    mp = _psutil.Process(m_pid)
                    _w(f"  {_C.DIM}{m_pid:>7}{_C.RESET}  {_C.BWHITE}{mp.name()}{_C.RESET}\n")
                except Exception:
                    pass
            _w(f"\n  {_C.DIM}Uzyj PID: mon proc <pid>{_C.RESET}\n\n")
            return
    except (_psutil.NoSuchProcess, _psutil.AccessDenied):
        pass

    if proc is None:
        _w(f"  {_C.RED}[!] Nie znaleziono procesu: {query}{_C.RESET}\n\n")
        return

    try:
        proc.cpu_percent()
    except Exception:
        pass
    time.sleep(0.4)

    try:
        with proc.oneshot():
            name    = proc.name()
            pid     = proc.pid
            status  = proc.status()
            cpu_pct = proc.cpu_percent()
            mem     = proc.memory_info()
            mem_pct = proc.memory_percent()
            create  = proc.create_time()
            try:
                cmd = " ".join(proc.cmdline()) or "?"
            except (_psutil.AccessDenied, Exception):
                cmd = "?"
            try:
                exe = proc.exe()
            except (_psutil.AccessDenied, Exception):
                exe = "?"
            try:
                user = proc.username().split("\\")[-1]
            except (_psutil.AccessDenied, Exception):
                user = "?"
            try:
                cwd = str(proc.cwd())
            except (_psutil.AccessDenied, Exception):
                cwd = "?"
            try:
                threads = proc.num_threads()
            except Exception:
                threads = "?"
            try:
                conns = len(proc.connections())
            except (_psutil.AccessDenied, Exception):
                conns = "?"
            try:
                open_files = len(proc.open_files())
            except (_psutil.AccessDenied, Exception):
                open_files = "?"
            try:
                nice = proc.nice()
            except Exception:
                nice = "?"
            try:
                ppid = proc.ppid()
                parent_name = _psutil.Process(ppid).name() if ppid else "?"
            except Exception:
                ppid, parent_name = "?", "?"
            vms = getattr(mem, "vms", None)

        # Zmienne środowiskowe procesu (poza oneshot — mogą być niedostępne)
        proc_env: dict = {}
        try:
            proc_env = proc.environ()
        except (_psutil.AccessDenied, Exception):
            pass

        # Procesy potomne
        children: list = []
        try:
            children = proc.children(recursive=False)
        except (_psutil.AccessDenied, Exception):
            pass

        _w(_sep(label=f"  Proces: {name} [{pid}]  "))

        uptime_s = int(time.time() - create)
        d, r = divmod(uptime_s, 86400); h, r = divmod(r, 3600); m = r // 60
        uptime_str = f"{d}d {h}h {m}m" if d else (f"{h}h {m}m" if h else f"{m}m")
        start_ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(create))

        status_c = _C.BGREEN if status == "running" else (_C.BYELLOW if status == "sleeping" else _C.DIM)

        col = 14
        rows = [
            ("PID",          f"{_C.BWHITE}{pid}{_C.RESET}"),
            ("Nazwa",        f"{_C.BWHITE}{name}{_C.RESET}"),
            ("Status",       f"{status_c}{status}{_C.RESET}"),
            ("Uzytkownik",   f"{_C.DIM}{user}{_C.RESET}"),
            ("Nice",         f"{_C.DIM}{nice}{_C.RESET}"),
            ("Rodzic",       f"{_C.DIM}{ppid}  {parent_name}{_C.RESET}"),
            ("",             ""),
            ("CPU",          f"{_bar(cpu_pct, width=18)}"),
            ("RAM (RSS)",    f"{_bar(mem_pct, width=18)}  {_C.DIM}{_fmt_bytes(mem.rss)}{_C.RESET}"),
            ("RAM (VMS)",    f"{_C.DIM}{_fmt_bytes(vms) if vms else '?'}{_C.RESET}"),
            ("",             ""),
            ("Watki",        f"{_C.BWHITE}{threads}{_C.RESET}"),
            ("Polaczenia",   f"{_C.BWHITE}{conns}{_C.RESET}"),
            ("Otwarte pliki",f"{_C.BWHITE}{open_files}{_C.RESET}"),
            ("Potomkowie",   f"{_C.BWHITE}{len(children)}{_C.RESET}"),
            ("",             ""),
            ("Uruchomiony",  f"{_C.DIM}{start_ts}{_C.RESET}"),
            ("Czas dzia.",   f"{_C.BGREEN}{uptime_str}{_C.RESET}"),
            ("",             ""),
            ("EXE",          f"{_C.DIM}{exe[:72]}{_C.RESET}"),
            ("CWD",          f"{_C.DIM}{cwd[:72]}{_C.RESET}"),
            ("Cmd",          f"{_C.DIM}{cmd[:72]}{_C.RESET}"),
        ]
        for lbl, val in rows:
            if not lbl:
                _w("\n")
                continue
            _w(f"  {_C.DIM}{lbl:<{col}}{_C.RESET} {val}\n")

        # ── Procesy potomne ──
        if children:
            _w(f"\n  {_C.BOLD}{_C.BCYAN}Potomkowie ({len(children)}):{_C.RESET}\n")
            for ch in children[:10]:
                try:
                    _w(f"  {_C.DIM}  {ch.pid:>7}{_C.RESET}  {_C.BWHITE}{ch.name()}{_C.RESET}\n")
                except Exception:
                    pass
            if len(children) > 10:
                _w(f"  {_C.DIM}  ... i {len(children) - 10} wiecej{_C.RESET}\n")

        # ── Zmienne środowiskowe procesu ──
        if proc_env:
            _w(f"\n  {_C.BOLD}{_C.BCYAN}Zmienne srodowiskowe procesu ({len(proc_env)}):{_C.RESET}\n")
            # Priorytetowe — klucze istotne dla debugowania
            priority_env = {
                "PATH", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_DEFAULT_ENV",
                "HOME", "USERPROFILE", "APPDATA", "TEMP", "TMP",
                "LANG", "LC_ALL", "TERM", "SHELL",
                "NODE_ENV", "RAILS_ENV", "DJANGO_SETTINGS_MODULE",
                "DATABASE_URL", "PORT", "HOST",
            }
            shown = 0
            for k in sorted(priority_env & proc_env.keys()):
                v = proc_env[k]
                val_t = v[:60] + ("…" if len(v) > 60 else "")
                _w(f"  {_C.BYELLOW}  {k:<28}{_C.RESET} {_C.DIM}{val_t}{_C.RESET}\n")
                shown += 1
            rest = {k: v for k, v in proc_env.items() if k not in priority_env}
            for k in sorted(rest)[:max(0, 15 - shown)]:
                v = rest[k]
                val_t = v[:60] + ("…" if len(v) > 60 else "")
                _w(f"  {_C.BCYAN}  {k:<28}{_C.RESET} {_C.DIM}{val_t}{_C.RESET}\n")
                shown += 1
            remaining = len(proc_env) - shown
            if remaining > 0:
                _w(f"  {_C.DIM}  ... i {remaining} wiecej "
                   f"(uzyj 'mon env' dla pelnej listy srodowiska){_C.RESET}\n")
        elif not proc_env:
            _w(f"\n  {_C.DIM}Zmienne srodowiskowe niedostepne (brak uprawnien).{_C.RESET}\n")

        _w("\n")

    except (_psutil.NoSuchProcess, _psutil.AccessDenied) as e:
        _w(f"  {_C.RED}[!] Blad odczytu: {e}{_C.RESET}\n\n")


def _view_ports(filtr: str = ""):
    """Otwarte porty sieciowe (LISTEN + ESTABLISHED), zgrupowane wg statusu."""
    if not _ensure_psutil():
        _w(f"\n  {_C.RED}[!] Wymaga psutil.{_C.RESET}\n\n")
        return

    _w("\n")

    try:
        conns = _psutil.net_connections(kind="inet")
    except (_psutil.AccessDenied, Exception) as e:
        _w(f"  {_C.RED}[!] Brak uprawnien lub blad: {e}{_C.RESET}\n\n")
        return

    # pid → name cache
    pid_names: dict = {}
    for p in _psutil.process_iter(["pid", "name"]):
        try:
            pid_names[p.info["pid"]] = p.info["name"] or "?"
        except Exception:
            pass

    rows = []
    for c in conns:
        if c.status not in ("LISTEN", "ESTABLISHED"):
            continue
        proto = "TCP" if c.type == 1 else ("UDP" if c.type == 2 else "???")
        laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "?"
        raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-"
        pid_s = str(c.pid or "")
        pname = pid_names.get(c.pid, "?") if c.pid else "?"
        rows.append({
            "proto":  proto,
            "laddr":  laddr,
            "raddr":  raddr,
            "status": c.status,
            "pid":    pid_s,
            "name":   pname,
        })

    # filtr — działa na laddr, raddr, name, pid
    if filtr:
        fl = filtr.lower()
        rows = [r for r in rows
                if fl in r["laddr"].lower()
                or fl in r["raddr"].lower()
                or fl in r["name"].lower()
                or fl in r["pid"]]

    if not rows:
        _w(_sep(label="  Otwarte Porty  "))
        _w(f"  {_C.DIM}Brak wynikow{' dla filtru: ' + filtr if filtr else ''}.{_C.RESET}\n\n")
        return

    # Rozdziel i posortuj
    listening    = sorted([r for r in rows if r["status"] == "LISTEN"],    key=lambda x: x["laddr"])
    established  = sorted([r for r in rows if r["status"] == "ESTABLISHED"], key=lambda x: x["laddr"])

    C_PROTO, C_LOCAL, C_REMOTE, C_PID = 5, 26, 26, 8

    def _print_section(section_rows: list, title: str, title_color: str):
        if not section_rows:
            return
        _w(_sep(label=f"  {title} ({len(section_rows)})  "))
        _w(f"  {_C.BOLD}{_C.BWHITE}"
           f"{'Proto':<{C_PROTO}}  "
           f"{'Lokalny':<{C_LOCAL}}"
           f"{'Zdalny':<{C_REMOTE}}"
           f"{'PID':<{C_PID}}"
           f"Proces"
           f"{_C.RESET}\n")
        _w(f"  {_C.BCYAN}{'─' * (_cols() - 6)}{_C.RESET}\n")
        for r in section_rows[:40]:
            col_proto = _ansi_pad(f"{_C.DIM}{r['proto']}{_C.RESET}", C_PROTO)
            col_l     = _ansi_pad(f"{title_color}{r['laddr']}{_C.RESET}", C_LOCAL)
            col_r     = _ansi_pad(f"{_C.DIM}{r['raddr']}{_C.RESET}", C_REMOTE)
            col_p     = _ansi_pad(f"{_C.DIM}{r['pid']}{_C.RESET}", C_PID)
            _w(f"  {col_proto}  {col_l}{col_r}{col_p}{_C.BWHITE}{r['name'][:22]}{_C.RESET}\n")
        if len(section_rows) > 40:
            _w(f"  {_C.DIM}... i {len(section_rows) - 40} wiecej{_C.RESET}\n")
        _w("\n")

    _print_section(listening,   "Nasluchujace (LISTEN)",    _C.BYELLOW)
    _print_section(established, "Aktywne (ESTABLISHED)",    _C.BGREEN)

    total = len(listening) + len(established)
    _w(f"  {_C.DIM}Lacznie: {total} polaczen"
       f"  ·  LISTEN: {len(listening)}"
       f"  ·  ESTABLISHED: {len(established)}"
       f"{' ·  filtr: ' + filtr if filtr else ''}{_C.RESET}\n\n")


def _view_runner(terminal):
    sr_mod = terminal.modules._loaded.get("sr")
    if not sr_mod:
        _w(f"\n  {_C.RED}[!] Modul 'sr' nie jest zaladowany.{_C.RESET}\n")
        return
    stats = getattr(sr_mod, "_RunnerStats", None)
    if not stats:
        _w(f"\n  {_C.RED}[!] Brak statystyk w module 'sr'.{_C.RESET}\n")
        return

    _w(f"\n{_C.BOLD}{_C.BCYAN}  Status Script Runner (sr):{_C.RESET}\n")
    _w(f"  {_C.BCYAN}{'─'*40}{_C.RESET}\n\n")

    if stats.active_script:
        elap = time.time() - stats.active_script["start"]
        _w(f"  {_C.BYELLOW}AKTYWNY:{_C.RESET}  {_C.BOLD}{stats.active_script['name']}{_C.RESET} "
           f"{_C.DIM}(od {elap:.1f}s){_C.RESET}\n")
    else:
        _w(f"  {_C.BYELLOW}STATUS:{_C.RESET}   Bezczynnosc\n")

    if stats.last_result:
        res = stats.last_result
        color = _C.BGREEN if res["exitcode"] == 0 else _C.BRED
        _w(f"  {_C.BYELLOW}OSTATNI:{_C.RESET}  {res['name']} ({color}KOD: {res['exitcode']}{_C.RESET})\n")

    if stats.error_history:
        _w(f"\n  {_C.BOLD}Historia bledow (ostatnie 5):{_C.RESET}\n")
        for err in stats.error_history:
            _w(f"  {_C.RED}[!] {_C.RESET}{err['name']} {_C.DIM}({err['timestamp']}){_C.RESET}\n")
    _w("\n")


def _cmd_mon_kill(pid_str: str, force: bool = False):
    try:
        pid = int(pid_str)
    except ValueError:
        _w(f"\n  {_C.RED}[!] PID musi byc liczba calkowita.{_C.RESET}\n")
        _w(f"  {_C.DIM}Przyklad: mon kill 1234{_C.RESET}\n\n")
        return
    if pid <= 0:
        _w(f"\n  {_C.RED}[!] Nieprawidlowy PID: {pid}{_C.RESET}\n\n")
        return
    if not _ensure_psutil():
        _w(f"\n  {_C.RED}[!] Brak biblioteki psutil.{_C.RESET}\n"
           f"  {_C.DIM}Instalacja: pip install psutil{_C.RESET}\n\n")
        return
    try:
        p = _psutil.Process(pid)
        name    = p.name()
        status  = p.status()
        try:
            user = p.username().split("\\")[-1]
        except Exception:
            user = "?"
        try:
            cpu_p = p.cpu_percent(interval=0.2)
        except Exception:
            cpu_p = 0.0

        sig_name = "SIGKILL (wymuszone)" if force else "SIGTERM (laskawa)"
        sig_c    = _C.BRED if force else _C.BYELLOW

        _w(f"\n  {_C.BOLD}{_C.BWHITE}Docelowy proces:{_C.RESET}\n")
        _w(f"  {_C.DIM}{'PID':<14}{_C.RESET}{_C.BWHITE}{pid}{_C.RESET}\n")
        _w(f"  {_C.DIM}{'Nazwa':<14}{_C.RESET}{_C.BWHITE}{name}{_C.RESET}\n")
        _w(f"  {_C.DIM}{'Uzytkownik':<14}{_C.RESET}{_C.DIM}{user}{_C.RESET}\n")
        _w(f"  {_C.DIM}{'Status':<14}{_C.RESET}{_C.DIM}{status}{_C.RESET}\n")
        _w(f"  {_C.DIM}{'CPU %':<14}{_C.RESET}{_C.DIM}{cpu_p:.1f}%{_C.RESET}\n")
        _w(f"  {_C.DIM}{'Sygnal':<14}{_C.RESET}{sig_c}{sig_name}{_C.RESET}\n\n")

        if force:
            _w(f"  {_C.BRED}⚠  SIGKILL nie pozwala procesowi na sprzatniecie zasobow!{_C.RESET}\n")

        _w(f"  {_C.BYELLOW}Czy na pewno chcesz zakonczyc '{name}' (PID {pid})? [t/N]: {_C.RESET}")
        _sys.stdout.flush()
        try:
            ans = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""

        if ans not in ("t", "tak", "y", "yes"):
            _w(f"  {_C.DIM}Anulowano.{_C.RESET}\n\n")
            return

        if force:
            p.kill()
            _w(f"\n  {_C.BGREEN}✔  SIGKILL wyslany → {name} (PID {pid}){_C.RESET}\n\n")
        else:
            p.terminate()
            _w(f"\n  {_C.BGREEN}✔  SIGTERM wyslany → {name} (PID {pid}){_C.RESET}\n")
            _w(f"  {_C.DIM}Jesli proces nie reaguje, uzyj: {_C.RESET}{_C.BYELLOW}mon kill9 {pid}{_C.RESET}\n\n")

    except _psutil.NoSuchProcess:
        _w(f"\n  {_C.RED}[!] Proces o PID {pid} nie istnieje.{_C.RESET}\n\n")
    except _psutil.AccessDenied:
        sig = "kill9" if force else "kill"
        _w(f"\n  {_C.RED}[!] Brak uprawnien do zakonczenia PID {pid}.{_C.RESET}\n")
        if not force:
            _w(f"  {_C.DIM}Sprobuj z uprawnieniami administratora lub: {_C.RESET}{_C.BYELLOW}mon kill9 {pid}{_C.RESET}\n")
        else:
            _w(f"  {_C.DIM}Uruchom CrossTerm jako administrator i uzyj: {_C.RESET}{_C.BYELLOW}mon {sig} {pid}{_C.RESET}\n")
        _w("\n")
    except Exception as e:
        _w(f"\n  {_C.RED}[!] Blad: {e}{_C.RESET}\n\n")


def _view_battery():
    if not _ensure_psutil():
        _w(f"\n  {_C.RED}[!] Brak biblioteki psutil.{_C.RESET}\n\n")
        return
    batt = _psutil.sensors_battery()
    if batt is None:
        _w(f"\n  {_C.DIM}Bateria nie zostala wykryta (zasilanie stacjonarne).{_C.RESET}\n\n")
        return
    _w(f"\n{_sep(label='  Bateria  ')}")
    _w(f"  Naladowanie:  {_bar(batt.percent)}\n")
    _w(f"  Zasilacz:     {_C.BGREEN if batt.power_plugged else _C.BYELLOW}"
       f"{'Podlaczony' if batt.power_plugged else 'Odlaczony'}{_C.RESET}\n")
    if not batt.power_plugged and batt.secsleft not in (-1, -2):
        h, m = divmod(batt.secsleft // 60, 60)
        _w(f"  Czas pracy:   {_C.BWHITE}{h}h {m}m{_C.RESET} pozostalo\n")
    _w("\n")


def _view_serial():
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        _w(f"\n{_sep(label='  Porty Serial/COM  ')}")
        if not ports:
            _w(f"  {_C.DIM}Nie znaleziono aktywnych portow COM.{_C.RESET}\n")
        else:
            for p in ports:
                _w(f"  {_C.BGREEN}{p.device:<10}{_C.RESET} {p.description}\n")
                if p.hwid != 'n/a':
                    _w(f"             {_C.DIM}ID: {p.hwid}{_C.RESET}\n")
        _w("\n")
    except ImportError:
        _w(f"\n  {_C.RED}[!] Brak biblioteki 'pyserial'. Zainstaluj: pip install pyserial{_C.RESET}\n\n")


def _serial_terminal(port_name: str, baud: int = 9600):
    try:
        import serial
        import serial.tools.list_ports as _slp
    except ImportError:
        _w(f"\n  {_C.RED}[!] Brak biblioteki 'pyserial'.{_C.RESET}\n"
           f"  {_C.DIM}Instalacja: pip install pyserial{_C.RESET}\n\n")
        return

    # Walidacja — czy port figuruje na liście systemowej
    available = [p.device for p in _slp.comports()]
    if port_name not in available:
        _w(f"\n  {_C.RED}[!] Port '{port_name}' nie jest dostepny.{_C.RESET}\n\n")
        if available:
            _w(f"  {_C.DIM}Dostepne porty:{_C.RESET}\n")
            for ap in available:
                _w(f"    {_C.BGREEN}{ap}{_C.RESET}\n")
            _w(f"\n  {_C.DIM}Uzycie: mon serial term <port>{_C.RESET}\n\n")
        else:
            _w(f"  {_C.DIM}Nie znaleziono zadnych portow COM/Serial w systemie.{_C.RESET}\n\n")
        return

    _w(f"\n  {_C.BOLD}Otwieranie terminala: {_C.BGREEN}{port_name}{_C.RESET}"
       f"{_C.BOLD}  @{baud} baud{_C.RESET}\n")
    _w(f"  {_C.DIM}Nacisnij Ctrl+C aby zamknac.{_C.RESET}\n\n")

    try:
        ser = serial.Serial(port_name, baud, timeout=1)
    except serial.SerialException as e:
        _w(f"  {_C.RED}[!] Nie mozna otworzyc portu: {e}{_C.RESET}\n\n")
        return

    try:
        while True:
            if ser.in_waiting:
                line = ser.readline().decode("utf-8", errors="replace").rstrip()
                if line:
                    ts = time.strftime("%H:%M:%S")
                    _w(f"  {_C.DIM}{ts}{_C.RESET}  {_C.BGREEN}▶{_C.RESET}  {line}\n")
            time.sleep(0.05)
    except KeyboardInterrupt:
        _w(f"\n  {_C.DIM}■  Terminal szeregowy zamkniety.{_C.RESET}\n\n")
    finally:
        ser.close()


def _view_usb():
    _w(f"\n{_sep(label='  Urzadzenia USB  ')}")
    sys_name = platform.system()
    if sys_name == "Windows":
        out = _run_cmd(
            'wmic path Win32_PnPEntity where "Service=\'usbhub\' or Service=\'usbccgp\'" get Name, DeviceID',
            shell=True, encoding="cp1250"
        )
        if not out.strip():
            _w(f"  {_C.RED}[!] Nie udalo sie pobrac listy USB przez WMIC.{_C.RESET}\n")
        else:
            for line in out.strip().splitlines()[1:]:
                if line.strip():
                    _w(f"  {_C.BGREEN}[USB]{_C.RESET} {line.strip()}\n")
    elif sys_name == "Linux":
        out = _run_cmd(["lsusb"])
        if out.strip():
            for line in out.splitlines():
                _w(f"  {_C.BCYAN}[USB]{_C.RESET} {line}\n")
        else:
            import importlib.util
            hint = "pyusb" if importlib.util.find_spec("usb") is not None else "usbutils (lsusb)"
            _w(f"  {_C.DIM}Zainstaluj {hint} dla detekcji USB.{_C.RESET}\n")
    _w("\n")


def _view_audio():
    _w(f"\n{_sep(label='  Urzadzenia Audio  ')}")
    sys_name = platform.system()
    if sys_name == "Windows":
        out = _run_cmd(
            'wmic path Win32_SoundDevice get Name, Status',
            shell=True, encoding="cp1250"
        )
        if not out.strip():
            _w(f"  {_C.RED}[!] Nie udalo sie pobrac listy urzadzen audio.{_C.RESET}\n")
        else:
            for line in out.strip().splitlines()[1:]:
                if line.strip():
                    _w(f"  {_C.BGREEN}[AUDIO]{_C.RESET} {line.strip()}\n")
    elif sys_name == "Linux":
        out = _run_cmd(["aplay", "-l"])
        if out.strip():
            for line in out.splitlines():
                if "card" in line.lower():
                    _w(f"  {_C.BCYAN}[AUDIO]{_C.RESET} {line}\n")
        else:
            _w(f"  {_C.DIM}Zainstaluj alsa-utils dla listy urzadzen.{_C.RESET}\n")
    _w("\n")


def _view_hw_info():
    _w(f"\n{_sep(label='  Informacje o Sprzecie  ')}")
    _w(f"  {_C.BOLD}OS:{_C.RESET}         {platform.system()} {platform.release()} ({platform.machine()})\n")
    _w(f"  {_C.BOLD}Procesor:{_C.RESET}   {platform.processor()}\n")
    _w(f"  {_C.BOLD}Python:{_C.RESET}     {platform.python_version()}\n")
    _w(f"  {_C.BOLD}Hostname:{_C.RESET}   {platform.node()}\n")

    sys_name = platform.system()
    if sys_name == "Windows":
        out = _run_cmd('wmic bios get SerialNumber, Manufacturer', shell=True, encoding="cp1250")
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if len(lines) >= 2:
            _w(f"  {_C.BOLD}BIOS/SN:{_C.RESET}    {lines[-1]}\n")
    elif sys_name == "Linux":
        for fpath, label in (
            ("/sys/class/dmi/id/sys_vendor",   "Producent"),
            ("/sys/class/dmi/id/product_name", "Model"),
            ("/sys/class/dmi/id/bios_version", "BIOS"),
        ):
            try:
                val = Path(fpath).read_text().strip()
                _w(f"  {_C.BOLD}{label}:{_C.RESET}{' ' * max(1, 12 - len(label))}{val}\n")
            except OSError:
                pass
    _w("\n")


def _view_temp():
    _w(f"\n{_sep(label='  Czujniki Temperatury  ')}")
    printed = False

    if _ensure_psutil():
        try:
            sensors = _psutil.sensors_temperatures()
        except AttributeError:
            sensors = {}

        if sensors:
            for chip, entries in sensors.items():
                _w(f"  {_C.BOLD}{_C.BCYAN}{chip}{_C.RESET}\n")
                for e in entries:
                    label = e.label or chip
                    t = e.current
                    tc = _C.BGREEN if t < 65 else (_C.BYELLOW if t < 80 else _C.BRED)
                    high_str = f"  {_C.DIM}(wys: {e.high:.0f}°C){_C.RESET}" if e.high else ""
                    crit_str = f"  {_C.DIM}(kryt: {e.critical:.0f}°C){_C.RESET}" if e.critical else ""
                    _w(f"    {_C.DIM}{label:<28}{_C.RESET} {tc}{t:5.1f} °C{_C.RESET}{high_str}{crit_str}\n")
                _w("\n")
                printed = True

    if not printed and platform.system() == "Linux":
        thermal_base = Path("/sys/class/thermal")
        if thermal_base.exists():
            for zone in sorted(thermal_base.glob("thermal_zone*")):
                try:
                    temp_raw = int((zone / "temp").read_text().strip()) / 1000.0
                    try:
                        typ = (zone / "type").read_text().strip()
                    except Exception:
                        typ = zone.name
                    tc = _C.BGREEN if temp_raw < 65 else (_C.BYELLOW if temp_raw < 80 else _C.BRED)
                    _w(f"  {_C.DIM}{typ:<28}{_C.RESET} {tc}{temp_raw:5.1f} °C{_C.RESET}\n")
                    printed = True
                except Exception:
                    pass
            if printed:
                _w("\n")

    if not printed and platform.system() == "Windows":
        out = _run_cmd(
            r"wmic /namespace:\\root\wmi PATH MSAcpi_ThermalZoneTemperature get CurrentTemperature",
            shell=True, encoding="cp1250"
        )
        if out.strip():
            vals = [ln.strip() for ln in out.splitlines() if ln.strip().lstrip("-").isdigit()]
            for i, v in enumerate(vals):
                try:
                    celsius = (int(v) / 10.0) - 273.15
                    tc = _C.BGREEN if celsius < 65 else (_C.BYELLOW if celsius < 80 else _C.BRED)
                    _w(f"  {_C.DIM}Strefa {i:<24}{_C.RESET} {tc}{celsius:5.1f} °C{_C.RESET}\n")
                    printed = True
                except ValueError:
                    pass
            if printed:
                _w("\n")

    if not printed:
        _w(f"  {_C.DIM}Brak dostepnych czujnikow temperatury na tym systemie.{_C.RESET}\n\n")


def _view_load():
    _w(f"\n{_sep(label='  Load Average  ')}")
    if hasattr(os, "getloadavg"):
        la1, la5, la15 = os.getloadavg()
        cpus = os.cpu_count() or 1
        _w(f"  {_C.DIM}{'Okres':<10}{'Load':>8}{'% CPU':>10}{_C.RESET}\n")
        _w(f"  {_C.BCYAN}{'─'*30}{_C.RESET}\n")
        for label, val in (("1 min", la1), ("5 min", la5), ("15 min", la15)):
            pct = val / cpus * 100
            pc = _C.BGREEN if pct < 70 else (_C.BYELLOW if pct < 100 else _C.BRED)
            _w(f"  {_C.BWHITE}{label:<10}{_C.RESET}{pc}{val:>8.2f}{_C.RESET}{pc}{pct:>9.1f}%{_C.RESET}\n")
        _w("\n")
    else:
        if _ensure_psutil():
            cpu_pct = _psutil.cpu_percent(interval=0.5)
            _w(f"  {_C.DIM}Load average niedostepny na Windows.{_C.RESET}\n")
            _w(f"  {_C.DIM}Aktualne obciazenie CPU:{_C.RESET} {_bar(cpu_pct)}\n\n")
        else:
            _w(f"  {_C.DIM}Niedostepne na tym systemie.{_C.RESET}\n\n")
            return

    if _ensure_psutil():
        procs = list(_psutil.process_iter(["status"]))
        total    = len(procs)
        running  = sum(1 for p in procs if p.info.get("status") == _psutil.STATUS_RUNNING)
        sleeping = sum(1 for p in procs if p.info.get("status") == _psutil.STATUS_SLEEPING)
        _w(f"  {_C.DIM}Procesy:{_C.RESET}  "
           f"{_C.BWHITE}razem {total}{_C.RESET}  "
           f"{_C.BGREEN}aktywne {running}{_C.RESET}  "
           f"{_C.DIM}spiace {sleeping}{_C.RESET}\n\n")


def _view_env(filtr: str = ""):
    _w(f"\n{_sep(label='  Zmienne Srodowiskowe  ')}")
    env = dict(os.environ)
    if filtr:
        filtr_up = filtr.upper()
        env = {k: v for k, v in env.items() if filtr_up in k.upper() or filtr_up in v.upper()}

    if not env:
        _w(f"  {_C.DIM}Brak wynikow dla filtru: '{filtr}'{_C.RESET}\n\n")
        return

    col_k = min(max((len(k) for k in env), default=20), 32) + 2
    _w(f"  {_C.BOLD}{_C.BWHITE}{'Zmienna':<{col_k}}Wartosc{_C.RESET}\n")
    _w(f"  {_C.BCYAN}{'─' * (_cols() - 6)}{_C.RESET}\n")

    priority = {
        "PATH", "PATHEXT", "HOME", "USER", "USERNAME", "COMPUTERNAME",
        "OS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
        "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA",
        "PROGRAMFILES", "USERPROFILE", "LANG", "SHELL", "TERM",
        "VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "PYTHONPATH",
    }

    def _row(k, v):
        key_c = _C.BYELLOW if k in priority else _C.BCYAN
        val_trunc = v[:80] + ("…" if len(v) > 80 else "")
        k_col = _ansi_pad(f"{key_c}{k}{_C.RESET}", col_k)
        _w(f"  {k_col}{_C.DIM}{val_trunc}{_C.RESET}\n")

    for k in sorted(priority & env.keys()):
        _row(k, env[k])
    _w("\n")
    for k in sorted(k for k in env if k not in priority):
        _row(k, env[k])
    _w(f"\n  {_C.DIM}Lacznie: {len(env)} zmiennych{' (filtr: ' + filtr + ')' if filtr else ''}{_C.RESET}\n\n")


def _view_sched():
    _w(f"\n{_sep(label='  Zaplanowane Zadania  ')}")
    sys_name = platform.system()

    if sys_name == "Windows":
        out = _run_cmd('schtasks /query /fo LIST /v', shell=True, encoding="cp1250")
        if not out.strip():
            _w(f"  {_C.DIM}Brak zaplanowanych zadan lub brak uprawnien.{_C.RESET}\n\n")
            return

        tasks: list = []
        current: dict = {}
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Nazwa zadania:") or line.startswith("TaskName:"):
                if current.get("name"):
                    tasks.append(current)
                current = {"name": line.split(":", 1)[1].strip()}
            elif line.startswith("Status:"):
                current["status"] = line.split(":", 1)[1].strip()
            elif "Nastepne uruchomienie" in line or "Next Run Time" in line:
                current["next"] = line.split(":", 1)[1].strip()
            elif "Ostatnie uruchomienie" in line or "Last Run Time" in line:
                current["last"] = line.split(":", 1)[1].strip()
        if current.get("name"):
            tasks.append(current)
        tasks = [t for t in tasks if t.get("name") and t["name"] not in ("N/A", "")]

        if not tasks:
            _w(f"  {_C.DIM}Brak zaplanowanych zadan lub brak uprawnien.{_C.RESET}\n\n")
            return

        col_n = min(max((len(t["name"]) for t in tasks), default=30), 50) + 2
        _w(f"  {_C.BOLD}{_C.BWHITE}{'Nazwa':<{col_n}}{'Status':<14}{'Nastepne':<22}Ostatnie{_C.RESET}\n")
        _w(f"  {_C.BCYAN}{'─' * (_cols() - 6)}{_C.RESET}\n")
        for t in tasks[:30]:
            status = t.get("status", "?")
            sc = _C.BGREEN if "Gotowe" in status or "Ready" in status else (
                 _C.BYELLOW if "Uruchomione" in status or "Running" in status else _C.DIM)
            name_col   = _ansi_pad(f"{_C.BWHITE}{t['name'][:50]}{_C.RESET}", col_n)
            status_col = _ansi_pad(f"{sc}{status[:12]}{_C.RESET}", 14)
            _w(f"  {name_col}{status_col}{_C.DIM}{t.get('next','?')[:20]:<22}{t.get('last','?')[:20]}{_C.RESET}\n")
        if len(tasks) > 30:
            _w(f"\n  {_C.DIM}... i {len(tasks) - 30} wiecej{_C.RESET}\n")
        _w("\n")

    else:
        found_any = False

        # crontab bieżącego użytkownika
        out = _run_cmd(["crontab", "-l"])
        if out.strip():
            lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]
            if lines:
                _w(f"  {_C.BOLD}{_C.BYELLOW}crontab (biezacy uzytkownik):{_C.RESET}\n")
                for ln in lines:
                    parts = ln.split(None, 5)
                    if len(parts) >= 6:
                        _w(f"  {_C.BCYAN}{' '.join(parts[:5]):<25}{_C.RESET} {_C.DIM}{parts[5][:60]}{_C.RESET}\n")
                    else:
                        _w(f"  {_C.DIM}{ln[:80]}{_C.RESET}\n")
                _w("\n")
                found_any = True

        # /etc/crontab + /etc/cron.d
        for cron_path in ("/etc/crontab", "/etc/cron.d"):
            p = Path(cron_path)
            files = list(p.iterdir()) if p.is_dir() else ([p] if p.exists() else [])
            for f in files:
                try:
                    content = f.read_text(errors="ignore")
                    lines = [ln for ln in content.splitlines()
                             if ln.strip() and not ln.startswith("#") and len(ln.split()) >= 6]
                    if lines:
                        _w(f"  {_C.BOLD}{_C.BYELLOW}{f}:{_C.RESET}\n")
                        for ln in lines[:10]:
                            parts = ln.split(None, 6)
                            _w(f"  {_C.BCYAN}{' '.join(parts[:5]):<25}{_C.RESET} {_C.DIM}{' '.join(parts[5:])[:55]}{_C.RESET}\n")
                        _w("\n")
                        found_any = True
                except (PermissionError, OSError):
                    pass

        # systemd timers
        out = _run_cmd(["systemctl", "list-timers", "--no-pager", "--all"])
        if out.strip():
            timer_lines = [ln for ln in out.splitlines() if ".timer" in ln and "UNIT" not in ln]
            if timer_lines:
                _w(f"  {_C.BOLD}{_C.BYELLOW}systemd timers:{_C.RESET}\n")
                for ln in timer_lines[:15]:
                    _w(f"  {_C.DIM}{ln[:_cols() - 6]}{_C.RESET}\n")
                _w("\n")
                found_any = True

        if not found_any:
            _w(f"  {_C.DIM}Nie znaleziono zadan cron lub brak uprawnien.{_C.RESET}\n\n")


def _view_uptime():
    _w("\n")
    _w(_sep(label="  Uptime  "))
    uptime_sec = 0.0
    if _ensure_psutil():
        try:
            uptime_sec = time.time() - _psutil.boot_time()
        except Exception:
            pass
    else:
        out = _run_cmd("net statistics server", shell=True, encoding="cp1250")
        for line in out.splitlines():
            if "Statystyki od" in line:
                _w(f"  {_C.BOLD}System uruchomiony od:{_C.RESET} {line.split('od')[1].strip()}\n\n")
                return

    if uptime_sec > 0:
        total_min = int(uptime_sec) // 60
        d, remainder = divmod(total_min, 1440)
        h, m = divmod(remainder, 60)
        _w(f"  {_C.BOLD}Uptime:{_C.RESET}  {_C.BGREEN}{d} dni, {h} godz, {m} min{_C.RESET}\n")
        boot_ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - uptime_sec))
        _w(f"  {_C.DIM}Uruchomiony:{_C.RESET}  {boot_ts}\n\n")
    else:
        _w(f"  {_C.RED}[!] Nie udalo sie odczytac uptime.{_C.RESET}\n\n")


def _view_export(filepath: str = ""):
    """Eksportuje rozszerzony snapshot systemu do pliku JSON."""
    _w(f"  {_C.DIM}Zbieranie danych...{_C.RESET}\r")

    cpu  = _get_cpu_info()
    ram  = _get_ram_info()
    disk = _get_disk_info()
    nets = _get_net_info()
    gpus = _get_gpu_info()

    # ── uptime ──
    uptime_sec: float = 0.0
    boot_time_str = ""
    if _ensure_psutil():
        try:
            bt = _psutil.boot_time()
            uptime_sec = time.time() - bt
            boot_time_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(bt))
        except Exception:
            pass

    # ── load average ──
    load_avg: dict = {}
    if hasattr(os, "getloadavg"):
        try:
            la1, la5, la15 = os.getloadavg()
            load_avg = {"1min": round(la1, 2), "5min": round(la5, 2), "15min": round(la15, 2)}
        except Exception:
            pass
    elif _ensure_psutil():
        try:
            pct = _psutil.cpu_percent(interval=0.2)
            load_avg = {"cpu_pct_now": round(pct, 1)}
        except Exception:
            pass

    # ── temperatury wszystkich czujników ──
    temps_all: dict = {}
    if _ensure_psutil():
        try:
            for chip, entries in (_psutil.sensors_temperatures() or {}).items():
                temps_all[chip] = [
                    {"label": e.label or chip, "current": e.current,
                     "high": e.high, "critical": e.critical}
                    for e in entries
                ]
        except Exception:
            pass

    # ── top 5 procesów CPU ──
    top_procs: list = []
    if _ensure_psutil():
        try:
            for p in _psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    top_procs.append({
                        "pid":  p.info["pid"],
                        "name": p.info["name"] or "?",
                        "cpu":  round(p.info.get("cpu_percent") or 0.0, 1),
                        "ram":  round(p.info.get("memory_percent") or 0.0, 2),
                    })
                except Exception:
                    pass
            top_procs = sorted(top_procs, key=lambda x: x["cpu"], reverse=True)[:5]
        except Exception:
            pass

    # ── adresy sieciowe ──
    net_addrs: dict = {}
    if _ensure_psutil():
        try:
            for iface, addrs in _psutil.net_if_addrs().items():
                ipv4 = [a.address for a in addrs if a.family == 2]
                ipv6 = [a.address.split("%")[0] for a in addrs if a.family == 10]
                if ipv4 or ipv6:
                    net_addrs[_clean_iface(iface)] = {"ipv4": ipv4, "ipv6": ipv6}
        except Exception:
            pass

    # ── liczba otwartych połączeń ──
    open_conns: dict = {"listen": 0, "established": 0, "total": 0}
    if _ensure_psutil():
        try:
            for c in _psutil.net_connections(kind="inet"):
                open_conns["total"] += 1
                if c.status == "LISTEN":
                    open_conns["listen"] += 1
                elif c.status == "ESTABLISHED":
                    open_conns["established"] += 1
        except Exception:
            pass

    snapshot = {
        "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%S"),
        "monitor_ver": "1.4",
        "system": {
            "os":        platform.system(),
            "release":   platform.release(),
            "version":   platform.version(),
            "machine":   platform.machine(),
            "hostname":  platform.node(),
            "python":    platform.python_version(),
            "boot_time": boot_time_str,
            "uptime_sec": round(uptime_sec, 0),
        },
        "load_average": load_avg,
        "cpu": {
            "name":       cpu.get("name", "?"),
            "cores_phys": cpu.get("count_phy"),
            "cores_log":  cpu.get("count_log"),
            "total_pct":  round(cpu.get("total", -1), 1),
            "per_core":   [round(p, 1) for p in cpu.get("per_core", [])],
            "freq_cur_mhz": cpu.get("freq_cur"),
            "freq_max_mhz": cpu.get("freq_max"),
            "temp_c":     cpu.get("temp"),
        },
        "ram": {
            "total":    ram.get("total", 0),
            "used":     ram.get("used", 0),
            "free":     ram.get("free", 0),
            "percent":  round(ram.get("percent", 0), 1),
            "swap_total":   ram.get("sw_total", 0),
            "swap_used":    ram.get("sw_used", 0),
            "swap_percent": round(ram.get("sw_pct", 0), 1),
        },
        "disks": [
            {
                "device":     d.get("device", "?"),
                "mountpoint": d["mountpoint"],
                "fstype":     d.get("fstype", "?"),
                "total":      d["total"],
                "used":       d["used"],
                "free":       d.get("free", 0),
                "percent":    round(d["percent"], 1),
            }
            for d in disk
        ],
        "network": {
            "interfaces": {_clean_iface(k): v for k, v in nets.items()},
            "addresses":  net_addrs,
            "connections": open_conns,
        },
        "gpu": [
            {
                "name":     g["name"],
                "type":     g.get("type", "?"),
                "ram_gb":   g.get("ram", 0),
                "load_pct": g.get("load"),
                "temp_c":   g.get("temp"),
                "mem_used_gb": g.get("mem_used"),
            }
            for g in gpus
        ],
        "temperatures": temps_all,
        "top_processes_cpu": top_procs,
    }

    # Walidacja/normalizacja ścieżki
    if not filepath:
        ts = time.strftime("%Y%m%d_%H%M%S")
        filepath = f"mon_snapshot_{ts}.json"
    elif not filepath.lower().endswith(".json"):
        filepath += ".json"

    out_path = Path(filepath)
    try:
        content = json.dumps(snapshot, indent=2, ensure_ascii=False)
        out_path.write_text(content, encoding="utf-8")
        file_sz = out_path.stat().st_size
        abs_path = str(out_path.resolve())

        _w(f"\n  {_C.BGREEN}✔  Snapshot zapisany:{_C.RESET}\n")
        _w(f"  {_C.DIM}{'Plik':<14}{_C.RESET}{_C.BWHITE}{abs_path}{_C.RESET}\n")
        _w(f"  {_C.DIM}{'Rozmiar':<14}{_C.RESET}{_C.DIM}{_fmt_bytes(file_sz)}{_C.RESET}\n")
        _w(f"  {_C.DIM}{'Sekcje':<14}{_C.RESET}{_C.DIM}"
           f"system · cpu · ram · dyski · siec · gpu · temperatury · procesy"
           f"{_C.RESET}\n\n")
    except OSError as e:
        _w(f"\n  {_C.RED}[!] Blad zapisu: {e}{_C.RESET}\n\n")


def _view_configtui():
    """Główny dashboard — CPU + GPU + RAM + Dysk + Sieć."""
    cpu  = _get_cpu_info()
    ram  = _get_ram_info()
    disk = _get_disk_info()
    nets = _get_net_info()

    # aktualizuj historię CPU
    global _cpu_history
    total_pct = cpu.get("total", -1)
    if total_pct >= 0:
        _cpu_history.append(total_pct)
        if len(_cpu_history) > 60:
            _cpu_history = _cpu_history[-60:]

    uname = platform.uname()
    now   = time.strftime("%Y-%m-%d  %H:%M:%S")
    _w("\n")

    w = _cols()
    pad    = max(0, (w - 36) // 2)
    border = "─" * (w - 4)
    _w(f"  {_C.BOLD}{_C.BCYAN}╭{border}╮{_C.RESET}\n")
    _w(f"  {_C.BOLD}{_C.BCYAN}│{_C.RESET}{'':>{pad}}{_C.BOLD}{_C.BWHITE}📊  CrossTerm Monitor v1.4{_C.RESET}"
       f"  {_C.DIM}{now}{_C.RESET}{'':<{pad}}{_C.BOLD}{_C.BCYAN}║{_C.RESET}\n")
    _w(f"  {_C.BOLD}{_C.BCYAN}╰{border}╯{_C.RESET}\n\n")

    _w(f"  {_C.DIM}🖥  Host  {_C.RESET}{_C.BWHITE}{uname.node}{_C.RESET}"
       f"   {_C.DIM}⚙  OS  {_C.RESET}{_C.BWHITE}{uname.system} {uname.release}{_C.RESET}\n\n")

    # ── CPU ──
    cpu_pct  = cpu.get("total", -1)
    cpu_name = cpu.get("name", "?")
    lc = cpu.get("count_log", "?")
    _w(f"  {_C.BOLD}{_C.BCYAN}▌{_C.BYELLOW} CPU  {_C.RESET}{_C.DIM}{cpu_name[:42]}{_C.RESET}\n")
    if cpu_pct >= 0:
        spark = _sparkline(_cpu_history, width=20)
        _w(f"       {_bar(cpu_pct)}  {_C.DIM}{lc} watkow{_C.RESET}  {_C.BCYAN}{spark}{_C.RESET}\n")
    temp = cpu.get("temp")
    if temp is not None:
        tc = _C.BGREEN if temp < 65 else (_C.BYELLOW if temp < 80 else _C.BRED)
        _w(f"       {_C.DIM}🌡  Temp  {_C.RESET}{tc}{temp:.1f} °C{_C.RESET}\n")
    _w("\n")

    # ── GPU ──
    gpus = _get_gpu_info()
    if gpus:
        for g in gpus[:2]:
            _w(f"  {_C.BOLD}{_C.BCYAN}▌{_C.BYELLOW} GPU  {_C.RESET}{_C.DIM}{g['name'][:42]}{_C.RESET}\n")
            if g['load'] is not None:
                temp_str = (f"  {_C.DIM}🌡 {g['temp']:.0f} °C{_C.RESET}"
                            if g.get('temp') is not None else "")
                _w(f"       {_bar(g['load'])}{temp_str}\n")
            elif g.get('mem_used') is not None:
                ram_g = g.get('ram', 0)
                mem_pct = (g['mem_used'] / ram_g) * 100 if ram_g > 0 else 0
                _w(f"       {_bar(mem_pct, width=14)}  {_C.DIM}{g['mem_used']:.1f} GB{_C.RESET}\n")
            elif g.get('ram', 0) > 0:
                _w(f"       {_C.DIM}VRAM  {_C.RESET}{_C.BCYAN}{g['ram']:.1f} GB{_C.RESET}\n")
        _w("\n")

    # ── RAM ──
    if ram:
        _w(f"  {_C.BOLD}{_C.BCYAN}▌{_C.BYELLOW} RAM  {_C.RESET}{_bar(ram['percent'])}  "
           f"{_C.DIM}{_fmt_bytes(ram['used'])} / {_fmt_bytes(ram['total'])}{_C.RESET}\n")
        if ram.get("sw_total", 0) > 0:
            _w(f"  {_C.BCYAN}▌{_C.RESET}  {_C.DIM}Swap {_C.RESET}{_bar(ram['sw_pct'], width=14)}  "
               f"{_C.DIM}{_fmt_bytes(ram['sw_used'])} / {_fmt_bytes(ram['sw_total'])}{_C.RESET}\n")
    _w("\n")

    # ── Dyski (max 4) ──
    if disk:
        _w(f"  {_C.BOLD}{_C.BCYAN}▌{_C.BYELLOW} DYSKI{_C.RESET}\n")
        for p in disk[:4]:
            _w(f"    {_C.BWHITE}{p['mountpoint']:<16}{_C.RESET}"
               f"{_bar(p['percent'], width=14)}  "
               f"{_C.DIM}{_fmt_bytes(p['used'])} / {_fmt_bytes(p['total'])}{_C.RESET}\n")
        _w("\n")

    # ── Sieć ──
    if nets:
        nets_clean = {_clean_iface(k): v for k, v in nets.items()}
        col_iface = max((len(n) for n in nets_clean), default=14) + 2
        _w(f"  {_C.BOLD}{_C.BCYAN}▌{_C.BYELLOW} SIEC{_C.RESET}\n")
        for iface, cnt in list(nets_clean.items())[:4]:
            c_iface = _ansi_pad(f"{_C.BCYAN}{iface}{_C.RESET}", col_iface)
            _w(f"    {c_iface}"
               f"  {_C.DIM}⬇ DN{_C.RESET} {_C.BGREEN}{_fmt_bytes(cnt['bytes_recv']):<14}{_C.RESET}"
               f"  {_C.DIM}⬆ UP{_C.RESET} {_C.BYELLOW}{_fmt_bytes(cnt['bytes_sent'])}{_C.RESET}\n")
        _w("\n")

    if not _ensure_psutil():
        _w(f"  {_C.DIM}💡 Zainstaluj psutil: {_C.RESET}{_C.BYELLOW}pip install psutil{_C.RESET}\n\n")


def _view_watch(interval: float = 2.0, terminal=None):
    _w("\x1b[?25l")
    try:
        while True:
            _w("\x1b[2J\x1b[H")
            _view_configtui()
            _w(f"\n  {_C.DIM}⟳  Odswiezanie co {interval}s  ·  Ctrl+C aby wyjsc{_C.RESET}")
            time.sleep(interval)
    except KeyboardInterrupt:
        _w(f"\n\n  {_C.DIM}■  Monitor zatrzymany.{_C.RESET}\n\n")
    finally:
        _w("\x1b[?25h")


# ─── dispatcher ───────────────────────────────────────────────────────────────

def _view_diff(path_a: str, path_b: str):
    """Porównuje dwa snapshoty JSON z 'mon export' i wyświetla różnice."""
    _w("\n")

    def _load(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            return {}

    a = _load(path_a)
    b = _load(path_b)

    if not a:
        _w(f"  {_C.RED}[!] Nie mozna wczytac: {path_a}{_C.RESET}\n\n"); return
    if not b:
        _w(f"  {_C.RED}[!] Nie mozna wczytac: {path_b}{_C.RESET}\n\n"); return

    ts_a = a.get("timestamp", "?")
    ts_b = b.get("timestamp", "?")
    _w(_sep(label="  Diff snapshotow  "))
    _w(f"  {_C.DIM}A:{_C.RESET} {_C.BWHITE}{Path(path_a).name}{_C.RESET}  {_C.DIM}{ts_a}{_C.RESET}\n")
    _w(f"  {_C.DIM}B:{_C.RESET} {_C.BWHITE}{Path(path_b).name}{_C.RESET}  {_C.DIM}{ts_b}{_C.RESET}\n\n")

    def _delta_str(va, vb, unit: str = "", fmt=None) -> str:
        """Formatuje zmianę wartości numerycznej z kolorem i strzałką."""
        try:
            fa, fb = float(va), float(vb)
        except (TypeError, ValueError):
            if va != vb:
                return f"{_C.BYELLOW}{va!r} → {vb!r}{_C.RESET}"
            return f"{_C.DIM}{va!r}{_C.RESET}"
        d = fb - fa
        if abs(d) < 0.05:
            color = _C.DIM; arrow = "="
        elif d > 0:
            color = _C.BYELLOW; arrow = "▲"
        else:
            color = _C.BGREEN; arrow = "▼"
        v_str = fmt(fb) if fmt else f"{fb:.1f}{unit}"
        d_str = fmt(abs(d)) if fmt else f"{abs(d):.1f}{unit}"
        return f"{color}{arrow} {v_str}  (Δ {d_str}){_C.RESET}"

    def _row(label: str, val_str: str):
        _w(f"  {_C.DIM}{label:<28}{_C.RESET} {val_str}\n")

    # ── CPU ──
    ca, cb = a.get("cpu", {}), b.get("cpu", {})
    _w(f"  {_C.BOLD}{_C.BCYAN}CPU{_C.RESET}\n")
    _row("Obciążenie %",   _delta_str(ca.get("total_pct"), cb.get("total_pct"), "%"))
    if ca.get("temp_c") is not None or cb.get("temp_c") is not None:
        _row("Temperatura °C", _delta_str(ca.get("temp_c", 0), cb.get("temp_c", 0), "°C"))
    freq_a = ca.get("freq_cur_mhz"); freq_b = cb.get("freq_cur_mhz")
    if freq_a and freq_b:
        _row("Częstotliwość MHz", _delta_str(freq_a, freq_b, " MHz"))
    _w("\n")

    # ── RAM ──
    ra, rb = a.get("ram", {}), b.get("ram", {})
    _w(f"  {_C.BOLD}{_C.BCYAN}RAM{_C.RESET}\n")
    _row("Użycie %",      _delta_str(ra.get("percent"), rb.get("percent"), "%"))
    _row("Użyte",         _delta_str(ra.get("used", 0), rb.get("used", 0), fmt=_fmt_bytes))
    if ra.get("swap_total", 0) or rb.get("swap_total", 0):
        _row("Swap %",    _delta_str(ra.get("swap_percent", 0), rb.get("swap_percent", 0), "%"))
    _w("\n")

    # ── Dyski ──
    da = {d["mountpoint"]: d for d in a.get("disks", [])}
    db = {d["mountpoint"]: d for d in b.get("disks", [])}
    all_mounts = sorted(set(da) | set(db))
    if all_mounts:
        _w(f"  {_C.BOLD}{_C.BCYAN}Dyski{_C.RESET}\n")
        for mp in all_mounts:
            if mp in da and mp in db:
                _row(f"  {mp} użycie %",
                     _delta_str(da[mp].get("percent"), db[mp].get("percent"), "%"))
                _row(f"  {mp} użyte",
                     _delta_str(da[mp].get("used", 0), db[mp].get("used", 0),
                                fmt=_fmt_bytes))
            elif mp in db:
                _row(f"  {mp}", f"{_C.BGREEN}[nowy]{_C.RESET}")
            else:
                _row(f"  {mp}", f"{_C.DIM}[usunieto]{_C.RESET}")
        _w("\n")

    # ── Sieć — bajty przesłane ──
    na = a.get("network", {}).get("interfaces", {})
    nb = b.get("network", {}).get("interfaces", {})
    all_ifaces = sorted(set(na) | set(nb))
    if all_ifaces:
        _w(f"  {_C.BOLD}{_C.BCYAN}Siec{_C.RESET}\n")
        for iface in all_ifaces:
            if iface in na and iface in nb:
                rx_d = nb[iface].get("bytes_recv", 0) - na[iface].get("bytes_recv", 0)
                tx_d = nb[iface].get("bytes_sent", 0) - na[iface].get("bytes_sent", 0)
                rx_c = _C.BGREEN if rx_d >= 0 else _C.BYELLOW
                tx_c = _C.BYELLOW if tx_d >= 0 else _C.BGREEN
                _row(f"  {iface}",
                     f"{_C.DIM}⬇{_C.RESET} {rx_c}+{_fmt_bytes(max(0, rx_d))}{_C.RESET}"
                     f"  {_C.DIM}⬆{_C.RESET} {tx_c}+{_fmt_bytes(max(0, tx_d))}{_C.RESET}")
        _w("\n")

    # ── Load average ──
    la, lb = a.get("load_average", {}), b.get("load_average", {})
    if la or lb:
        _w(f"  {_C.BOLD}{_C.BCYAN}Load Average{_C.RESET}\n")
        for key in ("1min", "5min", "15min"):
            if key in la or key in lb:
                _row(f"  {key}", _delta_str(la.get(key, 0), lb.get(key, 0)))
        _w("\n")

    _w(f"  {_C.DIM}Snapshot A: {ts_a}   →   Snapshot B: {ts_b}{_C.RESET}\n\n")


# ─── progi alertów ────────────────────────────────────────────────────────────

_ALERT_DEFAULTS = {
    "cpu":      85.0,   # %
    "ram":      90.0,   # %
    "swap":     80.0,   # %
    "disk":     90.0,   # %
    "temp_cpu": 80.0,   # °C
    "temp_gpu": 85.0,   # °C
}

_alert_thresholds: dict = dict(_ALERT_DEFAULTS)


def _view_alert(args_rest: list):
    """
    mon alert           — sprawdź system vs progi i wyświetl raport
    mon alert set <k> <v> — ustaw próg (np. mon alert set cpu 90)
    mon alert reset     — przywróć domyślne progi
    mon alert show      — pokaż aktualne progi
    """
    _w("\n")
    sub = args_rest[0].lower() if args_rest else ""

    if sub == "set":
        if len(args_rest) < 3:
            _w(f"  {_C.RED}[!] Uzycie: mon alert set <klucz> <wartosc>{_C.RESET}\n")
            _w(f"  {_C.DIM}Klucze: {', '.join(_ALERT_DEFAULTS)}{_C.RESET}\n\n")
            return
        key, val_s = args_rest[1].lower(), args_rest[2]
        if key not in _alert_thresholds:
            _w(f"  {_C.RED}[!] Nieznany klucz: '{key}'{_C.RESET}\n")
            _w(f"  {_C.DIM}Dostepne: {', '.join(_alert_thresholds)}{_C.RESET}\n\n")
            return
        try:
            val = float(val_s)
        except ValueError:
            _w(f"  {_C.RED}[!] Wartosc musi byc liczba.{_C.RESET}\n\n")
            return
        _alert_thresholds[key] = val
        _w(f"  {_C.BGREEN}✔  Prog '{key}' ustawiony na {val}{_C.RESET}\n\n")
        return

    if sub == "reset":
        _alert_thresholds.clear()
        _alert_thresholds.update(_ALERT_DEFAULTS)
        _w(f"  {_C.BGREEN}✔  Progi przywrocone do domyslnych.{_C.RESET}\n\n")
        return

    if sub == "show":
        _w(_sep(label="  Progi Alertow  "))
        for k, v in _alert_thresholds.items():
            dflt = _ALERT_DEFAULTS.get(k, "?")
            changed = f"  {_C.BYELLOW}(zmieniony z {dflt}){_C.RESET}" if v != dflt else ""
            unit = "°C" if "temp" in k else "%"
            _w(f"  {_C.BWHITE}{k:<16}{_C.RESET}{_C.BCYAN}{v}{unit}{_C.RESET}{changed}\n")
        _w("\n")
        return

    # ── Domyślne: sprawdź system i wyświetl raport ──
    _w(_sep(label="  Raport Alertow  "))

    alerts: list = []   # (poziom, kategoria, komunikat)
    ok_list: list = []

    def _chk(label: str, val: float | None, thresh_key: str, unit: str, fmt=None):
        if val is None:
            return
        thresh = _alert_thresholds.get(thresh_key, 999.0)
        val_s  = fmt(val) if fmt else f"{val:.1f}{unit}"
        if val >= thresh:
            diff = val - thresh
            diff_s = fmt(diff) if fmt else f"+{diff:.1f}{unit}"
            alerts.append(("WARN", label, f"{val_s}  (prog: {thresh}{unit}  przekroczono o {diff_s})"))
        else:
            margin = thresh - val
            margin_s = fmt(margin) if fmt else f"{margin:.1f}{unit}"
            ok_list.append((label, f"{val_s}  {_C.DIM}(margin do progu: {margin_s}){_C.RESET}"))

    # CPU
    cpu  = _get_cpu_info()
    _chk("CPU obciazenie",  cpu.get("total"),  "cpu",      "%")
    _chk("CPU temperatura", cpu.get("temp"),   "temp_cpu", "°C")

    # RAM
    ram = _get_ram_info()
    _chk("RAM",             ram.get("percent"),    "ram",  "%")
    _chk("Swap",            ram.get("sw_pct"),     "swap", "%")

    # Dyski
    for d in _get_disk_info():
        _chk(f"Dysk {d['mountpoint']}", d.get("percent"), "disk", "%")

    # Temperatury GPU
    for g in _get_gpu_info():
        if g.get("temp") is not None:
            _chk(f"GPU {g['name'][:20]} temp", g["temp"], "temp_gpu", "°C")

    # Wyświetl alerty
    if alerts:
        _w(f"  {_C.BRED}⚠  PRZEKROCZONE PROGI ({len(alerts)}):{_C.RESET}\n\n")
        for lvl, label, msg in alerts:
            _w(f"  {_C.BRED}▶  {label:<24}{_C.RESET} {_C.BYELLOW}{msg}{_C.RESET}\n")
        _w("\n")
    else:
        _w(f"  {_C.BGREEN}✔  Wszystkie wskazniki w normie.{_C.RESET}\n\n")

    if ok_list:
        _w(f"  {_C.DIM}Wskazniki OK:{_C.RESET}\n")
        for label, msg in ok_list:
            _w(f"  {_C.BGREEN}  ✓  {label:<24}{_C.RESET} {msg}\n")
        _w("\n")

    _w(f"  {_C.DIM}Zmien progi: mon alert set <klucz> <wartosc>  ·  "
       f"Podglad progow: mon alert show{_C.RESET}\n\n")



    """Zwraca najbliższą komendę do podanej — prosta odległość Levenshteina."""
    known = [
        "cpu", "gpu", "ram", "disk", "net", "netspeed", "top", "watch",
        "temp", "load", "env", "sched", "proc", "ports", "runner",
        "kill", "kill9", "battery", "uptime", "serial", "usb", "audio",
        "info", "export", "diff", "alert",
    ]
    def _lev(a: str, b: str) -> int:
        if len(a) < len(b):
            return _lev(b, a)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1,
                                prev[j] + (0 if ca == cb else 1)))
            prev = curr
        return prev[-1]

    best, best_d = None, 99
    for k in known:
        d = _lev(sub, k)
        if d < best_d:
            best, best_d = k, d
    return best if best_d <= 3 else ""


def _fuzzy_cmd_hint(sub: str) -> str:
    """Zwraca najbliższą komendę do podanej — prosta odległość Levenshteina."""
    known = [
        "cpu", "gpu", "ram", "disk", "net", "netspeed", "top", "watch",
        "temp", "load", "env", "sched", "proc", "ports", "runner",
        "kill", "kill9", "battery", "uptime", "serial", "usb", "audio",
        "info", "export", "diff", "alert",
    ]
    def _lev(a: str, b: str) -> int:
        if len(a) < len(b):
            return _lev(b, a)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1,
                                prev[j] + (0 if ca == cb else 1)))
            prev = curr
        return prev[-1]

    best, best_d = None, 99
    for k in known:
        d = _lev(sub, k)
        if d < best_d:
            best, best_d = k, d
    return best if best_d <= 3 else ""


def cmd_mon(args: list, terminal):
    """Dispatcher komend monitora systemu."""
    if not args:
        _view_configtui()
        return

    sub = args[0].lower()

    if sub == "cpu":
        if len(args) > 1 and args[1].lower() == "hist":
            _view_cpu_hist()
        else:
            _view_cpu(detailed=True)

    elif sub == "gpu":
        _view_gpu()

    elif sub == "ram":
        _view_ram()

    elif sub == "disk":
        if len(args) > 1 and args[1].lower() == "clean":
            path = args[2] if len(args) > 2 else "."
            try:
                top_n = int(args[3]) if len(args) > 3 else 15
                top_n = max(1, min(top_n, 100))
            except ValueError:
                top_n = 15
            if path == ".":
                _w(f"  {_C.DIM}Brak sciezki — skanowanie biezacego katalogu: "
                   f"{_C.RESET}{_C.BYELLOW}{Path('.').resolve()}{_C.RESET}\n")
            _view_disk_clean(path, top_n)
        else:
            _view_disk(args[1] if len(args) > 1 else None)

    elif sub == "net":
        _view_net()

    elif sub == "netspeed":
        try:
            s = float(args[1]) if len(args) > 1 else 1.0
        except ValueError:
            _w(f"  {_C.RED}[!] Interval musi byc liczba (np. 0.5 lub 2).{_C.RESET}\n\n")
            return
        if s <= 0:
            _w(f"  {_C.RED}[!] Interval musi byc wiekszy niz 0.{_C.RESET}\n\n")
            return
        if s > 60:
            _w(f"  {_C.BYELLOW}[!] Interval ograniczony do 60s.{_C.RESET}\n")
            s = 60.0
        _view_netspeed(s)

    elif sub == "top":
        if len(args) > 1 and args[1].lower() == "disk":
            try:
                n = int(args[2]) if len(args) > 2 else 10
            except ValueError:
                n = 10
            _view_top_disk(max(1, min(n, 50)))
        else:
            sort_by = "ram" if "ram" in [a.lower() for a in args] else "cpu"
            try:
                n = int(args[-1]) if args[-1].isdigit() else 10
            except (ValueError, IndexError):
                n = 10
            _view_top(max(1, min(n, 50)), sort_by)

    elif sub == "watch":
        try:
            s = float(args[1]) if len(args) > 1 else 2.0
        except ValueError:
            _w(f"  {_C.RED}[!] Interval musi byc liczba (np. 1 lub 5).{_C.RESET}\n\n")
            return
        if s <= 0:
            _w(f"  {_C.RED}[!] Interval musi byc wiekszy niz 0.{_C.RESET}\n\n")
            return
        if s > 300:
            _w(f"  {_C.BYELLOW}[!] Interval ograniczony do 300s.{_C.RESET}\n")
            s = 300.0
        _view_watch(s, terminal)

    elif sub == "temp":   _view_temp()
    elif sub == "load":   _view_load()

    elif sub == "env":
        _view_env(args[1] if len(args) > 1 else "")

    elif sub == "sched":  _view_sched()

    elif sub == "proc":
        if len(args) < 2:
            _w(f"\n  {_C.RED}[!] Brak argumentu.{_C.RESET}\n")
            _w(f"  {_C.DIM}Uzycie:  mon proc <nazwa>   lub   mon proc <pid>{_C.RESET}\n")
            _w(f"  {_C.DIM}Przyklad: mon proc python    lub   mon proc 1234{_C.RESET}\n\n")
        else:
            _view_proc(args[1])

    elif sub == "ports":
        _view_ports(args[1] if len(args) > 1 else "")

    elif sub == "runner":
        _view_runner(terminal)

    elif sub == "kill":
        if len(args) < 2:
            _w(f"\n  {_C.RED}[!] Brak PID.{_C.RESET}\n")
            _w(f"  {_C.DIM}Uzycie:  mon kill <pid>{_C.RESET}\n")
            _w(f"  {_C.DIM}Znajdz PID: mon top   lub   mon proc <nazwa>{_C.RESET}\n\n")
        else:
            _cmd_mon_kill(args[1], force=False)

    elif sub == "kill9":
        if len(args) < 2:
            _w(f"\n  {_C.RED}[!] Brak PID.{_C.RESET}\n")
            _w(f"  {_C.DIM}Uzycie:  mon kill9 <pid>{_C.RESET}\n")
            _w(f"  {_C.DIM}Uwaga: SIGKILL nie pozwala procesowi na sprzatanie zasobow.{_C.RESET}\n\n")
        else:
            _cmd_mon_kill(args[1], force=True)

    elif sub == "battery": _view_battery()
    elif sub == "uptime":  _view_uptime()

    elif sub == "serial":
        if len(args) > 1 and args[1].lower() == "term":
            if len(args) < 3:
                _w(f"\n  {_C.RED}[!] Brak nazwy portu.{_C.RESET}\n")
                _w(f"  {_C.DIM}Uzycie:  mon serial term <port>{_C.RESET}\n")
                _w(f"  {_C.DIM}Porty:   mon serial{_C.RESET}\n\n")
            else:
                _serial_terminal(args[2])
        else:
            _view_serial()

    elif sub == "usb":    _view_usb()
    elif sub == "audio":  _view_audio()
    elif sub == "info":   _view_hw_info()

    elif sub == "export":
        _view_export(args[1] if len(args) > 1 else "")

    elif sub == "diff":
        if len(args) < 3:
            _w(f"\n  {_C.RED}[!] Brak sciezek do snapshotow.{_C.RESET}\n")
            _w(f"  {_C.DIM}Uzycie: mon diff <snapshot_A.json> <snapshot_B.json>{_C.RESET}\n")
            _w(f"  {_C.DIM}Tworzenie snapshotu: mon export{_C.RESET}\n\n")
        else:
            _view_diff(args[1], args[2])

    elif sub == "alert":
        _view_alert(args[1:])

    else:
        hint = _fuzzy_cmd_hint(sub)
        _w(f"\n  {_C.RED}[!] Nieznana podkomenda: '{sub}'{_C.RESET}\n")
        if hint:
            _w(f"  {_C.DIM}Czy chodziło o: {_C.RESET}{_C.BYELLOW}mon {hint}{_C.RESET}?\n")
        _w(f"  {_C.DIM}Pelna lista komend: {_C.RESET}{_C.BYELLOW}mon{_C.RESET}\n\n")


def cmd_monitor(args: list, terminal):
    """Alias → mon."""
    cmd_mon(args, terminal)


# ─── CML_COMMANDS ─────────────────────────────────────────────────────────────

CML_COMMANDS = {
    "mon":     cmd_mon,
    "monitor": cmd_monitor,
}


# ─── menu CML ─────────────────────────────────────────────────────────────────

def cml_menu():
    w = _cols()
    border = "─" * (w - 4)
    _w(f"\n  {_C.BOLD}{_C.BCYAN}╭{border}╮{_C.RESET}\n")
    _w(f"  {_C.BOLD}{_C.BCYAN}│{_C.RESET}  {_C.BOLD}{_C.BWHITE}📊  Moduł: Monitor  v1.5{_C.RESET}"
       f"{'':>{w - 30}}{_C.BOLD}{_C.BCYAN}║{_C.RESET}\n")
    _w(f"  {_C.BOLD}{_C.BCYAN}╰{border}╯{_C.RESET}\n\n")

    groups = [
        ("PRZEGLĄD", [
            ("mon",                      "Pełny dashboard  (CPU · GPU · RAM · Dysk · Sieć)"),
            ("mon watch [s]",            "Live dashboard, odświeżanie co s sekund  [domyślnie 2]"),
            ("mon export [plik]",        "Eksport snapshotu systemu do JSON"),
            ("mon diff <A.json> <B.json>","Porównanie dwóch snapshotów  (Δ CPU · RAM · Dysk · Sieć)"),
            ("mon alert",                "Raport alertów  — sprawdź system vs progi"),
            ("mon alert set <k> <v>",    "Ustaw próg  (cpu · ram · swap · disk · temp_cpu · temp_gpu)"),
            ("mon alert show",           "Pokaż aktualne progi"),
        ]),
        ("KOMPONENTY", [
            ("mon cpu",               "Szczegóły CPU + każdy rdzeń osobno"),
            ("mon cpu hist",          "Historia obciążenia CPU  (sparkline)"),
            ("mon gpu",               "Karta graficzna  (obciążenie · temp · VRAM)"),
            ("mon ram",               "Pamięć RAM i swap"),
            ("mon disk",              "Wszystkie partycje"),
            ("mon disk <ścieżka>",    "Użycie konkretnej ścieżki / dysku"),
            ("mon disk clean <kat> [n]","Top N największych plików/katalogów  [domyślnie 15]"),
            ("mon net",               "Statystyki interfejsów sieciowych"),
            ("mon netspeed [s]",      "Prędkość sieci live  (RX/TX MB/s)  [domyślnie 1s]"),
            ("mon temp",              "Wszystkie czujniki temperatury"),
        ]),
        ("PROCESY", [
            ("mon top [n]",           "Top N procesów wg CPU  [domyślnie 10]"),
            ("mon top ram [n]",       "Top N procesów wg RAM"),
            ("mon top disk [n]",      "Top N procesów wg I/O dysku"),
            ("mon proc <nazwa|pid>",  "Szczegóły konkretnego procesu"),
            ("mon ports [filtr]",     "Otwarte porty sieciowe  (opcjonalny filtr)"),
            ("mon kill <pid>",        "Zakończ proces  (SIGTERM)"),
            ("mon kill9 <pid>",       "Wymuś zakończenie procesu  (SIGKILL)"),
        ]),
        ("SYSTEM", [
            ("mon uptime",            "Czas od uruchomienia systemu"),
            ("mon load",              "Load average systemu  (1/5/15 min)"),
            ("mon env [filtr]",       "Zmienne środowiskowe  (opcjonalny filtr)"),
            ("mon sched",             "Zaplanowane zadania  (cron / Task Scheduler)"),
            ("mon battery",           "Status baterii laptopa"),
            ("mon runner",            "Status skryptów z modułu Script Runner"),
        ]),
        ("SPRZĘT", [
            ("mon serial",            "Porty COM / Serial"),
            ("mon serial term <port>","Prosty terminal szeregowy (9600 baud)"),
            ("mon usb",               "Lista urządzeń USB"),
            ("mon audio",             "Urządzenia dźwiękowe"),
            ("mon info",              "Szczegółowe dane o sprzęcie  (BIOS · CPU · OS)"),
        ]),
    ]

    for group_name, cmds in groups:
        _w(f"  {_C.BOLD}{_C.BCYAN}  {group_name}{_C.RESET}\n")
        _w(f"  {_C.DIM}  {'─' * (w - 8)}{_C.RESET}\n")
        for c, d in cmds:
            _w(f"  {_C.BYELLOW}  {c:<32}{_C.RESET} {_C.DIM}{d}{_C.RESET}\n")
        _w("\n")

    if not _ensure_psutil():
        _w(f"  {_C.BYELLOW}  ⚠  psutil nie jest zainstalowany — część funkcji niedostępna.{_C.RESET}\n")
        _w(f"     {_C.DIM}Instalacja:{_C.RESET}  {_C.BYELLOW}pip install psutil{_C.RESET}\n\n")


# ─── on_load ──────────────────────────────────────────────────────────────────

def on_load():
    pass  # komunikat startowy wyciszony


# ── EcoSystem integration ─────────────────────────────────────────────────────

def setup(terminal):
    """Rejestruje komendę 'monitor' i alias 'mon' w TerminalX EcoSystem."""
    _t = terminal.t

    def _mon(args, terminal=terminal):
        if not args:
            cml_menu()
            return
        cmd_mon(args, terminal)

    terminal.register_command(
        "monitor", _mon,
        description=_t("cmd_monitor"),
        category=_t("cat_ecosystem"),
    )
    terminal.register_command(
        "mon", _mon,
        description=_t("cmd_monitor_alias"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal):
    """Wyrejestrowuje komendy monitora z TerminalX EcoSystem."""
    for cmd in ("monitor", "mon"):
        terminal.commands.pop(cmd, None)
