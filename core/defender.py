"""Defender module for TerminalX EcoSystem.

Ochrona systemu w czasie rzeczywistym - dziala jak antywirus:
  - Real-time watch: watek monitoruje CALY ekosystem co N sekund
    (core/ lang/ gui/ modules/ plugins/ scripts/ tools/ tests/ libs/ TerminalX.py)
  - Auto-kwarantanna: podejrzany plik automatycznie przenoszony bez pytania
  - Heurystyki v2: rozszerzone wzorce (obfuskacja, reverse shell, dropper)
  - Baseline integralnosci: alert gdy plik zmieni hash miedzy sesjami
  - Blokowanie niebezpiecznych komend (hooki na rm/cd/go)
  - Rejestr zdarzen z buforem (batch write, atomic save)
  - Rekurencyjny skan podkatalogow (os.walk)

polsoft.ITS(TM) Group  *  Sebastian Januchowski
Module: defender  v2.1.0
"""

import os
import re
import json
import time
import shutil
import threading

from ._shared import (
    ROOT_DIR, CACHE_DIR,
    RST, BOLD, DIM, YLW, ORG, RED, GRN, CYN, BCYN, MGT,
    _w, _pad, _strip, _atomic_write,
)
from . import _integration

# ---------------------------------------------------------------------------
# Sciezki
# ---------------------------------------------------------------------------

QUARANTINE_DIR  = os.path.join(ROOT_DIR, ".quarantine")
_DEFENDER_CACHE = os.path.join(CACHE_DIR, "defender")
EVENTS_FILE     = os.path.join(_DEFENDER_CACHE, "events.json")
BASELINE_FILE   = os.path.join(_DEFENDER_CACHE, "baseline.json")

# Sciezki zachowane dla kompatybilnosci wstecznej (uzywane tez przez _integration)
SCRIPTS_DIR     = os.path.join(ROOT_DIR, "scripts")
TOOLS_DIR       = os.path.join(ROOT_DIR, "tools")

# Pelne pokrycie ekosystemu - katalogi skanowane rekurencyjnie
_ECOSYSTEM_DIRS: list[str] = [
    os.path.join(ROOT_DIR, "core"),
    os.path.join(ROOT_DIR, "lang"),
    os.path.join(ROOT_DIR, "gui"),
    os.path.join(ROOT_DIR, "modules"),
    os.path.join(ROOT_DIR, "plugins"),
    os.path.join(ROOT_DIR, "scripts"),
    os.path.join(ROOT_DIR, "tools"),
    os.path.join(ROOT_DIR, "tests"),
    os.path.join(ROOT_DIR, "libs"),
]

# Pojedyncze pliki w ROOT_DIR objete ochrona
_ECOSYSTEM_FILES: list[str] = [
    os.path.join(ROOT_DIR, "TerminalX.py"),
]

# Podkatalogi wykluczone ze skanowania (cache, bytecode, kwarantanna)
_SKIP_DIRS: set[str] = {
    "__pycache__", ".cache", ".quarantine", ".trash", ".git",
}

_HASH_EXT       = ".sha256"
_MAX_EVENTS     = 500
_WATCH_INTERVAL = 5          # sekund miedzy cyklami watch
_SCAN_EXTS      = {          # rozszerzenia skanowane przez heurystyke (kod)
    ".py", ".ps1", ".bat", ".cmd", ".sh", ".js", ".vbs",
    ".wsf", ".hta", ".lnk", ".inf", ".reg",
}

# Rozszerzenia obrazow – sprawdzane osobno przez _scan_image_exif()
_IMG_EXTS_DEFENDER = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif",
    ".tiff", ".tif", ".ico", ".ppm", ".pgm", ".pbm",
}

# ---------------------------------------------------------------------------
# Stan modulu
# ---------------------------------------------------------------------------

_state = {
    "protection": True,
    "watch":      False,     # czy watek watch aktywny
    "auto_quarantine": True, # auto-kwarantanna przy wykryciu block
}

_dirs_ready   = False
_watch_thread: threading.Thread | None = None
_watch_stop   = threading.Event()
_original_run: dict = {}
_event_buffer: list = []
_event_lock   = threading.Lock()

# ---------------------------------------------------------------------------
# SHA-256 helpers (delegowane do sha256.py)
# ---------------------------------------------------------------------------

def _sha256_file(path: str) -> str:
    """Oblicz SHA-256 pliku delegujac do sha256.py (lub fallback wbudowany)."""
    result = _integration.call("sha256", "compute", path)
    if result is not None:
        digest, _ = result
        return digest
    # Fallback wbudowany (sha256.py niezaladowany)
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _sha256_compare(a: str, b: str) -> bool:
    result = _integration.call("sha256", "compare", a, b)
    return result if result is not None else a.lower() == b.lower()

def _sha256_load_hashfile(path: str) -> str | None:
    result = _integration.call("sha256", "load", path)
    if result is not None:
        return result
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.readline().split()[0] or None
    except OSError:
        return None

def _sha256_save_hashfile(target_path: str, digest: str) -> str:
    hashfile = target_path + _HASH_EXT
    saved = _integration.call("sha256", "save", hashfile, digest, os.path.basename(target_path))
    if saved is None:
        with open(hashfile, "w", encoding="utf-8") as f:
            f.write(f"{digest}  {os.path.basename(target_path)}\n")
    return hashfile

def _sha256_check_integrity(filepath: str) -> tuple[bool | None, str, str | None]:
    hashfile = filepath + _HASH_EXT
    if not os.path.isfile(hashfile):
        alt = os.path.join(os.path.dirname(filepath),
                           os.path.basename(filepath) + _HASH_EXT)
        if not os.path.isfile(alt):
            return None, "", None
        hashfile = alt
    expected = _sha256_load_hashfile(hashfile)
    if not expected:
        return None, "", None
    try:
        current = _sha256_file(filepath)
    except OSError:
        return None, "", expected
    ok = _sha256_compare(current, expected)
    return ok, current, expected

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_age(ts: float) -> str:
    age = time.time() - ts
    if age < 60:   return f"{int(age)}s"
    if age < 3600: return f"{int(age // 60)}m"
    return f"{int(age // 3600)}h"

def _ensure_dirs() -> None:
    global _dirs_ready
    if _dirs_ready:
        return
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    os.makedirs(_DEFENDER_CACHE, exist_ok=True)
    if not os.path.exists(EVENTS_FILE):
        _write_events([])
    _dirs_ready = True

def _is_scannable(path: str) -> bool:
    """Czy plik powinien byc skanowany heurystycznie."""
    ext = os.path.splitext(path)[1].lower()
    return ext in _SCAN_EXTS

