"""Cross-module integration bridge for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski

Centralny punkt integracji modulow. Zamiast bezposrednich importow miedzy
modulami (ktore tworza cykliczne zaleznosci), moduly moga tutaj
rejestrowac i pobierac serwisy w czasie dzialania.

Wzorzec: lazy service registry.
  - Modul X rejestruje swoje publiczne API przez `register(name, api_dict)`
  - Modul Y pobiera API przez `get(name)` - zwraca None jesli nieosiagalne
  - Brak twardych zaleznosci; wszystko jest opcjonalne i safe

Uzycie:
  # w sha256.py setup():
  from . import _integration
  _integration.register("sha256", {
      "compute":  _compute_hash,
      "compare":  _compare_hashes,
      "load":     _load_hashfile,
      "save":     _save_hashfile,
  })

  # w defender.py:
  from . import _integration
  digest = _integration.call("sha256", "compute", path)
  # lub (stary sposob):
  sha = _integration.get("sha256")
  if sha:
      digest, _ = sha["compute"](path)
"""

from __future__ import annotations
import os
import threading

_lock     = threading.Lock()
_registry: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Publiczne API - rejestr
# ---------------------------------------------------------------------------

def register(name: str, api: dict) -> None:
    """Zarejestruj modul pod kluczem name.

    api to slownik {klucz: callable_lub_wartosc}.
    Nadpisuje poprzednia rejestracje pod tym samym kluczem.
    """
    with _lock:
        _registry[name] = api


def unregister(name: str) -> None:
    """Wyrejestruj modul (wywolywane w teardown)."""
    with _lock:
        _registry.pop(name, None)


def get(name: str) -> dict | None:
    """Pobierz API modulu lub None jesli niezarejestrowany."""
    return _registry.get(name)


def registered() -> list[str]:
    """Zwroc liste nazw aktualnie zarejestrowanych modulow."""
    with _lock:
        return list(_registry.keys())


def is_available(name: str) -> bool:
    """Sprawdz czy modul jest zarejestrowany."""
    return name in _registry


def call(service: str, method: str, *args, default=None, **kwargs):
    """Wywolaj metode serwisu jesli dostepna; zwraca default w razie bledu.

    Skrotowa forma zamiast:
        svc = get("nazwa"); if svc and callable(svc.get("fn")): svc["fn"](...)

    Przyklad:
        digest = _integration.call("sha256", "compute", path)
        _integration.call("notify", "send", terminal, "OK", kind="ok")
    """
    svc = _registry.get(service)
    if svc is None:
        return default
    fn = svc.get(method)
    if not callable(fn):
        return default
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def status() -> dict:
    """Zwroc slownik {nazwa: lista_kluczy} dla wszystkich zarejestrowanych serwisow.

    Uzywane przez komende 'ecosystem status' do diagnostyki.
    """
    with _lock:
        return {name: sorted(api.keys()) for name, api in _registry.items()}


# ---------------------------------------------------------------------------
# Pomocnicze funkcje cross-module (uzywane bezposrednio przez moduly)
# ---------------------------------------------------------------------------

def compute_sha256(path: str) -> str | None:
    """Oblicz SHA-256 pliku. Deleguje do sha256.py jesli dostepny."""
    result = call("sha256", "compute", path)
    if result is not None:
        digest, _ = result
        return digest
    # Fallback wbudowany - nie wymaga zaladowanego modulu sha256
    import hashlib
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def log_debug_event(terminal, kind: str, msg: str) -> None:
    """Wyslij zdarzenie do logu debuggera (jesli zaladowany).

    Bezpieczne do wywolania zawsze - ignoruje bledy jesli debugger niedostepny.
    """
    call("debugger", "log_event", kind, msg)


