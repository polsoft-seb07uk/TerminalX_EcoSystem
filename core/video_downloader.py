# crossterm: {"id": "10", "aliases": ["yt", "ytdl", "youtube", "vimeo", "dwl"], "description": "Pobieranie filmów z internetu (yt-dlp) — YouTube, Vimeo i 1000+ serwisów", "version": "2.3"}
"""
video_dwl  –  Moduł CrossTerm do pobierania filmów z internetu
Obsługuje YouTube, Vimeo i ponad 1000 innych serwisów przez yt-dlp.
Wymaga: yt-dlp     →  pip install yt-dlp
v1.6: atomowy zapis JSON, timeout sieciowy, lepsza obsługa błędów
v1.8: rozbudowana obsługa cache (cache\\ metadanych, formatów, playlist)
      – TTL per-typ, limit rozmiaru, eviction LRU, komendy cache
v1.9: automatyczny fallback formatu przy błędzie FFmpeg/kodeka,
v2.0: komenda find — wyszukiwanie pobranych plików wideo/audio na dysku
      (filtrowanie po nazwie, rozszerzeniu, rozmiarze, dacie; sortowanie)
v2.1: usprawnienia istniejących funkcji:
v2.2: komenda search — wyszukiwanie wideo na YouTube przez yt-dlp
      (wybór wyniku, podgląd metadanych, bezpośrednie pobieranie lub kolejka)
v2.3: usprawnienia search:
      – _result_url() eliminuje 4-krotną duplikację URL resolution
      – extract_flat="in_playlist" zamiast True — więcej pól (views, dur, channel)
      – smart cache: limit normalizowany, klucz tylko po query+limit
      – interaktywna pętla — pozostaje aktywna po i/q aż do Enter/0
      – more/m <N> — doładowanie kolejnych N wyników bez nowego wyszukania
      – --filter <słowo> — usuwa wyniki zawierające frazę z tytułu
      – --sort views|date|dur — sortowanie wyników po stronie klienta
      – lepsza tabela: kolumna daty, skrócone tytuły z zachowaniem czytelności
      – _yt_search rozróżnia DownloadError/timeout od innych błędów
      – _load_json_list() eliminuje duplikację w history/queue load
      – _has_ytdlp() cachuje wynik importu (jednorazowy koszt)
      – _fmt_sz() poprawia obsługę b=0, dodaje TB jako TB
      – _validate_url() trim whitespace przed walidacją
      – _fetch_info() rozróżnia timeout od innych błędów sieciowych
      – _run_download() bezpieczny fallback tytułu gdy info=None
      – _ProgressBar.hook() reset state przy error poza lockiem
      – queue run naprawia logikę error_idxs (set of queue indices)
      – history search <wzorzec> — filtrowanie po tytule/URL/serwisie
      sprzątanie plików tymczasowych po błędzie, odporniejszy _download,
      ulepszony pasek postępu (wygładzanie, reset między strumieniami),
      poprawiona obsługa błędów w _run_download i queue run
"""

from __future__ import annotations

import sys
import re
import json
import hashlib
import threading
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

# ── CrossTerm API ─────────────────────────────────────────────────────────────

try:
    from __main__ import write, flush, A
except Exception:
    def write(s: str) -> None:
        sys.stdout.write(s)

    def flush() -> None:
        sys.stdout.flush()

    class A:
        RESET   = "\x1b[0m"
        BOLD    = "\x1b[1m"
        DIM     = "\x1b[2m"
        RED     = "\x1b[31m"
        GREEN   = "\x1b[32m"
        YELLOW  = "\x1b[33m"
        CYAN    = "\x1b[36m"
        BRED    = "\x1b[91m"
        BGREEN  = "\x1b[92m"
        BYELLOW = "\x1b[93m"
        BCYAN   = "\x1b[96m"
        BWHITE  = "\x1b[97m"

# ── Stałe modułu ─────────────────────────────────────────────────────────────

_DEFAULT_DIR  = Path(r"C:\.polsoft\download\media")
_QUEUE_FILE   = Path(__file__).parent / ".video_dwl_queue.json"
_HISTORY_FILE = Path.home() / ".video_dwl_history.json"
_HISTORY_MAX  = 500   # maksymalna liczba wpisów

# ── Cache ─────────────────────────────────────────────────────────────────────

_CACHE_DIR       = Path(__file__).parent / "cache"
_CACHE_INDEX     = _CACHE_DIR / "_index.json"

# TTL w sekundach dla poszczególnych typów cache
_CACHE_TTL: dict[str, int] = {
    "info":     3600 * 6,   # metadane filmu/playlisty  — 6 h
    "formats":  3600 * 12,  # lista formatów            — 12 h
    "playlist": 3600 * 2,   # wpisy playlisty           — 2 h
}
_CACHE_MAX_ENTRIES = 200    # maks. liczba wpisów (LRU eviction po przekroczeniu)
_CACHE_MAX_MB      = 50     # maks. rozmiar katalogu cache w MB

_FORMATS: dict[str, tuple[str, str]] = {
    "1": ("najlepsza jakość (video + audio)",
          "bestvideo+bestaudio/best"),
    "2": ("1080p  MP4",
          "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]"),
    "3": ("720p   MP4",
          "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]"),
    "4": ("480p   MP4",
          "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]"),
    "5": ("tylko audio  MP3",
          "bestaudio/best"),
    "6": ("tylko audio  M4A",
          "bestaudio[ext=m4a]/bestaudio"),
}

# Serwisy z dedykowaną etykietą (kolejność ma znaczenie — sprawdzamy od góry)
_KNOWN_SITES: list[tuple[str, str]] = [
    ("YouTube",     "youtube.com"),
    ("YouTube",     "youtu.be"),
    ("YouTube",     "youtube-nocookie.com"),
    ("Vimeo",       "vimeo.com"),
    ("Twitch",      "twitch.tv"),
    ("Twitter/X",   "twitter.com"),
    ("Twitter/X",   "x.com"),
    ("TikTok",      "tiktok.com"),
    ("Dailymotion", "dailymotion.com"),
    ("SoundCloud",  "soundcloud.com"),
    ("Bandcamp",    "bandcamp.com"),
    ("Reddit",      "reddit.com"),
    ("Facebook",    "facebook.com"),
    ("Instagram",   "instagram.com"),
]

_URL_RE = re.compile(r"https?://\S+")

# ── Silnik cache ──────────────────────────────────────────────────────────────
#
# Struktura na dysku:
#   cache/
#     _index.json          – rejestr wpisów: {key: {file, type, url, ts, hits, size}}
#     <sha256[:16]>.json   – dane wpisu (zserializowane metadane yt-dlp)
#
# Przepływ:
#   cache_get(url, ctype) -> dict | None   (None = miss lub wygasły)
#   cache_put(url, ctype, data)            (zapisuje + eviction LRU)
#   cache_invalidate(url)                  (usuwa wpisy dla URL)
#   cache_clear()                          (czyści cały cache)
#   cache_stats()                          (zwraca słownik ze statystykami)

_cache_lock = threading.Lock()


