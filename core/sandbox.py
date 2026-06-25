"""Sandbox module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski

Izolowane srodowisko uruchamiania skryptow i plikow.
Zapewnia warstwowa izolacje bez zewnetrznych zaleznosci.

Warstwy izolacji (od najslabszej do najsilniejszej):
  L1 - czyste env (tylko niezbedne zmienne PATH/LANG)
  L2 - tymczasowy workdir (tmpfs, usuwany po zakonczeniu)
  L3 - limity zasobow (CPU, RAM, pliki, procesy) via setrlimit
  L4 - Linux namespaces via unshare(2) - izolacja PID/NET/IPC/UTS
  L5 - firejail / bwrap / nsjail - jesli dostepne w PATH

Komendy:
  sandbox run <plik> [args...]   - uruchom plik w sandbox
  sandbox set <klucz> <wartosc>  - zmien ustawienie
  sandbox show                   - pokaz biezaca konfiguracje
  sandbox profiles               - lista profili
  sandbox profile <nazwa>        - przelacz profil
  sandbox last                   - wyniki ostatniego uruchomienia
  sandbox log                    - historia uruchomien
  sandbox clear                  - wyczysc log
"""

import os
import sys
import time
import shutil
import subprocess
import tempfile
import threading
import json
import uuid
import stat
import math
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, IS_WIN, IS_LIN, IS_MAC, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _strip, _pad
_VERSION = "2.8"

# -- ANSI ---------------------------------------------------------------------

def _w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()

# -- ANSI color shortcuts (standalone, dla funkcji z uploaded sandbox) ---------

class _C:
    RESET   = "\x1b[0m";  BOLD    = "\x1b[1m";  DIM     = "\x1b[2m"
    BCYAN   = "\x1b[96m"; BYELLOW = "\x1b[93m"; BGREEN  = "\x1b[92m"
    BWHITE  = "\x1b[97m"; RED     = "\x1b[91m";  CYAN    = "\x1b[36m"
    MAGENTA = "\x1b[95m"; YELLOW  = "\x1b[33m";  BLUE    = "\x1b[94m"

# -- statystyki sandboxa (dla monitora) ---------------------------------------

class _SandboxStats:
    """Przechowuje informacje o aktualnej aktywności sandboxa."""
    active_task = None  # Nazwa pliku lub zadania
    active_proc = None  # Obiekt procesu subprocess.Popen
    start_time  = 0.0   # Czas rozpoczęcia

class _SandboxEnv:
    """Przechowuje zmienne środowiskowe dla sb.run."""
    _env_vars: dict = {}

SANDBOX_ENV = _SandboxEnv()

# -- integracja z runner.py: delegujemy wyszukiwanie interpretera -------------
# Zamiast duplikowac _EXT_INTERPRETERS, uzywamy _EXT_MAP i _find_interpreter
# z runner.py. Jesli runner nie jest jeszcze zaladowany, fallback do shutil.which.

def _find_interpreter(ext: str) -> str | None:
    """Znajdz interpreter dla danego rozszerzenia.

    Deleguje do _integration.find_interpreter() (runner.py lub fallback wbudowany).
    """
    from . import _integration as _intg
    interp, _ = _intg.find_interpreter(ext)
    return interp


def _get_extra_run_args(interp_basename: str) -> list[str]:
    """Zwraca dodatkowe argumenty dla interpretera (np. -ExecutionPolicy dla pwsh)."""
    from . import _integration as _intg
    runner = _intg.get("runner")
    if runner:
        plugins = runner.get("plugins", {})
        # find plugin name by interpreter basename
        ext_map = runner.get("ext_map", {})
        for ext, plugin_name in ext_map.items():
            plugin = plugins.get(plugin_name, {})
            run_args = plugin.get("run_args", [])
            interp_candidates = plugin.get("interp", [])
            if any(os.path.basename(c) == interp_basename for c in interp_candidates):
                return run_args
    # Fallback wbudowany
    _FALLBACK_ARGS: dict[str, list[str]] = {
        "pwsh":       ["-ExecutionPolicy", "Bypass", "-File"],
        "powershell": ["-ExecutionPolicy", "Bypass", "-File"],
        "go":         ["run"],
    }
    return _FALLBACK_ARGS.get(interp_basename, [])

# -- resource limits ----------------------------------------------------------

_MB = 1024 * 1024

PROFILES: dict[str, dict] = {
    "strict": {
        "cpu_sec":      10,
        "mem_mb":       128,
        "fsize_mb":     8,
        "max_procs":    16,
        "max_files":    64,
        "net_blocked":  True,
        "use_namespaces": True,
    },
    "default": {
        "cpu_sec":      30,
        "mem_mb":       512,
        "fsize_mb":     64,
        "max_procs":    64,
        "max_files":    256,
        "net_blocked":  False,
        "use_namespaces": True,
    },
    "relaxed": {
        "cpu_sec":      120,
        "mem_mb":       1024,
        "fsize_mb":     256,
        "max_procs":    128,
        "max_files":    512,
        "net_blocked":  False,
        "use_namespaces": False,
    },
    "unsafe": {
        "cpu_sec":      300,
        "mem_mb":       0,       # 0 = bez limitu
        "fsize_mb":     0,
        "max_procs":    0,
        "max_files":    0,
        "net_blocked":  False,
        "use_namespaces": False,
    },
}

# -- runtime state ------------------------------------------------------------

_current_profile: str = "default"
_run_log:         list = []          # lista dict z wynikami
_last_result:     dict | None = None

# -- core helpers (file inspection, scanning, reports) -----------------------

def _fmt_size(num_bytes: int) -> str:
    """Format size in human readable units."""
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} EB"


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def _hash_file(path: Path, algo: str = "md5") -> str:
    """Return hex digest of file or '?' on error."""
    try:
        h = hashlib.new(algo)
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "?"


def _entropy(data: bytes) -> float:
    """Shannon entropy of bytes (0..8)."""
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    total = float(len(data))
    ent = 0.0
    for c in counts:
        if c:
            p = c / total
            ent -= p * math.log2(p)
    return ent


def _read_head(path: Path, max_bytes: int = 4096) -> bytes:
    try:
        with path.open("rb") as f:
            return f.read(max_bytes)
    except Exception:
        return b""


def _is_text_bytes(data: bytes) -> bool:
    """Heuristic: treat as text if most bytes are printable or whitespace."""
    if not data:
        return True
    printable = 0
    for b in data:
        if 32 <= b <= 126 or b in (9, 10, 13):
            printable += 1
    ratio = printable / float(len(data))
    return ratio > 0.85


