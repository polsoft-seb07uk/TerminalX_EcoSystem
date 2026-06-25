#!/usr/bin/env python3
# autor:   Sebastian Januchowski
# company: polsoft.ITS(TM) Group
# github:  https://github.com/polsoft-seb07uk
# email:   polsoft.its@fastservice.com
# license: MIT
"""
Moduł Virtual Environment Manager v1.2  (core)
Zarządza wirtualnym środowiskiem bibliotek w CrossTerm EcoSystem.

Zmiany v1.2 (core integration):
  - Przeniesiony z modules/ do core/  — ładuje się jako pełny moduł core
  - _VenvConfig używa _integration.call("config", ...) zamiast bezpośredniego
    odczytu/zapisu JSON  → eliminuje wyścig R-M-W z resztą konfiguracji
  - Powiadomienia (install ok/fail, sync summary) przez _integration.notify_event()
  - setup() rejestruje publiczne API w _integration pod kluczem "venv"
    → pkg.py i inne moduły mogą sprawdzać/używać środowiska wirtualnego
  - pkg.py "install libs" automatycznie rejestruje zainstalowane biblioteki
    w indeksie EcoSystem venv (przez _integration.call("venv", "register_pkg"))
  - teardown() wyrejestrowuje z _integration

Źródła bibliotek (priorytety):
  EcoSystem  — wirtualne środowisko terminala (~/.crossterm/venv/)
  os         — systemowy Python / system PATH

Komendy:
  venv                          — menu modułu
  venv list                     — lista bibliotek i ich źródeł
  venv status <lib>             — status i lokalizacja pojedynczej biblioteki
  venv set <lib> <source>       — ustaw źródło dla biblioteki (ecosystem|os|auto)
  venv path                     — pokaż aktualne ścieżki wyszukiwania
  venv path add <ścieżka>       — dodaj ścieżkę do środowiska wirtualnego
  venv path remove <ścieżka>    — usuń ścieżkę ze środowiska wirtualnego
  venv path clear               — wyczyść wszystkie ścieżki użytkownika
  venv install <lib>            — zainstaluj bibliotekę do środowiska wirtualnego (bez zależności)
  venv install <lib> --with-deps — instalacja z zależnościami
  venv uninstall <lib>          — odinstaluj bibliotekę ze środowiska wirtualnego
  venv reset                    — resetuj wszystkie ustawienia do domyślnych
  venv apply                    — zastosuj ścieżki do bieżącej sesji (sys.path)
  venv autoload                 — pokaż status autoload
  venv autoload on              — włącz automatyczne apply przy każdym starcie
  venv autoload off             — wyłącz automatyczne apply
  venv check                    — health-check: które biblioteki są niedostępne
  venv import <lib> [lib2 ...]  — faktyczny test importu (nie tylko lokalizacja)
  venv freeze [plik]            — eksport EcoSystem jako requirements.txt
  venv sync <requirements.txt>  — instaluj wszystko z pliku requirements do EcoSystem
  venv sync <req.txt> --with-deps — sync z zależnościami
  venv export                   — eksportuj konfigurację do pliku JSON
  ve / virtualenv               — aliasy do menu
"""

from __future__ import annotations

import sys
import os
import json
import subprocess
import importlib
import importlib.util
import importlib.metadata
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ._shared import ROOT_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad
from . import _integration

_sys = sys

# ─── Stałe ───────────────────────────────────────────────────────────────────

_CONFIG_DIR  = Path.home() / '.crossterm'
_VENV_DIR    = _CONFIG_DIR / 'venv'
_VENV_LIB    = _VENV_DIR / 'lib'

SOURCE_ECOSYSTEM = "ecosystem"
SOURCE_OS        = "os"
SOURCE_AUTO      = "auto"

VALID_SOURCES = (SOURCE_ECOSYSTEM, SOURCE_OS, SOURCE_AUTO)

# ─── ANSI skróty (zgodne z _shared.py) ───────────────────────────────────────

class _C:
    RESET   = RST
    BOLD    = BOLD
    DIM     = DIM
    BCYAN   = BCYN
    BYELLOW = YLW
    BGREEN  = GRN
    BWHITE  = WHT
    RED     = RED
    CYAN    = CYN
    MAGENTA = MGT
    YELLOW  = YLW
    BLUE    = BLU
    BRED    = "\x1b[101m"

_ANSI = re.compile(r'\x1b\[[0-9;]*[mA-Z]')

def _vis(s: str) -> int:
    return len(_ANSI.sub('', s))

def _padv(s: str, width: int) -> str:
    return s + ' ' * max(0, width - _vis(s))

# ─── Konfiguracja / Persystencja ─────────────────────────────────────────────

class _VenvConfig:
    """
    Przechowuje i persystuje konfigurację wirtualnego środowiska.

    v1.2: Używa _integration.call("config", ...) gdy config moduł jest
    zarejestrowany — eliminuje wyścig R-M-W.  Fallback do bezpośredniego
    JSON gdy config nieosiągalny (standalone / wczesny init).

    Struktura sekcji "venv" w config.json:
    {
      "venv": {
        "library_sources": {"pillow": "ecosystem", "requests": "auto"},
        "extra_paths":     ["/moje/biblioteki"],
        "autoload":        false
      }
    }
    """

    _CONFIG_FILE  = Path.home() / '.crossterm' / 'config.json'
    _LEGACY_FILE  = Path.home() / '.crossterm' / 'venv_config.json'
    _SECTION      = 'venv'

    def __init__(self) -> None:
        self.library_sources: Dict[str, str] = {}
        self.extra_paths: List[str]           = []
        self.autoload: bool                   = False
        self._load()

    # -- I/O ------------------------------------------------------------------

    def _read_section(self) -> dict:
        """Odczytaj sekcję 'venv' — przez _integration lub bezpośrednio."""
        # Próba przez moduł config zarejestrowany w _integration
        section = _integration.call("config", "get_section", self._SECTION, default=None)
        if isinstance(section, dict):
            return section
        # Fallback: bezpośredni odczyt JSON
        try:
            if self._CONFIG_FILE.exists():
                raw = json.loads(self._CONFIG_FILE.read_text(encoding='utf-8'))
                return raw.get(self._SECTION, {})
        except Exception:
            pass
        return {}

    def _load(self) -> None:
        """Wczytaj konfigurację — najpierw config.json, fallback do legacy pliku."""
        section = self._read_section()

        if section:
            self.library_sources = section.get('library_sources', {})
            self.extra_paths     = section.get('extra_paths', [])
            self.autoload        = bool(section.get('autoload', False))
            return

        # Fallback: stary venv_config.json (jednorazowa migracja)
        if self._LEGACY_FILE.exists():
            try:
                legacy = json.loads(self._LEGACY_FILE.read_text(encoding='utf-8'))
                self.library_sources = legacy.get('library_sources', {})
                self.extra_paths     = legacy.get('extra_paths', [])
                self.autoload        = bool(legacy.get('autoload', False))
                self._write()
            except Exception:
                pass

    def _as_dict(self) -> dict:
        return {
            'library_sources': self.library_sources,
            'extra_paths':     self.extra_paths,
            'autoload':        self.autoload,
        }

    def _write(self) -> None:
        """Zapisz sekcję 'venv' — przez _integration.config lub bezpośrednio."""
        # Próba przez moduł config zarejestrowany w _integration (eliminuje R-M-W)
        ok = _integration.call(
            "config", "set_section", self._SECTION, self._as_dict(), default=None
        )
        if ok is not None:
            return
        # Fallback: zapis bezpośredni (standalone / testy)
        try:
            self._CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            try:
                raw = json.loads(self._CONFIG_FILE.read_text(encoding='utf-8'))
            except Exception:
                raw = {}
            raw[self._SECTION] = self._as_dict()
            self._CONFIG_FILE.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False), encoding='utf-8'
            )
        except Exception as e:
            _w(f"{_C.RED}venv: nie można zapisać konfiguracji: {e}{_C.RESET}\n")

    def save(self) -> None:
        self._write()

    def reload(self) -> None:
        """Przeładuj konfigurację (np. po zmianie przez inny moduł)."""
        self._load()

    # -- API ------------------------------------------------------------------

    def get_source(self, lib: str) -> str:
        return self.library_sources.get(lib.lower(), SOURCE_AUTO)

    def set_source(self, lib: str, source: str) -> None:
        self.library_sources[lib.lower()] = source
        self._write()

    def add_path(self, path: str) -> bool:
        p = str(Path(path).expanduser().resolve())
        if p not in self.extra_paths:
            self.extra_paths.append(p)
            self._write()
            return True
        return False

    def remove_path(self, path: str) -> bool:
        p = str(Path(path).expanduser().resolve())
        if p in self.extra_paths:
            self.extra_paths.remove(p)
            self._write()
            return True
        return False

    def clear_paths(self) -> None:
        self.extra_paths.clear()
        self._write()

    def set_autoload(self, enabled: bool) -> None:
        self.autoload = enabled
        self._write()

    def reset(self) -> None:
        self.library_sources.clear()
        self.extra_paths.clear()
        self.autoload = False
        self._write()


