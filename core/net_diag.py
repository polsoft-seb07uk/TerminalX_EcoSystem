#!/usr/bin/env python3
# autor:   Sebastian Januchowski
# company: polsoft.ITS(TM) Group
# web:     www.polsoft.gt.tc
# github:  https://github.com/seb07uk
# email:   polsoft.its@fastservice.com
# license: MIT
# crossterm: {"id": "13", "aliases": ["diagnet", "netdiag"], "description": "Diagnostyka sieci — IP, DNS, interfejsy, routing, testy poł.", "version": "1.1", "author": "Sebastian Januchowski"}
"""
Moduł Network Diagnostics v1.1
  diagnet / diagnet                — menu modułu

  [ NETWORK — BASIC ]
  diagnet netinfo                  — podstawowe informacje o sieci i interfejsach
  diagnet iplocal                  — lokalny adres IP
  diagnet ippublic                 — publiczny adres IP
  diagnet iflist                   — lista interfejsów sieciowych
  diagnet ifstatus                 — status interfejsów sieciowych
  diagnet macresolve <host>        — pobranie adresu MAC (ARP)
  diagnet gateway                  — adres bramy domyślnej
  diagnet routes                   — tabela routingu

  [ NETWORK — DNS ]
  diagnet dnslookup <domena>       — podstawowe zapytanie DNS
  diagnet dnsresolve <host>        — rozwiązywanie nazwy na adres IP
  diagnet dnsreverse <ip>          — reverse DNS (PTR)
  diagnet dnsrecord <domena> <typ> — pobieranie rekordów DNS (A/MX/TXT/...)
  diagnet dnstest <serwer> <host>  — test odpowiedzi serwera DNS
  diagnet dnssoa <domena>          — rekord SOA domeny
  diagnet dnsns <domena>           — rekordy NS domeny
  diagnet dnsaaaa <domena>         — rekordy AAAA IPv6
  diagnet dnsaaaaa <domena>        — rozszerzone rekordy IPv6
  diagnet dnsall <domena>          — wszystkie dostępne rekordy DNS

  [ NETWORK — CONNECTION TESTING ]
  diagnet netping <host> [n]       — test połączenia TCP (ICMP fallback)
  diagnet tcping <host> <port> [n] — pomiar opóźnienia TCP
  diagnet httpping <url> [n]       — pomiar opóźnienia HTTP
  diagnet httpget <url>            — pobranie zasobu HTTP
  diagnet httpsget <url>           — pobranie zasobu HTTPS
  diagnet httphead <url>           — nagłówki HTTP HEAD
  diagnet portcheck <host> <port>  — sprawdzenie czy port jest otwarty
  diagnet portscan <host> [ports]  — skanowanie portów (popularne)
  diagnet portscan-fast <host>     — szybkie skanowanie portów (top 100)
  diagnet portscan-deep <host>     — głębokie skanowanie portów (1-65535)

  [ NETWORK — SOCKET / PROTOCOL ]
  diagnet socktest                 — test tworzenia gniazda
  diagnet socktcp <host> <port>    — test połączenia TCP
  diagnet sockudp <host> <port>    — test połączenia UDP
  diagnet sockraw [host]           — test gniazda RAW
  diagnet sockecho <tcp|udp> <host> <port> — echo test TCP/UDP
  diagnet socklatency <tcp|udp> <host> <port> [n] — pomiar opóźnienia socketów

  [ NETWORK — DISCOVERY / ENUMERATION ]
  diagnet netscan                  — skanowanie sieci lokalnej
  diagnet subnetscan <CIDR>        — skanowanie podsieci
  diagnet hostscan <host|CIDR>     — wykrywanie aktywnych hostów
  diagnet servicedetect <host> <port> — wykrywanie usług na porcie
  diagnet bannergrab <host> <port> — pobieranie banera usługi
  diagnet fingerprint <host> [port] — identyfikacja systemu zdalnego
  diagnet arpdiscover              — skanowanie ARP
  diagnet neighbordiscover         — wykrywanie sąsiadów sieciowych

  [ NETWORK — SECURITY / VISIBILITY ]
  diagnet firewallcheck            — test działania zapory
  diagnet proxycheck               — wykrywanie proxy
  diagnet vpnstatus                — wykrywanie aktywnego VPN
  diagnet torcheck                 — wykrywanie ruchu przez TOR
  diagnet dnsleak                  — test wycieku DNS
  diagnet portvisibility           — widoczność portów z zewnątrz
  diagnet openports                — lista otwartych portów
  diagnet blockedports             — lista zablokowanych portów
"""

import sys
import os
import socket
import platform
import subprocess
import struct
import re
import time
import ipaddress
from typing import List, Optional, Tuple, Dict, Any

_sys = sys

def _w(s):
    _sys.stdout.write(s)
    _sys.stdout.flush()

class _C:
    RESET   = "\x1b[0m";  BOLD    = "\x1b[1m";  DIM     = "\x1b[2m"
    BCYAN   = "\x1b[96m"; BYELLOW = "\x1b[93m"; BGREEN  = "\x1b[92m"
    BWHITE  = "\x1b[97m"; RED     = "\x1b[91m"; CYAN    = "\x1b[36m"
    MAGENTA = "\x1b[95m"; YELLOW  = "\x1b[33m"; BLUE    = "\x1b[94m"
    GREEN   = "\x1b[32m"; GRAY    = "\x1b[90m"

_ANSI = re.compile(r'\x1b\[[0-9;]*[mA-Z]')

def _vis(s):
    return len(_ANSI.sub('', s))

def _pad(s, width):
    return s + ' ' * max(0, width - _vis(s))

_OS = platform.system()   # 'Windows', 'Linux', 'Darwin'

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd: List[str], timeout: int = 6) -> Tuple[int, str, str]:
    """Run a subprocess, return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
            errors='replace'
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, '', f'Komenda nie znaleziona: {cmd[0]}'
    except subprocess.TimeoutExpired:
        return -1, '', 'Timeout'
    except Exception as e:
        return -1, '', str(e)


def _section(title: str):
    _w(f"\n{_C.BOLD}{_C.BCYAN}  ── {title} ──{_C.RESET}\n\n")


def _row(label: str, value: str, label_w: int = 22):
    lbl = _pad(f"  {_C.BYELLOW}{label}{_C.RESET}", label_w + len(_C.BYELLOW) + len(_C.RESET) + 2)
    _w(f"{lbl} {value}\n")


def _ok(msg: str):
    _w(f"  {_C.BGREEN}[OK]{_C.RESET} {msg}\n")


def _err(msg: str):
    _w(f"  {_C.RED}[ERR]{_C.RESET} {msg}\n")


def _warn(msg: str):
    _w(f"  {_C.YELLOW}[!]{_C.RESET} {msg}\n")


def _hr(char: str = '─', width: int = 56):
    _w(f"  {_C.DIM}{char * width}{_C.RESET}\n")


# ─── DNS via socket (no external deps) ────────────────────────────────────────

def _resolve_a(host: str) -> List[str]:
    """Resolve A records (IPv4) via getaddrinfo."""
    try:
        results = socket.getaddrinfo(host, None, socket.AF_INET)
        return list(dict.fromkeys(r[4][0] for r in results))
    except socket.gaierror:
        return []


def _resolve_aaaa(host: str) -> List[str]:
    """Resolve AAAA records (IPv6) via getaddrinfo."""
    try:
        results = socket.getaddrinfo(host, None, socket.AF_INET6)
        return list(dict.fromkeys(r[4][0] for r in results))
    except socket.gaierror:
        return []


def _reverse_dns(ip: str) -> str:
    """PTR lookup."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except socket.herror:
        return '(brak rekordu PTR)'
    except Exception as e:
        return f'(błąd: {e})'


def _dns_tool_available() -> Optional[str]:
    """Return first available DNS CLI tool."""
    for tool in ('dig', 'nslookup', 'host'):
        rc, _, _ = _run([tool, '--version'] if tool == 'dig' else [tool, 'localhost'],
                        timeout=3)
        if rc != -1:
            return tool
    return None


def _dig_query(domain: str, rtype: str, server: str = '') -> Tuple[bool, str]:
    """Run dig/nslookup query, return (success, raw_output)."""
    # Try dig first
    cmd_dig = ['dig', '+noall', '+answer', domain, rtype]
    if server:
        cmd_dig.insert(1, f'@{server}')
    rc, out, _ = _run(cmd_dig)
    if rc == 0 and out:
        return True, out

    # Fallback: nslookup
    cmd_ns = ['nslookup', f'-type={rtype}', domain]
    if server:
        cmd_ns.append(server)
    rc, out, _ = _run(cmd_ns)
    if rc == 0:
        return True, out

    # Fallback: host (Linux/Mac)
    if rtype == 'A':
        rc, out, _ = _run(['host', domain])
        if rc == 0:
            return True, out

    return False, ''


