#!/usr/bin/env python3
# autor:   Sebastian Januchowski
# company: polsoft.ITS(TM) Group
# github:  https://github.com/seb07uk
# email:   polsoft.its@fastservice.com
# crossterm: {"id": "30", "description": "Skaner urządzeń WiFi w sieci lokalnej", "version": "1.4.0", "author": "crossterm-module", "aliases": ["wifi", "wscan"]}
"""
WiFi Scanner — moduł CrossTerm  v1.4
Wykrywa urządzenia w sieci lokalnej.

Metody skanowania (auto-wybór wg uprawnień):
  1. ARP sweep  — root/admin, Linux/Windows  (najszybsza, ~1-3s dla /24)
  2. Raw ICMP   — root/admin, Linux/Mac       (szybka, ~2-4s dla /24)
  3. Subprocess ping — fallback bez root      (wolna, ~5-15s dla /24)

Działa na Windows, Linux i macOS bez zewnętrznych zależności.
"""

from __future__ import annotations

import os
import sys
import platform
import subprocess
import socket
import struct
import select
import re
import threading
import time
import ipaddress
from typing import Optional

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS   = platform.system() == "Darwin"
IS_LINUX   = platform.system() == "Linux"

# ── Sprawdzenie uprawnień root/admin ──────────────────────────────────────────

def _is_root() -> bool:
    """True jeśli proces ma uprawnienia root (Linux/Mac) lub Administrator (Windows)."""
    try:
        if IS_WINDOWS:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        else:
            return os.geteuid() == 0
    except Exception:
        return False

# ── ANSI ──────────────────────────────────────────────────────────────────────

class _A:
    RESET   = "\x1b[0m"
    BOLD    = "\x1b[1m"
    DIM     = "\x1b[2m"
    RED     = "\x1b[31m"
    GREEN   = "\x1b[32m"
    YELLOW  = "\x1b[33m"
    CYAN    = "\x1b[36m"
    BGREEN  = "\x1b[92m"
    BYELLOW = "\x1b[93m"
    BBLUE   = "\x1b[94m"
    BCYAN   = "\x1b[96m"
    BWHITE  = "\x1b[97m"

def _w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()

# ── Wykrywanie własnego IP, maski i interfejsu ────────────────────────────────

def _default_iface_linux() -> str:
    """Zwraca nazwę domyślnego interfejsu sieciowego (Linux) przez /proc/net/route."""
    try:
        with open("/proc/net/route") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "00000000":
                    return parts[0]
    except Exception:
        pass
    return "eth0"

def _iface_mac_ip_linux(iface: str) -> tuple[bytes, str]:
    """Zwraca (mac_bytes, ip_str) dla podanego interfejsu (Linux, ioctl)."""
    import fcntl
    SIOCGIFHWADDR = 0x8927
    SIOCGIFADDR   = 0x8915
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        buf  = struct.pack("256s", iface[:15].encode())
        mac  = fcntl.ioctl(s.fileno(), SIOCGIFHWADDR, buf)[18:24]
        buf  = struct.pack("256s", iface[:15].encode())
        ip_b = fcntl.ioctl(s.fileno(), SIOCGIFADDR,   buf)[20:24]
        return mac, socket.inet_ntoa(ip_b)
    finally:
        s.close()

def _local_networks() -> list[ipaddress.IPv4Network]:
    """Zwraca listę sieci IPv4 hosta (bez loopback)."""
    networks: list[ipaddress.IPv4Network] = []

    def _add(ip_cidr: str) -> None:
        try:
            net = ipaddress.IPv4Interface(ip_cidr).network
            if not net.is_loopback and net not in networks:
                networks.append(net)
        except ValueError:
            pass

    try:
        if IS_WINDOWS:
            out = subprocess.check_output(["ipconfig"], text=True, errors="replace")
            ip_re   = re.compile(r"IPv4[^:]*:\s*([\d.]+)")
            mask_re = re.compile(r"Subnet Mask[^:]*:\s*([\d.]+)")
            for ip, mask in zip(ip_re.findall(out), mask_re.findall(out)):
                _add(f"{ip}/{mask}")
        else:
            for cmd in (["ip", "addr"], ["ifconfig", "-a"]):
                try:
                    out = subprocess.check_output(
                        cmd, text=True, errors="replace", stderr=subprocess.DEVNULL
                    )
                    for m in re.finditer(
                        r"inet (?:addr:)?([\d.]+)(?:/(\d+)|\s+netmask\s+([\d.]+))", out
                    ):
                        prefix = m.group(2) or m.group(3)
                        if prefix:
                            _add(f"{m.group(1)}/{prefix}")
                    if networks:
                        break
                except FileNotFoundError:
                    continue
    except Exception:
        pass

    if not networks:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            _add(f"{local_ip}/24")
        except Exception:
            pass

    return networks

# ══════════════════════════════════════════════════════════════════════════════
# METODA 1: ARP SWEEP (Linux, root)  ← najszybsza
# Wysyła ramki ARP broadcast przez surowy socket L2, zbiera odpowiedzi.
# Nie wymaga ICMP, wykrywa hosty, które blokują ping.
# ══════════════════════════════════════════════════════════════════════════════

ETH_P_ARP = 0x0806

def _build_arp_request(src_mac: bytes, src_ip: str, tgt_ip: str) -> bytes:
    """Buduje ramkę Ethernet z ARP request (broadcast)."""
    eth  = b"\xff\xff\xff\xff\xff\xff" + src_mac + struct.pack("!H", ETH_P_ARP)
    # htype=1(ETH), ptype=0x0800(IPv4), hlen=6, plen=4, op=1(request)
    arp  = struct.pack("!HHBBH", 1, 0x0800, 6, 4, 1)
    arp += src_mac + socket.inet_aton(src_ip)
    arp += b"\x00" * 6 + socket.inet_aton(tgt_ip)
    return eth + arp