# Singleton
_cfg = _VenvConfig()

# ─── Cache wyników _resolve_library ──────────────────────────────────────────

_resolve_cache: Dict[str, Tuple[Optional[dict], str]] = {}

def _invalidate_resolve_cache() -> None:
    _resolve_cache.clear()


# ─── Wykrywanie bibliotek ─────────────────────────────────────────────────────

def _normalize_lib(name: str) -> str:
    """PEP 503 / PyPI canonical normalization: foo-Bar_Baz → foo-bar-baz."""
    return re.sub(r'[-_.]+', '-', name).lower()


class _EcosystemIndex:
    """
    Indeks bibliotek zainstalowanych w katalogu --target (pip install --target).
    Skanuje *.dist-info, czyta METADATA + top_level.txt.
    """

    def __init__(self, target_dir: Path) -> None:
        self.target_dir = target_dir
        self._cache: Optional[Dict[str, dict]] = None

    def invalidate(self) -> None:
        self._cache = None

    def _build(self) -> Dict[str, dict]:
        index: Dict[str, dict] = {}
        if not self.target_dir.exists():
            return index

        for dist_info in self.target_dir.glob('*.dist-info'):
            meta_file = dist_info / 'METADATA'
            if not meta_file.exists():
                continue
            try:
                name = version = None
                for line in meta_file.read_text(encoding='utf-8', errors='ignore').splitlines():
                    if line.startswith('Name:'):
                        name = line.split(':', 1)[1].strip()
                    elif line.startswith('Version:'):
                        version = line.split(':', 1)[1].strip()
                    if name and version:
                        break
                if not name:
                    continue

                location = self._resolve_location(dist_info, name)
                key = _normalize_lib(name)
                index[key] = {
                    'name':      name,
                    'version':   version,
                    'location':  location,
                    'dist_info': str(dist_info),
                }
            except Exception:
                continue

        return index

    def _resolve_location(self, dist_info: Path, pkg_name: str) -> str:
        tl = dist_info / 'top_level.txt'
        if tl.exists():
            for mod in tl.read_text(encoding='utf-8', errors='ignore').strip().splitlines():
                mod = mod.strip()
                if not mod:
                    continue
                pkg_dir = self.target_dir / mod
                if pkg_dir.is_dir() and (pkg_dir / '__init__.py').exists():
                    return str(pkg_dir / '__init__.py')
                mod_file = self.target_dir / (mod + '.py')
                if mod_file.exists():
                    return str(mod_file)

        guesses = [
            pkg_name.lower().replace('-', '_'),
            pkg_name.lower().replace('-', ''),
        ]
        for g in guesses:
            pkg_dir = self.target_dir / g
            if pkg_dir.is_dir() and (pkg_dir / '__init__.py').exists():
                return str(pkg_dir / '__init__.py')
            mod_file = self.target_dir / (g + '.py')
            if mod_file.exists():
                return str(mod_file)

        return str(dist_info)

    @property
    def _index(self) -> Dict[str, dict]:
        if self._cache is None:
            self._cache = self._build()
        return self._cache

    def find(self, lib: str) -> Optional[dict]:
        return self._index.get(_normalize_lib(lib))

    def all_packages(self) -> List[dict]:
        return sorted(self._index.values(), key=lambda d: d['name'].lower())


def _all_venv_search_dirs() -> List[Path]:
    dirs: List[Path] = []
    if _VENV_LIB.exists():
        dirs.append(_VENV_LIB)
        for sp in _VENV_LIB.rglob('site-packages'):
            if sp.is_dir():
                dirs.append(sp)
    for ep in _cfg.extra_paths:
        p = Path(ep)
        if p.exists():
            dirs.append(p)
    return dirs


_eco_indices: Dict[str, _EcosystemIndex] = {}

def _get_index(target_dir: Path) -> _EcosystemIndex:
    key = str(target_dir)
    if key not in _eco_indices:
        _eco_indices[key] = _EcosystemIndex(target_dir)
    return _eco_indices[key]

def _invalidate_all_indices() -> None:
    for idx in _eco_indices.values():
        idx.invalidate()


def _find_in_ecosystem(lib: str) -> Optional[dict]:
    for target_dir in _all_venv_search_dirs():
        result = _get_index(target_dir).find(lib)
        if result:
            return result
    return None


def _find_in_os(lib: str) -> Optional[dict]:
    try:
        dist = importlib.metadata.distribution(lib)
    except importlib.metadata.PackageNotFoundError:
        try:
            dist = importlib.metadata.distribution(lib.replace('-', '_').lower())
        except importlib.metadata.PackageNotFoundError:
            return None

    name    = dist.metadata['Name'] or lib
    version = dist.metadata['Version'] or '?'
    dist_info_path = str(dist.locate_file(''))

    location: Optional[str] = None
    tl_text: Optional[str] = dist.read_text('top_level.txt')
    if tl_text:
        for mod in tl_text.strip().splitlines():
            mod = mod.strip()
            if not mod:
                continue
            try:
                spec = importlib.util.find_spec(mod)
                if spec and spec.origin:
                    location = spec.origin
                    break
            except (ModuleNotFoundError, ValueError):
                continue

    if not location:
        for candidate in [lib.replace('-', '_').lower(), name.replace('-', '_').lower()]:
            try:
                spec = importlib.util.find_spec(candidate)
                if spec and spec.origin:
                    location = spec.origin
                    break
            except (ModuleNotFoundError, ValueError):
                continue

    return {
        'name':      name,
        'version':   version,
        'location':  location or dist_info_path,
        'dist_info': dist_info_path,
    }