def find_interpreter(ext: str) -> tuple[str | None, list[str]]:
    """Znajdz interpreter dla danego rozszerzenia pliku.

    Deleguje do runner.py (pelna lista 30+ jezykow).
    Zwraca (sciezka_do_interpretera, dodatkowe_args) lub (None, []).
    """
    result = call("runner", "find_interpreter", ext)
    if result is not None:
        return result

    # Fallback
    import shutil, sys
    _FB: dict[str, tuple[list[str], list[str]]] = {
        ".py":  ([sys.executable], []),
        ".js":  (["node"], []),
        ".sh":  (["bash", "sh"], []),
        ".ps1": (["pwsh", "powershell"], ["-ExecutionPolicy", "Bypass", "-File"]),
        ".rb":  (["ruby"], []),
        ".php": (["php"], []),
        ".lua": (["lua", "lua5.4"], []),
    }
    candidates, extra = _FB.get(ext.lower(), ([], []))
    for c in candidates:
        path = shutil.which(c)
        if path:
            return path, extra
    return None, []


def defender_scan_file(path: str) -> bool:
    """Sprawdz plik przez Defendera. Zwraca True jesli bezpieczny."""
    result = call("defender", "scan_file", path, default=None)
    return result if result is not None else True  # bez defendera - nie blokuj


def defender_check_integrity(path: str) -> tuple[bool | None, str, str | None]:
    """Sprawdz integralnosc pliku przez Defendera."""
    result = call("defender", "check_integrity", path)
    return result if result is not None else (None, "", None)


# ---------------------------------------------------------------------------
# imgtools helpers
# ---------------------------------------------------------------------------

def is_image_file(path: str) -> bool:
    """Sprawdz czy plik ma rozszerzenie obrazu obslugiwane przez imgtools."""
    result = call("imgtools", "is_image", path, default=None)
    if result is not None:
        return bool(result)
    # fallback bez zaladowanego modulu
    _IMG = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif",
            ".tiff", ".tif", ".ico", ".ppm", ".pgm", ".pbm"}
    return os.path.splitext(path)[1].lower() in _IMG


def img_convert(path: str, fmt: str) -> None:
    """Konwertuj plik graficzny do innego formatu (deleguje do imgtools)."""
    call("imgtools", "convert", path, fmt)


def img_thumb(path: str, size: int = 128) -> None:
    """Stworz miniature pliku graficznego (deleguje do imgtools)."""
    call("imgtools", "thumb", path, size)


# ---------------------------------------------------------------------------
# notify helpers
# ---------------------------------------------------------------------------

def notify_event(terminal, message: str, kind: str = "info",
                  title: str = "", compact: bool = True) -> None:
    """Wyslij powiadomienie (chmurke) z dowolnego modulu EcoSystemu.

    Centralny, bezpieczny punkt wejscia dla calego ekosystemu - moduly
    (defender, task, pkg, docs, trash, sandbox, ...) wywoluja te funkcje
    zamiast importowac notify.py bezposrednio, co eliminuje zaleznosci
    cykliczne i sprawia, ze wywolanie jest zawsze bezpieczne (no-op, jesli
    modul notify nie jest zaladowany).

    Parametry:
        terminal - instancja TerminalX lub None (np. w watku w tle bez
                    dostepu do obiektu terminala - uzyty zostanie wtedy
                    rejestr serwisow _integration jako fallback)
        message  - tresc powiadomienia
        kind     - info | ok | warn | err | tip
        title    - opcjonalny nadpis chmurki
        compact  - jednolinijkowy styl (domyslnie True - mniej inwazyjne
                    dla zdarzen tla / automatycznych)
    """
    try:
        notifier = getattr(terminal, "notify", None) if terminal is not None else None
        if callable(notifier):
            notifier(message, kind=kind, title=title, compact=compact)
            return
        call("notify", "send", terminal, message, kind=kind, title=title, compact=compact)
    except Exception:
        pass


def notify_event_later(terminal, message: str, delay: float = 0.0,
                        kind: str = "info", title: str = "") -> None:
    """Jak notify_event(), ale z opoznieniem (delegacja do notify.send_later)."""
    try:
        later = getattr(terminal, "notify_later", None) if terminal is not None else None
        if callable(later):
            later(message, delay, kind=kind, title=title)
            return
        call("notify", "send_later", terminal, message, delay, kind=kind, title=title)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# config helpers