def _arp_sweep(
    network: ipaddress.IPv4Network,
    timeout: float = 2.0,
    progress: bool = True,
) -> dict[str, str]:
    """
    ARP sweep: wysyła ARP request do każdego hosta w sieci,
    zbiera odpowiedzi przez `timeout` sekund.
    Zwraca dict {ip: mac}.
    Wymaga: Linux + root + AF_PACKET.
    """
    iface   = _default_iface_linux()
    src_mac, src_ip = _iface_mac_ip_linux(iface)

    hosts   = list(network.hosts())
    total   = len(hosts)
    results : dict[str, str] = {}

    # Jeden socket do wysyłania i odbierania
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ARP))
    sock.bind((iface, 0))

    # ── Wątek odbierający odpowiedzi ARP reply ────────────────────────────────
    stop_recv = threading.Event()

    def receiver() -> None:
        while not stop_recv.is_set():
            ready = select.select([sock], [], [], 0.1)
            if not ready[0]:
                continue
            try:
                frame, _ = sock.recvfrom(65535)
            except Exception:
                continue
            # Ethernet header = 14B; ARP = dalej
            if len(frame) < 42:
                continue
            eth_type = struct.unpack("!H", frame[12:14])[0]
            if eth_type != ETH_P_ARP:
                continue
            arp_op = struct.unpack("!H", frame[20:22])[0]
            if arp_op != 2:          # 2 = ARP reply
                continue
            sender_mac = frame[22:28]
            sender_ip  = socket.inet_ntoa(frame[28:32])
            mac_str    = ":".join(f"{b:02x}" for b in sender_mac)
            results[sender_ip] = mac_str

    recv_thread = threading.Thread(target=receiver, daemon=True)
    recv_thread.start()

    # ── Wysyłanie ARP requestów ───────────────────────────────────────────────
    # Rozbite na batches żeby nie przepełnić bufora socketu
    BATCH = 256
    t_send_start = time.time()

    for i, host in enumerate(hosts):
        pkt = _build_arp_request(src_mac, src_ip, str(host))
        try:
            sock.send(pkt)
        except Exception:
            pass
        if progress and (i + 1) % max(total // 40, 1) == 0:
            pct    = (i + 1) * 100 // total
            bar_w  = 30
            filled = pct * bar_w // 100
            bar    = "█" * filled + "░" * (bar_w - filled)
            sys.stdout.write(
                f"\r  {_A.DIM}[{bar}] {pct:3d}%  wysłano {i+1}/{total}{_A.RESET}"
            )
            sys.stdout.flush()
        # Małe opóźnienie co BATCH żeby nie tracić pakietów
        if (i + 1) % BATCH == 0:
            time.sleep(0.01)

    t_sent = time.time()
    send_time = t_sent - t_send_start

    if progress:
        sys.stdout.write(f"\r{' ' * 60}\r")
        sys.stdout.flush()
        _w(f"  {_A.DIM}Wysłano {total} ARP requestów ({send_time:.2f}s), czekam na odpowiedzi...{_A.RESET}\r")

    # Poczekaj na odpowiedzi — max `timeout` sekund od ostatniego wysłania
    # ale minimum jeszcze 0.5s
    wait = max(timeout - send_time, 0.5)
    time.sleep(wait)

    stop_recv.set()
    recv_thread.join(timeout=1)
    sock.close()

    if progress:
        sys.stdout.write(f"\r{' ' * 70}\r")
        sys.stdout.flush()

    return results


def _can_arp_sweep() -> bool:
    """Sprawdza czy ARP sweep jest możliwy (Linux + root + AF_PACKET)."""
    if not IS_LINUX:
        return False
    if not _is_root():
        return False
    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ARP))
        s.close()
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# METODA 2: RAW ICMP PING (Linux/Mac, root)  ← szybka
# Jeden socket SOCK_RAW do wysyłania ICMP echo request,
# jeden wątek odbierający wszystkie odpowiedzi równocześnie.
# Eliminuje overhead subprocess (fork/exec per host).
# ══════════════════════════════════════════════════════════════════════════════

def _icmp_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    chk = sum((data[i] << 8) + data[i + 1] for i in range(0, len(data), 2))
    chk = (~((chk >> 16) + (chk & 0xFFFF))) & 0xFFFF
    return chk

def _build_icmp_echo(pid: int, seq: int) -> bytes:
    header = struct.pack("!BBHHH", 8, 0, 0, pid, seq)
    data   = b"polsoft_wifiscan"
    chk    = _icmp_checksum(header + data)
    return struct.pack("!BBHHH", 8, 0, chk, pid, seq) + data