def _resolve_library(lib: str) -> Tuple[Optional[dict], str]:
    cache_key = _normalize_lib(lib)
    if cache_key in _resolve_cache:
        return _resolve_cache[cache_key]

    source = _cfg.get_source(lib)

    if source == SOURCE_OS:
        info = _find_in_os(lib)
        result = (info, 'os') if info else (None, 'os')
    elif source == SOURCE_ECOSYSTEM:
        info = _find_in_ecosystem(lib)
        if info:
            result = (info, 'ecosystem')
        else:
            info = _find_in_os(lib)
            result = (info, 'os [fallback]') if info else (None, 'ecosystem [nie znaleziono]')
    else:
        info = _find_in_ecosystem(lib)
        if info:
            result = (info, 'ecosystem')
        else:
            info = _find_in_os(lib)
            result = (info, 'os') if info else (None, 'auto [nie znaleziono]')

    _resolve_cache[cache_key] = result
    return result


def _installed_in_venv() -> List[dict]:
    seen: set = set()
    result: List[dict] = []
    for target_dir in _all_venv_search_dirs():
        for pkg in _get_index(target_dir).all_packages():
            key = _normalize_lib(pkg['name'])
            if key not in seen:
                seen.add(key)
                result.append(pkg)
    return result


# ─── Funkcje pomocnicze UI ───────────────────────────────────────────────────

def _source_badge(source: str) -> str:
    badge_map = {
        SOURCE_ECOSYSTEM: f"{_C.BGREEN}[EcoSystem]{_C.RESET}",
        SOURCE_OS:        f"{_C.BYELLOW}[OS]       {_C.RESET}",
        SOURCE_AUTO:      f"{_C.CYAN}[auto]     {_C.RESET}",
    }
    return badge_map.get(source, f"{_C.DIM}[{source}]{_C.RESET}")

def _used_badge(used: str) -> str:
    if 'ecosystem' in used and 'fallback' not in used:
        return f"{_C.BGREEN}▶ EcoSystem{_C.RESET}"
    if 'fallback' in used:
        return f"{_C.YELLOW}▶ OS (fallback){_C.RESET}"
    if used == 'os':
        return f"{_C.BYELLOW}▶ OS{_C.RESET}"
    return f"{_C.RED}✗ nie znaleziono{_C.RESET}"

def _hline(char='─', width=70) -> str:
    return _C.DIM + char * width + _C.RESET + '\n'

# ─── Komendy modułu ───────────────────────────────────────────────────────────

def _cmd_venv_menu(args: list, terminal) -> None:
    _w(f"\n{_C.BOLD}{_C.BCYAN}  ╭──────────────────────────────────────────────────╮{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  │   🐍  CrossTerm Virtual Environment Manager v1.2  │{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  ╰──────────────────────────────────────────────────╯{_C.RESET}\n\n")
    _w(f"  {_C.BCYAN}{'Komenda':<30}{_C.RESET} {_C.BYELLOW}Opis{_C.RESET}\n")
    _w(_hline())
    rows = [
        ("venv",                     "To menu"),
        ("venv list",                "Lista bibliotek i ich źródeł"),
        ("venv status <lib>",        "Szczegóły biblioteki (gdzie szuka, co znalazło)"),
        ("venv set <lib> <source>",  "Ustaw źródło: ecosystem | os | auto"),
        ("venv path",                "Pokaż ścieżki wirtualnego środowiska"),
        ("venv path add <ścieżka>",  "Dodaj ścieżkę do środowiska"),
        ("venv path remove <ścieżka>","Usuń ścieżkę ze środowiska"),
        ("venv path clear",          "Wyczyść wszystkie dodatkowe ścieżki"),
        ("venv install <lib>",        "Zainstaluj do EcoSystem (bez zależności)"),
        ("venv install <lib> --with-deps", "Zainstaluj z zależnościami"),
        ("venv uninstall <lib>",     "Odinstaluj bibliotekę z EcoSystem"),
        ("venv apply",               "Zastosuj ścieżki do bieżącej sesji"),
        ("venv autoload",            "Pokaż status autoload (auto apply przy starcie)"),
        ("venv autoload on|off",     "Włącz / wyłącz automatyczne apply przy starcie"),
        ("venv check",               "Health-check: które biblioteki są niedostępne"),
        ("venv import <lib>",        "Faktyczny test importu (nie tylko lokalizacja)"),
        ("venv freeze [plik]",       "Eksport EcoSystem jako requirements.txt"),
        ("venv sync <req.txt>",      "Instaluj wszystko z pliku requirements"),
        ("venv sync <req.txt> --with-deps", "Sync z zależnościami"),
        ("venv reset",               "Resetuj konfigurację do domyślnych"),
        ("venv export",              "Eksportuj konfigurację do JSON"),
    ]
    for cmd, desc in rows:
        _w(f"  {_C.BCYAN}{cmd:<30}{_C.RESET} {desc}\n")
    _w(_hline())
    _w(f"\n  {_C.BOLD}Źródła:{_C.RESET}\n")
    _w(f"  {_C.BGREEN}ecosystem{_C.RESET}  — najpierw ~/.crossterm/venv/, potem fallback do OS\n")
    _w(f"  {_C.BYELLOW}os{_C.RESET}        — wyłącznie systemowy Python / PATH\n")
    _w(f"  {_C.CYAN}auto{_C.RESET}      — sprawdza oba, preferuje EcoSystem {_C.DIM}(domyślne){_C.RESET}\n")
    _autoload_lbl = f"{_C.BGREEN}ON{_C.RESET}" if _cfg.autoload else f"{_C.DIM}OFF{_C.RESET}"
    _w(f"\n  {_C.BOLD}Autoload:{_C.RESET} {_autoload_lbl}  {_C.DIM}(venv autoload on|off){_C.RESET}\n")
    _w(f"\n  {_C.DIM}Konfiguracja: {_cfg._CONFIG_FILE}  [sekcja: \"{_cfg._SECTION}\"]{_C.RESET}\n")
    _w(f"  {_C.DIM}Biblioteki:   {_VENV_LIB}{_C.RESET}\n\n")


def _cmd_venv_list(args: list, terminal) -> None:
    libs_with_source = list(_cfg.library_sources.keys())
    eco_pkgs  = {_normalize_lib(p['name']): p for p in _installed_in_venv()}
    eco_names = [p['name'] for p in eco_pkgs.values()]

    all_libs = sorted(
        set(libs_with_source) | {_normalize_lib(n) for n in eco_names},
        key=str.lower
    )

    if not all_libs:
        _w(f"\n  {_C.DIM}Brak skonfigurowanych bibliotek.\n")
        _w(f"  Użyj{_C.RESET} {_C.BCYAN}venv set <lib> <source>{_C.RESET}{_C.DIM} aby skonfigurować lub\n")
        _w(f"  {_C.RESET}{_C.BCYAN}venv install <lib>{_C.RESET}{_C.DIM} aby zainstalować do EcoSystem.{_C.RESET}\n\n")
        return

    _w(f"\n{_C.BOLD}{_C.BWHITE}  ── Biblioteki wirtualnego środowiska ──{_C.RESET}\n\n")
    _w(f"  {_C.BOLD}{_pad('Biblioteka', 22)} {_pad('Ver', 10)} {_pad('Priorytet', 13)} {_pad('Używa', 16)} Lokalizacja{_C.RESET}\n")
    _w(_hline())

    for lib in all_libs:
        source_cfg  = _cfg.get_source(lib)
        info, used  = _resolve_library(lib)

        ver_str = f"{_C.DIM}{info['version']}{_C.RESET}" if info and info.get('version') else f"{_C.DIM}?{_C.RESET}"
        loc_str = f"{_C.DIM}{info['location']}{_C.RESET}" if info and info.get('location') else f"{_C.RED}nie znaleziono{_C.RESET}"
        display_name = info['name'] if info else lib

        _w(
            f"  {_C.BWHITE}{_padv(display_name, 22)}{_C.RESET}"
            f"{_padv(ver_str, 10 + len(ver_str) - _vis(ver_str))} "
            f"{_source_badge(source_cfg)} "
            f"{_padv(_used_badge(used), 16 + len(_used_badge(used)) - _vis(_used_badge(used)))} "
            f"{loc_str}\n"
        )

    _w(_hline())
    _w(f"\n  {_C.DIM}Razem: {len(all_libs)} bibliotek(i){_C.RESET}\n\n")