def _local_ip() -> str:
    """Get primary local IP without network call."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '(niedostępny)'


def _public_ip() -> str:
    """Fetch public IP via HTTP (stdlib only)."""
    try:
        import urllib.request
        services = [
            'https://api.ipify.org',
            'https://checkip.amazonaws.com',
            'https://icanhazip.com',
        ]
        for url in services:
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    return resp.read().decode().strip()
            except Exception:
                continue
        return '(niedostępny)'
    except Exception:
        return '(niedostępny)'


def _get_interfaces() -> List[Dict[str, Any]]:
    """Return list of network interfaces with IP info, cross-platform."""
    ifaces = []

    if _OS == 'Windows':
        rc, out, _ = _run(['ipconfig', '/all'])
        if rc == 0:
            current: Dict[str, Any] = {}
            for line in out.splitlines():
                line = line.rstrip()
                # New adapter block
                if line and not line.startswith(' '):
                    if current.get('name'):
                        ifaces.append(current)
                    name = line.rstrip(':').rstrip('.')
                    current = {'name': name, 'ipv4': [], 'ipv6': [], 'mac': '', 'status': 'unknown'}
                elif 'IPv4' in line or 'IP Address' in line:
                    m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', line)
                    if m:
                        current.setdefault('ipv4', []).append(m.group(1))
                elif 'IPv6' in line:
                    m = re.search(r'([0-9a-fA-F:]{5,})', line)
                    if m and '::' not in m.group(1) or True:
                        current.setdefault('ipv6', []).append(m.group(1))
                elif 'Physical' in line or 'MAC' in line:
                    m = re.search(r'([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}', line)
                    if m:
                        current['mac'] = m.group(0)
                elif 'Media State' in line:
                    current['status'] = 'disconnected' if 'disconnected' in line.lower() else 'connected'
            if current.get('name'):
                ifaces.append(current)
    else:
        # Linux / macOS — try ip addr, fallback ifconfig
        rc, out, _ = _run(['ip', 'addr'])
        if rc == 0:
            current = {}
            for line in out.splitlines():
                m_iface = re.match(r'^\d+:\s+(\S+):', line)
                if m_iface:
                    if current.get('name'):
                        ifaces.append(current)
                    current = {
                        'name': m_iface.group(1),
                        'ipv4': [], 'ipv6': [], 'mac': '',
                        'status': 'UP' if 'UP' in line else 'DOWN'
                    }
                elif 'link/ether' in line:
                    m = re.search(r'link/ether\s+([0-9a-f:]+)', line)
                    if m:
                        current['mac'] = m.group(1)
                elif 'inet ' in line:
                    m = re.search(r'inet\s+(\d{1,3}(?:\.\d{1,3}){3})', line)
                    if m:
                        current.setdefault('ipv4', []).append(m.group(1))
                elif 'inet6' in line:
                    m = re.search(r'inet6\s+([0-9a-fA-F:]+)', line)
                    if m:
                        current.setdefault('ipv6', []).append(m.group(1))
            if current.get('name'):
                ifaces.append(current)
        else:
            # fallback: ifconfig
            rc, out, _ = _run(['ifconfig'])
            if rc == 0:
                current = {}
                for line in out.splitlines():
                    m_iface = re.match(r'^(\S+)', line)
                    if m_iface and not line.startswith('\t') and not line.startswith(' '):
                        if current.get('name'):
                            ifaces.append(current)
                        current = {
                            'name': m_iface.group(1).rstrip(':'),
                            'ipv4': [], 'ipv6': [], 'mac': '', 'status': 'UP'
                        }
                    elif 'inet ' in line:
                        m = re.search(r'inet\s+(\d{1,3}(?:\.\d{1,3}){3})', line)
                        if m:
                            current.setdefault('ipv4', []).append(m.group(1))
                    elif 'inet6' in line:
                        m = re.search(r'inet6\s+([0-9a-fA-F:]+)', line)
                        if m:
                            current.setdefault('ipv6', []).append(m.group(1))
                    elif 'ether' in line:
                        m = re.search(r'ether\s+([0-9a-f:]+)', line)
                        if m:
                            current['mac'] = m.group(1)
                if current.get('name'):
                    ifaces.append(current)

    return ifaces


def _default_gateway() -> str:
    """Return default gateway address, cross-platform."""
    if _OS == 'Windows':
        rc, out, _ = _run(['ipconfig'])
        for line in out.splitlines():
            if 'Default Gateway' in line or 'Brama domyślna' in line:
                m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', line)
                if m:
                    return m.group(1)
    else:
        # ip route
        rc, out, _ = _run(['ip', 'route'])
        if rc == 0:
            for line in out.splitlines():
                if line.startswith('default'):
                    m = re.search(r'via\s+(\S+)', line)
                    if m:
                        return m.group(1)
        # fallback: netstat -rn
        rc, out, _ = _run(['netstat', '-rn'])
        if rc == 0:
            for line in out.splitlines():
                if line.startswith('0.0.0.0') or line.startswith('default'):
                    parts = line.split()
                    if len(parts) >= 2:
                        gw = parts[1] if parts[1] not in ('0.0.0.0', 'UG', '*') else (parts[2] if len(parts) > 2 else '')
                        if re.match(r'\d{1,3}(?:\.\d{1,3}){3}', gw):
                            return gw
    return '(nie znaleziono)'


# ═══════════════════════════════════════════════════════════════════════════════
# NETWORK — BASIC
# ═══════════════════════════════════════════════════════════════════════════════

def _cmd_net_menu(args, terminal):
    """Menu główne modułu."""
    if args:
        subcmd = args[0]
        fullcmd = f"diagnet.{subcmd}"
        if fullcmd in CML_COMMANDS:
            return CML_COMMANDS[fullcmd](args[1:], terminal)
        _warn(f"Nieznana komenda sieciowa: {subcmd}")
        _w(f"  {_C.DIM}Użyj: diagnet <komenda> [argumenty]{_C.RESET}\n\n")
        return

    _w(f"\n{_C.BOLD}{_C.BCYAN}  ╭────────────────────────────────────────╮{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  │    Network Diagnostics  v1.0            │{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  ╰────────────────────────────────────────╯{_C.RESET}\n\n")

    _w(f"  {_C.BOLD}{_C.BWHITE}[ NETWORK — BASIC ]{_C.RESET}\n")
    cmds_basic = [
        ("netinfo",              "podstawowe informacje o sieci i interfejsach"),
        ("iplocal",              "lokalny adres IP"),
        ("ippublic",             "publiczny adres IP (wymaga internetu)"),
        ("iflist",               "lista interfejsów sieciowych"),
        ("ifstatus",             "status interfejsów sieciowych"),
        ("macresolve <host>",    "pobranie adresu MAC z tablicy ARP"),
        ("gateway",              "adres bramy domyślnej"),
        ("routes",               "tabela routingu"),
    ]
    for cmd, desc in cmds_basic:
        _w(f"  {_C.BYELLOW}{_pad(cmd, 26)}{_C.RESET} {_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BOLD}{_C.BWHITE}[ NETWORK — DNS ]{_C.RESET}\n")
    cmds_dns = [
        ("dnslookup <domena>",        "podstawowe zapytanie DNS (A)"),
        ("dnsresolve <host>",         "rozwiązywanie nazwy na adres IP"),
        ("dnsreverse <ip>",           "reverse DNS (rekord PTR)"),
        ("dnsrecord <domena> <typ>",  "pobieranie rekordów DNS (A/MX/TXT/...)"),
        ("dnstest <serwer> <host>",   "test odpowiedzi serwera DNS"),
        ("dnssoa <domena>",           "rekord SOA domeny"),
        ("dnsns <domena>",            "rekordy NS domeny"),
        ("dnsaaaa <domena>",          "rekordy AAAA IPv6"),
        ("dnsaaaaa <domena>",         "rozszerzone rekordy IPv6 (AAAA + PTR)"),
        ("dnsall <domena>",           "wszystkie dostępne rekordy DNS"),
    ]
    for cmd, desc in cmds_dns:
        _w(f"  {_C.BYELLOW}{_pad(cmd, 26)}{_C.RESET} {_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BOLD}{_C.BWHITE}[ NETWORK — CONNECTION TESTING ]{_C.RESET}\n")
    cmds_conn = [
        ("netping <host> [n]",       "test połączenia TCP (ICMP fallback)"),
        ("tcping <host> <port> [n]", "pomiar opóźnienia TCP"),
        ("httpping <url> [n]",       "pomiar opóźnienia HTTP"),
        ("httpget <url>",            "pobranie zasobu HTTP"),
        ("httpsget <url>",           "pobranie zasobu HTTPS"),
        ("httphead <url>",            "nagłówki HTTP HEAD (jak net head)"),
        ("portcheck <host> <port>",  "sprawdzenie czy port jest otwarty"),
        ("portscan <host> [ports]",  "skanowanie portów (popularne)"),
        ("portscan-fast <host>",     "szybkie skanowanie portów (top 100)"),
        ("portscan-deep <host>",     "głębokie skanowanie portów (1-65535)"),
    ]
    for cmd, desc in cmds_conn:
        _w(f"  {_C.BYELLOW}{_pad(cmd, 26)}{_C.RESET} {_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BOLD}{_C.BWHITE}[ NETWORK — SOCKET / PROTOCOL ]{_C.RESET}\n")
    cmds_socket = [
        ("socktest",                "test tworzenia gniazda"),
        ("socktcp <host> <port>",   "test połączenia TCP"),
        ("sockudp <host> <port>",   "test połączenia UDP"),
        ("sockraw [host]",          "test gniazda RAW"),
        ("sockecho <tcp|udp> <host> <port>", "echo test TCP/UDP"),
        ("socklatency <tcp|udp> <host> <port> [n]", "pomiar opóźnienia socketów"),
    ]
    for cmd, desc in cmds_socket:
        _w(f"  {_C.BYELLOW}{_pad(cmd, 26)}{_C.RESET} {_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BOLD}{_C.BWHITE}[ NETWORK — DISCOVERY / ENUMERATION ]{_C.RESET}\n")
    cmds_discovery = [
        ("netscan",                "skanowanie sieci lokalnej"),
        ("subnetscan <CIDR>",      "skanowanie podsieci"),
        ("hostscan <host|CIDR>",   "wykrywanie aktywnych hostów"),
        ("servicedetect <host> <port>", "wykrywanie usług na porcie"),
        ("bannergrab <host> <port>", "pobieranie banera usługi"),
        ("fingerprint <host> [port]", "identyfikacja systemu zdalnego"),
        ("arpdiscover",            "skanowanie ARP"),
        ("neighbordiscover",       "wykrywanie sąsiadów sieciowych"),
    ]
    for cmd, desc in cmds_discovery:
        _w(f"  {_C.BYELLOW}{_pad(cmd, 26)}{_C.RESET} {_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.BOLD}{_C.BWHITE}[ NETWORK — SECURITY / VISIBILITY ]{_C.RESET}\n")
    cmds_security = [
        ("firewallcheck",           "test działania zapory"),
        ("proxycheck",              "wykrywanie proxy"),
        ("vpnstatus",               "wykrywanie aktywnego VPN"),
        ("torcheck",                "wykrywanie ruchu przez TOR"),
        ("dnsleak",                 "test wycieku DNS"),
        ("portvisibility",          "widoczność portów z zewnątrz"),
        ("openports",               "lista otwartych portów"),
        ("blockedports",            "lista zablokowanych portów"),
    ]
    for cmd, desc in cmds_security:
        _w(f"  {_C.BYELLOW}{_pad(cmd, 26)}{_C.RESET} {_C.DIM}{desc}{_C.RESET}\n")

    _w(f"\n  {_C.DIM}Użycie: diagnet <komenda> [argumenty]{_C.RESET}\n\n")


def _cmd_netinfo(args, terminal):
    """Podstawowe informacje o sieci i interfejsach."""
    _section("Network Info")

    hostname = socket.gethostname()
    _row("Hostname",    f"{_C.BWHITE}{hostname}{_C.RESET}")
    _row("System OS",   f"{_C.BWHITE}{_OS} {platform.release()}{_C.RESET}")

    ip_local = _local_ip()
    _row("IP lokalny",  f"{_C.BGREEN}{ip_local}{_C.RESET}")

    gw = _default_gateway()
    _row("Brama (GW)",  f"{_C.CYAN}{gw}{_C.RESET}")

    # Hostname resolution
    try:
        resolved = socket.gethostbyname(hostname)
        _row("FQDN → IP", f"{_C.CYAN}{resolved}{_C.RESET}")
    except Exception:
        _row("FQDN → IP", f"{_C.RED}(błąd rozwiązywania){_C.RESET}")

    _hr()
    ifaces = _get_interfaces()
    active = [i for i in ifaces if i.get('ipv4') or i.get('ipv6')]
    _w(f"  Interfejsy aktywne: {_C.BGREEN}{len(active)}{_C.RESET} / {_C.BWHITE}{len(ifaces)}{_C.RESET} łącznie\n")
    for iface in active[:6]:
        ips = ', '.join(iface.get('ipv4', []))
        _w(f"  {_C.BYELLOW}{_pad(iface['name'], 14)}{_C.RESET} {_C.BGREEN}{ips}{_C.RESET}\n")
    _w("\n")


def _cmd_iplocal(args, terminal):
    """Lokalny adres IP."""
    _section("IP Lokalny")
    ip = _local_ip()
    _w(f"  {_C.BGREEN}{ip}{_C.RESET}\n\n")


def _cmd_ippublic(args, terminal):
    """Publiczny adres IP."""
    _section("IP Publiczny")
    _w(f"  {_C.DIM}Łączenie z serwisem zewnętrznym...{_C.RESET}\n")
    ip = _public_ip()
    _w(f"  {_C.BGREEN}{ip}{_C.RESET}\n\n")


def _cmd_iflist(args, terminal):
    """Lista interfejsów sieciowych."""
    _section("Lista interfejsów")
    ifaces = _get_interfaces()
    if not ifaces:
        _err("Brak danych o interfejsach.")
        _w("\n")
        return

    _w(f"  {_C.BOLD}{_pad('Interfejs', 16)}{_pad('MAC', 20)}{_pad('IPv4', 18)}{_C.RESET}\n")
    _hr()
    for iface in ifaces:
        name  = iface.get('name', '?')
        mac   = iface.get('mac', '—')
        ipv4s = ', '.join(iface.get('ipv4', [])) or '—'
        _w(f"  {_C.BYELLOW}{_pad(name, 16)}{_C.RESET}"
           f"{_C.DIM}{_pad(mac, 20)}{_C.RESET}"
           f"{_C.BGREEN}{ipv4s}{_C.RESET}\n")
    _w("\n")


def _cmd_ifstatus(args, terminal):
    """Status interfejsów sieciowych."""
    _section("Status interfejsów")
    ifaces = _get_interfaces()
    if not ifaces:
        _err("Brak danych o interfejsach.")
        _w("\n")
        return

    for iface in ifaces:
        name   = iface.get('name', '?')
        status = iface.get('status', 'unknown')
        has_ip = bool(iface.get('ipv4') or iface.get('ipv6'))

        if has_ip:
            status_str = f"{_C.BGREEN}[AKTYWNY]{_C.RESET}"
        elif 'down' in str(status).lower() or 'disconnected' in str(status).lower():
            status_str = f"{_C.RED}[DOWN]{_C.RESET}"
        else:
            status_str = f"{_C.YELLOW}[BRAK IP]{_C.RESET}"

        ipv4s = ', '.join(iface.get('ipv4', [])) or ''
        ipv6s = ', '.join(iface.get('ipv6', [])[:1]) or ''
        detail = ipv4s or ipv6s or '—'

        _w(f"  {status_str} {_C.BYELLOW}{_pad(name, 18)}{_C.RESET} {_C.DIM}{detail}{_C.RESET}\n")
    _w("\n")


def _cmd_macresolve(args, terminal):
    """Pobranie adresu MAC z tablicy ARP."""
    _section("MAC Resolve (ARP)")
    if not args:
        _warn("Użycie: diagnet macresolve <host|ip>")
        _w("\n")
        return

    target = args[0]
    _w(f"  Target: {_C.BYELLOW}{target}{_C.RESET}\n\n")

    # First try to ping to populate ARP cache
    ping_cmd = ['ping', '-n', '1', target] if _OS == 'Windows' else ['ping', '-c', '1', '-W', '2', target]
    _run(ping_cmd, timeout=5)

    # Read ARP table
    if _OS == 'Windows':
        rc, out, _ = _run(['arp', '-a'])
    else:
        rc, out, _ = _run(['arp', '-n'])
        if rc != 0:
            rc, out, _ = _run(['ip', 'neigh'])

    if rc != 0 or not out:
        _err("Nie można odczytać tablicy ARP.")
        _w("\n")
        return

    # Resolve target to IP first
    try:
        target_ip = socket.gethostbyname(target)
    except Exception:
        target_ip = target

    found = False
    mac_pattern = re.compile(r'([0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}'
                              r'[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2})')
    for line in out.splitlines():
        if target_ip in line or target in line:
            m = mac_pattern.search(line)
            if m:
                _ok(f"MAC: {_C.BGREEN}{m.group(1)}{_C.RESET}  ({_C.DIM}IP: {target_ip}{_C.RESET})")
                found = True
                break

    if not found:
        _warn(f"Adres MAC dla '{target}' ({target_ip}) nie znaleziony w tablicy ARP.")
        _w(f"  {_C.DIM}(Host może być poza siecią lokalną lub ARP wygasł){_C.RESET}\n")
    _w("\n")


def _cmd_gateway(args, terminal):
    """Adres bramy domyślnej."""
    _section("Brama domyślna (Gateway)")
    gw = _default_gateway()
    _w(f"  {_C.BGREEN}{gw}{_C.RESET}")
    if re.match(r'\d{1,3}(?:\.\d{1,3}){3}', gw):
        hostname = _reverse_dns(gw)
        _w(f"  {_C.DIM}({hostname}){_C.RESET}")
    _w("\n\n")


def _cmd_routes(args, terminal):
    """Tabela routingu."""
    _section("Tabela routingu")

    if _OS == 'Windows':
        rc, out, _ = _run(['route', 'print'])
        if rc == 0:
            # Parse IPv4 route table section
            in_section = False
            _w(f"  {_C.BOLD}{_pad('Sieć docelowa', 18)}{_pad('Maska', 16)}{_pad('Brama', 16)}{_pad('Iface', 16)}{'Metryka':>8}{_C.RESET}\n")
            _hr()
            for line in out.splitlines():
                if 'IPv4 Route' in line or 'Trasy IPv4' in line:
                    in_section = True
                    continue
                if 'IPv6' in line and in_section:
                    break
                if in_section:
                    parts = line.split()
                    if len(parts) >= 5 and re.match(r'\d+\.\d+', parts[0]):
                        diagnet, mask, gw, iface, metric = parts[0], parts[1], parts[2], parts[3], parts[4]
                        _w(f"  {_C.CYAN}{_pad(diagnet, 18)}{_C.RESET}"
                           f"{_C.DIM}{_pad(mask, 16)}{_C.RESET}"
                           f"{_C.BYELLOW}{_pad(gw, 16)}{_C.RESET}"
                           f"{_C.DIM}{_pad(iface, 16)}{_C.RESET}"
                           f"{_C.DIM}{metric:>8}{_C.RESET}\n")
    else:
        rc, out, _ = _run(['ip', 'route'])
        if rc == 0:
            _w(f"  {_C.BOLD}Tablica routingu (ip route):{_C.RESET}\n\n")
            for line in out.splitlines():
                if line.startswith('default'):
                    _w(f"  {_C.BGREEN}{line}{_C.RESET}\n")
                else:
                    parts = line.split()
                    dest = parts[0] if parts else line
                    rest = ' '.join(parts[1:])
                    _w(f"  {_C.CYAN}{_pad(dest, 22)}{_C.RESET}{_C.DIM}{rest}{_C.RESET}\n")
        else:
            rc, out, _ = _run(['netstat', '-rn'])
            if rc == 0:
                for line in out.splitlines():
                    _w(f"  {_C.DIM}{line}{_C.RESET}\n")
            else:
                _err("Nie można odczytać tablicy routingu.")
    _w("\n")


# ═══════════════════════════════════════════════════════════════════════════════
# NETWORK — DNS
# ═══════════════════════════════════════════════════════════════════════════════

def _cmd_dnslookup(args, terminal):
    """Podstawowe zapytanie DNS (typ A)."""
    _section("DNS Lookup")
    if not args:
        _warn("Użycie: diagnet dnslookup <domena>")
        _w("\n")
        return

    domain = args[0]
    _w(f"  Domena:   {_C.BYELLOW}{domain}{_C.RESET}\n")
    _w(f"  Typ:      {_C.DIM}A (IPv4){_C.RESET}\n\n")

    t0 = time.time()
    ips = _resolve_a(domain)
    elapsed = (time.time() - t0) * 1000

    if ips:
        for ip in ips:
            _ok(f"{_C.BGREEN}{ip}{_C.RESET}")
        _w(f"\n  {_C.DIM}Czas: {elapsed:.1f} ms{_C.RESET}\n")
    else:
        _err(f"Brak rekordów A dla '{domain}'")
    _w("\n")


def _cmd_dnsresolve(args, terminal):
    """Rozwiązywanie nazwy na adres IP (A + AAAA)."""
    _section("DNS Resolve")
    if not args:
        _warn("Użycie: diagnet dnsresolve <host>")
        _w("\n")
        return

    host = args[0]
    _w(f"  Host: {_C.BYELLOW}{host}{_C.RESET}\n\n")

    # IPv4
    t0 = time.time()
    ipv4 = _resolve_a(host)
    t4 = (time.time() - t0) * 1000

    # IPv6
    t0 = time.time()
    ipv6 = _resolve_aaaa(host)
    t6 = (time.time() - t0) * 1000

    if ipv4:
        _w(f"  {_C.BGREEN}IPv4 (A):{_C.RESET}\n")
        for ip in ipv4:
            _w(f"    {_C.BWHITE}{ip}{_C.RESET}\n")
        _w(f"  {_C.DIM}  → {t4:.1f} ms{_C.RESET}\n\n")
    else:
        _warn("Brak rekordów A (IPv4)")

    if ipv6:
        _w(f"  {_C.BLUE}IPv6 (AAAA):{_C.RESET}\n")
        for ip in ipv6:
            _w(f"    {_C.BWHITE}{ip}{_C.RESET}\n")
        _w(f"  {_C.DIM}  → {t6:.1f} ms{_C.RESET}\n\n")
    else:
        _w(f"  {_C.DIM}Brak rekordów AAAA (IPv6){_C.RESET}\n\n")


def _cmd_dnsreverse(args, terminal):
    """Reverse DNS (rekord PTR)."""
    _section("DNS Reverse (PTR)")
    if not args:
        _warn("Użycie: diagnet dnsreverse <adres_IP>")
        _w("\n")
        return

    ip = args[0]
    _w(f"  IP: {_C.BYELLOW}{ip}{_C.RESET}\n\n")

    t0 = time.time()
    hostname = _reverse_dns(ip)
    elapsed = (time.time() - t0) * 1000

    if hostname.startswith('('):
        _warn(f"PTR: {hostname}")
    else:
        _ok(f"PTR: {_C.BGREEN}{hostname}{_C.RESET}")

    _w(f"  {_C.DIM}Czas: {elapsed:.1f} ms{_C.RESET}\n\n")


def _cmd_dnsrecord(args, terminal):
    """Pobieranie rekordów DNS określonego typu."""
    _section("DNS Record")
    if len(args) < 2:
        _warn("Użycie: diagnet dnsrecord <domena> <typ>")
        _w(f"  {_C.DIM}Typy: A, AAAA, MX, TXT, NS, SOA, CNAME, PTR{_C.RESET}\n\n")
        return

    domain, rtype = args[0], args[1].upper()
    _w(f"  Domena: {_C.BYELLOW}{domain}{_C.RESET}   Typ: {_C.BCYAN}{rtype}{_C.RESET}\n\n")

    # Socket fallbacks for basic types
    if rtype == 'A':
        ips = _resolve_a(domain)
        if ips:
            for ip in ips:
                _w(f"  {_C.BGREEN}{domain:<40} A    {ip}{_C.RESET}\n")
        else:
            _warn("Brak rekordów A")
        _w("\n")
        return

    if rtype == 'AAAA':
        ips = _resolve_aaaa(domain)
        if ips:
            for ip in ips:
                _w(f"  {_C.BLUE}{domain:<40} AAAA {ip}{_C.RESET}\n")
        else:
            _warn("Brak rekordów AAAA")
        _w("\n")
        return

    # For other types: try dig/nslookup
    ok, out = _dig_query(domain, rtype)
    if ok and out:
        _w(f"  {_C.BWHITE}")
        for line in out.splitlines():
            if line.strip():
                _w(f"  {line}\n")
        _w(f"{_C.RESET}")
    else:
        _warn(f"Brak wyników dla {rtype} lub narzędzia dig/nslookup niedostępne.")
        _w(f"  {_C.DIM}(zainstaluj 'bind-utils' lub 'dnsutils' aby użyć dig){_C.RESET}\n")
    _w("\n")


def _cmd_dnstest(args, terminal):
    """Test odpowiedzi serwera DNS."""
    _section("DNS Server Test")
    if len(args) < 2:
        _warn("Użycie: diagnet dnstest <serwer_dns> <host>")
        _w(f"  {_C.DIM}Przykład: diagnet dnstest 8.8.8.8 google.com{_C.RESET}\n\n")
        return

    server, host = args[0], args[1]
    _w(f"  Serwer DNS: {_C.BYELLOW}{server}{_C.RESET}\n")
    _w(f"  Zapytanie:  {_C.BYELLOW}{host}{_C.RESET}\n\n")

    # Test via socket with custom DNS server
    def query_with_server(dns_server: str, hostname: str) -> Tuple[bool, str, float]:
        """Build a minimal DNS A query and send it via UDP."""
        try:
            # Build minimal DNS query packet
            txid = os.urandom(2)
            flags = b'\x01\x00'      # standard query, recursion desired
            qdcount = b'\x00\x01'
            ancount = b'\x00\x00'
            nscount = b'\x00\x00'
            arcount = b'\x00\x00'
            header = txid + flags + qdcount + ancount + nscount + arcount

            # Encode QNAME
            qname = b''
            for label in hostname.split('.'):
                encoded = label.encode()
                qname += bytes([len(encoded)]) + encoded
            qname += b'\x00'

            qtype  = b'\x00\x01'   # A record
            qclass = b'\x00\x01'   # IN
            question = qname + qtype + qclass
            packet = header + question

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(4)
            t0 = time.time()
            sock.sendto(packet, (dns_server, 53))
            data, _ = sock.recvfrom(512)
            elapsed = (time.time() - t0) * 1000
            sock.close()

            # Parse response: check ANCOUNT
            ancount_val = (data[6] << 8) | data[7]
            rcode = data[3] & 0x0F

            if rcode == 0 and ancount_val > 0:
                return True, f"{ancount_val} rekord(y)", elapsed
            elif rcode == 3:
                return False, "NXDOMAIN (domena nie istnieje)", elapsed
            elif rcode != 0:
                return False, f"RCODE={rcode}", elapsed
            else:
                return True, "OK (brak odpowiedzi w sekcji AN)", elapsed
        except socket.timeout:
            return False, "Timeout (>4s)", 0.0
        except Exception as e:
            return False, str(e), 0.0

    success, detail, ms = query_with_server(server, host)
    if success:
        _ok(f"Serwer {_C.BYELLOW}{server}{_C.RESET} odpowiedział: {_C.BGREEN}{detail}{_C.RESET}")
        _w(f"  {_C.DIM}Czas odpowiedzi: {ms:.1f} ms{_C.RESET}\n")
    else:
        _err(f"Serwer {server} nie odpowiedział: {detail}")

    # Compare with system resolver
    _w(f"\n  {_C.DIM}Porównanie z systemowym resolverem:{_C.RESET}\n")
    ips = _resolve_a(host)
    if ips:
        _ok(f"System resolver: {_C.BGREEN}{', '.join(ips)}{_C.RESET}")
    else:
        _err("System resolver: brak odpowiedzi")
    _w("\n")


def _cmd_dnssoa(args, terminal):
    """Rekord SOA domeny."""
    _section("DNS SOA")
    if not args:
        _warn("Użycie: diagnet dnssoa <domena>")
        _w("\n")
        return

    domain = args[0]
    _w(f"  Domena: {_C.BYELLOW}{domain}{_C.RESET}\n\n")

    ok, out = _dig_query(domain, 'SOA')
    if ok and out:
        _w(f"  {_C.BWHITE}")
        for line in out.splitlines():
            if 'SOA' in line or line.strip():
                # Try to parse SOA fields: mname rname serial refresh retry expire minimum
                m = re.search(r'SOA\s+(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', line)
                if m:
                    mname, rname, serial, refresh, retry, expire, minimum = m.groups()
                    _row("Primary NS",  f"{_C.BGREEN}{mname}{_C.RESET}")
                    _row("Responsible", f"{_C.CYAN}{rname.replace('.', '@', 1)}{_C.RESET}")
                    _row("Serial",      f"{_C.BWHITE}{serial}{_C.RESET}")
                    _row("Refresh",     f"{_C.DIM}{refresh}s ({int(refresh)//3600}h){_C.RESET}")
                    _row("Retry",       f"{_C.DIM}{retry}s{_C.RESET}")
                    _row("Expire",      f"{_C.DIM}{expire}s ({int(expire)//86400}d){_C.RESET}")
                    _row("Minimum TTL", f"{_C.DIM}{minimum}s{_C.RESET}")
                else:
                    _w(f"  {line}\n")
        _w(f"{_C.RESET}")
    else:
        # fallback: nslookup
        rc, out, _ = _run(['nslookup', f'-type=SOA', domain])
        if rc == 0 and out:
            for line in out.splitlines():
                if line.strip() and not line.startswith('Server') and not line.startswith('Address'):
                    _w(f"  {_C.DIM}{line}{_C.RESET}\n")
        else:
            _warn("Brak rekordu SOA lub narzędzia DNS niedostępne.")
            _w(f"  {_C.DIM}(zainstaluj 'bind-utils' lub 'dnsutils'){_C.RESET}\n")
    _w("\n")


def _cmd_dnsns(args, terminal):
    """Rekordy NS domeny."""
    _section("DNS NS Records")
    if not args:
        _warn("Użycie: diagnet dnsns <domena>")
        _w("\n")
        return

    domain = args[0]
    _w(f"  Domena: {_C.BYELLOW}{domain}{_C.RESET}\n\n")

    ok, out = _dig_query(domain, 'NS')
    if ok and out:
        ns_list = re.findall(r'NS\s+(\S+)', out)
        if ns_list:
            for i, ns in enumerate(ns_list, 1):
                ns_ip = _resolve_a(ns.rstrip('.'))
                ip_str = ns_ip[0] if ns_ip else '?'
                _w(f"  {_C.DIM}{i:>2}.{_C.RESET} {_C.BGREEN}{ns.rstrip('.'):<40}{_C.RESET} {_C.DIM}{ip_str}{_C.RESET}\n")
        else:
            for line in out.splitlines():
                if line.strip():
                    _w(f"  {line}\n")
    else:
        _warn("Brak rekordów NS lub narzędzia DNS niedostępne.")
    _w("\n")


def _cmd_dnsaaaa(args, terminal):
    """Rekordy AAAA IPv6."""
    _section("DNS AAAA (IPv6)")
    if not args:
        _warn("Użycie: diagnet dnsaaaa <domena>")
        _w("\n")
        return

    domain = args[0]
    _w(f"  Domena: {_C.BYELLOW}{domain}{_C.RESET}\n\n")

    t0 = time.time()
    ips = _resolve_aaaa(domain)
    elapsed = (time.time() - t0) * 1000

    if ips:
        _w(f"  {_C.BLUE}Rekordy AAAA ({len(ips)}):{_C.RESET}\n")
        for ip in ips:
            _w(f"  {_C.BWHITE}  {ip}{_C.RESET}\n")
        _w(f"\n  {_C.DIM}Czas: {elapsed:.1f} ms{_C.RESET}\n")
    else:
        _warn(f"Brak rekordów AAAA dla '{domain}'")
        _w(f"  {_C.DIM}(domena może nie obsługiwać IPv6){_C.RESET}\n")
    _w("\n")


def _cmd_dnsaaaaa(args, terminal):
    """Rozszerzone rekordy IPv6 (AAAA + reverse PTR dla każdego adresu)."""
    _section("DNS AAAAA — Extended IPv6")
    if not args:
        _warn("Użycie: diagnet dnsaaaaa <domena>")
        _w("\n")
        return

    domain = args[0]
    _w(f"  Domena: {_C.BYELLOW}{domain}{_C.RESET}\n\n")

    ips = _resolve_aaaa(domain)
    if not ips:
        _warn(f"Brak rekordów AAAA dla '{domain}'")
        _w(f"  {_C.DIM}(domena może nie obsługiwać IPv6){_C.RESET}\n\n")
        return

    _w(f"  {_C.BLUE}Rekordy AAAA + PTR ({len(ips)}):{_C.RESET}\n")
    _hr()
    for ip in ips:
        _w(f"\n  {_C.BWHITE}AAAA:{_C.RESET} {_C.BLUE}{ip}{_C.RESET}\n")
        ptr = _reverse_dns(ip)
        status = _C.BGREEN if not ptr.startswith('(') else _C.DIM
        _w(f"  {_C.DIM}PTR: {_C.RESET}{status}{ptr}{_C.RESET}\n")

        # Scope detection
        scope = '(Global Unicast)'
        if ip.startswith('fe80'):
            scope = f'{_C.YELLOW}(Link-Local){_C.RESET}'
        elif ip.startswith('fc') or ip.startswith('fd'):
            scope = f'{_C.YELLOW}(Unique Local){_C.RESET}'
        elif ip.startswith('::1'):
            scope = f'{_C.DIM}(Loopback){_C.RESET}'
        _w(f"  {_C.DIM}Scope: {_C.RESET}{scope}\n")
    _w("\n")


def _cmd_dnsall(args, terminal):
    """Wszystkie dostępne rekordy DNS."""
    _section("DNS All Records")
    if not args:
        _warn("Użycie: diagnet dnsall <domena>")
        _w("\n")
        return

    domain = args[0]
    _w(f"  Domena: {_C.BYELLOW}{domain}{_C.RESET}\n\n")

    record_types = ['A', 'AAAA', 'MX', 'NS', 'TXT', 'SOA', 'CNAME']
    results: Dict[str, Any] = {}

    # === A ===
    ips4 = _resolve_a(domain)
    if ips4:
        results['A'] = ips4

    # === AAAA ===
    ips6 = _resolve_aaaa(domain)
    if ips6:
        results['AAAA'] = ips6

    # === dig/nslookup for the rest ===
    has_dig = _dns_tool_available()
    if has_dig:
        for rtype in ['MX', 'NS', 'TXT', 'SOA', 'CNAME']:
            ok, out = _dig_query(domain, rtype)
            if ok and out.strip():
                lines = [l.strip() for l in out.splitlines() if l.strip()]
                if lines:
                    results[rtype] = lines

    # === Display ===
    if not results:
        _err(f"Brak rekordów DNS dla '{domain}'")
        _w("\n")
        return

    colors = {
        'A':     _C.BGREEN,
        'AAAA':  _C.BLUE,
        'MX':    _C.MAGENTA,
        'NS':    _C.CYAN,
        'TXT':   _C.YELLOW,
        'SOA':   _C.BYELLOW,
        'CNAME': _C.BWHITE,
    }

    for rtype, data in results.items():
        color = colors.get(rtype, _C.BWHITE)
        _w(f"  {_C.BOLD}{color}{rtype}{_C.RESET}\n")
        if isinstance(data, list):
            for entry in data:
                _w(f"    {_C.DIM}•{_C.RESET} {entry}\n")
        _w("\n")

    if not has_dig:
        _w(f"  {_C.DIM}* Rekordy MX/TXT/SOA/NS/CNAME wymagają dig/nslookup.\n"
           f"    Zainstaluj 'bind-utils' (Linux) lub 'dnsutils' (Debian/Ubuntu).{_C.RESET}\n\n")


# ═══════════════════════════════════════════════════════════════════════════════
# NETWORK — CONNECTION TESTING
# ═══════════════════════════════════════════════════════════════════════════════

# Popularne porty używane przy skanowaniu
_COMMON_PORTS: List[Tuple[int, str]] = [
    (21, 'FTP'), (22, 'SSH'), (23, 'Telnet'), (25, 'SMTP'), (53, 'DNS'),
    (80, 'HTTP'), (110, 'POP3'), (111, 'RPC'), (135, 'MSRPC'), (139, 'NetBIOS'),
    (143, 'IMAP'), (443, 'HTTPS'), (445, 'SMB'), (587, 'SMTP-TLS'), (631, 'IPP'),
    (993, 'IMAPS'), (995, 'POP3S'), (1080, 'SOCKS'), (1433, 'MSSQL'),
    (1521, 'Oracle'), (2049, 'NFS'), (2181, 'Zookeeper'), (3000, 'Dev'),
    (3306, 'MySQL'), (3389, 'RDP'), (4369, 'EPMD'), (5000, 'Dev/UPnP'),
    (5432, 'PostgreSQL'), (5672, 'AMQP'), (5900, 'VNC'), (6379, 'Redis'),
    (6443, 'K8s API'), (7000, 'Cassandra'), (8080, 'HTTP-Alt'), (8443, 'HTTPS-Alt'),
    (8888, 'Jupyter'), (9200, 'Elasticsearch'), (9300, 'ES-Cluster'),
    (11211, 'Memcached'), (27017, 'MongoDB'), (27018, 'MongoDB-Shard'),
    (50000, 'SAP'), (50070, 'Hadoop'),
]

_TOP100_PORTS: List[int] = [
    7, 9, 13, 21, 22, 23, 25, 37, 53, 79, 80, 88, 110, 111, 113, 119, 135,
    139, 143, 194, 389, 443, 445, 465, 514, 515, 587, 631, 636, 873, 902,
    993, 995, 1025, 1080, 1194, 1433, 1434, 1521, 1723, 2049, 2082, 2083,
    2086, 2087, 2095, 2096, 2181, 2222, 2375, 2376, 3000, 3128, 3268, 3269,
    3306, 3389, 3690, 4369, 4444, 4848, 5000, 5432, 5672, 5900, 5984, 6379,
    6443, 6667, 7001, 7002, 7070, 7777, 8000, 8008, 8080, 8081, 8443, 8888,
    8983, 9000, 9042, 9090, 9092, 9200, 9300, 9418, 10000, 11211, 15672,
    27017, 27018, 28017, 50000, 50070, 61616,
]


def _tcp_connect(host: str, port: int, timeout: float = 3.0) -> Tuple[bool, float, str]:
    """Próba połączenia TCP. Zwraca (sukces, czas_ms, błąd)."""
    try:
        ip = socket.gethostbyname(host)
        t0 = time.time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        rc = s.connect_ex((ip, port))
        elapsed = (time.time() - t0) * 1000
        s.close()
        if rc == 0:
            return True, elapsed, ''
        return False, elapsed, f'connect_ex={rc}'
    except socket.gaierror as e:
        return False, 0.0, f'DNS error: {e}'
    except Exception as e:
        return False, 0.0, str(e)


def _udp_probe(host: str, port: int, timeout: float = 3.0) -> Tuple[bool, float, str, Optional[str]]:
    """Wysyła próbkę UDP i opcjonalnie czeka na odpowiedź."""
    try:
        ip = socket.gethostbyname(host)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        t0 = time.time()
        payload = b'netdiag-udp-test'
        s.sendto(payload, (ip, port))
        try:
            data, _ = s.recvfrom(4096)
            elapsed = (time.time() - t0) * 1000
            s.close()
            return True, elapsed, '', data.decode('utf-8', errors='replace')
        except socket.timeout:
            elapsed = (time.time() - t0) * 1000
            s.close()
            return True, elapsed, 'brak odpowiedzi', None
    except socket.gaierror as e:
        return False, 0.0, f'DNS error: {e}', None
    except Exception as e:
        return False, 0.0, str(e), None


def _create_raw_socket(proto: int = socket.IPPROTO_ICMP) -> Tuple[bool, str]:
    """Próba utworzenia gniazda RAW dla protokołu ICMP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, proto)
        s.close()
        return True, ''
    except Exception as e:
        return False, str(e)