def _raw_icmp_sweep(
    network: ipaddress.IPv4Network,
    timeout: float = 1.5,
    progress: bool = True,
) -> list[str]:
    """
    Raw ICMP sweep: wysyła ICMP echo request do każdego hosta przez jeden
    surowy socket, zbiera odpowiedzi w osobnym wątku.
    Zwraca listę odpowiadających IP.
    Wymaga: root (Linux/Mac). Na Windows wymaga podwyższonych uprawnień.
    """
    hosts = list(network.hosts())
    total = len(hosts)
    pid   = os.getpid() & 0xFFFF

    alive: set[str] = set()
    lock  = threading.Lock()

    # Socket do wysyłania
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, 64)

    # Socket do odbierania (osobny — unika wyścigu)
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    recv_sock.settimeout(0.1)

    stop_recv  = threading.Event()

    def receiver() -> None:
        while not stop_recv.is_set():
            ready = select.select([recv_sock], [], [], 0.1)
            if not ready[0]:
                continue
            try:
                raw, addr = recv_sock.recvfrom(1024)
            except Exception:
                continue
            # IP header = 20B (min), ICMP zaczyna się od bajtu 20
            if len(raw) < 28:
                continue
            icmp_type = raw[20]
            icmp_code = raw[21]
            if icmp_type == 0 and icmp_code == 0:   # echo reply
                with lock:
                    alive.add(addr[0])

    recv_thread = threading.Thread(target=receiver, daemon=True)
    recv_thread.start()

    # Wysyłaj ICMP echo do wszystkich hostów
    t_send_start = time.time()
    for seq, host in enumerate(hosts):
        pkt = _build_icmp_echo(pid, seq & 0xFFFF)
        try:
            send_sock.sendto(pkt, (str(host), 0))
        except Exception:
            pass
        if progress and (seq + 1) % max(total // 40, 1) == 0:
            pct    = (seq + 1) * 100 // total
            bar_w  = 30
            filled = pct * bar_w // 100
            bar    = "█" * filled + "░" * (bar_w - filled)
            sys.stdout.write(
                f"\r  {_A.DIM}[{bar}] {pct:3d}%  wysłano {seq+1}/{total}{_A.RESET}"
            )
            sys.stdout.flush()

    t_sent    = time.time()
    send_time = t_sent - t_send_start

    if progress:
        sys.stdout.write(f"\r{' ' * 60}\r")
        sys.stdout.flush()
        _w(f"  {_A.DIM}Wysłano {total} ICMP requestów ({send_time:.2f}s), czekam na odpowiedzi...{_A.RESET}\r")

    wait = max(timeout - send_time, 0.3)
    time.sleep(wait)

    stop_recv.set()
    recv_thread.join(timeout=1)
    send_sock.close()
    recv_sock.close()

    if progress:
        sys.stdout.write(f"\r{' ' * 70}\r")
        sys.stdout.flush()

    return list(alive)


def _can_raw_icmp() -> bool:
    """Sprawdza czy raw ICMP jest możliwy."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        s.close()
        return _is_root()
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# METODA 3: SUBPROCESS PING (fallback, bez root)
# ══════════════════════════════════════════════════════════════════════════════

def _ping_subprocess(ip: str, timeout: int = 1) -> bool:
    t = max(timeout, 1)
    try:
        if IS_WINDOWS:
            cmd = ["ping", "-n", "1", "-w", str(t * 1000), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(t), ip]
        r = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=t + 1,
        )
        return r.returncode == 0
    except Exception:
        return False

def _subprocess_ping_sweep(
    network: ipaddress.IPv4Network,
    workers: int = 128,
    timeout: int = 1,
    progress: bool = True,
) -> list[str]:
    """Fallback: ping przez subprocess, wielowątkowy."""
    hosts = list(network.hosts())
    total = len(hosts)
    found: list[str] = []
    lock  = threading.Lock()
    done  = [0]

    def worker(ip_obj: ipaddress.IPv4Address) -> None:
        ip = str(ip_obj)
        alive = _ping_subprocess(ip, timeout)
        with lock:
            if alive:
                found.append(ip)
            done[0] += 1
            if progress and done[0] % max(total // 40, 1) == 0:
                pct    = done[0] * 100 // total
                bar_w  = 30
                filled = pct * bar_w // 100
                bar    = "█" * filled + "░" * (bar_w - filled)
                sys.stdout.write(
                    f"\r  {_A.DIM}[{bar}] {pct:3d}%  ({done[0]}/{total}){_A.RESET}"
                )
                sys.stdout.flush()

    sem = threading.Semaphore(workers)

    def bounded(h: ipaddress.IPv4Address) -> None:
        with sem:
            worker(h)

    threads = [threading.Thread(target=bounded, args=(h,), daemon=True) for h in hosts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if progress:
        sys.stdout.write(f"\r{' ' * 60}\r")
        sys.stdout.flush()

    return found


# ══════════════════════════════════════════════════════════════════════════════
# ARP TABLE (odczyt z systemu)
# ══════════════════════════════════════════════════════════════════════════════

def _arp_table() -> dict[str, str]:
    """Zwraca słownik ip → mac z systemowej tablicy ARP."""
    # Szybka ścieżka: /proc/net/arp (Linux)
    if IS_LINUX:
        try:
            result: dict[str, str] = {}
            with open("/proc/net/arp") as f:
                next(f)  # pomiń nagłówek
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4 and parts[3] != "00:00:00:00:00:00":
                        result[parts[0]] = parts[3].lower()
            if result:
                return result
        except Exception:
            pass

    # Fallback: komenda arp
    try:
        if IS_WINDOWS:
            out = subprocess.check_output(["arp", "-a"], text=True, errors="replace")
            result = {}
            for m in re.finditer(r"([\d.]+)\s+([\da-fA-F:-]{11,})\s+\w+", out):
                ip, mac = m.group(1), m.group(2).replace("-", ":").lower()
                result[ip] = mac
            return result
        else:
            out = subprocess.check_output(["arp", "-n"], text=True, errors="replace")
            result = {}
            for m in re.finditer(r"([\d.]+)\s+\S+\s+([\da-fA-F:]{11,})", out):
                ip, mac = m.group(1), m.group(2).lower()
                if mac not in ("(incomplete)", "<incomplete>"):
                    result[ip] = mac
            return result
    except Exception:
        return {}

# ── Rozwiązywanie hostname (równoległe) ───────────────────────────────────────

def _resolve_hostnames(ips: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    lock = threading.Lock()

    def resolve(ip: str) -> None:
        try:
            name = socket.gethostbyaddr(ip)[0]
        except Exception:
            name = ""
        with lock:
            results[ip] = name

    threads = [threading.Thread(target=resolve, args=(ip,), daemon=True) for ip in ips]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3)
    for ip in ips:
        results.setdefault(ip, "")
    return results

# ── Vendor OUI ────────────────────────────────────────────────────────────────

_OUI: dict[str, str] = {
    "00:50:56": "VMware",        "00:0c:29": "VMware",
    "00:1a:11": "Google",        "f4:f5:d8": "Google",
    "b8:27:eb": "Raspberry Pi",  "dc:a6:32": "Raspberry Pi",
    "e4:5f:01": "Raspberry Pi",  "28:cd:c1": "Apple",
    "3c:22:fb": "Apple",         "a4:c3:f0": "Apple",
    "00:17:f2": "Apple",         "ac:de:48": "Apple",
    "18:65:90": "Apple",         "f0:18:98": "Apple",
    "fc:fb:fb": "Ubiquiti",      "dc:9f:db": "Ubiquiti",
    "44:d9:e7": "Ubiquiti",      "00:27:22": "Ubiquiti",
    "00:1b:17": "Intel",         "00:21:6b": "Intel",
    "8c:8d:28": "Intel",         "00:26:c6": "Intel",
    "74:d0:2b": "Intel",         "00:1c:c0": "Intel",
    "08:00:27": "VirtualBox",    "0a:00:27": "VirtualBox",
    "00:50:ba": "D-Link",        "00:1c:f0": "D-Link",
    "1c:7e:e5": "D-Link",        "00:90:4c": "Epson",
    "00:e0:4c": "Realtek",       "52:54:00": "QEMU/KVM",
    "00:16:3e": "Xen",           "00:15:5d": "Microsoft Hyper-V",
    "28:d2:44": "TP-Link",       "50:c7:bf": "TP-Link",
    "ac:84:c9": "TP-Link",       "e8:de:27": "TP-Link",
    "00:1d:0f": "ASUS",          "04:92:26": "ASUS",
    "2c:fd:a1": "ASUS",          "10:7b:44": "ASUS",
    "00:22:b0": "ASUS",          "bc:ee:7b": "ASUS",
    "7c:2e:bd": "Netgear",       "a0:40:a0": "Netgear",
    "30:46:9a": "Netgear",       "20:4e:7f": "Netgear",
    "c0:ff:d4": "Samsung",       "00:12:47": "Samsung",
    "84:55:a5": "Samsung",       "1c:62:b8": "Samsung",
    "38:d4:0b": "Huawei",        "00:e0:fc": "Huawei",
    "48:46:fb": "Huawei",        "28:6e:d4": "Huawei",
}

def _vendor(mac: str) -> str:
    return _OUI.get(mac[:8].lower(), "")

# ── Formatowanie wyników ──────────────────────────────────────────────────────

def _print_results(devices: list[dict], method: str = "") -> None:
    if not devices:
        _w(f"\n  {_A.DIM}Nie znaleziono żadnych urządzeń.{_A.RESET}\n\n")
        return

    col_ip  = max((len(d["ip"])       for d in devices), default=15)
    col_mac = max((len(d["mac"])      for d in devices), default=17)
    col_hn  = max((len(d["hostname"]) for d in devices), default=8)
    col_hn  = max(col_hn, 8)

    method_s = f"  {_A.DIM}[metoda: {method}]{_A.RESET}" if method else ""
    _w(f"\n  {_A.BOLD}{_A.BWHITE}")
    _w(f"  {'#':<4} {'IP':<{col_ip}}  {'MAC':<{col_mac}}  {'Hostname':<{col_hn}}  Producent\n")
    _w(f"  {'─'*4} {'─'*col_ip}  {'─'*col_mac}  {'─'*col_hn}  {'─'*20}\n")
    _w(_A.RESET)

    for i, d in enumerate(sorted(devices, key=lambda x: ipaddress.ip_address(x["ip"])), 1):
        ip_s  = f"{_A.BCYAN}{d['ip']:<{col_ip}}{_A.RESET}"
        mac_s = f"{_A.DIM}{d['mac']:<{col_mac}}{_A.RESET}"
        hn_s  = (f"{_A.BWHITE}{d['hostname']:<{col_hn}}{_A.RESET}"
                 if d["hostname"] else f"{'':<{col_hn}}")
        vnd_s = (f"{_A.BYELLOW}{d['vendor']}{_A.RESET}"
                 if d["vendor"] else f"{_A.DIM}nieznany{_A.RESET}")
        _w(f"  {_A.DIM}{i:<4}{_A.RESET} {ip_s}  {mac_s}  {hn_s}  {vnd_s}\n")

    _w(f"\n  {_A.BGREEN}✓{_A.RESET}  Znaleziono {_A.BOLD}{len(devices)}{_A.RESET} urządzenie(a){method_s}\n\n")

# ── Główna funkcja skanowania ─────────────────────────────────────────────────

def _do_scan(args: list[str], terminal=None) -> None:
    """
    Skanuje sieć lokalną. Auto-wybiera najszybszą dostępną metodę.

      wifi scan [SIEĆ]        — np. 'wifi scan 192.168.1.0/24'
      wifi scan --fast        — ARP/ICMP z krótszym oczekiwaniem
      wifi scan --slow        — dłuższy timeout (sieci z dużym pingiem)
      wifi scan --ping        — wymuś metodę subprocess ping
      wifi scan --arp         — wymuś metodę ARP sweep (wymaga root)
      wifi scan --icmp        — wymuś metodę raw ICMP (wymaga root)
    """
    target_net : Optional[str] = None
    timeout    = 1.5      # domyślny timeout odpowiedzi
    workers    = 128      # dla subprocess fallback
    force_mode : Optional[str] = None   # "arp" / "icmp" / "ping"

    for a in args:
        if a == "--fast":
            timeout = 0.8
            workers = 256
        elif a == "--slow":
            timeout = 3.0
            workers = 64
        elif a == "--ping":
            force_mode = "ping"
        elif a == "--arp":
            force_mode = "arp"
        elif a == "--icmp":
            force_mode = "icmp"
        elif "/" in a:
            target_net = a

    if target_net:
        try:
            networks = [ipaddress.IPv4Network(target_net, strict=False)]
        except ValueError as e:
            _w(f"  {_A.RED}Błędna sieć: {e}{_A.RESET}\n")
            return
    else:
        networks = _local_networks()

    if not networks:
        _w(
            f"  {_A.RED}Nie można wykryć lokalnej sieci. "
            f"Podaj sieć ręcznie: wifi scan 192.168.1.0/24{_A.RESET}\n"
        )
        return

    # Wybór metody
    if force_mode == "arp":
        if not _can_arp_sweep():
            _w(f"  {_A.RED}ARP sweep wymaga Linux + root. Uruchom jako root lub sudo.{_A.RESET}\n")
            return
        method = "arp"
    elif force_mode == "icmp":
        if not _can_raw_icmp():
            _w(f"  {_A.RED}Raw ICMP wymaga root. Uruchom jako root lub sudo.{_A.RESET}\n")
            return
        method = "icmp"
    elif force_mode == "ping":
        method = "ping"
    else:
        # Auto-wybór: ARP → ICMP → ping
        if _can_arp_sweep():
            method = "arp"
        elif _can_raw_icmp():
            method = "icmp"
        else:
            method = "ping"

    method_labels = {
        "arp":  f"{_A.BGREEN}ARP sweep{_A.RESET}    {_A.DIM}(najszybsza, wymaga root){_A.RESET}",
        "icmp": f"{_A.BYELLOW}Raw ICMP{_A.RESET}     {_A.DIM}(szybka, wymaga root){_A.RESET}",
        "ping": f"{_A.DIM}subprocess ping{_A.RESET} {_A.DIM}(fallback, bez root){_A.RESET}",
    }

    for net in networks:
        host_count = net.num_addresses - 2
        _w(
            f"\n  {_A.BOLD}Skanowanie:{_A.RESET} {_A.BCYAN}{net}{_A.RESET}  "
            f"{_A.DIM}({host_count} hostów){_A.RESET}\n"
            f"  {_A.BOLD}Metoda:{_A.RESET}     {method_labels[method]}\n\n"
        )

        t_start = time.time()

        if method == "arp":
            arp_results = _arp_sweep(net, timeout=timeout)
            live_ips    = list(arp_results.keys())
            # MAC już mamy z ARP sweep — uzupełnij systemowym ARP dla brakujących
            sys_arp     = _arp_table()
            sys_arp.update(arp_results)   # sweep ma pierwszeństwo
            arp_data    = sys_arp

        elif method == "icmp":
            live_ips = _raw_icmp_sweep(net, timeout=timeout)
            arp_data = _arp_table()

        else:  # ping
            live_ips = _subprocess_ping_sweep(net, workers=workers, timeout=int(timeout))
            arp_data = _arp_table()

        t_scan = time.time() - t_start

        if live_ips:
            _w(f"  {_A.DIM}Rozwiązywanie nazw hostów...{_A.RESET}\r")
            hostnames = _resolve_hostnames(live_ips)
            devices: list[dict] = []
            for ip in live_ips:
                mac      = arp_data.get(ip, "??:??:??:??:??:??")
                hostname = hostnames.get(ip, "")
                vendor   = _vendor(mac)
                devices.append({"ip": ip, "mac": mac, "hostname": hostname, "vendor": vendor})
            sys.stdout.write(f"\r{' ' * 50}\r")
            sys.stdout.flush()
        else:
            devices = []

        elapsed = time.time() - t_start
        _print_results(devices, method=method)
        _w(f"  {_A.DIM}Czas: {elapsed:.1f}s  (skan: {t_scan:.1f}s){_A.RESET}\n\n")


def _do_arp(args: list[str], terminal=None) -> None:
    """Wyświetla aktualną tablicę ARP (bez skanowania)."""
    _w(f"\n  {_A.BOLD}{_A.BWHITE}Tablica ARP:{_A.RESET}\n\n")
    table = _arp_table()
    if not table:
        _w(f"  {_A.DIM}(pusta){_A.RESET}\n\n")
        return
    col = max(len(ip) for ip in table)
    for ip, mac in sorted(table.items(), key=lambda x: ipaddress.ip_address(x[0])):
        vendor = _vendor(mac)
        vnd_s  = f"{_A.BYELLOW}{vendor}{_A.RESET}" if vendor else f"{_A.DIM}nieznany{_A.RESET}"
        _w(f"  {_A.BCYAN}{ip:<{col}}{_A.RESET}  {_A.DIM}{mac}{_A.RESET}  {vnd_s}\n")
    _w(f"\n  {_A.DIM}{len(table)} wpis(ów){_A.RESET}\n\n")


def _do_info(args: list[str], terminal=None) -> None:
    """Wyświetla informacje o lokalnych interfejsach i wybranej metodzie skanowania."""
    _w(f"\n  {_A.BOLD}{_A.BWHITE}Interfejsy sieciowe:{_A.RESET}\n\n")
    networks = _local_networks()
    if not networks:
        _w(f"  {_A.DIM}(brak danych){_A.RESET}\n\n")
    else:
        for net in networks:
            _w(f"  {_A.BCYAN}{net}{_A.RESET}\n")

    root = _is_root()
    can_arp  = _can_arp_sweep()
    can_icmp = _can_raw_icmp()

    _w(f"\n  {_A.BOLD}{_A.BWHITE}Dostępne metody skanowania:{_A.RESET}\n\n")
    _w(f"  {'ARP sweep':<18}  {'✓' if can_arp  else '✗'}  "
       f"{_A.DIM}{'dostępna' if can_arp  else 'wymaga Linux + root'}{_A.RESET}\n")
    _w(f"  {'Raw ICMP':<18}  {'✓' if can_icmp else '✗'}  "
       f"{_A.DIM}{'dostępna' if can_icmp else 'wymaga root'}{_A.RESET}\n")
    _w(f"  {'Subprocess ping':<18}  ✓  {_A.DIM}zawsze dostępna (fallback){_A.RESET}\n")
    _w(f"\n  {_A.DIM}Uprawnienia root: {'TAK' if root else 'NIE'}{_A.RESET}\n\n")


# ══════════════════════════════════════════════════════════════════════════════
# WIFI LIST / CONNECT / DISCONNECT
# Windows  : netsh wlan
# Linux    : nmcli (preferowane) lub wpa_cli (fallback)
# macOS    : networksetup
# ══════════════════════════════════════════════════════════════════════════════

def _wifi_list_networks() -> list[dict]:
    """
    Zwraca listę dostępnych sieci WiFi.
    Każdy element: {"ssid": str, "signal": str, "secured": bool, "bssid": str}
    """
    networks: list[dict] = []

    try:
        if IS_WINDOWS:
            out = subprocess.check_output(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                text=True, errors="replace", stderr=subprocess.DEVNULL
            )
            current: dict = {}
            for line in out.splitlines():
                line = line.strip()
                if line.lower().startswith("ssid") and "bssid" not in line.lower():
                    if current.get("ssid"):
                        networks.append(current)
                    ssid = line.split(":", 1)[-1].strip()
                    current = {"ssid": ssid, "signal": "", "secured": False, "bssid": ""}
                elif "bssid" in line.lower():
                    current["bssid"] = line.split(":", 1)[-1].strip()
                elif "signal" in line.lower():
                    current["signal"] = line.split(":", 1)[-1].strip()
                elif "authentication" in line.lower():
                    auth = line.split(":", 1)[-1].strip().lower()
                    current["secured"] = auth not in ("open", "")
            if current.get("ssid"):
                networks.append(current)

        elif IS_LINUX:
            # nmcli: szybkie i czytelne
            try:
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY", "dev", "wifi", "list"],
                    text=True, errors="replace", stderr=subprocess.DEVNULL
                )
                seen: set[str] = set()
                for line in out.splitlines():
                    parts = line.split(":")
                    if len(parts) >= 4:
                        ssid     = parts[0]
                        bssid    = ":".join(parts[1:7]) if len(parts) >= 7 else parts[1]
                        signal   = parts[-2] if len(parts) >= 3 else ""
                        security = parts[-1]
                        if ssid and ssid not in seen:
                            seen.add(ssid)
                            networks.append({
                                "ssid"   : ssid,
                                "bssid"  : bssid,
                                "signal" : f"{signal}%",
                                "secured": bool(security.strip()),
                            })
            except FileNotFoundError:
                # fallback: iwlist
                iface = _default_iface_linux()
                out = subprocess.check_output(
                    ["iwlist", iface, "scan"],
                    text=True, errors="replace", stderr=subprocess.DEVNULL
                )
                ssid_re   = re.compile(r'ESSID:"([^"]*)"')
                signal_re = re.compile(r"Signal level=(-?\d+)")
                enc_re    = re.compile(r"Encryption key:(on|off)")
                bssid_re  = re.compile(r"Address:\s*([\dA-Fa-f:]{17})")
                cells = re.split(r"Cell \d+", out)
                for cell in cells[1:]:
                    ssid_m   = ssid_re.search(cell)
                    signal_m = signal_re.search(cell)
                    enc_m    = enc_re.search(cell)
                    bssid_m  = bssid_re.search(cell)
                    if ssid_m:
                        networks.append({
                            "ssid"   : ssid_m.group(1),
                            "bssid"  : bssid_m.group(1) if bssid_m else "",
                            "signal" : f"{signal_m.group(1)} dBm" if signal_m else "",
                            "secured": enc_m.group(1) == "on" if enc_m else False,
                        })

        elif IS_MACOS:
            airport = (
                "/System/Library/PrivateFrameworks/Apple80211.framework"
                "/Versions/Current/Resources/airport"
            )
            out = subprocess.check_output(
                [airport, "-s"],
                text=True, errors="replace", stderr=subprocess.DEVNULL
            )
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    networks.append({
                        "ssid"   : parts[0],
                        "bssid"  : parts[1] if len(parts) > 1 else "",
                        "signal" : parts[2] if len(parts) > 2 else "",
                        "secured": len(parts) > 6,
                    })
    except Exception as e:
        _w(f"  {_A.RED}Błąd skanowania sieci: {e}{_A.RESET}\n")

    return networks


def _do_list(args: list[str], terminal=None) -> None:
    """Wyświetla dostępne sieci WiFi."""
    _w(f"\n  {_A.DIM}Szukam dostępnych sieci...{_A.RESET}\r")
    nets = _wifi_list_networks()
    sys.stdout.write(f"\r{' ' * 40}\r")
    sys.stdout.flush()

    if not nets:
        _w(f"  {_A.RED}Nie znaleziono żadnych sieci WiFi.{_A.RESET}\n\n")
        return

    _w(f"\n  {_A.BOLD}{_A.BWHITE}  {'#':<4} {'SSID':<32} {'Sygnał':<10} {'Zabezp.':<10} BSSID\n")
    _w(f"  {'─'*4} {'─'*32} {'─'*10} {'─'*10} {'─'*17}\n{_A.RESET}")
    for i, n in enumerate(nets, 1):
        ssid_s = f"{_A.BCYAN}{n['ssid']:<32}{_A.RESET}"
        sig_s  = f"{_A.BYELLOW}{n['signal']:<10}{_A.RESET}"
        sec_s  = (f"{_A.GREEN}{'WPA/WEP':<10}{_A.RESET}" if n["secured"]
                  else f"{_A.DIM}{'otw.':<10}{_A.RESET}")
        bssid_s = f"{_A.DIM}{n['bssid']}{_A.RESET}"
        _w(f"  {_A.DIM}{i:<4}{_A.RESET} {ssid_s} {sig_s} {sec_s} {bssid_s}\n")
    _w(f"\n  {_A.DIM}Znaleziono {len(nets)} sieć(i){_A.RESET}\n\n")


def _read_password_masked(prompt: str = "  Hasło: ") -> str:
    """Czyta hasło ze stdin z maskowaniem znaków jako '*'."""
    import sys, tty, termios
    _w(prompt)
    pwd = []
    try:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                ch = sys.stdin.read(1)
                if ch in ("\r", "\n"):
                    break
                elif ch in ("\x7f", "\x08"):  # backspace
                    if pwd:
                        pwd.pop()
                        _w("\b \b")
                elif ch == "\x03":            # Ctrl+C
                    _w("\n")
                    raise KeyboardInterrupt
                else:
                    pwd.append(ch)
                    _w("*")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except (ImportError, AttributeError):
        # Windows fallback
        import msvcrt
        _w("\b \b" * len(pwd))  # wyczyść ewentualne echo
        pwd = []
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                break
            elif ch in ("\x08", "\x7f"):
                if pwd:
                    pwd.pop()
                    _w("\b \b")
            else:
                pwd.append(ch)
                _w("*")
    _w("\n")
    return "".join(pwd)


def _spinner_start(msg: str) -> tuple:
    """Uruchamia spinner w tle. Zwraca (stop_event, thread)."""
    stop = threading.Event()
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def _run() -> None:
        i = 0
        while not stop.is_set():
            _w(f"\r  {_A.CYAN}{frames[i % len(frames)]}{_A.RESET}  {_A.DIM}{msg}{_A.RESET}")
            i += 1
            time.sleep(0.1)
        _w(f"\r{' ' * (len(msg) + 8)}\r")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return stop, t


def _spinner_stop(stop_event: threading.Event, thread: threading.Thread) -> None:
    stop_event.set()
    thread.join()


def _get_gateway_ip() -> Optional[str]:
    """Zwraca IP bramy domyślnej."""
    try:
        if IS_WINDOWS:
            out = subprocess.check_output(
                ["ipconfig"], text=True, errors="replace"
            )
            m = re.search(r"Default Gateway[^:]*:\s*([\d.]+)", out)
            return m.group(1) if m else None
        else:
            for cmd in (["ip", "route"], ["route", "-n"]):
                try:
                    out = subprocess.check_output(
                        cmd, text=True, errors="replace", stderr=subprocess.DEVNULL
                    )
                    m = re.search(r"(?:default|0\.0\.0\.0)\s+(?:via\s+)?([\d.]+)", out)
                    if m:
                        return m.group(1)
                except FileNotFoundError:
                    continue
    except Exception:
        pass
    return None


def _get_local_ip() -> Optional[str]:
    """Zwraca bieżący lokalny adres IPv4."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _ping_gateway(gateway: str, count: int = 2, timeout_s: int = 3) -> bool:
    """Wysyła ping do bramy. Zwraca True jeśli odpowiada."""
    try:
        if IS_WINDOWS:
            cmd = ["ping", "-n", str(count), "-w", str(timeout_s * 1000), gateway]
        else:
            cmd = ["ping", "-c", str(count), "-W", str(timeout_s), gateway]
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout_s + 2)
        return r.returncode == 0
    except Exception:
        return False