def _cache_key(url: str, ctype: str) -> str:
    """SHA-256 pierwszych 16 znaków jako unikalny klucz pliku."""
    raw = f"{ctype}:{url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_index_load() -> dict:
    """Wczytuje indeks cache; zwraca {} przy braku/uszkodzeniu."""
    try:
        if _CACHE_INDEX.exists():
            data = json.loads(_CACHE_INDEX.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _cache_index_save(index: dict) -> None:
    """Zapisuje indeks atomowo."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_INDEX.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_CACHE_INDEX)
    except Exception:
        tmp.unlink(missing_ok=True)


def _cache_dir_size_mb() -> float:
    """Zwraca rozmiar katalogu cache w MB."""
    try:
        return sum(f.stat().st_size for f in _CACHE_DIR.rglob("*") if f.is_file()) / (1024 * 1024)
    except Exception:
        return 0.0


def _cache_evict_lru(index: dict) -> dict:
    """Usuwa najstarsze wpisy (LRU) aż do osiągnięcia limitów."""
    entries = sorted(index.items(), key=lambda kv: (kv[1].get("hits", 0), kv[1].get("ts", 0)))
    while (len(index) > _CACHE_MAX_ENTRIES or _cache_dir_size_mb() > _CACHE_MAX_MB) and entries:
        key, meta = entries.pop(0)
        f = _CACHE_DIR / meta.get("file", "")
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass
        index.pop(key, None)
    return index


def cache_get(url: str, ctype: str) -> dict | None:
    """Zwraca dane z cache lub None przy miss/wygaśnięciu.

    Args:
        url:   URL zasobu
        ctype: typ cache – 'info', 'formats', 'playlist'
    """
    key = _cache_key(url, ctype)
    ttl = _CACHE_TTL.get(ctype, 3600)

    with _cache_lock:
        index = _cache_index_load()
        meta  = index.get(key)
        if not meta:
            return None

        age = datetime.now().timestamp() - meta.get("ts", 0)
        if age > ttl:
            # Wygasły — usuń wpis
            f = _CACHE_DIR / meta.get("file", "")
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
            index.pop(key, None)
            _cache_index_save(index)
            return None

        f = _CACHE_DIR / meta["file"]
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            index.pop(key, None)
            _cache_index_save(index)
            return None

        meta["hits"] = meta.get("hits", 0) + 1
        meta["last_hit"] = datetime.now().isoformat(timespec="seconds")
        _cache_index_save(index)
        return data


def cache_put(url: str, ctype: str, data: dict) -> None:
    """Zapisuje dane do cache i uruchamia eviction jeśli potrzeba.

    Args:
        url:   URL zasobu
        ctype: typ cache – 'info', 'formats', 'playlist'
        data:  dane do zapisu (musi być JSON-serializowalny)
    """
    key      = _cache_key(url, ctype)
    filename = f"{key}.json"
    filepath = _CACHE_DIR / filename

    with _cache_lock:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            tmp = filepath.with_suffix(".tmp")
            tmp.write_text(raw, encoding="utf-8")
            tmp.replace(filepath)
        except Exception:
            return

        index = _cache_index_load()
        index[key] = {
            "file":    filename,
            "type":    ctype,
            "url":     url,
            "ts":      datetime.now().timestamp(),
            "hits":    0,
            "size":    len(raw.encode()),
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        index = _cache_evict_lru(index)
        _cache_index_save(index)


def cache_invalidate(url: str) -> int:
    """Usuwa wszystkie wpisy cache dla danego URL. Zwraca liczbę usuniętych."""
    removed = 0
    with _cache_lock:
        index = _cache_index_load()
        to_del = [k for k, v in index.items() if v.get("url") == url]
        for key in to_del:
            f = _CACHE_DIR / index[key].get("file", "")
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
            index.pop(key, None)
            removed += 1
        if removed:
            _cache_index_save(index)
    return removed


def cache_clear() -> int:
    """Czyści cały cache. Zwraca liczbę usuniętych wpisów."""
    with _cache_lock:
        index = _cache_index_load()
        count = len(index)
        try:
            for f in _CACHE_DIR.glob("*.json"):
                f.unlink(missing_ok=True)
        except Exception:
            pass
        _cache_index_save({})
    return count


def cache_stats() -> dict:
    """Zwraca słownik ze statystykami cache."""
    with _cache_lock:
        index = _cache_index_load()
    now = datetime.now().timestamp()
    by_type: dict[str, int] = {}
    expired = 0
    total_hits = 0
    for meta in index.values():
        ctype = meta.get("type", "?")
        by_type[ctype] = by_type.get(ctype, 0) + 1
        if now - meta.get("ts", 0) > _CACHE_TTL.get(ctype, 3600):
            expired += 1
        total_hits += meta.get("hits", 0)
    return {
        "total":       len(index),
        "expired":     expired,
        "by_type":     by_type,
        "total_hits":  total_hits,
        "size_mb":     round(_cache_dir_size_mb(), 2),
        "max_entries": _CACHE_MAX_ENTRIES,
        "max_mb":      _CACHE_MAX_MB,
        "ttl":         _CACHE_TTL,
    }


def _detect_site(url: str) -> str:
    """Zwraca czytelną nazwę serwisu lub domenę hosta."""
    for name, fragment in _KNOWN_SITES:
        if fragment in url:
            return name
    m = re.search(r"https?://(?:www\.)?([^/?#]+)", url)
    return m.group(1) if m else "nieznany serwis"

# ── Pomocnicze ────────────────────────────────────────────────────────────────

_ytdlp_module = None          # cache importu — import wykonuje się tylko raz
_ytdlp_available: bool | None = None


def _has_ytdlp() -> bool:
    """Sprawdza dostępność yt-dlp — wynik jest cachowany po pierwszym wywołaniu."""
    global _ytdlp_available, _ytdlp_module
    if _ytdlp_available is None:
        try:
            import yt_dlp as _m
            _ytdlp_module = _m
            _ytdlp_available = True
        except ImportError:
            _ytdlp_available = False
    return _ytdlp_available


def _fmt_dur(sec: int | float | None) -> str:
    if not sec:
        return "N/A"
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _fmt_sz(b: int | float | None) -> str:
    """Formatuje bajty na czytelny string. None → 'N/A'; 0 → '0 B'."""
    if b is None:
        return "N/A"
    b = float(b)
    if b == 0:
        return "0 B"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def _ask(prompt: str, default: str = "") -> str:
    write(f"  {A.BYELLOW}{prompt}{A.RESET} ")
    flush()
    try:
        ans = input()
    except (EOFError, KeyboardInterrupt):
        ans = default
    return ans.strip() or default


def _confirm(prompt: str, default: bool = True) -> bool:
    hint = "[T/n]" if default else "[t/N]"
    ans = _ask(f"{prompt} {hint}").lower()
    if not ans:
        return default
    return ans in ("t", "tak", "y", "yes", "1")


def _validate_url(url: str) -> bool:
    """Zwraca True jeśli url wygląda jak poprawny HTTP/HTTPS URL."""
    return bool(_URL_RE.match(url.strip()))


def _err(msg: str) -> None:
    write(f"  {A.BRED}✗ {msg}{A.RESET}\n")


def _ok(msg: str) -> None:
    write(f"  {A.BGREEN}✔ {msg}{A.RESET}\n")


def _info(msg: str) -> None:
    write(f"  {A.DIM}{msg}{A.RESET}\n")


# ── Pobieranie metadanych ─────────────────────────────────────────────────────

def _fetch_info(url: str, force: bool = False) -> dict | None:
    """Pobiera metadane (z cache jeśli dostępne i świeże).

    Args:
        url:   URL zasobu
        force: pomiń cache i pobierz świeże dane
    """
    import socket
    yt_dlp = _ytdlp_module  # używamy cachowanego modułu

    ctype = "playlist" if "list=" in url or "/playlist" in url else "info"

    if not force:
        cached = cache_get(url, ctype)
        if cached is not None:
            _info("Metadane z cache  (użyj --no-cache aby wymusić odświeżenie)")
            return cached

    opts = {
        "quiet":          True,
        "no_warnings":    True,
        "skip_download":  True,
        "socket_timeout": 20,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
        if data:
            cache_put(url, ctype, data)
        return data
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "timed out" in msg.lower() or isinstance(e.__cause__, socket.timeout):
            _err("Przekroczono limit czasu połączenia. Sprawdź sieć i spróbuj ponownie.")
        else:
            _err(f"Nie można pobrać metadanych: {msg}")
        return None
    except socket.timeout:
        _err("Timeout sieci przy pobieraniu metadanych.")
        return None
    except Exception as e:
        _err(f"Nieoczekiwany błąd: {e}")
        return None


def _fmt_date(raw: str | None) -> str:
    """Formatuje datę z yt-dlp (YYYYMMDD) na czytelną (YYYY-MM-DD)."""
    if not raw or len(raw) < 8:
        return raw or "N/A"
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _show_info(info: dict) -> None:
    is_pl = info.get("_type") == "playlist"
    if is_pl:
        entries = [e for e in (info.get("entries") or []) if e]
        write(f"\n  {A.BOLD}{A.BCYAN}📋 Playlista:{A.RESET}  {A.BWHITE}{info.get('title', '?')}{A.RESET}\n")
        write(f"  {A.DIM}{'─'*62}{A.RESET}\n")
        for i, e in enumerate(entries, 1):
            title = (e.get("title") or "?")[:52]
            dur   = _fmt_dur(e.get("duration"))
            write(
                f"  {A.BYELLOW}{i:>3}.{A.RESET}  {A.BWHITE}{title:<52}{A.RESET}"
                f"  {A.DIM}{dur:>7}{A.RESET}\n"
            )
        total_dur = sum(e.get("duration") or 0 for e in entries)
        write(
            f"  {A.DIM}{'─'*62}{A.RESET}\n"
            f"  {A.DIM}Łącznie: {len(entries)} filmów"
            + (f"   •   {_fmt_dur(total_dur)}" if total_dur else "")
            + f"{A.RESET}\n"
        )
    else:
        W = 20

        def row(icon: str, k: str, v: str) -> None:
            write(f"  {icon}  {A.BCYAN}{k:<{W}}{A.RESET}{A.BWHITE}{v}{A.RESET}\n")

        write(f"\n  {A.BOLD}{A.BCYAN}{'─'*56}{A.RESET}\n")
        row("🎬", "Tytuł",        info.get("title") or "N/A")
        row("👤", "Kanał",        info.get("channel") or info.get("uploader") or "N/A")
        row("⏱ ", "Czas trwania", _fmt_dur(info.get("duration")))
        row("👁 ", "Wyświetlenia", f"{int(info.get('view_count', 0)):,}" if info.get("view_count") else "N/A")
        row("📅", "Data",         _fmt_date(info.get("upload_date")))
        filesize = info.get("filesize") or info.get("filesize_approx")
        if filesize:
            row("💾", "Rozmiar",   _fmt_sz(filesize))
        desc = (info.get("description") or "").strip()
        if desc:
            row("📝", "Opis",      desc[:60] + ("…" if len(desc) > 60 else ""))
        write(f"  {A.BOLD}{A.BCYAN}{'─'*56}{A.RESET}\n")
    write("\n")


# ── Pasek postępu ─────────────────────────────────────────────────────────────

class _ProgressBar:
    """Liniowy pasek postępu rysowany w terminalu przez write()."""

    BAR_W     = 40
    _MIN_STEP = 1   # minimalny krok % do przerysowania (ogranicza migotanie)

    def __init__(self) -> None:
        self._active    = False
        self._lock      = threading.Lock()
        self._last_pct  = -1
        self._stream_id = ""   # śledzi zmiany pliku (nowy strumień → reset)

    @staticmethod
    def _fmt_eta(sec: int | None) -> str:
        if sec is None:
            return "…"
        m, s = divmod(int(sec), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    @staticmethod
    def _speed_color(bps: float) -> str:
        if bps >= 5 * 1024 * 1024:
            return A.BGREEN
        if bps >= 1 * 1024 * 1024:
            return A.BYELLOW
        return A.BRED

    def _reset_stream(self) -> None:
        """Wymuś pełne przerysowanie przy zmianie strumienia (video → audio)."""
        self._last_pct  = -1
        self._active    = False

    def hook(self, d: dict) -> None:
        status = d.get("status")

        if status == "downloading":
            fname = Path(d.get("filename", "")).name

            # Wykryj zmianę strumienia (np. .f788.mp4 → .f140.m4a)
            stream_id = fname
            if stream_id != self._stream_id:
                self._stream_id = stream_id
                self._reset_stream()

            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done  = d.get("downloaded_bytes", 0)
            speed = d.get("speed") or 0
            eta   = d.get("eta")

            pct = int(done / total * 100) if total else 0
            # Rysuj tylko gdy zmiana ≥ _MIN_STEP lub dopiero startujemy
            if pct - self._last_pct < self._MIN_STEP and self._last_pct >= 0:
                return
            self._last_pct = pct

            fname_s = fname[:50] + "…" if len(fname) > 50 else fname
            fill    = int(self.BAR_W * pct / 100)
            bar     = "█" * fill + "░" * (self.BAR_W - fill)
            spd_c   = self._speed_color(speed) if speed else A.DIM
            spd_s   = _fmt_sz(int(speed)) + "/s" if speed else "??/s"
            eta_s   = self._fmt_eta(eta)
            done_s  = _fmt_sz(done)
            total_s = f"/ {_fmt_sz(total)}" if total else ""

            with self._lock:
                if self._active:
                    write("\x1b[2A\x1b[2K\r")
                else:
                    self._active = True

                write(f"  {A.DIM}{fname_s}{A.RESET}\n")
                write(
                    f"  {A.BGREEN}{bar}{A.RESET} "
                    f"{A.BYELLOW}{pct:>3}%{A.RESET}  "
                    f"{A.DIM}{done_s}{total_s}{A.RESET}  "
                    f"{spd_c}{spd_s}{A.RESET}  "
                    f"{A.DIM}ETA {eta_s}{A.RESET}\n"
                )
                flush()

        elif status == "finished":
            with self._lock:
                if self._active:
                    write("\x1b[2A\x1b[2K\r")
                    self._active = False
                fname = Path(d.get("filename", "")).name[:60]
                _ok(fname)
                write("\n")
                flush()
            self._last_pct  = -1
            self._stream_id = ""

        elif status == "error":
            with self._lock:
                if self._active:
                    write("\n")   # opuść linię paska jeśli był aktywny
                    flush()
                self._active = False
            self._last_pct  = -1
            self._stream_id = ""


# ── Pobieranie pliku ─────────────────────────────────────────────────────────

def _build_postprocessors(audio_only: bool, fmt: str) -> list[dict]:
    if not audio_only:
        return []
    ext = "m4a" if "m4a" in fmt else "mp3"
    return [{"key": "FFmpegExtractAudio",
             "preferredcodec": ext,
             "preferredquality": "192"}]


# Słowa kluczowe w komunikacie błędu DownloadError wskazujące na problem FFmpeg
_FFMPEG_ERROR_HINTS = (
    "codec parameters",
    "could not find codec",
    "postprocessing",
    "ffmpeg",
    "muxer",
    "invalid data found",
    "moov atom not found",
)


def _is_ffmpeg_error(msg: str) -> bool:
    low = msg.lower()
    return any(h in low for h in _FFMPEG_ERROR_HINTS)


# Fallbacki FFmpeg — jawne selektory wymuszające H.264 (avc1) + AAC/m4a.
# Kolejność: od najlepszej do najbardziej kompaktowej.
# Używamy vcodec=avc1 żeby ominąć VP9/AV1 które mogą nie przejść przez FFmpeg.
_FFMPEG_FALLBACK_CHAIN: list[tuple[str, str]] = [
    (
        "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]"
        "/bestvideo[vcodec^=avc1][height<=1080]+bestaudio"
        "/best[vcodec^=avc1][height<=1080]",
        "1080p H.264 + AAC",
    ),
    (
        "bestvideo[vcodec^=avc1][height<=720]+bestaudio[ext=m4a]"
        "/bestvideo[vcodec^=avc1][height<=720]+bestaudio"
        "/best[vcodec^=avc1][height<=720]",
        "720p H.264 + AAC",
    ),
    (
        "bestvideo[vcodec^=avc1][height<=480]+bestaudio[ext=m4a]"
        "/bestvideo[vcodec^=avc1][height<=480]+bestaudio"
        "/best[vcodec^=avc1][height<=480]",
        "480p H.264 + AAC",
    ),
    (
        "best[ext=mp4]/best",
        "najlepsze MP4 (single-file)",
    ),
]


def _cleanup_temp_files(out_dir: Path) -> None:
    """Usuwa pliki tymczasowe yt-dlp (.part, .ytdl, fragmenty) z katalogu."""
    patterns = ("*.part", "*.ytdl", "*.f[0-9]*.mp4", "*.f[0-9]*.m4a",
                "*.f[0-9]*.webm", "*.temp.*")
    removed = 0
    for pat in patterns:
        for f in out_dir.glob(pat):
            try:
                f.unlink()
                removed += 1
            except Exception:
                pass
    if removed:
        _info(f"Usunięto {removed} plik/ów tymczasowych.")


def _download_once(url: str, fmt: str, out_dir: Path, audio_only: bool,
                   bar: "_ProgressBar",
                   resume: bool = True) -> tuple[dict | None, str | None]:
    """Jedna próba pobierania. Zwraca (result, error_msg)."""
    import yt_dlp
    result: dict = {}

    def _post_hook(d: dict) -> None:
        if d.get("status") == "finished":
            info = d.get("info_dict") or {}
            if not result.get("title"):
                result["title"] = info.get("title", "")
            if not result.get("filesize"):
                result["filesize"] = (
                    d.get("total_bytes")
                    or d.get("total_bytes_estimate")
                    or info.get("filesize")
                    or info.get("filesize_approx")
                )
            if not result.get("filename"):
                result["filename"] = d.get("filename", "")

    opts = {
        "format":              fmt,
        "outtmpl":             str(out_dir / "%(title)s.%(ext)s"),
        "progress_hooks":      [bar.hook, _post_hook],
        "merge_output_format": "mp4",
        "quiet":               True,
        "no_warnings":         True,
        "postprocessors":      _build_postprocessors(audio_only, fmt),
        "retries":             5,
        "fragment_retries":    5,
        "socket_timeout":      30,
        "continuedl":          resume,
        # Nie używamy ignoreerrors — chcemy widzieć rzeczywiste błędy
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ret = ydl.download([url])
        if ret == 0:
            return result, None
        return None, f"yt-dlp zakończył z kodem {ret}"
    except yt_dlp.utils.DownloadError as e:
        return None, str(e)
    except Exception as e:
        return None, f"Nieoczekiwany błąd: {e}"


def _download(url: str, fmt: str, out_dir: Path, audio_only: bool,
              fmt_key: str = "") -> dict | None:
    """Pobiera plik. Przy błędzie FFmpeg/kodeka uruchamia łańcuch fallbacków H.264.

    Zwraca słownik z metadanymi przy sukcesie, None przy nieodwracalnym błędzie.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    bar = _ProgressBar()

    # ── Pierwsza próba z żądanym formatem (z resumem) ────────────────────────
    result, err = _download_once(url, fmt, out_dir, audio_only, bar, resume=True)
    if result is not None:
        return result

    _err(f"Błąd pobierania: {err}")

    if not (err and _is_ffmpeg_error(err)):
        return None   # błąd sieciowy lub inny — nie próbuj fallbacków

    # ── Błąd FFmpeg — wyczyść pliki i uruchom łańcuch fallbacków H.264 ───────
    _cleanup_temp_files(out_dir)
    write(
        f"\n  {A.BYELLOW}⚠  Błąd FFmpeg/kodeka — uruchamiam łańcuch fallbacków "
        f"(wymuszam H.264){A.RESET}\n"
    )

    for fb_fmt, fb_desc in _FFMPEG_FALLBACK_CHAIN:
        # Pomiń jeśli to dokładnie ten sam string który już zawiódł
        if fb_fmt == fmt:
            continue
        write(f"\n  {A.DIM}▸ Próbuję: {A.BWHITE}{fb_desc}{A.RESET}\n\n")
        flush()
        bar = _ProgressBar()
        # resume=False — nie doczytuj ew. uszkodzonych pozostałości
        result, err2 = _download_once(url, fb_fmt, out_dir, audio_only, bar,
                                      resume=False)
        if result is not None:
            _ok(f"Pobrano w formacie fallback: {fb_desc}")
            return result
        _err(f"Fallback '{fb_desc}' zawiódł: {err2}")
        _cleanup_temp_files(out_dir)
        # Jeśli kolejny fallback też ma błąd FFmpeg — kontynuuj; inaczej przerwij
        if err2 and not _is_ffmpeg_error(err2):
            break

    _info("Wszystkie fallbacki wyczerpane. Spróbuj zaktualizować FFmpeg lub yt-dlp.")
    return None


# ── Wspólna logika komendy get ────────────────────────────────────────────────

def _run_download(url: str, fmt_key: str, out_dir: Path, force_fetch: bool = False) -> None:
    """Pobiera film, wyświetla wynik i zapisuje w historii."""
    fmt_label, fmt_str = _FORMATS[fmt_key]
    audio_only = "audio" in fmt_label
    site = _detect_site(url)

    _info(f"Pobieranie metadanych  [{site}]…")
    flush()
    info = _fetch_info(url, force=force_fetch)
    if info:
        _show_info(info)

    write(f"  {A.BGREEN}▶{A.RESET}  {A.CYAN}{fmt_label}{A.RESET}  →  {A.DIM}{out_dir}{A.RESET}\n\n")
    flush()

    meta = _download(url, fmt_str, out_dir, audio_only, fmt_key=fmt_key)
    if meta is not None:
        _ok(f"Gotowe!  → {out_dir}")
        title = meta.get("title") or (info.get("title") if info else None) or ""
        _history_append({
            "title":     title,
            "url":       url,
            "fmt_key":   fmt_key,
            "fmt_label": fmt_label,
            "filesize":  meta.get("filesize"),
            "site":      site,
            "out_dir":   str(out_dir),
            "date":      datetime.now().isoformat(timespec="seconds"),
        })
    else:
        _err("Pobieranie nie powiodło się.")
        # Unieważnij cache — metadane mogły wskazywać na błędny format
        removed = cache_invalidate(url)
        if removed:
            _info(f"Cache unieważniony dla tego URL ({removed} wpis/ów).")
    write("\n")


# ── Historia pobierań ────────────────────────────────────────────────────────

"""
Historia jest listą słowników w ~/.video_dwl_history.json (najnowsze na końcu).
Każdy wpis:
  { "title": str, "url": str, "fmt_key": str, "fmt_label": str,
    "filesize": int|None, "out_dir": str, "date": str (ISO) }
"""


def _load_json_list(path: Path, label: str) -> list[dict]:
    """Wczytuje listę JSON z pliku; przy problemach loguje błąd i zwraca []."""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            _err(f"{label}: nieoczekiwany format pliku — zresetowano.")
    except json.JSONDecodeError:
        _err(f"{label}: uszkodzony JSON w {path} — zresetowano.")
    except Exception as e:
        _err(f"{label}: błąd odczytu: {e}")
    return []


def _history_load() -> list[dict]:
    return _load_json_list(_HISTORY_FILE, "Historia")


def _atomic_json_write(path: Path, data) -> None:
    """Zapisuje JSON atomowo: najpierw do pliku tymczasowego, potem rename."""
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise e


def _history_save(h: list[dict]) -> None:
    try:
        _atomic_json_write(_HISTORY_FILE, h)
    except Exception as e:
        _err(f"Nie można zapisać historii: {e}")


def _history_append(entry: dict) -> None:
    h = _history_load()
    h.append(entry)
    if len(h) > _HISTORY_MAX:
        h = h[-_HISTORY_MAX:]
    _history_save(h)


def _history_print(h: list[dict], limit: int) -> None:
    shown = h[-limit:] if limit < len(h) else h
    if not shown:
        write(f"\n  {A.DIM}Historia jest pusta.{A.RESET}\n\n")
        return

    offset = len(h) - len(shown)
    write(f"\n  {A.BOLD}Historia pobierań{A.RESET}  {A.DIM}({len(h)} łącznie, pokazuję {len(shown)}){A.RESET}\n\n")

    # Nagłówki kolumn
    write(
        f"  {A.DIM}{'Nr':>3}  {'Tytuł':<46}  {'Serwis':<11}  {'Format':<18}  {'Rozmiar':>8}  {'Data'}{A.RESET}\n"
        f"  {A.DIM}{'─'*3}  {'─'*46}  {'─'*11}  {'─'*18}  {'─'*8}  {'─'*10}{A.RESET}\n"
    )
    for local_i, item in enumerate(shown):
        nr        = offset + local_i + 1
        title     = (item.get("title") or item["url"])[:46]
        fmt_label = (item.get("fmt_label") or _FORMATS.get(item.get("fmt_key", ""), ("?",))[0])[:18]
        size_s    = _fmt_sz(item.get("filesize")) if item.get("filesize") else "—"
        date_s    = item.get("date", "")[:10]
        site_s    = (item.get("site") or _detect_site(item["url"]))[:11]
        write(
            f"  {A.BYELLOW}{nr:>3}{A.RESET}  "
            f"{A.BWHITE}{title:<46}{A.RESET}  "
            f"{A.BCYAN}{site_s:<11}{A.RESET}  "
            f"{A.DIM}{fmt_label:<18}{A.RESET}  "
            f"{A.DIM}{size_s:>8}{A.RESET}  "
            f"{A.DIM}{date_s}{A.RESET}\n"
        )
    write(f"  {A.DIM}{'─'*3}  {'─'*46}  {'─'*11}  {'─'*18}  {'─'*8}  {'─'*10}{A.RESET}\n\n")


def _cmd_history(args: list[str], terminal=None) -> None:
    """Wyświetl historię pobierań, szukaj lub wyczyść.

    Użycie:
      history [N]             Pokaż ostatnie N wpisów (domyślnie 20)
      history search <tekst>  Szukaj po tytule, URL lub serwisie
      history clear           Wyczyść całą historię
    """
    sub = args[0] if args else ""

    # ── history search <wzorzec> ──────────────────────────────────────────────
    if sub == "search":
        query = " ".join(args[1:]).strip().lower()
        if not query:
            write(f"  {A.BYELLOW}Użycie:{A.RESET}  history search <wzorzec>\n")
            return
        h = _history_load()
        hits = [
            item for item in h
            if query in (item.get("title") or "").lower()
            or query in item.get("url", "").lower()
            or query in (item.get("site") or "").lower()
        ]
        if not hits:
            _info(f"Brak wyników dla: '{query}'")
            write("\n")
            return
        _history_print(hits, len(hits))
        return

    if sub == "clear":
        h = _history_load()
        if not h:
            _info("Historia jest już pusta.")
            write("\n")
            return
        if _confirm(f"Usunąć {len(h)} wpisów z historii?", default=False):
            _history_save([])
            _ok("Historia wyczyszczona.")
        else:
            _info("Anulowano.")
        write("\n")
        return

    # Domyślnie lub gdy podano liczbę
    limit = 20
    if sub and sub.isdigit():
        limit = int(sub)
    elif sub and not sub.isdigit():
        _err(f"Nieznana podkomenda: '{sub}'. Użyj: history [N] lub history clear")
        write("\n")
        return

    _history_print(_history_load(), limit)


# ── Kolejka pobierania ───────────────────────────────────────────────────────

"""
Kolejka jest listą słowników zapisaną w _QUEUE_FILE (JSON).
Każda pozycja:
  { "url": str, "fmt_key": str, "out_dir": str, "added": str (ISO), "skip": bool }
"""


def _queue_load() -> list[dict]:
    return _load_json_list(_QUEUE_FILE, "Kolejka")


def _queue_save(q: list[dict]) -> None:
    try:
        _atomic_json_write(_QUEUE_FILE, q)
    except Exception as e:
        _err(f"Nie można zapisać kolejki: {e}")


def _queue_print(q: list[dict]) -> None:
    if not q:
        write(f"\n  {A.DIM}Kolejka jest pusta.{A.RESET}\n\n")
        return

    write(f"\n  {A.BOLD}Kolejka pobierania  ({len(q)} pozycji):{A.RESET}\n\n")
    write(f"  {A.DIM}{'─'*68}{A.RESET}\n")
    for i, item in enumerate(q, 1):
        skip_tag = f"  {A.BYELLOW}[pominięta]{A.RESET}" if item.get("skip") else ""
        fmt_label = _FORMATS.get(item["fmt_key"], ("?", ""))[0]
        url_short  = item["url"][:50] + "…" if len(item["url"]) > 50 else item["url"]
        out_short  = item["out_dir"]
        write(
            f"  {A.BYELLOW}{i:>2}.{A.RESET}  {A.BWHITE}{url_short}{A.RESET}{skip_tag}\n"
            f"        {A.DIM}format: {fmt_label}   →  {out_short}{A.RESET}\n"
        )
    write(f"  {A.DIM}{'─'*68}{A.RESET}\n\n")


def _cmd_queue(args: list[str], terminal=None) -> None:
    """Zarządzaj kolejką pobierania.

    Podkomendy:
      queue add <URL> [fmt 1-6] [ścieżka]   Dodaj do kolejki
      queue list                              Pokaż kolejkę
      queue skip <nr>                         Oznacz pozycję jako pominiętą
      queue unskip <nr>                       Cofnij pominięcie
      queue clear                             Wyczyść całą kolejkę
      queue run                               Pobierz wszystkie (niepominięte) pozycje
    """
    if not _has_ytdlp():
        _err("Zainstaluj yt-dlp:  pip install yt-dlp")
        return

    sub = args[0] if args else "list"

    # ── queue list ────────────────────────────────────────────────────────────
    if sub == "list":
        _queue_print(_queue_load())
        return

    # ── queue clear ───────────────────────────────────────────────────────────
    if sub == "clear":
        q = _queue_load()
        if not q:
            _info("Kolejka jest już pusta.")
            write("\n")
            return
        if _confirm(f"Usunąć {len(q)} pozycji z kolejki?", default=False):
            _queue_save([])
            _ok("Kolejka wyczyszczona.")
        else:
            _info("Anulowano.")
        write("\n")
        return

    # ── queue add <URL> [fmt] [ścieżka] ──────────────────────────────────────
    if sub == "add":
        rest = args[1:]
        if not rest:
            write(f"  {A.BYELLOW}Użycie:{A.RESET}  queue add <URL> [format 1-6] [ścieżka]\n")
            return
        url = rest[0]
        if not _validate_url(url):
            _err("Nieprawidłowy lub nieobsługiwany URL.")
            return
        fmt_key = rest[1] if len(rest) > 1 else "1"
        if fmt_key not in _FORMATS:
            _err("Format musi być 1–6 (domyślnie 1).")
            return
        out_dir = str(Path(rest[2]).expanduser().resolve()) if len(rest) > 2 else str(_DEFAULT_DIR)

        q = _queue_load()
        entry = {
            "url":     url,
            "fmt_key": fmt_key,
            "out_dir": out_dir,
            "added":   datetime.now().isoformat(timespec="seconds"),
            "skip":    False,
        }
        q.append(entry)
        _queue_save(q)
        fmt_label = _FORMATS[fmt_key][0]
        write(
            f"\n  {A.BGREEN}✔{A.RESET}  Dodano do kolejki jako pozycja {A.BYELLOW}#{len(q)}{A.RESET}\n"
            f"     {A.DIM}{url[:60]}   format: {fmt_label}{A.RESET}\n\n"
        )
        return

    # ── queue skip / unskip <nr> ──────────────────────────────────────────────
    if sub in ("skip", "unskip"):
        rest = args[1:]
        if not rest or not rest[0].isdigit():
            write(f"  {A.BYELLOW}Użycie:{A.RESET}  queue {sub} <numer>\n")
            return
        nr = int(rest[0])
        q  = _queue_load()
        if nr < 1 or nr > len(q):
            _err(f"Brak pozycji #{nr} (kolejka ma {len(q)} elementów).")
            write("\n")
            return
        q[nr - 1]["skip"] = (sub == "skip")
        _queue_save(q)
        verb = "Pominięto" if sub == "skip" else "Przywrócono"
        _ok(f"{verb} pozycję #{nr}.")
        write("\n")
        return

    # ── queue run ─────────────────────────────────────────────────────────────
    if sub == "run":
        q = _queue_load()
        active = [(i, item) for i, item in enumerate(q) if not item.get("skip")]
        if not active:
            _info("Brak pozycji do pobrania (kolejka pusta lub wszystkie pominięte).")
            write("\n")
            return

        write(
            f"\n  {A.BOLD}{A.BCYAN}"
            f"  ╭──────────────────────────────────────────────────╮\n"
            f"  ║   ▶  video_dwl  —  uruchamiam kolejkę            ║\n"
            f"  ╰──────────────────────────────────────────────────╯{A.RESET}\n\n"
        )
        total     = len(active)
        success   = 0
        failed: list[int] = []
        t_start   = datetime.now()

        for pos, (idx, item) in enumerate(active, 1):
            fk        = item["fmt_key"]
            fmt_label = _FORMATS[fk][0]
            write(
                f"  {A.BOLD}{A.BCYAN}[{pos}/{total}]{A.RESET}  "
                f"{A.DIM}{item['url'][:54]}{A.RESET}  "
                f"{A.DIM}({fmt_label}){A.RESET}\n\n"
            )
            flush()
            t_item = datetime.now()
            out_dir = Path(item["out_dir"])
            ok = _download(item["url"], _FORMATS[fk][1], out_dir,
                           "audio" in fmt_label, fmt_key=fk)
            elapsed = (datetime.now() - t_item).seconds
            if ok is not None:
                success += 1
                _history_append({
                    "title":     ok.get("title", ""),
                    "url":       item["url"],
                    "fmt_key":   fk,
                    "fmt_label": fmt_label,
                    "filesize":  ok.get("filesize"),
                    "out_dir":   item["out_dir"],
                    "date":      datetime.now().isoformat(timespec="seconds"),
                })
                _info(f"Ukończono w {elapsed}s")
            else:
                failed.append(pos)

        # Podsumowanie
        total_elapsed = int((datetime.now() - t_start).total_seconds())
        m, s = divmod(total_elapsed, 60)
        elapsed_str = f"{m}:{s:02d}"
        write(f"  {A.DIM}{'─'*54}{A.RESET}\n")
        write(f"  {A.BGREEN}✔ Pobrano:{A.RESET}  {success}/{total}   {A.DIM}czas: {elapsed_str}{A.RESET}\n")
        if failed:
            nums = ", ".join(f"#{n}" for n in failed)
            write(f"  {A.BRED}✗ Błędy:{A.RESET}   pozycje {nums}\n")
        write("\n")

        # Usuń ukończone (te bez błędów) z kolejki.
        # failed zawiera 1-based numery pozycji w active (nie w q).
        # Mapujemy je z powrotem na oryginalne indeksy w q.
        failed_active_positions = {pos - 1 for pos in failed}  # 0-based w active
        error_idxs = {active[p][0] for p in failed_active_positions}  # idx w q
        remaining  = [item for i, item in enumerate(q) if i in error_idxs or item.get("skip")]
        _queue_save(remaining)
        if not remaining:
            _info("Kolejka wyczyszczona po zakończeniu.")
            write("\n")
        return

    # Nieznana podkomenda
    _err(f"Nieznana podkomenda: '{sub}'. Użyj: add, list, skip, unskip, clear, run")
    write("\n")


# ── Menu interaktywne (cml_menu) ─────────────────────────────────────────────

def cml_menu() -> None:
    """Wyświetla interaktywne menu modułu video_dwl."""
    if not _has_ytdlp():
        write(
            f"\n  {A.BRED}✗ Brak yt-dlp!{A.RESET}\n"
            f"  Zainstaluj:  {A.BYELLOW}pip install yt-dlp{A.RESET}\n\n"
        )
        return

    write(
        f"\n{A.BOLD}{A.BCYAN}"
        f"  ╭────────────────────────────────────────────╮\n"
        f"  ║   ▶  video_dwl  v1.9  —  Video Downloader  ║\n"
        f"  ╰────────────────────────────────────────────╯{A.RESET}\n\n"
    )

    # ── URL ──────────────────────────────────────────────────────────────────
    url = _ask("URL (YouTube, Vimeo, Twitch…):")
    if not url:
        _info("Anulowano.")
        write("\n")
        return
    if not _validate_url(url):
        _err("Nieprawidłowy lub nieobsługiwany URL.")
        write("\n")
        return
    site = _detect_site(url)
    write(f"  {A.DIM}Wykryto serwis:{A.RESET}  {A.BCYAN}{site}{A.RESET}\n\n")

    # ── Format ───────────────────────────────────────────────────────────────
    write(f"  {A.BOLD}Wybierz format:{A.RESET}\n\n")
    for k, (label, _) in _FORMATS.items():
        write(f"    {A.BYELLOW}{k}{A.RESET}  {label}\n")
    write("\n")

    fmt_key = _ask("Wybierz format [1-6]:", default="1")
    if fmt_key not in _FORMATS:
        _err("Nieznany format.")
        write("\n")
        return

    # ── Folder docelowy ───────────────────────────────────────────────────────
    write(f"\n  {A.DIM}Domyślny folder:{A.RESET} {A.BCYAN}{_DEFAULT_DIR}{A.RESET}\n")
    if _confirm("Zmienić folder zapisu?", default=False):
        raw = _ask("Ścieżka:", default=str(_DEFAULT_DIR))
        out_dir = Path(raw).expanduser().resolve()
    else:
        out_dir = _DEFAULT_DIR

    # ── Potwierdzenie ─────────────────────────────────────────────────────────
    fmt_label, _ = _FORMATS[fmt_key]
    write(
        f"\n  {A.BOLD}Format:{A.RESET}  {A.CYAN}{fmt_label}{A.RESET}\n"
        f"  {A.BOLD}Folder:{A.RESET}  {A.CYAN}{out_dir}{A.RESET}\n\n"
    )
    if not _confirm("Rozpocząć pobieranie?"):
        _info("Anulowano.")
        write("\n")
        return

    write(f"\n  {A.BGREEN}▶  Pobieranie…{A.RESET}\n\n")
    flush()
    _run_download(url, fmt_key, out_dir)


# ── Komendy CML ──────────────────────────────────────────────────────────────

def _cmd_get(args: list[str], terminal=None) -> None:
    """Pobierz film:  get <URL> [format_nr] [ścieżka]
                      get --reuse <nr>  (powtórz wpis z historii)
                      get --no-cache <URL> [format_nr] [ścieżka]
    Przykłady:
      get https://youtu.be/XXXXX
      get https://youtu.be/XXXXX 3
      get https://youtu.be/XXXXX 5 ~/Muzyka
      get --reuse 7
      get --no-cache https://youtu.be/XXXXX
    """
    if not _has_ytdlp():
        _err("Zainstaluj yt-dlp:  pip install yt-dlp")
        return

    if not args:
        write(f"  {A.BYELLOW}Użycie:{A.RESET}  get <URL> [format 1-6] [ścieżka]\n"
              f"           get --reuse <nr>\n"
              f"           get --no-cache <URL> [format 1-6] [ścieżka]\n")
        return

    # ── flaga --no-cache ───────────────────────────────────────────────────────
    force_fetch = False
    if args[0] == "--no-cache":
        force_fetch = True
        args = args[1:]
        if not args:
            write(f"  {A.BYELLOW}Użycie:{A.RESET}  get --no-cache <URL> [format 1-6] [ścieżka]\n")
            return

    # ── tryb --reuse ──────────────────────────────────────────────────────────
    if args[0] == "--reuse":
        if len(args) < 2 or not args[1].isdigit():
            write(f"  {A.BYELLOW}Użycie:{A.RESET}  get --reuse <numer z historii>\n")
            return
        nr = int(args[1])
        h  = _history_load()
        if nr < 1 or nr > len(h):
            _err(f"Brak wpisu #{nr} (historia ma {len(h)} pozycji).")
            write("\n")
            return
        item = h[nr - 1]
        title = (item.get("title") or item["url"])[:54]
        write(
            f"\n  {A.BOLD}Ponawiam:{A.RESET}  {A.BWHITE}{title}{A.RESET}\n"
            f"  {A.DIM}format: {item.get('fmt_label', '?')}   →  {item['out_dir']}{A.RESET}\n\n"
        )
        if not _confirm("Rozpocząć pobieranie?"):
            _info("Anulowano.")
            write("\n")
            return
        _run_download(item["url"], item["fmt_key"], Path(item["out_dir"]), force_fetch)
        return

    # ── tryb normalny ─────────────────────────────────────────────────────────
    url = args[0]
    if not _validate_url(url):
        _err("Nieprawidłowy lub nieobsługiwany URL.")
        return

    fmt_key = args[1] if len(args) > 1 else "1"
    if fmt_key not in _FORMATS:
        _err("Format musi być 1–6 (domyślnie 1).")
        return

    out_dir = Path(args[2]).expanduser().resolve() if len(args) > 2 else _DEFAULT_DIR
    _run_download(url, fmt_key, out_dir, force_fetch)


def _cmd_info(args: list[str], terminal=None) -> None:
    """Pokaż informacje o filmie/playliście bez pobierania:  info <URL> [--no-cache]"""
    if not _has_ytdlp():
        _err("Zainstaluj yt-dlp:  pip install yt-dlp")
        return
    if not args:
        write(f"  {A.BYELLOW}Użycie:{A.RESET}  info <URL> [--no-cache]\n")
        return

    force = "--no-cache" in args
    url_args = [a for a in args if a != "--no-cache"]
    url = url_args[0] if url_args else ""

    if not _validate_url(url):
        _err("Nieprawidłowy lub nieobsługiwany URL.")
        return
    _info("Pobieranie informacji…")
    flush()
    info = _fetch_info(url, force=force)
    if info:
        _show_info(info)


def _cmd_formats(args: list[str], terminal=None) -> None:
    """Wyświetl dostępne formaty pobierania."""
    write(f"\n  {A.BOLD}Formaty video_dwl:{A.RESET}\n\n")
    write(f"  {A.DIM}{'─'*58}{A.RESET}\n")
    for k, (label, fmt) in _FORMATS.items():
        write(f"  {A.BYELLOW}{k}{A.RESET}  {A.BWHITE}{label}{A.RESET}\n")
        write(f"     {A.DIM}{fmt}{A.RESET}\n")
    write(f"  {A.DIM}{'─'*58}{A.RESET}\n\n")


def _cmd_sites(args: list[str], terminal=None) -> None:
    """Lista znanych serwisów (yt-dlp obsługuje ich ponad 1000)."""
    # Grupuj domeny pod jedną nazwą serwisu
    grouped: dict[str, list[str]] = {}
    for name, domain in _KNOWN_SITES:
        grouped.setdefault(name, []).append(domain)

    write(f"\n  {A.BOLD}Znane serwisy video_dwl:{A.RESET}\n\n")
    write(f"  {A.DIM}{'─'*50}{A.RESET}\n")
    for name, domains in grouped.items():
        write(f"  {A.BYELLOW}▸{A.RESET}  {A.BWHITE}{name:<14}{A.RESET}  {A.DIM}{', '.join(domains)}{A.RESET}\n")
    write(
        f"  {A.DIM}{'─'*50}{A.RESET}\n"
        f"\n  {A.DIM}yt-dlp obsługuje ponad 1000 serwisów — każdy publiczny\n"
        f"  URL z wideo zadziała, nawet jeśli nie ma go na liście.{A.RESET}\n\n"
    )



# ── Wyszukiwanie plików ───────────────────────────────────────────────────────

# Rozszerzenia traktowane jako pliki wideo/audio
_MEDIA_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv",
    ".m4v", ".ts", ".3gp",
    ".mp3", ".m4a", ".aac", ".opus", ".ogg", ".flac", ".wav",
}