def _latency_bar(ms: float, max_ms: float = 500.0) -> str:
    """Pasek wizualny opóźnienia."""
    width = 20
    filled = int(min(ms / max_ms, 1.0) * width)
    if ms < 50:
        color = _C.BGREEN
    elif ms < 150:
        color = _C.BYELLOW
    else:
        color = _C.RED
    bar = '█' * filled + '░' * (width - filled)
    return f"{color}[{bar}]{_C.RESET} {color}{ms:7.1f} ms{_C.RESET}"


def _cmd_netping(args, terminal):
    """Test połączenia TCP/ICMP do hosta."""
    _section("Diagnet Ping")
    if not args:
        _warn("Użycie: diagnet netping <host> [liczba=4]")
        _w(f"  {_C.DIM}Przykład: diagnet netping google.com 5{_C.RESET}\n\n")
        return

    host = args[0]
    count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 4
    count = max(1, min(count, 20))

    # Resolve
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        _err(f"Nie można rozwiązać nazwy: {host}")
        _w("\n")
        return

    display = f"{host}" if host != ip else ip
    _w(f"  Host:   {_C.BYELLOW}{display}{_C.RESET}  {_C.DIM}({ip}){_C.RESET}\n")
    _w(f"  Próby:  {_C.DIM}{count}{_C.RESET}\n")
    _w(f"  Metoda: {_C.DIM}TCP:80/443 (ICMP wymaga root){_C.RESET}\n\n")

    # Wybierz port — próbuj 80, potem 443
    probe_port = 80
    test_ok, _, _ = _tcp_connect(ip, 80, timeout=1.0)
    if not test_ok:
        probe_port = 443

    times: List[float] = []
    lost = 0

    for i in range(1, count + 1):
        ok, ms, err = _tcp_connect(ip, probe_port, timeout=3.0)
        if ok:
            times.append(ms)
            bar = _latency_bar(ms)
            _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {bar}  {_C.DIM}port {probe_port}{_C.RESET}\n")
        else:
            lost += 1
            _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {_C.RED}timeout / brak odpowiedzi{_C.RESET}  {_C.DIM}({err}){_C.RESET}\n")
        time.sleep(0.2)

    _hr()
    sent = count
    received = len(times)
    loss_pct = (lost / sent) * 100

    _w(f"\n  Wysłano: {_C.BWHITE}{sent}{_C.RESET}  "
       f"Otrzymano: {_C.BGREEN}{received}{_C.RESET}  "
       f"Utracono: {_C.RED if lost > 0 else _C.DIM}{lost} ({loss_pct:.0f}%){_C.RESET}\n")

    if times:
        _w(f"  Min: {_C.BGREEN}{min(times):.1f} ms{_C.RESET}  "
           f"Max: {_C.BYELLOW}{max(times):.1f} ms{_C.RESET}  "
           f"Avg: {_C.BWHITE}{sum(times)/len(times):.1f} ms{_C.RESET}\n")
    _w("\n")


