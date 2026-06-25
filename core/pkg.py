"""Package manager module for TerminalX EcoSystem.

Alternatywa dla winget - pobieranie, instalacja i zarzadzanie pakietami
z sieci bezposrednio z poziomu terminala.

Obslugiwane zrodla:
  pip       - pakiety Python (PyPI)
  npm       - pakiety Node.js (npmjs.com)
  gh        - release binaries z GitHub
  url       - dowolny bezposredni URL (zip / exe / msi / tar.gz)

Katalog instalacji:
  <root>/tools/         - pliki binarne / exe
  <root>/libs/          - biblioteki (pip / npm)
  <root>/.cache/pkg/    - metadane, historia, cache

polsoft.ITS Group  *  Sebastian Januchowski
Module: Pkg  v1.0.0
"""

import os
import sys
import re as _re
import json
import time
import shutil
import hashlib
import zipfile
import tarfile
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional
from . import _integration

# -- paths ---------------------------------------------------------------------

from ._shared import ROOT_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad
TOOLS_DIR = os.path.join(ROOT_DIR, "tools")
LIBS_DIR  = os.path.join(ROOT_DIR, "libs")
CACHE_DIR = os.path.join(ROOT_DIR, ".cache", "pkg")
DB_FILE   = os.path.join(CACHE_DIR, "installed.json")
HIST_FILE = os.path.join(CACHE_DIR, "history.json")
TMP_DIR   = os.path.join(CACHE_DIR, "tmp")

# -- ANSI ----------------------------------------------------------------------


_ansi = _re.compile(r'\x1b\[[0-9;]*[mA-Z]')

# -- ensure dirs ---------------------------------------------------------------

def _ensure_dirs():
    for d in (TOOLS_DIR, LIBS_DIR, CACHE_DIR, TMP_DIR):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(DB_FILE):
        _write_db({})
    if not os.path.exists(HIST_FILE):
        _write_hist([])

# -- DB helpers ----------------------------------------------------------------