def _parse_size(s: str) -> int | None:
    """Parsuje '10M', '500K', '2G' → bajty. Zwraca None przy błędzie."""
    s = s.strip().upper()
    units = {"B": 1, "K": 1024, "KB": 1024, "M": 1024**2, "MB": 1024**2,
             "G": 1024**3, "GB": 1024**3}
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)([BKMG][B]?)$", s)
    if not m:
        m = re.match(r"^([0-9]+(?:\.[0-9]+)?)$", s)
        if m:
            return int(float(m.group(1)))
        return None
    return int(float(m.group(1)) * units.get(m.group(2), 1))


def _cmd_find(args: list[str], terminal=None) -> None:
    """Wyszukaj pobrane pliki wideo/audio na dysku.

    Użycie:
      find [wzorzec]                  Szukaj po nazwie (glob/podstring)
      find --dir <ścieżka>            Folder do przeszukania (def. ~/Pobrane/Wideo)
      find --ext mp4,mkv,mp3         Filtruj po rozszerzeniach (przecinek)
      find --sort size|date|name     Porządek sortowania (def. name)
      find --sort size --desc        Odwróć kierunek sortowania
      find --min-size <rozmiar>      Minimalny rozmiar (np. 10M, 500K, 1G)
      find --max-size <rozmiar>      Maksymalny rozmiar
      find --limit N                 Maks. liczba wyników (def. 50)
      find --no-recurse              Tylko pierwszy poziom katalogu

    Przykłady:
      find                           Lista wszystkich plików wideo/audio
      find python                    Filmy z "python" w nazwie
      find --ext mp3,m4a --sort size Pliki audio posortowane wg rozmiaru
      find --min-size 100M           Duże pliki (≥ 100 MB)
      find --dir ~/Desktop --ext mp4
    """
    # ── Parsowanie argumentów ─────────────────────────────────────────────────
    pattern:    str | None = None
    search_dir: Path       = _DEFAULT_DIR
    exts:       set[str]   = set()
    sort_by:    str        = "name"   # name | size | date
    descending: bool       = False
    min_bytes:  int | None = None
    max_bytes:  int | None = None
    limit:      int        = 50
    recurse:    bool       = True

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--dir":
            i += 1
            if i >= len(args):
                _err("--dir wymaga ścieżki.")
                return
            search_dir = Path(args[i]).expanduser().resolve()
        elif a == "--ext":
            i += 1
            if i >= len(args):
                _err("--ext wymaga listy rozszerzeń.")
                return
            exts = {"." + e.lstrip(".").lower() for e in args[i].split(",")}
        elif a == "--sort":
            i += 1
            if i >= len(args) or args[i] not in ("size", "date", "name"):
                _err("--sort przyjmuje: size, date, name.")
                return
            sort_by = args[i]
        elif a == "--desc":
            descending = True
        elif a == "--min-size":
            i += 1
            if i >= len(args):
                _err("--min-size wymaga wartości (np. 10M).")
                return
            min_bytes = _parse_size(args[i])
            if min_bytes is None:
                _err(f"Nieprawidłowy rozmiar: '{args[i]}' (np. 10M, 500K, 2G).")
                return
        elif a == "--max-size":
            i += 1
            if i >= len(args):
                _err("--max-size wymaga wartości (np. 500M).")
                return
            max_bytes = _parse_size(args[i])
            if max_bytes is None:
                _err(f"Nieprawidłowy rozmiar: '{args[i]}'.")
                return
        elif a == "--limit":
            i += 1
            if i >= len(args) or not args[i].isdigit():
                _err("--limit wymaga liczby całkowitej.")
                return
            limit = int(args[i])
        elif a == "--no-recurse":
            recurse = False
        elif a.startswith("--"):
            _err(f"Nieznana opcja: '{a}'. Użyj: find --help.")
            return
        else:
            # Wolny argument → wzorzec nazwy
            pattern = a
        i += 1

    # Jeśli nie podano --ext, szukaj wszystkich znanych typów mediów
    active_exts = exts if exts else _MEDIA_EXTENSIONS

    # ── Skanowanie katalogu ───────────────────────────────────────────────────
    if not search_dir.exists():
        _err(f"Folder nie istnieje: {search_dir}")
        write(f"  {A.DIM}Użyj: find --dir <ścieżka>{A.RESET}\n\n")
        return

    _info(f"Szukam w: {search_dir}" + ("" if recurse else "  [bez podkatalogów]"))
    flush()

    try:
        iter_fn = search_dir.rglob("*") if recurse else search_dir.glob("*")
        all_files = [f for f in iter_fn if f.is_file()]
    except PermissionError as e:
        _err(f"Brak uprawnień: {e}")
        return

    # ── Filtrowanie ───────────────────────────────────────────────────────────
    results: list[tuple[Path, int, float]] = []   # (path, size, mtime)
    pattern_low = pattern.lower() if pattern else None

    for f in all_files:
        if f.suffix.lower() not in active_exts:
            continue
        if pattern_low and pattern_low not in f.name.lower():
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        sz = st.st_size
        mt = st.st_mtime
        if min_bytes is not None and sz < min_bytes:
            continue
        if max_bytes is not None and sz > max_bytes:
            continue
        results.append((f, sz, mt))

    # ── Sortowanie ────────────────────────────────────────────────────────────
    if sort_by == "size":
        results.sort(key=lambda x: x[1], reverse=descending)
    elif sort_by == "date":
        results.sort(key=lambda x: x[2], reverse=descending)
    else:  # name
        results.sort(key=lambda x: x[0].name.lower(), reverse=descending)

    # ── Wyświetlenie wyników ──────────────────────────────────────────────────
    total_found = len(results)
    shown       = results[:limit]
    total_size  = sum(sz for _, sz, _ in results)

    write(f"\n  {A.BOLD}Znalezione pliki mediów{A.RESET}"
          f"  {A.DIM}({total_found} plików"
          + (f", pokazuję {len(shown)}" if total_found > limit else "")
          + f"){A.RESET}\n\n")

    if not shown:
        write(f"  {A.DIM}Brak plików pasujących do kryteriów.{A.RESET}\n")
        if not search_dir.exists() or not any(True for _ in search_dir.iterdir()):
            write(f"  {A.DIM}Folder jest pusty lub nie istnieje.{A.RESET}\n")
        write("\n")
        return

    # Nagłówek tabeli
    write(
        f"  {A.DIM}{'#':>3}  {'Nazwa':<52}  {'Rozmiar':>9}  {'Data':<10}  Ext{A.RESET}\n"
        f"  {A.DIM}{'─'*3}  {'─'*52}  {'─'*9}  {'─'*10}  {'─'*6}{A.RESET}\n"
    )

    for idx, (fpath, sz, mt) in enumerate(shown, 1):
        name   = fpath.name
        name_s = (name[:51] + "…") if len(name) > 52 else name
        ext    = fpath.suffix.lower().lstrip(".")
        sz_s   = _fmt_sz(sz)
        date_s = datetime.fromtimestamp(mt).strftime("%Y-%m-%d")

        # Koloruj rozszerzenie (video vs audio)
        audio_exts = {".mp3", ".m4a", ".aac", ".opus", ".ogg", ".flac", ".wav"}
        ext_color  = A.BYELLOW if fpath.suffix.lower() in audio_exts else A.BCYAN

        write(
            f"  {A.DIM}{idx:>3}{A.RESET}  "
            f"{A.BWHITE}{name_s:<52}{A.RESET}  "
            f"{A.DIM}{sz_s:>9}{A.RESET}  "
            f"{A.DIM}{date_s:<10}{A.RESET}  "
            f"{ext_color}{ext:<6}{A.RESET}\n"
        )

    write(f"  {A.DIM}{'─'*3}  {'─'*52}  {'─'*9}  {'─'*10}  {'─'*6}{A.RESET}\n")

    # Podsumowanie
    write(
        f"\n  {A.DIM}Łącznie: {total_found} plik/ów   "
        f"Rozmiar: {_fmt_sz(total_size)}   "
        f"Folder: {search_dir}{A.RESET}\n"
    )
    if total_found > limit:
        write(f"  {A.BYELLOW}Pokazano {limit} z {total_found}. Użyj --limit N aby zobaczyć więcej.{A.RESET}\n")
    write("\n")


