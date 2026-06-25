"""Moduł aktualizacji TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski
Module: update  v1.2.0

Ręczna aktualizacja plików terminala z repozytorium GitHub.
Komenda 'update terminal' pobiera listę plików z GitHub API,
porównuje sumy SHA-1 blobów z plikami lokalnymi i pobiera
tylko zmienione lub nowe pliki.

Komendy:
  update terminal              - interaktywny wybór + aktualizacja
  update terminal --check      - tylko sprawdź; nie pobieraj
  update terminal --dry-run    - alias --check
  update terminal --force      - pobierz wszystkie pliki (bez porównania)
  update terminal --list       - pokaż zmiany bez aktualizacji
  update terminal --yes        - pomiń potwierdzenia (tryb nieinteraktywny)
  update rollback              - przywróć pliki .bak
"""

import difflib
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from ._shared import (
    ROOT_DIR, CACHE_DIR,
    RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, WHT,
    _w, _atomic_write,
)
from . import _integration

_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# Konfiguracja repozytorium
# ---------------------------------------------------------------------------

_REPO_OWNER  = "polsoft-seb07uk"
_REPO_NAME   = "TerminalX_EcoSystem"
_REPO_BRANCH = "main"
_API_BASE    = "https://api.github.com"
_RAW_BASE    = "https://raw.githubusercontent.com"
_USER_AGENT  = "TerminalX-polsoft/1.0"

_STATE_FILE  = os.path.join(CACHE_DIR, "global", "update_state.json")

_SKIP_PATHS: frozenset[str] = frozenset({
    ".cache", ".quarantine", ".trash", "key",
    "scripts/logs", "tests/__pycache__",
})

_UPDATE_EXTS: frozenset[str] = frozenset({
    ".py", ".txt", ".md", ".json", ".ini", ".ps1", ".bat", ".html", ".js",
})

# Maksymalna liczba linii diff wyświetlana inline przed truncation
_DIFF_MAX_LINES = 40

# ---------------------------------------------------------------------------
# Helpers sieciowe
# ---------------------------------------------------------------------------

def _gh_request(path: str, token: str | None = None) -> tuple[int, object]:
    url = f"{_API_BASE}{path}"
    headers = {
        "Accept":     "application/vnd.github+json",
        "User-Agent": _USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"message": exc.reason}
        return exc.code, payload
    except urllib.error.URLError as exc:
        return 0, {"message": str(exc.reason)}