# ---------------------------------------------------------------------------

def config_get(key: str, fallback=None):
    """Pobierz wartosc konfiguracji. Deleguje do config.py lub fallback None."""
    result = call("config", "get", key, fallback, default=None)
    return result if result is not None else fallback


def config_color_code(name: str) -> str:
    """Pobierz kod ANSI koloru z konfiguracji."""
    return call("config", "color_code", name, default="") or ""


# ---------------------------------------------------------------------------
# ansi helpers
# ---------------------------------------------------------------------------

def ansi_is_supported() -> bool:
    """Czy terminal obsluguje ANSI escape codes."""
    return bool(call("ansi", "is_supported", default=True))


def ansi_is_truecolor() -> bool:
    """Czy terminal obsluguje True Color (24-bit)."""
    return bool(call("ansi", "is_truecolor", default=False))


def ansi_paint(markup: str) -> str:
    """Przetworz markup [bold], [red], etc. przez ansi.paint() jesli dostepny."""
    return call("ansi", "paint", markup, default=markup) or markup


# ---------------------------------------------------------------------------
# ai helpers
# ---------------------------------------------------------------------------

def ai_send_message(text: str, system: str = "", use_history: bool = False) -> str | None:
    """Wyślij wiadomość do aktywnego modelu AI.

    Zwraca odpowiedź jako string lub None gdy moduł AI niedostępny / brak profilu.
    Bezpieczne do wywołania z dowolnego modułu — nie rzuca wyjątków.

    Parametry:
        text        - treść wiadomości
        system      - opcjonalny system prompt (nadpisuje domyślny profilu)
        use_history - czy dołączyć historię konwersacji (domyślnie False)
    """
    return call("ai", "send_message", text,
                system=system, use_history=use_history, default=None)


def ai_is_ready() -> bool:
    """Sprawdź czy moduł AI jest załadowany i ma aktywny profil."""
    result = call("ai", "is_ready", default=None)
    return bool(result) if result is not None else False


def ai_active_profile() -> dict | None:
    """Zwróć aktywny profil AI (dict z provider, model, api_key...) lub None."""
    fn = (_registry.get("ai") or {}).get("active_profile")
    if callable(fn):
        try:
            return fn()
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# venv helpers
# ---------------------------------------------------------------------------

def venv_find_library(lib: str):
    """Znajdź bibliotekę przez venv manager (ecosystem → os fallback).

    Zwraca (info_dict|None, źródło) lub (None, '') gdy venv nieosiągalny.
    """
    result = call("venv", "find_library", lib, default=None)
    if result is not None:
        return result
    return (None, "")


def venv_apply_paths() -> int:
    """Zastosuj ścieżki EcoSystem do sys.path.

    Zwraca liczbę dodanych ścieżek lub 0 gdy venv nieosiągalny.
    """
    result = call("venv", "apply_paths", default=0)
    return result if isinstance(result, int) else 0


def venv_register_installed(lib_name: str, version: str, source: str = "ecosystem") -> None:
    """Zarejestruj pakiet zainstalowany przez pkg.py w indeksie venv.

    Wywoływane przez pkg.py po udanej instalacji pip, żeby venv
    od razu wiedział o nowym pakiecie bez konieczności ręcznego
    'venv set <lib> ecosystem'.
    """
    call("venv", "register_installed", lib_name, version, source)


def venv_is_available() -> bool:
    """Sprawdź czy moduł venv jest załadowany."""
    return is_available("venv")


# ---------------------------------------------------------------------------
# trash helpers
# ---------------------------------------------------------------------------