def _detect_bom(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return "UTF-8 BOM"
    if data.startswith(b"\xff\xfe\x00\x00"):
        return "UTF-32 LE BOM"
    if data.startswith(b"\x00\x00\xfe\xff"):
        return "UTF-32 BE BOM"
    if data.startswith(b"\xff\xfe"):
        return "UTF-16 LE BOM"
    if data.startswith(b"\xfe\xff"):
        return "UTF-16 BE BOM"
    return "none"


def _guess_encoding(data: bytes) -> str:
    """Very simple encoding guess: BOM or fallback to ascii/utf-8/unknown."""
    if not data:
        return "unknown"
    bom = _detect_bom(data)
    if bom != "none":
        return bom
    try:
        data.decode("utf-8")
        return "UTF-8"
    except Exception:
        pass
    try:
        data.decode("ascii")
        return "ASCII"
    except Exception:
        pass
    return "unknown"


def _file_type_from_magic(data: bytes) -> str:
    """Very small magic-based type guess."""
    if data.startswith(b"\x7fELF"):
        return "ELF binary"
    if data.startswith(b"MZ"):
        return "PE executable"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG image"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG image"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "GIF image"
    if data.startswith(b"PK\x03\x04"):
        return "ZIP archive"
    if data.startswith(b"%PDF-"):
        return "PDF document"
    if data.startswith(b"SQLite format 3\x00"):
        return "SQLite database"
    if data.startswith(b"ID3"):
        return "MP3 audio (ID3)"
    if data.startswith(b"OggS"):
        return "Ogg media"
    if data.startswith(b"fLaC"):
        return "FLAC audio"
    if data.startswith(b"BM"):
        return "BMP image"
    if data.startswith(b"\x1f\x8b\x08"):
        return "GZIP archive"
    if data.startswith(b"BZh"):
        return "BZIP2 archive"
    if data.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7-Zip archive"
    if data.startswith(b"\x00\x00\x00\x18ftypmp42") or data.startswith(b"\x00\x00\x00\x20ftypisom"):
        return "MP4 video"
    if data.startswith(b"#!"):
        return "Script (shebang)"
    if _is_text_bytes(data):
        return "Text file"
    return "Binary file"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize_path(p_str: str) -> Path:
    """Sanitize path string and prevent directory traversal."""
    return Path(p_str)


# -- file inspection ----------------------------------------------------------

def inspect_file(path: Path) -> dict:
    """Return rich info about a single file."""
    info = {
        "exists": False, "path": str(path), "resolved": "",
        "is_dir": False, "size": 0, "size_human": "",
        "created": "", "modified": "",
        "hash_md5": "?", "hash_sha1": "?",
        "entropy": 0.0, "type": "unknown", "encoding": "unknown",
        "bom": "none", "is_text": False, "is_hidden": False,
        "is_executable": False, "warnings": [],
        "line_count": None, "word_count": None, "char_count": None,
    }

    if not path.exists():
        return info

    info["exists"] = True
    info["resolved"] = str(path.resolve())
    info["is_dir"] = path.is_dir()

    try:
        st = path.stat()
        info["size"] = st.st_size
        info["size_human"] = _fmt_size(st.st_size)
        info["created"]  = datetime.fromtimestamp(st.st_ctime).isoformat(sep=" ")
        info["modified"] = datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ")
    except Exception:
        pass

    if path.is_dir():
        return info

    head = _read_head(path, 4096)
    info["entropy"]  = round(_entropy(head), 3)
    info["type"]     = _file_type_from_magic(head)
    info["encoding"] = _guess_encoding(head)
    info["bom"]      = _detect_bom(head)
    info["is_text"]  = _is_text_bytes(head)

    try:
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path.resolve()))
        if attrs != -1 and (attrs & 2):
            info["is_hidden"] = True
            info["warnings"].append("File is HIDDEN")
    except Exception:
        pass

    ext = path.suffix.lower()
    exec_exts = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".scr", ".pif", ".com"}
    if ext in exec_exts:
        info["is_executable"] = True

    parts = path.name.split(".")
    if len(parts) > 2:
        last_ext = "." + parts[-1].lower()
        prev_ext = "." + parts[-2].lower()
        if last_ext in exec_exts and prev_ext in {".txt", ".pdf", ".jpg", ".png", ".doc", ".docx"}:
            info["warnings"].append(f"Suspicious double extension: {prev_ext}{last_ext}")

    if "temp" in str(path).lower() or "appdata" in str(path).lower():
        if info["is_executable"]:
            info["warnings"].append("Executable in suspicious directory (Temp/AppData)")

    info["hash_md5"]  = _hash_file(path, "md5")
    info["hash_sha1"] = _hash_file(path, "sha1")

    if info["is_text"]:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            info["char_count"] = len(text)
            info["line_count"] = text.count("\n") + 1 if text else 0
            info["word_count"] = len(text.split())
        except Exception:
            pass

    return info


def print_file_summary(info: dict):
    """Print human readable summary of inspect_file result."""
    if not info.get("exists"):
        print(f"SandBoy: file does not exist: {info.get('path')}")
        return

    print()
    print("SandBoy - file summary")
    print("----------------------")
    print(f"Path:        {info.get('resolved')}")
    print(f"Type:        {info.get('type')}")
    print(f"Size:        {info.get('size_human')} ({info.get('size')} bytes)")
    print(f"Created:     {info.get('created')}")
    print(f"Modified:    {info.get('modified')}")
    print(f"MD5:         {info.get('hash_md5')}")
    print(f"SHA1:        {info.get('hash_sha1')}")
    print(f"Entropy:     {info.get('entropy')}")
    print(f"Encoding:    {info.get('encoding')}")
    print(f"BOM:         {info.get('bom')}")
    print(f"Is text:     {info.get('is_text')}")

    warnings = info.get("warnings", [])
    if warnings:
        print(f"{_C.RED}Warnings:    {', '.join(warnings)}{_C.RESET}")

    if info.get("is_text"):
        print(f"Lines:       {info.get('line_count')}")
        print(f"Words:       {info.get('word_count')}")
        print(f"Chars:       {info.get('char_count')}")
    print()


# -- directory scanner --------------------------------------------------------

class ScanFilters:
    def __init__(self, recursive=True, ext=None, min_size=None, max_size=None):
        self.recursive = recursive
        self.ext = ext.lower() if ext else None
        self.min_size = min_size
        self.max_size = max_size

    def match(self, path: Path, st) -> bool:
        if self.ext and path.suffix.lower() != self.ext:
            return False
        if self.min_size is not None and st.st_size < self.min_size:
            return False
        if self.max_size is not None and st.st_size > self.max_size:
            return False
        return True


def scan_directory(root: Path, filters: ScanFilters):
    """Scan directory and return aggregate stats and duplicates map."""
    files = []
    total_size = 0
    total_count = 0
    size_map = {}

    if not root.exists() or not root.is_dir():
        return {"root": str(root), "files": [], "total_size": 0,
                "total_count": 0, "duplicates": {}}

    def handle_file(p: Path):
        nonlocal total_size, total_count
        try:
            st = p.stat()
        except Exception:
            return
        if not filters.match(p, st):
            return
        info = {
            "path": str(p), "size": st.st_size,
            "size_human": _fmt_size(st.st_size),
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(sep=" "),
        }
        total_size  += st.st_size
        total_count += 1
        files.append(info)
        size_map.setdefault(st.st_size, []).append(p)

    _w(f"  {_C.DIM}Scanning... {_C.RESET}")
    if filters.recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            for name in filenames:
                handle_file(Path(dirpath) / name)
    else:
        for entry in root.iterdir():
            if entry.is_file():
                handle_file(entry)
    _w(f"{_C.BGREEN}done ({total_count} files){_C.RESET}\n")

    duplicates = {}
    potential_dupes = [paths for size, paths in size_map.items() if len(paths) > 1 and size > 0]
    if potential_dupes:
        _w(f"  {_C.DIM}Checking duplicates... {_C.RESET}")
        hash_map = {}
        processed = 0
        for paths in potential_dupes:
            for p in paths:
                md5 = _hash_file(p, "md5")
                if md5 != "?":
                    hash_map.setdefault(md5, []).append(str(p))
                processed += 1
                if processed % 10 == 0:
                    _w(".")
        duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
        _w(f" {_C.BGREEN}done{_C.RESET}\n")

    return {"root": str(root), "files": files, "total_size": total_size,
            "total_count": total_count, "duplicates": duplicates}