def _cmd_venv_status(args: list, terminal) -> None:
    if not args:
        _w(f"{_C.RED}Użycie: venv status <nazwa_biblioteki>{_C.RESET}\n")
        return

    lib = args[0]
    source_cfg = _cfg.get_source(lib)

    _w(f"\n{_C.BOLD}{_C.BWHITE}  ── Status biblioteki: {_C.BCYAN}{lib}{_C.BWHITE} ──{_C.RESET}\n\n")
    _w(f"  {_C.BYELLOW}Skonfigurowane źródło:{_C.RESET} {_source_badge(source_cfg)}\n\n")

    eco_info = _find_in_ecosystem(lib)
    _w(f"  {_C.BGREEN}[EcoSystem]{_C.RESET} {_VENV_LIB}\n")
    if eco_info:
        _w(f"    {_C.BGREEN}✓ Znaleziono:{_C.RESET} {eco_info['name']} {_C.DIM}v{eco_info['version']}{_C.RESET}\n")
        _w(f"    {_C.DIM}Lokalizacja: {eco_info['location']}{_C.RESET}\n")
        _w(f"    {_C.DIM}dist-info:   {eco_info['dist_info']}{_C.RESET}\n")
    else:
        _w(f"    {_C.DIM}✗ Nie znaleziono w środowisku wirtualnym{_C.RESET}\n")

    os_info = _find_in_os(lib)
    _w(f"\n  {_C.BYELLOW}[OS/System]{_C.RESET} {sys.executable}\n")
    if os_info:
        _w(f"    {_C.BGREEN}✓ Znaleziono:{_C.RESET} {os_info['name']} {_C.DIM}v{os_info['version']}{_C.RESET}\n")
        _w(f"    {_C.DIM}Lokalizacja: {os_info['location']}{_C.RESET}\n")
        _w(f"    {_C.DIM}dist-info:   {os_info['dist_info']}{_C.RESET}\n")
    else:
        _w(f"    {_C.DIM}✗ Nie znaleziono w systemowym Pythonie{_C.RESET}\n")

    info, used = _resolve_library(lib)
    _w(f"\n  {_C.BOLD}Wynik (przy aktualnym priorytecie):{_C.RESET}\n")
    if info:
        _w(f"    {_used_badge(used)}  {_C.DIM}v{info['version']}{_C.RESET}\n")
        _w(f"    {_C.DIM}Ścieżka: {info['location']}{_C.RESET}\n")
    else:
        _w(f"    {_C.RED}✗ Biblioteka niedostępna w żadnym źródle!{_C.RESET}\n")
        _w(f"    {_C.DIM}Użyj: venv install {lib}  — aby zainstalować do EcoSystem{_C.RESET}\n")

    _w(f"\n  {_C.DIM}Aby zmienić źródło: venv set {lib} ecosystem|os|auto{_C.RESET}\n\n")


def _cmd_venv_set(args: list, terminal) -> None:
    if len(args) < 2:
        _w(f"{_C.RED}Użycie: venv set <biblioteka> <źródło>{_C.RESET}\n")
        _w(f"  Źródła: {_C.BGREEN}ecosystem{_C.RESET} | {_C.BYELLOW}os{_C.RESET} | {_C.CYAN}auto{_C.RESET}\n")
        _w("  Przykład: venv set pyinstaller os\n")
        _w("  Przykład: venv set pillow ecosystem\n")
        return

    lib    = args[0].lower()
    source = args[1].lower()

    if source not in VALID_SOURCES:
        _w(f"{_C.RED}venv set: nieznane źródło '{source}'{_C.RESET}\n")
        _w(f"  Dostępne: {_C.BGREEN}ecosystem{_C.RESET} | {_C.BYELLOW}os{_C.RESET} | {_C.CYAN}auto{_C.RESET}\n")
        return

    old_source = _cfg.get_source(lib)
    _cfg.set_source(lib, source)
    _resolve_cache.pop(_normalize_lib(lib), None)

    _w(f"  {_C.BGREEN}✓{_C.RESET} {_C.BWHITE}{lib}{_C.RESET}: "
       f"{_source_badge(old_source)} {_C.DIM}→{_C.RESET} {_source_badge(source)}\n")

    info, used = _resolve_library(lib)
    if info:
        _w(f"  {_C.DIM}Aktualnie dostępna przez:{_C.RESET} {_used_badge(used)} {_C.DIM}v{info['version']}{_C.RESET}\n")
        _w(f"  {_C.DIM}Lokalizacja: {info['location']}{_C.RESET}\n")
    else:
        _w(f"  {_C.YELLOW}⚠ Biblioteka '{lib}' nie jest zainstalowana w wybranym źródle.{_C.RESET}\n")
        if source in (SOURCE_ECOSYSTEM, SOURCE_AUTO):
            _w(f"  {_C.DIM}Użyj: venv install {lib}  — aby zainstalować do EcoSystem{_C.RESET}\n")
    _w("\n")