def trash_move(path: str) -> bool:
    """Przenieś plik/katalog do .trash/.

    Deleguje do trash.move_to_trash(); fallback wbudowany (shutil.move do TRASH_DIR).
    Zwraca True przy sukcesie, False przy błędzie lub braku modułu.
    """
    result = call("trash", "move_to_trash", path, default=None)
    if result is not None:
        return bool(result)
    # fallback bez załadowanego modułu trash
    import shutil
    from datetime import datetime as _dt
    from ._shared import TRASH_DIR
    try:
        if not os.path.exists(path):
            return False
        os.makedirs(TRASH_DIR, exist_ok=True)
        name = os.path.basename(path)
        dst  = os.path.join(TRASH_DIR, name)
        if os.path.exists(dst):
            base, ext = os.path.splitext(name)
            dst = os.path.join(TRASH_DIR, f"{base}~{_dt.now().strftime('%Y%m%d_%H%M%S')}{ext}")
        shutil.move(path, dst)
        return True
    except Exception:
        return False


def trash_list() -> list:
    """Zwróć listę wpisów w .trash/ jako [{name, path, size, is_dir}]."""
    result = call("trash", "list_trash", default=None)
    if result is not None:
        return result
    # fallback bez modułu trash
    from ._shared import TRASH_DIR
    if not os.path.exists(TRASH_DIR):
        return []
    out = []
    for entry in sorted(os.listdir(TRASH_DIR)):
        full   = os.path.join(TRASH_DIR, entry)
        is_dir = os.path.isdir(full)
        size   = 0 if is_dir else os.path.getsize(full)
        out.append({"name": entry, "path": full, "size": size, "is_dir": is_dir})
    return out


def trash_ensure() -> None:
    """Upewnij się, że katalog .trash/ istnieje."""
    call("trash", "ensure_trash")


# ---------------------------------------------------------------------------
# search helpers
# ---------------------------------------------------------------------------

def search_files(pattern: str, start_dir: str = ".", extension: str = "",
                 limit: int = 50, recursive: bool = True) -> list:
    """Przeszukaj system plików przez moduł search.

    Zwraca listę ścieżek pasujących plików lub [] gdy moduł niedostępny.
    Bezpieczne do wywołania z dowolnego modułu.
    """
    svc = _registry.get("search")
    if svc is None:
        return []
    searcher_cls = svc.get("FileSearcher")
    if searcher_cls is None:
        return []
    try:
        results = []
        gen = searcher_cls.search(
            start_dir, pattern,
            extension=extension,
            recursive=recursive,
            limit=limit,
        )
        for item in gen:
            results.append(item)
            if len(results) >= limit:
                break
        return results
    except Exception:
        return []


# ---------------------------------------------------------------------------
# cache helpers
# ---------------------------------------------------------------------------

def cache_ensure() -> None:
    """Upewnij się, że katalog .cache/ istnieje."""
    call("cache", "ensure_cache")


def cache_read_index() -> dict:
    """Odczytaj główny indeks cache lub {} gdy moduł niedostępny."""
    result = call("cache", "read_index", default=None)
    return result if isinstance(result, dict) else {}


def cache_write_index(data: dict) -> bool:
    """Zapisz dane do głównego indeksu cache. Zwraca True przy sukcesie."""
    result = call("cache", "write_index", data, default=None)
    return bool(result) if result is not None else False


# ---------------------------------------------------------------------------
# history helpers
# ---------------------------------------------------------------------------

def history_get() -> list:
    """Zwróć historię komend terminala lub [] gdy moduł niedostępny."""
    result = call("history", "get_history", default=None)
    return result if isinstance(result, list) else []


def history_record(entry: str) -> None:
    """Dodaj wpis do historii komend."""
    call("history", "record", entry)


# ---------------------------------------------------------------------------
# task helpers
# ---------------------------------------------------------------------------

def task_get_all() -> dict:
    """Zwróć słownik wszystkich zadań lub {} gdy moduł niedostępny."""
    result = call("task", "get_tasks", default=None)
    return result if isinstance(result, dict) else {}


def task_is_available() -> bool:
    """Sprawdź czy moduł task jest załadowany."""
    return is_available("task")