def _collect_files(dirs: list[str],
                   extra_files: list[str] | None = None) -> list[str]:
    """Zbierz pliki rekurencyjnie z listy katalogow + opcjonalnych plikow root.

    Pomija podkatalogi z _SKIP_DIRS oraz pliki pomocnicze (.gitkeep, .meta.json).
    """
    result: list[str] = []
    for fp in (extra_files or []):
        if os.path.isfile(fp):
            result.append(fp)
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, subdirs, files in os.walk(d, topdown=True):
            subdirs[:] = sorted(s for s in subdirs if s not in _SKIP_DIRS)
            for fname in sorted(files):
                if fname.endswith(".meta.json") or fname == ".gitkeep":
                    continue
                result.append(os.path.join(root, fname))
    return result


def _ecosystem_dirs() -> list[str]:
    """Istniejace katalogi ekosystemu."""
    return [d for d in _ECOSYSTEM_DIRS if os.path.isdir(d)]


def _ecosystem_files() -> list[str]:
    """Istniejace pliki root ekosystemu (np. TerminalX.py)."""
    return [f for f in _ECOSYSTEM_FILES if os.path.isfile(f)]


def _all_ecosystem_files() -> list[str]:
    """Wszystkie pliki ekosystemu: katalogi + root-files."""
    return _collect_files(_ecosystem_dirs(), _ecosystem_files())

# ---------------------------------------------------------------------------
# Rejestr zdarzen (bufor + atomic write)
# ---------------------------------------------------------------------------

def _read_events() -> list:
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _write_events(data: list) -> None:
    _atomic_write(EVENTS_FILE, data, makedirs=True)

def _flush_events() -> None:
    global _event_buffer
    with _event_lock:
        if not _event_buffer:
            return
        pending = _event_buffer
        _event_buffer = []
    existing = _read_events()
    merged   = existing + pending
    if len(merged) > _MAX_EVENTS:
        merged = merged[-_MAX_EVENTS:]
    _write_events(merged)

def _log_event(severity: str, source: str, detail: str) -> None:
    with _event_lock:
        _event_buffer.append({
            "ts":       time.time(),
            "severity": severity,
            "source":   source,
            "detail":   detail,
        })
        buf_len = len(_event_buffer)
    if severity in ("BLOCK", "QUARANTINE") or buf_len >= 5:
        _flush_events()

# ---------------------------------------------------------------------------
# Baseline integralnosci (caly ekosystem)
# ---------------------------------------------------------------------------

def _load_baseline() -> dict:
    """Wczytaj baseline hashow: {sciezka: hash}."""
    try:
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_baseline(data: dict) -> None:
    _atomic_write(BASELINE_FILE, data, makedirs=True)

def _build_baseline(dirs: list[str] | None = None) -> dict:
    """Zbuduj slownik {sciezka: sha256} dla calego ekosystemu.

    Parametr dirs ignorowany - zachowany dla kompatybilnosci.
    """
    baseline = {}
    for fpath in _all_ecosystem_files():
        if fpath.endswith(_HASH_EXT):
            continue
        try:
            baseline[fpath] = _sha256_file(fpath)
        except OSError:
            pass
    return baseline


def _check_baseline_integrity(dirs: list[str] | None = None) -> list[tuple[str, str]]:
    """Porownaj aktualny stan calego ekosystemu z zapisanym baseline.

    Parametr dirs ignorowany - zachowany dla kompatybilnosci.
    Zwraca liste (sciezka, powod) dla plikow ktore sie zmienily lub pojawiły nowe.
    """
    baseline = _load_baseline()
    if not baseline:
        return []
    violations = []
    for fpath in _all_ecosystem_files():
        if fpath.endswith(_HASH_EXT):
            continue
        if fpath not in baseline:
            violations.append((fpath, "nowy plik (nie ma w baseline)"))
            continue
        try:
            current = _sha256_file(fpath)
            if current != baseline[fpath]:
                violations.append((fpath, f"hash zmieniony: {current[:12]}... != {baseline[fpath][:12]}..."))
        except OSError:
            pass
    return violations

# ---------------------------------------------------------------------------
# Heurystyki v2 - wzorce skanera
# ---------------------------------------------------------------------------