# ── Wyszukiwanie YouTube ──────────────────────────────────────────────────────

_SEARCH_CACHE_TTL = 3600 * 2   # 2 h — TTL cache wyników wyszukiwania


def _result_url(entry: dict) -> str:
    """Zwraca kanoniczny URL wideo z wpisu yt-dlp (lub pusty string)."""
    url = entry.get("url") or entry.get("webpage_url") or ""
    if url and _validate_url(url):
        return url
    vid_id = entry.get("id", "")
    if vid_id:
        return f"https://www.youtube.com/watch?v={vid_id}"
    return ""


def _yt_search(query: str, limit: int = 10, force: bool = False) -> list[dict]:
    """Zwraca listę wyników wyszukiwania YouTube (przez yt-dlp ytsearch:).

    Używa extract_flat="in_playlist" — szybsze niż pełne info, ale zawiera
    view_count, duration, channel, upload_date w przeciwieństwie do extract_flat=True.
    Wyniki cachowane pod kluczem (query, limit) — zmiana limitu to nowy wpis.
    """
    import socket
    cache_key_url = f"__ytsearch__{limit}__{query}"
    if not force:
        cached = cache_get(cache_key_url, "info")
        if cached and isinstance(cached.get("entries"), list):
            _info("Wyniki z cache  (użyj --no-cache aby odświeżyć)")
            return [e for e in cached["entries"] if e]

    yt_dlp = _ytdlp_module
    opts = {
        "quiet":          True,
        "no_warnings":    True,
        "skip_download":  True,
        "extract_flat":   "in_playlist",   # bogatsza flat niż True
        "socket_timeout": 20,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        entries = [e for e in (data.get("entries") or []) if e]
        if entries:
            cache_put(cache_key_url, "info", data)
        return entries
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "timed out" in msg.lower() or isinstance(e.__cause__, socket.timeout):
            _err("Timeout wyszukiwania. Sprawdź połączenie sieciowe.")
        else:
            _err(f"Błąd wyszukiwania: {msg}")
        return []
    except socket.timeout:
        _err("Timeout sieci przy wyszukiwaniu.")
        return []
    except Exception as e:
        _err(f"Nieoczekiwany błąd wyszukiwania: {e}")
        return []


def _apply_search_filters(
    results: list[dict],
    filter_kw: str | None,
    sort_by: str | None,
    sort_desc: bool,
    only_video: bool,
) -> list[dict]:
    """Filtruje i sortuje wyniki wyszukiwania po stronie klienta."""
    out = list(results)

    # Odfiltruj typy inne niż "video" (playlisty, kanały) — zawsze
    out = [e for e in out if e.get("_type") != "playlist"
                            and e.get("_type") != "channel"]

    # --filter: odrzuć wyniki których tytuł zawiera frazę
    if filter_kw:
        fkw_low = filter_kw.lower()
        out = [e for e in out if fkw_low not in (e.get("title") or "").lower()]

    # Opcjonalnie ogranicz do czystych wideo (brak na żywo / Shorts)
    if only_video:
        out = [e for e in out
               if not e.get("is_live")
               and (e.get("duration") or 0) > 60]   # Shorts ≤ 60s

    # Sortowanie po stronie klienta
    if sort_by == "views":
        out.sort(key=lambda e: e.get("view_count") or 0, reverse=sort_desc)
    elif sort_by == "date":
        out.sort(key=lambda e: e.get("upload_date") or "", reverse=sort_desc)
    elif sort_by == "dur":
        out.sort(key=lambda e: e.get("duration") or 0, reverse=sort_desc)

    return out


def _print_search_results(
    results: list[dict], query: str, offset: int = 0
) -> None:
    """Wyświetla tabelę wyników wyszukiwania.

    offset — numer pierwszego wyniku na liście (domyślnie 0, +N po 'more')
    """
    write(
        f"\n  {A.BOLD}{A.BCYAN}Wyniki YouTube:{A.RESET}  "
        f"{A.DIM}\"{query}\"{A.RESET}"
        + (f"  {A.DIM}(wyniki {offset+1}–{offset+len(results)}){A.RESET}" if offset else "")
        + "\n\n"
    )
    write(
        f"  {A.DIM}{'Nr':>3}  {'Tytuł':<48}  {'Czas':>7}  {'Kanał':<20}  {'Data':<10}  Wyświetlenia{A.RESET}\n"
        f"  {A.DIM}{'─'*3}  {'─'*48}  {'─'*7}  {'─'*20}  {'─'*10}  {'─'*13}{A.RESET}\n"
    )
    for i, e in enumerate(results, 1):
        nr      = offset + i
        title   = (e.get("title") or "?")
        title_s = (title[:47] + "…") if len(title) > 48 else title
        dur     = _fmt_dur(e.get("duration"))
        channel = (e.get("channel") or e.get("uploader") or "?")[:20]
        views   = e.get("view_count")
        views_s = f"{int(views):,}".replace(",", "\u00a0") if views else "—"
        date_s  = _fmt_date(e.get("upload_date")) if e.get("upload_date") else "—"
        live    = f" {A.BRED}LIVE{A.RESET}" if e.get("is_live") else ""
        write(
            f"  {A.BYELLOW}{nr:>3}{A.RESET}  "
            f"{A.BWHITE}{title_s:<48}{A.RESET}  "
            f"{A.DIM}{dur:>7}{A.RESET}  "
            f"{A.BCYAN}{channel:<20}{A.RESET}  "
            f"{A.DIM}{date_s:<10}{A.RESET}  "
            f"{A.DIM}{views_s}{A.RESET}{live}\n"
        )
    write(f"  {A.DIM}{'─'*3}  {'─'*48}  {'─'*7}  {'─'*20}  {'─'*10}  {'─'*13}{A.RESET}\n\n")


def _cmd_search(args: list[str], terminal=None) -> None:
    """Wyszukaj wideo na YouTube i opcjonalnie pobierz wybrany wynik.

    Użycie:
      search <zapytanie>                    Szukaj (domyślnie 10 wyników)
      search <zapytanie> --limit N          Liczba wyników (1–50, def. 10)
      search <zapytanie> --no-cache         Pomiń cache, pobierz świeże dane
      search <zapytanie> --filter <słowo>   Wyklucz wyniki z danym słowem w tytule
      search <zapytanie> --sort views|date|dur  Sortuj wyniki
      search <zapytanie> --desc             Odwróć kierunek sortowania
      search <zapytanie> --video            Tylko filmy (bez Shorts i live)
      search <zapytanie> --get N [fmt]      Pobierz wynik nr N (fmt 1–6, def. 1)
      search <zapytanie> --queue N [fmt]    Dodaj wynik nr N do kolejki

    Tryb interaktywny (po wyświetleniu listy wyników):
      <nr>            pobierz wynik nr N (format domyślny 1)
      <nr> <fmt>      pobierz wynik nr N w formacie 1–6
      q <nr> [fmt]    dodaj do kolejki
      i <nr>          pokaż szczegółowe informacje o filmie
      m [N]           załaduj kolejnych N wyników (def. +10)
      Enter / 0       anuluj i wyjdź

    Przykłady:
      search python tutorial
      search lofi mix --limit 5 --sort views
      search rickroll --get 1 3
      search synthwave --filter \"shorts\" --video
    """
    if not _has_ytdlp():
        _err("Zainstaluj yt-dlp:  pip install yt-dlp")
        return

    if not args:
        write(
            f"  {A.BYELLOW}Użycie:{A.RESET}  search <zapytanie> [opcje]\n"
            f"  {A.DIM}Opcje: --limit N  --no-cache  --filter <słowo>  --sort views|date|dur{A.RESET}\n"
            f"  {A.DIM}       --desc  --video  --get N [fmt]  --queue N [fmt]{A.RESET}\n"
        )
        return

    # ── Parsowanie argumentów ─────────────────────────────────────────────────
    limit      = 10
    force      = False
    action     = None     # 'get' | 'queue' | None (interactive)
    action_nr  = None
    action_fmt = "1"
    filter_kw  = None
    sort_by    = None     # 'views' | 'date' | 'dur' | None
    sort_desc  = True     # domyślnie malejąco (views desc, date desc)
    only_video = False
    query_parts: list[str] = []

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--limit":
            i += 1
            if i >= len(args) or not args[i].isdigit():
                _err("--limit wymaga liczby całkowitej.")
                return
            limit = max(1, min(50, int(args[i])))
        elif a == "--no-cache":
            force = True
        elif a == "--filter":
            i += 1
            if i >= len(args):
                _err("--filter wymaga słowa kluczowego.")
                return
            filter_kw = args[i]
        elif a == "--sort":
            i += 1
            if i >= len(args) or args[i] not in ("views", "date", "dur"):
                _err("--sort przyjmuje: views, date, dur.")
                return
            sort_by = args[i]
        elif a == "--desc":
            sort_desc = True
        elif a == "--asc":
            sort_desc = False
        elif a == "--video":
            only_video = True
        elif a in ("--get", "--queue"):
            action = "get" if a == "--get" else "queue"
            i += 1
            if i >= len(args) or not args[i].isdigit():
                _err(f"{a} wymaga numeru wyniku (np. --get 1).")
                return
            action_nr = int(args[i])
            if i + 1 < len(args) and args[i + 1] in _FORMATS:
                i += 1
                action_fmt = args[i]
        else:
            query_parts.append(a)
        i += 1

    query = " ".join(query_parts).strip()
    if not query:
        _err("Podaj zapytanie do wyszukania.")
        return

    # ── Wyszukiwanie i filtrowanie ────────────────────────────────────────────
    _info(f"Szukam na YouTube: \"{query}\"…")
    flush()
    raw_results = _yt_search(query, limit=limit, force=force)

    if not raw_results:
        _err("Brak wyników lub błąd wyszukiwania.")
        write("\n")
        return

    results = _apply_search_filters(raw_results, filter_kw, sort_by, sort_desc, only_video)

    if not results:
        _err("Wszystkie wyniki odfiltrowane. Zmień kryteria filtrowania.")
        write("\n")
        return

    _print_search_results(results, query)

    # ── Tryb nieinteraktywny (--get / --queue) ────────────────────────────────
    if action is not None and action_nr is not None:
        if action_nr < 1 or action_nr > len(results):
            _err(f"Numer {action_nr} poza zakresem (wyniki: 1–{len(results)}).")
            write("\n")
            return
        chosen = results[action_nr - 1]
        url    = _result_url(chosen)
        if not url:
            _err("Nie można ustalić URL dla wybranego wyniku.")
            write("\n")
            return
        if action == "get":
            _run_download(url, action_fmt, _DEFAULT_DIR, force_fetch=force)
        else:
            q = _queue_load()
            q.append({
                "url":     url,
                "fmt_key": action_fmt,
                "out_dir": str(_DEFAULT_DIR),
                "added":   datetime.now().isoformat(timespec="seconds"),
                "skip":    False,
            })
            _queue_save(q)
            title_s = (chosen.get("title") or url)[:54]
            write(
                f"  {A.BGREEN}✔{A.RESET}  Dodano do kolejki jako "
                f"#{A.BYELLOW}{len(q)}{A.RESET}\n"
                f"     {A.DIM}{title_s}   format: {_FORMATS[action_fmt][0]}{A.RESET}\n\n"
            )
        return

    # ── Tryb interaktywny — pętla ─────────────────────────────────────────────
    write(
        f"  {A.DIM}Polecenia:{A.RESET}\n"
        f"  {A.DIM}  <nr> [fmt]      → pobierz (fmt 1–6, def. 1){A.RESET}\n"
        f"  {A.DIM}  q <nr> [fmt]    → dodaj do kolejki{A.RESET}\n"
        f"  {A.DIM}  i <nr>          → szczegółowe info{A.RESET}\n"
        f"  {A.DIM}  m [N]           → załaduj kolejne N wyników (def. +10){A.RESET}\n"
        f"  {A.DIM}  Enter / 0       → wyjdź{A.RESET}\n\n"
    )
    flush()

    # Pętla interaktywna — trwa do jawnego wyjścia
    page_offset = 0
    while True:
        raw = _ask(f"Wybierz [1–{len(results)}]:", default="0").strip()
        if not raw or raw == "0":
            _info("Wyjście.")
            write("\n")
            return

        parts = raw.split()
        cmd0  = parts[0].lower()

        # ── m [N] — more: załaduj kolejne wyniki ─────────────────────────────
        if cmd0 == "m":
            extra = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
            extra = max(1, min(50, extra))
            new_limit = limit + extra
            _info(f"Ładowanie kolejnych {extra} wyników…")
            flush()
            raw_results2 = _yt_search(query, limit=new_limit, force=True)
            new_filtered = _apply_search_filters(
                raw_results2, filter_kw, sort_by, sort_desc, only_video
            )
            if len(new_filtered) <= len(results):
                _info("Brak nowych wyników do załadowania.")
                write("\n")
            else:
                new_entries = new_filtered[len(results):]
                page_offset = len(results)
                _print_search_results(new_entries, query, offset=page_offset)
                results = new_filtered
                limit = new_limit
            continue

        # ── i <nr> — info ─────────────────────────────────────────────────────
        if cmd0 == "i":
            if len(parts) < 2 or not parts[1].isdigit():
                _err("Użycie: i <numer>")
                continue
            nr = int(parts[1])
            if nr < 1 or nr > len(results):
                _err(f"Numer {nr} poza zakresem (1–{len(results)}).")
                continue
            chosen = results[nr - 1]
            url = _result_url(chosen)
            if not url:
                _err("Brak URL dla tego wyniku.")
                continue
            _info("Pobieranie szczegółowych metadanych…")
            flush()
            info = _fetch_info(url, force=False)
            if info:
                _show_info(info)
            continue   # wróć do pętli

        # ── q <nr> [fmt] — kolejka ────────────────────────────────────────────
        if cmd0 == "q":
            if len(parts) < 2 or not parts[1].isdigit():
                _err("Użycie: q <numer> [format 1–6]")
                continue
            nr      = int(parts[1])
            fmt_key = parts[2] if len(parts) > 2 and parts[2] in _FORMATS else "1"
            if nr < 1 or nr > len(results):
                _err(f"Numer {nr} poza zakresem (1–{len(results)}).")
                continue
            chosen = results[nr - 1]
            url = _result_url(chosen)
            if not url:
                _err("Brak URL dla tego wyniku.")
                continue
            q = _queue_load()
            q.append({
                "url":     url,
                "fmt_key": fmt_key,
                "out_dir": str(_DEFAULT_DIR),
                "added":   datetime.now().isoformat(timespec="seconds"),
                "skip":    False,
            })
            _queue_save(q)
            title_s = (chosen.get("title") or url)[:54]
            write(
                f"  {A.BGREEN}✔{A.RESET}  Dodano do kolejki #{A.BYELLOW}{len(q)}{A.RESET}  "
                f"{A.DIM}{title_s}{A.RESET}\n\n"
            )
            continue   # wróć do pętli

        # ── <nr> [fmt] — pobierz i wyjdź ─────────────────────────────────────
        nr_str  = parts[0]
        fmt_key = parts[1] if len(parts) > 1 and parts[1] in _FORMATS else "1"

        if not nr_str.isdigit():
            _err(f"Nieznane polecenie: '{raw}'. Wpisz numer, q, i, m lub 0.")
            continue

        nr = int(nr_str)
        if nr < 1 or nr > len(results):
            _err(f"Numer {nr} poza zakresem (1–{len(results)}).")
            continue

        chosen = results[nr - 1]
        url = _result_url(chosen)
        if not url:
            _err("Nie można ustalić URL dla wybranego wyniku.")
            continue

        write(
            f"\n  {A.BOLD}Wybrany:{A.RESET}  "
            f"{A.BWHITE}{(chosen.get('title') or url)[:70]}{A.RESET}\n"
            f"  {A.DIM}Format: {_FORMATS[fmt_key][0]}{A.RESET}\n\n"
        )
        _run_download(url, fmt_key, _DEFAULT_DIR, force_fetch=force)
        return   # po pobraniu wychodzimy


def _cmd_help(args: list[str], terminal=None) -> None:
    """Pomoc — lista komend modułu video_dwl."""
    cmds = {
        "get <URL> [fmt] [ścieżka]":          "Pobierz film/audio z dowolnego serwisu",
        "get --no-cache <URL> [fmt] [ścieżka]": "Pobierz z pominięciem cache",
        "get --reuse <nr>":                    "Pobierz ponownie z historii",
        "info <URL> [--no-cache]":             "Pokaż info bez pobierania",
        "formats":                             "Lista formatów (1–6)",
        "sites":                               "Lista obsługiwanych serwisów",
        "history [N]":                         "Pokaż ostatnie N pobrań (def. 20)",
        "history search <wzorzec>":            "Szukaj w historii po tytule/URL/serwisie",
        "history clear":                       "Wyczyść historię",
        "queue add <URL> [fmt] [ścieżka]":    "Dodaj do kolejki",
        "queue list":                          "Pokaż kolejkę",
        "queue skip/unskip <nr>":             "Pomiń / przywróć pozycję",
        "queue run":                           "Pobierz całą kolejkę",
        "queue clear":                         "Wyczyść kolejkę",
        "cache":                               "Zarządzaj cache metadanych",
        "cache stats":                         "Statystyki cache",
        "cache clear":                         "Wyczyść cały cache",
        "cache drop <URL>":                    "Usuń cache dla podanego URL",
        "cache list":                          "Pokaż zawartość cache",
        "search <zapytanie>":                  "Szukaj wideo na YouTube (interaktywnie)",
        "search <zapytanie> --get N [fmt]":   "Znajdź i od razu pobierz wynik nr N",
        "search <zapytanie> --queue N":       "Znajdź i dodaj wynik do kolejki",
        "search <zapytanie> --filter <słowo>":"Wyklucz wyniki zawierające słowo",
        "search <zapytanie> --sort views|date|dur": "Sortuj wyniki",
        "search <zapytanie> --video":         "Tylko filmy (bez Shorts i livestreamów)",
        "search <zapytanie> --limit N":       "Inna liczba wyników (def. 10, maks. 50)",
        "find [wzorzec] [opcje]":             "Wyszukaj pobrane pliki na dysku",
        "find --ext mp4,mkv":                 "Filtruj po rozszerzeniu",
        "find --dir <ścieżka>":               "Szukaj w innym folderze",
        "find --sort size|date|name":         "Sortowanie wyników",
        "find --min-size 10M":                "Minimalna wielkość pliku",
        "help":                                "Ta pomoc",
    }
    write(f"\n  {A.BOLD}{A.BCYAN}video  v2.3  —  komendy modułu:{A.RESET}\n\n")
    for c, d in cmds.items():
        write(f"  {A.BYELLOW}video {c:<38}{A.RESET}  {A.DIM}{d}{A.RESET}\n")
    write(
        f"\n  {A.DIM}Aliasy: yt · ytdl · youtube · vimeo · dwl{A.RESET}\n"
        f"  {A.DIM}Wpisz 'video' bez argumentów aby zobaczyć tę pomoc.{A.RESET}\n\n"
    )


def _cmd_cache(args: list[str], terminal=None) -> None:
    """Zarządzaj cache metadanych wideo.

    Podkomendy:
      cache              Pokaż statystyki (jak cache stats)
      cache stats        Statystyki: rozmiar, wpisy, TTL, trafienia
      cache list         Lista wszystkich wpisów (URL, typ, wiek, trafienia)
      cache clear        Wyczyść cały cache (po potwierdzeniu)
      cache drop <URL>   Usuń wpisy dla konkretnego URL
    """
    sub = args[0] if args else "stats"

    # ── cache stats ───────────────────────────────────────────────────────────
    if sub in ("stats", ""):
        st = cache_stats()
        write(f"\n  {A.BOLD}Cache metadanych video_dwl:{A.RESET}\n\n")
        write(f"  {A.DIM}{'─'*52}{A.RESET}\n")

        def row(icon: str, label: str, val: str) -> None:
            write(f"  {icon}  {A.BCYAN}{label:<20}{A.RESET}{A.BWHITE}{val}{A.RESET}\n")

        row("📦", "Łącznie wpisów",  f"{st['total']} / {st['max_entries']}")
        row("⏰", "Wygasłych",       str(st["expired"]))
        row("💾", "Rozmiar",         f"{st['size_mb']} MB / {st['max_mb']} MB")
        row("🎯", "Trafień łącznie", str(st["total_hits"]))

        if st["by_type"]:
            write(f"\n  {A.DIM}Według typu:{A.RESET}\n")
            for ctype, count in sorted(st["by_type"].items()):
                ttl_h = st["ttl"].get(ctype, 3600) // 3600
                write(f"    {A.BYELLOW}{ctype:<12}{A.RESET}  {count} wpisów  "
                      f"{A.DIM}(TTL {ttl_h}h){A.RESET}\n")

        write(f"\n  {A.DIM}Lokalizacja: {_CACHE_DIR}{A.RESET}\n")
        write(f"  {A.DIM}{'─'*52}{A.RESET}\n\n")
        return

    # ── cache list ────────────────────────────────────────────────────────────
    if sub == "list":
        with _cache_lock:
            index = _cache_index_load()

        if not index:
            write(f"\n  {A.DIM}Cache jest pusty.{A.RESET}\n\n")
            return

        now = datetime.now().timestamp()
        entries = sorted(index.values(), key=lambda v: v.get("ts", 0), reverse=True)

        write(f"\n  {A.BOLD}Zawartość cache  ({len(entries)} wpisów):{A.RESET}\n\n")
        write(f"  {A.DIM}{'Typ':<10}{'Wiek':>8}  {'Traf':>5}  {'Rozmiar':>8}  URL{A.RESET}\n")
        write(f"  {A.DIM}{'─'*10}{'─'*8}  {'─'*5}  {'─'*8}  {'─'*40}{A.RESET}\n")

        for meta in entries:
            ctype   = meta.get("type", "?")
            age_s   = int(now - meta.get("ts", now))
            if age_s < 60:
                age_str = f"{age_s}s"
            elif age_s < 3600:
                age_str = f"{age_s // 60}m"
            else:
                age_str = f"{age_s // 3600}h"
            ttl     = _CACHE_TTL.get(ctype, 3600)
            expired = age_s > ttl
            hits    = meta.get("hits", 0)
            size_s  = _fmt_sz(meta.get("size", 0))
            url_s   = meta.get("url", "")[:52]
            stale   = f"  {A.BRED}[wygasły]{A.RESET}" if expired else ""
            write(
                f"  {A.BYELLOW}{ctype:<10}{A.RESET}"
                f"{A.DIM}{age_str:>8}{A.RESET}  "
                f"{A.DIM}{hits:>5}{A.RESET}  "
                f"{A.DIM}{size_s:>8}{A.RESET}  "
                f"{A.BWHITE}{url_s}{A.RESET}{stale}\n"
            )
        write(f"  {A.DIM}{'─'*80}{A.RESET}\n\n")
        return

    # ── cache clear ───────────────────────────────────────────────────────────
    if sub == "clear":
        with _cache_lock:
            count = len(_cache_index_load())
        if count == 0:
            _info("Cache jest już pusty.")
            write("\n")
            return
        if _confirm(f"Usunąć {count} wpisów z cache?", default=False):
            removed = cache_clear()
            _ok(f"Cache wyczyszczony ({removed} wpisów).")
        else:
            _info("Anulowano.")
        write("\n")
        return

    # ── cache drop <URL> ──────────────────────────────────────────────────────
    if sub == "drop":
        rest = args[1:]
        if not rest:
            write(f"  {A.BYELLOW}Użycie:{A.RESET}  cache drop <URL>\n")
            return
        url = rest[0]
        if not _validate_url(url):
            _err("Nieprawidłowy URL.")
            return
        removed = cache_invalidate(url)
        if removed:
            _ok(f"Usunięto {removed} wpis/ów cache dla podanego URL.")
        else:
            _info("Brak wpisów cache dla podanego URL.")
        write("\n")
        return

    _err(f"Nieznana podkomenda: '{sub}'. Użyj: stats, list, clear, drop")
    write("\n")


# ── Rejestr komend ────────────────────────────────────────────────────────────

CML_COMMANDS: dict[str, object] = {
    "get":     _cmd_get,
    "info":    _cmd_info,
    "formats": _cmd_formats,
    "sites":   _cmd_sites,
    "history": _cmd_history,
    "queue":   _cmd_queue,
    "cache":   _cmd_cache,
    "find":    _cmd_find,
    "search":  _cmd_search,
    "help":    _cmd_help,
}


# ── Standalone (python video_dwl.py) ─────────────────────────────────────────

if __name__ == "__main__":
    cml_menu()


# ── EcoSystem integration ─────────────────────────────────────────────────────

def setup(terminal):
    """Rejestruje komendę 'video' w TerminalX EcoSystem."""
    _t = terminal.t

    def _video(args, terminal=terminal):
        if not args:
            _cmd_help([], terminal)
            return
        sub  = args[0].lower()
        rest = args[1:]
        if sub in CML_COMMANDS:
            CML_COMMANDS[sub](rest, terminal)
        else:
            write(
                f"  {A.BRED}✗ Nieznana podkomenda: '{sub}'{A.RESET}  "
                f"—  wpisz {A.BYELLOW}video help{A.RESET} po pełną listę.\n"
            )

    terminal.register_command(
        "video", _video,
        description=_t("cmd_video"),
        category=_t("cat_ecosystem"),
    )
    # aliasy zgodne z crossterm-header modułu
    for alias in ("yt", "ytdl", "youtube", "vimeo", "dwl"):
        terminal.register_command(
            alias, _video,
            description=_t("cmd_video_alias", alias=alias),
            category=_t("cat_ecosystem"),
        )


def teardown(terminal):
    """Wyrejestrowuje komendy video_downloader z TerminalX EcoSystem."""
    for cmd in ("video", "yt", "ytdl", "youtube", "vimeo", "dwl"):
        terminal.commands.pop(cmd, None)