def _cmd_venv_path(args: list, terminal) -> None:
    sub = args[0].lower() if args else ''

    if sub == 'add':
        if len(args) < 2:
            _w(f"{_C.RED}Użycie: venv path add <ścieżka>{_C.RESET}\n")
            return
        path_str = ' '.join(args[1:])
        p = Path(path_str).expanduser().resolve()
        if _cfg.add_path(str(p)):
            _w(f"  {_C.BGREEN}✓{_C.RESET} Dodano ścieżkę: {p}\n")
            _invalidate_resolve_cache()
            if not p.exists():
                _w(f"  {_C.YELLOW}⚠ Katalog nie istnieje (zostanie użyty gdy powstanie){_C.RESET}\n")
        else:
            _w(f"  {_C.DIM}Ścieżka już istnieje w konfiguracji: {p}{_C.RESET}\n")
        _w("\n")
        return

    if sub == 'remove':
        if len(args) < 2:
            _w(f"{_C.RED}Użycie: venv path remove <ścieżka>{_C.RESET}\n")
            return
        path_str = ' '.join(args[1:])
        p = Path(path_str).expanduser().resolve()
        if _cfg.remove_path(str(p)):
            _invalidate_resolve_cache()
            _w(f"  {_C.BGREEN}✓{_C.RESET} Usunięto ścieżkę: {p}\n\n")
        else:
            _w(f"  {_C.DIM}Ścieżka nie była w konfiguracji.{_C.RESET}\n\n")
        return

    if sub == 'clear':
        _cfg.clear_paths()
        _invalidate_resolve_cache()
        _w(f"  {_C.BGREEN}✓{_C.RESET} Wyczyszczono wszystkie dodatkowe ścieżki.\n\n")
        return

    _w(f"\n{_C.BOLD}{_C.BWHITE}  ── Ścieżki wirtualnego środowiska ──{_C.RESET}\n\n")

    _w(f"  {_C.BYELLOW}Wbudowane (EcoSystem):{_C.RESET}\n")
    if _VENV_LIB.exists():
        _w(f"  {_C.BGREEN}  ✓{_C.RESET} {_VENV_LIB}\n")
        for sp in _VENV_LIB.rglob('site-packages'):
            if sp.is_dir():
                _w(f"  {_C.BGREEN}  ✓{_C.RESET} {sp} {_C.DIM}(site-packages){_C.RESET}\n")
    else:
        _w(f"  {_C.DIM}  (pusty — użyj venv install aby zainstalować biblioteki){_C.RESET}\n")

    _w(f"\n  {_C.BYELLOW}Dodatkowe ścieżki użytkownika:{_C.RESET}\n")
    if _cfg.extra_paths:
        for ep in _cfg.extra_paths:
            p = Path(ep)
            ok = _C.BGREEN + "✓" if p.exists() else _C.RED + "✗"
            _w(f"  {ok}{_C.RESET} {ep}\n")
    else:
        _w(f"  {_C.DIM}  (brak — użyj: venv path add <ścieżka>){_C.RESET}\n")

    _w(f"\n  {_C.BYELLOW}Systemowe Python sys.path (aktywne):{_C.RESET}\n")
    for sp in sys.path[:6]:
        _w(f"  {_C.DIM}  {sp}{_C.RESET}\n")
    if len(sys.path) > 6:
        _w(f"  {_C.DIM}  ... ({len(sys.path)-6} więcej){_C.RESET}\n")

    _w(f"\n  {_C.DIM}Zarządzanie: venv path add|remove|clear{_C.RESET}\n\n")


def _pip_install_to_ecosystem(pkg_spec: str, with_deps: bool) -> dict:
    """Uruchom pip install --target do _VENV_LIB.

    Zwraca dict: {ok, lib_base, eco_info, deps, stderr, timeout}
    """
    lib_base = re.split(r'[><=!~;\[@\s]', pkg_spec)[0].strip()

    cmd = [
        sys.executable, '-m', 'pip', 'install',
        '--target', str(_VENV_LIB),
    ]
    if not with_deps:
        cmd.append('--no-deps')
    cmd.append(pkg_spec)

    result_dict = {
        'ok': False, 'lib_base': lib_base, 'eco_info': None,
        'deps': [], 'stderr': '', 'timeout': False,
    }

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        result_dict['stderr'] = result.stderr.strip()

        if result.returncode != 0:
            return result_dict

        _invalidate_all_indices()
        _invalidate_resolve_cache()
        result_dict['ok'] = True
        result_dict['eco_info'] = _find_in_ecosystem(lib_base)

        if with_deps:
            deps: List[str] = []
            for line in result.stdout.splitlines():
                if line.startswith('Successfully installed'):
                    pkgs = line.replace('Successfully installed', '').split()
                    norm_base = _normalize_lib(lib_base)
                    for p in pkgs:
                        p_name = _normalize_lib(p.rsplit('-', 1)[0])
                        if p_name != norm_base:
                            deps.append(p)
            result_dict['deps'] = deps

    except subprocess.TimeoutExpired:
        result_dict['timeout'] = True
    except Exception as e:
        result_dict['stderr'] = str(e)

    return result_dict


def _cmd_venv_install(args: list, terminal) -> None:
    if not args:
        _w(f"{_C.RED}Użycie: venv install <biblioteka> [--with-deps]{_C.RESET}\n")
        _w("  Przykład: venv install requests\n")
        _w("  Przykład: venv install pillow==10.3.0\n")
        _w("  Przykład: venv install httpx --with-deps\n")
        return

    flags     = {a.lower() for a in args}
    with_deps = '--with-deps' in flags or '--deps' in flags
    pkg_args  = [a for a in args if not a.startswith('--')]
    if not pkg_args:
        _w(f"{_C.RED}venv install: brak nazwy pakietu.{_C.RESET}\n")
        return
    lib = ' '.join(pkg_args)

    _VENV_LIB.mkdir(parents=True, exist_ok=True)

    deps_label = f"{_C.BGREEN}z zależnościami{_C.RESET}" if with_deps else f"{_C.DIM}bez zależności{_C.RESET}"
    _w(f"\n  {_C.BOLD}Instalacja {_C.BCYAN}{lib}{_C.RESET}{_C.BOLD} do EcoSystem  {_C.RESET}[{deps_label}{_C.BOLD}]{_C.RESET}\n")
    _w(f"  {_C.DIM}Cel: {_VENV_LIB}{_C.RESET}\n\n")

    r = _pip_install_to_ecosystem(lib, with_deps=with_deps)

    if r['timeout']:
        _integration.notify_event(terminal, f"venv install: timeout ({lib})", kind="err")
        _w(f"  {_C.RED}✗ Timeout — instalacja trwała zbyt długo (>120s){_C.RESET}\n\n")
        return

    if not r['ok']:
        _integration.notify_event(terminal, f"venv install: błąd ({r['lib_base']})", kind="err")
        _w(f"  {_C.RED}✗ Błąd instalacji:{_C.RESET}\n")
        for line in r['stderr'].splitlines():
            _w(f"    {_C.DIM}{line}{_C.RESET}\n")
        _w("\n")
        return

    eco_info = r['eco_info']
    if eco_info:
        _w(f"  {_C.BGREEN}✓ Zainstalowano: {eco_info['name']} v{eco_info['version']}{_C.RESET}\n")
        _w(f"  {_C.DIM}Lokalizacja: {eco_info['location']}{_C.RESET}\n")
        _integration.notify_event(
            terminal,
            f"venv: zainstalowano {eco_info['name']} v{eco_info['version']}",
            kind="ok", compact=True
        )
        # Poinformuj pkg o nowo zainstalowanym pakiecie (opcjonalne)
        _integration.call("pkg", "hist_add", "venv-install", r['lib_base'],
                          eco_info.get('version', ''), "venv")
    else:
        _w(f"  {_C.BGREEN}✓ pip zakończył pomyślnie.{_C.RESET}\n")
        _w(f"  {_C.YELLOW}⚠ Indeks EcoSystem nie wykrywa pakietu — sprawdź 'venv check'.{_C.RESET}\n")

    if with_deps and r['deps']:
        _w(f"  {_C.DIM}Zależności: {', '.join(r['deps'])}{_C.RESET}\n")
    elif not with_deps:
        _w(f"  {_C.DIM}Instalacja bez zależności. Jeśli import się nie powiedzie, użyj --with-deps.{_C.RESET}\n")

    lib_key = _normalize_lib(r['lib_base'])
    if _cfg.get_source(lib_key) == SOURCE_AUTO:
        _cfg.set_source(lib_key, SOURCE_ECOSYSTEM)
        _w(f"  {_C.DIM}Źródło ustawione na: ecosystem{_C.RESET}\n")

    _w(f"\n  {_C.DIM}Użyj 'venv apply' aby aktywować w bieżącej sesji.{_C.RESET}\n\n")