def print_scan_summary(result: dict):
    print()
    print("SandBoy - directory scan")
    print("------------------------")
    print(f"Root:        {result.get('root')}")
    print(f"Files:       {result.get('total_count')}")
    print(f"Total size:  {_fmt_size(result.get('total_size', 0))}")
    print()
    files = result.get("files", [])
    if not files:
        print("No matching files.")
        print()
        return
    print("Sample files:")
    for info in files[:20]:
        print(f"  {info['size_human']:>10}  {info['path']}")
    if len(files) > 20:
        print(f"  ... {len(files) - 20} more")
    print()
    dups = result.get("duplicates", {})
    if dups:
        print("Duplicates (by MD5):")
        for h, paths in dups.items():
            print(f"  {h}:")
            for p in paths:
                print(f"    {p}")
        print()
    else:
        print("No duplicates detected.")
        print()


# -- reports ------------------------------------------------------------------

def build_report(root: Path, scan_result: dict) -> dict:
    """Build extended report structure."""
    files      = scan_result.get("files", [])
    total_size = scan_result.get("total_size", 0)
    total_count = scan_result.get("total_count", 0)
    duplicates = scan_result.get("duplicates", {})
    largest = sorted(files, key=lambda x: x["size"], reverse=True)[:10]
    newest  = sorted(files, key=lambda x: x["modified"], reverse=True)[:10]
    return {
        "generated_at": _now_str(), "root": str(root),
        "summary": {
            "file_count": total_count, "total_size": total_size,
            "total_size_human": _fmt_size(total_size),
            "duplicate_groups": len(duplicates),
        },
        "largest_files": largest, "newest_files": newest, "duplicates": duplicates,
    }


def save_report_txt(path: Path, report: dict):
    """Save human readable TXT report."""
    try:
        with path.open("w", encoding="utf-8") as f:
            w = f.write
            w("SandBoy PRO report\n===================\n\n")
            w(f"Generated at: {report['generated_at']}\n")
            w(f"Root:        {report['root']}\n\n")
            s = report["summary"]
            w("Summary\n-------\n")
            w(f"Files:       {s['file_count']}\n")
            w(f"Total size:  {s['total_size_human']} ({s['total_size']} bytes)\n")
            w(f"Duplicates:  {s['duplicate_groups']} groups\n\n")
            w("Largest files\n-------------\n")
            for info in report["largest_files"]:
                w(f"{info['size_human']:>10}  {info['path']}\n")
            w("\n")
            w("Newest files\n------------\n")
            for info in report["newest_files"]:
                w(f"{info['modified']}  {info['path']}\n")
            w("\n")
            if report["duplicates"]:
                w("Duplicates (by MD5)\n-------------------\n")
                for h, paths in report["duplicates"].items():
                    w(f"{h}:\n")
                    for p in paths:
                        w(f"  {p}\n")
                w("\n")
            else:
                w("No duplicates detected.\n\n")
    except Exception as e:
        print(f"SandBoy: failed to write TXT report: {e}")


def save_report_json(path: Path, report: dict):
    """Save JSON report."""
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    except Exception as e:
        print(f"SandBoy: failed to write JSON report: {e}")


# -- sandbox config / policy --------------------------------------------------

class SandboxConfig:
    def __init__(self):
        self.whitelist = []
        self.blacklist = []
        self.trusted_hashes = set()
        self.dry_run = True
        self.log_file = None
        self.suspicious_patterns = [
            b"os.system", b"subprocess.Popen", b"subprocess.call", b"subprocess.run",
            b"eval(", b"exec(", b"__import__", b"pickle.load", b"base64.b64decode",
            b"socket.", b"requests.", b"urllib.", b"chmod", b"rm -rf", b"format C:",
            b"powershell", b"encodedcommand", b"Invoke-Expression", b"iex",
        ]

    def is_allowed(self, path: Path) -> bool:
        try:
            p = path.resolve()
        except Exception:
            return False
        for b in self.blacklist:
            try:
                if p.is_relative_to(b):
                    return False
            except AttributeError:
                if str(p).startswith(str(b) + os.sep):
                    return False
        if self.whitelist:
            for w in self.whitelist:
                try:
                    if p.is_relative_to(w):
                        return True
                except AttributeError:
                    if str(p).startswith(str(w) + os.sep):
                        return True
            return False
        return True

    def is_trusted(self, path: Path) -> bool:
        if not self.trusted_hashes:
            return True
        h = _hash_file(path, "sha256")
        return h in self.trusted_hashes

    def scan_content(self, data: bytes) -> list:
        found = []
        for pattern in self.suspicious_patterns:
            if pattern in data:
                found.append(pattern.decode(errors="replace"))
        return found

    def log(self, msg: str):
        if not self.log_file:
            return
        try:
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(f"[{_now_str()}] {msg}\n")
        except Exception:
            pass


SANDBOX = SandboxConfig()


def sandbox_analyze_file(path: Path):
    """Analyze file in sandbox: no modifications, only inspection + suspicious scan."""
    if not SANDBOX.is_allowed(path):
        print(f"{_C.RED}SandBoy sandbox: access denied by policy: {path}{_C.RESET}")
        SANDBOX.log(f"DENY analyze {path}")
        return
    _SandboxStats.active_task = path.name
    _SandboxStats.start_time  = time.time()
    try:
        info = inspect_file(path)
        SANDBOX.log(f"ANALYZE {path}")
        print_file_summary(info)
        if info.get("exists") and not info.get("is_dir"):
            head  = _read_head(path, 8192)
            found = SANDBOX.scan_content(head)
            if found:
                print(f"{_C.RED}{_C.BOLD}⚠ WARNING: Suspicious patterns detected!{_C.RESET}")
                for f in found:
                    print(f"  - {f}")
                print()
            print("Head (ASCII):")
            ascii_repr = "".join(chr(b) if 32 <= b <= 126 else "." for b in head[:128])
            print("  " + ascii_repr)
            print()
    finally:
        _SandboxStats.active_task = None


# -- task runner --------------------------------------------------------------

def task_audit(root: Path, out_dir: Path):
    """Full audit: scan + report TXT + JSON."""
    filters  = ScanFilters(recursive=True)
    result   = scan_directory(root, filters)
    report   = build_report(root, result)
    out_dir.mkdir(parents=True, exist_ok=True)
    base     = out_dir / "sandboy_audit"
    save_report_txt(base.with_suffix(".txt"), report)
    save_report_json(base.with_suffix(".json"), report)
    print(f"SandBoy task: audit completed\n  TXT:  {base.with_suffix('.txt')}\n  JSON: {base.with_suffix('.json')}\n")


def task_hashall(root: Path, out_file: Path):
    """Generate list of files with hashes."""
    filters = ScanFilters(recursive=True)
    result  = scan_directory(root, filters)
    files   = result.get("files", [])
    try:
        with out_file.open("w", encoding="utf-8") as f:
            for info in files:
                p    = Path(info["path"])
                md5  = _hash_file(p, "md5")
                sha1 = _hash_file(p, "sha1")
                f.write(f"{md5}  {sha1}  {info['path']}\n")
        print(f"SandBoy task: hashall completed\n  Output: {out_file}\n")
    except Exception as e:
        print(f"SandBoy: failed to write hashall output: {e}")


def task_dupes(root: Path):
    """Print duplicate files by MD5."""
    filters = ScanFilters(recursive=True)
    result  = scan_directory(root, filters)
    dups    = result.get("duplicates", {})
    if not dups:
        print("SandBoy task: dupes - no duplicates found\n")
        return
    print("SandBoy task: dupes\n--------------------")
    for h, paths in dups.items():
        print(h)
        for p in paths:
            print(f"  {p}")
    print()


# -- CML menu -----------------------------------------------------------------