def _cmd_tcping(args, terminal):
    """Pomiar opóźnienia TCP (wielokrotny)."""
    _section("TCP Ping")
    if len(args) < 2:
        _warn("Użycie: diagnet tcping <host> <port> [liczba=5]")
        _w(f"  {_C.DIM}Przykład: diagnet tcping google.com 443 10{_C.RESET}\n\n")
        return

    host = args[0]
    try:
        port = int(args[1])
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _err(f"Nieprawidłowy port: {args[1]}")
        _w("\n")
        return

    count = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
    count = max(1, min(count, 30))

    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        _err(f"Nie można rozwiązać nazwy: {host}")
        _w("\n")
        return

    display = host if host != ip else ip
    _w(f"  Host:  {_C.BYELLOW}{display}{_C.RESET}  {_C.DIM}({ip}){_C.RESET}\n")
    _w(f"  Port:  {_C.BCYAN}{port}{_C.RESET}\n")
    _w(f"  Próby: {_C.DIM}{count}{_C.RESET}\n\n")

    times: List[float] = []
    lost = 0

    for i in range(1, count + 1):
        ok, ms, err = _tcp_connect(ip, port, timeout=3.0)
        if ok:
            times.append(ms)
            bar = _latency_bar(ms)
            _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {bar}\n")
        else:
            lost += 1
            _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {_C.RED}✗ timeout / port zamknięty{_C.RESET}  {_C.DIM}({err}){_C.RESET}\n")
        time.sleep(0.15)

    _hr()
    received = len(times)
    loss_pct = (lost / count) * 100

    _w(f"\n  Wysłano: {_C.BWHITE}{count}{_C.RESET}  "
       f"OK: {_C.BGREEN}{received}{_C.RESET}  "
       f"Błędy: {_C.RED if lost > 0 else _C.DIM}{lost} ({loss_pct:.0f}%){_C.RESET}\n")

    if times:
        avg = sum(times) / len(times)
        jitter = max(times) - min(times)
        _w(f"  Min: {_C.BGREEN}{min(times):.1f} ms{_C.RESET}  "
           f"Max: {_C.BYELLOW}{max(times):.1f} ms{_C.RESET}  "
           f"Avg: {_C.BWHITE}{avg:.1f} ms{_C.RESET}  "
           f"Jitter: {_C.DIM}{jitter:.1f} ms{_C.RESET}\n")
    _w("\n")