def _cmd_venv_uninstall(args: list, terminal) -> None:
    if not args:
        _w(f"{_C.RED}Użycie: venv uninstall <biblioteka>{_C.RESET}\n")
        return

    lib = args[0]

    if not _VENV_LIB.exists():
        _w(f"  {_C.DIM}Środowisko wirtualne jest puste.{_C.RESET}\n\n")
        return

    eco_info = _find_in_ecosystem(lib)
    if not eco_info:
        _w(f"  {_C.YELLOW}⚠ Nie znaleziono '{lib}' w środowisku wirtualnym (EcoSystem).{_C.RESET}\n\n")
        return

    dist_info_path = Path(eco_info['dist_info'])
    install_dir    = dist_info_path.parent
    to_remove: List[Path] = [dist_info_path]

    tl = dist_info_path / 'top_level.txt'
    if tl.exists():
        for mod in tl.read_text(encoding='utf-8', errors='ignore').strip().splitlines():
            mod = mod.strip()
            if not mod:
                continue
            pkg_dir = install_dir / mod
            if pkg_dir.exists():
                to_remove.append(pkg_dir)
            mod_file = install_dir / (mod + '.py')
            if mod_file.exists():
                to_remove.append(mod_file)
            cache = install_dir / '__pycache__'
            if cache.exists():
                for f in cache.glob(f'{mod}*.pyc'):
                    to_remove.append(f)

    _w(f"\n  {_C.BOLD}Usuwanie {_C.BCYAN}{eco_info['name']} v{eco_info['version']}{_C.RESET}{_C.BOLD} z EcoSystem...{_C.RESET}\n")
    for item in to_remove:
        if not item.exists():
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            _w(f"  {_C.BGREEN}✓{_C.RESET} Usunięto: {item.name}\n")
        except Exception as e:
            _w(f"  {_C.RED}✗ Błąd przy usuwaniu {item.name}: {e}{_C.RESET}\n")

    _invalidate_all_indices()
    _invalidate_resolve_cache()

    lib_key = _normalize_lib(lib)
    if lib_key in _cfg.library_sources:
        del _cfg.library_sources[lib_key]
        _cfg.save()
        _w(f"  {_C.DIM}Usunięto konfigurację źródła.{_C.RESET}\n")

    _integration.notify_event(
        terminal, f"venv: odinstalowano {eco_info['name']}", kind="info", compact=True
    )
    _w("\n")


def _cmd_venv_apply(args: list, terminal) -> None:
    added: List[str] = []
    for p in _all_venv_search_dirs():
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
            added.append(sp)

    _w(f"\n  {_C.BOLD}Zastosowanie ścieżek EcoSystem do sys.path:{_C.RESET}\n\n")
    if added:
        for a in added:
            _w(f"  {_C.BGREEN}+ {a}{_C.RESET}\n")
        _w(f"\n  {_C.BGREEN}✓ Dodano {len(added)} ścieżek.{_C.RESET}\n")
        _w(f"  {_C.DIM}Biblioteki z EcoSystem są teraz dostępne do importu w tej sesji.{_C.RESET}\n")
    else:
        _w(f"  {_C.DIM}Wszystkie ścieżki były już aktywne.{_C.RESET}\n")
    _w("\n")


def _cmd_venv_autoload(args: list, terminal) -> None:
    sub = args[0].lower() if args else ''

    if sub == 'on':
        _cfg.set_autoload(True)
        _w(f"\n  {_C.BGREEN}✓ Autoload włączony.{_C.RESET}\n")
        _w(f"  {_C.DIM}Ścieżki EcoSystem będą automatycznie stosowane przy każdym starcie terminala.{_C.RESET}\n\n")
        return

    if sub == 'off':
        _cfg.set_autoload(False)
        _w(f"\n  {_C.BYELLOW}✓ Autoload wyłączony.{_C.RESET}\n")
        _w(f"  {_C.DIM}Ścieżki EcoSystem nie są stosowane automatycznie.{_C.RESET}\n\n")
        return

    status     = _cfg.autoload
    label      = f"{_C.BGREEN}ON{_C.RESET}"  if status else f"{_C.BYELLOW}OFF{_C.RESET}"
    icon       = "✓" if status else "✗"
    icon_color = _C.BGREEN if status else _C.DIM

    _w(f"\n{_C.BOLD}{_C.BWHITE}  ── Autoload ──{_C.RESET}\n\n")
    _w(f"  {icon_color}{icon}{_C.RESET} Autoload: {label}\n")
    _w(f"\n  {_C.DIM}Gdy ON — on_load() automatycznie stosuje ścieżki EcoSystem\n")
    _w(f"  do sys.path przy każdym starcie terminala (bez 'venv apply').{_C.RESET}\n\n")
    _w(f"  {_C.BCYAN}venv autoload on{_C.RESET}   — włącz\n")
    _w(f"  {_C.BCYAN}venv autoload off{_C.RESET}  — wyłącz\n\n")
    _w(f"  {_C.DIM}Konfiguracja: {_cfg._CONFIG_FILE}  [sekcja: \"{_cfg._SECTION}\"]{_C.RESET}\n\n")


def _cmd_venv_reset(args: list, terminal) -> None:
    _w(f"  {_C.YELLOW}⚠ Reset konfiguracji wirtualnego środowiska (nie usuwa plików bibliotek).{_C.RESET}\n")
    _w(f"  {_C.DIM}Naciśnij ENTER aby potwierdzić, Ctrl+C aby anulować...{_C.RESET}\n")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        _w(f"\n  {_C.DIM}Anulowano.{_C.RESET}\n\n")
        return

    _cfg.reset()
    _invalidate_resolve_cache()
    _w(f"  {_C.BGREEN}✓ Konfiguracja zresetowana.{_C.RESET}\n")
    _w(f"  {_C.DIM}Wszystkie biblioteki używają teraz źródła 'auto'.{_C.RESET}\n\n")


def _cmd_venv_export(args: list, terminal) -> None:
    out_path = Path('venv_export.json')
    if args:
        out_path = Path(args[0]).expanduser().resolve()

    try:
        eco_pkgs = _installed_in_venv()
        data = {
            'crossterm_venv_export': True,
            'library_sources': _cfg.library_sources,
            'extra_paths':     _cfg.extra_paths,
            'venv_lib_dir':    str(_VENV_LIB),
            'installed_in_venv': [
                {'name': p['name'], 'version': p['version'], 'location': p['location']}
                for p in eco_pkgs
            ],
        }
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        _w(f"  {_C.BGREEN}✓{_C.RESET} Eksport zapisany: {out_path}\n\n")
    except Exception as e:
        _w(f"  {_C.RED}✗ Błąd eksportu: {e}{_C.RESET}\n\n")