def _verify_connection_post_connect(ssid: str) -> None:
    """
    Po udanym connect: pinguje bramę i wyświetla aktualny IP.
    Wywoływane po każdej udanej próbie połączenia.
    """
    # Chwila na przydzielenie IP przez DHCP
    time.sleep(1.5)

    local_ip = _get_local_ip()
    gateway  = _get_gateway_ip()

    if local_ip:
        _w(f"  {_A.DIM}IP:{_A.RESET}  {_A.BWHITE}{local_ip}{_A.RESET}\n")
    else:
        _w(f"  {_A.DIM}IP:{_A.RESET}  {_A.YELLOW}nie przydzielono{_A.RESET}\n")

    if gateway:
        spin_stop, spin_t = _spinner_start(f"Weryfikacja połączenia (ping {gateway})...")
        ok = _ping_gateway(gateway)
        _spinner_stop(spin_stop, spin_t)
        if ok:
            _w(f"  {_A.BGREEN}✓{_A.RESET}  Brama {_A.BWHITE}{gateway}{_A.RESET} odpowiada — {_A.BGREEN}sieć działa{_A.RESET}\n\n")
        else:
            _w(f"  {_A.YELLOW}⚠{_A.RESET}  Brama {_A.BWHITE}{gateway}{_A.RESET} nie odpowiada — brak dostępu do sieci\n\n")
    else:
        _w(f"  {_A.YELLOW}⚠{_A.RESET}  Nie wykryto bramy domyślnej\n\n")