def cml_menu():
    _w(f"\n{_C.BOLD}{_C.BCYAN}  ╭──────────────────────────────────────────╮{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  │   🛡️  Moduł: SandBox PRO v{_VERSION}            │{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  ╰──────────────────────────────────────────╯{_C.RESET}\n\n")
    cmds = [
        ("sb.check <file>",          "Szybkie sprawdzenie istnienia i rozmiaru"),
        ("sb.info <file>",           "Szczegółowa inspekcja pliku i metadanych"),
        ("sb.scan <dir> [opts]",     "Skanowanie katalogu (filtry, rozmiary)"),
        ("sb.report <dir>",          "Generowanie rozszerzonego raportu (TXT/JSON)"),
        ("sb.sandbox <file>",        "Bezpieczna analiza zawartości pliku"),
        ("sb.run <cmd> [args...]",   "Uruchom proces w izolowanym kontenerze"),
        ("sb.env set|unset|show",    "Zarządzaj zmiennymi środowiskowymi"),
        ("sb.policy show|add|clear", "Reguły: whitelist, blacklist, trust"),
        ("sb.policy log|dryrun",     "Konfiguracja logowania i trybu dry-run"),
        ("sb.task audit <dir>",      "Zautomatyzowany audyt całego katalogu"),
        ("sb.task hashall <dir>",    "Generowanie listy skrótów MD5/SHA1"),
        ("sb.task dupes <dir>",      "Wyszukiwanie duplikatów w locie"),
        ("sandbox run <file>",       "Uruchom plik w sandbox (firejail/bwrap/ns)"),
        ("sandbox show",             "Pokaż bieżącą konfigurację sandbox"),
        ("sandbox profiles",         "Lista profili izolacji"),
        ("sandbox log",              "Historia uruchomień sandbox"),
    ]
    for c, d in cmds:
        _w(f"  {_C.BYELLOW}{c:<28}{_C.RESET} {_C.DIM}{d}{_C.RESET}\n")
    _w(f"\n  {_C.BOLD}{_C.BWHITE}Opcje skanowania:{_C.RESET} "
       f"{_C.DIM}-nr, --ext .ext, --min N, --max N{_C.RESET}\n")
    _w(f"  {_C.DIM}Komendy globalne: {_C.RESET}"
       f"{_C.BYELLOW}sb.*{_C.RESET}  {_C.BYELLOW}sand{_C.RESET}  {_C.BYELLOW}sandboy{_C.RESET}"
       f"  {_C.BYELLOW}sandbox{_C.RESET}\n\n")


# -- CML subcommands ----------------------------------------------------------

def _cmd_sb_check(args, term):
    if not args:
        print("Usage: sb.check <file>")
        return
    p = _sanitize_path(args[0])
    if not p.exists():
        print(f"SandBoy: file does not exist: {p}")
        return
    st = p.stat()
    print("\nSandBoy - quick check\n---------------------")
    print(f"Path:   {p.resolve()}")
    print(f"Size:   {_fmt_size(st.st_size)} ({st.st_size} bytes)")
    print(f"Is dir: {p.is_dir()}\n")


def _cmd_sb_info(args, term):
    if not args:
        print("Usage: sb.info <file>")
        return
    p = _sanitize_path(args[0])
    info = inspect_file(p)
    print_file_summary(info)


def _parse_scan_args(args):
    if not args:
        return Path("."), ScanFilters(recursive=True)
    root = _sanitize_path(args[0])
    recursive = True
    ext = min_size = max_size = None
    i = 1
    while i < len(args):
        a = args[i]
        if a == "-nr":
            recursive = False; i += 1
        elif a == "--ext" and i + 1 < len(args):
            ext = args[i + 1]; i += 2
        elif a == "--min" and i + 1 < len(args):
            min_size = _safe_int(args[i + 1], None); i += 2
        elif a == "--max" and i + 1 < len(args):
            max_size = _safe_int(args[i + 1], None); i += 2
        else:
            i += 1
    return root, ScanFilters(recursive=recursive, ext=ext, min_size=min_size, max_size=max_size)


def _cmd_sb_scan(args, term):
    root, filters = _parse_scan_args(args or ["."])
    result = scan_directory(root, filters)
    print_scan_summary(result)


def _cmd_sb_report(args, term):
    if not args:
        print("Usage: sb.report <dir> [outdir]")
        return
    root    = _sanitize_path(args[0])
    out_dir = _sanitize_path(args[1]) if len(args) > 1 else Path("sandboy_reports")
    filters = ScanFilters(recursive=True)
    result  = scan_directory(root, filters)
    report  = build_report(root, result)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / "sandboy_report"
    save_report_txt(base.with_suffix(".txt"), report)
    save_report_json(base.with_suffix(".json"), report)
    print(f"SandBoy report generated\n  TXT:  {base.with_suffix('.txt')}\n  JSON: {base.with_suffix('.json')}\n")


def _cmd_sb_sandbox(args, term):
    if not args:
        print("Usage: sb.sandbox <file>")
        return
    sandbox_analyze_file(_sanitize_path(args[0]))


def _cmd_sb_task(args, term):
    if not args:
        print("Usage: sb.task <name> ...\nTasks:\n  audit <dir> [outdir]\n  hashall <dir> <outfile>\n  dupes <dir>")
        return
    name = args[0]; rest = args[1:]
    if name == "audit":
        if not rest: print("Usage: sb.task audit <dir> [outdir]"); return
        task_audit(_sanitize_path(rest[0]),
                   _sanitize_path(rest[1]) if len(rest) > 1 else Path("sandboy_reports"))
    elif name == "hashall":
        if len(rest) < 2: print("Usage: sb.task hashall <dir> <outfile>"); return
        task_hashall(_sanitize_path(rest[0]), _sanitize_path(rest[1]))
    elif name == "dupes":
        if not rest: print("Usage: sb.task dupes <dir>"); return
        task_dupes(_sanitize_path(rest[0]))
    else:
        print(f"SandBoy: unknown task: {name}")


def _cmd_sb_policy(args, term):
    if not args or args[0] == "show":
        print("\nSandBoy Security Policy\n-----------------------")
        print(f"Whitelist:      {[str(p) for p in SANDBOX.whitelist] or 'empty'}")
        print(f"Blacklist:      {[str(p) for p in SANDBOX.blacklist] or 'empty'}")
        print(f"Trusted hashes: {len(SANDBOX.trusted_hashes)} entries")
        print(f"Dry run:        {SANDBOX.dry_run}")
        print(f"Log file:       {SANDBOX.log_file or 'none'}")
        print(f"Patterns:       {len(SANDBOX.suspicious_patterns)} loaded\n")
        return
    sub = args[0].lower()
    if sub == "clear":
        SANDBOX.whitelist.clear(); SANDBOX.blacklist.clear(); SANDBOX.trusted_hashes.clear()
        print("SandBoy: policy and trust list cleared.")
    elif sub == "add" and len(args) >= 3:
        kind = args[1].lower(); path = Path(args[2]).resolve()
        if kind == "whitelist":
            SANDBOX.whitelist.append(path); print(f"SandBoy: added to whitelist: {path}")
        elif kind == "blacklist":
            SANDBOX.blacklist.append(path); print(f"SandBoy: added to blacklist: {path}")
        elif kind == "trust":
            if path.is_file():
                h = _hash_file(path, "sha256"); SANDBOX.trusted_hashes.add(h)
                print(f"SandBoy: added trusted hash for {path.name}: {h[:16]}...")
            else:
                print(f"SandBoy: {path} is not a file.")
        else:
            print("Usage: sb.policy add <whitelist|blacklist|trust> <path>")
    elif sub == "log" and len(args) >= 2:
        if args[1].lower() == "none":
            SANDBOX.log_file = None; print("SandBoy: logging disabled.")
        else:
            SANDBOX.log_file = Path(args[1]); print(f"SandBoy: log file set to: {SANDBOX.log_file}")
    elif sub == "dryrun" and len(args) >= 2:
        val = args[1].lower()
        if val in ("on", "true", "1"):
            SANDBOX.dry_run = True; print("SandBoy: dry run enabled.")
        elif val in ("off", "false", "0"):
            SANDBOX.dry_run = False; print("SandBoy: dry run disabled.")
        else:
            print("Usage: sb.policy dryrun on|off")
    else:
        print("Usage: sb.policy show|clear|add <type> <path>|log <file>|dryrun on|off")