def _cmd_venv_check(args: list, terminal) -> None:
    libs_cfg  = list(_cfg.library_sources.keys())
    eco_pkgs  = {_normalize_lib(p['name']) for p in _installed_in_venv()}
    all_libs  = sorted(set(libs_cfg) | eco_pkgs, key=str.lower)

    if not all_libs:
        _w(f"\n  {_C.DIM}Brak skonfigurowanych bibliotek — nic do sprawdzenia.{_C.RESET}\n\n")
        return

    _w(f"\n{_C.BOLD}{_C.BWHITE}  ── Health-check środowiska ──{_C.RESET}\n\n")

    ok_count  = 0
    bad_count = 0
    bad_list: List[str] = []

    for lib in all_libs:
        info, used = _resolve_library(lib)
        if info:
            ok_count += 1
            ver = info.get('version', '?')
            src = _used_badge(used)
            _w(f"  {_C.BGREEN}✓{_C.RESET} {_C.BWHITE}{lib:<22}{_C.RESET} {_C.DIM}v{ver:<12}{_C.RESET} {src}\n")
        else:
            bad_count += 1
            bad_list.append(lib)
            cfg_src = _cfg.get_source(lib)
            _w(f"  {_C.RED}✗{_C.RESET} {_C.BWHITE}{lib:<22}{_C.RESET} {_C.RED}NIEDOSTĘPNA{_C.RESET}"
               f"  {_C.DIM}(źródło: {cfg_src}){_C.RESET}\n")

    _w(_hline())
    _w(f"\n  Razem: {_C.BGREEN}{ok_count} OK{_C.RESET}")
    if bad_count:
        _w(f"  {_C.RED}{bad_count} BRAK{_C.RESET}")
        _w(f"\n\n  {_C.YELLOW}Niedostępne biblioteki:{_C.RESET}\n")
        for b in bad_list:
            _w(f"    {_C.DIM}venv install {b}{_C.RESET}\n")
    else:
        _w(f"  {_C.DIM}— wszystkie biblioteki dostępne{_C.RESET}")
    _w("\n\n")


def _cmd_venv_import(args: list, terminal) -> None:
    if not args:
        _w(f"{_C.RED}Użycie: venv import <biblioteka> [biblioteka2 ...]{_C.RESET}\n")
        return

    _w(f"\n{_C.BOLD}{_C.BWHITE}  ── Test importu bibliotek ──{_C.RESET}\n\n")

    for lib in args:
        import_name = re.split(r'[><=!~;\[@\s]', lib)[0].strip().replace('-', '_')

        _applied: List[str] = []
        for p in _all_venv_search_dirs():
            sp = str(p)
            if sp not in sys.path:
                sys.path.insert(0, sp)
                _applied.append(sp)

        try:
            mod = importlib.import_module(import_name)
            ver = getattr(mod, '__version__', None) or getattr(mod, 'VERSION', None) or '?'
            loc = getattr(mod, '__file__', None) or '(wbudowany)'
            _w(f"  {_C.BGREEN}✓{_C.RESET} {_C.BWHITE}{lib}{_C.RESET}\n")
            _w(f"    {_C.DIM}wersja  : {ver}{_C.RESET}\n")
            _w(f"    {_C.DIM}lokalizacja: {loc}{_C.RESET}\n")
        except ImportError as e:
            _w(f"  {_C.RED}✗ {lib}{_C.RESET}  {_C.RED}ImportError: {e}{_C.RESET}\n")
            _w(f"    {_C.DIM}Wskazówka: venv install {lib}{_C.RESET}\n")
        except Exception as e:
            _w(f"  {_C.RED}✗ {lib}{_C.RESET}  {_C.RED}{type(e).__name__}: {e}{_C.RESET}\n")
        finally:
            for sp in _applied:
                try:
                    sys.path.remove(sp)
                except ValueError:
                    pass
        _w("\n")


def _cmd_venv_freeze(args: list, terminal) -> None:
    out_path: Optional[Path] = None
    if args:
        out_path = Path(args[0]).expanduser().resolve()

    eco_pkgs = _installed_in_venv()

    if not eco_pkgs:
        _w(f"\n  {_C.DIM}EcoSystem jest pusty — brak bibliotek do wyeksportowania.{_C.RESET}\n\n")
        return

    lines = [f"{p['name']}=={p['version']}" for p in eco_pkgs if p.get('version') and p['version'] != '?']

    if out_path:
        try:
            out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            _w(f"\n  {_C.BGREEN}✓{_C.RESET} Zapisano {len(lines)} pakiet(ów) do: {out_path}\n\n")
        except Exception as e:
            _w(f"\n  {_C.RED}✗ Błąd zapisu: {e}{_C.RESET}\n\n")
    else:
        _w(f"\n{_C.BOLD}{_C.BWHITE}  ── requirements.txt (EcoSystem) ──{_C.RESET}\n\n")
        for ln in lines:
            _w(f"  {_C.BCYN}{ln}{_C.RESET}\n")
        _w(f"\n  {_C.DIM}Razem: {len(lines)} pakiet(ów){_C.RESET}\n")
        _w(f"  {_C.DIM}Zapisz do pliku: venv freeze requirements.txt{_C.RESET}\n\n")


def _cmd_venv_sync(args: list, terminal) -> None:
    if not args:
        _w(f"{_C.RED}Użycie: venv sync <requirements.txt> [--with-deps]{_C.RESET}\n")
        return

    flags     = {a.lower() for a in args}
    with_deps = '--with-deps' in flags or '--deps' in flags
    path_args = [a for a in args if not a.startswith('--')]
    if not path_args:
        _w(f"{_C.RED}venv sync: brak ścieżki do pliku requirements.{_C.RESET}\n")
        return

    req_path = Path(path_args[0]).expanduser().resolve()
    if not req_path.exists():
        _w(f"  {_C.RED}✗ Plik nie istnieje: {req_path}{_C.RESET}\n\n")
        return

    raw_lines = req_path.read_text(encoding='utf-8', errors='ignore').splitlines()
    packages: List[str] = []
    for line in raw_lines:
        line = line.split('#')[0].strip()
        if not line or line.startswith('-'):
            continue
        packages.append(line)

    if not packages:
        _w(f"  {_C.YELLOW}⚠ Plik nie zawiera żadnych pakietów: {req_path}{_C.RESET}\n\n")
        return

    deps_label = f"{_C.BGREEN}z zależnościami{_C.RESET}" if with_deps else f"{_C.DIM}bez zależności{_C.RESET}"
    _w(f"\n{_C.BOLD}{_C.BWHITE}  ── Sync z {req_path.name} → EcoSystem ──{_C.RESET}  [{deps_label}{_C.BOLD}]{_C.RESET}\n")
    _w(f"  {_C.DIM}Znaleziono {len(packages)} pakiet(ów).{_C.RESET}\n\n")

    _VENV_LIB.mkdir(parents=True, exist_ok=True)

    ok_list:  List[str] = []
    err_list: List[str] = []

    for i, pkg in enumerate(packages, 1):
        _w(f"  [{i}/{len(packages)}] {_C.BCYN}{pkg}{_C.RESET} ... ")
        _sys.stdout.flush()

        r = _pip_install_to_ecosystem(pkg, with_deps=with_deps)

        if r['timeout']:
            _w(f"{_C.RED}✗ timeout{_C.RESET}\n")
            err_list.append(r['lib_base'])
            continue

        if not r['ok']:
            err_msg = r['stderr'].splitlines()[-1] if r['stderr'] else 'błąd pip'
            _w(f"{_C.RED}✗{_C.RESET}  {_C.DIM}{err_msg}{_C.RESET}\n")
            err_list.append(r['lib_base'])
            continue

        eco_info = r['eco_info']
        if eco_info:
            _w(f"{_C.BGREEN}✓{_C.RESET}  {_C.DIM}v{eco_info['version']}{_C.RESET}")
            if with_deps and r['deps']:
                _w(f"  {_C.DIM}+{len(r['deps'])} dep{_C.RESET}")
            _w("\n")
        else:
            _w(f"{_C.BGREEN}✓{_C.RESET}  {_C.YELLOW}⚠ nie wykryto przez indeks{_C.RESET}\n")

        ok_list.append(r['lib_base'])

    _w(f"\n{_hline()}")
    _w(f"  {_C.BGREEN}✓ Zainstalowano: {len(ok_list)}{_C.RESET}")
    if err_list:
        _w(f"   {_C.RED}✗ Błędy: {len(err_list)}{_C.RESET}  {_C.DIM}({', '.join(err_list)}){_C.RESET}")
    _w(f"\n  {_C.DIM}Użyj 'venv apply' aby aktywować ścieżki w bieżącej sesji.{_C.RESET}\n\n")

    _integration.notify_event(
        terminal,
        f"venv sync: {len(ok_list)} zainstalowano, {len(err_list)} błędów",
        kind="ok" if not err_list else "warn",
        compact=True
    )