def _http_request(url: str, method: str = 'GET', timeout: int = 8,
                  head_only: bool = False) -> Tuple[bool, int, float, float, str, Dict]:
    """
    Wykonuje żądanie HTTP/HTTPS.
    Zwraca: (sukces, status_code, czas_connect_ms, czas_total_ms, body_preview, headers)
    """
    import urllib.request
    import urllib.error
    import ssl

    # Normalizacja URL
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers_out = {}
    try:
        req = urllib.request.Request(url, method=method if method != 'GET' else None)
        req.add_header('User-Agent', 'netdiag/1.1 (polsoft.ITS)')
        req.add_header('Accept', '*/*')

        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            t_connected = (time.time() - t0) * 1000
            body = b''
            if not head_only:
                body = resp.read(8192)
            t_total = (time.time() - t0) * 1000
            status = resp.status
            for k, v in resp.headers.items():
                headers_out[k.lower()] = v
            preview = body[:512].decode('utf-8', errors='replace') if body else ''
            return True, status, t_connected, t_total, preview, headers_out
    except urllib.error.HTTPError as e:
        t_total = (time.time() - t0) * 1000 if 't0' in dir() else 0.0
        headers_out = dict(e.headers) if e.headers else {}
        return True, e.code, t_total, t_total, str(e.reason), headers_out
    except Exception as e:
        return False, 0, 0.0, 0.0, str(e), {}


def _status_color(code: int) -> str:
    if 200 <= code < 300:
        return _C.BGREEN
    elif 300 <= code < 400:
        return _C.BCYAN
    elif 400 <= code < 500:
        return _C.BYELLOW
    elif code >= 500:
        return _C.RED
    return _C.BWHITE


def _cmd_httpping(args, terminal):
    """Pomiar opóźnienia HTTP — wielokrotne żądania HEAD."""
    _section("HTTP Ping")
    if not args:
        _warn("Użycie: diagnet httpping <url> [liczba=5]")
        _w(f"  {_C.DIM}Przykład: diagnet httpping https://google.com 5{_C.RESET}\n\n")
        return

    url = args[0]
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url
    count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
    count = max(1, min(count, 20))

    _w(f"  URL:   {_C.BYELLOW}{url}{_C.RESET}\n")
    _w(f"  Próby: {_C.DIM}{count}{_C.RESET}  Metoda: {_C.DIM}GET{_C.RESET}\n\n")

    times: List[float] = []
    statuses: List[int] = []
    errors = 0

    for i in range(1, count + 1):
        ok, status, t_conn, t_total, _, hdrs = _http_request(url, head_only=True, timeout=6)
        if ok and status > 0:
            times.append(t_total)
            statuses.append(status)
            sc = _status_color(status)
            bar = _latency_bar(t_total, max_ms=2000.0)
            _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {bar}  {sc}HTTP {status}{_C.RESET}\n")
        else:
            errors += 1
            _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {_C.RED}✗ błąd połączenia{_C.RESET}  {_C.DIM}({_}){_C.RESET}\n")
        time.sleep(0.2)

    _hr()
    _w(f"\n  Próby: {_C.BWHITE}{count}{_C.RESET}  "
       f"OK: {_C.BGREEN}{len(times)}{_C.RESET}  "
       f"Błędy: {_C.RED if errors > 0 else _C.DIM}{errors}{_C.RESET}\n")
    if times:
        _w(f"  Min: {_C.BGREEN}{min(times):.1f} ms{_C.RESET}  "
           f"Max: {_C.BYELLOW}{max(times):.1f} ms{_C.RESET}  "
           f"Avg: {_C.BWHITE}{sum(times)/len(times):.1f} ms{_C.RESET}\n")
    _w("\n")


def _cmd_httpget(args, terminal):
    """Pobranie zasobu HTTP i wyświetlenie szczegółów odpowiedzi."""
    _section("HTTP GET")
    if not args:
        _warn("Użycie: diagnet httpget <url>")
        _w(f"  {_C.DIM}Przykład: diagnet httpget http://example.com{_C.RESET}\n\n")
        return

    url = args[0]
    if not url.startswith('http://'):
        url = 'http://' + url.lstrip('https://')
        # Jeśli użytkownik podał https://, przekieruj do httpsget
        if args[0].startswith('https://'):
            url = args[0]

    _w(f"  URL: {_C.BYELLOW}{url}{_C.RESET}\n\n")
    _w(f"  {_C.DIM}Wysyłanie żądania...{_C.RESET}\n")

    ok, status, t_conn, t_total, body, hdrs = _http_request(url, head_only=False, timeout=10)

    if not ok:
        _err(f"Błąd połączenia: {body}")
        _w("\n")
        return

    sc = _status_color(status)
    _w(f"\n")
    _row("Status",       f"{sc}HTTP {status}{_C.RESET}")
    _row("Czas total",   f"{_latency_bar(t_total, 3000)}")
    _row("Content-Type", f"{_C.DIM}{hdrs.get('content-type', '—')}{_C.RESET}")
    _row("Content-Len",  f"{_C.DIM}{hdrs.get('content-length', '—')}{_C.RESET}")
    _row("Server",       f"{_C.DIM}{hdrs.get('server', '—')}{_C.RESET}")
    _row("X-Powered-By", f"{_C.DIM}{hdrs.get('x-powered-by', '—')}{_C.RESET}")

    # Przekierowanie
    loc = hdrs.get('location', '')
    if loc:
        _row("Location", f"{_C.BCYAN}{loc}{_C.RESET}")

    _hr()
    _w(f"\n  {_C.BOLD}Podgląd treści:{_C.RESET}\n")
    if body.strip():
        preview_lines = body.strip().splitlines()[:20]
        for line in preview_lines:
            _w(f"  {_C.DIM}{line[:100]}{_C.RESET}\n")
        if len(body.strip().splitlines()) > 20:
            _w(f"  {_C.DIM}... (wyświetlono 20 z {len(body.splitlines())} linii){_C.RESET}\n")
    else:
        _w(f"  {_C.DIM}(pusta odpowiedź){_C.RESET}\n")
    _w("\n")


def _cmd_httpsget(args, terminal):
    """Pobranie zasobu HTTPS i wyświetlenie szczegółów odpowiedzi."""
    _section("HTTPS GET")
    if not args:
        _warn("Użycie: diagnet httpsget <url>")
        _w(f"  {_C.DIM}Przykład: diagnet httpsget https://example.com{_C.RESET}\n\n")
        return

    url = args[0]
    if not url.startswith('https://'):
        # Usuń ewentualne http:// i dodaj https://
        url = 'https://' + re.sub(r'^https?://', '', url)

    _w(f"  URL: {_C.BYELLOW}{url}{_C.RESET}\n\n")
    _w(f"  {_C.DIM}Wysyłanie żądania HTTPS...{_C.RESET}\n")

    ok, status, t_conn, t_total, body, hdrs = _http_request(url, head_only=False, timeout=10)

    if not ok:
        _err(f"Błąd połączenia: {body}")
        _w("\n")
        return

    import ssl
    # Pobierz info o certyfikacie
    cert_info = ''
    try:
        parsed = re.match(r'https://([^/:]+)(?::(\d+))?', url)
        if parsed:
            cert_host = parsed.group(1)
            cert_port = int(parsed.group(2) or 443)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((cert_host, cert_port), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=cert_host) as ssock:
                    cert = ssock.getpeercert()
                    cipher = ssock.cipher()
                    tls_ver = ssock.version()
                    if cert:
                        subject = dict(x[0] for x in cert.get('subject', []))
                        expires = cert.get('notAfter', '?')
                        cert_info = f"{subject.get('commonName', '?')}  exp: {expires}  {tls_ver} {cipher[0] if cipher else ''}"
    except Exception:
        pass

    sc = _status_color(status)
    _w(f"\n")
    _row("Status",       f"{sc}HTTP {status}{_C.RESET}")
    _row("Czas total",   f"{_latency_bar(t_total, 3000)}")
    if cert_info:
        _row("TLS cert",    f"{_C.BGREEN}{cert_info}{_C.RESET}")
    _row("Content-Type", f"{_C.DIM}{hdrs.get('content-type', '—')}{_C.RESET}")
    _row("Content-Len",  f"{_C.DIM}{hdrs.get('content-length', '—')}{_C.RESET}")
    _row("Server",       f"{_C.DIM}{hdrs.get('server', '—')}{_C.RESET}")
    _row("HSTS",         f"{_C.DIM}{hdrs.get('strict-transport-security', '—')}{_C.RESET}")

    loc = hdrs.get('location', '')
    if loc:
        _row("Location", f"{_C.BCYAN}{loc}{_C.RESET}")

    _hr()
    _w(f"\n  {_C.BOLD}Podgląd treści:{_C.RESET}\n")
    if body.strip():
        preview_lines = body.strip().splitlines()[:20]
        for line in preview_lines:
            _w(f"  {_C.DIM}{line[:100]}{_C.RESET}\n")
        if len(body.strip().splitlines()) > 20:
            _w(f"  {_C.DIM}... (wyświetlono 20 z {len(body.splitlines())} linii){_C.RESET}\n")
    else:
        _w(f"  {_C.DIM}(pusta odpowiedź){_C.RESET}\n")
    _w("\n")


def _cmd_portcheck(args, terminal):
    """Sprawdzenie czy dany port jest otwarty."""
    _section("Port Check")
    if len(args) < 2:
        _warn("Użycie: diagnet portcheck <host> <port>")
        _w(f"  {_C.DIM}Przykład: diagnet portcheck google.com 443{_C.RESET}\n\n")
        return

    host = args[0]
    try:
        port = int(args[1])
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _err(f"Nieprawidłowy port: {args[1]}")
        _w("\n")
        return

    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        _err(f"Nie można rozwiązać nazwy: {host}")
        _w("\n")
        return

    # Znajdź nazwę usługi
    service = next((name for p, name in _COMMON_PORTS if p == port), '')
    try:
        service = service or socket.getservbyport(port)
    except Exception:
        pass

    display = host if host != ip else ip
    _w(f"  Host:  {_C.BYELLOW}{display}{_C.RESET}  {_C.DIM}({ip}){_C.RESET}\n")
    _w(f"  Port:  {_C.BCYAN}{port}{_C.RESET}  {_C.DIM}{service}{_C.RESET}\n\n")

    # Test z kilkoma timeoutami
    for timeout in (1.0, 2.0, 3.0):
        ok, ms, err = _tcp_connect(ip, port, timeout=timeout)
        if ok:
            break

    if ok:
        _ok(f"Port {_C.BCYAN}{port}{_C.RESET} jest {_C.BGREEN}OTWARTY{_C.RESET}  "
            f"{_C.DIM}({ms:.1f} ms){_C.RESET}")
        if service:
            _w(f"  {_C.DIM}Usługa: {service}{_C.RESET}\n")
    else:
        _err(f"Port {_C.BCYAN}{port}{_C.RESET} jest {_C.RED}ZAMKNIĘTY / FILTROWANY{_C.RESET}  "
             f"{_C.DIM}({err}){_C.RESET}")
    _w("\n")


def _portscan_worker(ip: str, ports_with_names: List[Tuple[int, str]],
                     timeout: float = 1.0, max_threads: int = 50
                     ) -> List[Tuple[int, str, float]]:
    """
    Skanuje listę portów współbieżnie.
    Zwraca listę otwartych: [(port, service, ms), ...]
    """
    import threading

    open_ports: List[Tuple[int, str, float]] = []
    lock = threading.Lock()
    semaphore = threading.Semaphore(max_threads)

    def probe(port: int, service: str):
        with semaphore:
            ok, ms, _ = _tcp_connect(ip, port, timeout=timeout)
            if ok:
                with lock:
                    open_ports.append((port, service, ms))

    threads = []
    for port, service in ports_with_names:
        t = threading.Thread(target=probe, args=(port, service), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=timeout + 1.0)

    return sorted(open_ports, key=lambda x: x[0])


def _print_portscan_results(open_ports: List[Tuple[int, str, float]],
                             total: int, elapsed: float):
    """Wyświetla wyniki skanowania portów."""
    _hr()
    if not open_ports:
        _w(f"\n  {_C.DIM}Brak otwartych portów.{_C.RESET}\n")
    else:
        _w(f"\n  {_C.BOLD}Otwarte porty ({len(open_ports)}):{_C.RESET}\n\n")
        _w(f"  {_C.BOLD}{_C.DIM}{_pad('Port', 8)}{_pad('Usługa', 18)}{_pad('Opóźnienie', 14)}{_C.RESET}\n")
        _hr()
        for port, service, ms in open_ports:
            bar = _latency_bar(ms, max_ms=300.0)
            _w(f"  {_C.BCYAN}{_pad(str(port), 8)}{_C.RESET}"
               f"{_C.BGREEN}{_pad(service or '?', 18)}{_C.RESET}"
               f"{bar}\n")

    _w(f"\n  {_C.DIM}Przeskanowano {total} portów w {elapsed:.1f}s  |  "
       f"Otwarte: {len(open_ports)}{_C.RESET}\n\n")