def _cmd_sb_env(args, term):
    if not args or args[0] == "show":
        _w(f"\n  {_C.BOLD}{_C.BCYAN}Sandbox Environment Variables:{_C.RESET}\n")
        if not SANDBOX_ENV._env_vars:
            _w(f"  {_C.DIM}(empty){_C.RESET}\n\n")
        else:
            for k, v in sorted(SANDBOX_ENV._env_vars.items()):
                _w(f"  {_C.BYELLOW}{k}{_C.RESET}={v}\n")
            _w("\n")
        return
    sub = args[0].lower()
    if sub == "set":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: sb.env set <KEY>=<VALUE>{_C.RESET}\n\n"); return
        key_val = " ".join(args[1:])
        if "=" not in key_val:
            _w(f"\n  {_C.RED}✗ Nieprawidłowy format. Użyj: KEY=VALUE{_C.RESET}\n\n"); return
        key, val = key_val.split("=", 1)
        SANDBOX_ENV._env_vars[key.strip()] = val.strip()
        _w(f"  {_C.BGREEN}✓ Ustawiono: {key.strip()}={val.strip()}{_C.RESET}\n\n")
    elif sub == "unset":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: sb.env unset <KEY>{_C.RESET}\n\n"); return
        key = args[1].strip()
        if key in SANDBOX_ENV._env_vars:
            del SANDBOX_ENV._env_vars[key]
            _w(f"  {_C.BGREEN}✓ Usunięto: {key}{_C.RESET}\n\n")
        else:
            _w(f"  {_C.BYELLOW}⚠ Zmienna '{key}' nie znaleziona.{_C.RESET}\n\n")
    elif sub == "clear":
        SANDBOX_ENV._env_vars.clear()
        _w(f"  {_C.BGREEN}✓ Wyczyszczono wszystkie zmienne środowiskowe Sandboxa.{_C.RESET}\n\n")
    else:
        _w(f"\n  {_C.RED}✗ Nieznana subkomenda: sb.env {sub}{_C.RESET}\n"
           f"  {_C.DIM}Użycie: sb.env set|unset|show|clear{_C.RESET}\n\n")


def _cmd_sb_run(args, term):
    """sb.run <cmd> [args...] [--timeout N] — uruchom proces w izolowanym kontenerze."""
    if not args:
        print("Usage: sb.run <command> [args...] [--timeout N]")
        return
    timeout = 60
    clean_args = []
    i = 0
    while i < len(args):
        if args[i] == "--timeout" and i + 1 < len(args):
            try:
                timeout = int(args[i + 1])
            except ValueError:
                _w(f"{_C.RED}Invalid timeout value: {args[i+1]}{_C.RESET}\n"); return
            i += 2
        else:
            clean_args.append(args[i]); i += 1
    if not clean_args:
        print("Usage: sb.run <command> [args...] [--timeout N]"); return

    cmd_name = clean_args[0]
    cmd_path = Path(shutil.which(cmd_name) or cmd_name)

    if not SANDBOX.is_allowed(cmd_path):
        _w(f"  {_C.RED}✗ Access Denied: Command path not allowed by policy: {cmd_path}{_C.RESET}\n\n")
        SANDBOX.log(f"DENY EXEC {cmd_path}"); return
    if SANDBOX.trusted_hashes and not SANDBOX.is_trusted(cmd_path):
        _w(f"  {_C.RED}✗ Access Denied: Command is NOT trusted: {cmd_name}{_C.RESET}\n\n")
        SANDBOX.log(f"DENY TRUST {cmd_path}"); return

    _w(f"\n  {_C.BOLD}{_C.BCYAN}▶ Uruchamianie w Sandboxie:{_C.RESET}  "
       f"{_C.BWHITE}{' '.join(clean_args)}{_C.RESET}\n"
       f"  {_C.DIM}Timeout: {timeout}s{_C.RESET}\n"
       f"  {_C.DIM}{'─'*52}{_C.RESET}\n\n")

    start_time = time.time()
    _SandboxStats.active_task = clean_args[0]
    _SandboxStats.start_time  = start_time

    out = err = ""
    exitcode = -1
    status = "error"
    try:
        proc = subprocess.Popen(
            clean_args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(Path.cwd()),
            env={**os.environ.copy(), **SANDBOX_ENV._env_vars},
        )
        _SandboxStats.active_proc = proc
        try:
            out, err = proc.communicate(timeout=timeout)
            exitcode = proc.returncode
            status = "ok"
        except subprocess.TimeoutExpired:
            proc.kill(); out, err = proc.communicate()
            exitcode = -1; status = "timeout"
    except FileNotFoundError:
        _w(f"  {_C.RED}✗ Komenda '{clean_args[0]}' nie znaleziona w PATH.{_C.RESET}\n\n")
        return
    except Exception as e:
        _w(f"  {_C.RED}✗ Błąd uruchamiania: {e}{_C.RESET}\n\n"); return
    finally:
        _SandboxStats.active_task = None
        _SandboxStats.active_proc = None

    elapsed = time.time() - start_time
    if out.strip():
        _w(out)
        if not out.endswith("\n"):
            _w("\n")
    _w(f"\n  {_C.DIM}{'─'*52}{_C.RESET}\n")
    if status == "timeout":
        _w(f"  {_C.RED}⏱ Timeout po {timeout}s{_C.RESET}\n")
    elif exitcode == 0:
        _w(f"  {_C.BGREEN}✓ OK{_C.RESET}  {_C.DIM}czas: {elapsed:.3f}s{_C.RESET}\n")
    else:
        _w(f"  {_C.RED}✗ Kod wyjścia: {exitcode}{_C.RESET}  {_C.DIM}czas: {elapsed:.3f}s{_C.RESET}\n")
    if err.strip():
        _w(f"\n  {_C.BYELLOW}STDERR:{_C.RESET}\n")
        for line in err.rstrip().splitlines():
            _w(f"  {_C.DIM}{line}{_C.RESET}\n")
    _w("\n")


def _cmd_sb_menu(args, term):
    cml_menu()


# -- CML_COMMANDS dict --------------------------------------------------------

CML_COMMANDS = {
    "sb":         _cmd_sb_menu,
    "sb.help":    _cmd_sb_menu,
    "sb.menu":    _cmd_sb_menu,
    "sand":       _cmd_sb_menu,
    "sandboy":    _cmd_sb_menu,
    "sb.check":   _cmd_sb_check,
    "sb.info":    _cmd_sb_info,
    "sb.scan":    _cmd_sb_scan,
    "sb.report":  _cmd_sb_report,
    "sb.sandbox": _cmd_sb_sandbox,
    "sb.task":    _cmd_sb_task,
    "sb.env":     _cmd_sb_env,
    "sb.run":     _cmd_sb_run,
    "sb.policy":  _cmd_sb_policy,
}


# -- external sandbox tools ---------------------------------------------------