# ─── Główny dispatcher komendy 'venv' ────────────────────────────────────────

def _cmd_venv(args: list, terminal) -> None:
    # Przeładuj konfigurację przy pierwszej komendzie (sync z config.py)
    _cfg.reload()

    if not args:
        _cmd_venv_menu(args, terminal)
        return

    sub = args[0].lower()
    rest = args[1:]

    dispatch = {
        'list':      _cmd_venv_list,
        'ls':        _cmd_venv_list,
        'status':    _cmd_venv_status,
        'info':      _cmd_venv_status,
        'set':       _cmd_venv_set,
        'source':    _cmd_venv_set,
        'path':      _cmd_venv_path,
        'paths':     _cmd_venv_path,
        'install':   _cmd_venv_install,
        'add':       _cmd_venv_install,
        'uninstall': _cmd_venv_uninstall,
        'remove':    _cmd_venv_uninstall,
        'apply':     _cmd_venv_apply,
        'activate':  _cmd_venv_apply,
        'autoload':  _cmd_venv_autoload,
        'check':     _cmd_venv_check,
        'health':    _cmd_venv_check,
        'import':    _cmd_venv_import,
        'test':      _cmd_venv_import,
        'freeze':    _cmd_venv_freeze,
        'sync':      _cmd_venv_sync,
        'reset':     _cmd_venv_reset,
        'export':    _cmd_venv_export,
        'help':      _cmd_venv_menu,
    }

    fn = dispatch.get(sub)
    if fn:
        fn(rest, terminal)
    else:
        _w(f"{_C.RED}venv: nieznana podkomenda '{sub}'{_C.RESET}\n")
        _w(f"  {_C.DIM}Dostępne: {', '.join(dispatch)}{_C.RESET}\n")
        _w(f"  {_C.DIM}Lub wpisz: venv  — aby zobaczyć menu{_C.RESET}\n\n")


# ─── Publiczne API (używane przez _integration) ───────────────────────────────

def find_in_ecosystem(lib: str) -> Optional[dict]:
    """API: znajdź bibliotekę w EcoSystem. Używane przez inne moduły."""
    return _find_in_ecosystem(lib)

def find_library(lib: str) -> Tuple[Optional[dict], str]:
    """API: rozwiąż bibliotekę zgodnie z konfiguracją źródeł."""
    return _resolve_library(lib)

def get_venv_paths() -> List[str]:
    """API: zwróć listę ścieżek środowiska wirtualnego jako string."""
    return [str(p) for p in _all_venv_search_dirs()]

def apply_paths_to_sys() -> int:
    """API: zastosuj ścieżki EcoSystem do sys.path. Zwraca liczbę dodanych."""
    added = 0
    for p in _all_venv_search_dirs():
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
            added += 1
    return added

def register_installed(lib_name: str, version: str, source: str = SOURCE_ECOSYSTEM) -> None:
    """API: rejestruj pakiet zainstalowany przez pkg.py w konfiguracji venv."""
    lib_key = _normalize_lib(lib_name)
    if _cfg.get_source(lib_key) == SOURCE_AUTO:
        _cfg.set_source(lib_key, source)
    _invalidate_all_indices()
    _invalidate_resolve_cache()

def is_autoload() -> bool:
    """API: czy autoload jest włączony."""
    return _cfg.autoload

def get_config_snapshot() -> dict:
    """API: zwróć kopię aktualnej konfiguracji venv (do debuggera / statusu)."""
    return {
        'library_sources': dict(_cfg.library_sources),
        'extra_paths':     list(_cfg.extra_paths),
        'autoload':        _cfg.autoload,
        'venv_lib':        str(_VENV_LIB),
        'venv_lib_exists': _VENV_LIB.exists(),
        'installed_count': len(_installed_in_venv()),
    }


# ─── on_load ─────────────────────────────────────────────────────────────────

def on_load() -> None:
    """Wywoływane przy ładowaniu modułu — stosuje ścieżki gdy autoload=on."""
    if not _cfg.autoload:
        return
    for p in _all_venv_search_dirs():
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)


# ─── setup / teardown ────────────────────────────────────────────────────────

def setup(terminal) -> None:
    """Rejestruje komendy venv w TerminalX EcoSystem i API w _integration."""
    # Przeładuj config (może być teraz dostępny przez _integration)
    _cfg.reload()

    # Rejestracja publicznego API w _integration
    _integration.register("venv", {
        # Wyszukiwanie bibliotek
        "find_in_ecosystem": find_in_ecosystem,
        "find_library":      find_library,
        # Zarządzanie ścieżkami
        "get_venv_paths":    get_venv_paths,
        "apply_paths":       apply_paths_to_sys,
        # Rejestracja pakietów z zewnątrz (np. z pkg.py)
        "register_installed": register_installed,
        # Stan / diagnostyka
        "is_autoload":       is_autoload,
        "config_snapshot":   get_config_snapshot,
        # Unieważnianie cache
        "invalidate_cache":  _invalidate_resolve_cache,
    })

    # Autoload — zastosuj ścieżki jeśli włączone
    on_load()

    def _t(key, **kw):
        return terminal.t(key, **kw)

    def _venv(args):
        _cmd_venv(args, terminal)

    terminal.register_command(
        "venv", _venv,
        description=_t("cmd_venv"),
        category=_t("cat_ecosystem"),
    )
    terminal.register_command(
        "ve", _venv,
        description=_t("cmd_ve"),
        category=_t("cat_ecosystem"),
    )
    terminal.register_command(
        "virtualenv", _venv,
        description=_t("cmd_virtualenv"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal) -> None:
    """Wyrejestruje komendy i API venv."""
    _integration.unregister("venv")
    for cmd in ("venv", "ve", "virtualenv"):
        terminal.commands.pop(cmd, None)


# ─── Metadane modułu ─────────────────────────────────────────────────────────

MODULE_CMD            = "venv"
MODULE_DESCRIPTION    = "Menedżer wirtualnego środowiska bibliotek (install, sync, freeze...)"
MODULE_DESCRIPTION_EN = "Virtual environment manager (install, sync, freeze...)"
MODULE_VERSION        = "1.2"