def _ping_host(host: str, timeout: int = 1) -> Tuple[bool, Optional[int], str]:
    """Ping hosta raz i zwróć TTL gdy dostępny."""
    if _OS == 'Windows':
        cmd = ['ping', '-n', '1', '-w', str(timeout * 1000), host]
    else:
        cmd = ['ping', '-c', '1', '-W', str(timeout), host]
    rc, out, err = _run(cmd, timeout=timeout + 2)
    if rc != 0 or not out:
        return False, None, err or 'timeout'
    ttl = None
    m = re.search(r'TTL[=:](\d+)', out, re.IGNORECASE)
    if m:
        ttl = int(m.group(1))
    return True, ttl, ''


def _network_hosts_from_cidr(cidr: str) -> List[str]:
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        return [str(ip) for ip in net.hosts()]
    except Exception:
        return []


def _scan_hosts(hosts: List[str], timeout: int = 1, max_threads: int = 50) -> List[str]:
    import threading
    active: List[str] = []
    lock = threading.Lock()
    sem = threading.Semaphore(max_threads)

    def worker(host: str):
        with sem:
            ok, _, _ = _ping_host(host, timeout=timeout)
            if ok:
                with lock:
                    active.append(host)

    threads = []
    for host in hosts:
        t = threading.Thread(target=worker, args=(host,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    return sorted(active, key=lambda x: tuple(int(p) for p in x.split('.')))


def _local_network_cidr() -> Optional[str]:
    ip = _local_ip()
    if not ip or ip.startswith('('):
        return None
    try:
        return str(ipaddress.ip_network(f"{ip}/24", strict=False))
    except Exception:
        return None


def _grab_banner(host: str, port: int, timeout: float = 4.0) -> Tuple[bool, str]:
    try:
        ip = socket.gethostbyname(host)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        try:
            data = s.recv(2048)
            if not data and port in (80, 443):
                req = f"HEAD / HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
                s.sendall(req.encode('ascii', 'ignore'))
                data = s.recv(2048)
        except socket.timeout:
            data = b''
        s.close()
        return True, data.decode('utf-8', errors='replace').strip()
    except Exception as e:
        return False, str(e)


def _fingerprint_os(ttl: Optional[int], banner: str) -> str:
    parts = []
    if ttl is not None:
        if ttl >= 128:
            parts.append('Windows-like (TTL>=128)')
        elif ttl >= 64:
            parts.append('Linux/Unix-like (TTL>=64)')
        elif ttl >= 32:
            parts.append('Network device / embedded (TTL<64)')
    if 'apache' in banner.lower():
        parts.append('Apache web server')
    if 'nginx' in banner.lower():
        parts.append('Nginx web server')
    if 'iis' in banner.lower() or 'microsoft-iis' in banner.lower():
        parts.append('Microsoft IIS')
    if 'ssh-' in banner.lower():
        parts.append('SSH service present')
    if not parts:
        parts.append('Brak jednoznacznej identyfikacji')
    return '; '.join(parts)


def _parse_arp_table(out: str) -> List[Tuple[str, str, str]]:
    entries: List[Tuple[str, str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F:-]{17})\s+(\w+)', line)
        if m:
            entries.append((m.group(1), m.group(2), m.group(3)))
        else:
            m2 = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F:-]{17})', line)
            if m2:
                entries.append((m2.group(1), m2.group(2), 'unknown'))
    return entries


def _discover_neighbors() -> List[Tuple[str, str, str]]:
    if _OS == 'Windows':
        rc, out, _ = _run(['arp', '-a'])
    else:
        rc, out, _ = _run(['ip', 'neigh'])
        if rc != 0 or not out:
            rc, out, _ = _run(['arp', '-n'])
    if rc != 0 or not out:
        return []
    if _OS == 'Windows':
        return _parse_arp_table(out)
    results: List[Tuple[str, str, str]] = []
    for line in out.splitlines():
        m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})\s+dev\s+\S+\s+lladdr\s+([0-9a-f:]{17})\s+\S+\s+(\S+)', line)
        if m:
            results.append((m.group(1), m.group(2), m.group(3)))
        else:
            m2 = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})\s+dev\s+\S+\s+lladdr\s+([0-9a-f:]{17})', line)
            if m2:
                results.append((m2.group(1), m2.group(2), 'unknown'))
    return results


def _cmd_portscan(args, terminal):
    """Skanowanie popularnych portów hosta."""
    _section("Port Scan")
    if not args:
        _warn("Użycie: diagnet portscan <host> [porty]")
        _w(f"  {_C.DIM}Przykład: diagnet portscan google.com\n"
           f"           diagnet portscan 192.168.1.1 22,80,443,8080{_C.RESET}\n\n")
        return

    host = args[0]
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        _err(f"Nie można rozwiązać nazwy: {host}")
        _w("\n")
        return

    # Parsuj opcjonalną listę portów
    if len(args) > 1:
        try:
            custom = []
            for p in args[1].split(','):
                p = p.strip()
                if '-' in p:
                    a, b = p.split('-', 1)
                    custom.extend(range(int(a), int(b) + 1))
                else:
                    custom.append(int(p))
            ports_to_scan = [(p, next((n for pp, n in _COMMON_PORTS if pp == p), '')) for p in custom]
        except ValueError:
            _err(f"Nieprawidłowa lista portów: {args[1]}")
            _w("\n")
            return
    else:
        ports_to_scan = _COMMON_PORTS[:]

    display = host if host != ip else ip
    _w(f"  Host:   {_C.BYELLOW}{display}{_C.RESET}  {_C.DIM}({ip}){_C.RESET}\n")
    _w(f"  Porty:  {_C.DIM}{len(ports_to_scan)} (popularne){_C.RESET}\n")
    _w(f"  Tryb:   {_C.DIM}TCP connect, 50 wątków{_C.RESET}\n\n")
    _w(f"  {_C.DIM}Skanowanie...{_C.RESET}\n")

    t0 = time.time()
    open_ports = _portscan_worker(ip, ports_to_scan, timeout=1.0, max_threads=50)
    elapsed = time.time() - t0

    _print_portscan_results(open_ports, len(ports_to_scan), elapsed)


def _cmd_portscan_fast(args, terminal):
    """Szybkie skanowanie portów — top 100 portów, agresywny timeout."""
    _section("Port Scan — Fast (top 100)")
    if not args:
        _warn("Użycie: diagnet portscan-fast <host>")
        _w(f"  {_C.DIM}Przykład: diagnet portscan-fast 192.168.1.1{_C.RESET}\n\n")
        return

    host = args[0]
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        _err(f"Nie można rozwiązać nazwy: {host}")
        _w("\n")
        return

    ports_to_scan = [(p, next((n for pp, n in _COMMON_PORTS if pp == p), ''))
                     for p in _TOP100_PORTS]

    display = host if host != ip else ip
    _w(f"  Host:   {_C.BYELLOW}{display}{_C.RESET}  {_C.DIM}({ip}){_C.RESET}\n")
    _w(f"  Porty:  {_C.DIM}{len(ports_to_scan)} (top 100){_C.RESET}\n")
    _w(f"  Tryb:   {_C.DIM}TCP connect, 100 wątków, timeout 0.5s{_C.RESET}\n\n")
    _w(f"  {_C.DIM}Szybkie skanowanie...{_C.RESET}\n")

    t0 = time.time()
    open_ports = _portscan_worker(ip, ports_to_scan, timeout=0.5, max_threads=100)
    elapsed = time.time() - t0

    _print_portscan_results(open_ports, len(ports_to_scan), elapsed)


def _cmd_netscan(args, terminal):
    """Skanowanie sieci lokalnej"""
    _section("Net Scan")
    cidr = _local_network_cidr()
    if not cidr:
        _err("Nie można określić lokalnej podsieci")
        _w("\n")
        return
    _w(f"  Local subnet: {_C.BYELLOW}{cidr}{_C.RESET}\n")
    hosts = _network_hosts_from_cidr(cidr)
    active = _scan_hosts(hosts, timeout=1, max_threads=100)
    _w(f"\n  {_C.BOLD}Aktywne hosty ({len(active)}):{_C.RESET}\n")
    for host in active:
        _w(f"  {_C.BGREEN}{host}{_C.RESET}\n")
    _w("\n")


def _cmd_subnetscan(args, terminal):
    """Skanowanie podsieci"""
    _section("Subnet Scan")
    if not args:
        _warn("Użycie: diagnet subnetscan <CIDR>")
        _w("\n")
        return
    cidr = args[0]
    hosts = _network_hosts_from_cidr(cidr)
    if not hosts:
        _err(f"Nieprawidłowa podsieć: {cidr}")
        _w("\n")
        return
    _w(f"  Subnet: {_C.BYELLOW}{cidr}{_C.RESET}\n")
    active = _scan_hosts(hosts, timeout=1, max_threads=100)
    _w(f"\n  {_C.BOLD}Aktywne hosty ({len(active)}):{_C.RESET}\n")
    for host in active:
        _w(f"  {_C.BGREEN}{host}{_C.RESET}\n")
    _w("\n")


def _cmd_hostscan(args, terminal):
    """Wykrywanie aktywnych hostów"""
    _section("Host Scan")
    if not args:
        _warn("Użycie: diagnet hostscan <host|CIDR>")
        _w("\n")
        return
    target = args[0]
    if '/' in target:
        hosts = _network_hosts_from_cidr(target)
        if not hosts:
            _err(f"Nieprawidłowy zakres: {target}")
            _w("\n")
            return
        active = _scan_hosts(hosts, timeout=1, max_threads=100)
    else:
        ok, _, _ = _ping_host(target, timeout=2)
        active = [target] if ok else []
    _w(f"\n  {_C.BOLD}Aktywne hosty ({len(active)}):{_C.RESET}\n")
    for host in active:
        _w(f"  {_C.BGREEN}{host}{_C.RESET}\n")
    _w("\n")


def _cmd_servicedetect(args, terminal):
    """Wykrywanie usług na porcie"""
    _section("Service Detect")
    if len(args) < 2:
        _warn("Użycie: diagnet servicedetect <host> <port>")
        _w("\n")
        return
    host, port_arg = args[0], args[1]
    try:
        port = int(port_arg)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _err(f"Nieprawidłowy port: {port_arg}")
        _w("\n")
        return
    ok, banner = _grab_banner(host, port, timeout=4.0)
    service = ''
    try:
        service = socket.getservbyport(port)
    except Exception:
        service = ''
    if ok:
        _ok(f"Host: {host}:{port} — połączenie powiodło się")
        if service:
            _row("Usługa", f"{_C.BGREEN}{service}{_C.RESET}")
        if banner:
            _row("Baner", f"{_C.DIM}{banner.splitlines()[0]}{_C.RESET}")
    else:
        _err(f"Nie udało się wykryć usługi: {banner}")
    _w("\n")


def _cmd_bannergrab(args, terminal):
    """Pobieranie banera usługi"""
    _section("Banner Grab")
    if len(args) < 2:
        _warn("Użycie: diagnet bannergrab <host> <port>")
        _w("\n")
        return
    host, port_arg = args[0], args[1]
    try:
        port = int(port_arg)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _err(f"Nieprawidłowy port: {port_arg}")
        _w("\n")
        return
    ok, banner = _grab_banner(host, port, timeout=4.0)
    if ok:
        _ok(f"Połączenie do {host}:{port} powiodło się")
        if banner:
            _w(f"\n  {_C.BOLD}Banner:{_C.RESET}\n")
            for line in banner.splitlines()[:20]:
                _w(f"  {_C.DIM}{line}{_C.RESET}\n")
        else:
            _warn("Brak danych banera")
    else:
        _err(f"Błąd banera: {banner}")
    _w("\n")


def _cmd_fingerprint(args, terminal):
    """Identyfikacja systemu zdalnego"""
    _section("Fingerprint")
    if not args:
        _warn("Użycie: diagnet fingerprint <host> [port]")
        _w("\n")
        return
    host = args[0]
    port = int(args[1]) if len(args) > 1 and args[1].isdigit() else 80
    ok, banner = _grab_banner(host, port, timeout=4.0)
    ping_ok, ttl, _ = _ping_host(host, timeout=2)
    summary = _fingerprint_os(ttl, banner if ok else '')
    _row("Host", f"{_C.BYELLOW}{host}{_C.RESET}")
    _row("Port", f"{_C.BCYAN}{port}{_C.RESET}")
    if ok:
        _ok(f"Połączenie TCP do {host}:{port} powiodło się")
    else:
        _warn(f"Połączenie TCP nieudane: {banner}")
    if ping_ok:
        _row("TTL", f"{_C.BWHITE}{ttl}{_C.RESET}")
    _row("Wniosek", f"{_C.BGREEN}{summary}{_C.RESET}")
    _w("\n")


def _cmd_arpdiscover(args, terminal):
    """Skanowanie ARP"""
    _section("ARP Discover")
    entries = _discover_neighbors()
    if not entries:
        _err("Brak wpisów ARP / sąsiadów")
        _w("\n")
        return
    _w(f"  {_C.BOLD}{_pad('IP', 16)}{_pad('MAC', 22)}{_pad('State', 12)}{_C.RESET}\n")
    _hr()
    for ip, mac, state in entries:
        _w(f"  {_C.BGREEN}{_pad(ip, 16)}{_C.RESET}{_C.BYELLOW}{_pad(mac, 22)}{_C.RESET}{_C.DIM}{_pad(state, 12)}{_C.RESET}\n")
    _w("\n")