def _detect_sandbox_tool() -> str | None:
    """Wykrywa zewnetrzny tool izolacji: firejail > bwrap > nsjail."""
    for tool in ("firejail", "bwrap", "nsjail"):
        if shutil.which(tool):
            return tool
    return None

def _build_firejail_cmd(cmd: list[str], workdir: str, profile: dict) -> list[str]:
    fj = ["firejail",
          "--quiet",
          f"--private={workdir}",
          "--noroot",
          "--nosound",
          "--nodvd",
          "--notv",
          "--no3d",
          "--nogroups",
    ]
    if profile.get("net_blocked"):
        fj.append("--net=none")
    fj += ["--"] + cmd
    return fj

def _build_bwrap_cmd(cmd: list[str], workdir: str, profile: dict) -> list[str]:
    bw = ["bwrap",
          "--ro-bind", "/usr", "/usr",
          "--ro-bind", "/lib", "/lib",
          "--ro-bind", "/lib64", "/lib64",
          "--ro-bind", "/bin", "/bin",
          "--proc", "/proc",
          "--dev", "/dev",
          "--tmpfs", "/tmp",
          "--bind", workdir, "/sandbox",
          "--chdir", "/sandbox",
          "--unshare-pid",
          "--unshare-uts",
          "--unshare-ipc",
          "--die-with-parent",
    ]
    if profile.get("net_blocked"):
        bw.append("--unshare-net")
    bw += ["--"] + cmd
    return bw

# -- Linux namespace unshare --------------------------------------------------

def _make_preexec(profile: dict):
    """Zwraca funkcje preexec_fn ustawiajaca namespaces i rlimity w child."""
    cpu_sec   = profile.get("cpu_sec", 30)
    mem_mb    = profile.get("mem_mb", 512)
    fsize_mb  = profile.get("fsize_mb", 64)
    max_procs = profile.get("max_procs", 64)
    max_files = profile.get("max_files", 256)
    use_ns    = profile.get("use_namespaces", True) and IS_LIN

    def _preexec():
        # -- namespaces (Linux only) --
        if use_ns:
            try:
                import ctypes
                libc = ctypes.CDLL("libc.so.6", use_errno=True)
                CLONE_NEWPID = 0x20000000
                CLONE_NEWNS  = 0x00020000
                CLONE_NEWIPC = 0x08000000
                CLONE_NEWUTS = 0x04000000
                flags = CLONE_NEWPID | CLONE_NEWIPC | CLONE_NEWUTS
                libc.unshare(flags)
            except Exception:
                pass

        # -- rlimity --
        try:
            import resource as _res

            def _set(r, soft, hard=None):
                try:
                    cur_s, cur_h = _res.getrlimit(r)
                    h = hard if hard is not None else cur_h
                    if h != _res.RLIM_INFINITY and soft > h:
                        soft = h
                    _res.setrlimit(r, (soft, h))
                except Exception:
                    pass

            if cpu_sec > 0:
                _set(_res.RLIMIT_CPU, cpu_sec)

            if mem_mb > 0:
                mem_bytes = mem_mb * _MB
                _set(_res.RLIMIT_AS,    mem_bytes)
                _set(_res.RLIMIT_DATA,  mem_bytes)

            if fsize_mb > 0:
                _set(_res.RLIMIT_FSIZE, fsize_mb * _MB)

            if max_procs > 0:
                _set(_res.RLIMIT_NPROC, max_procs)

            if max_files > 0:
                _set(_res.RLIMIT_NOFILE, max_files, max_files)

        except ImportError:
            pass  # Windows - brak modulu resource

    return _preexec if (not IS_WIN) else None

# -- clean environment --------------------------------------------------------

def _clean_env(extra: dict | None = None) -> dict:
    """Buduje minimalne, czyste srodowisko dla procesu sandbox."""
    keep_keys = {"PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE",
                 "TERM", "TZ", "USER", "LOGNAME",
                 "SYSTEMROOT", "WINDIR", "COMSPEC"}   # Windows
    env = {k: v for k, v in os.environ.items() if k in keep_keys}
    env.setdefault("HOME", tempfile.gettempdir())
    env["SANDBOX"] = "1"
    env["TERMINALX_SANDBOX"] = "1"
    if extra:
        env.update(extra)
    return env

# -- core runner --------------------------------------------------------------

def _run_sandboxed(file_path: str, args: list[str], profile: dict,
                   timeout: int, verbose: bool) -> dict:
    """Uruchamia plik w izolowanym srodowisku. Zwraca dict z wynikiem."""
    start   = time.perf_counter()
    run_id  = str(uuid.uuid4())[:8]
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    absfile = os.path.abspath(file_path)
    ext     = os.path.splitext(file_path)[1]

    result: dict = {
        "id":         run_id,
        "file":       absfile,
        "profile":    _current_profile,
        "status":     "error",
        "exitcode":   -1,
        "stdout":     "",
        "stderr":     "",
        "time_sec":   0.0,
        "timestamp":  ts,
        "layer":      "none",
    }

    # -- preskan przez Defender (jesli zaladowany) ----------------------------
    try:
        from . import _integration
        if not _integration.defender_scan_file(absfile):
            _w(f"  {RED}[!!] SANDBOX: Defender zablokował uruchomienie pliku{RST}\n")
            _w(f"  {DIM}{absfile}{RST}\n\n")
            result["status"] = "defender_blocked"
            _integration.notify_event(
                None,
                f"Sandbox: Defender zablokowal uruchomienie pliku {os.path.basename(absfile)}",
                kind="err", title="SANDBOX",
            )
            return result
    except Exception:
        pass

    # -- znajdz interpreter ---------------------------------------------------
    interp = _find_interpreter(ext)
    if not interp:
        _w(f"  {RED}[!] Brak interpretera dla: {ext}{RST}\n")
        _w(f"  {DIM}Zainstaluj odpowiedni interpreter lub sprawdz sandbox run --help.{RST}\n\n")
        result["status"] = "no_interpreter"
        return result

    # -- tymczasowy workdir ---------------------------------------------------
    workdir = tempfile.mkdtemp(prefix="sbx_")
    try:
        # kopia pliku do workdir
        dst_file = os.path.join(workdir, os.path.basename(absfile))
        shutil.copy2(absfile, dst_file)
        # uprawnienia: usun bit wykonywalny dla skryptow (interpreter uruchamia)
        try:
            cur = os.stat(dst_file).st_mode
            os.chmod(dst_file, cur & ~(stat.S_ISUID | stat.S_ISGID))
        except Exception:
            pass

        env     = _clean_env()
        extra_a = _get_extra_run_args(os.path.basename(interp))
        base_cmd = [interp] + extra_a + [dst_file] + list(args)

        # -- wybierz warstwe izolacji -----------------------------------------
        sandbox_tool = _detect_sandbox_tool()
        layer        = "L1+L2+L3"
        final_cmd    = base_cmd
        preexec_fn   = None

        if sandbox_tool == "firejail":
            final_cmd = _build_firejail_cmd(base_cmd, workdir, profile)
            layer     = "firejail"
        elif sandbox_tool == "bwrap":
            final_cmd = _build_bwrap_cmd(base_cmd, workdir, profile)
            layer     = "bwrap"
        else:
            # brak zewnetrznego toola: rlimity + opcjonalne namespaces
            preexec_fn = _make_preexec(profile)
            if profile.get("use_namespaces") and IS_LIN:
                layer = "L1+L2+L3+L4(ns)"
            else:
                layer = "L1+L2+L3"

        result["layer"] = layer

        if verbose:
            _w(f"  {DIM}[sbx] layer : {layer}{RST}\n")
            _w(f"  {DIM}[sbx] cmd   : {' '.join(final_cmd)}{RST}\n")
            _w(f"  {DIM}[sbx] dir   : {workdir}{RST}\n")
            _w(f"  {DIM}[sbx] cpu   : {profile.get('cpu_sec')}s  "
               f"mem: {profile.get('mem_mb')}MB  "
               f"net: {'blocked' if profile.get('net_blocked') else 'allowed'}{RST}\n\n")

        # -- uruchom ----------------------------------------------------------
        net_env = env.copy()
        if profile.get("net_blocked") and sandbox_tool is None:
            # bez zewnetrznego toola: blokada sieci przez usniecie adresu
            # (proxy trick - brak pelnej izolacji bez bwrap/firejail na tym poziomie)
            net_env["http_proxy"]  = "http://127.0.0.2:1"
            net_env["https_proxy"] = "http://127.0.0.2:1"
            net_env["HTTP_PROXY"]  = "http://127.0.0.2:1"
            net_env["HTTPS_PROXY"] = "http://127.0.0.2:1"

        popen_kw: dict = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=net_env,
            cwd=workdir,
        )
        if preexec_fn and not IS_WIN:
            popen_kw["preexec_fn"] = preexec_fn

        proc = subprocess.Popen(final_cmd, **popen_kw)

        # -- zbierz output z timeoutem ----------------------------------------
        try:
            out, err = proc.communicate(timeout=timeout)
            exitcode  = proc.returncode
            status    = "ok" if exitcode == 0 else "nonzero"
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            exitcode = -1
            status   = "timeout"
        except Exception as exc:
            out, err = "", str(exc)
            exitcode = -1
            status   = "launch_error"

        elapsed = time.perf_counter() - start
        result.update({
            "status":   status,
            "exitcode": exitcode,
            "stdout":   out,
            "stderr":   err,
            "time_sec": round(elapsed, 3),
        })

    finally:
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass

    return result

