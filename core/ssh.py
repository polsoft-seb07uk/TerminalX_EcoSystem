"""SSH core module for TerminalX EcoSystem.

SSH/SFTP client — tunnels, SFTP, keys, connection manager.
Requires: paramiko

Author  : Sebastian Januchowski
Company : polsoft.ITS(TM) Group
Web     : www.polsoft.gt.tc
GitHub  : https://github.com/seb07uk
E-mail  : polsoft.its@fastservice.com
License : MIT
"""


from __future__ import annotations

import os
import sys
import json
import socket
import threading
import time
import stat
import getpass
import select as _select
import shutil
import platform
import base64
import hashlib
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

from ._shared import IS_WIN as _IS_WINDOWS, _w, RST, BOLD, DIM, RED, GRN, YLW, CYN, BCYN, BLU, MGT, WHT

# ─── Pomocnicze funkcje komunikatów ──────────────────────────────────────────
def _err(msg: str) -> None:
    _w(f"  {RED}[!] {msg}{RST}\n")

def _warn(msg: str) -> None:
    _w(f"  {YLW}[!] {msg}{RST}\n")

def _ok(msg: str) -> None:
    _w(f"  {GRN}[+] {msg}{RST}\n")

def _inf(msg: str) -> None:
    _w(f"  {CYN}[i] {msg}{RST}\n")

# ─── Metadane modułu ─────────────────────────────────────────────────────────

MODULE_NAME    = "ssh"
MODULE_VERSION = "2.0.0"
MODULE_DESC    = "Klient SSH/SFTP — tunele, SFTP, klucze, menedżer połączeń"

# ─── Ścieżki konfiguracyjne ───────────────────────────────────────────────────

_SSH_DIR      = Path.home() / ".crossterm" / "ssh"
_HOSTS_FILE   = _SSH_DIR / "hosts.json"
_KEYS_DIR     = _SSH_DIR / "keys"
_KNOWN_HOSTS  = Path.home() / ".ssh" / "known_hosts"
_SYSTEM_SSH_DIR = Path.home() / ".ssh"

def _ensure_dirs() -> None:
    _SSH_DIR.mkdir(parents=True, exist_ok=True)
    _KEYS_DIR.mkdir(parents=True, exist_ok=True)
    _SYSTEM_SSH_DIR.mkdir(parents=True, exist_ok=True)
    # Bezpieczne uprawnienia dla katalogu kluczy
    try:
        os.chmod(_KEYS_DIR, 0o700)
        os.chmod(_SYSTEM_SSH_DIR, 0o700)
    except Exception:
        pass

# ─── Menedżer połączeń (bookmarks) ───────────────────────────────────────────