# (opis, regex, poziom: "warn" | "block")
_SCRIPT_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # --- destrukcja ---
    ("Usuwanie rekurencyjne (rm -rf)",
        re.compile(r'rm\s+-[^\s]*r[^\s]*f|rm\s+-[^\s]*f[^\s]*r', re.I), "block"),
    ("Format dysku",
        re.compile(r'\bformat\b.*?(/[quy]\b|\b[A-Za-z]\b:(?:[\\/]|\s|$))', re.I), "block"),
    ("Usuwanie systemowe (del /f /s)",
        re.compile(r'\bdel\b.*/[fFsS]', re.I), "block"),
    ("Nadpisanie urzadzenia blokowego (> /dev/sd*)",
        re.compile(r'>\s*/dev/sd[a-z]', re.I), "block"),
    ("Usuwanie logow Windows (wevtutil/Clear-EventLog)",
        re.compile(r'wevtutil\s+cl|Clear-EventLog', re.I), "block"),

    # --- wylaczanie ochrony ---
    ("Wylaczenie Windows Defendera",
        re.compile(r'Set-MpPreference.*Disable|DisableRealtimeMonitoring', re.I), "block"),
    ("Wylaczenie UAC / firewalla",
        re.compile(r'netsh.*firewall.*set.*disable|ConvertTo-SecureString.*\|.*Bypass', re.I), "block"),
    ("Zmiana polityki wykonywania PS (Bypass/Unrestricted)",
        re.compile(r'Set-ExecutionPolicy\s+(Bypass|Unrestricted|RemoteSigned)', re.I), "block"),

    # --- download + exec (dropper) ---
    ("Dropper: Invoke-Expression / IEX",
        re.compile(r'Invoke-Expression|iex\s*\(', re.I), "block"),
    ("Dropper: IWR/wget/curl + exec",
        re.compile(r'(Invoke-WebRequest|wget|curl).*\|\s*(iex|bash|sh|python|cmd)', re.I), "block"),
    ("Dropper: DownloadFile + exec",
        re.compile(r'DownloadFile|DownloadString|WebClient', re.I), "warn"),
    ("Dropper: bitsadmin transfer",
        re.compile(r'bitsadmin\s+/transfer', re.I), "warn"),
    ("Dropper: certutil -decode/-urlcache",
        re.compile(r'certutil\s+.*(-decode|-urlcache)', re.I), "block"),
    ("Dropper: mshta http",
        re.compile(r'mshta\s+https?://', re.I), "block"),
    ("Dropper: regsvr32 /s /u /i:http",
        re.compile(r'regsvr32\s+.*/i:https?://', re.I), "block"),
    ("Dropper: rundll32 javascript",
        re.compile(r'rundll32\s+.*javascript:', re.I), "block"),

    # --- reverse shell ---
    ("Reverse shell: nc/ncat -e",
        re.compile(r'\bnc(at)?\b.*-e\s+/(bin/sh|bin/bash|cmd)', re.I), "block"),
    ("Reverse shell: bash -i >& /dev/tcp",
        re.compile(r'bash\s+-i\s+>&\s*/dev/tcp/', re.I), "block"),
    ("Reverse shell: Python socket exec",
        re.compile(r'import\s+socket.*exec\s*\(|socket\.connect.*exec', re.I), "block"),
    ("Reverse shell: PowerShell TCPClient",
        re.compile(r'Net\.Sockets\.TCPClient|System\.Net\.Sockets', re.I), "warn"),

    # --- obfuskacja ---
    ("Obfuskacja: -EncodedCommand / -enc base64",
        re.compile(r'-EncodedCommand|-enc\s+[A-Za-z0-9+/]{20,}', re.I), "block"),
    ("Obfuskacja: eval(base64_decode)",
        re.compile(r'eval\s*\(\s*base64_decode|eval\s*\(\s*gzinflate', re.I), "block"),
    ("Obfuskacja: char concat (chr/[char])",
        re.compile(r'(\[char\]\d+\s*\+\s*){3,}|(\(chr\(\d+\)\s*\+\s*){3,}', re.I), "warn"),
    ("Obfuskacja: VBScript Execute",
        re.compile(r'\bExecute\s*\(|ExecuteGlobal\s*\(', re.I), "warn"),
    ("Obfuskacja: Python exec + compile",
        re.compile(r'\bexec\s*\(\s*compile\s*\(|exec\s*\(\s*__import__', re.I), "block"),

    # --- persistence ---
    ("Persistence: zadanie systemowe (schtasks/Register-ScheduledTask)",
        re.compile(r'schtasks\s+/create|Register-ScheduledTask', re.I), "warn"),
    ("Persistence: klucz Run w rejestrze",
        re.compile(r'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run|'
                   r'HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run', re.I), "block"),
    ("Persistence: modyfikacja rejestru HKLM",
        re.compile(r'reg\s+(add|delete|import)\s+HKLM', re.I), "warn"),
    ("Persistence: .bashrc/.profile modyfikacja",
        re.compile(r'echo\s+.*>>\s*~?/?(\.bashrc|\.profile|\.bash_profile)', re.I), "warn"),

    # --- eskalacja uprawnien ---
    ("Eskalacja: runas /user",
        re.compile(r'\brunas\b.*/user', re.I), "warn"),
    ("Eskalacja: sudo chmod 777",
        re.compile(r'sudo\s+chmod\s+777', re.I), "warn"),
    ("Eskalacja: setuid/setgid bit",
        re.compile(r'chmod\s+[ug]\+s|chmod\s+[0-9]*[2-3][0-9]{3}', re.I), "warn"),

    # --- system ---
    ("System: shutdown/restart",
        re.compile(r'\bshutdown\b|\brestart-computer\b', re.I), "warn"),
    ("System: kill -9 1 (zabicie init)",
        re.compile(r'kill\s+-9\s+1\b', re.I), "block"),
]

_BLOCKED_COMMANDS: list[tuple[str, re.Pattern]] = [
    ("rm -rf /",     re.compile(r'^rm\s+.*-[^\s]*r[^\s]*f\s+/', re.I)),
    ("del /f /s",    re.compile(r'^del\s+.*/[fF].*(/[sS]|/[qQ])', re.I)),
    ("format C:",    re.compile(r'^format\s+[A-Z]:', re.I)),
    ("shutdown /s",  re.compile(r'^shutdown\s+(/s|/r|/h)', re.I)),
    ("> /dev/sda",   re.compile(r'>\s*/dev/sd[a-z]', re.I)),
    ("kill -9 1",    re.compile(r'^kill\s+-9\s+1\b', re.I)),
]

# ---------------------------------------------------------------------------
# Skaner
# ---------------------------------------------------------------------------

def _scan_file(filepath: str) -> list[tuple[str, str]]:
    """Skanuj plik. Zwraca liste (opis, poziom) trafien."""
    if not _is_scannable(filepath):
        return []
    hits: list[tuple[str, str]] = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return hits
    for desc, pattern, level in _SCRIPT_PATTERNS:
        if pattern.search(content):
            hits.append((desc, level))
    return hits

def _scan_file_safe(path: str) -> bool:
    """Public API dla _integration: True = brak zagrozenia block-level.

    Dla plikow graficznych deleguje rowniez do _scan_image_exif() przez imgtools.
    """
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in _IMG_EXTS_DEFENDER:
            # Pliki graficzne: sprawdz EXIF anomalie przez imgtools
            hits = _scan_image_exif(path)
            for desc, level in hits:
                _log_event("WARN" if level in ("warn", "block") else "INFO",
                           path, f"[img_exif] {desc}")
                if level == "block":
                    return False
            return True
        hits = _scan_file(path)
        for desc, level in hits:
            if level == "block":
                _log_event("WARN", path, f"[scan_safe] wykryto: {desc}")
                return False
        return True
    except Exception:
        return True