def _cmd_neighbordiscover(args, terminal):
    """Wykrywanie sąsiadów sieciowych"""
    _section("Neighbor Discover")
    entries = _discover_neighbors()
    if not entries:
        _err("Brak sąsiadów sieciowych")
        _w("\n")
        return
    _w(f"  {_C.BOLD}{_pad('IP', 16)}{_pad('MAC', 22)}{_pad('State', 12)}{_C.RESET}\n")
    _hr()
    for ip, mac, state in entries:
        _w(f"  {_C.BGREEN}{_pad(ip, 16)}{_C.RESET}{_C.BYELLOW}{_pad(mac, 22)}{_C.RESET}{_C.DIM}{_pad(state, 12)}{_C.RESET}\n")
    _w("\n")


def _get_dns_servers() -> List[str]:
    servers: List[str] = []
    if _OS == 'Windows':
        rc, out, _ = _run(['ipconfig', '/all'], timeout=5)
        capture = False
        for line in out.splitlines():
            raw = line.strip()
            if raw.lower().startswith('dns servers'):
                capture = True
                parts = raw.split(':', 1)
                if len(parts) > 1 and parts[1].strip():
                    servers.append(parts[1].strip())
                continue
            if capture:
                if raw and re.match(r'\d{1,3}(?:\.\d{1,3}){3}', raw):
                    servers.append(raw)
                    continue
                capture = False
    else:
        try:
            with open('/etc/resolv.conf', 'r', encoding='utf-8', errors='ignore') as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith('nameserver'):
                        parts = line.split()
                        if len(parts) >= 2:
                            servers.append(parts[1])
        except Exception:
            pass
    return list(dict.fromkeys([s for s in servers if s]))


def _get_listening_ports() -> List[Tuple[str, str, int, str]]:
    entries: List[Tuple[str, str, int, str]] = []
    if _OS == 'Windows':
        rc, out, _ = _run(['netstat', '-an'], timeout=4)
        if rc == 0:
            for line in out.splitlines():
                if 'LISTENING' not in line.upper():
                    continue
                parts = re.split(r'\s+', line.strip())
                if len(parts) < 4:
                    continue
                proto = parts[0]
                local = parts[1]
                state = parts[-1]
                m = re.search(r'(.+):(\d+)$', local)
                if m:
                    entries.append((proto, m.group(1), int(m.group(2)), state))
    else:
        rc, out, _ = _run(['ss', '-tnl'], timeout=4)
        if rc == 0 and out:
            for line in out.splitlines():
                if line.strip().startswith('State') or not line.strip():
                    continue
                parts = re.split(r'\s+', line.strip())
                if len(parts) < 4:
                    continue
                local = parts[3]
                m = re.search(r'(.+):(\d+)$', local)
                if m:
                    entries.append(('TCP', m.group(1), int(m.group(2)), 'LISTEN'))
        else:
            rc, out, _ = _run(['netstat', '-tnl'], timeout=4)
            if rc == 0:
                for line in out.splitlines():
                    if not line.startswith('tcp'):
                        continue
                    parts = re.split(r'\s+', line.strip())
                    if len(parts) < 4:
                        continue
                    local = parts[3]
                    m = re.search(r'(.+):(\d+)$', local)
                    if m:
                        entries.append(('TCP', m.group(1), int(m.group(2)), 'LISTEN'))
    return entries


def _local_port_scan(port_list: List[int], timeout: float = 0.5) -> Tuple[List[Tuple[int, str, float]], List[int]]:
    ports_with_names = [(p, next((name for pp, name in _COMMON_PORTS if pp == p), '')) for p in port_list]
    open_ports = _portscan_worker('127.0.0.1', ports_with_names, timeout=timeout, max_threads=50)
    open_nums = [p for p, _, _ in open_ports]
    blocked = [p for p in port_list if p not in open_nums]
    return open_ports, blocked