def _read_db() -> dict:
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _write_db(data: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _read_hist() -> list:
    try:
        with open(HIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _write_hist(data: list):
    with open(HIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _hist_add(action: str, name: str, version: str = "", source: str = "", note: str = ""):
    hist = _read_hist()
    hist.append({
        "action":  action,
        "name":    name,
        "version": version,
        "source":  source,
        "note":    note,
        "ts":      time.time(),
    })
    _write_hist(hist[-500:])   # keep last 500 entries

# -- human helpers -------------------------------------------------------------

def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

def _human_age(ts: float) -> str:
    age = time.time() - ts
    if age < 60:    return f"{int(age)}s"
    if age < 3600:  return f"{int(age//60)}m"
    if age < 86400: return f"{int(age//3600)}h"
    return f"{int(age//86400)}d"

def _sha256(path: str) -> str:
    """Oblicz SHA-256 pliku; deleguje do sha256 modułu przez _integration."""
    result = _integration.compute_sha256(path)
    return result or ""

# -- progress bar --------------------------------------------------------------

def _progress(downloaded: int, total: int, width: int = 36):
    if total <= 0:
        filled = 0
        pct = "?%"
    else:
        ratio  = min(downloaded / total, 1.0)
        filled = int(width * ratio)
        pct    = f"{ratio*100:.1f}%"
    bar = GRN + "#" * filled + DIM + "." * (width - filled) + RST
    dl  = _human_size(downloaded)
    tot = _human_size(total) if total > 0 else "?"
    _w(f"\r  [{bar}] {YLW}{pct:>6}{RST}  {DIM}{dl} / {tot}{RST}  ")

# -- download engine -----------------------------------------------------------

class _DownloadError(Exception):
    pass

def _download(url: str, dest: str, label: str = "") -> str:
    """Pobiera URL do pliku dest. Zwraca sciezke do pobranego pliku."""
    _w(f"\n  {BLU}?{RST}  {DIM}{label or url}{RST}\n")
    headers = {"User-Agent": "TerminalX/1.0 (polsoft.ITS; +https://github.com/polsoft-its)"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    _progress(downloaded, total)
    except urllib.error.HTTPError as e:
        raise _DownloadError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise _DownloadError(f"URL error: {e.reason}")
    _w(f"\n  {GRN}[V]{RST}  {_human_size(os.path.getsize(dest))}\n")
    return dest

# -- source drivers ------------------------------------------------------------

def _install_pip(name: str, version: str = "", _t=None) -> bool:
    """Instaluje pakiet pip do libs/ (--target)."""
    pkg = f"{name}=={version}" if version else name
    dest = os.path.join(LIBS_DIR, "pip")
    os.makedirs(dest, exist_ok=True)
    _w(f"\n  {CYN}pip install{RST} {YLW}{pkg}{RST}  ->  {DIM}{dest}{RST}\n\n")
    cmd = [sys.executable, "-m", "pip", "install", pkg, "--target", dest, "--quiet"]
    try:
        proc = subprocess.run(cmd, capture_output=False, text=True)
        if proc.returncode != 0:
            _w(f"\n  {RED}{_t('pkg_pip_fail', pkg=pkg)}{RST}\n")
            return False
    except FileNotFoundError:
        _w(f"\n  {RED}{_t('pkg_pip_not_found')}{RST}\n")
        return False
    _w(f"\n  {GRN}{_t('pkg_installed', name=pkg)}{RST}\n")
    return True


def _install_npm(name: str, version: str = "", _t=None) -> bool:
    """Instaluje pakiet npm do libs/npm."""
    pkg = f"{name}@{version}" if version else name
    dest = os.path.join(LIBS_DIR, "npm")
    os.makedirs(dest, exist_ok=True)
    _w(f"\n  {CYN}npm install{RST} {YLW}{pkg}{RST}  ->  {DIM}{dest}{RST}\n\n")
    npm_bin = shutil.which("npm")
    if not npm_bin:
        _w(f"\n  {RED}{_t('pkg_npm_not_found')}{RST}\n")
        return False
    cmd = [npm_bin, "install", pkg, "--prefix", dest]
    try:
        proc = subprocess.run(cmd, capture_output=False, text=True)
        if proc.returncode != 0:
            _w(f"\n  {RED}{_t('pkg_npm_fail', pkg=pkg)}{RST}\n")
            return False
    except Exception as exc:
        _w(f"\n  {RED}{exc}{RST}\n")
        return False
    _w(f"\n  {GRN}{_t('pkg_installed', name=pkg)}{RST}\n")
    return True


def _install_gh(repo: str, tag: str = "", pattern: str = "", _t=None) -> bool:
    """
    Pobiera binary release z GitHub.
    repo  - "owner/repo"
    tag   - "v1.2.3" lub "" (latest)
    pattern - fragment nazwy assetu do dopasowania (np. "win64.zip")
    """
    if "/" not in repo:
        _w(f"\n  {RED}{_t('pkg_gh_bad_repo')}{RST}\n")
        return False

    # resolve release API
    if tag:
        api = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    else:
        api = f"https://api.github.com/repos/{repo}/releases/latest"

    _w(f"\n  {CYN}GitHub:{RST} {YLW}{repo}{RST}  {DIM}({tag or 'latest'}){RST}\n")
    try:
        req = urllib.request.Request(
            api,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "TerminalX/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read().decode())
    except Exception as exc:
        _w(f"\n  {RED}{_t('pkg_gh_api_fail', exc=exc)}{RST}\n")
        return False

    assets = release.get("assets", [])
    if not assets:
        _w(f"\n  {RED}{_t('pkg_gh_no_assets')}{RST}\n")
        return False

    # pick asset
    chosen = None
    for a in assets:
        if pattern and pattern.lower() in a["name"].lower():
            chosen = a
            break
    if not chosen:
        # interaktywny wybor
        _w(f"\n  {BOLD}{_t('pkg_gh_pick_asset')}{RST}\n\n")
        for i, a in enumerate(assets, 1):
            sz = _human_size(a.get("size", 0))
            _w(f"    {YLW}[{i}]{RST} {_pad(a['name'], 40)}{DIM}{sz}{RST}\n")
        _w("\n")
        try:
            choice = input(f"  {CYN}> {RST}").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(assets):
                chosen = assets[idx]
            else:
                _w(f"  {RED}{_t('pkg_invalid_choice')}{RST}\n")
                return False
        except (ValueError, EOFError):
            _w(f"  {RED}{_t('pkg_invalid_choice')}{RST}\n")
            return False

    url  = chosen["browser_download_url"]
    name = chosen["name"]
    tmp  = os.path.join(TMP_DIR, name)
    try:
        _download(url, tmp, label=name)
    except _DownloadError as e:
        _w(f"\n  {RED}{e}{RST}\n")
        return False

    # extract or move
    dest_name = _extract_or_place(tmp, name, _t=_t)
    if not dest_name:
        return False

    tag_actual = release.get("tag_name", tag or "?")
    _w(f"\n  {GRN}{_t('pkg_installed', name=f'{repo}  {tag_actual}')}{RST}\n")
    return True, tag_actual, name


def _install_url(url: str, filename: str = "", _t=None) -> bool:
    """Pobiera dowolny URL i instaluje."""
    filename = filename or os.path.basename(urllib.parse.urlparse(url).path) or "package"
    tmp = os.path.join(TMP_DIR, filename)
    try:
        _download(url, tmp, label=filename)
    except _DownloadError as e:
        _w(f"\n  {RED}{e}{RST}\n")
        return False
    return bool(_extract_or_place(tmp, filename, _t=_t))


def _extract_or_place(src: str, name: str, _t=None) -> Optional[str]:
    """
    Rozpakowuje archiwum do tools/ lub umieszcza plik bezposrednio.
    Zwraca docelowa nazwe lub None przy bledzie.
    """
    ext = name.lower()
    if ext.endswith(".zip"):
        _w(f"  {DIM}{_t('pkg_extracting')}{RST}\n")
        dest_dir = os.path.join(TOOLS_DIR, os.path.splitext(name)[0])
        os.makedirs(dest_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(src) as zf:
                zf.extractall(dest_dir)
        except zipfile.BadZipFile as exc:
            _w(f"\n  {RED}{_t('pkg_extract_fail', exc=exc)}{RST}\n")
            return None
        _w(f"  {GRN}->  {DIM}{dest_dir}{RST}\n")
        os.remove(src)
        return dest_dir

    elif ext.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
        _w(f"  {DIM}{_t('pkg_extracting')}{RST}\n")
        dest_dir = os.path.join(TOOLS_DIR, name.split(".tar")[0])
        os.makedirs(dest_dir, exist_ok=True)
        try:
            with tarfile.open(src) as tf:
                tf.extractall(dest_dir)
        except Exception as exc:
            _w(f"\n  {RED}{_t('pkg_extract_fail', exc=exc)}{RST}\n")
            return None
        _w(f"  {GRN}->  {DIM}{dest_dir}{RST}\n")
        os.remove(src)
        return dest_dir

    else:
        # exe / msi / single file - kopiuj do tools/
        dest = os.path.join(TOOLS_DIR, name)
        shutil.move(src, dest)
        _w(f"  {GRN}->  {DIM}{dest}{RST}\n")
        return dest

# -- command handlers ----------------------------------------------------------

def _parse_flags(args: list) -> dict:
    """
    Parsuje flage --version/-v, --pattern/-p, --file/-f, --source/-s.
    Zwraca dict z kluczami: version, pattern, filename, source, positional[].
    """
    result = {"version": "", "pattern": "", "filename": "", "source": "", "pos": []}
    flag_map = {
        "--version": "version", "-v": "version",
        "--pattern": "pattern", "-p": "pattern",
        "--file":    "filename", "-": "filename",
        "--source":  "source",  "-s": "source",
    }
    i = 0
    while i < len(args):
        a = args[i]
        if a in flag_map:
            key = flag_map[a]
            i += 1
            if i < len(args):
                result[key] = args[i]
        else:
            result["pos"].append(a)
        i += 1
    return result


def _cmd_install_libs(_t) -> None:
    """Wyszukaj requirements.txt w libs/ i zainstaluj wszystkie aktywne pakiety."""
    req_path = os.path.join(LIBS_DIR, "requirements.txt")

    if not os.path.isfile(req_path):
        _w(f"\n  {RED}{_t('pkg_libs_req_not_found', path=req_path)}{RST}\n\n")
        return

    _w(f"\n  {BOLD}{CYN}{_t('pkg_libs_reading', path=req_path)}{RST}\n\n")

    packages: list[str] = []
    with open(req_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            pkg = line.split("#")[0].strip()
            if pkg:
                packages.append(pkg)

    if not packages:
        _w(f"  {YLW}{_t('pkg_libs_no_packages')}{RST}\n\n")
        return

    _w(f"  {DIM}{_t('pkg_libs_found', n=len(packages))}{RST}\n\n")
    for p in packages:
        _w(f"    {DIM}{p}{RST}\n")
    _w("\n")

    _ensure_dirs()
    dest    = os.path.join(LIBS_DIR, "pip")
    ok_cnt  = 0
    err_cnt = 0

    for pkg in packages:
        _w(f"  {CYN}pip install{RST} {YLW}{pkg}{RST}  ->  {DIM}{dest}{RST}\n")
        cmd = [sys.executable, "-m", "pip", "install", pkg, "--target", dest, "--quiet"]
        try:
            proc = subprocess.run(cmd, capture_output=False, text=True)
            if proc.returncode == 0:
                _w(f"  {GRN}{_t('pkg_libs_ok', pkg=pkg)}{RST}\n\n")
                ok_cnt += 1
            else:
                _w(f"  {RED}{_t('pkg_libs_fail', pkg=pkg)}{RST}\n\n")
                err_cnt += 1
        except FileNotFoundError:
            _w(f"  {RED}{_t('pkg_pip_not_found')}{RST}\n\n")
            err_cnt += 1
            break

    if err_cnt == 0:
        _w(f"  {GRN}{BOLD}{_t('pkg_libs_done', ok=ok_cnt, fail=err_cnt)}{RST}\n\n")
        _integration.notify_event(
            None, f"Biblioteki: {ok_cnt} zainstalowano, 0 bledow.",
            kind="ok", title="PKG",
        )
    else:
        _w(f"  {YLW}{BOLD}{_t('pkg_libs_done', ok=ok_cnt, fail=err_cnt)}{RST}\n\n")
        _integration.notify_event(
            None, f"Biblioteki: {ok_cnt} zainstalowano, {err_cnt} bledow.",
            kind="warn", title="PKG",
        )


def _cmd_install(args, _t):
    """pkg install <source> <name> [opcje]"""
    if not args:
        _w(f"\n  {RED}{_t('pkg_install_usage')}{RST}\n"); return

    cfg = _parse_flags(args)
    pos = cfg["pos"]

    if len(pos) < 2:
        _w(f"\n  {RED}{_t('pkg_install_usage')}{RST}\n"); return

    source = pos[0].lower()
    name   = pos[1]
    ver    = cfg["version"]
    pat    = cfg["pattern"]
    fname  = cfg["filename"]

    _ensure_dirs()
    db = _read_db()

    ok      = False
    version = ver or "?"
    src_tag = source

    if source == "libs":
        # `pkg install libs` -> install from requirements.txt
        _cmd_install_libs(_t)
        return

    elif source == "pip":
        ok = _install_pip(name, ver, _t=_t)
        src_tag = "pip"

    elif source == "npm":
        ok = _install_npm(name, ver, _t=_t)
        src_tag = "npm"

    elif source == "gh":
        result = _install_gh(name, ver, pat, _t=_t)
        if isinstance(result, tuple):
            ok, version, _ = result
        else:
            ok = result
        src_tag = "github"

    elif source == "url":
        ok = _install_url(name, fname, _t=_t)
        src_tag = "url"

    else:
        _w(f"\n  {RED}{_t('pkg_unknown_source', src=source)}{RST}\n")
        _w(f"  {DIM}{_t('pkg_sources_available')}{RST}\n")
        return

    if ok:
        db[f"{source}:{name}"] = {
            "name":      name,
            "version":   version,
            "source":    src_tag,
            "installed": time.time(),
        }
        _write_db(db)
        _hist_add("install", name, version, src_tag)
        _integration.notify_event(
            None, f"Zainstalowano: {name} ({src_tag}{' ' + version if version != '?' else ''})",
            kind="ok", title="PKG",
        )
        # Poinformuj venv o nowo zainstalowanym pakiecie pip
        if src_tag == "pip":
            _integration.venv_register_installed(name, version, "ecosystem")
    else:
        _integration.notify_event(
            None, f"Instalacja nieudana: {name} ({src_tag})",
            kind="err", title="PKG",
        )


def _cmd_remove(args, _t):
    """pkg remove <source> <name>"""
    if len(args) < 2:
        _w(f"\n  {RED}{_t('pkg_remove_usage')}{RST}\n"); return

    source, name = args[0].lower(), args[1]
    db_key = f"{source}:{name}"
    db = _read_db()

    if db_key not in db:
        _w(f"\n  {YLW}{_t('pkg_not_installed', name=name)}{RST}\n")
        return

    if source == "pip":
        _w(f"\n  {CYN}pip uninstall{RST} {YLW}{name}{RST}\n\n")
        cmd = [sys.executable, "-m", "pip", "uninstall", name, "-y"]
        subprocess.run(cmd, text=True, encoding="utf-8")

    elif source == "npm":
        npm_bin = shutil.which("npm")
        if npm_bin:
            dest = os.path.join(LIBS_DIR, "npm")
            _w(f"\n  {CYN}npm uninstall{RST} {YLW}{name}{RST}\n\n")
            subprocess.run([npm_bin, "uninstall", name, "--prefix", dest], text=True, encoding="utf-8")

    else:
        # gh / url - usun folder z tools/
        candidate = os.path.join(TOOLS_DIR, os.path.splitext(name)[0] if '.' in name else name)
        if os.path.isdir(candidate):
            shutil.rmtree(candidate)
            _w(f"  {GRN}{_t('pkg_removed_dir', path=candidate)}{RST}\n")
        elif os.path.isfile(candidate):
            os.remove(candidate)
            _w(f"  {GRN}{_t('pkg_removed_file', path=candidate)}{RST}\n")
        else:
            _w(f"  {YLW}{_t('pkg_remove_manual', name=name)}{RST}\n")

    del db[db_key]
    _write_db(db)
    _hist_add("remove", name, source=source)
    _w(f"  {GRN}{_t('pkg_removed', name=name)}{RST}\n")
    _integration.notify_event(
        None, f"Odinstalowano: {name} ({source})", kind="ok", title="PKG",
    )


def _cmd_list(args, _t):
    """pkg list [source]"""
    _ensure_dirs()
    db = _read_db()
    if not db:
        _w(f"\n  {DIM}{_t('pkg_list_empty')}{RST}\n\n"); return

    filter_src = args[0].lower() if args else ""
    rows = [(k, v) for k, v in db.items()
            if not filter_src or v.get("source", "") == filter_src]
    rows.sort(key=lambda x: x[1].get("installed", 0), reverse=True)

    _w(f"\n{BOLD}  {_pad('PAKIET', 28)}{_pad('WERSJA', 14)}{_pad('ZRODLO', 10)}{'ZAINSTALOWANY'}{RST}\n")
    _w(f"  {'-'*68}\n")
    for key, entry in rows:
        n   = entry.get("name",    key)
        ver = entry.get("version", "?")
        src = entry.get("source",  "?")
        age = _human_age(entry.get("installed", time.time()))
        src_color = {"pip": GRN, "npm": YLW, "github": BLU, "url": MGT}.get(src, DIM)
        _w(f"  {YLW}{_pad(n, 28)}{RST}{_pad(ver, 14)}{src_color}{_pad(src, 10)}{RST}{DIM}{age} temu{RST}\n")
    _w(f"\n  {DIM}{_t('pkg_list_total', n=len(rows))}{RST}\n\n")


def _cmd_info(args, _t):
    """pkg info <source> <name>"""
    if len(args) < 2:
        _w(f"\n  {RED}{_t('pkg_info_usage')}{RST}\n"); return
    source, name = args[0].lower(), args[1]
    db_key = f"{source}:{name}"
    db = _read_db()
    if db_key not in db:
        _w(f"\n  {YLW}{_t('pkg_not_installed', name=name)}{RST}\n"); return
    e = db[db_key]
    _w(f"\n{BOLD}  {name}{RST}\n  {'-'*40}\n")
    for k, v in [
        (_t('pkg_field_source'),    e.get("source",    "?")),
        (_t('pkg_field_version'),   e.get("version",   "?")),
        (_t('pkg_field_installed'), time.strftime("%Y-%m-%d %H:%M",
                                    time.localtime(e.get("installed", 0)))),
    ]:
        _w(f"  {CYN}{_pad(k+':', 16)}{RST}{v}\n")
    _w("\n")


def _cmd_search_pkg(args, _t):
    """pkg search <source> <query>  - wyszukuje w rejestrze danego zrodla."""
    if len(args) < 2:
        _w(f"\n  {RED}{_t('pkg_search_usage')}{RST}\n"); return

    source = args[0].lower()
    query  = args[1]

    if source == "pip":
        _w(f"\n  {CYN}PyPI:{RST} https://pypi.org/pypi/{query}/json\n")
        try:
            url = f"https://pypi.org/pypi/{urllib.parse.quote(query)}/json"
            req = urllib.request.Request(url, headers={"User-Agent": "TerminalX/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            info = data.get("info", {})
            _w(f"\n  {BOLD}{YLW}{info.get('name', query)}{RST}  {DIM}v{info.get('version', '?')}{RST}\n")
            summary = info.get("summary", "")
            if summary:
                _w(f"  {summary}\n")
            _w(f"\n  {DIM}Autor:    {info.get('author', '?')}\n")
            _w(f"  Licencja: {info.get('license', '?')}\n")
            _w(f"  PyPI:     {info.get('project_url', info.get('package_url',''))}{RST}\n\n")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                _w(f"\n  {RED}{_t('pkg_not_found_pypi', name=query)}{RST}\n\n")
            else:
                _w(f"\n  {RED}HTTP {e.code}{RST}\n\n")
        except Exception as exc:
            _w(f"\n  {RED}{exc}{RST}\n\n")

    elif source == "gh":
        _w(f"\n  {CYN}GitHub API:{RST} repos/{query}\n")
        try:
            url = f"https://api.github.com/repos/{urllib.parse.quote(query, safe='/')}"
            req = urllib.request.Request(url, headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "TerminalX/1.0",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            _w(f"\n  {BOLD}{YLW}{data.get('full_name', query)}{RST}\n")
            _w(f"  {data.get('description', '')}\n")
            _w(f"\n  {DIM}?  {data.get('stargazers_count', 0):,}  "
               f"|  {data.get('language', '?')}  "
               f"|  {data.get('license', {}).get('spdx_id', '?')}\n")
            _w(f"  URL:  {data.get('html_url', '')}{RST}\n\n")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                _w(f"\n  {RED}{_t('pkg_not_found_gh', name=query)}{RST}\n\n")
            else:
                _w(f"\n  {RED}HTTP {e.code}{RST}\n\n")
        except Exception as exc:
            _w(f"\n  {RED}{exc}{RST}\n\n")

    else:
        _w(f"\n  {YLW}{_t('pkg_search_sources')}{RST}\n\n")


def _cmd_upgrade(args, _t):
    """pkg upgrade pip <name>  -  aktualizacja pakietu pip."""
    if len(args) < 2:
        _w(f"\n  {RED}{_t('pkg_upgrade_usage')}{RST}\n"); return
    source, name = args[0].lower(), args[1]
    if source != "pip":
        _w(f"\n  {YLW}{_t('pkg_upgrade_pip_only')}{RST}\n"); return
    _w(f"\n  {CYN}pip install --upgrade{RST} {YLW}{name}{RST}\n\n")
    dest = os.path.join(LIBS_DIR, "pip")
    os.makedirs(dest, exist_ok=True)
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", name,
           "--target", dest, "--quiet"]
    proc = subprocess.run(cmd, text=True, encoding="utf-8")
    if proc.returncode == 0:
        db = _read_db()
        key = f"pip:{name}"
        if key in db:
            db[key]["version"] = "latest"
            _write_db(db)
        _hist_add("upgrade", name, source="pip")
        _w(f"\n  {GRN}{_t('pkg_upgraded', name=name)}{RST}\n")
    else:
        _w(f"\n  {RED}{_t('pkg_upgrade_fail', name=name)}{RST}\n")


def _cmd_history(args, _t):
    """pkg history [n]"""
    hist = _read_hist()
    if not hist:
        _w(f"\n  {DIM}{_t('pkg_history_empty')}{RST}\n\n"); return
    try:
        limit = int(args[0]) if args else 20
    except ValueError:
        limit = 20
    rows = hist[-limit:][::-1]
    _w(f"\n{BOLD}  {_pad('AKCJA', 12)}{_pad('PAKIET', 28)}{_pad('WERSJA', 14)}{'KIEDY'}{RST}\n")
    _w(f"  {'-'*64}\n")
    for r in rows:
        action = r.get("action", "?")
        col = {
            "install":  GRN,
            "remove":   RED,
            "upgrade":  YLW,
        }.get(action, DIM)
        _w(f"  {col}{_pad(action, 12)}{RST}"
           f"{YLW}{_pad(r.get('name',''), 28)}{RST}"
           f"{_pad(r.get('version','?'), 14)}"
           f"{DIM}{_human_age(r.get('ts', time.time()))} temu{RST}\n")
    _w("\n")


def _cmd_check(args, _t):
    """pkg check - sprawdza dostepnosc pip i npm."""
    _w(f"\n  {BOLD}{_t('pkg_check_header')}{RST}\n\n")
    checks = [
        ("Python / pip", sys.executable, [sys.executable, "-m", "pip", "--version"]),
        ("npm",          shutil.which("npm") or "-", ["npm", "--version"] if shutil.which("npm") else None),
        ("curl (optional)", shutil.which("curl") or "-", None),
        ("git  (optional)", shutil.which("git")  or "-", None),
    ]
    for label, path, cmd in checks:
        ver = ""
        if cmd:
            try:
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip().split("\n")[0]
                ver = f"  {DIM}{out[:60]}{RST}"
                status = GRN + "[V]" + RST
            except Exception:
                status = RED + "[X]" + RST
        else:
            status = GRN + "[V]" + RST if path != "-" else YLW + "-" + RST
        _w(f"  [{status}]  {_pad(label, 20)}{DIM}{path}{RST}{ver}\n")
    _w("\n")

# -- update all ---------------------------------------------------------------

def _cmd_update_all(_t) -> None:
    """Aktualizuje zainstalowane pakiety pip z zachowaniem zgodnosci zaleznosci."""
    _w(f"\n  {BOLD}{CYN}{_t('pkg_update_header')}{RST}\n\n")

    # -- pobierz liste przestarzalych pakietow ---------------------------------
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
            capture_output=True, text=True,
        )
        outdated = json.loads(result.stdout) if result.stdout.strip() else []
    except Exception as exc:
        _w(f"  {RED}{exc}{RST}\n\n")
        return

    if not outdated:
        _w(f"  {GRN}{_t('pkg_update_no_pkgs')}{RST}\n\n")
        return

    _w(f"  {DIM}{_t('pkg_libs_found', n=len(outdated))}{RST}\n\n")

    dest     = os.path.join(LIBS_DIR, "pip")
    os.makedirs(dest, exist_ok=True)
    ok_cnt   = 0
    err_cnt  = 0
    skip_cnt = 0

    for entry in outdated:
        pkg     = entry.get("name", "")
        ver_old = entry.get("version", "?")
        ver_new = entry.get("latest_version", "?")
        if not pkg:
            continue

        _w(f"  {CYN}pip install --upgrade{RST} {YLW}{pkg}{RST}"
           f"  {DIM}{ver_old} -> {ver_new}{RST}  ->  {DIM}{dest}{RST}\n")

        cmd = [
            sys.executable, "-m", "pip", "install", "--upgrade",
            "--upgrade-strategy", "only-if-needed",
            pkg, "--target", dest, "--quiet",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            stderr_low = proc.stderr.lower()

            if proc.returncode == 0 and "incompatible" not in stderr_low and "conflict" not in stderr_low:
                _w(f"  {GRN}{_t('pkg_update_ok', pkg=pkg)}{RST}\n\n")
                ok_cnt += 1
            elif "incompatible" in stderr_low or "conflict" in stderr_low:
                conflict_line = next(
                    (l.strip() for l in proc.stderr.splitlines()
                     if "incompatible" in l.lower() or "conflict" in l.lower()),
                    proc.stderr.strip()[:120],
                )
                _w(f"  {YLW}[!] {pkg}  {DIM}{conflict_line}{RST}\n\n")
                skip_cnt += 1
            else:
                _w(f"  {RED}{_t('pkg_update_fail', pkg=pkg)}{RST}\n\n")
                err_cnt += 1

        except FileNotFoundError:
            _w(f"  {RED}{_t('pkg_pip_not_found')}{RST}\n\n")
            err_cnt += 1
            break

    # -- podsumowanie ----------------------------------------------------------
    parts = []
    if ok_cnt:   parts.append(f"{GRN}{ok_cnt} ok{RST}")
    if skip_cnt: parts.append(f"{YLW}{skip_cnt} pominieto (konflikt){RST}")
    if err_cnt:  parts.append(f"{RED}{err_cnt} bledow{RST}")
    summary = ",  ".join(parts) if parts else f"{DIM}brak zmian{RST}"
    _w(f"  {BOLD}{summary}{RST}\n\n")

    notify_kind = "ok" if err_cnt == 0 else "warn"
    _integration.notify_event(
        None,
        f"Update: {ok_cnt} zaktualizowano, {skip_cnt} pominieto, {err_cnt} bledow.",
        kind=notify_kind, title="PKG",
    )


# -- menu ----------------------------------------------------------------------

def _pkg_menu(_t):
    _w(f"\n{BOLD}{CYN}  +==========================================+{RST}\n")
    _w(f"{BOLD}{CYN}  |  ?  {_t('pkg_module_title'):<36}|{RST}\n")
    _w(f"{BOLD}{CYN}  +==========================================+{RST}\n\n")

    sections = [
        (_t("pkg_section_install"), [
            ("pkg install pip <name>",           _t("pkg_help_install_pip")),
            ("pkg install npm <name>",           _t("pkg_help_install_npm")),
            ("pkg install gh <owner/repo>",      _t("pkg_help_install_gh")),
            ("pkg install url <url>",            _t("pkg_help_install_url")),
        ]),
        (_t("pkg_section_manage"), [
            ("pkg list [source]",                _t("pkg_help_list")),
            ("pkg info <source> <name>",         _t("pkg_help_info")),
            ("pkg remove <source> <name>",       _t("pkg_help_remove")),
            ("pkg upgrade pip <name>",           _t("pkg_help_upgrade")),
        ]),
        (_t("pkg_section_discover"), [
            ("pkg search pip <name>",            _t("pkg_help_search_pip")),
            ("pkg search gh <owner/repo>",       _t("pkg_help_search_gh")),
        ]),
        (_t("pkg_section_other"), [
            ("pkg install libs",                 _t("cmd_install_libs")),
            ("pkg update libs",                  _t("cmd_update_libs")),
            ("pkg history [n]",                  _t("pkg_help_history")),
            ("pkg check",                        _t("pkg_help_check")),
        ]),
    ]

    for section_title, cmds in sections:
        _w(f"  {BOLD}{BLU}{section_title}{RST}\n")
        for c, d in cmds:
            _w(f"    {YLW}{_pad(c, 32)}{RST} {DIM}{d}{RST}\n")
        _w("\n")

    _w(f"  {DIM}{_t('pkg_flags_hint')}{RST}\n")
    _w(f"  {DIM}  --version/-v <ver>   --pattern/-p <pat>   --file/-f <fname>{RST}\n\n")

# -- setup / teardown ----------------------------------------------------------

def setup(terminal):
    _ensure_dirs()


    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("pkg", {
            "read_db": _read_db,
            "hist_add": _hist_add,
        })
    except Exception:
        pass
    def _t(key, **kw):
        return terminal.t(key, **kw)

    _SUBS = {
        "install": _cmd_install,
        "libs":    lambda a, _t=_t: _cmd_install_libs(_t),
        "remove":  _cmd_remove,
        "rm":      _cmd_remove,
        "list":    _cmd_list,
        "ls":      _cmd_list,
        "info":    _cmd_info,
        "search":  _cmd_search_pkg,
        "upgrade": _cmd_upgrade,
        "up":      _cmd_upgrade,
        "history": _cmd_history,
        "hist":    _cmd_history,
        "check":   _cmd_check,
        "update":  lambda a, _t=_t: (_cmd_update_all(_t) if not a or a[0].lower() == "libs" else _w(f"\n  {RED}{_t('pkg_update_libs_usage')}{RST}\n\n")),
    }

    def pkg_cmd(args):
        if not args:
            _pkg_menu(_t); return
        sub = args[0].lower()
        # "pkg install libs" — intercept przed ogólnym install
        if sub == "install" and len(args) >= 2 and args[1].lower() == "libs":
            _cmd_install_libs(_t)
            return
        if sub in _SUBS:
            _SUBS[sub](args[1:], _t=_t)
        else:
            _w(f"\n  {RED}{_t('pkg_unknown_sub', sub=sub)}{RST}\n")
            _pkg_menu(_t)

    terminal.register_command(
        "pkg", pkg_cmd,
        description=_t("cmd_pkg"),
        category=_t("cat_ecosystem"),
    )

    # -- alias: pip <sub> [args] ------------------------------------------
    # Mapuje popularne komendy pip na pkg, żeby użytkownicy mogli pisać
    # np. "pip install python-barcode" zamiast "pkg install pip python-barcode".
    #
    #   pip install <name> [==ver]   →  pkg install pip <name> [==ver]
    #   pip uninstall <name>         →  pkg remove <name>
    #   pip list                     →  pkg list
    #   pip show <name>              →  pkg info <name>
    #   pip upgrade <name>           →  pkg upgrade pip <name>
    #   pip search <query>           →  pkg search pip <query>
    #   pip check                    →  pkg check
    #   pip history                  →  pkg history
    #   (brak args / inne)           →  pkg menu

    def pip_cmd(args):
        if not args:
            _pkg_menu(_t)
            return
        sub = args[0].lower()
        rest = args[1:]
        if sub in ("install", "i"):
            if not rest:
                _w("\n  \x1b[91m[!] Użycie: pip install <nazwa> [==wersja]\x1b[0m\n\n")
                return
            _cmd_install(["pip"] + rest, _t=_t)
        elif sub in ("uninstall", "remove", "rm"):
            if not rest:
                _w("\n  \x1b[91m[!] Użycie: pip uninstall <nazwa>\x1b[0m\n\n")
                return
            _cmd_remove(rest, _t=_t)
        elif sub in ("list", "ls"):
            _cmd_list(rest, _t=_t)
        elif sub in ("show", "info"):
            if not rest:
                _w("\n  \x1b[91m[!] Użycie: pip show <nazwa>\x1b[0m\n\n")
                return
            _cmd_info(rest, _t=_t)
        elif sub in ("upgrade", "up"):
            if not rest:
                _w("\n  \x1b[91m[!] Użycie: pip upgrade <nazwa>\x1b[0m\n\n")
                return
            _cmd_upgrade(["pip"] + rest, _t=_t)
        elif sub == "search":
            if not rest:
                _w("\n  \x1b[91m[!] Użycie: pip search <fraza>\x1b[0m\n\n")
                return
            _cmd_search_pkg(["pip"] + rest, _t=_t)
        elif sub == "check":
            _cmd_check(rest, _t=_t)
        elif sub in ("history", "hist"):
            _cmd_history(rest, _t=_t)
        else:
            _w(f"\n  \x1b[93m[?] pip: nieznana subkomenda '{sub}'\x1b[0m\n")
            _w("  \x1b[2mDostępne: install | uninstall | list | show | upgrade | search | check | history\x1b[0m\n\n")

    terminal.register_command(
        "pip", pip_cmd,
        description="Alias pip → pkg (install/uninstall/list/show/upgrade/search/check)",
        category=_t("cat_ecosystem"),
    )


def teardown(terminal):
    try:
        from . import _integration as _intg
        _intg.unregister("pkg")
    except Exception:
        pass
    terminal.commands.pop("pkg", None)
    terminal.commands.pop("pip", None)