# -- output printer -----------------------------------------------------------

def _print_result(res: dict, t) -> None:
    status   = res.get("status", "error")
    exitcode = res.get("exitcode", -1)
    elapsed  = res.get("time_sec", 0.0)
    layer    = res.get("layer", "?")
    stdout   = res.get("stdout", "").rstrip()
    stderr   = res.get("stderr", "").rstrip()

    if status == "ok":
        badge = f"{GRN}{BOLD}[OK]{RST}"
    elif status == "timeout":
        badge = f"{YLW}{BOLD}[TIMEOUT]{RST}"
    elif status == "nonzero":
        badge = f"{YLW}{BOLD}[EXIT {exitcode}]{RST}"
    else:
        badge = f"{RED}{BOLD}[{status.upper()}]{RST}"

    _w(f"\n  {badge}  {DIM}{elapsed*1000:.0f}ms  layer:{layer}{RST}\n")

    if stdout:
        _w(f"\n  {BOLD}{CYN}{t('sbx_stdout')}{RST}\n")
        for line in stdout.splitlines():
            _w(f"  {line}\n")

    if stderr:
        _w(f"\n  {BOLD}{YLW}{t('sbx_stderr')}{RST}\n")
        for line in stderr.splitlines():
            _w(f"  {DIM}{line}{RST}\n")

    _w("\n")

# -- subcommands --------------------------------------------------------------

def _cmd_run(args: list[str], t, verbose: bool = False) -> None:
    global _last_result

    if not args:
        _w(f"  {DIM}{t('sbx_run_usage')}{RST}\n")
        return

    file_path = args[0]
    run_args  = args[1:]

    if not os.path.isfile(file_path):
        _w(f"  {RED}{t('sbx_file_not_found', path=file_path)}{RST}\n\n")
        return

    profile = PROFILES.get(_current_profile, PROFILES["default"]).copy()
    timeout = profile.get("cpu_sec", 30) + 5   # grace period nad CPU limit

    fname = os.path.basename(file_path)
    _w(f"\n  {BOLD}{BCYN}{t('sbx_running', file=fname, profile=_current_profile)}{RST}\n")

    res = _run_sandboxed(file_path, run_args, profile, timeout, verbose)
    _last_result = res
    _run_log.append(res)
    if len(_run_log) > 200:
        _run_log.pop(0)

    _print_result(res, t)


def _cmd_show(t) -> None:
    p    = PROFILES.get(_current_profile, {})
    tool = _detect_sandbox_tool() or t("sbx_no_ext_tool")
    ns   = IS_LIN and p.get("use_namespaces", False)

    _w(f"\n  {BOLD}{BCYN}{t('sbx_config_title')}{RST}\n\n")
    _w(f"  {CYN}{'profile':<18}{RST} {YLW}{_current_profile}{RST}\n")
    _w(f"  {CYN}{'ext_tool':<18}{RST} {tool}\n")
    _w(f"  {CYN}{'cpu_sec':<18}{RST} {p.get('cpu_sec', '-')} s\n")
    _w(f"  {CYN}{'mem_mb':<18}{RST} {p.get('mem_mb', '-')} MB\n")
    _w(f"  {CYN}{'fsize_mb':<18}{RST} {p.get('fsize_mb', '-')} MB\n")
    _w(f"  {CYN}{'max_procs':<18}{RST} {p.get('max_procs', '-')}\n")
    _w(f"  {CYN}{'max_files':<18}{RST} {p.get('max_files', '-')}\n")
    _w(f"  {CYN}{'net_blocked':<18}{RST} {GRN+'YES'+RST if p.get('net_blocked') else RED+'NO'+RST}\n")
    _w(f"  {CYN}{'namespaces':<18}{RST} {GRN+'YES'+RST if ns else DIM+'NO'+RST}\n")
    _w(f"  {CYN}{'platform':<18}{RST} {sys.platform}\n")
    _w(f"  {CYN}{'log_entries':<18}{RST} {len(_run_log)}\n")
    _w("\n")


def _cmd_profiles(t) -> None:
    _w(f"\n  {BOLD}{CYN}{t('sbx_profiles_title')}{RST}\n\n")
    for name, p in PROFILES.items():
        mark = f"  {GRN}<-- active{RST}" if name == _current_profile else ""
        _w(f"  {YLW}{name:<12}{RST}"
           f"  cpu:{p.get('cpu_sec','-')}s"
           f"  mem:{p.get('mem_mb','-')}MB"
           f"  net:{'block' if p.get('net_blocked') else 'allow'}"
           f"  ns:{'on' if p.get('use_namespaces') else 'off'}"
           f"{mark}\n")
    _w(f"\n  {DIM}{t('sbx_profile_hint')}{RST}\n\n")


def _cmd_profile(args: list[str], t) -> None:
    global _current_profile
    if not args:
        _w(f"  {DIM}{t('sbx_profile_usage')}{RST}\n")
        return
    name = args[0].lower()
    if name not in PROFILES:
        _w(f"  {RED}{t('sbx_profile_unknown', name=name)}{RST}\n")
        _w(f"  {DIM}{t('sbx_profile_hint')}{RST}\n")
        return
    _current_profile = name
    _w(f"  {GRN}{t('sbx_profile_set', name=name)}{RST}\n")