def _scan_image_exif(filepath: str) -> list[tuple[str, str]]:
    """Sprawdza plik graficzny pod katem anomalii w metadanych EXIF.

    Deleguje do imgtools przez _integration – jesli modul nie jest zaladowany,
    zwraca pusta liste (fail-safe, nie blokuje).
    Wykrywa: ukryty kod w UserComment, GPS w plikach biurowych, anomalie rozmiaru.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in _IMG_EXTS_DEFENDER:
        return []
    try:
        from . import _integration as _intg
        img_svc = _intg.get("imgtools")
        if not img_svc:
            return []
        analyse = img_svc.get("analyse_image")
        if not callable(analyse):
            return []
        data = analyse(filepath)
        if not data:
            return []

        hits: list[tuple[str, str]] = []
        exif = data.get("exif", {})

        # UserComment z kodem/skryptem
        uc = exif.get("UserComment", "")
        if uc and any(kw in uc.lower() for kw in
                      ("exec", "eval", "import", "script", "<?php", "<script",
                       "powershell", "cmd.exe", "base64")):
            hits.append((f"EXIF UserComment zawiera potencjalny kod: {uc[:60]}", "warn"))

        # GPS w pliku z podejrzanym rozmiarem (np. < 500B = pusty kontent + exif)
        if "GPSInfo" in exif and data.get("size_bytes", 999999) < 2048:
            hits.append(("Maly plik graficzny z danymi GPS – mozliwa steganografia", "warn"))

        # Wymiary obrazu 0x0 lub ekstremalnie duze przy malym rozmiarze pliku
        w, h = data.get("width", 0), data.get("height", 0)
        fsize = data.get("size_bytes", 0)
        if w > 0 and h > 0 and fsize > 0:
            theoretical_min = w * h // 100  # bardzo heurystyczne
            if theoretical_min > fsize * 10:
                hits.append((f"Anomalia wymiarow/rozmiaru: {w}x{h} px ale {fsize} B", "info"))

        return hits
    except Exception:
        return []


def _scan_dir(directory: str) -> list[tuple[str, str, list]]:
    """Skanuj katalog rekurencyjnie. Zwraca [(fname, fpath, hits)]."""
    results = []
    for fpath in _collect_files([directory]):
        hits = _scan_file(fpath)
        if hits:
            fname = os.path.relpath(fpath, directory)
            results.append((fname, fpath, hits))
    return results


def _scan_ecosystem() -> list[tuple[str, str, list]]:
    """Skanuj caly ekosystem. Zwraca [(relpath, fpath, hits)]."""
    results = []
    for fpath in _all_ecosystem_files():
        hits = _scan_file(fpath)
        if hits:
            relpath = os.path.relpath(fpath, ROOT_DIR)
            results.append((relpath, fpath, hits))
    return results

# ---------------------------------------------------------------------------
# Kwarantanna
# ---------------------------------------------------------------------------

def _quarantine_file(filepath: str, reason: str) -> str | None:
    """Przenies plik do kwarantanny. Zapisuje hash SHA-256 jako dowod."""
    _ensure_dirs()
    basename = os.path.basename(filepath)
    dst = os.path.join(QUARANTINE_DIR, basename)
    base, ext = os.path.splitext(basename)
    counter = 1
    while os.path.exists(dst):
        dst = os.path.join(QUARANTINE_DIR, f"{base}~{counter}{ext}")
        counter += 1
    try:
        try:
            digest = _sha256_file(filepath)
            _sha256_save_hashfile(dst, digest)
            _log_event("INFO", filepath, f"SHA-256 przed kwarantanna: {digest[:16]}...")
        except Exception:
            pass
        shutil.move(filepath, dst)
        _log_event("QUARANTINE", filepath, f"Auto-kwarantanna: {reason}")
        return dst
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Real-time watch (watek tla)
# ---------------------------------------------------------------------------

_watch_state: dict = {
    "snapshots":  {},   # {fpath: (mtime, size)} - snapshot systemu plikow
    "hashes":     {},   # {fpath: sha256}         - cache haszy
    "last_cycle": 0.0,
}


def _watch_snapshot() -> dict:
    """Zrob snapshot {fpath: (mtime, size)} dla calego ekosystemu."""
    snap = {}
    for fpath in _all_ecosystem_files():
        try:
            st = os.stat(fpath)
            snap[fpath] = (st.st_mtime, st.st_size)
        except OSError:
            pass
    return snap


def _watch_cycle(terminal) -> None:
    """Jeden cykl watch: sprawdz zmiany, nowe pliki, integralnosc baseline."""
    current_snap = _watch_snapshot()
    prev_snap    = _watch_state["snapshots"]
    hashes       = _watch_state["hashes"]
    baseline     = _load_baseline()
    alerts: list[str] = []

    for fpath, (mtime, size) in current_snap.items():
        fname = os.path.basename(fpath)

        # --- nowy plik ---
        if fpath not in prev_snap:
            hits = _scan_file(fpath)
            if hits:
                levels = {lv for _, lv in hits}
                severity = "BLOCK" if "block" in levels else "WARN"
                detail = f"{fname}: {', '.join(d for d, _ in hits[:2])}"
                _log_event(severity, fpath, detail)
                if severity == "BLOCK" and _state["auto_quarantine"]:
                    dst = _quarantine_file(fpath, f"watch: {hits[0][0]}")
                    if dst:
                        alerts.append(
                            f"{RED}{BOLD}[QUARANTINE]{RST} {fname} "
                            f"{DIM}-> {os.path.basename(dst)}{RST}"
                        )
                    continue
                else:
                    alerts.append(
                        f"{ORG}[WATCH-WARN]{RST} {fname}: "
                        f"{DIM}{hits[0][0]}{RST}"
                    )
            else:
                _log_event("INFO", fpath, f"Nowy plik w EcoSystem: {fname}")
            # Dodaj do baseline jesli istnieje
            if baseline:
                try:
                    baseline[fpath] = _sha256_file(fpath)
                    _save_baseline(baseline)
                except OSError:
                    pass
            continue

        # --- plik zmieniony (mtime lub size) ---
        if (mtime, size) != prev_snap.get(fpath, (0, 0)):
            hits = _scan_file(fpath)
            # sprawdz hash zeby potwierdzic realną zmiane treści
            try:
                new_hash = _sha256_file(fpath)
            except OSError:
                continue
            old_hash = hashes.get(fpath)
            if old_hash and new_hash == old_hash:
                # mtime/size zmienione ale tresc ta sama - pomijamy
                hashes[fpath] = new_hash
                continue
            hashes[fpath] = new_hash

            # sprawdz baseline
            if fpath in baseline and baseline[fpath] != new_hash:
                _log_event("BLOCK", fpath,
                           f"[watch] hash zmieniony: {new_hash[:12]}...")
                if hits:
                    levels = {lv for _, lv in hits}
                    if "block" in levels and _state["auto_quarantine"]:
                        dst = _quarantine_file(fpath, f"watch: zmieniony + zagrożenie: {hits[0][0]}")
                        if dst:
                            alerts.append(
                                f"{RED}{BOLD}[QUARANTINE]{RST} {fname} "
                                f"(zmieniony + zagrożenie) {DIM}-> {os.path.basename(dst)}{RST}"
                            )
                        continue
                alerts.append(
                    f"{ORG}[WATCH-MOD]{RST} {fname}: "
                    f"{DIM}hash zmieniony{RST}"
                    + (f" + wzorzec: {hits[0][0]}" if hits else "")
                )
            elif hits:
                levels = {lv for _, lv in hits}
                severity = "BLOCK" if "block" in levels else "WARN"
                _log_event(severity, fpath, f"[watch] wzorzec: {hits[0][0]}")
                if severity == "BLOCK" and _state["auto_quarantine"]:
                    dst = _quarantine_file(fpath, f"watch: {hits[0][0]}")
                    if dst:
                        alerts.append(
                            f"{RED}{BOLD}[QUARANTINE]{RST} {fname} "
                            f"{DIM}-> {os.path.basename(dst)}{RST}"
                        )
                    continue
                alerts.append(
                    f"{ORG}[WATCH-WARN]{RST} {fname}: "
                    f"{DIM}{hits[0][0]}{RST}"
                )

    # --- usuniete pliki ---
    for fpath in prev_snap:
        if fpath not in current_snap:
            fname = os.path.basename(fpath)
            _log_event("WARN", fpath, f"[watch] plik usunięty: {fname}")

    _watch_state["snapshots"] = current_snap
    _watch_state["last_cycle"] = time.time()

    # Wyswietl alerty w terminalu (watek tla -> bezpieczny print)
    if alerts:
        _w(f"\n  {BOLD}{BCYN}[DEFENDER WATCH]{RST}\n")
        for a in alerts:
            _w(f"  {a}\n")
        _w("\n")

        # Przekaz alert do modulu notify, aby byl widoczny nawet jesli
        # uzytkownik nie sledzi na biezaco wyjscia watku watch (chmurka +
        # zapis do historii powiadomien). Podsumowanie budowane jest z
        # samych liczb/etykiet (bez ANSI i bez wklejania pelnego tekstu
        # alertu), zeby nie ucinac sie brzydko w jednolinijkowej chmurce.
        quarantined = sum(1 for a in alerts if "QUARANTINE" in a)
        warned      = len(alerts) - quarantined
        kind = "err" if quarantined else "warn"
        if len(alerts) == 1:
            first_clean = _strip(alerts[0])
            summary = first_clean if len(first_clean) <= 60 else first_clean[:57] + "..."
        else:
            parts = []
            if quarantined: parts.append(f"{quarantined}x KWAR")
            if warned:       parts.append(f"{warned}x WARN")
            summary = f"Defender watch: {', '.join(parts)}."
        _integration.notify_event(
            terminal, summary, kind=kind, title="DEFENDER WATCH"
        )


def _watch_loop(terminal) -> None:
    """Petla watku watch."""
    # Inicjalizacja snapshot przy starcie
    _watch_state["snapshots"] = _watch_snapshot()
    # Wypelnij cache haszy
    for fpath in _watch_state["snapshots"]:
        try:
            _watch_state["hashes"][fpath] = _sha256_file(fpath)
        except OSError:
            pass

    while not _watch_stop.is_set():
        _watch_stop.wait(timeout=_WATCH_INTERVAL)
        if _watch_stop.is_set():
            break
        if _state["protection"]:
            try:
                _watch_cycle(terminal)
            except Exception:
                pass
    _flush_events()


def _start_watch(terminal) -> None:
    global _watch_thread
    if _state["watch"]:
        return
    _watch_stop.clear()
    _watch_thread = threading.Thread(
        target=_watch_loop, args=(terminal,),
        name="defender-watch", daemon=True,
    )
    _watch_thread.start()
    _state["watch"] = True


def _stop_watch() -> None:
    global _watch_thread
    if not _state["watch"]:
        return
    _watch_stop.set()
    if _watch_thread and _watch_thread.is_alive():
        _watch_thread.join(timeout=_WATCH_INTERVAL + 1)
    _watch_thread = None
    _state["watch"] = False

# ---------------------------------------------------------------------------
# Hooki komend
# ---------------------------------------------------------------------------

def _make_guarded(terminal, cmd_name: str, original_func):
    def guarded(args):
        if _state["protection"]:
            full_cmd = " ".join([cmd_name] + args)
            for desc, pattern in _BLOCKED_COMMANDS:
                if pattern.search(full_cmd):
                    _log_event("BLOCK", cmd_name, f"Zablokowano: {desc} -> {full_cmd}")
                    try:
                        from . import _integration
                        _integration.log_debug_event(
                            terminal, "WARN",
                            f"DEFENDER BLOCK: {cmd_name} -> {desc}",
                        )
                    except Exception:
                        pass
                    _w(f"\n  {RED}{BOLD}!!  DEFENDER: Zablokowano niebezpieczne polecenie{RST}\n")
                    _w(f"  {YLW}Wykryto:{RST} {desc}\n")
                    _w(f"  {DIM}Polecenie: {full_cmd}{RST}\n\n")
                    return
        original_func(args)
    return guarded

def _install_hooks(terminal) -> None:
    for cmd_name in ("rm", "cd", "go"):
        if cmd_name in terminal.commands and cmd_name not in _original_run:
            orig = terminal.commands[cmd_name]["func"]
            _original_run[cmd_name] = orig
            terminal.commands[cmd_name]["func"] = _make_guarded(terminal, cmd_name, orig)

def _remove_hooks(terminal) -> None:
    for cmd_name, orig in _original_run.items():
        if cmd_name in terminal.commands:
            terminal.commands[cmd_name]["func"] = orig
    _original_run.clear()

# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def _menu() -> None:
    watch_status = f"{GRN}ON{RST}" if _state["watch"] else f"{DIM}OFF{RST}"
    prot_status  = f"{GRN}AKTYWNA{RST}" if _state["protection"] else f"{RED}WYLACZONA{RST}"
    aq_status    = f"{GRN}ON{RST}" if _state["auto_quarantine"] else f"{DIM}OFF{RST}"
    _w(f"\n{BOLD}{BCYN}  +==========================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |   >>  Modul: Defender  v2.1.0           |{RST}\n")
    _w(f"{BOLD}{BCYN}  +==========================================+{RST}\n\n")
    _w(f"  Ochrona: {prot_status}   Watch: {watch_status}   Auto-kwarantanna: {aq_status}\n\n")
    cmds = [
        ("defender scan",               "Skanuj scripts/ i tools/"),
        ("defender scan <sciezka>",     "Skanuj wskazany plik lub katalog"),
        ("defender integrity",          "Weryfikacja SHA-256 (caly ekosystem)"),
        ("defender integrity --save",   "Zapisz/odswiez baseline SHA-256"),
        ("defender baseline",           "Pokaz status baseline"),
        ("defender watch on",           "Uruchom real-time monitor"),
        ("defender watch off",          "Zatrzymaj real-time monitor"),
        ("defender quarantine",         "Lista plikow w kwarantannie"),
        ("defender restore <nazwa>",    "Przywroc plik z kwarantanny"),
        ("defender events",             "Rejestr zdarzen bezpieczenstwa"),
        ("defender events clear",       "Wyczysc rejestr zdarzen"),
        ("defender auto on|off",        "Wlacz/wylacz auto-kwarantanne"),
        ("defender on",                 "Wlacz ochrone"),
        ("defender off",                "Wylacz ochrone (niezalecane)"),
        ("defender status",             "Pokaz pelny status modulu"),
    ]
    for c, d in cmds:
        _w(f"  {YLW}{_pad(c, 36)}{RST} {DIM}{d}{RST}\n")
    _w("\n")


def _cmd_scan(args: list) -> None:
    _ensure_dirs()
    if args:
        path = " ".join(args)
        if os.path.isfile(path):
            hits = _scan_file(path)
            targets = [(os.path.basename(path), path, hits)] if hits else []
            _do_report(targets, path)
        elif os.path.isdir(path):
            _do_report(_scan_dir(path), path)
        else:
            _w(f"  {RED}Nie znaleziono: {path}{RST}\n")
        return
    results = _scan_ecosystem()
    _do_report(results, "EcoSystem (pelny skan)")


def _do_report(results: list, label: str) -> None:
    _w(f"\n{BOLD}  Skan: {DIM}{label}{RST}\n")
    _w(f"  {'-'*60}\n")
    if not results:
        _w(f"  {GRN}[V]  Brak zagrozen.{RST}\n\n")
        return
    for fname, fpath, hits in results:
        blocks = [h for h in hits if h[1] == "block"]
        icon   = f"{RED}[X]{RST}" if blocks else f"{ORG}[!]{RST}"
        _w(f"\n  {icon} {BOLD}{fname}{RST}\n")
        for desc, level in hits:
            col = RED if level == "block" else ORG
            tag = "BLOCK" if level == "block" else "WARN "
            _w(f"      {col}[{tag}]{RST} {desc}\n")
        # integralnosc SHA-256
        ok, current, expected = _sha256_check_integrity(fpath)
        if ok is True:
            _w(f"      {GRN}[SHA] OK{RST}  {DIM}{current[:12]}...{RST}\n")
        elif ok is False:
            _w(f"      {RED}[SHA] HASH NIEZGODNY - plik zmodyfikowany!{RST}\n")
            _w(f"             {DIM}oczekiwany: {expected[:16]}...{RST}\n")
            _w(f"             {RED}aktualny:   {current[:16]}...{RST}\n")
            _log_event("BLOCK", fpath, f"SHA-256 naruszona: {current[:16]}...")
        else:
            _w(f"      {DIM}[SHA] Brak baseline (uzyj: defender integrity --save){RST}\n")
        # auto-kwarantanna przy block
        if blocks and _state["auto_quarantine"]:
            dst = _quarantine_file(fpath, f"scan: {blocks[0][0]}")
            if dst:
                _w(f"      {MGT}[QUARANTINE]{RST} Przeniesiono -> {os.path.basename(dst)}\n")
        _log_event(
            "BLOCK" if blocks else "WARN",
            fpath,
            f"Skan: {', '.join(d for d, _ in hits[:3])}",
        )
    _w(f"\n  {BOLD}Zagrozen: {RED}{len(results)}{RST}\n\n")
    if results:
        _integration.notify_event(
            None,
            f"Skan '{label}': wykryto {len(results)} zagrozenie(n).",
            kind="err", title="DEFENDER SCAN",
        )


def _cmd_integrity(args: list) -> None:
    _ensure_dirs()
    save_mode = "--save" in args
    remaining = [a for a in args if a != "--save"]
    if remaining:
        dirs = [os.path.abspath(remaining[0])]
    else:
        dirs = _ecosystem_dirs()

    if remaining:
        all_files = [
            f for f in _collect_files(dirs)
            if not f.endswith(_HASH_EXT) and not f.endswith(".meta.json")
        ]
        label = os.path.basename(dirs[0])
    else:
        all_files = [
            f for f in _all_ecosystem_files()
            if not f.endswith(_HASH_EXT) and not f.endswith(".meta.json")
        ]
        label = "EcoSystem (pelny)"
    if not all_files:
        _w(f"\n  {DIM}Brak plikow do sprawdzenia.{RST}\n\n")
        return

    mode_tag = f"  {ORG}[TRYB: ZAPIS BASELINE]{RST}" if save_mode else ""
    _w(f"\n{BOLD}{BCYN}  +============================================+{RST}\n")
    _w(f"{BOLD}{BCYN}  |   >>  Defender Integrity Check            |{RST}\n")
    _w(f"{BOLD}{BCYN}  +============================================+{RST}\n")
    _w(f"  {DIM}Zakres: {label}{RST}{mode_tag}\n\n")

    ok_cnt = fail_cnt = new_cnt = err_cnt = 0
    if save_mode:
        baseline = {}

    for fpath in all_files:
        fname = os.path.relpath(fpath, ROOT_DIR)
        try:
            if save_mode:
                digest = _sha256_file(fpath)
                _sha256_save_hashfile(fpath, digest)
                baseline[fpath] = digest
                _w(f"  {GRN}[SAVE]{RST} {YLW}{_pad(fname, 32)}{RST}  {DIM}{digest[:16]}...{RST}\n")
                new_cnt += 1
            else:
                ok, current, expected = _sha256_check_integrity(fpath)
                if ok is True:
                    _w(f"  {GRN}[ OK ]{RST} {YLW}{_pad(fname, 32)}{RST}  {DIM}{current[:16]}...{RST}\n")
                    ok_cnt += 1
                elif ok is False:
                    _w(f"  {RED}[FAIL]{RST} {BOLD}{_pad(fname, 32)}{RST}  {RED}NIEZGODNY!{RST}\n")
                    _w(f"         {DIM}oczekiwany: {expected[:32]}...{RST}\n")
                    _w(f"         {RED}aktualny:   {current[:32]}...{RST}\n")
                    _log_event("BLOCK", fpath, f"[integrity] SHA-256 niezgodny: {current[:16]}...")
                    fail_cnt += 1
                else:
                    _w(f"  {DIM}[ ?? ]{RST} {_pad(fname, 32)}  {DIM}brak .sha256{RST}\n")
                    new_cnt += 1
        except OSError as exc:
            _w(f"  {RED}[ ERR]{RST} {_pad(fname, 32)}  {RED}{exc}{RST}\n")
            err_cnt += 1

    _w(f"\n  {'-'*60}\n")
    if save_mode:
        _save_baseline(baseline)
        _w(f"  {GRN}Baseline zapisany: {new_cnt} plikow.{RST}\n")
        _log_event("INFO", label, f"Integrity baseline: {new_cnt} plikow")
    else:
        parts = []
        if ok_cnt:   parts.append(f"{GRN}{ok_cnt} OK{RST}")
        if fail_cnt: parts.append(f"{RED}{fail_cnt} NARUSZONE{RST}")
        if new_cnt:  parts.append(f"{DIM}{new_cnt} bez hasha{RST}")
        if err_cnt:  parts.append(f"{ORG}{err_cnt} bledy{RST}")
        _w(f"  {BOLD}Wynik:{RST}  {'  |  '.join(parts)}\n")
        if fail_cnt:
            _w(f"\n  {RED}{BOLD}!! Wykryto zmodyfikowane pliki.{RST}\n")
            _integration.notify_event(
                None,
                f"Integrity check ({label}): {fail_cnt} plik(ow) zmodyfikowanych!",
                kind="err", title="DEFENDER INTEGRITY",
            )
    _w("\n")


def _cmd_baseline(args: list) -> None:
    """Pokaz status baseline (ile plikow, kiedy zapisany)."""
    baseline = _load_baseline()
    if not baseline:
        _w(f"  {DIM}Brak baseline. Uzyj: defender integrity --save{RST}\n")
        return
    violations = _check_baseline_integrity()
    try:
        mtime = os.path.getmtime(BASELINE_FILE)
        age   = _human_age(mtime)
    except OSError:
        age = "?"
    _w(f"\n  {BOLD}Baseline integralnosci:{RST}\n")
    _w(f"  {CYN}{_pad('Plikow w baseline:', 24)}{RST}{YLW}{len(baseline)}{RST}\n")
    _w(f"  {CYN}{_pad('Ostatnia aktualizacja:', 24)}{RST}{DIM}{age} temu{RST}\n")
    if not violations:
        _w(f"  {CYN}{_pad('Status:', 24)}{RST}{GRN}OK - brak zmian{RST}\n")
    else:
        _w(f"  {CYN}{_pad('Status:', 24)}{RST}{RED}NARUSZONE: {len(violations)} plik(ow){RST}\n")
        for fpath, reason in violations[:10]:
            rp = os.path.relpath(fpath, ROOT_DIR)
            _w(f"    {RED}[!!]{RST} {rp}: {DIM}{reason}{RST}\n")
        if len(violations) > 10:
            _w(f"    {DIM}... i {len(violations) - 10} wiecej{RST}\n")
    _w("\n")


def _cmd_watch(args: list, terminal) -> None:
    if not args:
        status = f"{GRN}ON{RST}" if _state["watch"] else f"{DIM}OFF{RST}"
        _w(f"  Watch: {status}   (defender watch on|off)\n")
        return
    sub = args[0].lower()
    if sub == "on":
        if _state["watch"]:
            _w(f"  {DIM}Watch juz dziala.{RST}\n"); return
        _start_watch(terminal)
        _log_event("INFO", "defender", f"Watch uruchomiony (interval: {_WATCH_INTERVAL}s)")
        _w(f"  {GRN}[V]  Watch uruchomiony{RST}  {DIM}(co {_WATCH_INTERVAL}s: caly ekosystem){RST}\n")
    elif sub == "off":
        if not _state["watch"]:
            _w(f"  {DIM}Watch nie jest aktywny.{RST}\n"); return
        _stop_watch()
        _log_event("INFO", "defender", "Watch zatrzymany")
        _w(f"  {ORG}Watch zatrzymany.{RST}\n")
    else:
        _w(f"  {RED}Uzycie: defender watch on|off{RST}\n")


def _cmd_auto(args: list) -> None:
    if not args:
        status = f"{GRN}ON{RST}" if _state["auto_quarantine"] else f"{DIM}OFF{RST}"
        _w(f"  Auto-kwarantanna: {status}   (defender auto on|off)\n")
        return
    sub = args[0].lower()
    if sub == "on":
        _state["auto_quarantine"] = True
        _w(f"  {GRN}[V]  Auto-kwarantanna wlaczona.{RST}\n")
    elif sub == "off":
        _state["auto_quarantine"] = False
        _w(f"  {ORG}Auto-kwarantanna wylaczona.{RST}\n")
    else:
        _w(f"  {RED}Uzycie: defender auto on|off{RST}\n")


def _cmd_quarantine(args: list) -> None:
    _ensure_dirs()
    entries = [
        e for e in os.listdir(QUARANTINE_DIR)
        if os.path.isfile(os.path.join(QUARANTINE_DIR, e))
        and not e.endswith(_HASH_EXT)
    ]
    if not entries:
        _w(f"  {DIM}Kwarantanna jest pusta.{RST}\n"); return
    _w(f"\n{BOLD}  {'PLIK':<32}{'ROZMIAR':<14}{'SHA256 (dowod)'}{RST}\n")
    _w(f"  {'-'*70}\n")
    for e in sorted(entries):
        fpath = os.path.join(QUARANTINE_DIR, e)
        size  = os.path.getsize(fpath)
        # sprawdz czy jest dowod hash
        hf = fpath + _HASH_EXT
        proof = ""
        if os.path.isfile(hf):
            h = _sha256_load_hashfile(hf)
            proof = f"{DIM}{h[:16]}...{RST}" if h else ""
        _w(f"  {ORG}{_pad(e, 32)}{RST}{DIM}{size:,} B{RST:<14}  {proof}\n")
    _w("\n")


def _cmd_restore(args: list) -> None:
    if not args:
        _w(f"  {RED}Uzycie: defender restore <nazwa>{RST}\n"); return
    _ensure_dirs()
    name = args[0]
    src  = os.path.join(QUARANTINE_DIR, name)
    if not os.path.exists(src):
        _w(f"  {RED}Nie znaleziono w kwarantannie: {name}{RST}\n"); return
    dst = os.path.join(os.getcwd(), name)
    try:
        shutil.move(src, dst)
        _log_event("INFO", name, "Przywrocono z kwarantanny")
        _w(f"  {GRN}Przywrocono:{RST} {name} -> {dst}\n")
    except Exception as exc:
        _w(f"  {RED}Blad: {exc}{RST}\n")


def _cmd_events(args: list) -> None:
    _ensure_dirs()
    if args and args[0] == "clear":
        global _event_buffer
        with _event_lock:
            _event_buffer = []
        _write_events([])
        _w(f"  {GRN}Rejestr wyczyszczony.{RST}\n"); return
    _flush_events()
    events = _read_events()
    if not events:
        _w(f"  {DIM}Rejestr jest pusty.{RST}\n"); return
    _w(f"\n{BOLD}  {'CZAS':<8}{'POZIOM':<12}{'ZRODLO':<30}{'SZCZEGOLY'}{RST}\n")
    _w(f"  {'-'*82}\n")
    cols = {"INFO": DIM, "WARN": ORG, "BLOCK": RED, "QUARANTINE": MGT}
    for ev in reversed(events[-50:]):
        sev = ev.get("severity", "INFO")
        col = cols.get(sev, DIM)
        age = _human_age(ev.get("ts", time.time()))
        src = os.path.basename(ev.get("source", "?"))[:28]
        det = ev.get("detail", "")[:50]
        _w(f"  {DIM}{_pad(age + 'ago', 8)}{RST}"
           f"{col}{_pad(sev, 12)}{RST}"
           f"{_pad(src, 30)}{DIM}{det}{RST}\n")
    _w("\n")


def _cmd_on(args: list, terminal) -> None:
    if _state["protection"]:
        _w(f"  {DIM}Ochrona juz aktywna.{RST}\n"); return
    _state["protection"] = True
    _install_hooks(terminal)
    _log_event("INFO", "defender", "Ochrona wlaczona")
    _w(f"  {GRN}[V]  Ochrona wlaczona.{RST}\n")


def _cmd_off(args: list, terminal) -> None:
    if not _state["protection"]:
        _w(f"  {DIM}Ochrona juz wylaczona.{RST}\n"); return
    _w(f"  {ORG}[!]  Wylaczenie ochrony naraza system na ryzyko.{RST}\n")
    _w(f"  {DIM}Potwierdz: defender off --confirm{RST}\n")
    if "--confirm" not in args:
        return
    _state["protection"] = False
    _remove_hooks(terminal)
    _log_event("WARN", "defender", "Ochrona wylaczona przez uzytkownika")
    _w(f"  {RED}Ochrona wylaczona.{RST}\n")


def _cmd_status(args: list) -> None:
    _ensure_dirs()
    _flush_events()
    events = _read_events()
    blocks = warns = 0
    for e in events:
        sev = e.get("severity")
        if sev == "BLOCK":      blocks += 1
        elif sev == "WARN":     warns  += 1
    quarant = sum(
        1 for e in os.listdir(QUARANTINE_DIR)
        if os.path.isfile(os.path.join(QUARANTINE_DIR, e))
        and not e.endswith(_HASH_EXT)
    )
    prot_s  = f"{GRN}AKTYWNA{RST}"   if _state["protection"]     else f"{RED}WYLACZONA{RST}"
    watch_s = f"{GRN}ON{RST}"         if _state["watch"]           else f"{DIM}OFF{RST}"
    aq_s    = f"{GRN}ON{RST}"         if _state["auto_quarantine"] else f"{DIM}OFF{RST}"
    hooks_s = (f"{GRN}{len(_original_run)} komend{RST}"
               if _original_run else f"{DIM}brak{RST}")
    baseline = _load_baseline()
    base_s  = (f"{YLW}{len(baseline)} plikow{RST}"
               if baseline else f"{DIM}brak baseline{RST}")
    _w(f"\n{BOLD}  Status Defendera v2.1.0:{RST}\n\n")
    rows = [
        ("Ochrona:",          prot_s),
        ("Real-time watch:",  watch_s),
        ("Auto-kwarantanna:", aq_s),
        ("Hooki komend:",     hooks_s),
        ("Wzorce skanera:",   f"{YLW}{len(_SCRIPT_PATTERNS)}{RST}"),
        ("Baseline:",         base_s),
        ("Zdarzen lacznie:",  f"{YLW}{len(events)}{RST}"),
        ("  BLOCK:",          f"{RED}{blocks}{RST}"),
        ("  WARN:",           f"{ORG}{warns}{RST}"),
        ("W kwarantannie:",   f"{MGT}{quarant}{RST}"),
        ("Kwarantanna:",      f"{DIM}{QUARANTINE_DIR}{RST}"),
        ("Logi:",             f"{DIM}{EVENTS_FILE}{RST}"),
    ]
    for k, v in rows:
        _w(f"  {CYN}{_pad(k, 24)}{RST}{v}\n")
    _w("\n")

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_SUB: dict[str, tuple] = {
    "scan":        (_cmd_scan,        False),
    "integrity":   (_cmd_integrity,   False),
    "baseline":    (_cmd_baseline,    False),
    "quarantine":  (_cmd_quarantine,  False),
    "restore":     (_cmd_restore,     False),
    "events":      (_cmd_events,      False),
    "status":      (_cmd_status,      False),
    "watch":       (_cmd_watch,       True),
    "auto":        (_cmd_auto,        False),
    "on":          (_cmd_on,          True),
    "off":         (_cmd_off,         True),
}

# ---------------------------------------------------------------------------
# setup / teardown
# ---------------------------------------------------------------------------

def setup(terminal) -> None:
    _ensure_dirs()
    _install_hooks(terminal)

    # Skan startowy calego ekosystemu (nie blokuje, tylko loguje)
    def _startup_scan():
        found = []
        for fpath in _all_ecosystem_files():
            hits = _scan_file(fpath)
            if hits:
                found.append((fpath, hits))
        if found:
            _log_event("WARN", "defender",
                       f"Skan startowy: {len(found)} zagrozen w ekosystemie")

    t = threading.Thread(target=_startup_scan, daemon=True, name="defender-startup")
    t.start()

    # Uruchom watch jesli ochrona aktywna
    _start_watch(terminal)
    _log_event("INFO", "defender", "Defender v2.1.0 uruchomiony (watch ON - pelny ekosystem)")

    def defender_cmd(args: list) -> None:
        if not args:
            _menu(); return
        sub = args[0]
        if sub not in _SUB:
            _w(f"  {RED}Nieznane podpolecenie: {sub}{RST}\n")
            _menu(); return
        fn, needs_terminal = _SUB[sub]
        fn(args[1:], terminal) if needs_terminal else fn(args[1:])

    terminal.register_command(
        "defender", defender_cmd,
        description=terminal.t("cmd_defender"),
        category=terminal.t("cat_ecosystem"),
    )

    try:
        from . import _integration
        _integration.register("defender", {
            "scan_file":       _scan_file_safe,
            "check_integrity": _sha256_check_integrity,
            "is_protected":    lambda: _state["protection"],
        })
    except Exception:
        pass


def teardown(terminal) -> None:
    _stop_watch()
    _remove_hooks(terminal)
    _log_event("INFO", "defender", "Defender zatrzymany")
    _flush_events()
    terminal.commands.pop("defender", None)
    try:
        from . import _integration
        _integration.unregister("defender")
    except Exception:
        pass