def _win_profile_exists(ssid: str) -> bool:
    """Sprawdza czy profil WiFi dla danego SSID już istnieje na Windows."""
    try:
        out = subprocess.check_output(
            ["netsh", "wlan", "show", "profiles"],
            text=True, errors="replace", stderr=subprocess.DEVNULL
        )
        return ssid.lower() in out.lower()
    except Exception:
        return False


def _win_delete_profile(ssid: str) -> None:
    """Usuwa profil WiFi z Windows (przed nadpisaniem)."""
    try:
        subprocess.run(
            ["netsh", "wlan", "delete", "profile", f"name={ssid}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def _win_add_profile(ssid: str, password: str) -> bool:
    """
    Tworzy profil WPA2PSK/AES. Jeśli netsh odrzuci, próbuje fallback WPAPSK/TKIP.
    Zwraca True gdy profil dodany pomyślnie.
    """
    def _build_xml(auth: str, enc: str) -> str:
        return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM><security>
        <authEncryption>
            <authentication>{auth}</authentication>
            <encryption>{enc}</encryption>
            <useOneX>false</useOneX>
        </authEncryption>
        <sharedKey>
            <keyType>passPhrase</keyType>
            <protected>false</protected>
            <keyMaterial>{password}</keyMaterial>
        </sharedKey>
    </security></MSM>
</WLANProfile>"""

    profile_path = os.path.join(os.environ.get("TEMP", "."), "_cterm_wifi_profile.xml")
    for auth, enc in [("WPA2PSK", "AES"), ("WPAPSK", "TKIP")]:
        try:
            with open(profile_path, "w", encoding="utf-8") as f:
                f.write(_build_xml(auth, enc))
            r = subprocess.run(
                ["netsh", "wlan", "add", "profile", f"filename={profile_path}"],
                capture_output=True, text=True
            )
            if r.returncode == 0:
                return True
            # jeśli WPA2PSK/AES odrzucone — próbuj fallback
        except Exception:
            pass
        finally:
            try:
                os.remove(profile_path)
            except Exception:
                pass
    return False


def _do_connect(args: list[str], terminal=None) -> None:
    """
    Łączy z siecią WiFi.

      wifi connect <SSID>               — otwarta sieć lub zapisany profil
      wifi connect <SSID> <HASŁO>       — sieć WPA/WPA2
      wifi connect <SSID> --open        — wymuś połączenie bez hasła
      wifi connect <SSID> --ask         — zawsze pytaj o hasło (enterprise)
    """
    if not args:
        _w(
            f"  {_A.YELLOW}Użycie:{_A.RESET}  wifi connect <SSID> [HASŁO] [--open] [--ask]\n"
            f"  Przykład: wifi connect MojaSiec MojeHaslo\n\n"
        )
        return

    ssid       = args[0]
    force_open = "--open" in args
    force_ask  = "--ask"  in args
    password   = None

    # Wyciągnij hasło z args (nie-flagowy drugi argument)
    for a in args[1:]:
        if not a.startswith("--"):
            password = a
            break

    # Interaktywne pytanie o hasło gdy nie podano (i sieć nie jest otwarta)
    if password is None and not force_open and not force_ask:
        try:
            # Sprawdź czy sieć w ogóle jest zabezpieczona
            nets = _wifi_list_networks()
            secured = next((n["secured"] for n in nets if n["ssid"] == ssid), True)
        except Exception:
            secured = True

        if secured:
            _w(f"\n  {_A.DIM}Sieć '{_A.RESET}{_A.BCYAN}{ssid}{_A.RESET}{_A.DIM}' wymaga hasła{_A.RESET}\n")
            try:
                password = _read_password_masked(f"  {_A.BYELLOW}Hasło:{_A.RESET} ")
                if not password:
                    _w(f"  {_A.RED}✗{_A.RESET}  Hasło nie może być puste.\n\n")
                    return
            except KeyboardInterrupt:
                _w(f"  {_A.YELLOW}Anulowano.{_A.RESET}\n\n")
                return

    spin_stop, spin_t = _spinner_start(f"Łączenie z '{ssid}'...")

    try:
        if IS_WINDOWS:
            if password and not force_open:
                # Sprawdź czy profil już istnieje — nie nadpisuj bez powodu
                if _win_profile_exists(ssid):
                    _spinner_stop(spin_stop, spin_t)
                    _w(f"  {_A.DIM}Profil '{ssid}' już istnieje — używam istniejącego{_A.RESET}\n")
                    spin_stop, spin_t = _spinner_start(f"Łączenie z '{ssid}'...")
                else:
                    ok = _win_add_profile(ssid, password)
                    if not ok:
                        _spinner_stop(spin_stop, spin_t)
                        _w(f"  {_A.RED}✗{_A.RESET}  Nie udało się dodać profilu WiFi.\n\n")
                        return

            result = subprocess.run(
                ["netsh", "wlan", "connect", f"name={ssid}"],
                text=True, capture_output=True
            )
            _spinner_stop(spin_stop, spin_t)
            if result.returncode == 0:
                _w(f"  {_A.BGREEN}✓{_A.RESET}  Połączono z '{_A.BCYAN}{ssid}{_A.RESET}'\n")
                _verify_connection_post_connect(ssid)
            else:
                _w(f"  {_A.RED}✗{_A.RESET}  Błąd: {result.stdout.strip() or result.stderr.strip()}\n\n")

        elif IS_LINUX:
            NMCLI_TIMEOUT = 40
            try:
                if force_ask:
                    # Enterprise / EAP: przekaż do nmcli --ask (interaktywne)
                    _spinner_stop(spin_stop, spin_t)
                    _w(f"  {_A.DIM}Tryb enterprise — nmcli poprosi o dane uwierzytelnienia:{_A.RESET}\n\n")
                    subprocess.run(
                        ["nmcli", "--ask", "dev", "wifi", "connect", ssid],
                        timeout=120
                    )
                    spin_stop, spin_t = _spinner_start("Weryfikacja...")
                    result_rc = 0
                    err = ""
                elif password:
                    proc = subprocess.run(
                        ["nmcli", "dev", "wifi", "connect", ssid, "password", password],
                        text=True, capture_output=True, timeout=NMCLI_TIMEOUT
                    )
                    result_rc = proc.returncode
                    err = (proc.stderr or proc.stdout).strip()
                else:
                    proc = subprocess.run(
                        ["nmcli", "dev", "wifi", "connect", ssid],
                        text=True, capture_output=True, timeout=NMCLI_TIMEOUT
                    )
                    result_rc = proc.returncode
                    err = (proc.stderr or proc.stdout).strip()

                _spinner_stop(spin_stop, spin_t)

                if result_rc == 0:
                    _w(f"  {_A.BGREEN}✓{_A.RESET}  Połączono z '{_A.BCYAN}{ssid}{_A.RESET}'\n")
                    _verify_connection_post_connect(ssid)
                else:
                    # Obsługa "already connected"
                    if "already" in err.lower() and "connect" in err.lower():
                        _w(f"  {_A.BYELLOW}⚡{_A.RESET}  Już połączono z '{_A.BCYAN}{ssid}{_A.RESET}'\n")
                        _verify_connection_post_connect(ssid)
                    else:
                        _w(f"  {_A.RED}✗{_A.RESET}  Błąd nmcli: {err}\n\n")

            except subprocess.TimeoutExpired:
                _spinner_stop(spin_stop, spin_t)
                _w(
                    f"  {_A.RED}✗{_A.RESET}  Timeout po {NMCLI_TIMEOUT}s — "
                    f"sieć nie odpowiada lub błędne hasło\n"
                    f"  {_A.DIM}Sprawdź: nmcli dev status  |  journalctl -u NetworkManager -n 20{_A.RESET}\n\n"
                )
                return

            except FileNotFoundError:
                # Fallback: wpa_supplicant / wpa_cli
                _spinner_stop(spin_stop, spin_t)
                _w(f"  {_A.YELLOW}nmcli niedostępne — próba przez wpa_cli...{_A.RESET}\n")
                if password:
                    result = subprocess.run(
                        ["wpa_cli", "-i", _default_iface_linux(), "add_network"],
                        text=True, capture_output=True
                    )
                    net_id = result.stdout.strip()
                    cmds = [
                        ["wpa_cli", "set_network", net_id, "ssid",  f'"{ssid}"'],
                        ["wpa_cli", "set_network", net_id, "psk",   f'"{password}"'],
                        ["wpa_cli", "enable_network",  net_id],
                        ["wpa_cli", "select_network",  net_id],
                    ]
                    for c in cmds:
                        subprocess.run(c, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    _w(f"  {_A.BGREEN}✓{_A.RESET}  Żądanie połączenia wysłane (wpa_cli)\n")
                    _verify_connection_post_connect(ssid)
                else:
                    _w(f"  {_A.RED}✗{_A.RESET}  wpa_cli wymaga hasła lub konfiguracji wpa_supplicant.conf\n\n")
                return

        elif IS_MACOS:
            iface = "en0"
            if password:
                result = subprocess.run(
                    ["networksetup", "-setairportnetwork", iface, ssid, password],
                    text=True, capture_output=True
                )
            else:
                result = subprocess.run(
                    ["networksetup", "-setairportnetwork", iface, ssid],
                    text=True, capture_output=True
                )
            _spinner_stop(spin_stop, spin_t)
            if result.returncode == 0:
                _w(f"  {_A.BGREEN}✓{_A.RESET}  Połączono z '{_A.BCYAN}{ssid}{_A.RESET}'\n")
                _verify_connection_post_connect(ssid)
            else:
                err = (result.stderr or result.stdout).strip()
                _w(f"  {_A.RED}✗{_A.RESET}  Błąd: {err or 'nieznany błąd'}\n\n")

        else:
            _spinner_stop(spin_stop, spin_t)
            _w(f"  {_A.RED}System nieobsługiwany.{_A.RESET}\n\n")

    except subprocess.TimeoutExpired:
        _spinner_stop(spin_stop, spin_t)
        _w(f"  {_A.RED}✗{_A.RESET}  Timeout — sieć nie odpowiada lub błędne hasło.\n\n")
    except PermissionError:
        _spinner_stop(spin_stop, spin_t)
        _w(f"  {_A.RED}✗{_A.RESET}  Brak uprawnień. Spróbuj jako Administrator/root.\n\n")
    except KeyboardInterrupt:
        _spinner_stop(spin_stop, spin_t)
        _w(f"\n  {_A.YELLOW}Anulowano.{_A.RESET}\n\n")
    except Exception as e:
        _spinner_stop(spin_stop, spin_t)
        _w(f"  {_A.RED}✗{_A.RESET}  Błąd: {e}\n\n")


def _do_disconnect(args: list[str], terminal=None) -> None:
    """
    Rozłącza bieżące połączenie WiFi lub wybrany interfejs.

      wifi disconnect              — rozłącz domyślny interfejs
      wifi disconnect <interfejs>  — np. wifi disconnect wlan0
    """
    _w(f"\n  {_A.DIM}Rozłączanie...{_A.RESET}\n")

    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["netsh", "wlan", "disconnect"],
                text=True, capture_output=True
            )
            if result.returncode == 0:
                _w(f"  {_A.BGREEN}✓{_A.RESET}  Rozłączono.\n\n")
            else:
                _w(f"  {_A.RED}✗{_A.RESET}  {result.stdout.strip()}\n\n")

        elif IS_LINUX:
            iface = args[0] if args else _default_iface_linux()
            try:
                result = subprocess.run(
                    ["nmcli", "dev", "disconnect", iface],
                    text=True, capture_output=True
                )
                if result.returncode == 0:
                    _w(f"  {_A.BGREEN}✓{_A.RESET}  Rozłączono interfejs '{_A.BCYAN}{iface}{_A.RESET}'\n\n")
                else:
                    err = (result.stderr or result.stdout).strip()
                    _w(f"  {_A.RED}✗{_A.RESET}  {err}\n\n")
            except FileNotFoundError:
                subprocess.run(
                    ["ip", "link", "set", iface, "down"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                _w(f"  {_A.BGREEN}✓{_A.RESET}  Interfejs '{_A.BCYAN}{iface}{_A.RESET}' wyłączony (ip link set down)\n\n")

        elif IS_MACOS:
            iface = args[0] if args else "en0"
            result = subprocess.run(
                ["networksetup", "-setairportpower", iface, "off"],
                text=True, capture_output=True
            )
            subprocess.run(
                ["networksetup", "-setairportpower", iface, "on"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            _w(f"  {_A.BGREEN}✓{_A.RESET}  Rozłączono ('{_A.BCYAN}{iface}{_A.RESET}')\n\n")

        else:
            _w(f"  {_A.RED}System nieobsługiwany.{_A.RESET}\n\n")

    except PermissionError:
        _w(f"  {_A.RED}✗{_A.RESET}  Brak uprawnień. Spróbuj jako Administrator/root.\n\n")
    except Exception as e:
        _w(f"  {_A.RED}✗{_A.RESET}  Błąd: {e}\n\n")


# ── CrossTerm API ─────────────────────────────────────────────────────────────

CML_COMMANDS: dict = {
    "wifi"            : _do_scan,
    "wscan"           : _do_scan,
    "wifi scan"       : _do_scan,
    "wifi arp"        : _do_arp,
    "wifi info"       : _do_info,
    "wifi list"       : _do_list,
    "wifi connect"    : _do_connect,
    "wifi disconnect" : _do_disconnect,
    "wscan scan"      : _do_scan,
    "wscan arp"       : _do_arp,
    "wscan info"      : _do_info,
    "wscan list"      : _do_list,
    "wscan connect"   : _do_connect,
    "wscan disconnect": _do_disconnect,
}


def cml_menu() -> None:
    _w(f"\n{_A.BOLD}{_A.BCYAN}  ╔══════════════════════════════════════════════╗{_A.RESET}\n")
    _w(f"{_A.BOLD}{_A.BCYAN}  ║       WiFi Scanner  ─  wifi_scan  v1.4       ║{_A.RESET}\n")
    _w(f"{_A.BOLD}{_A.BCYAN}  ╚══════════════════════════════════════════════╝{_A.RESET}\n\n")
    cmds = [
        ("wifi scan",              "Skanuj (auto-wybór najszybszej metody)"),
        ("wifi scan --fast",       "Szybkie skanowanie (krótszy timeout)"),
        ("wifi scan --slow",       "Wolne skanowanie (duże opóźnienie sieci)"),
        ("wifi scan --arp",        "Wymuś ARP sweep [wymaga root]"),
        ("wifi scan --icmp",       "Wymuś raw ICMP  [wymaga root]"),
        ("wifi scan --ping",       "Wymuś subprocess ping [bez root]"),
        ("wifi scan 192.168.x/24", "Skanuj wybraną sieć"),
        ("wifi arp",               "Pokaż tablicę ARP"),
        ("wifi info",              "Pokaż interfejsy i dostępne metody"),
        ("wifi list",              "Lista dostępnych sieci WiFi"),
        ("wifi connect <SSID>",         "Połącz z siecią (profil / otwarta)"),
        ("wifi connect <SSID> <HASŁO>", "Połącz z siecią WPA/WPA2"),
        ("wifi connect <SSID> --ask",   "Połącz z siecią enterprise (nmcli --ask)"),
        ("wifi connect <SSID> --open",  "Wymuś połączenie bez hasła"),
        ("wifi disconnect",        "Rozłącz bieżące połączenie WiFi"),
        ("wifi disconnect <iface>","Rozłącz wybrany interfejs"),
    ]
    for cmd, desc in cmds:
        _w(f"  {_A.BYELLOW}{cmd:<34}{_A.RESET}  {_A.DIM}{desc}{_A.RESET}\n")
    _w("\n")


def on_load(terminal=None) -> None:
    pass  # komunikat startowy wyciszony


# ── Standalone ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        _do_scan([])
    elif args[0] in ("scan", "s"):
        _do_scan(args[1:])
    elif args[0] == "arp":
        _do_arp(args[1:])
    elif args[0] == "info":
        _do_info(args[1:])
    elif args[0] == "list":
        _do_list(args[1:])
    elif args[0] == "connect":
        _do_connect(args[1:])
    elif args[0] in ("disconnect", "dc"):
        _do_disconnect(args[1:])
    elif args[0].startswith("--") or "/" in args[0]:
        _do_scan(args)
    else:
        _w(
            f"  {_A.YELLOW}Użycie:{_A.RESET} wifi_scan.py [scan|arp|info|list|connect|disconnect] [opcje]\n"
            f"  Opcje skan: --fast  --slow  --arp  --icmp  --ping\n"
            f"  Przykłady:\n"
            f"    python wifi_scan.py\n"
            f"    sudo python wifi_scan.py --arp\n"
            f"    python wifi_scan.py scan 192.168.1.0/24 --fast\n"
            f"    python wifi_scan.py list\n"
            f"    python wifi_scan.py connect MojaSiec MojeHaslo\n"
            f"    python wifi_scan.py disconnect\n"
        )


# ─── EcoSystem core integration ───────────────────────────────────────────────

_SUBS = {
    "scan":       _do_scan,
    "arp":        _do_arp,
    "info":       _do_info,
    "list":       _do_list,
    "connect":    _do_connect,
    "disconnect": _do_disconnect,
    "dc":         _do_disconnect,
}


def _dispatch(args, terminal):
    """Dispatcher: wifi [sub] [args...]  lub  wifi (bez args → menu)."""
    if not args:
        cml_menu()
        return
    sub = args[0].lower()
    fn  = _SUBS.get(sub)
    if fn:
        fn(args[1:], terminal)
    else:
        # Brak pasującej subkomendy → zakładamy że to wifi scan z opcją/adresem
        _do_scan(args, terminal)


def setup(terminal):
    """Rejestruje komendy wifi/wscan w TerminalX EcoSystem."""
    cat = terminal.t("cat_general")

    def _wifi(args):  _dispatch(args, terminal)
    def _wscan(args): _dispatch(args, terminal)

    terminal.register_command(
        "wifi", _wifi,
        description=terminal.t("cmd_wifi"),
        category=cat,
    )
    terminal.register_command(
        "wscan", _wscan,
        description=terminal.t("cmd_wifi_alias"),
        category=cat,
    )

    on_load(terminal)


def teardown(terminal):
    """Wyrejestrowuje komendy wifi/wscan z TerminalX EcoSystem."""
    for cmd in ("wifi", "wscan"):
        terminal.commands.pop(cmd, None)