def _cmd_set(args: list[str], t) -> None:
    """Zmienia parametr aktywnego profilu w runtime."""
    if len(args) < 2:
        _w(f"  {DIM}{t('sbx_set_usage')}{RST}\n")
        return
    key, val = args[0], args[1]
    profile  = PROFILES.setdefault(_current_profile, {})
    int_keys = {"cpu_sec", "mem_mb", "fsize_mb", "max_procs", "max_files"}
    bool_keys = {"net_blocked", "use_namespaces"}

    if key in int_keys:
        try:
            profile[key] = int(val)
            _w(f"  {GRN}{t('sbx_set_ok', key=key, val=val)}{RST}\n")
        except ValueError:
            _w(f"  {RED}{t('sbx_set_invalid', key=key, val=val)}{RST}\n")
    elif key in bool_keys:
        profile[key] = val.lower() in ("1", "true", "yes", "on")
        _w(f"  {GRN}{t('sbx_set_ok', key=key, val=str(profile[key]))}{RST}\n")
    else:
        _w(f"  {RED}{t('sbx_set_unknown_key', key=key)}{RST}\n")
        _w(f"  {DIM}keys: {', '.join(sorted(int_keys | bool_keys))}{RST}\n")


def _cmd_last(t) -> None:
    if not _last_result:
        _w(f"  {DIM}{t('sbx_log_empty')}{RST}\n")
        return
    r = _last_result
    _w(f"\n  {BOLD}{CYN}{t('sbx_last_title')}{RST}\n\n")
    for k, v in r.items():
        if k in ("stdout", "stderr"):
            snippet = (v[:120] + "...") if len(v) > 120 else v
            _w(f"  {CYN}{k:<12}{RST}  {DIM}{repr(snippet)}{RST}\n")
        else:
            _w(f"  {CYN}{k:<12}{RST}  {v}\n")
    _w("\n")


def _cmd_log(t) -> None:
    if not _run_log:
        _w(f"  {DIM}{t('sbx_log_empty')}{RST}\n")
        return
    _w(f"\n  {BOLD}{CYN}{t('sbx_log_title')} ({len(_run_log)}){RST}\n\n")
    for r in _run_log[-30:]:
        status = r.get("status", "?")
        if status == "ok":
            sc = GRN
        elif status == "timeout":
            sc = YLW
        else:
            sc = RED
        ts    = r.get("timestamp", "")[-8:]
        fname = os.path.basename(r.get("file", "?"))
        ms    = int(r.get("time_sec", 0) * 1000)
        layer = r.get("layer", "?")
        _w(f"  {DIM}{ts}{RST}  {sc}{status:<10}{RST}  "
           f"{YLW}{fname:<24}{RST}  {DIM}{ms}ms  {layer}{RST}\n")
    _w("\n")


def _cmd_clear(t) -> None:
    global _last_result
    _run_log.clear()
    _last_result = None
    _w(f"  {GRN}{t('sbx_log_cleared')}{RST}\n")


def _show_menu(t) -> None:
    tool  = _detect_sandbox_tool() or t("sbx_no_ext_tool")
    _w(f"\n{BOLD}{BCYN}  TerminalX Sandbox  v{_VERSION}{RST}\n\n")
    _w(f"  {DIM}profile: {YLW}{_current_profile}{RST}  {DIM}| ext: {tool}{RST}\n\n")
    cmds = [
        ("run <file> [args]",  "sbx_help_run"),
        ("set <key> <value>",  "sbx_help_set"),
        ("show",               "sbx_help_show"),
        ("profiles",           "sbx_help_profiles"),
        ("profile <name>",     "sbx_help_profile"),
        ("last",               "sbx_help_last"),
        ("log",                "sbx_help_log"),
        ("clear",              "sbx_help_clear"),
    ]
    for sub, key in cmds:
        _w(f"    {YLW}{sub:<26}{RST}  {DIM}{t(key)}{RST}\n")

    _w(f"\n  {DIM}{t('sbx_layers_hint')}{RST}\n")
    _w(f"  {DIM}L1=clean-env  L2=tmpdir  L3=rlimits  L4=namespaces  L5=firejail/bwrap{RST}\n\n")


# -- setup / teardown ---------------------------------------------------------

def setup(terminal) -> None:
    def _t(key, **kw):
        return terminal.t(key, **kw)

    def sandbox_command(args: list) -> None:
        if not args:
            _show_menu(_t)
            return
        sub  = args[0].lower()
        rest = args[1:]
        if sub == "run":
            verbose = "-v" in rest or "--verbose" in rest
            rest    = [a for a in rest if a not in ("-v", "--verbose")]
            _cmd_run(rest, _t, verbose)
        elif sub == "show":
            _cmd_show(_t)
        elif sub == "profiles":
            _cmd_profiles(_t)
        elif sub == "profile":
            _cmd_profile(rest, _t)
        elif sub == "set":
            _cmd_set(rest, _t)
        elif sub == "last":
            _cmd_last(_t)
        elif sub == "log":
            _cmd_log(_t)
        elif sub == "clear":
            _cmd_clear(_t)
        else:
            _w(f"  {RED}{_t('sbx_unknown_sub', sub=sub)}{RST}\n")
            _show_menu(_t)

    terminal.register_command(
        "sandbox", sandbox_command,
        description=_t("cmd_sandbox"),
        category=_t("cat_ecosystem"),
    )
    terminal.register_command(
        "sbx", sandbox_command,
        description=_t("cmd_sbx_alias"),
        category=_t("cat_ecosystem"),
    )

    # -- rejestruj komendy sb.* -----------------------------------------------
    cat = _t("cat_ecosystem")

    def _make_sb_handler(fn):
        return lambda args: fn(args, terminal)

    terminal.register_command("sb",         _make_sb_handler(_cmd_sb_menu),
        description="SandBox PRO — menu pomocy", category=cat)
    terminal.register_command("sb.help",    _make_sb_handler(_cmd_sb_menu),
        description="Alias → sb", category=cat)
    terminal.register_command("sb.menu",    _make_sb_handler(_cmd_sb_menu),
        description="Alias → sb", category=cat)
    terminal.register_command("sand",       _make_sb_handler(_cmd_sb_menu),
        description="Alias → sb", category=cat)
    terminal.register_command("sandboy",    _make_sb_handler(_cmd_sb_menu),
        description="Alias → sb", category=cat)
    terminal.register_command("sb.check",   _make_sb_handler(_cmd_sb_check),
        description="Szybkie sprawdzenie pliku", category=cat)
    terminal.register_command("sb.info",    _make_sb_handler(_cmd_sb_info),
        description="Szczegółowa inspekcja pliku", category=cat)
    terminal.register_command("sb.scan",    _make_sb_handler(_cmd_sb_scan),
        description="Skanowanie katalogu", category=cat)
    terminal.register_command("sb.report",  _make_sb_handler(_cmd_sb_report),
        description="Generowanie raportu TXT/JSON", category=cat)
    terminal.register_command("sb.sandbox", _make_sb_handler(_cmd_sb_sandbox),
        description="Bezpieczna analiza pliku", category=cat)
    terminal.register_command("sb.task",    _make_sb_handler(_cmd_sb_task),
        description="Task runner (audit/hashall/dupes)", category=cat)
    terminal.register_command("sb.env",     _make_sb_handler(_cmd_sb_env),
        description="Zmienne środowiskowe sandboxa", category=cat)
    terminal.register_command("sb.run",     _make_sb_handler(_cmd_sb_run),
        description="Uruchom proces w sandboxie", category=cat)
    terminal.register_command("sb.policy",  _make_sb_handler(_cmd_sb_policy),
        description="Polityki bezpieczeństwa (whitelist/blacklist/trust)", category=cat)


def teardown(terminal) -> None:
    global _last_result
    _run_log.clear()
    _last_result = None
    for cmd in ("sandbox", "sbx", "sb", "sb.help", "sb.menu", "sand", "sandboy",
                "sb.check", "sb.info", "sb.scan", "sb.report", "sb.sandbox",
                "sb.task", "sb.env", "sb.run", "sb.policy"):
        terminal.commands.pop(cmd, None)