# ---------------------------------------------------------------------------
# scripts / tools helpers
# ---------------------------------------------------------------------------

def scripts_list() -> list:
    """Zwróć listę skryptów z katalogu scripts/ lub [] gdy niedostępny."""
    result = call("scripts", "list_scripts", default=None)
    return result if isinstance(result, list) else []


def scripts_dir() -> str:
    """Zwróć ścieżkę do katalogu scripts/ lub pusty string."""
    result = call("scripts", "scripts_dir", default=None)
    return str(result) if result is not None else ""


def tools_list() -> list:
    """Zwróć listę narzędzi z katalogu tools/ lub [] gdy niedostępny."""
    result = call("tools", "list_tools", default=None)
    return result if isinstance(result, list) else []


def tools_dir() -> str:
    """Zwróć ścieżkę do katalogu tools/ lub pusty string."""
    result = call("tools", "tools_dir", default=None)
    return str(result) if result is not None else ""


# ---------------------------------------------------------------------------
# imgtools helpers (rozszerzenie istniejących)
# ---------------------------------------------------------------------------

def imgtools_analyse(path: str) -> dict | None:
    """Zwróć raport analizy obrazu (dict) przez imgtools lub None."""
    return call("imgtools", "analyse_image", path, default=None)


def imgtools_resize(path: str, spec: str) -> None:
    """Zmień rozmiar obrazu według specyfikacji (np. '50%', '800x600')."""
    call("imgtools", "resize", path, spec)


def imgtools_gray(path: str) -> None:
    """Konwertuj obraz na skalę szarości."""
    call("imgtools", "gray", path)


# ---------------------------------------------------------------------------
# runner helpers (rozszerzenie istniejącego find_interpreter)
# ---------------------------------------------------------------------------

def runner_active_jobs() -> dict:
    """Zwróć słownik aktywnych zadań runner-a lub {} gdy niedostępny."""
    svc = _registry.get("runner")
    if svc is None:
        return {}
    jobs = svc.get("active_jobs")
    return dict(jobs) if jobs is not None else {}


def runner_ext_map() -> dict:
    """Zwróć mapę rozszerzeń → interpreterów z runner-a lub {} gdy niedostępny."""
    svc = _registry.get("runner")
    if svc is None:
        return {}
    m = svc.get("ext_map")
    return dict(m) if m is not None else {}


# ---------------------------------------------------------------------------
# debugger helpers (rozszerzenie istniejącego log_debug_event)
# ---------------------------------------------------------------------------

def debugger_is_active() -> bool:
    """Sprawdź czy debugger jest załadowany."""
    return is_available("debugger")


def debugger_get_session_stats() -> dict:
    """Zwróć statystyki bieżącej sesji debuggera lub {} gdy niedostępny."""
    result = call("debugger", "session_stats", default=None)
    return result if isinstance(result, dict) else {}


# ---------------------------------------------------------------------------
# github helpers
# ---------------------------------------------------------------------------

def github_get_token() -> str:
    """Pobierz token GitHub z modułu github lub ''."""
    result = call("github", "get_token", default=None)
    return str(result) if result is not None else ""


def github_is_available() -> bool:
    """Sprawdź czy moduł github jest załadowany z aktywnym tokenem."""
    return is_available("github") and bool(github_get_token())


# ---------------------------------------------------------------------------
# pkg helpers
# ---------------------------------------------------------------------------

def pkg_install(package: str, terminal=None) -> bool:
    """Zainstaluj pakiet pip przez moduł pkg. Zwraca True przy sukcesie."""
    result = call("pkg", "install", package, terminal, default=None)
    return bool(result) if result is not None else False


def pkg_is_installed(package: str) -> bool:
    """Sprawdź czy pakiet jest zainstalowany (przez pkg lub importlib)."""
    result = call("pkg", "is_installed", package, default=None)
    if result is not None:
        return bool(result)
    # fallback: importlib
    import importlib.util
    return importlib.util.find_spec(package.replace("-", "_")) is not None