def _load_hosts() -> Dict[str, dict]:
    _ensure_dirs()
    if _HOSTS_FILE.exists():
        try:
            return json.loads(_HOSTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_hosts(hosts: Dict[str, dict]) -> None:
    _ensure_dirs()
    _HOSTS_FILE.write_text(
        json.dumps(hosts, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

def _get_host_entry(name: str) -> Optional[dict]:
    return _load_hosts().get(name)

# ─── Import paramiko z graceful degradation ──────────────────────────────────

_PARAMIKO_OK = False
try:
    import paramiko
    _PARAMIKO_OK = True
except ImportError:
    paramiko = None  # type: ignore

def _require_paramiko() -> bool:
    if _PARAMIKO_OK:
        return True
    _err("Biblioteka 'paramiko' nie jest zainstalowana.")
    _w("\n  Zainstaluj ją komendą:\n")
    _w(f"    {BCYN}pip install paramiko{RST}\n\n")
    return False

# ─── Parsowanie adresu ────────────────────────────────────────────────────────

def _parse_target(target: str) -> Tuple[str, str, int]:
    """Parsuj [user@]host[:port] → (user, host, port).

    Obsługuje IPv6 w nawiasach kwadratowych: user@[::1]:2222
    """
    user = getpass.getuser()
    port = 22
    if "@" in target:
        user, target = target.split("@", 1)

    # IPv6 w nawiasach: [::1] lub [::1]:port
    if target.startswith("["):
        end = target.find("]")
        if end != -1:
            host = target[1:end]
            rest = target[end+1:]
            if rest.startswith(":"):
                try:
                    port = int(rest[1:])
                except ValueError:
                    pass
            return user, host, port

    # Zwykły host lub host:port (nie IPv6 bez nawiasów)
    if ":" in target:
        host, port_s = target.rsplit(":", 1)
        try:
            port = int(port_s)
        except ValueError:
            host = target
    else:
        host = target
    return user, host, port

# ─── Wczytywanie klucza prywatnego ───────────────────────────────────────────

def _load_pkey(path: str, password: Optional[str] = None):
    """Próbuje wczytać klucz prywatny (auto-detekcja algorytmu).

    Hasło do zaszyfrowanego klucza pytane jest co najwyżej raz —
    po uzyskaniu próbuje wszystkich loaderów z tym samym hasłem.
    """
    if not _PARAMIKO_OK:
        return None
    loaders = [
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.RSAKey,
        paramiko.DSSKey,
    ]
    passphrase_asked = False
    pwd = password

    for loader in loaders:
        try:
            return loader.from_private_key_file(path, password=pwd)
        except paramiko.ssh_exception.PasswordRequiredException:
            if not passphrase_asked:
                try:
                    pwd = getpass.getpass(f"  Hasło do klucza {path}: ")
                except (KeyboardInterrupt, EOFError):
                    return None
                passphrase_asked = True
            try:
                return loader.from_private_key_file(path, password=pwd)
            except Exception:
                continue
        except Exception:
            continue
    return None

def _find_default_keys() -> List[str]:
    """Zwraca listę domyślnych kluczy SSH użytkownika."""
    names = ["id_ed25519", "id_ecdsa", "id_rsa", "id_dsa"]
    found = []
    for name in names:
        p = _SYSTEM_SSH_DIR / name
        if p.exists():
            found.append(str(p))
    # Klucze w katalogu crossterm
    for p in _KEYS_DIR.glob("*.key"):
        found.append(str(p))
    return found

# ─── Tworzenie klienta SSH ────────────────────────────────────────────────────

def _make_client(
    host: str,
    port: int,
    user: str,
    password: Optional[str] = None,
    key_file: Optional[str] = None,
    timeout: int = 15,
    ignore_host_key: bool = False,
) -> "paramiko.SSHClient":
    """Tworzy i zwraca połączonego klienta SSH lub rzuca wyjątek."""
    client = paramiko.SSHClient()

    # Polityka weryfikacji hosta
    if ignore_host_key:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
        try:
            if _KNOWN_HOSTS.exists():
                client.load_host_keys(str(_KNOWN_HOSTS))
        except Exception:
            pass
        try:
            client.load_system_host_keys()
        except Exception:
            pass

    connect_kwargs: dict = dict(
        hostname=host,
        port=port,
        username=user,
        timeout=timeout,
        look_for_keys=True,
        allow_agent=True,
    )

    # Klucz prywatny
    if key_file:
        pkey = _load_pkey(key_file)
        if pkey:
            connect_kwargs["pkey"] = pkey
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False
        else:
            _warn(f"Nie udało się wczytać klucza: {key_file}")

    # Hasło
    if password:
        connect_kwargs["password"] = password

    client.connect(**connect_kwargs)
    return client

# ─── Interaktywna powłoka PTY ─────────────────────────────────────────────────

def _interactive_shell(client: "paramiko.SSHClient", host: str) -> None:
    """Uruchamia interaktywną sesję PTY (cross-platform: Unix + Windows)."""
    chan = client.invoke_shell(
        term=os.environ.get("TERM", "xterm-256color"),
        width=shutil.get_terminal_size((80, 24)).columns,
        height=shutil.get_terminal_size((80, 24)).lines,
    )
    chan.setblocking(False)
    _w(f"\n  {DIM}Nawiązano połączenie SSH. Wpisz ~. aby się rozłączyć.{RST}\n\n")

    if _IS_WINDOWS:
        _interactive_shell_windows(chan)
    else:
        _interactive_shell_unix(chan)

    chan.close()


def _interactive_shell_unix(chan) -> None:
    """PTY shell dla Unix/Linux/macOS — używa tty/termios."""
    try:
        import tty
        import termios as _termios
    except ImportError:
        _err("Moduł 'tty'/'termios' niedostępny na tej platformie.")
        return

    old_settings = None
    try:
        fd = sys.stdin.fileno()
        old_settings = _termios.tcgetattr(fd)
        tty.setraw(fd)

        escape_seq_buf = ""
        while True:
            r, _, _ = _select.select([chan, sys.stdin], [], [], 0.1)

            if chan in r:
                try:
                    data = chan.recv(4096)
                    if not data:
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                except Exception:
                    break

            if sys.stdin in r:
                try:
                    ch_bytes = os.read(fd, 1)
                except OSError:
                    break
                if not ch_bytes:
                    break
                ch = ch_bytes.decode("utf-8", errors="replace")

                escape_seq_buf += ch
                if escape_seq_buf.endswith("\r~."):
                    _w(f"\n\n  {GRN}Połączenie zakończone.{RST}\n")
                    break
                if len(escape_seq_buf) > 3:
                    escape_seq_buf = escape_seq_buf[-3:]

                if chan.closed:
                    break
                chan.send(ch_bytes)

            if chan.exit_status_ready():
                break

    except KeyboardInterrupt:
        _w(f"\n  {YLW}Przerwano przez użytkownika.{RST}\n")
    finally:
        if old_settings is not None:
            try:
                import termios as _t
                _t.tcsetattr(sys.stdin.fileno(), _t.TCSADRAIN, old_settings)
            except Exception:
                pass


def _interactive_shell_windows(chan) -> None:
    """PTY shell dla Windows — używa msvcrt + wątku do odczytu stdin."""
    import msvcrt  # type: ignore[import]

    stop_event = threading.Event()

    def _read_stdin():
        """Wątek czytający klawiaturę na Windows przez msvcrt."""
        escape_seq_buf = ""
        try:
            while not stop_event.is_set() and not chan.closed:
                if msvcrt.kbhit():
                    ch_bytes = msvcrt.getwch().encode("utf-8", errors="replace")
                    ch = ch_bytes.decode("utf-8", errors="replace")
                    escape_seq_buf += ch
                    if escape_seq_buf.endswith("\r~."):
                        stop_event.set()
                        break
                    if len(escape_seq_buf) > 3:
                        escape_seq_buf = escape_seq_buf[-3:]
                    chan.send(ch_bytes)
                else:
                    time.sleep(0.01)
        except Exception:
            stop_event.set()

    t = threading.Thread(target=_read_stdin, daemon=True)
    t.start()

    try:
        while not stop_event.is_set():
            if chan.exit_status_ready():
                break
            try:
                r, _, _ = _select.select([chan], [], [], 0.1)
                if chan in r:
                    data = chan.recv(4096)
                    if not data:
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
            except Exception:
                break
    except KeyboardInterrupt:
        _w(f"\n  {YLW}Przerwano przez użytkownika.{RST}\n")
    finally:
        stop_event.set()
        _w(f"\n\n  {GRN}Połączenie zakończone.{RST}\n")

# ═══════════════════════════════════════════════════════════════════════════════
#  KOMENDA: ssh
# ═══════════════════════════════════════════════════════════════════════════════

_SSH_COMMANDS = """
  {BOLD}{WHT}SSH — Moduł CrossTerm v2.0{RST}  {DIM}(ssh help — pełna pomoc){RST}

  {BCYN}Połączenie{RST}
    ssh {WHT}<host>{RST}                połącz (bieżący użytkownik, port 22)
    ssh {WHT}run{RST} <host> <cmd>      wykonaj polecenie zdalnie

  {BCYN}Menedżer połączeń{RST}
    ssh {WHT}save{RST} <nazwa> user@host  zapisz połączenie
    ssh {WHT}list{RST}                  lista zapisanych połączeń
    ssh {WHT}info{RST} <nazwa>           szczegóły połączenia
    ssh {WHT}del{RST}  <nazwa>           usuń zapisane połączenie

  {BCYN}SFTP{RST}
    ssh {WHT}sftp{RST} <host>            otwórz sesję SFTP

  {BCYN}Tunelowanie{RST}
    ssh {WHT}tunnel{RST} local  <spec> <host>
    ssh {WHT}tunnel{RST} remote <spec> <host>
    ssh {WHT}tunnel{RST} list / stop <id>

  {BCYN}Klucze{RST}
    ssh {WHT}keygen{RST} [ed25519|rsa|ecdsa] [nazwa]
    ssh {WHT}keys{RST}                  lista kluczy
    ssh {WHT}pubkey{RST} [plik]          wyświetl klucz publiczny
    ssh {WHT}copy-id{RST} user@host      skopiuj klucz na serwer

  {BCYN}Diagnostyka{RST}
    ssh {WHT}test{RST} <host>            test połączenia
    ssh {WHT}keyscan{RST} <host>         fingerprint hosta
    ssh {WHT}known-hosts{RST} [del <host>]
"""

_SSH_HELP = """
  {BOLD}{WHT}SSH — Moduł CrossTerm v2.0{RST}

  {BCYN}Połączenie:{RST}
    ssh <host>                         połącz (bieżący użytkownik, port 22)
    ssh user@host                      połącz jako user
    ssh user@host:2222                 połącz na niestandardowy port
    ssh user@host -i ~/.ssh/id_rsa     połącz kluczem prywatnym
    ssh user@host -p 2222              alternatywna składnia portu
    ssh user@host -k                   pomiń weryfikację klucza hosta
    ssh user@host -t 30                timeout połączenia (domyślnie 15s)

  {BCYN}Wykonywanie poleceń:{RST}
    ssh run <host> <polecenie>         wykonaj polecenie zdalnie
    ssh run user@host:2222 "ls -la"   z portem i użytkownikiem
    ssh run <host> <polecenie> -T 120 timeout polecenia w sekundach (domyślnie 60)

  {BCYN}Menedżer połączeń:{RST}
    ssh save <nazwa> user@host[:port] [-i klucz] [-p hasło]
    ssh list                           lista zapisanych połączeń
    ssh info <nazwa>                   szczegóły połączenia
    ssh del <nazwa>                    usuń zapisane połączenie
    ssh <nazwa>                        połącz używając zapisanej nazwy

  {BCYN}SFTP:{RST}
    ssh sftp <host>                    otwórz sesję SFTP
    (w sesji SFTP: ls, cd, lcd, get, put, rm, mkdir, chmod, stat, quit)

  {BCYN}Tunelowanie portów:{RST}
    ssh tunnel local  <[lhost:]lport:rhost:rport> user@host
    ssh tunnel remote <[rhost:]rport:lhost:lport> user@host
    ssh tunnel list                    lista aktywnych tuneli
    ssh tunnel stop <id>               zatrzymaj tunel

  {BCYN}Klucze:{RST}
    ssh keygen [ed25519|rsa|ecdsa] [nazwa]   generuj parę kluczy
    ssh keygen                         (domyślnie: ed25519, id_ed25519)
    ssh keys                           lista kluczy w ~/.ssh i ~/.crossterm/ssh/keys
    ssh pubkey [plik_klucza]           wyświetl klucz publiczny
    ssh copy-id user@host [klucz]      skopiuj klucz publiczny na serwer

  {BCYN}Diagnostyka:{RST}
    ssh test <host>                    test połączenia (ping SSH)
    ssh keyscan <host>                 wyświetl fingerprint hosta
    ssh known-hosts                    lista wpisów known_hosts
    ssh known-hosts del <host>         usuń wpis z known_hosts

  {BCYN}Opcje połączenia:{RST}
    -i <plik>    klucz prywatny
    -p <hasło>   hasło (niezalecane; lepiej użyj klucza)
    -P <port>    port (alternatywa dla user@host:port)
    -k           ignoruj weryfikację klucza hosta (AutoAddPolicy)
    -t <s>       timeout w sekundach
"""

def _cmd_ssh(args: List[str], terminal=None) -> None:
    if not args:
        _w(_SSH_COMMANDS)
        return

    sub = args[0]

    # ── Subkomendy słownikowe ────────────────────────────────────────────────
    if sub in ("help", "--help", "-h", "?"):
        _w(_SSH_HELP)
    elif sub == "run":
        _ssh_run(args[1:])
    elif sub == "sftp":
        _ssh_sftp(args[1:])
    elif sub == "save":
        _ssh_save(args[1:])
    elif sub == "list":
        _ssh_list()
    elif sub == "info":
        _ssh_info(args[1:])
    elif sub in ("del", "delete", "remove", "rm"):
        _ssh_del(args[1:])
    elif sub == "tunnel":
        _ssh_tunnel(args[1:])
    elif sub == "keygen":
        _ssh_keygen(args[1:])
    elif sub == "keys":
        _ssh_keys()
    elif sub == "pubkey":
        _ssh_pubkey(args[1:])
    elif sub in ("copy-id", "copyid"):
        _ssh_copy_id(args[1:])
    elif sub == "test":
        _ssh_test(args[1:])
    elif sub == "keyscan":
        _ssh_keyscan(args[1:])
    elif sub in ("known-hosts", "known_hosts"):
        _ssh_known_hosts(args[1:])
    else:
        # Może to być nazwa zapisanego połączenia lub bezpośredni adres
        _ssh_connect(args)

def _parse_conn_args(args: List[str]) -> Tuple[str, str, int, Optional[str], Optional[str], int, bool]:
    """Parsuj argumenty połączenia → (user, host, port, key, password, timeout, ignore_key)."""
    # Sprawdź czy to zapisana nazwa
    if args and not any(c in args[0] for c in ["@", ".", ":"]) and args[0].isidentifier():
        entry = _get_host_entry(args[0])
        if entry:
            user = entry.get("user", getpass.getuser())
            host = entry["host"]
            port = int(entry.get("port", 22))
            key  = entry.get("key")
            pwd  = entry.get("password")
            timeout = int(entry.get("timeout", 15))
            ignore  = entry.get("ignore_host_key", False)
            return user, host, port, key, pwd, timeout, ignore

    # Bezpośredni adres
    target = args[0]
    user, host, port = _parse_target(target)

    key = None
    pwd = None
    timeout = 15
    ignore  = False

    i = 1
    while i < len(args):
        a = args[i]
        if a in ("-i",) and i + 1 < len(args):
            key = args[i + 1]; i += 2
        elif a in ("-p",) and i + 1 < len(args):
            pwd = args[i + 1]; i += 2
        elif a in ("-P",) and i + 1 < len(args):
            try: port = int(args[i + 1])
            except ValueError: pass
            i += 2
        elif a in ("-t",) and i + 1 < len(args):
            try: timeout = int(args[i + 1])
            except ValueError: pass
            i += 2
        elif a == "-k":
            ignore = True; i += 1
        else:
            i += 1

    return user, host, port, key, pwd, timeout, ignore

def _ssh_connect(args: List[str]) -> None:
    if not _require_paramiko():
        return
    user, host, port, key, password, timeout, ignore_key = _parse_conn_args(args)

    if not password and not key:
        # Zapytaj o hasło jeśli nie ma klucza
        default_keys = _find_default_keys()
        if not default_keys:
            try:
                password = getpass.getpass(f"  Hasło dla {user}@{host}: ")
            except (KeyboardInterrupt, EOFError):
                _w("\n")
                _err("Anulowano.")
                return

    _w(f"\n  {DIM}Łączę z {BCYN}{user}@{host}:{port}{RST}{DIM}…{RST}\n")
    try:
        client = _make_client(host, port, user, password, key, timeout, ignore_key)
    except paramiko.AuthenticationException:
        _err("Błąd uwierzytelnienia — sprawdź login, hasło lub klucz.")
        return
    except paramiko.SSHException as e:
        _err(f"Błąd SSH: {e}")
        return
    except (socket.timeout, TimeoutError):
        _err(f"Przekroczono czas połączenia ({timeout}s).")
        return
    except socket.gaierror as e:
        _err(f"Nie można rozwiązać nazwy hosta: {e}")
        return
    except Exception as e:
        _err(f"Błąd połączenia: {e}")
        return

    _ok(f"Połączono z {BCYN}{host}:{port}{RST} jako {YLW}{user}{RST}")

    try:
        _interactive_shell(client, host)
    finally:
        client.close()

# ─── SSH RUN ─────────────────────────────────────────────────────────────────

def _ssh_run(args: List[str]) -> None:
    """ssh run <host> <polecenie> [-T <timeout_cmd>]"""
    if not _require_paramiko():
        return
    if len(args) < 2:
        _err("Użycie: ssh run <host> <polecenie>")
        return

    conn_args = [args[0]]
    cmd_parts = []
    cmd_timeout = 60
    i = 1
    while i < len(args):
        if args[i] in ("-i", "-p", "-P", "-t") and i + 1 < len(args):
            conn_args += [args[i], args[i+1]]; i += 2
        elif args[i] == "-k":
            conn_args.append("-k"); i += 1
        elif args[i] == "-T" and i + 1 < len(args):
            try: cmd_timeout = int(args[i+1])
            except ValueError: pass
            i += 2
        else:
            cmd_parts.append(args[i]); i += 1

    command = " ".join(cmd_parts)
    if not command:
        _err("Brak polecenia do wykonania.")
        return

    user, host, port, key, password, timeout, ignore_key = _parse_conn_args(conn_args)

    if not password and not key and not _find_default_keys():
        try:
            password = getpass.getpass(f"  Hasło dla {user}@{host}: ")
        except (KeyboardInterrupt, EOFError):
            _w("\n"); _err("Anulowano."); return

    _inf(f"Wykonuję na {user}@{host}:{port}: {BCYN}{command}{RST}")
    try:
        client = _make_client(host, port, user, password, key, timeout, ignore_key)
        stdin_, stdout_, stderr_ = client.exec_command(command, timeout=cmd_timeout)
        # Odczytaj stdout/stderr przed recv_exit_status aby uniknąć deadlocka
        out = stdout_.read().decode("utf-8", errors="replace")
        err = stderr_.read().decode("utf-8", errors="replace")
        exit_code = stdout_.channel.recv_exit_status()
        client.close()

        if out:
            _w(out)
        if err:
            _w(f"{YLW}{err}{RST}")
        if exit_code != 0:
            _w(f"  {DIM}Exit code: {exit_code}{RST}\n")
    except Exception as e:
        _err(f"Błąd: {e}")

# ─── SFTP ─────────────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def _fmt_mode(m: int) -> str:
    """Formatuj tryb pliku POSIX jako drwxrwxrwx."""
    bits = [
        (stat.S_IRUSR, "r"), (stat.S_IWUSR, "w"), (stat.S_IXUSR, "x"),
        (stat.S_IRGRP, "r"), (stat.S_IWGRP, "w"), (stat.S_IXGRP, "x"),
        (stat.S_IROTH, "r"), (stat.S_IWOTH, "w"), (stat.S_IXOTH, "x"),
    ]
    prefix = "d" if stat.S_ISDIR(m) else ("l" if stat.S_ISLNK(m) else "-")
    return prefix + "".join(c if m & bit else "-" for bit, c in bits)

def _ssh_sftp(args: List[str]) -> None:
    """Interaktywna sesja SFTP."""
    if not _require_paramiko():
        return
    if not args:
        _err("Użycie: ssh sftp <host>")
        return

    user, host, port, key, password, timeout, ignore_key = _parse_conn_args(args)

    if not password and not key and not _find_default_keys():
        try:
            password = getpass.getpass(f"  Hasło dla {user}@{host}: ")
        except (KeyboardInterrupt, EOFError):
            _w("\n"); _err("Anulowano."); return

    _inf(f"Łączę SFTP: {user}@{host}:{port}…")
    try:
        client = _make_client(host, port, user, password, key, timeout, ignore_key)
        sftp = client.open_sftp()
    except Exception as e:
        _err(f"Błąd SFTP: {e}"); return

    _ok(f"SFTP: {BCYN}{host}{RST}")
    _inf("Komendy: ls, cd, lcd, get, put, rm, rmdir, mkdir, chmod, stat, pwd, lpwd, quit")
    _w("\n")

    remote_cwd = "."
    try:
        remote_cwd = sftp.normalize(".")
    except Exception:
        pass
    local_cwd = str(Path.cwd())

    PROMPT = f"{BOLD}{BCYN}sftp>{RST} "

    while True:
        try:
            _w(PROMPT)
            line = sys.stdin.readline().strip()
        except (KeyboardInterrupt, EOFError):
            _w("\n"); break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        rest = parts[1:]

        # ── quit ──
        if cmd in ("quit", "bye", "exit", "q"):
            break

        # ── pwd ──
        elif cmd == "pwd":
            _w(f"  Zdalne: {BCYN}{remote_cwd}{RST}\n")

        # ── lpwd ──
        elif cmd == "lpwd":
            _w(f"  Lokalne: {GRN}{local_cwd}{RST}\n")

        # ── ls ──
        elif cmd in ("ls", "dir", "ll"):
            path = rest[0] if rest else remote_cwd
            try:
                entries = sftp.listdir_attr(path)
                entries.sort(key=lambda e: (not stat.S_ISDIR(e.st_mode or 0), e.filename.lower()))
                _w(f"\n  {DIM}{path}{RST}\n")
                for e in entries:
                    mode = _fmt_mode(e.st_mode or 0)
                    size = _fmt_size(e.st_size or 0).rjust(10)
                    mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.st_mtime or 0))
                    name = e.filename
                    if stat.S_ISDIR(e.st_mode or 0):
                        name_c = f"{BLU}{name}/{RST}"
                    elif e.st_mode and (e.st_mode & 0o111):
                        name_c = f"{GRN}{name}{RST}"
                    else:
                        name_c = name
                    _w(f"  {DIM}{mode}{RST}  {size}  {DIM}{mtime}{RST}  {name_c}\n")
                _w("\n")
            except Exception as ex:
                _err(f"ls: {ex}")

        # ── cd ──
        elif cmd == "cd":
            if not rest:
                _err("cd: podaj ścieżkę")
            else:
                try:
                    new_path = rest[0]
                    normalized = sftp.normalize(
                        new_path if new_path.startswith("/") else remote_cwd + "/" + new_path
                    )
                    sftp.chdir(normalized)
                    remote_cwd = normalized
                    _inf(f"→ {remote_cwd}")
                except Exception as ex:
                    _err(f"cd: {ex}")

        # ── lcd ──
        elif cmd == "lcd":
            if not rest:
                _err("lcd: podaj ścieżkę")
            else:
                try:
                    p = Path(rest[0]).expanduser()
                    if not p.is_absolute():
                        p = Path(local_cwd) / p
                    if not p.is_dir():
                        _err(f"lcd: nie ma takiego katalogu: {rest[0]}")
                    else:
                        local_cwd = str(p.resolve())
                        _inf(f"→ {local_cwd}")
                except Exception as ex:
                    _err(f"lcd: {ex}")

        # ── get ──
        elif cmd == "get":
            if not rest:
                _err("get: podaj nazwę pliku")
            else:
                remote_path = rest[0]
                if not remote_path.startswith("/"):
                    remote_path = remote_cwd + "/" + remote_path
                local_name = rest[1] if len(rest) > 1 else Path(remote_path).name
                local_path = str(Path(local_cwd) / local_name)
                try:
                    _inf(f"Pobieranie: {remote_path} → {local_path}")
                    _progress_sftp(sftp, "get", remote_path, local_path)
                    _ok(f"Pobrano: {local_name}")
                except Exception as ex:
                    _err(f"get: {ex}")

        # ── put ──
        elif cmd == "put":
            if not rest:
                _err("put: podaj nazwę pliku")
            else:
                local_path = str(Path(local_cwd) / rest[0])
                if not Path(local_path).exists():
                    _err(f"put: nie znaleziono pliku: {local_path}")
                else:
                    remote_name = rest[1] if len(rest) > 1 else Path(local_path).name
                    remote_path = remote_cwd + "/" + remote_name
                    try:
                        _inf(f"Wysyłanie: {local_path} → {remote_path}")
                        _progress_sftp(sftp, "put", local_path, remote_path)
                        _ok(f"Wysłano: {remote_name}")
                    except Exception as ex:
                        _err(f"put: {ex}")

        # ── rm ──
        elif cmd in ("rm", "delete", "del"):
            if not rest: _err("rm: podaj plik"); continue
            rp = rest[0] if rest[0].startswith("/") else remote_cwd + "/" + rest[0]
            try:
                sftp.remove(rp)
                _ok(f"Usunięto: {rest[0]}")
            except Exception as ex:
                _err(f"rm: {ex}")

        # ── rmdir ──
        elif cmd == "rmdir":
            if not rest: _err("rmdir: podaj katalog"); continue
            rp = rest[0] if rest[0].startswith("/") else remote_cwd + "/" + rest[0]
            try:
                sftp.rmdir(rp)
                _ok(f"Usunięto katalog: {rest[0]}")
            except Exception as ex:
                _err(f"rmdir: {ex}")

        # ── mkdir ──
        elif cmd == "mkdir":
            if not rest: _err("mkdir: podaj nazwę katalogu"); continue
            rp = rest[0] if rest[0].startswith("/") else remote_cwd + "/" + rest[0]
            try:
                sftp.mkdir(rp)
                _ok(f"Utworzono katalog: {rest[0]}")
            except Exception as ex:
                _err(f"mkdir: {ex}")

        # ── chmod ──
        elif cmd == "chmod":
            if len(rest) < 2: _err("chmod: chmod <tryb_octal> <plik>"); continue
            try:
                mode = int(rest[0], 8)
                rp = rest[1] if rest[1].startswith("/") else remote_cwd + "/" + rest[1]
                sftp.chmod(rp, mode)
                _ok(f"Zmieniono uprawnienia: {rest[1]} → {rest[0]}")
            except Exception as ex:
                _err(f"chmod: {ex}")

        # ── stat ──
        elif cmd == "stat":
            if not rest: _err("stat: podaj plik"); continue
            rp = rest[0] if rest[0].startswith("/") else remote_cwd + "/" + rest[0]
            try:
                s = sftp.stat(rp)
                _w(f"\n  {WHT}{rest[0]}{RST}\n")
                _w(f"  Rozmiar:       {_fmt_size(s.st_size or 0)}\n")
                _w(f"  Uprawnienia:   {_fmt_mode(s.st_mode or 0)}\n")
                _w(f"  Modyfikacja:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.st_mtime or 0))}\n")
                _w(f"  Dostęp:        {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.st_atime or 0))}\n")
                _w(f"  UID/GID:       {s.st_uid}/{s.st_gid}\n\n")
            except Exception as ex:
                _err(f"stat: {ex}")

        # ── help ──
        elif cmd in ("help", "?"):
            _w("""
  {BOLD}Komendy SFTP:{RST}
    ls [ścieżka]           listuj pliki
    cd <ścieżka>           zmień katalog zdalny
    lcd <ścieżka>          zmień katalog lokalny
    pwd / lpwd             pokaż bieżący katalog
    get <plik> [lokalny]   pobierz plik
    put <plik> [zdalny]    wyślij plik
    rm <plik>              usuń plik
    rmdir <katalog>        usuń katalog
    mkdir <katalog>        utwórz katalog
    chmod <tryb> <plik>    zmień uprawnienia (np. 644)
    stat <plik>            informacje o pliku
    quit / exit            zakończ sesję SFTP
\n""")

        else:
            _warn(f"Nieznana komenda SFTP: {cmd}. Wpisz 'help'.")

    sftp.close()
    client.close()
    _ok("Sesja SFTP zakończona.")

def _progress_sftp(sftp, direction: str, src: str, dst: str) -> None:
    """Transfer z paskiem postępu."""
    cols = shutil.get_terminal_size((80, 24)).columns
    bar_width = max(10, min(30, cols - 40))

    total_size = 0
    if direction == "get":
        try:
            total_size = sftp.stat(src).st_size or 0
        except Exception:
            total_size = 0
    else:
        try:
            total_size = os.path.getsize(src)
        except Exception:
            total_size = 0

    def _callback(done: int, total_bytes: int) -> None:
        tb = total_bytes or total_size
        if tb > 0:
            pct = done / tb
            filled = int(bar_width * pct)
            bar = "█" * filled + "░" * (bar_width - filled)
            _w(f"\r  [{BCYN}{bar}{RST}] {pct*100:5.1f}%  {_fmt_size(done)}/{_fmt_size(tb)}   ")

    if direction == "get":
        sftp.get(src, dst, callback=_callback)
    else:
        sftp.put(src, dst, callback=_callback)

    _w("\n")

# ─── MENEDŻER POŁĄCZEŃ ────────────────────────────────────────────────────────

def _ssh_save(args: List[str]) -> None:
    """ssh save <nazwa> user@host[:port] [-i klucz] [-p hasło]"""
    if len(args) < 2:
        _err("Użycie: ssh save <nazwa> user@host[:port] [-i klucz] [-P port] [-p hasło]")
        return

    name   = args[0]
    target = args[1]
    user, host, port = _parse_target(target)

    key = None
    pwd = None
    ignore_key = False
    timeout = 15
    i = 2
    while i < len(args):
        a = args[i]
        if a == "-i" and i + 1 < len(args): key = args[i+1]; i += 2
        elif a == "-p" and i + 1 < len(args): pwd = args[i+1]; i += 2
        elif a == "-P" and i + 1 < len(args):
            try: port = int(args[i+1])
            except ValueError: pass
            i += 2
        elif a == "-k": ignore_key = True; i += 1
        elif a == "-t" and i + 1 < len(args):
            try: timeout = int(args[i+1])
            except ValueError: pass
            i += 2
        else: i += 1

    hosts = _load_hosts()
    hosts[name] = {
        "host": host, "port": port, "user": user,
        "key": key, "password": pwd,
        "timeout": timeout, "ignore_host_key": ignore_key,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_hosts(hosts)
    _ok(f"Zapisano połączenie '{BCYN}{name}{RST}' → {user}@{host}:{port}")

def _ssh_list() -> None:
    hosts = _load_hosts()
    if not hosts:
        _inf("Brak zapisanych połączeń. Użyj: ssh save <nazwa> user@host")
        return
    _w(f"\n  {BOLD}{WHT}Zapisane połączenia SSH{RST}\n\n")
    _w(f"  {'Nazwa':<18} {'Użytkownik':<16} {'Host':<28} {'Port':<6} {'Klucz'}\n")
    _w(f"  {'─'*18} {'─'*16} {'─'*28} {'─'*6} {'─'*20}\n")
    for name, e in sorted(hosts.items()):
        key_info = Path(e["key"]).name if e.get("key") else ("●hasło" if e.get("password") else "auto")
        has_pwd = "🔑" if e.get("key") else ("🔒" if e.get("password") else "  ")
        _w(f"  {BCYN}{name:<18}{RST} "
           f"{YLW}{e.get('user',''):<16}{RST} "
           f"{e.get('host',''):<28} "
           f"{str(e.get('port',22)):<6} "
           f"{DIM}{key_info}{RST}\n")
    _w("\n")

def _ssh_info(args: List[str]) -> None:
    if not args: _err("ssh info <nazwa>"); return
    entry = _get_host_entry(args[0])
    if not entry:
        _err(f"Nie znaleziono połączenia: {args[0]}")
        return
    _w(f"\n  {BOLD}{WHT}{args[0]}{RST}\n\n")
    rows = [
        ("Host",        entry.get("host", "")),
        ("Port",        str(entry.get("port", 22))),
        ("Użytkownik",  entry.get("user", "")),
        ("Klucz",       entry.get("key") or "(brak)"),
        ("Hasło",       "●●●●●●" if entry.get("password") else "(brak)"),
        ("Timeout",     f"{entry.get('timeout', 15)}s"),
        ("Ignoruj klucz hosta", "TAK" if entry.get("ignore_host_key") else "NIE"),
        ("Dodano",      entry.get("created", "")),
    ]
    for k, v in rows:
        _w(f"  {BCYN}{k:<22}{RST} {v}\n")
    _w("\n")

def _ssh_del(args: List[str]) -> None:
    if not args: _err("ssh del <nazwa>"); return
    hosts = _load_hosts()
    if args[0] not in hosts:
        _err(f"Nie znaleziono: {args[0]}")
        return
    del hosts[args[0]]
    _save_hosts(hosts)
    _ok(f"Usunięto połączenie: {args[0]}")

# ─── TUNELOWANIE PORTÓW ───────────────────────────────────────────────────────

_tunnels: Dict[int, dict] = {}
_tunnel_lock = threading.Lock()
_tunnel_id_counter = [0]

def _next_tunnel_id() -> int:
    with _tunnel_lock:
        _tunnel_id_counter[0] += 1
        return _tunnel_id_counter[0]

def _ssh_tunnel(args: List[str]) -> None:
    if not args or args[0] == "list":
        _tunnel_list()
        return
    if args[0] == "stop":
        _tunnel_stop(args[1:])
        return
    if args[0] not in ("local", "remote", "l", "r"):
        _err("Użycie: ssh tunnel local|remote <spec> <host>")
        _err("  spec: [lhost:]lport:rhost:rport")
        return

    direction = "local" if args[0] in ("local", "l") else "remote"
    if len(args) < 3:
        _err(f"ssh tunnel {direction} <spec> <host>")
        return

    spec   = args[1]
    conn_a = args[2:]

    # Parsuj specyfikację [bind:]lport:rhost:rport
    parts = spec.split(":")
    if len(parts) == 3:
        bind_host = "127.0.0.1"
        local_port, remote_host, remote_port = parts
    elif len(parts) == 4:
        bind_host, local_port, remote_host, remote_port = parts
    else:
        _err(f"Nieprawidłowa specyfikacja tunelu: {spec}")
        return

    try:
        local_port  = int(local_port)
        remote_port = int(remote_port)
    except ValueError:
        _err("Porty muszą być liczbami całkowitymi.")
        return

    if not _require_paramiko():
        return

    user, host, port, key, password, timeout, ignore_key = _parse_conn_args(conn_a)

    if not password and not key and not _find_default_keys():
        try:
            password = getpass.getpass(f"  Hasło dla {user}@{host}: ")
        except (KeyboardInterrupt, EOFError):
            _w("\n"); _err("Anulowano."); return

    try:
        client = _make_client(host, port, user, password, key, timeout, ignore_key)
    except Exception as e:
        _err(f"Błąd połączenia: {e}"); return

    tid = _next_tunnel_id()
    stop_event = threading.Event()

    if direction == "local":
        desc = f"L {bind_host}:{local_port} → {remote_host}:{remote_port} via {host}"
        t = threading.Thread(
            target=_local_tunnel_thread,
            args=(client, bind_host, local_port, remote_host, remote_port, stop_event),
            daemon=True,
        )
    else:
        desc = f"R {host}:{remote_port} → {bind_host}:{local_port}"
        t = threading.Thread(
            target=_remote_tunnel_thread,
            args=(client, bind_host, local_port, remote_host, remote_port, stop_event),
            daemon=True,
        )

    with _tunnel_lock:
        _tunnels[tid] = {
            "id": tid, "desc": desc, "client": client,
            "stop": stop_event, "thread": t,
            "started": time.strftime("%H:%M:%S"),
        }

    t.start()
    _ok(f"Tunel #{tid} uruchomiony: {BCYN}{desc}{RST}")
    _inf("Użyj 'ssh tunnel list' / 'ssh tunnel stop <id>' do zarządzania.")

def _local_tunnel_thread(
    client, bind: str, lport: int,
    rhost: str, rport: int,
    stop_event: threading.Event,
) -> None:
    """Wątek lokalnego tunelu portowego (L)."""
    import socketserver

    class _Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                chan = client.get_transport().open_channel(
                    "direct-tcpip", (rhost, rport),
                    self.request.getpeername(),
                )
            except Exception:
                return
            while not stop_event.is_set():
                r, _, _ = _select.select([self.request, chan], [], [], 1)
                if self.request in r:
                    data = self.request.recv(1024)
                    if not data: break
                    chan.send(data)
                if chan in r:
                    data = chan.recv(1024)
                    if not data: break
                    self.request.send(data)
            chan.close()

    class _Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    try:
        with _Server((bind, lport), _Handler) as srv:
            srv.socket.settimeout(1)
            while not stop_event.is_set():
                try:
                    srv.handle_request()
                except Exception:
                    pass
    except Exception:
        pass

def _remote_tunnel_thread(
    client, bind: str, lport: int,
    rhost: str, rport: int,
    stop_event: threading.Event,
) -> None:
    """Wątek zdalnego tunelu portowego (R)."""
    transport = client.get_transport()
    try:
        transport.request_port_forward(rhost or "", rport)
    except Exception as e:
        _err(f"Zdalny tunel: nie można uruchomić nasłuchiwania na porcie {rport}: {e}")
        return

    while not stop_event.is_set():
        chan = transport.accept(timeout=1)
        if chan is None:
            continue
        sock = socket.socket()
        try:
            sock.connect((bind, lport))
        except Exception:
            chan.close()
            continue

        def _pipe(src, dst):
            try:
                while True:
                    r, _, _ = _select.select([src], [], [], 1)
                    if r:
                        data = src.recv(1024)
                        if not data: break
                        dst.send(data)
            except Exception:
                pass
            finally:
                try: src.close()
                except Exception: pass
                try: dst.close()
                except Exception: pass

        threading.Thread(target=_pipe, args=(chan, sock), daemon=True).start()
        threading.Thread(target=_pipe, args=(sock, chan), daemon=True).start()

def _tunnel_list() -> None:
    with _tunnel_lock:
        if not _tunnels:
            _inf("Brak aktywnych tuneli."); return
        _w(f"\n  {BOLD}Aktywne tunele SSH{RST}\n\n")
        _w(f"  {'ID':<5} {'Czas':<10} Opis\n")
        _w(f"  {'─'*5} {'─'*10} {'─'*50}\n")
        for tid, t in sorted(_tunnels.items()):
            alive = "✓" if t["thread"].is_alive() else "✗"
            _w(f"  {BCYN}#{tid:<4}{RST} {t['started']:<10} {t['desc']}  {DIM}{alive}{RST}\n")
        _w("\n")

def _tunnel_stop(args: List[str]) -> None:
    if not args: _err("ssh tunnel stop <id>"); return
    try:
        tid = int(args[0].lstrip("#"))
    except ValueError:
        _err("Podaj numer tunelu (np. ssh tunnel stop 1)"); return
    with _tunnel_lock:
        t = _tunnels.get(tid)
    if not t:
        _err(f"Tunel #{tid} nie istnieje."); return
    t["stop"].set()
    try: t["client"].close()
    except Exception: pass
    with _tunnel_lock:
        _tunnels.pop(tid, None)
    _ok(f"Tunel #{tid} zatrzymany.")

# ─── ZARZĄDZANIE KLUCZAMI ─────────────────────────────────────────────────────

def _ssh_keygen(args: List[str]) -> None:
    """Generuj parę kluczy SSH."""
    if not _require_paramiko():
        return

    algo = "ed25519"
    name = None
    bits = 4096

    i = 0
    while i < len(args):
        a = args[i].lower()
        if a in ("ed25519", "rsa", "ecdsa", "dsa"):
            algo = a; i += 1
        elif a in ("-b", "--bits") and i + 1 < len(args):
            try: bits = int(args[i+1])
            except ValueError: pass
            i += 2
        else:
            name = args[i]; i += 1

    if not name:
        name = f"id_{algo}"

    # Ścieżka wyjściowa
    key_path = _KEYS_DIR / f"{name}.key"
    pub_path = _KEYS_DIR / f"{name}.key.pub"

    # Sprawdź czy plik istnieje
    if key_path.exists():
        _w(f"  {YLW}Plik {key_path} już istnieje.{RST}\n")
        _w("  Nadpisać? [t/N] ")
        ans = sys.stdin.readline().strip().lower()
        if ans not in ("t", "y", "tak", "yes"):
            _inf("Anulowano."); return

    _w(f"\n  {DIM}Generuję klucz {algo.upper()}…{RST}\n")

    try:
        if algo == "ed25519":
            key = paramiko.Ed25519Key.generate()
        elif algo == "rsa":
            key = paramiko.RSAKey.generate(bits=bits)
        elif algo == "ecdsa":
            key = paramiko.ECDSAKey.generate()
        elif algo == "dsa":
            key = paramiko.DSSKey.generate(bits=1024)
        else:
            _err(f"Nieznany algorytm: {algo}"); return

        # Zapisz klucz prywatny
        key.write_private_key_file(str(key_path))
        try:
            os.chmod(key_path, 0o600)   # ignorowane na Windows
        except Exception:
            pass

        # Zapisz klucz publiczny
        pub_key_str = f"{key.get_name()} {key.get_base64()} {name}@crossterm\n"
        pub_path.write_text(pub_key_str, encoding="utf-8")
        try:
            os.chmod(pub_path, 0o644)   # ignorowane na Windows
        except Exception:
            pass

        _ok(f"Klucz prywatny: {BCYN}{key_path}{RST}")
        _ok(f"Klucz publiczny: {BCYN}{pub_path}{RST}")

        # Fingerprint
        raw = base64.b64decode(key.get_base64())
        digest = hashlib.sha256(raw).digest()
        fp = "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode()
        _inf(f"Fingerprint: {fp}")

        _w(f"\n  {DIM}Klucz publiczny:{RST}\n")
        _w(f"  {WHT}{pub_key_str.strip()}{RST}\n\n")

    except Exception as e:
        _err(f"Błąd generowania klucza: {e}")

def _ssh_keys() -> None:
    """Lista dostępnych kluczy SSH."""
    _w(f"\n  {BOLD}Klucze SSH{RST}\n\n")

    dirs = [
        (_SYSTEM_SSH_DIR, "Systemowe (~/.ssh)"),
        (_KEYS_DIR, "CrossTerm"),
    ]

    for directory, label in dirs:
        if not directory.exists():
            continue
        keys = list(directory.glob("id_*")) + list(directory.glob("*.key"))
        # Deduplikacja
        keys = [k for k in keys if not k.suffix == ".pub"]
        if not keys:
            continue
        _w(f"  {BCYN}{label}{RST}\n")
        for kp in sorted(keys):
            pub = Path(str(kp) + ".pub")
            has_pub = "+" if pub.exists() else " "
            size = kp.stat().st_size
            _w(f"    {has_pub} {WHT}{kp.name:<30}{RST}  {DIM}{size}B  {kp.parent}{RST}\n")
            if pub.exists():
                try:
                    pub_line = pub.read_text(encoding="utf-8").strip()[:80]
                    _w(f"      {DIM}{pub_line}…{RST}\n")
                except Exception:
                    pass
        _w("\n")

def _ssh_pubkey(args: List[str]) -> None:
    """Wyświetl klucz publiczny."""
    if args:
        kp = Path(args[0]).expanduser()
    else:
        # Szukaj domyślnego
        defaults = _find_default_keys()
        if not defaults:
            _err("Nie znaleziono kluczy. Użyj: ssh keygen")
            return
        kp = Path(defaults[0])

    pub_path = Path(str(kp) + ".pub")
    if pub_path.exists():
        content = pub_path.read_text(encoding="utf-8").strip()
        _w(f"\n  {BCYN}{pub_path}{RST}\n")
        _w(f"  {WHT}{content}{RST}\n\n")
    else:
        # Wygeneruj z klucza prywatnego
        if not _require_paramiko():
            return
        pkey = _load_pkey(str(kp))
        if pkey:
            pub = f"{pkey.get_name()} {pkey.get_base64()}"
            _w(f"\n  {WHT}{pub}{RST}\n\n")
        else:
            _err(f"Nie można wczytać klucza: {kp}")

def _ssh_copy_id(args: List[str]) -> None:
    """Skopiuj klucz publiczny na serwer (ssh-copy-id)."""
    if not _require_paramiko():
        return
    if not args:
        _err("Użycie: ssh copy-id user@host [plik_klucza_publicznego]")
        return

    conn_args = [args[0]]
    key_file  = args[1] if len(args) > 1 else None

    if not key_file:
        defaults = _find_default_keys()
        if not defaults:
            _err("Nie znaleziono kluczy. Użyj: ssh keygen")
            return
        key_file = defaults[0]

    # Wczytaj klucz publiczny
    pub_path = Path(str(key_file) + ".pub")
    if not pub_path.exists():
        pub_path = Path(key_file)
    if not pub_path.exists():
        _err(f"Nie znaleziono klucza publicznego: {key_file}")
        return

    pub_content = pub_path.read_text(encoding="utf-8").strip()

    user, host, port, _, password, timeout, ignore_key = _parse_conn_args(conn_args)

    if not password:
        try:
            password = getpass.getpass(f"  Hasło dla {user}@{host} (jednorazowe): ")
        except (KeyboardInterrupt, EOFError):
            _w("\n"); _err("Anulowano."); return

    _inf(f"Kopiuję klucz na {user}@{host}:{port}…")
    try:
        client = _make_client(host, port, user, password, None, timeout, ignore_key)
        sftp = client.open_sftp()
        try:
            # Utwórz ~/.ssh jeśli nie istnieje (cross-platform przez SFTP)
            try:
                sftp.stat(".ssh")
            except IOError:
                sftp.mkdir(".ssh")
            try:
                sftp.chmod(".ssh", 0o700)
            except Exception:
                pass

            # Dołącz klucz tylko jeśli jeszcze go nie ma
            try:
                with sftp.open(".ssh/authorized_keys", "r") as fh:
                    existing = fh.read().decode("utf-8", errors="replace")
            except IOError:
                existing = ""

            if pub_content not in existing:
                with sftp.open(".ssh/authorized_keys", "a") as fh:
                    fh.write(pub_content.rstrip("\n") + "\n")

            try:
                sftp.chmod(".ssh/authorized_keys", 0o600)
            except Exception:
                pass
        finally:
            sftp.close()

        client.close()
        _ok("Klucz skopiowany. Możesz teraz logować się bez hasła.")
    except Exception as e:
        _err(f"Błąd copy-id: {e}")

# ─── DIAGNOSTYKA ──────────────────────────────────────────────────────────────

def _ssh_test(args: List[str]) -> None:
    """Test połączenia SSH (banner + czas)."""
    if not _require_paramiko():
        return
    if not args:
        _err("ssh test <host>")
        return

    user, host, port, key, password, timeout, ignore_key = _parse_conn_args(args)
    _inf(f"Test: {host}:{port}…")
    t0 = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        banner = sock.recv(256).decode("utf-8", errors="replace").strip()
        sock.close()
        elapsed = (time.time() - t0) * 1000
        _ok(f"Port SSH {host}:{port} dostępny — {elapsed:.0f}ms")
        _inf(f"Banner: {banner}")
    except (socket.timeout, TimeoutError):
        _err(f"Timeout ({timeout}s) — {host}:{port} nie odpowiada.")
    except ConnectionRefusedError:
        _err(f"Połączenie odrzucone — port {port} zamknięty.")
    except socket.gaierror as e:
        _err(f"Nie można rozwiązać nazwy: {e}")
    except Exception as e:
        _err(f"Błąd: {e}")

def _ssh_keyscan(args: List[str]) -> None:
    """Pobierz fingerprint klucza hosta."""
    if not _require_paramiko():
        return
    if not args:
        _err("ssh keyscan <host> [port]")
        return

    host = args[0]
    port = int(args[1]) if len(args) > 1 else 22

    _inf(f"Skanowanie {host}:{port}…")
    try:
        transport = paramiko.Transport((host, port))
        transport.start_client(timeout=10)
        host_key = transport.get_remote_server_key()
        transport.close()

        raw = base64.b64decode(host_key.get_base64())
        sha256 = "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
        md5    = ":".join(f"{b:02x}" for b in hashlib.md5(raw).digest())

        _w(f"\n  {WHT}{host}:{port}{RST}\n")
        _w(f"  Typ:         {BCYN}{host_key.get_name()}{RST}\n")
        _w(f"  SHA256:      {GRN}{sha256}{RST}\n")
        _w(f"  MD5:         {DIM}{md5}{RST}\n")
        _w(f"\n  {DIM}Klucz publiczny:{RST}\n")
        _w(f"  {host} {host_key.get_name()} {host_key.get_base64()}\n\n")

    except Exception as e:
        _err(f"Keyscan: {e}")

def _ssh_known_hosts(args: List[str]) -> None:
    """Zarządzanie known_hosts."""
    if args and args[0] == "del":
        if len(args) < 2:
            _err("ssh known-hosts del <host>"); return
        target = args[1]
        if not _KNOWN_HOSTS.exists():
            _err("Brak pliku known_hosts."); return
        lines = _KNOWN_HOSTS.read_text(encoding="utf-8").splitlines()
        new_lines = [line for line in lines if not line.startswith(target)]
        removed = len(lines) - len(new_lines)
        content = "\n".join(new_lines)
        if content:
            content += "\n"
        _KNOWN_HOSTS.write_text(content, encoding="utf-8")
        if removed:
            _ok(f"Usunięto {removed} wpis(y) dla: {target}")
        else:
            _warn(f"Nie znaleziono wpisów dla: {target}")
        return

    # Wyświetl known_hosts
    if not _KNOWN_HOSTS.exists():
        _inf("Brak pliku ~/.ssh/known_hosts"); return

    lines = _KNOWN_HOSTS.read_text(encoding="utf-8").splitlines()
    _w(f"\n  {BOLD}known_hosts{RST}  {DIM}({len(lines)} wpisów){RST}\n\n")
    for i, line in enumerate(lines[:50], 1):
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        host = parts[0] if parts else "?"
        algo = parts[1] if len(parts) > 1 else "?"
        _w(f"  {DIM}{i:3}.{RST}  {BCYN}{host:<40}{RST}  {DIM}{algo}{RST}\n")
    if len(lines) > 50:
        _w(f"\n  {DIM}… i {len(lines) - 50} więcej wpisów{RST}\n")
    _w("\n")


def _on_unload() -> None:
    """Zatrzymuje wszystkie aktywne tunele SSH."""
    with _tunnel_lock:
        for t in list(_tunnels.values()):
            try: t["stop"].set()
            except Exception: pass
            try: t["client"].close()
            except Exception: pass
        _tunnels.clear()


# ─── Integracja z TerminalX EcoSystem ────────────────────────────────────────

def setup(terminal) -> None:
    """Rejestruje komendę 'ssh' w TerminalX."""
    _ensure_dirs()

    _t = terminal.t

    def _ssh_cmd(args):
        _cmd_ssh(args, terminal)

    terminal.register_command(
        "ssh",
        _ssh_cmd,
        description=_t("cmd_ssh") if "cmd_ssh" in getattr(terminal, "_t", {}) else
                    "SSH/SFTP — połączenia, tunele, klucze (paramiko)",
        category=_t("cat_net") if "cat_net" in getattr(terminal, "_t", {}) else "network",
    )


def teardown(terminal) -> None:
    """Zatrzymuje tunele i wyrejestrowuje komendę."""
    _on_unload()
    terminal.commands.pop("ssh", None)