def _download_raw(rel_path: str, token: str | None = None) -> bytes | None:
    url = (
        f"{_RAW_BASE}/{_REPO_OWNER}/{_REPO_NAME}/"
        f"{_REPO_BRANCH}/{rel_path.lstrip('/')}"
    )
    headers = {"User-Agent": _USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    _integration.log_debug_event(None, "io", f"[update] download: {rel_path}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception:
        return None

# ---------------------------------------------------------------------------
# GitHub Tree API
# ---------------------------------------------------------------------------

def _fetch_tree(token: str | None = None) -> list[dict] | None:
    path = f"/repos/{_REPO_OWNER}/{_REPO_NAME}/git/trees/{_REPO_BRANCH}?recursive=1"
    _integration.log_debug_event(None, "io",
        f"[update] fetch tree: {_REPO_OWNER}/{_REPO_NAME}@{_REPO_BRANCH}")
    code, data = _gh_request(path, token=token)
    if code != 200 or not isinstance(data, dict):
        return None
    return data.get("tree") or []

# ---------------------------------------------------------------------------
# SHA-1 lokalnego pliku — zgodna z gitowym "blob SHA"
# ---------------------------------------------------------------------------

def _git_sha1(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            content = f.read()
    except OSError:
        return None
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()

# ---------------------------------------------------------------------------
# Filtrowanie drzewa
# ---------------------------------------------------------------------------

def _should_update(entry: dict) -> bool:
    if entry.get("type") != "blob":
        return False
    rel = entry.get("path", "")
    if rel.split("/")[0].startswith("."):
        return False
    for skip in _SKIP_PATHS:
        if rel == skip or rel.startswith(skip + "/"):
            return False
    _, ext = os.path.splitext(rel)
    return ext.lower() in _UPDATE_EXTS

# ---------------------------------------------------------------------------
# Porównanie i wykrywanie zmian
# ---------------------------------------------------------------------------

def _detect_changes(tree: list[dict]) -> tuple[list[dict], list[dict]]:
    changed: list[dict] = []
    new: list[dict] = []
    for entry in tree:
        if not _should_update(entry):
            continue
        rel   = entry["path"]
        local = os.path.join(ROOT_DIR, rel)
        if not os.path.exists(local):
            new.append(entry)
        elif _git_sha1(local) != entry.get("sha", ""):
            changed.append(entry)
    return changed, new

# ---------------------------------------------------------------------------
# Zapis / odczyt stanu
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(data: dict) -> None:
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    _atomic_write(_STATE_FILE, data)

# ---------------------------------------------------------------------------
# Token GitHub
# ---------------------------------------------------------------------------

def _get_github_token() -> str | None:
    return _integration.github_get_token() or None

# ---------------------------------------------------------------------------
# Raw getch — cross-platform (Unix + Windows)
# ---------------------------------------------------------------------------

def _getch() -> str:
    """Odczytaj jeden znak bez echa i bez Enter. Cross-platform."""
    try:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            # obsługa strzałek: ESC [ A/B/C/D
            if ch == "\x1b":
                rest = sys.stdin.read(2)
                ch = ch + rest
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch
    except (ImportError, AttributeError, OSError):
        pass
    try:
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):      # extended key prefix
            msvcrt.getwch()             # discard scan code
            return ""
        return ch
    except ImportError:
        pass
    # ostateczny fallback: readline
    try:
        return input()[:1]
    except EOFError:
        return ""

# ---------------------------------------------------------------------------
# Diff inline — ujednolicony format z kolorowaniem ANSI
# ---------------------------------------------------------------------------

def _render_diff(local_path: str, remote_content: bytes,
                 max_lines: int = _DIFF_MAX_LINES) -> str | None:
    """Zwróć ujednolicony diff local↔remote jako pokolorowany string.

    Zwraca None gdy plik binarny lub diff jest pusty.
    """
    try:
        local_text = open(local_path, encoding="utf-8", errors="replace").readlines()
    except OSError:
        local_text = []

    try:
        remote_text = remote_content.decode("utf-8", errors="replace").splitlines(keepends=True)
    except Exception:
        return None  # binarny

    diff = list(difflib.unified_diff(
        local_text, remote_text,
        fromfile=f"lokalny   {os.path.basename(local_path)}",
        tofile=f"zdalny    {os.path.basename(local_path)}",
        lineterm="",
    ))

    if not diff:
        return None

    lines_out: list[str] = []
    truncated = False

    for i, line in enumerate(diff):
        if i >= max_lines:
            truncated = True
            break
        if line.startswith("---") or line.startswith("+++"):
            lines_out.append(f"    {DIM}{line}{RST}")
        elif line.startswith("@@"):
            lines_out.append(f"    {BCYN}{line}{RST}")
        elif line.startswith("+"):
            lines_out.append(f"    {GRN}{line}{RST}")
        elif line.startswith("-"):
            lines_out.append(f"    {RED}{line}{RST}")
        else:
            lines_out.append(f"    {DIM}{line}{RST}")

    result = "\n".join(lines_out)
    if truncated:
        remaining = len(diff) - max_lines
        result += f"\n    {DIM}... i jeszcze {remaining} linii{RST}"
    return result

# ---------------------------------------------------------------------------
# Statystyki diff — szybkie podsumowanie (+N / -N)
# ---------------------------------------------------------------------------

def _diff_stats(local_path: str, remote_content: bytes) -> tuple[int, int]:
    """Zwróć (added, removed) liczbę zmienionych linii."""
    try:
        local_lines  = open(local_path, encoding="utf-8", errors="replace").readlines()
        remote_lines = remote_content.decode("utf-8", errors="replace").splitlines(keepends=True)
    except Exception:
        return 0, 0
    added = removed = 0
    for line in difflib.unified_diff(local_lines, remote_lines):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed

# ---------------------------------------------------------------------------
# Interaktywny wybór plików (menu spacja/enter)
# ---------------------------------------------------------------------------

# Stany selekcji per plik
_SEL_ON   = "on"    # zaznaczony — do aktualizacji
_SEL_OFF  = "off"   # odznaczony — pomiń
_SEL_DIFF = "diff"  # tymczasowy — pokaż diff, wróć


def _tag_label(kind: str) -> str:
    if kind == "changed":
        return f"{YLW}~{RST}"
    return f"{GRN}+{RST}"


def _render_selector(entries: list[dict], selected: list[bool],
                     cursor: int, contents: dict[str, bytes]) -> None:
    """Przerysuj całe menu selekcji. Używa ANSI do nadpisania ekranu."""
    _w("\x1b[2J\x1b[H")   # clear screen + go home

    _w(f"\n  {BOLD}{CYN}Wybierz pliki do aktualizacji{RST}"
       f"  {DIM}({len(entries)} zmian){RST}\n\n")

    _w(f"  {DIM}Spacja — zaznacz/odznacz  "
       f"D — diff  "
       f"A — wszystkie  "
       f"N — żadne  "
       f"Enter — zatwierdź  "
       f"Q — anuluj{RST}\n\n")

    for i, entry in enumerate(entries):
        rel   = entry["path"]
        kind  = entry.get("_kind", "new")
        tag   = _tag_label(kind)
        chk   = f"{GRN}[✔]{RST}" if selected[i] else f"{DIM}[ ]{RST}"
        arrow = f"{BCYN}▶{RST} " if i == cursor else "  "

        # statystyki +/- tylko dla zmienionych plików tekstowych
        stats = ""
        if kind == "changed" and rel in contents:
            local = os.path.join(ROOT_DIR, rel)
            if os.path.exists(local):
                added, removed = _diff_stats(local, contents[rel])
                if added or removed:
                    stats = (f"  {DIM}("
                             f"{GRN}+{added}{RST}{DIM}/"
                             f"{RED}-{removed}{RST}{DIM}){RST}")

        _w(f"  {arrow}{chk} {tag}  {rel}{stats}\n")

    sel_count = sum(selected)
    _w(f"\n  {DIM}Zaznaczono: {BOLD}{WHT}{sel_count}{RST}"
       f"{DIM}/{len(entries)}{RST}\n\n")


def _interactive_select(entries: list[dict],
                        contents: dict[str, bytes]) -> list[dict] | None:
    """Interaktywne menu wyboru plików.

    Zwraca przefiltrowaną listę wpisów (tylko zaznaczone),
    lub None gdy użytkownik anulował.
    """
    if not entries:
        return []

    selected = [True] * len(entries)
    cursor   = 0
    n        = len(entries)

    while True:
        _render_selector(entries, selected, cursor, contents)

        ch = _getch().lower()

        if ch in ("\x1b[a", "\x1b[d", "k"):   # strzałka góra / k
            cursor = (cursor - 1) % n
        elif ch in ("\x1b[b", "\x1b[c", "j"): # strzałka dół / j
            cursor = (cursor + 1) % n
        elif ch == " ":                         # toggle selekcji
            selected[cursor] = not selected[cursor]
            cursor = (cursor + 1) % n
        elif ch == "a":                         # zaznacz wszystkie
            selected = [True] * n
        elif ch in ("n", "u"):                  # odznacz wszystkie
            selected = [False] * n
        elif ch == "d":                         # diff bieżącego pliku
            _show_diff_screen(entries[cursor], contents)
            # po powrocie (dowolny klawisz) wracamy do menu
        elif ch in ("\r", "\n", ""):            # Enter — zatwierdź
            break
        elif ch in ("q", "\x03", "\x1b"):      # Q / Ctrl+C / ESC — anuluj
            _w("\x1b[2J\x1b[H")
            return None

    _w("\x1b[2J\x1b[H")
    return [e for e, s in zip(entries, selected) if s]


def _show_diff_screen(entry: dict, contents: dict[str, bytes]) -> None:
    """Pełnoekranowy podgląd diff dla jednego pliku."""
    rel = entry["path"]
    _w("\x1b[2J\x1b[H")
    _w(f"\n  {BOLD}{CYN}Diff: {rel}{RST}\n\n")

    content = contents.get(rel)
    if content is None:
        _w(f"  {DIM}(plik nowy — brak diff){RST}\n\n")
    else:
        local = os.path.join(ROOT_DIR, rel)
        rendered = _render_diff(local, content, max_lines=200)
        if rendered:
            _w(rendered + "\n")
        else:
            _w(f"  {DIM}(brak zmian tekstowych lub plik binarny){RST}\n\n")

    _w(f"\n  {DIM}Naciśnij dowolny klawisz, aby wrócić...{RST}\n")
    _getch()

# ---------------------------------------------------------------------------
# Progress bar w tle (nieblokujący)
# ---------------------------------------------------------------------------

def _progress_bar(done: int, total: int, width: int = 28) -> str:
    if total == 0:
        return f"[{'█' * width}] {done}/{total}"
    filled = int(width * done / total)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {done}/{total}"


class _ProgressPrinter:
    """Renderuje progress inline bez blokowania wątku pobierania."""

    def __init__(self, total: int):
        self._total   = total
        self._done    = 0
        self._lock    = threading.Lock()
        self._current = ""
        self._active  = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while self._active:
            with self._lock:
                done    = self._done
                current = self._current
            bar  = _progress_bar(done, self._total)
            name = f"  {current}" if current else ""
            _w(f"\r  {CYN}{bar}{RST}{DIM}{name:<40}{RST}")
            time.sleep(0.12)

    def tick(self, filename: str = "") -> None:
        with self._lock:
            self._done    += 1
            self._current  = filename

    def stop(self) -> None:
        self._active = False
        self._thread.join(timeout=0.5)
        _w("\r" + " " * 80 + "\r")

# ---------------------------------------------------------------------------
# Pobierz zawartości plików do podglądu (równolegle, z cache)
# ---------------------------------------------------------------------------

def _prefetch_contents(entries: list[dict],
                       token: str | None) -> dict[str, bytes]:
    """Pobierz zdalne treści wszystkich wpisów równolegle.

    Zwraca {rel_path: bytes}. Pliki których nie udało się pobrać są pomijane.
    """
    results: dict[str, bytes] = {}
    lock = threading.Lock()

    def _fetch_one(entry: dict) -> None:
        rel = entry["path"]
        content = _download_raw(rel, token=token)
        if content is not None:
            with lock:
                results[rel] = content

    threads = [threading.Thread(target=_fetch_one, args=(e,), daemon=True)
               for e in entries]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    return results

# ---------------------------------------------------------------------------
# Potwierdzenie zbiorowe przed zapisem
# ---------------------------------------------------------------------------

def _confirm_proceed(count: int) -> bool:
    """Zapytaj użytkownika czy kontynuować zapis. Zwraca True jeśli tak."""
    _w(f"\n  {BOLD}{WHT}Zastosować {count} aktualizacji?{RST}"
       f"  {DIM}[T/n]{RST}  ")
    try:
        answer = input().strip().lower()
    except EOFError:
        answer = ""
    return answer in ("", "t", "y", "tak", "yes")

# ---------------------------------------------------------------------------
# Zapis pliku (tmp → defender scan → atomic replace)
# ---------------------------------------------------------------------------

def _write_file(rel: str, content: bytes, terminal) -> str:
    """Zapisz plik.

    Zwraca: 'ok' | 'fail' | 'blocked'
    """
    local = os.path.join(ROOT_DIR, rel)
    tmp   = local + ".upd_tmp"

    try:
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
    except OSError as exc:
        _integration.log_debug_event(terminal, "warn",
            f"[update] tmp write failed: {rel}: {exc}")
        return "fail"

    if not _integration.defender_scan_file(tmp):
        _integration.log_debug_event(terminal, "warn",
            f"[update] defender blocked: {rel}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return "blocked"

    try:
        os.replace(tmp, local)
        _integration.log_debug_event(terminal, "io", f"[update] written: {rel}")
        return "ok"
    except OSError as exc:
        _integration.log_debug_event(terminal, "warn",
            f"[update] replace failed: {rel}: {exc}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return "fail"

# ---------------------------------------------------------------------------
# Główna komenda
# ---------------------------------------------------------------------------

def _cmd_update(args: list, _t, terminal=None) -> None:
    """update terminal [--check|--dry-run] [--force] [--list] [--yes]"""
    check_only   = "--check"   in args or "--dry-run" in args
    force_all    = "--force"   in args
    list_only    = "--list"    in args
    auto_yes     = "--yes"     in args

    token = _get_github_token()

    _w(f"\n  {BOLD}{CYN}TerminalX Update  v{_VERSION}{RST}\n")
    _w(f"  {DIM}Repozytorium: {_REPO_OWNER}/{_REPO_NAME} @ {_REPO_BRANCH}{RST}\n\n")

    # 1. Drzewo plików z GitHub
    _w(f"  {DIM}{_t('upd_fetching_tree')}...{RST}\n")
    tree = _fetch_tree(token=token)
    _integration.log_debug_event(terminal, "io", "[update] tree fetch complete")

    if tree is None:
        _w(f"\n  {RED}{_t('upd_tree_error')}{RST}\n\n")
        _integration.notify_event(terminal, _t("upd_tree_error"),
                                   kind="err", title="Update", compact=True)
        return

    blob_entries = [e for e in tree if e.get("type") == "blob"]
    _w(f"  {DIM}{_t('upd_tree_ok', count=len(blob_entries))}{RST}\n\n")

    # 2. Wykryj zmiany
    if force_all:
        changed = [e for e in tree if _should_update(e)]
        new: list[dict] = []
        _w(f"  {YLW}{_t('upd_force_mode')}{RST}\n\n")
    else:
        _w(f"  {DIM}{_t('upd_comparing')}...{RST}\n")
        changed, new = _detect_changes(tree)

    # Oznacz typ dla późniejszego renderowania
    for e in changed:
        e["_kind"] = "changed"
    for e in new:
        e["_kind"] = "new"

    total = len(changed) + len(new)

    if total == 0:
        _w(f"  {GRN}{_t('upd_up_to_date')}{RST}\n\n")
        _save_state({"last_check": _now_iso(), "status": "up-to-date"})
        _integration.notify_event(terminal, _t("upd_up_to_date"),
                                   kind="ok", title="Update", compact=True)
        return

    _w(f"  {YLW}{_t('upd_changes_found', total=total, changed=len(changed), new=len(new))}{RST}\n\n")

    # 3. Tryby tylko-odczyt
    if check_only or list_only:
        if changed:
            _w(f"  {BOLD}{WHT}{_t('upd_modified')}{RST}\n")
            for e in changed:
                _w(f"    {YLW}~{RST}  {e['path']}\n")
            _w("\n")
        if new:
            _w(f"  {BOLD}{WHT}{_t('upd_new_files')}{RST}\n")
            for e in new:
                _w(f"    {GRN}+{RST}  {e['path']}\n")
            _w("\n")
        _w(f"  {DIM}{_t('upd_check_only_hint')}{RST}\n\n")
        return

    # 4. Prefetch zawartości (potrzebne do diff i do zapisu)
    all_entries = changed + new
    _w(f"  {DIM}Pobieranie zawartości ({total} plików)...{RST}\n")
    prog = _ProgressPrinter(total)

    contents: dict[str, bytes] = {}
    fetch_lock = threading.Lock()

    def _fetch_and_tick(entry: dict) -> None:
        rel     = entry["path"]
        content = _download_raw(rel, token=token)
        with fetch_lock:
            if content is not None:
                contents[rel] = content
        prog.tick(rel)

    threads = [threading.Thread(target=_fetch_and_tick, args=(e,), daemon=True)
               for e in all_entries]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)

    prog.stop()

    fetch_ok   = len(contents)
    fetch_fail = total - fetch_ok
    if fetch_fail:
        _w(f"  {YLW}⚠  Nie pobrano {fetch_fail} pliku(ów) — zostaną pominięte.{RST}\n\n")
    else:
        _w(f"  {GRN}✔  Pobrano {fetch_ok} plików.{RST}\n\n")

    # Zaktualizuj listę — tylko pliki które faktycznie pobrano
    all_entries = [e for e in all_entries if e["path"] in contents]
    if not all_entries:
        _w(f"  {RED}Brak dostępnych plików do aktualizacji.{RST}\n\n")
        return

    # 5. Interaktywny wybór (pomiń przy --yes lub gdy stdin nie jest TTY)
    is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()

    if auto_yes or not is_tty:
        to_update = all_entries
        if not auto_yes:
            # Pokaż listę bez menu
            for e in changed:
                if e in to_update:
                    _w(f"    {YLW}~{RST}  {e['path']}\n")
            for e in new:
                if e in to_update:
                    _w(f"    {GRN}+{RST}  {e['path']}\n")
            _w("\n")
    else:
        to_update = _interactive_select(all_entries, contents)
        if to_update is None:
            _w(f"\n  {YLW}Aktualizacja anulowana.{RST}\n\n")
            _integration.notify_event(terminal, "Aktualizacja anulowana.",
                                       kind="warn", title="Update", compact=True)
            return
        if not to_update:
            _w(f"\n  {DIM}Nie zaznaczono żadnych plików.{RST}\n\n")
            return

    # 6. Potwierdzenie zbiorcze
    if not auto_yes and is_tty:
        if not _confirm_proceed(len(to_update)):
            _w(f"  {YLW}Anulowano.{RST}\n\n")
            return

    # 7. Zapis z progress barem
    _w(f"\n  {DIM}{_t('upd_downloading')}...{RST}\n\n")

    ok_count      = 0
    fail_count    = 0
    blocked_count = 0
    progress      = _ProgressPrinter(len(to_update))

    for entry in to_update:
        rel     = entry["path"]
        content = contents[rel]
        _integration.log_debug_event(terminal, "io", f"[update] writing: {rel}")

        result = _write_file(rel, content, terminal)

        if result == "ok":
            ok_count += 1
        elif result == "blocked":
            blocked_count += 1
            fail_count    += 1
            progress.stop()
            _w(f"  {YLW}⚠{RST}  {rel}  {YLW}{_t('upd_scan_blocked')}{RST}\n")
            progress = _ProgressPrinter(len(to_update) - ok_count - fail_count)
        else:
            fail_count += 1
            progress.stop()
            _w(f"  {RED}✖{RST}  {rel}  {RED}{_t('upd_dl_fail')}{RST}\n")
            progress = _ProgressPrinter(len(to_update) - ok_count - fail_count)

        progress.tick(rel)

    progress.stop()

    # 8. Podsumowanie
    _w(f"\n  {'─' * 48}\n")
    summary_color = GRN if fail_count == 0 else (YLW if ok_count > 0 else RED)
    _w(f"  {BOLD}{summary_color}"
       f"{_t('upd_summary', ok=ok_count, fail=fail_count)}"
       f"{RST}\n")
    if blocked_count:
        _w(f"  {DIM}Zablokowanych przez Defendera: {blocked_count}{RST}\n")
    if fail_count:
        _w(f"  {DIM}{_t('upd_fail_hint')}{RST}\n")
    _w(f"  {DIM}{_t('upd_restart_hint')}{RST}\n\n")

    # 9. Powiadomienie
    if fail_count == 0:
        _integration.notify_event(terminal,
            _t("upd_summary", ok=ok_count, fail=0),
            kind="ok", title="Update", compact=True)
    elif ok_count > 0:
        _integration.notify_event(terminal,
            _t("upd_summary", ok=ok_count, fail=fail_count),
            kind="warn", title="Update", compact=True)
    else:
        _integration.notify_event(terminal,
            _t("upd_summary", ok=0, fail=fail_count),
            kind="err", title="Update", compact=True)

    # 10. Zapisz stan
    _save_state({
        "last_update":   _now_iso(),
        "status":        "ok" if fail_count == 0 else "partial",
        "files_updated": ok_count,
        "files_failed":  fail_count,
    })


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

def _show_help(_t) -> None:
    state    = _load_state()
    last     = state.get("last_update") or state.get("last_check")
    last_str = last or _t("upd_never")
    repo_url = f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}"

    _w(f"\n  {BOLD}{CYN}Update  v{_VERSION}{RST}\n\n")
    _w(f"  {DIM}{_t('upd_help_desc')}{RST}\n")
    _w(f"  {DIM}{_t('upd_help_repo', url=repo_url)}{RST}\n")
    _w(f"  {DIM}{_t('upd_help_last', last=last_str)}{RST}\n\n")
    rows = [
        ("update terminal",             _t("upd_help_run")),
        ("update terminal --check",     _t("upd_help_check")),
        ("update terminal --dry-run",   _t("upd_help_check")),
        ("update terminal --list",      _t("upd_help_list")),
        ("update terminal --force",     _t("upd_help_force")),
        ("update terminal --yes",       "zastosuj bez pytania"),
        ("update rollback",             "przywróć z plików .bak"),
    ]
    for cmd, desc in rows:
        _w(f"  {YLW}{cmd:<36}{RST}  {DIM}{desc}{RST}\n")
    _w("\n")

# ---------------------------------------------------------------------------
# Rollback + cleanup .bak
# ---------------------------------------------------------------------------

def _cleanup_bak_files(root: str) -> int:
    removed = 0
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            if fname.endswith(".bak"):
                fpath = os.path.join(dirpath, fname)
                try:
                    os.remove(fpath)
                    _integration.log_debug_event(None, "io",
                        f"[update] removed .bak: {fpath}")
                    removed += 1
                except OSError:
                    pass
    return removed


def _cmd_rollback(args: list, _t, terminal=None) -> None:
    _w(f"\n  {BOLD}{CYN}Rollback{RST}\n\n")
    restored = 0
    failed   = 0

    for dirpath, _dirs, files in os.walk(ROOT_DIR):
        for fname in files:
            if not fname.endswith(".bak"):
                continue
            bak  = os.path.join(dirpath, fname)
            orig = bak[:-4]
            _integration.log_debug_event(terminal, "io", f"[update] rollback: {orig}")
            try:
                os.replace(bak, orig)
                restored += 1
            except OSError as exc:
                _w(f"  {RED}✖{RST}  {orig}  {RED}{exc}{RST}\n")
                failed += 1

    if restored == 0 and failed == 0:
        _w(f"  {DIM}Brak plików .bak — nic do przywrócenia.{RST}\n\n")
        return

    _w(f"  {GRN if failed == 0 else YLW}"
       f"Przywrócono: {restored}  Błędy: {failed}{RST}\n")

    if failed == 0 and restored > 0:
        removed = _cleanup_bak_files(ROOT_DIR)
        if removed:
            _w(f"  {DIM}Usunięto {removed} plików .bak.{RST}\n")
        _integration.notify_event(terminal,
            f"Rollback OK — przywrócono {restored} plików",
            kind="ok", title="Update", compact=True)
    else:
        _integration.notify_event(terminal,
            f"Rollback częściowy — błędy: {failed}",
            kind="warn", title="Update", compact=True)

    _w("\n")

# ---------------------------------------------------------------------------
# setup / teardown
# ---------------------------------------------------------------------------

def setup(terminal) -> None:
    _t = terminal.t

    _integration.register("update", {
        "run": lambda args=None: _cmd_update(args or [], _t, terminal),
    })

    def update(args: list) -> None:
        if not args:
            _show_help(_t)
            return
        sub = args[0].lower()
        if sub == "terminal":
            _cmd_update(args[1:], _t, terminal)
        elif sub == "rollback":
            _cmd_rollback(args[1:], _t, terminal)
        else:
            _w(f"\n  {RED}{_t('upd_unknown_sub', sub=sub)}{RST}\n\n")

    terminal.register_command(
        "update", update,
        description=_t("cmd_update"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal) -> None:
    _integration.unregister("update")
    terminal.commands.pop("update", None)