def _cmd_firewallcheck(args, terminal):
    """Test działania zapory."""
    _section("Firewall Check")
    if _OS == 'Windows':
        rc, out, _ = _run(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'], timeout=5)
        if rc == 0 and re.search(r'\bstate\b.*on|włączony', out, re.I):
            _ok('Zapora Windows jest włączona')
            _row('Status', 'ON')
            _w('\n')
            return
        if rc == 0 and re.search(r'\bstate\b.*off|wyłączony', out, re.I):
            _warn('Zapora Windows jest wyłączona')
            _row('Status', 'OFF')
            _w('\n')
            return
        _warn('Nie udało się jednoznacznie określić stanu zapory Windows')
        _w(f'  {_C.DIM}{out}{_C.RESET}\n\n')
        return

    rc, out, _ = _run(['ufw', 'status'], timeout=4)
    if rc == 0:
        if 'active' in out.lower():
            _ok('UFW jest aktywny')
            _w(f'  {_C.DIM}{out}{_C.RESET}\n\n')
            return
        if 'inactive' in out.lower():
            _warn('UFW jest nieaktywny')
            _w(f'  {_C.DIM}{out}{_C.RESET}\n\n')
            return

    rc, out, _ = _run(['firewall-cmd', '--state'], timeout=4)
    if rc == 0:
        if out.strip() == 'running':
            _ok('firewalld działa')
        else:
            _warn('firewalld nie działa')
        _w(f'  {_C.DIM}{out}{_C.RESET}\n\n')
        return

    rc, out, _ = _run(['iptables', '-L'], timeout=4)
    if rc == 0 and 'Chain' in out:
        _ok('iptables jest załadowany')
        _w(f'  {_C.DIM}Wyjście iptables...{_C.RESET}\n')
        _w(f'  {_C.DIM}{out.splitlines()[0]}{_C.RESET}\n\n')
        return

    _warn('Nie wykryto aktywnej zapory lub narzędzia nie są dostępne')
    _w('\n')


def _cmd_proxycheck(args, terminal):
    """Wykrywanie proxy."""
    _section('Proxy Check')
    proxies: List[str] = []
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        value = os.environ.get(key)
        if value:
            proxies.append(f'{key}={value}')

    if _OS == 'Windows':
        rc, out, _ = _run(['netsh', 'winhttp', 'show', 'proxy'], timeout=4)
        if rc == 0 and 'proxy server' in out.lower() and 'direct access' not in out.lower():
            proxies.append(out.strip())

    if proxies:
        _ok('Wykryto ustawienia proxy')
        for proxy in proxies:
            _w(f'  {_C.DIM}{proxy}{_C.RESET}\n')
    else:
        _warn('Nie wykryto proxy ani ustawień pośrednika HTTP/HTTPS')
    _w('\n')


def _cmd_vpnstatus(args, terminal):
    """Wykrywanie aktywnego VPN."""
    _section('VPN Status')
    matches: List[str] = []
    if _OS == 'Windows':
        rc, out, _ = _run(['ipconfig', '/all'], timeout=4)
        if rc == 0:
            for line in out.splitlines():
                if re.search(r'vpn|tap|tun|ppp|wireguard|openvpn|cisco', line, re.I):
                    matches.append(line.strip())
    else:
        rc, out, _ = _run(['ip', 'addr'], timeout=4)
        if rc == 0:
            for line in out.splitlines():
                if re.search(r'\b(tun|tap|ppp|wg|vpn)\d*\b', line, re.I):
                    matches.append(line.strip())
        else:
            rc, out, _ = _run(['ifconfig'], timeout=4)
            if rc == 0:
                for line in out.splitlines():
                    if re.search(r'\b(tun|tap|ppp|wg|vpn)\d*\b', line, re.I):
                        matches.append(line.strip())
    if matches:
        _ok('Wygląda na aktywne połączenie VPN / interfejs VPN')
        for match in list(dict.fromkeys(matches))[:10]:
            _w(f'  {_C.DIM}{match}{_C.RESET}\n')
    else:
        _warn('Nie wykryto typowych interfejsów VPN')
    _w('\n')


def _cmd_torcheck(args, terminal):
    """Wykrywanie ruchu przez TOR."""
    _section('TOR Check')
    tor_ports: List[str] = []
    for port in (9050, 9150):
        ok, _, _ = _tcp_connect('127.0.0.1', port, timeout=1.0)
        if ok:
            tor_ports.append(f'127.0.0.1:{port}')
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        value = os.environ.get(key, '')
        if '127.0.0.1:9050' in value or '127.0.0.1:9150' in value:
            tor_ports.append(f'{key}={value}')

    if tor_ports:
        _ok('Wykryto lokalny serwer TOR/SOCKS')
        for entry in tor_ports:
            _w(f'  {_C.DIM}{entry}{_C.RESET}\n')
    else:
        _warn('Nie wykryto lokalnego serwera TOR')
    _w('\n')


def _cmd_dnsleak(args, terminal):
    """Test wycieku DNS."""
    _section('DNS Leak')
    servers = _get_dns_servers()
    if not servers:
        _err('Nie udało się odczytać serwerów DNS')
        _w('\n')
        return
    _w(f'  {_C.BOLD}Znalezione serwery DNS:{_C.RESET}\n')
    private = False
    for server in servers:
        _w(f'  {_C.DIM}{server}{_C.RESET}\n')
        try:
            addr = ipaddress.ip_address(server)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                private = True
        except Exception:
            pass
    if private:
        _warn('Co najmniej jeden serwer DNS jest prywatny/lokalny — możliwe wycieki DNS poza VPN')
    else:
        _ok('Serwery DNS wyglądają na publiczne / zdalne')
    _w('\n')


def _cmd_portvisibility(args, terminal):
    """Widoczność portów z zewnątrz."""
    _section('Port Visibility')
    ports = _get_listening_ports()
    if not ports:
        _warn('Brak nasłuchujących portów')
        _w('\n')
        return
    visible: List[Tuple[str, str, int, str]] = []
    for proto, host, port, state in ports:
        try:
            addr = ipaddress.ip_address(host)
        except Exception:
            addr = None
        if host in ('0.0.0.0', '::') or (addr is not None and not addr.is_loopback):
            visible.append((proto, host, port, state))
    if not visible:
        _ok('Brak portów wystawionych na zewnątrz; wszystkie nasłuchują lokalnie')
    else:
        _ok('Porty widoczne z zewnątrz (nasłuch na wszystkich interfejsach lub adresach publicznych):')
        _w(f"  {_C.BOLD}{_pad('Prot', 6)}{_pad('Adres', 22)}{_pad('Port', 8)}{_C.RESET}\n")
        _hr()
        for proto, host, port, _ in visible:
            _w(f"  {_C.BCYAN}{_pad(proto, 6)}{_C.RESET}{_C.BGREEN}{_pad(host, 22)}{_C.RESET}{_C.BYELLOW}{_pad(str(port), 8)}{_C.RESET}\n")
    _w('\n')


def _cmd_openports(args, terminal):
    """Lista otwartych portów."""
    _section('Open Ports')
    open_ports, _ = _local_port_scan([p for p, _ in _COMMON_PORTS], timeout=0.4)
    if not open_ports:
        _warn('Brak otwartych portów na localhost wśród popularnych portów')
        _w('\n')
        return
    _w(f"  {_C.BOLD}{_pad('Port', 8)}{_pad('Usługa', 20)}{_pad('Opóźnienie', 12)}{_C.RESET}\n")
    _hr()
    for port, service, latency in open_ports:
        _w(f"  {_C.BCYAN}{_pad(str(port), 8)}{_C.RESET}{_C.BGREEN}{_pad(service or '?', 20)}{_C.RESET}{_pad(f'{latency:.1f} ms', 12)}\n")
    _w('\n')


def _cmd_blockedports(args, terminal):
    """Lista zablokowanych portów."""
    _section('Blocked Ports')
    _, blocked = _local_port_scan([p for p, _ in _COMMON_PORTS], timeout=0.4)
    if not blocked:
        _ok('Żaden z popularnych portów nie został zablokowany / wszystkie są otwarte')
        _w('\n')
        return
    _w(f"  {_C.BOLD}{_pad('Port', 8)}{_pad('Usługa', 20)}{_C.RESET}\n")
    _hr()
    for port in blocked:
        service = next((name for pp, name in _COMMON_PORTS if pp == port), '')
        _w(f"  {_C.BCYAN}{_pad(str(port), 8)}{_C.RESET}{_C.BGREEN}{_pad(service or '?', 20)}{_C.RESET}\n")
    _w('\n')


def _cmd_portscan_deep(args, terminal):
    _section("Port Scan — Deep (1-65535)")
    if not args:
        _warn("Użycie: diagnet portscan-deep <host>")
        _w(f"  {_C.DIM}Przykład: diagnet portscan-deep 192.168.1.1{_C.RESET}\n")
        _w(f"  {_C.YELLOW}Uwaga: skanuje 65535 portów — może zająć kilka minut!{_C.RESET}\n\n")
        return

    host = args[0]
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        _err(f"Nie można rozwiązać nazwy: {host}")
        _w("\n")
        return

    display = host if host != ip else ip
    _w(f"  Host:   {_C.BYELLOW}{display}{_C.RESET}  {_C.DIM}({ip}){_C.RESET}\n")
    _w(f"  Porty:  {_C.DIM}1–65535 (pełny zakres){_C.RESET}\n")
    _w(f"  Tryb:   {_C.DIM}TCP connect, 200 wątków, timeout 0.4s{_C.RESET}\n")
    _w(f"  {_C.YELLOW}[!] To może chwilę potrwać...{_C.RESET}\n\n")

    # Buduj pary (port, service) dla całego zakresu — partiami dla wizualizacji postępu
    port_map = {p: n for p, n in _COMMON_PORTS}
    chunk_size = 5000
    all_open: List[Tuple[int, str, float]] = []
    total_ports = 65535

    t0 = time.time()
    for chunk_start in range(1, total_ports + 1, chunk_size):
        chunk_end = min(chunk_start + chunk_size - 1, total_ports)
        chunk = [(p, port_map.get(p, '')) for p in range(chunk_start, chunk_end + 1)]
        pct = chunk_end / total_ports * 100
        _w(f"\r  {_C.DIM}Skanowanie {chunk_start:>5}–{chunk_end:<5}  [{pct:5.1f}%]{_C.RESET}")
        _sys.stdout.flush()
        open_chunk = _portscan_worker(ip, chunk, timeout=0.4, max_threads=200)
        all_open.extend(open_chunk)

    elapsed = time.time() - t0
    _w(f"\r  {_C.DIM}{'Gotowe':50}{_C.RESET}\n")

    _print_portscan_results(sorted(all_open, key=lambda x: x[0]), total_ports, elapsed)


def _cmd_socktest(args, terminal):
    """Test tworzenia gniazd TCP, UDP i RAW."""
    _section("Socket Test")
    if args:
        _warn("Użycie: diagnet socktest")
        _w("\n")
        return

    for label, family, sock_type, proto in [
        ("TCP", socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP),
        ("UDP", socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP),
        ("RAW", socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP),
    ]:
        try:
            s = socket.socket(family, sock_type, proto)
            s.close()
            _ok(f"Tworzenie gniazda {label} powiodło się")
        except Exception as e:
            _err(f"{label}: {e}")
    _w("\n")


def _cmd_socktcp(args, terminal):
    """Test połączenia TCP."""
    _section("Socket TCP")
    if len(args) < 2:
        _warn("Użycie: diagnet socktcp <host> <port>")
        _w("\n")
        return

    host = args[0]
    try:
        port = int(args[1])
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _err(f"Nieprawidłowy port: {args[1]}")
        _w("\n")
        return

    ok, ms, err = _tcp_connect(host, port, timeout=4.0)
    if ok:
        _ok(f"TCP {host}:{port} otwarte — czas {ms:.1f} ms")
    else:
        _err(f"TCP {host}:{port} nieosiągalne — {err}")
    _w("\n")


def _cmd_sockudp(args, terminal):
    """Test połączenia UDP."""
    _section("Socket UDP")
    if len(args) < 2:
        _warn("Użycie: diagnet sockudp <host> <port>")
        _w("\n")
        return

    host = args[0]
    try:
        port = int(args[1])
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _err(f"Nieprawidłowy port: {args[1]}")
        _w("\n")
        return

    ok, ms, err, data = _udp_probe(host, port, timeout=3.0)
    if not ok:
        _err(f"UDP {host}:{port} błąd — {err}")
    else:
        if data is not None:
            _ok(f"UDP {host}:{port} wysłane i odebrano odpowiedź w {ms:.1f} ms")
            _w(f"  {_C.DIM}Odpowiedź: {data}{_C.RESET}\n")
        else:
            _warn(f"UDP {host}:{port} wysłane — brak odpowiedzi (UDP nie gwarantuje odpowiedzi)")
            _w(f"  {_C.DIM}Czas wysłania: {ms:.1f} ms{_C.RESET}\n")
    _w("\n")


def _cmd_sockraw(args, terminal):
    """Test gniazda RAW."""
    _section("Socket RAW")
    host = args[0] if args else ''
    if host:
        _w(f"  Host: {_C.BYELLOW}{host}{_C.RESET}\n\n")
    ok, err = _create_raw_socket()
    if ok:
        _ok("Gniazdo RAW zostało utworzone")
    else:
        _err(f"Nie udało się utworzyć gniazda RAW — {err}")
    if host and ok:
        try:
            ip = socket.gethostbyname(host)
            _w(f"  {_C.DIM}Rozwiązano do {ip}{_C.RESET}\n")
        except Exception as e:
            _warn(f"Nie można rozwiązać hosta: {e}")
    _w("\n")


def _cmd_sockecho(args, terminal):
    """Echo test TCP/UDP."""
    _section("Socket Echo")
    if len(args) < 3:
        _warn("Użycie: diagnet sockecho <tcp|udp> <host> <port>")
        _w("\n")
        return

    proto = args[0].lower()
    host = args[1]
    try:
        port = int(args[2])
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _err(f"Nieprawidłowy port: {args[2]}")
        _w("\n")
        return

    payload = b'netdiag-echo-test'
    if proto == 'tcp':
        try:
            ip = socket.gethostbyname(host)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            t0 = time.time()
            sock.connect((ip, port))
            sock.sendall(payload)
            data = sock.recv(1024)
            elapsed = (time.time() - t0) * 1000
            sock.close()
            if data:
                _ok(f"Echo TCP {host}:{port} udane — {elapsed:.1f} ms")
                _w(f"  {_C.DIM}Odpowiedź: {data[:128].decode('utf-8', errors='replace')}{_C.RESET}\n")
            else:
                _warn(f"Echo TCP {host}:{port} wysłane, ale brak odpowiedzi")
        except Exception as e:
            _err(f"Echo TCP nieudane — {e}")
    elif proto == 'udp':
        try:
            ip = socket.gethostbyname(host)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            t0 = time.time()
            sock.sendto(payload, (ip, port))
            try:
                data, _ = sock.recvfrom(1024)
                elapsed = (time.time() - t0) * 1000
                _ok(f"Echo UDP {host}:{port} udane — {elapsed:.1f} ms")
                _w(f"  {_C.DIM}Odpowiedź: {data[:128].decode('utf-8', errors='replace')}{_C.RESET}\n")
            except socket.timeout:
                elapsed = (time.time() - t0) * 1000
                _warn(f"Echo UDP {host}:{port} wysłane, brak odpowiedzi — {elapsed:.1f} ms")
            finally:
                sock.close()
        except Exception as e:
            _err(f"Echo UDP nieudane — {e}")
    else:
        _err(f"Nieznany protokół: {proto}. Użyj tcp lub udp")
    _w("\n")


def _cmd_socklatency(args, terminal):
    """Pomiar opóźnienia socketów TCP/UDP."""
    _section("Socket Latency")
    if len(args) < 3:
        _warn("Użycie: diagnet socklatency <tcp|udp> <host> <port> [liczba=5]")
        _w("\n")
        return

    proto = args[0].lower()
    host = args[1]
    try:
        port = int(args[2])
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _err(f"Nieprawidłowy port: {args[2]}")
        _w("\n")
        return

    count = int(args[3]) if len(args) > 3 and args[3].isdigit() else 5
    count = max(1, min(count, 20))
    _w(f"  Protokoł: {_C.BYELLOW}{proto.upper()}{_C.RESET}\n")
    _w(f"  Host:    {_C.BYELLOW}{host}{_C.RESET}\n")
    _w(f"  Port:    {_C.BCYAN}{port}{_C.RESET}\n")
    _w(f"  Próby:   {_C.DIM}{count}{_C.RESET}\n\n")

    times: List[float] = []
    errors = 0

    for i in range(1, count + 1):
        if proto == 'tcp':
            ok, ms, err = _tcp_connect(host, port, timeout=3.0)
            if ok:
                times.append(ms)
                bar = _latency_bar(ms)
                _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {bar}\n")
            else:
                errors += 1
                _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {_C.RED}✗ {_C.RESET}{_C.DIM}{err}{_C.RESET}\n")
        elif proto == 'udp':
            ok, ms, err, _ = _udp_probe(host, port, timeout=3.0)
            if ok:
                times.append(ms)
                bar = _latency_bar(ms)
                _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {bar}\n")
            else:
                errors += 1
                _w(f"  {_C.DIM}[{i:>2}]{_C.RESET} {_C.RED}✗ {_C.RESET}{_C.DIM}{err}{_C.RESET}\n")
        else:
            _err(f"Nieznany protokół: {proto}. Użyj tcp lub udp")
            _w("\n")
            return
        time.sleep(0.1)

    _hr()
    _w(f"\n  Próby: {_C.BWHITE}{count}{_C.RESET}  "
       f"OK: {_C.BGREEN}{len(times)}{_C.RESET}  "
       f"Błędy: {_C.RED if errors > 0 else _C.DIM}{errors}{_C.RESET}\n")
    if times:
        _w(f"  Min: {_C.BGREEN}{min(times):.1f} ms{_C.RESET}  "
           f"Max: {_C.BYELLOW}{max(times):.1f} ms{_C.RESET}  "
           f"Avg: {_C.BWHITE}{sum(times)/len(times):.1f} ms{_C.RESET}\n")
    _w("\n")


# ═══════════════════════════════════════════════════════════════════════════════
# CML — Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def cml_menu():
    _cmd_net_menu([], None)



def _cmd_httphead(args, terminal):
    """HTTP HEAD request — nagłówki odpowiedzi (net head)."""
    if not args:
        _warn("Użycie: diagnet.httphead <url>")
        return
    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    _w(f"  {_C.DIM}HEAD {url}…{_C.RESET}\n")
    ok, status, t_conn, t_total, _, hdrs = _http_request(url, head_only=True, timeout=10)
    color = _C.BGREEN if ok and status < 400 else _C.RED
    _w(f"  {color}{status}{_C.RESET}  {_C.DIM}(połączenie {t_conn:.0f} ms / całkowity {t_total:.0f} ms){_C.RESET}\n")
    if hdrs:
        _w(f"\n")
        for k, v in hdrs.items():
            _w(f"  {_C.BYELLOW}{k:<28}{_C.RESET} {v}\n")
    _w("\n")

CML_COMMANDS = {
    # menu
    "diagnet":              _cmd_net_menu,
    "netdiag":              _cmd_net_menu,

    # basic
    "diagnet.netinfo":      _cmd_netinfo,
    "diagnet.iplocal":      _cmd_iplocal,
    "diagnet.ippublic":     _cmd_ippublic,
    "diagnet.iflist":       _cmd_iflist,
    "diagnet.ifstatus":     _cmd_ifstatus,
    "diagnet.macresolve":   _cmd_macresolve,
    "diagnet.gateway":      _cmd_gateway,
    "diagnet.routes":       _cmd_routes,

    # dns
    "diagnet.dnslookup":    _cmd_dnslookup,
    "diagnet.dnsresolve":   _cmd_dnsresolve,
    "diagnet.dnsreverse":   _cmd_dnsreverse,
    "diagnet.dnsrecord":    _cmd_dnsrecord,
    "diagnet.dnstest":      _cmd_dnstest,
    "diagnet.dnssoa":       _cmd_dnssoa,
    "diagnet.dnsns":        _cmd_dnsns,
    "diagnet.dnsaaaa":      _cmd_dnsaaaa,
    "diagnet.dnsaaaaa":     _cmd_dnsaaaaa,
    "diagnet.dnsall":       _cmd_dnsall,

    # connection testing
    "diagnet.netping":      _cmd_netping,
    "diagnet.tcping":       _cmd_tcping,
    "diagnet.httpping":     _cmd_httpping,
    "diagnet.httpget":      _cmd_httpget,
    "diagnet.httpsget":     _cmd_httpsget,
    "diagnet.portcheck":    _cmd_portcheck,
    "diagnet.portscan":     _cmd_portscan,
    "diagnet.portscan-fast":_cmd_portscan_fast,
    "diagnet.portscan-deep":_cmd_portscan_deep,

    # socket / protocol
    "diagnet.socktest":     _cmd_socktest,
    "diagnet.socktcp":      _cmd_socktcp,
    "diagnet.sockudp":      _cmd_sockudp,
    "diagnet.sockraw":      _cmd_sockraw,
    "diagnet.sockecho":     _cmd_sockecho,
    "diagnet.socklatency":  _cmd_socklatency,

    # discovery / enumeration
    "diagnet.netscan":      _cmd_netscan,
    "diagnet.subnetscan":   _cmd_subnetscan,
    "diagnet.hostscan":     _cmd_hostscan,
    "diagnet.servicedetect":_cmd_servicedetect,
    "diagnet.bannergrab":   _cmd_bannergrab,
    "diagnet.fingerprint":  _cmd_fingerprint,
    "diagnet.arpdiscover":  _cmd_arpdiscover,
    "diagnet.neighbordiscover": _cmd_neighbordiscover,

    # security / visibility
    "diagnet.firewallcheck":   _cmd_firewallcheck,
    "diagnet.proxycheck":      _cmd_proxycheck,
    "diagnet.vpnstatus":       _cmd_vpnstatus,
    "diagnet.torcheck":        _cmd_torcheck,
    "diagnet.dnsleak":         _cmd_dnsleak,
    "diagnet.portvisibility":  _cmd_portvisibility,
    "diagnet.openports":       _cmd_openports,
    "diagnet.blockedports":    _cmd_blockedports,
    "diagnet.httphead":        _cmd_httphead,
}

def on_load():
    """Optional initialization hook called when module loads."""
    pass


# ── EcoSystem integration ─────────────────────────────────────────────────────

MODULE_CMD = "net.diag"

def setup(terminal):
    """Rejestruje net.diag + alias net w TerminalX EcoSystem (kategoria: sieć)."""
    on_load()

    cat = terminal.t("cat_net")

    # ── net.diag — główna komenda ─────────────────────────────────────────────
    def _net_diag(args):
        if not args:
            _cmd_net_menu([], terminal)
        else:
            _cmd_net_menu(args, terminal)

    terminal.register_command(
        "net.diag", _net_diag,
        description=terminal.t("cmd_net_diag"),
        category=cat,
    )




def _compat_ip(args, terminal):
    """Dispatcher net ip [public|local|all] → net_diag equivalents."""
    mode = args[0].lower() if args else "all"
    if mode in ("local", "all"):
        _cmd_iplocal([], terminal)
    if mode in ("public", "all"):
        _cmd_ippublic([], terminal)


def teardown(terminal):
    """Wyrejestrowuje net.diag i net z TerminalX EcoSystem."""
    terminal.commands.pop("net.diag", None)
