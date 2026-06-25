#!/usr/bin/env python3
# autor:   CrossTerm AI Module
# license: MIT
# core module: ai — Asystent AI (przeniesiony z modules/ai.py)
"""
╔══════════════════════════════════════════════════════════════════════════╗
║                     CrossTerm AI Module v2.1                           ║
╠══════════════════════════════════════════════════════════════════════════╣
║  KOMENDY TERMINALA:                                                     ║
║   ai                           — menu główne / status                  ║
║   ai ask <pytanie>             — szybkie pytanie (odpowiedź w terminalu)║
║   ai chat                      — otwórz okno chat GUI (nie blokuje TUI)║
║   ai profile                   — zarządzanie profilami API              ║
║   ai profile preset            — lista gotowych presetów (30+ modeli)  ║
║   ai profile preset <klucz>    — zainstaluj gotowy preset              ║
║   ai profile add <nazwa>       — dodaj własny profil ręcznie           ║
║   ai profile list              — wylistuj profile                      ║
║   ai profile use <nazwa>       — aktywuj profil                        ║
║   ai profile del <nazwa>       — usuń profil                           ║
║   ai profile show <nazwa>      — pokaż szczegóły profilu               ║
║   ai set model <model>         — zmień model w aktywnym profilu        ║
║   ai set system <tekst>        — ustaw system prompt                   ║
║   ai history                   — pokaż historię konwersacji            ║
║   ai clear                     — wyczyść historię                      ║
║   ai info                      — informacje o API / modelach           ║
╠══════════════════════════════════════════════════════════════════════════╣
║  GOTOWE PRESETY (ai profile preset <klucz>):                           ║
║   Anthropic : claude-opus · claude-sonnet · claude-haiku               ║
║   OpenAI    : gpt-4o · gpt-4o-mini · gpt-4.1 · o3 · o4-mini          ║
║   Google    : gemini-pro · gemini-flash · gemini-flash-lite            ║
║   Groq FREE : groq-llama · groq-deepseek · groq-mixtral               ║
║   xAI       : grok-3 · grok-3-mini                                    ║
║   DeepSeek  : deepseek-chat · deepseek-r1                             ║
║   Mistral   : mistral-large · codestral                               ║
║   Perplexity: perplexity-pro · perplexity-sonar                       ║
║   Cohere    : cohere-r+                                               ║
║   Lokalne   : ollama-llama · lmstudio · openrouter                    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import re
import threading
import time
import textwrap
from pathlib import Path
from typing import Optional, List, Dict, Any

# ─── SHARED ────────────────────────────────────────────────────────────────────
# Importujemy stałe ANSI i ROOT_DIR z _shared zamiast definiować lokalnie.

from ._shared import (
    ROOT_DIR,
    RST   as _RST,
    BOLD  as _BOLD,
    DIM   as _DIM,
    YLW   as _YLW,
    GRN   as _GRN,
    RED   as _RED,
    CYN   as _CYN,
    BCYN  as _BCYN,
    MGT   as _MGT,
    BLU   as _BLU,
    WHT   as _WHT,
    _w    as _w,
    _strip,
)


class _C:
    """Mapowanie nazw kolorów używanych przez ai.py na stałe z _shared."""
    RESET   = _RST
    BOLD    = _BOLD
    DIM     = _DIM
    BCYAN   = _BCYN
    BYELLOW = _YLW
    BGREEN  = _GRN
    BWHITE  = _WHT
    RED     = _RED
    CYAN    = _CYN
    MAGENTA = _MGT
    YELLOW  = _YLW
    BLUE    = _BLU
    GREEN   = _GRN
    GRAY    = "\x1b[90m" if _RST else ""
    WHITE   = _WHT

_ANSI = re.compile(r'\x1b\[[0-9;]*[mA-Z]')

def _vis(s: str) -> int:
    return len(_strip(s))

def _wl(s: str = "") -> None:
    _w(s + "\n")

# ─── ŚCIEŻKI / KONFIGURACJA ────────────────────────────────────────────────────

_TERM_DIR    = Path(ROOT_DIR)
_CONFIG_FILE = Path.home() / '.crossterm' / 'config.json'
_AI_DIR      = Path.home() / '.crossterm' / 'ai'
_KEYS_DIR    = Path(ROOT_DIR) / 'key'
_KEYS_FILE   = _KEYS_DIR / 'api_keys.ini'

def _ensure_dirs() -> None:
    _AI_DIR.mkdir(parents=True, exist_ok=True)
    _KEYS_DIR.mkdir(parents=True, exist_ok=True)

def _load_global_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}

def _save_global_config(raw: dict) -> None:
    try:
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_FILE.write_text(json.dumps(raw, indent=2), encoding='utf-8')
    except Exception as e:
        _wl(f"{_C.RED}Błąd zapisu config: {e}{_C.RESET}")

def _update_config(**kwargs) -> None:
    raw = _load_global_config()
    ai_section = raw.get('ai', {})
    for k, v in kwargs.items():
        if v is None:
            ai_section.pop(k, None)
        else:
            ai_section[k] = v
    raw['ai'] = ai_section
    _save_global_config(raw)

def _read_ai_config() -> dict:
    return _load_global_config().get('ai', {})

# ─── KLUCZE API Z PLIKU ─────────────────────────────────────────────────────────
#
# Plik key/api_keys.ini przechowuje klucze API w formacie INI.
# Każda sekcja = provider, klucz = api_key.
# Plik jest generowany przez `ai keys generate` — użytkownik wpisuje swoje klucze.
# Przy starcie modułu klucze są wczytywane automatycznie i używane podczas
# instalacji presetów (ai profile preset <klucz>) zamiast pytania o klucz.

# Mapowanie provider → etykieta w pliku INI (sekcja)
_KEYS_PROVIDERS: list[tuple[str, str, str, str]] = [
    # (provider_id, sekcja INI, key_hint, url)
    ('anthropic',   'Anthropic',   'sk-ant-api03-...',       'https://console.anthropic.com/account/keys'),
    ('openai',      'OpenAI',      'sk-proj-...',            'https://platform.openai.com/api-keys'),
    ('google',      'Google',      'AIzaSy...',              'https://aistudio.google.com/app/apikey'),
    ('groq',        'Groq',        'gsk_...',                'https://console.groq.com/keys'),
    ('xai',         'xAI',         'xai-...',                'https://console.x.ai'),
    ('deepseek',    'DeepSeek',    'sk-...',                 'https://platform.deepseek.com/api_keys'),
    ('mistral',     'Mistral',     'klucz Mistral API',      'https://console.mistral.ai/api-keys'),
    ('perplexity',  'Perplexity',  'pplx-...',               'https://www.perplexity.ai/settings/api'),
    ('cohere',      'Cohere',      'klucz Cohere API',       'https://dashboard.cohere.com/api-keys'),
    ('openrouter',  'OpenRouter',  'sk-or-...',              'https://openrouter.ai/keys'),
]

_KEYS_FILE_HEADER = """\
; ============================================================
;  CrossTerm AI — plik kluczy API
;  Wygenerowany przez: ai keys generate
; ============================================================
;
;  Instrukcja:
;   1. Wpisz swoje klucze API obok api_key = (zastąp placeholder)
;   2. Sekcje bez klucza zostaw bez zmian — zostaną zignorowane
;   3. Wczytaj klucze komendą: ai keys load
;      lub uruchom terminal ponownie (auto-load przy starcie)
;
;  Klucze są przechowywane lokalnie, nigdzie nie wysyłane.
; ============================================================

"""

_KEYS_FILE_LOCAL_SECTION = """\
; ── Lokalne / OpenRouter ─────────────────────────────────────
[OpenRouter]
; Dostęp do setek modeli przez jeden klucz: https://openrouter.ai/keys
api_key = sk-or-...

[Ollama]
; Lokalny Ollama — wpisz cokolwiek (np. ollama), serwer nie wymaga klucza
api_key = ollama

[LMStudio]
; Lokalny LM Studio — wpisz cokolwiek (np. lmstudio)
api_key = lmstudio

"""


def _generate_keys_file(overwrite: bool = False) -> bool:
    """Generuje plik key/api_keys.ini ze wszystkimi providerami.

    Zwraca True gdy plik został zapisany, False gdy już istnieje i overwrite=False.
    """
    _ensure_dirs()

    if _KEYS_FILE.exists() and not overwrite:
        return False

    lines: list[str] = [_KEYS_FILE_HEADER]

    for provider_id, section, hint, url in _KEYS_PROVIDERS:
        lines.append(f'; ── {section} {"─" * max(1, 45 - len(section))}\n')
        lines.append(f'[{section}]\n')
        lines.append(f'; Klucz API: {url}\n')
        lines.append(f'api_key = {hint}\n')
        lines.append('\n')

    lines.append(_KEYS_FILE_LOCAL_SECTION)

    try:
        _KEYS_FILE.write_text(''.join(lines), encoding='utf-8')
        return True
    except OSError:
        return False


def _load_keys_from_file() -> dict[str, str]:
    """Wczytaj klucze API z key/api_keys.ini.

    Zwraca słownik {provider_id: api_key}.
    Ignoruje sekcje z placeholder (klucze zaczynające się od 'sk-ant-api03-...' itp.).
    """
    if not _KEYS_FILE.exists():
        return {}

    import configparser
    cfg = configparser.ConfigParser(comment_prefixes=(';', '#'), inline_comment_prefixes=(';',))
    try:
        cfg.read(_KEYS_FILE, encoding='utf-8')
    except Exception:
        return {}

    # Mapowanie sekcji INI → provider_id
    _section_to_provider = {s.lower(): pid for pid, s, _, _ in _KEYS_PROVIDERS}
    # Dodatkowe lokalne
    _section_to_provider.update({
        'openrouter': 'openrouter',
        'ollama':     'ollama',
        'lmstudio':   'lmstudio',
    })

    # Zbiór znanych placeholderów — jeśli klucz == placeholder → pomiń
    _placeholders = {hint for _, _, hint, _ in _KEYS_PROVIDERS}
    _placeholders.update({'sk-or-...', 'ollama', 'lmstudio', '', 'twój_klucz'})

    result: dict[str, str] = {}
    for section in cfg.sections():
        key = cfg.get(section, 'api_key', fallback='').strip()
        if not key or key in _placeholders:
            continue
        # Sprawdź czy klucz wygląda jak placeholder (kończy się na '...')
        if key.endswith('...'):
            continue
        provider_id = _section_to_provider.get(section.lower())
        if provider_id:
            result[provider_id] = key

    return result


# Globalny cache wczytanych kluczy (ładowany raz przy on_load)
_loaded_api_keys: dict[str, str] = {}


def _get_key_for_provider(provider_id: str) -> Optional[str]:
    """Zwróć klucz API dla danego providera z wczytanego pliku (lub None)."""
    return _loaded_api_keys.get(provider_id)


# ─── PROFILE ───────────────────────────────────────────────────────────────────


PROVIDER_DEFAULTS = {
    'anthropic': {
        'model':    'claude-sonnet-4-5',
        'base_url': 'https://api.anthropic.com/v1',
        'models':   [
            'claude-opus-4-5',
            'claude-sonnet-4-5',
            'claude-haiku-4-5',
            'claude-opus-4-0',
            'claude-sonnet-4-0',
        ],
    },
    'openai': {
        'model':    'gpt-4o',
        'base_url': 'https://api.openai.com/v1',
        'models':   [
            'gpt-4o',
            'gpt-4o-mini',
            'gpt-4-turbo',
            'gpt-4.1',
            'gpt-4.1-mini',
            'gpt-4.1-nano',
            'o3',
            'o4-mini',
        ],
    },
    'google': {
        'model':    'gemini-2.0-flash',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta',
        'models':   [
            'gemini-2.5-pro-preview-05-06',
            'gemini-2.5-flash-preview-05-20',
            'gemini-2.0-flash',
            'gemini-2.0-flash-lite',
            'gemini-1.5-pro',
            'gemini-1.5-flash',
        ],
    },
    'mistral': {
        'model':    'mistral-large-latest',
        'base_url': 'https://api.mistral.ai/v1',
        'models':   [
            'mistral-large-latest',
            'mistral-medium-latest',
            'mistral-small-latest',
            'codestral-latest',
            'open-mixtral-8x22b',
        ],
    },
    'groq': {
        'model':    'llama-3.3-70b-versatile',
        'base_url': 'https://api.groq.com/openai/v1',
        'models':   [
            'llama-3.3-70b-versatile',
            'llama-3.1-8b-instant',
            'mixtral-8x7b-32768',
            'gemma2-9b-it',
            'deepseek-r1-distill-llama-70b',
        ],
    },
    'xai': {
        'model':    'grok-3',
        'base_url': 'https://api.x.ai/v1',
        'models':   [
            'grok-3',
            'grok-3-mini',
            'grok-3-fast',
            'grok-2-1212',
        ],
    },
    'deepseek': {
        'model':    'deepseek-chat',
        'base_url': 'https://api.deepseek.com/v1',
        'models':   [
            'deepseek-chat',
            'deepseek-reasoner',
        ],
    },
    'cohere': {
        'model':    'command-r-plus',
        'base_url': 'https://api.cohere.ai/v1',
        'models':   [
            'command-r-plus',
            'command-r',
            'command-light',
        ],
    },
    'perplexity': {
        'model':    'sonar-pro',
        'base_url': 'https://api.perplexity.ai',
        'models':   [
            'sonar-pro',
            'sonar',
            'sonar-reasoning-pro',
            'sonar-reasoning',
        ],
    },
    'openai_compatible': {
        'model':    'llama3',
        'base_url': 'http://localhost:11434/v1',
        'models':   [],
    },
}

# ── Kolory i etykiety providerów ────────────────────────────────────────────────

PROVIDER_LABELS = {
    'anthropic':         f"{_C.MAGENTA}Anthropic{_C.RESET}",
    'openai':            f"{_C.GREEN}OpenAI{_C.RESET}",
    'google':            f"{_C.BYELLOW}Google{_C.RESET}",
    'mistral':           f"{_C.CYAN}Mistral{_C.RESET}",
    'groq':              f"{_C.BGREEN}Groq{_C.RESET}",
    'xai':               f"{_C.BWHITE}xAI{_C.RESET}",
    'deepseek':          f"{_C.BLUE}DeepSeek{_C.RESET}",
    'cohere':            f"{_C.BCYAN}Cohere{_C.RESET}",
    'perplexity':        f"{_C.BYELLOW}Perplexity{_C.RESET}",
    'openai_compatible': f"{_C.CYAN}OpenAI-Compatible{_C.RESET}",
}

# ── Gotowe presetowe profile (wymagają tylko wpisania API key) ───────────────────

# Każdy preset: klucz = krótka nazwa CLI
# Pola: provider, name (wyświetlana), model, system_prompt, key_url, key_hint, desc
PROFILE_PRESETS: Dict[str, dict] = {

    # ── Anthropic ──────────────────────────────────────────────────────────────
    'claude-opus': {
        'provider': 'anthropic', 'profile_name': 'claude-opus',
        'model': 'claude-opus-4-5',
        'desc': 'Anthropic Claude Opus 4.5 — najinteligentniejszy model Claude',
        'key_url': 'https://console.anthropic.com/account/keys',
        'key_hint': 'sk-ant-...',
        'system_prompt': '',
    },
    'claude-sonnet': {
        'provider': 'anthropic', 'profile_name': 'claude-sonnet',
        'model': 'claude-sonnet-4-5',
        'desc': 'Anthropic Claude Sonnet 4.5 — balans inteligencji i szybkości',
        'key_url': 'https://console.anthropic.com/account/keys',
        'key_hint': 'sk-ant-...',
        'system_prompt': '',
    },
    'claude-haiku': {
        'provider': 'anthropic', 'profile_name': 'claude-haiku',
        'model': 'claude-haiku-4-5',
        'desc': 'Anthropic Claude Haiku 4.5 — najszybszy i najtańszy Claude',
        'key_url': 'https://console.anthropic.com/account/keys',
        'key_hint': 'sk-ant-...',
        'system_prompt': '',
    },

    # ── OpenAI ─────────────────────────────────────────────────────────────────
    'gpt-4o': {
        'provider': 'openai', 'profile_name': 'gpt-4o',
        'model': 'gpt-4o',
        'desc': 'OpenAI GPT-4o — flagowy multimodalny model OpenAI',
        'key_url': 'https://platform.openai.com/api-keys',
        'key_hint': 'sk-...',
        'system_prompt': '',
    },
    'gpt-4o-mini': {
        'provider': 'openai', 'profile_name': 'gpt-4o-mini',
        'model': 'gpt-4o-mini',
        'desc': 'OpenAI GPT-4o Mini — szybki i tani GPT-4o',
        'key_url': 'https://platform.openai.com/api-keys',
        'key_hint': 'sk-...',
        'system_prompt': '',
    },
    'gpt-4.1': {
        'provider': 'openai', 'profile_name': 'gpt-4.1',
        'model': 'gpt-4.1',
        'desc': 'OpenAI GPT-4.1 — najnowszy model z oknem 1M tokenów',
        'key_url': 'https://platform.openai.com/api-keys',
        'key_hint': 'sk-...',
        'system_prompt': '',
    },
    'o3': {
        'provider': 'openai', 'profile_name': 'o3',
        'model': 'o3',
        'desc': 'OpenAI o3 — model rozumowania (reasoning)',
        'key_url': 'https://platform.openai.com/api-keys',
        'key_hint': 'sk-...',
        'system_prompt': '',
    },
    'o4-mini': {
        'provider': 'openai', 'profile_name': 'o4-mini',
        'model': 'o4-mini',
        'desc': 'OpenAI o4-mini — szybki model rozumowania',
        'key_url': 'https://platform.openai.com/api-keys',
        'key_hint': 'sk-...',
        'system_prompt': '',
    },

    # ── Google ─────────────────────────────────────────────────────────────────
    'gemini-pro': {
        'provider': 'google', 'profile_name': 'gemini-pro',
        'model': 'gemini-2.5-pro-preview-05-06',
        'desc': 'Google Gemini 2.5 Pro — najlepszy model Google z myśleniem',
        'key_url': 'https://aistudio.google.com/app/apikey',
        'key_hint': 'AIzaSy...',
        'system_prompt': '',
    },
    'gemini-flash': {
        'provider': 'google', 'profile_name': 'gemini-flash',
        'model': 'gemini-2.5-flash-preview-05-20',
        'desc': 'Google Gemini 2.5 Flash — szybki model z myśleniem',
        'key_url': 'https://aistudio.google.com/app/apikey',
        'key_hint': 'AIzaSy...',
        'system_prompt': '',
    },
    'gemini-flash-lite': {
        'provider': 'google', 'profile_name': 'gemini-flash-lite',
        'model': 'gemini-2.0-flash-lite',
        'desc': 'Google Gemini 2.0 Flash Lite — najtańszy Gemini',
        'key_url': 'https://aistudio.google.com/app/apikey',
        'key_hint': 'AIzaSy...',
        'system_prompt': '',
    },

    # ── Mistral ────────────────────────────────────────────────────────────────
    'mistral-large': {
        'provider': 'mistral', 'profile_name': 'mistral-large',
        'model': 'mistral-large-latest',
        'desc': 'Mistral Large — flagowy model Mistral AI',
        'key_url': 'https://console.mistral.ai/api-keys',
        'key_hint': 'klucz Mistral API',
        'system_prompt': '',
    },
    'codestral': {
        'provider': 'mistral', 'profile_name': 'codestral',
        'model': 'codestral-latest',
        'desc': 'Mistral Codestral — specjalistyczny model do kodu',
        'key_url': 'https://console.mistral.ai/api-keys',
        'key_hint': 'klucz Mistral API',
        'system_prompt': 'Jesteś ekspertem programowania. Odpowiadaj zwięźle, podawaj działający kod.',
    },

    # ── Groq (darmowe, bardzo szybkie) ────────────────────────────────────────
    'groq-llama': {
        'provider': 'groq', 'profile_name': 'groq-llama',
        'model': 'llama-3.3-70b-versatile',
        'desc': 'Groq Llama 3.3 70B — darmowe, ultraszybkie wnioskowanie',
        'key_url': 'https://console.groq.com/keys',
        'key_hint': 'gsk_...',
        'system_prompt': '',
    },
    'groq-deepseek': {
        'provider': 'groq', 'profile_name': 'groq-deepseek',
        'model': 'deepseek-r1-distill-llama-70b',
        'desc': 'Groq DeepSeek R1 70B — szybkie rozumowanie za darmo',
        'key_url': 'https://console.groq.com/keys',
        'key_hint': 'gsk_...',
        'system_prompt': '',
    },
    'groq-mixtral': {
        'provider': 'groq', 'profile_name': 'groq-mixtral',
        'model': 'mixtral-8x7b-32768',
        'desc': 'Groq Mixtral 8x7B — MoE model, okno 32k tokenów',
        'key_url': 'https://console.groq.com/keys',
        'key_hint': 'gsk_...',
        'system_prompt': '',
    },

    # ── xAI Grok ──────────────────────────────────────────────────────────────
    'grok-3': {
        'provider': 'xai', 'profile_name': 'grok-3',
        'model': 'grok-3',
        'desc': 'xAI Grok 3 — flagowy model Elona Muska',
        'key_url': 'https://console.x.ai',
        'key_hint': 'xai-...',
        'system_prompt': '',
    },
    'grok-3-mini': {
        'provider': 'xai', 'profile_name': 'grok-3-mini',
        'model': 'grok-3-mini',
        'desc': 'xAI Grok 3 Mini — mniejszy, tańszy Grok z rozumowaniem',
        'key_url': 'https://console.x.ai',
        'key_hint': 'xai-...',
        'system_prompt': '',
    },

    # ── DeepSeek ──────────────────────────────────────────────────────────────
    'deepseek-chat': {
        'provider': 'deepseek', 'profile_name': 'deepseek-chat',
        'model': 'deepseek-chat',
        'desc': 'DeepSeek V3 — zaawansowany chiński model, bardzo tani',
        'key_url': 'https://platform.deepseek.com/api_keys',
        'key_hint': 'klucz DeepSeek API',
        'system_prompt': '',
    },
    'deepseek-r1': {
        'provider': 'deepseek', 'profile_name': 'deepseek-r1',
        'model': 'deepseek-reasoner',
        'desc': 'DeepSeek R1 — model rozumowania krok po kroku (CoT)',
        'key_url': 'https://platform.deepseek.com/api_keys',
        'key_hint': 'klucz DeepSeek API',
        'system_prompt': '',
    },

    # ── Perplexity (szuka w necie) ─────────────────────────────────────────────
    'perplexity-pro': {
        'provider': 'perplexity', 'profile_name': 'perplexity-pro',
        'model': 'sonar-pro',
        'desc': 'Perplexity Sonar Pro — AI z wyszukiwaniem internetowym',
        'key_url': 'https://www.perplexity.ai/settings/api',
        'key_hint': 'pplx-...',
        'system_prompt': 'Odpowiadaj po polsku, cytuj źródła.',
    },
    'perplexity-sonar': {
        'provider': 'perplexity', 'profile_name': 'perplexity-sonar',
        'model': 'sonar',
        'desc': 'Perplexity Sonar — szybsze AI z wyszukiwaniem, tańsze',
        'key_url': 'https://www.perplexity.ai/settings/api',
        'key_hint': 'pplx-...',
        'system_prompt': '',
    },

    # ── Cohere ─────────────────────────────────────────────────────────────────
    'cohere-r+': {
        'provider': 'cohere', 'profile_name': 'cohere-r+',
        'model': 'command-r-plus',
        'desc': 'Cohere Command R+ — silny model RAG i agentowy',
        'key_url': 'https://dashboard.cohere.com/api-keys',
        'key_hint': 'klucz Cohere API',
        'system_prompt': '',
    },

    # ── Lokalne (OpenAI-compatible) ────────────────────────────────────────────
    'ollama-llama': {
        'provider': 'openai_compatible', 'profile_name': 'ollama-llama',
        'model': 'llama3.2',
        'base_url': 'http://localhost:11434/v1',
        'desc': 'Ollama (lokalnie) — llama3.2, brak klucza API',
        'key_url': 'https://ollama.com',
        'key_hint': 'wpisz cokolwiek (np. "ollama")',
        'system_prompt': '',
    },
    'lmstudio': {
        'provider': 'openai_compatible', 'profile_name': 'lmstudio',
        'model': 'local-model',
        'base_url': 'http://localhost:1234/v1',
        'desc': 'LM Studio (lokalnie) — dowolny model załadowany w LM Studio',
        'key_url': 'https://lmstudio.ai',
        'key_hint': 'wpisz cokolwiek (np. "lmstudio")',
        'system_prompt': '',
    },
    'openrouter': {
        'provider': 'openai_compatible', 'profile_name': 'openrouter',
        'model': 'openai/gpt-4o',
        'base_url': 'https://openrouter.ai/api/v1',
        'desc': 'OpenRouter — dostęp do setek modeli przez jeden klucz',
        'key_url': 'https://openrouter.ai/keys',
        'key_hint': 'sk-or-...',
        'system_prompt': '',
    },
}

class ProfileManager:
    """Zarządza profilami API przechowywanymi w ~/.crossterm/config.json → ai.profiles"""

    def _load(self) -> dict:
        return _read_ai_config()

    def _profiles(self) -> dict:
        return self._load().get('profiles', {})

    def _save_profiles(self, profiles: dict) -> None:
        _update_config(profiles=profiles)

    def active_name(self) -> Optional[str]:
        return self._load().get('active_profile')

    def active(self) -> Optional[dict]:
        name = self.active_name()
        if not name:
            return None
        return self._profiles().get(name)

    def list_profiles(self) -> dict:
        return self._profiles()

    def add(self, name: str, provider: str, api_key: str,
            model: str = '', base_url: str = '', system_prompt: str = '') -> bool:
        if provider not in PROVIDER_DEFAULTS:
            _wl(f"{_C.RED}Nieznany provider: {provider}{_C.RESET}")
            return False
        defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS['openai_compatible'])
        profiles = self._profiles()
        profiles[name] = {
            'provider':      provider,
            'api_key':       api_key,
            'model':         model or defaults['model'],
            'base_url':      base_url or defaults['base_url'],
            'system_prompt': system_prompt,
            'created':       time.strftime('%Y-%m-%d %H:%M'),
        }
        self._save_profiles(profiles)
        return True

    def delete(self, name: str) -> bool:
        profiles = self._profiles()
        if name not in profiles:
            return False
        del profiles[name]
        self._save_profiles(profiles)
        active = self.active_name()
        if active == name:
            _update_config(active_profile=None)
        return True

    def use(self, name: str) -> bool:
        if name not in self._profiles():
            return False
        _update_config(active_profile=name)
        return True

    def set_field(self, name: str, field: str, value: str) -> bool:
        profiles = self._profiles()
        if name not in profiles:
            return False
        profiles[name][field] = value
        self._save_profiles(profiles)
        return True

_profile_mgr = ProfileManager()

# ─── HISTORIA KONWERSACJI ───────────────────────────────────────────────────────

class ConversationHistory:
    """Przechowuje historię wiadomości (w pamięci + zapis do pliku)."""

    def __init__(self) -> None:
        self._messages: List[Dict[str, str]] = []
        self._history_file = _AI_DIR / 'history.json'
        _ensure_dirs()

    def add(self, role: str, content: str) -> None:
        self._messages.append({'role': role, 'content': content})
        self._persist()

    def clear(self) -> None:
        self._messages.clear()
        self._persist()

    def messages(self) -> List[Dict[str, str]]:
        return list(self._messages)

    def _persist(self) -> None:
        try:
            self._history_file.write_text(
                json.dumps(self._messages, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception:
            pass

    def load(self) -> None:
        try:
            if self._history_file.exists():
                self._messages = json.loads(
                    self._history_file.read_text(encoding='utf-8')
                )
        except Exception:
            self._messages = []

_history = ConversationHistory()

# ─── KLIENTY API ────────────────────────────────────────────────────────────────

def _http_post(url: str, headers: dict, body: dict, timeout: int = 60) -> dict:
    """Minimalistyczny HTTP POST — używa urllib (stdlib, bez zależności)."""
    import urllib.request
    import urllib.error

    data = json.dumps(body).encode('utf-8')
    req  = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body_err = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f"HTTP {e.code}: {body_err}") from e


def _call_anthropic(profile: dict, messages: list, system: str = '') -> str:
    url = profile['base_url'].rstrip('/') + '/messages'
    headers = {
        'x-api-key':         profile['api_key'],
        'anthropic-version': '2023-06-01',
        'content-type':      'application/json',
    }
    body: dict = {
        'model':      profile['model'],
        'max_tokens': 4096,
        'messages':   messages,
    }
    sp = system or profile.get('system_prompt', '')
    if sp:
        body['system'] = sp
    resp = _http_post(url, headers, body)
    return resp['content'][0]['text']


def _call_openai_compat(profile: dict, messages: list, system: str = '') -> str:
    """Obsługuje OpenAI, Groq, xAI, DeepSeek, Mistral, Perplexity, Cohere,
    OpenRouter i dowolny inny serwer kompatybilny z OpenAI chat/completions."""
    url = profile['base_url'].rstrip('/') + '/chat/completions'
    headers = {
        'Authorization': f"Bearer {profile['api_key']}",
        'Content-Type':  'application/json',
    }
    all_msgs = []
    sp = system or profile.get('system_prompt', '')
    if sp:
        all_msgs.append({'role': 'system', 'content': sp})
    all_msgs.extend(messages)
    body: dict = {
        'model':    profile['model'],
        'messages': all_msgs,
    }
    resp = _http_post(url, headers, body)
    return resp['choices'][0]['message']['content']


def _call_google(profile: dict, messages: list, system: str = '') -> str:
    model   = profile['model']
    api_key = profile['api_key']
    base    = profile['base_url'].rstrip('/')
    url     = f"{base}/models/{model}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}

    contents = []
    for m in messages:
        role = 'user' if m['role'] == 'user' else 'model'
        contents.append({'role': role, 'parts': [{'text': m['content']}]})

    body: dict = {'contents': contents}
    sp = system or profile.get('system_prompt', '')
    if sp:
        body['system_instruction'] = {'parts': [{'text': sp}]}

    resp = _http_post(url, headers, body)
    return resp['candidates'][0]['content']['parts'][0]['text']


# Providerzy obsługiwani przez natywne API (reszta → OpenAI-compat)
_NATIVE_PROVIDERS = {
    'anthropic': _call_anthropic,
    'google':    _call_google,
}


def send_message(user_text: str, profile: Optional[dict] = None,
                 system: str = '', use_history: bool = True) -> str:
    """Wyślij wiadomość do aktywnego (lub podanego) profilu API."""
    p = profile or _profile_mgr.active()
    if not p:
        raise RuntimeError(
            "Brak aktywnego profilu. Ustaw profil: ai profile use <nazwa>"
        )

    if use_history:
        _history.add('user', user_text)
        msgs = _history.messages()
    else:
        msgs = [{'role': 'user', 'content': user_text}]

    provider = p.get('provider', 'openai')

    if provider in _NATIVE_PROVIDERS:
        reply = _NATIVE_PROVIDERS[provider](p, msgs, system)
    else:
        # openai, openai_compatible, groq, xai, deepseek, mistral,
        # perplexity, cohere, openrouter — wszystkie mają /chat/completions
        reply = _call_openai_compat(p, msgs, system)

    if use_history:
        _history.add('assistant', reply)

    return reply

# ─── GUI CHAT (tkinter, osobny wątek — nie blokuje TUI) ─────────────────────────

_gui_window: Optional[Any] = None
_gui_lock   = threading.Lock()


def _run_gui_chat(profile: dict) -> None:
    """Uruchamia okno GUI chat w osobnym wątku Tk."""
    try:
        import tkinter as tk
        from tkinter import scrolledtext
    except ImportError:
        _wl(f"{_C.RED}tkinter niedostępny — zainstaluj python3-tk{_C.RESET}")
        return

    gui_history: List[Dict[str, str]] = []

    root = tk.Tk()
    root.title(f"AI Chat · {profile.get('model', '?')} [{profile.get('provider','?')}]")
    root.geometry("720x520")
    root.configure(bg="#111111")
    root.resizable(True, True)
    root.attributes("-topmost", False)

    # ── Kolory ────────────────────────────────────────────────────────────────
    BG      = "#111111"
    BG2     = "#1a1a1a"
    FG      = "#e0e0e0"
    FG_DIM  = "#888888"
    ACCENT  = "#5b8dd9"
    USER_FG = "#93c5fd"
    BOT_FG  = "#86efac"
    ERR_FG  = "#f87171"
    ENTRY   = "#1f1f1f"

    FONT_MONO = ("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10)
    FONT_NORM = ("Segoe UI", 10)  if sys.platform == "win32" else ("Sans", 10)
    FONT_BOLD = ("Segoe UI Bold", 10) if sys.platform == "win32" else ("Sans Bold", 10)

    # ── Pasek tytułu (z możliwością przeciągania) ──────────────────────────────
    title_bar = tk.Frame(root, bg="#1c1c2e", height=32)
    title_bar.pack(fill="x", side="top")
    title_bar.pack_propagate(False)

    prov = profile.get('provider', '?').capitalize()
    mod  = profile.get('model', '?')
    lbl  = tk.Label(title_bar, text=f"  🤖  AI Chat  ·  {prov} / {mod}",
                    bg="#1c1c2e", fg=FG, font=FONT_NORM, anchor="w")
    lbl.pack(side="left", fill="y", padx=6)

    def _close():
        global _gui_window
        root.destroy()
        _gui_window = None

    btn_x = tk.Button(title_bar, text="✕", bg="#1c1c2e", fg=FG_DIM,
                      activebackground="#3a0000", activeforeground="white",
                      relief="flat", cursor="hand2", command=_close,
                      font=FONT_NORM, padx=8)
    btn_x.pack(side="right", fill="y")

    def _drag_start(e):
        root._dx, root._dy = e.x, e.y

    def _drag_move(e):
        x = root.winfo_x() + e.x - root._dx
        y = root.winfo_y() + e.y - root._dy
        root.geometry(f"+{x}+{y}")

    title_bar.bind("<Button-1>",   _drag_start)
    title_bar.bind("<B1-Motion>",  _drag_move)
    lbl.bind(      "<Button-1>",   _drag_start)
    lbl.bind(      "<B1-Motion>",  _drag_move)

    # ── Obszar wiadomości ──────────────────────────────────────────────────────
    chat_frame = tk.Frame(root, bg=BG)
    chat_frame.pack(fill="both", expand=True, padx=0, pady=0)

    chat_box = scrolledtext.ScrolledText(
        chat_frame, wrap="word", bg=BG2, fg=FG,
        font=FONT_MONO, state="disabled",
        relief="flat", bd=0, padx=12, pady=10,
        selectbackground=ACCENT,
    )
    chat_box.pack(fill="both", expand=True)

    # Tag kolory
    chat_box.tag_config("user",      foreground=USER_FG, font=(FONT_BOLD[0], FONT_BOLD[1]))
    chat_box.tag_config("user_text", foreground=FG)
    chat_box.tag_config("bot",       foreground=BOT_FG,  font=(FONT_BOLD[0], FONT_BOLD[1]))
    chat_box.tag_config("bot_text",  foreground=FG)
    chat_box.tag_config("error",     foreground=ERR_FG)
    chat_box.tag_config("sep",       foreground="#333333")
    chat_box.tag_config("thinking",  foreground=FG_DIM, font=(FONT_MONO[0], FONT_MONO[1]))

    def _append(text: str, tag: str = "bot_text") -> None:
        chat_box.configure(state="normal")
        chat_box.insert("end", text, tag)
        chat_box.configure(state="disabled")
        chat_box.see("end")

    def _append_sep() -> None:
        _append("\n" + "─" * 60 + "\n", "sep")

    # ── Panel wejściowy ────────────────────────────────────────────────────────
    bottom = tk.Frame(root, bg="#151515", pady=6)
    bottom.pack(fill="x", side="bottom")

    # Wiersz informacyjny
    info_var = tk.StringVar(value=f"Model: {mod}  |  Provider: {prov}  |  Enter — wyślij  |  Shift+Enter — nowy wiersz")
    info_lbl = tk.Label(bottom, textvariable=info_var, bg="#151515",
                        fg=FG_DIM, font=(FONT_NORM[0], 8), anchor="w")
    info_lbl.pack(fill="x", padx=10)

    entry_frame = tk.Frame(bottom, bg="#151515")
    entry_frame.pack(fill="x", padx=8, pady=(4, 4))

    entry = tk.Text(entry_frame, height=3, bg=ENTRY, fg=FG,
                    insertbackground=FG, relief="flat", font=FONT_MONO,
                    padx=8, pady=6, wrap="word")
    entry.pack(side="left", fill="both", expand=True)
    entry.focus()

    send_btn = tk.Button(entry_frame, text="▶ Wyślij", bg=ACCENT, fg="white",
                         activebackground="#4a7bc7", activeforeground="white",
                         relief="flat", cursor="hand2", font=FONT_NORM,
                         padx=12)
    send_btn.pack(side="right", padx=(6, 0), fill="y")

    # ── Przyciski dolne ────────────────────────────────────────────────────────
    btn_row = tk.Frame(bottom, bg="#151515")
    btn_row.pack(fill="x", padx=8, pady=(0, 2))

    def _btn(parent, text, cmd, fg_col=FG_DIM):
        b = tk.Button(parent, text=text, command=cmd,
                      bg="#1a1a1a", fg=fg_col,
                      activebackground="#252525", activeforeground=FG,
                      relief="flat", cursor="hand2", font=(FONT_NORM[0], 8),
                      padx=6, pady=2)
        b.pack(side="left", padx=2)
        return b

    def _do_clear():
        chat_box.configure(state="normal")
        chat_box.delete("1.0", "end")
        chat_box.configure(state="disabled")
        gui_history.clear()

    def _do_copy_last():
        if gui_history:
            root.clipboard_clear()
            root.clipboard_append(gui_history[-1].get('content', ''))
            info_var.set("✓ Skopiowano ostatnią odpowiedź")
            root.after(2000, lambda: info_var.set(
                f"Model: {mod}  |  Provider: {prov}  |  Enter — wyślij  |  Shift+Enter — nowy wiersz"))

    def _do_export():
        out = _AI_DIR / f"chat_export_{time.strftime('%Y%m%d_%H%M%S')}.json"
        try:
            out.write_text(json.dumps(gui_history, indent=2, ensure_ascii=False), encoding='utf-8')
            info_var.set(f"✓ Zapisano: {out}")
        except Exception as ex:
            info_var.set(f"Błąd eksportu: {ex}")
        root.after(3000, lambda: info_var.set(
            f"Model: {mod}  |  Provider: {prov}  |  Enter — wyślij  |  Shift+Enter — nowy wiersz"))

    _btn(btn_row, "🗑 Wyczyść",       _do_clear)
    _btn(btn_row, "📋 Kopiuj ostatnią", _do_copy_last)
    _btn(btn_row, "💾 Eksportuj",      _do_export)

    _sys_prompt_var = tk.StringVar(value=profile.get('system_prompt', ''))

    def _do_system():
        win = tk.Toplevel(root)
        win.title("System Prompt")
        win.geometry("500x220")
        win.configure(bg=BG)
        win.grab_set()
        tk.Label(win, text="System Prompt:", bg=BG, fg=FG, font=FONT_NORM).pack(anchor="w", padx=10, pady=(10,2))
        t = tk.Text(win, height=6, bg=ENTRY, fg=FG, insertbackground=FG,
                    relief="flat", font=FONT_MONO, padx=6, pady=4)
        t.pack(fill="both", expand=True, padx=10)
        t.insert("1.0", _sys_prompt_var.get())
        def _save_sp():
            _sys_prompt_var.set(t.get("1.0", "end").strip())
            win.destroy()
        tk.Button(win, text="Zapisz", command=_save_sp,
                  bg=ACCENT, fg="white", relief="flat", padx=12, pady=4,
                  cursor="hand2").pack(pady=8)
        win.bind("<Escape>", lambda e: win.destroy())

    _btn(btn_row, "⚙ System prompt", _do_system, ACCENT)

    # ── Logika wysyłania ────────────────────────────────────────────────────────
    _sending = threading.Event()

    def _do_send(event=None):
        if _sending.is_set():
            return
        text = entry.get("1.0", "end").strip()
        if not text:
            return

        entry.delete("1.0", "end")
        _append("\n")
        _append("You  ", "user")
        _append(f"[{time.strftime('%H:%M')}]\n", "sep")
        _append(text + "\n", "user_text")
        gui_history.append({'role': 'user', 'content': text})

        _sending.set()
        send_btn.configure(state="disabled", text="⏳")

        def _think():
            _append("\n", "thinking")
            _append("● Przetwarzam...\n", "thinking")
            try:
                reply = send_message(
                    text, profile=profile,
                    system=_sys_prompt_var.get(),
                    use_history=False,
                )
                # Usuń "przetwarzam" — nadpisz czyszcząc ostatnie linie
                chat_box.configure(state="normal")
                # Cofnij "● Przetwarzam...\n" i "\n" (dwa wiersze)
                chat_box.delete("end-3l", "end")
                chat_box.configure(state="disabled")

                _append_sep()
                _append("AI   ", "bot")
                _append(f"[{time.strftime('%H:%M')}]\n", "sep")
                for line in reply.splitlines():
                    _append(line + "\n", "bot_text")
                gui_history.append({'role': 'assistant', 'content': reply})
            except Exception as ex:
                chat_box.configure(state="normal")
                try:
                    chat_box.delete("end-3l", "end")
                except Exception:
                    pass
                chat_box.configure(state="disabled")
                _append(f"\n⚠ Błąd: {ex}\n", "error")
            finally:
                _sending.clear()
                send_btn.configure(state="normal", text="▶ Wyślij")

        threading.Thread(target=_think, daemon=True).start()

    send_btn.configure(command=_do_send)

    def _on_enter(event):
        if event.state & 0x1:   # Shift+Enter → nowy wiersz
            return None
        _do_send()
        return "break"

    entry.bind("<Return>", _on_enter)
    root.bind("<Escape>", lambda e: _close())

    # ── Powitanie ──────────────────────────────────────────────────────────────
    _append(f"╔{'═'*58}╗\n", "sep")
    _append(f"║  CrossTerm AI Chat — {prov} · {mod}{' '*(36-len(prov)-len(mod))}║\n", "bot")
    _append(f"║  Wpisz pytanie i naciśnij Enter lub ▶ Wyślij{' '*12}║\n", "sep")
    _append(f"╚{'═'*58}╝\n\n", "sep")

    root.protocol("WM_DELETE_WINDOW", _close)
    root.mainloop()


def _open_gui(args, terminal=None) -> None:
    global _gui_window

    profile = _profile_mgr.active()
    if not profile:
        _wl(f"{_C.RED}Brak aktywnego profilu. Ustaw: ai profile use <nazwa>{_C.RESET}")
        return

    with _gui_lock:
        if _gui_window is not None:
            _wl(f"{_C.BYELLOW}Okno AI chat już jest otwarte.{_C.RESET}")
            return
        _gui_window = True   # flaga - zostanie zastąpiona rootem w wątku

    t = threading.Thread(target=_run_gui_chat, args=(profile,), daemon=True)
    t.start()
    _wl(f"{_C.BGREEN}✓ Otwarto okno AI chat ({profile.get('provider','?')} · {profile.get('model','?')}){_C.RESET}")
    _wl(f"{_C.DIM}  Okno działa niezależnie — terminal pozostaje aktywny.{_C.RESET}")

# ─── INTERAKTYWNY TERMINAL CHAT ─────────────────────────────────────────────────

def _inline_chat(args, terminal=None) -> None:
    """Tryb inline chat w terminalu (bez GUI)."""
    profile = _profile_mgr.active()
    if not profile:
        _wl(f"{_C.RED}Brak aktywnego profilu.{_C.RESET}")
        return

    prov = profile.get('provider', '?')
    mod  = profile.get('model', '?')

    _wl(f"\n{_C.BCYAN}╭── AI Terminal Chat ──────────────────────╮{_C.RESET}")
    _wl(f"{_C.BCYAN}│{_C.RESET} Provider : {_C.BOLD}{prov}{_C.RESET}")
    _wl(f"{_C.BCYAN}│{_C.RESET} Model    : {_C.BOLD}{mod}{_C.RESET}")
    _wl(f"{_C.BCYAN}│{_C.RESET} Wyjście  : {_C.DIM}exit / quit / Ctrl+C{_C.RESET}")
    _wl(f"{_C.BCYAN}╰───────────────────────────────────────────╯{_C.RESET}\n")

    while True:
        try:
            sys.stdout.write(f"{_C.BYELLOW}You ›{_C.RESET} ")
            sys.stdout.flush()
            line = sys.stdin.readline()
            if not line:
                break
            text = line.strip()
            if not text:
                continue
            if text.lower() in ('exit', 'quit', 'q', ':q'):
                _wl(f"{_C.DIM}Zamknięto chat.{_C.RESET}")
                break

            _wl(f"{_C.DIM}Przetwarzam...{_C.RESET}")
            try:
                reply = send_message(text, use_history=True)
                _wl(f"\n{_C.BGREEN}AI ›{_C.RESET}")
                for para in reply.split('\n'):
                    wrapped = textwrap.fill(para, width=78) if para.strip() else para
                    _wl(f"  {wrapped}" if wrapped else "")
                _wl("")
            except Exception as ex:
                _wl(f"{_C.RED}⚠ Błąd: {ex}{_C.RESET}\n")

        except KeyboardInterrupt:
            _wl(f"\n{_C.DIM}Przerwano.{_C.RESET}")
            break

# ─── KOMENDY PROFILÓW ───────────────────────────────────────────────────────────

def _prompt(label: str, secret: bool = False) -> str:
    import getpass
    sys.stdout.write(f"  {_C.BYELLOW}{label}{_C.RESET}: ")
    sys.stdout.flush()
    if secret:
        return getpass.getpass("")
    return sys.stdin.readline().strip()

def _cmd_profile_add(args, terminal=None) -> None:
    name = args[0] if args else _prompt("Nazwa profilu")
    if not name:
        _wl(f"{_C.RED}Podaj nazwę profilu.{_C.RESET}")
        return

    _wl(f"\n{_C.BCYAN}Dostępne providery:{_C.RESET}")
    for i, (k, lbl) in enumerate(PROVIDER_LABELS.items(), 1):
        _wl(f"  {_C.DIM}{i}.{_C.RESET} {lbl}")
    prov_input = _prompt("Provider (nazwa lub numer)")

    prov_map = list(PROVIDER_DEFAULTS.keys())
    provider = ''
    if prov_input.isdigit() and 1 <= int(prov_input) <= len(prov_map):
        provider = prov_map[int(prov_input) - 1]
    elif prov_input in PROVIDER_DEFAULTS:
        provider = prov_input
    else:
        # fuzzy
        for k in PROVIDER_DEFAULTS:
            if prov_input.lower() in k:
                provider = k
                break
    if not provider:
        _wl(f"{_C.RED}Nieznany provider: {prov_input}{_C.RESET}")
        return

    api_key  = _prompt("API Key", secret=True)
    if not api_key:
        _wl(f"{_C.RED}API Key jest wymagany.{_C.RESET}")
        return

    defaults = PROVIDER_DEFAULTS[provider]
    _wl(f"  {_C.DIM}Dostępne modele: {', '.join(defaults['models'][:5])}{_C.RESET}")
    model    = _prompt(f"Model [{defaults['model']}]") or defaults['model']
    base_url = ''
    if provider == 'openai_compatible':
        base_url = _prompt(f"Base URL [{defaults['base_url']}]") or defaults['base_url']

    sp = _prompt("System prompt (opcjonalny, Enter aby pominąć)")

    ok = _profile_mgr.add(name, provider, api_key, model, base_url, sp)
    if ok:
        _wl(f"\n{_C.BGREEN}✓ Profil '{name}' dodany.{_C.RESET}")
        if not _profile_mgr.active_name():
            _profile_mgr.use(name)
            _wl(f"{_C.BGREEN}✓ Aktywowano jako domyślny.{_C.RESET}")
    else:
        _wl(f"{_C.RED}Błąd podczas dodawania profilu.{_C.RESET}")


def _cmd_profile_list(args, terminal=None) -> None:
    profiles = _profile_mgr.list_profiles()
    active   = _profile_mgr.active_name()

    if not profiles:
        _wl(f"{_C.DIM}Brak zapisanych profili. Dodaj: ai profile add{_C.RESET}")
        return

    _wl(f"\n{_C.BCYAN}{'─'*58}{_C.RESET}")
    _wl(f"  {'Nazwa':<18} {'Provider':<16} {'Model':<28} {'Aktywny'}")
    _wl(f"{_C.BCYAN}{'─'*58}{_C.RESET}")
    for name, p in profiles.items():
        marker = f"{_C.BGREEN}✓{_C.RESET}" if name == active else " "
        prov   = PROVIDER_LABELS.get(p.get('provider','?'), p.get('provider','?'))
        model  = p.get('model','?')[:28]
        n_col  = f"{_C.BWHITE}{name}{_C.RESET}" if name == active else name
        _wl(f"  {n_col:<18} {prov:<16} {_C.DIM}{model}{_C.RESET:<28} {marker}")
    _wl(f"{_C.BCYAN}{'─'*58}{_C.RESET}\n")


def _cmd_profile_use(args, terminal=None) -> None:
    name = args[0] if args else _prompt("Nazwa profilu do aktywacji")
    if _profile_mgr.use(name):
        _wl(f"{_C.BGREEN}✓ Aktywowano profil: {name}{_C.RESET}")
    else:
        _wl(f"{_C.RED}Profil '{name}' nie istnieje. Lista: ai profile list{_C.RESET}")


def _cmd_profile_del(args, terminal=None) -> None:
    name = args[0] if args else _prompt("Nazwa profilu do usunięcia")
    sys.stdout.write(f"  {_C.RED}Usunąć profil '{name}'? [t/N]{_C.RESET} ")
    sys.stdout.flush()
    ans = sys.stdin.readline().strip().lower()
    if ans in ('t', 'y', 'tak', 'yes'):
        if _profile_mgr.delete(name):
            _wl(f"{_C.BGREEN}✓ Usunięto profil: {name}{_C.RESET}")
        else:
            _wl(f"{_C.RED}Profil '{name}' nie istnieje.{_C.RESET}")
    else:
        _wl(f"{_C.DIM}Anulowano.{_C.RESET}")


def _cmd_profile_show(args, terminal=None) -> None:
    name = args[0] if args else _profile_mgr.active_name()
    if not name:
        _wl(f"{_C.RED}Podaj nazwę lub aktywuj profil.{_C.RESET}")
        return
    p = _profile_mgr.list_profiles().get(name)
    if not p:
        _wl(f"{_C.RED}Profil '{name}' nie istnieje.{_C.RESET}")
        return
    _wl(f"\n{_C.BCYAN}Profil: {_C.BWHITE}{name}{_C.RESET}")
    for k, v in p.items():
        disp = ('*' * min(len(str(v)), 8) + '...') if k == 'api_key' else v
        _wl(f"  {_C.DIM}{k:<16}{_C.RESET} {disp}")
    _wl("")


def _cmd_profile(args, terminal=None) -> None:
    sub = args[0] if args else ''
    rest = args[1:]
    if sub == 'add':      _cmd_profile_add(rest, terminal)
    elif sub == 'list':   _cmd_profile_list(rest, terminal)
    elif sub == 'use':    _cmd_profile_use(rest, terminal)
    elif sub == 'del':    _cmd_profile_del(rest, terminal)
    elif sub == 'show':   _cmd_profile_show(rest, terminal)
    elif sub in ('preset', 'presets', 'templates'):
        _cmd_profile_preset(rest, terminal)
    else:
        # skrót: "ai profile <nazwa>" → aktywacja jeśli istnieje
        if sub and sub in _profile_mgr.list_profiles():
            _cmd_profile_use([sub], terminal)
        else:
            _cmd_profile_list([], terminal)
            _wl(f"{_C.DIM}Podkomendy: add · list · use · del · show · preset{_C.RESET}")


# ─── GOTOWE PRESETY ─────────────────────────────────────────────────────────────

_PRESET_GROUP_ORDER = [
    ('anthropic',         '🟣 Anthropic Claude'),
    ('openai',            '🟢 OpenAI GPT / o-series'),
    ('google',            '🟡 Google Gemini'),
    ('groq',              '🟩 Groq (darmowe, bardzo szybkie)'),
    ('xai',               '⬜ xAI Grok'),
    ('deepseek',          '🔵 DeepSeek'),
    ('mistral',           '🩵 Mistral AI'),
    ('perplexity',        '🔸 Perplexity (z wyszukiwaniem)'),
    ('cohere',            '🩸 Cohere'),
    ('openai_compatible', '⚙  Lokalne / OpenRouter'),
]


def _cmd_profile_preset(args, terminal=None) -> None:
    """
    ai profile preset           — lista wszystkich presetów z grupowaniem
    ai profile preset <klucz>   — dodaj preset podając tylko API key
    """
    if args:
        _preset_install(args[0], terminal)
        return

    _wl(f"\n{_C.BCYAN}╭── Gotowe profile AI ──────────────────────────────────────────────╮{_C.RESET}")
    _wl(f"{_C.BCYAN}│{_C.RESET}  Użycie: {_C.BYELLOW}ai profile preset <klucz>{_C.RESET}   — instaluje profil (pyta o API key)")
    _wl(f"{_C.BCYAN}├───────────────────────────────────────────────────────────────────┤{_C.RESET}")

    grouped: Dict[str, list] = {}
    for key, preset in PROFILE_PRESETS.items():
        prov = preset['provider']
        grouped.setdefault(prov, []).append((key, preset))

    installed = set(_profile_mgr.list_profiles().keys())

    for prov_id, prov_label in _PRESET_GROUP_ORDER:
        if prov_id not in grouped:
            continue
        _wl(f"{_C.BCYAN}│{_C.RESET}  {_C.BOLD}{prov_label}{_C.RESET}")
        for key, preset in grouped[prov_id]:
            tick = f"{_C.BGREEN}✓{_C.RESET}" if preset['profile_name'] in installed else f"{_C.DIM}○{_C.RESET}"
            desc = preset['desc']
            hint = preset.get('key_hint', '')
            _wl(f"{_C.BCYAN}│{_C.RESET}  {tick} {_C.BYELLOW}{key:<22}{_C.RESET} {_C.DIM}{desc}{_C.RESET}")
            _wl(f"{_C.BCYAN}│{_C.RESET}    {_C.GRAY}klucz: {hint}  →  {preset.get('key_url','')}{_C.RESET}")

    _wl(f"{_C.BCYAN}╰───────────────────────────────────────────────────────────────────╯{_C.RESET}")
    _wl(f"  {_C.DIM}Przykład: ai profile preset groq-llama{_C.RESET}\n")


def _preset_install(key: str, terminal=None) -> None:
    """Instaluje gotowy preset — pyta tylko o API key."""
    preset = PROFILE_PRESETS.get(key)
    if not preset:
        # Fuzzy search
        matches = [k for k in PROFILE_PRESETS if key.lower() in k.lower()]
        if len(matches) == 1:
            preset = PROFILE_PRESETS[matches[0]]
            key    = matches[0]
        elif matches:
            _wl(f"{_C.BYELLOW}Znaleziono kilka pasujących presetów:{_C.RESET}")
            for m in matches:
                _wl(f"  {_C.DIM}·{_C.RESET} {m}")
            return
        else:
            _wl(f"{_C.RED}Nieznany preset: '{key}'{_C.RESET}")
            _wl(f"{_C.DIM}Lista presetów: ai profile preset{_C.RESET}")
            return

    pname    = preset['profile_name']
    provider = preset['provider']
    model    = preset['model']
    desc     = preset['desc']
    key_url  = preset.get('key_url', '')
    key_hint = preset.get('key_hint', '')
    sp       = preset.get('system_prompt', '')
    base_url = preset.get('base_url', PROVIDER_DEFAULTS.get(provider, {}).get('base_url', ''))

    prov_label = PROVIDER_LABELS.get(provider, provider)
    _wl(f"\n{_C.BCYAN}╭── Instalacja presetu ──────────────────────╮{_C.RESET}")
    _wl(f"{_C.BCYAN}│{_C.RESET}  Preset   : {_C.BOLD}{key}{_C.RESET}")
    _wl(f"{_C.BCYAN}│{_C.RESET}  Provider : {prov_label}")
    _wl(f"{_C.BCYAN}│{_C.RESET}  Model    : {_C.BOLD}{model}{_C.RESET}")
    _wl(f"{_C.BCYAN}│{_C.RESET}  Opis     : {_C.DIM}{desc}{_C.RESET}")
    if key_url:
        _wl(f"{_C.BCYAN}│{_C.RESET}  API klucz: {_C.DIM}{key_url}{_C.RESET}")
    _wl(f"{_C.BCYAN}╰───────────────────────────────────────────╯{_C.RESET}")

    # Sprawdź czy profil już istnieje
    existing = _profile_mgr.list_profiles().get(pname)
    if existing:
        sys.stdout.write(f"  {_C.BYELLOW}Profil '{pname}' już istnieje. Nadpisać? [t/N]{_C.RESET} ")
        sys.stdout.flush()
        ans = sys.stdin.readline().strip().lower()
        if ans not in ('t', 'y', 'tak', 'yes'):
            _wl(f"{_C.DIM}Anulowano.{_C.RESET}")
            return

    # Pola opcjonalne dla local/OpenRouter
    if provider == 'openai_compatible':
        default_bu = PROVIDER_DEFAULTS['openai_compatible']['base_url']
        if base_url != default_bu:
            _wl(f"  {_C.DIM}Base URL: {base_url}{_C.RESET}")
        else:
            sys.stdout.write(f"  {_C.BYELLOW}Base URL [{base_url}]{_C.RESET}: ")
            sys.stdout.flush()
            inp = sys.stdin.readline().strip()
            if inp:
                base_url = inp

        sys.stdout.write(f"  {_C.BYELLOW}Model [{model}]{_C.RESET}: ")
        sys.stdout.flush()
        inp = sys.stdin.readline().strip()
        if inp:
            model = inp

    # Dla lokalnych modeli API key może być dummy
    if provider == 'openai_compatible' and 'localhost' in base_url:
        _wl(f"  {_C.DIM}(lokalny serwer — klucz API może być dowolny, np. 'ollama'){_C.RESET}")

    # Sprawdź czy klucz jest dostępny z pliku api_keys.ini
    file_key = _get_key_for_provider(provider)
    if not file_key and provider == 'openai_compatible':
        # Dla OpenRouter sprawdź osobno
        file_key = _get_key_for_provider('openrouter') if 'openrouter' in base_url else None

    if file_key:
        _wl(f"  {_C.BGREEN}✓ Klucz API wczytany z pliku key/api_keys.ini{_C.RESET}")
        api_key = file_key
    else:
        import getpass
        sys.stdout.write(
            f"  {_C.BYELLOW}API Key{_C.RESET} {_C.DIM}[{key_hint}]{_C.RESET}: "
        )
        sys.stdout.flush()
        api_key = getpass.getpass("")

    if not api_key:
        _wl(f"{_C.RED}Anulowano — klucz API jest wymagany.{_C.RESET}")
        return

    ok = _profile_mgr.add(pname, provider, api_key, model, base_url, sp)
    if ok:
        _wl(f"\n{_C.BGREEN}✓ Profil '{pname}' zainstalowany.{_C.RESET}")
        if not _profile_mgr.active_name():
            _profile_mgr.use(pname)
            _wl(f"{_C.BGREEN}✓ Aktywowano jako domyślny.{_C.RESET}")
        else:
            sys.stdout.write(f"  {_C.BYELLOW}Aktywować jako domyślny? [t/N]{_C.RESET} ")
            sys.stdout.flush()
            ans = sys.stdin.readline().strip().lower()
            if ans in ('t', 'y', 'tak', 'yes'):
                _profile_mgr.use(pname)
                _wl(f"{_C.BGREEN}✓ Aktywowano.{_C.RESET}")
    else:
        _wl(f"{_C.RED}Błąd instalacji presetu.{_C.RESET}")




# ─── KOMENDY KLUCZY API ──────────────────────────────────────────────────────────

def _cmd_keys(args, terminal=None) -> None:
    """
    ai keys                 — status (które klucze są wczytane)
    ai keys generate        — wygeneruj plik key/api_keys.ini
    ai keys generate --force — nadpisz istniejący plik
    ai keys load            — wczytaj / odśwież klucze z pliku
    ai keys show            — pokaż zawartość pliku (z maskowaniem kluczy)
    ai keys path            — pokaż ścieżkę do pliku
    ai keys clear           — wyczyść wszystkie klucze z pamięci
    ai keys clear <provider> — wyczyść konkretny klucz z pamięci
    """
    global _loaded_api_keys

    sub = args[0].lower() if args else ''

    if sub == 'generate':
        force = '--force' in args or '-f' in args
        if _KEYS_FILE.exists() and not force:
            _wl(f"\n  {_C.BYELLOW}Plik już istnieje: {_KEYS_FILE}{_C.RESET}")
            _wl(f"  {_C.DIM}Użyj: ai keys generate --force  aby nadpisać{_C.RESET}\n")
            return
        ok = _generate_keys_file(overwrite=force)
        if ok:
            _wl(f"\n  {_C.BGREEN}✓ Wygenerowano plik kluczy:{_C.RESET}")
            _wl(f"  {_C.DIM}{_KEYS_FILE}{_C.RESET}\n")
            _wl(f"  {_C.BYELLOW}Edytuj plik i wpisz swoje klucze API,{_C.RESET}")
            _wl(f"  {_C.DIM}następnie wczytaj: ai keys load{_C.RESET}\n")
        else:
            _wl(f"\n  {_C.RED}Błąd zapisu pliku: {_KEYS_FILE}{_C.RESET}\n")
        return

    if sub == 'load':
        _loaded_api_keys = _load_keys_from_file()
        if not _loaded_api_keys:
            if not _KEYS_FILE.exists():
                _wl(f"\n  {_C.BYELLOW}Brak pliku kluczy.{_C.RESET}")
                _wl(f"  {_C.DIM}Wygeneruj go: ai keys generate{_C.RESET}\n")
            else:
                _wl(f"\n  {_C.DIM}Plik istnieje, ale nie znaleziono uzupełnionych kluczy.{_C.RESET}")
                _wl(f"  {_C.DIM}Edytuj: {_KEYS_FILE}{_C.RESET}\n")
        else:
            _wl(f"\n  {_C.BGREEN}✓ Wczytano {len(_loaded_api_keys)} klucz(y) API:{_C.RESET}")
            for pid, key in _loaded_api_keys.items():
                masked = key[:6] + '...' + key[-3:] if len(key) > 10 else '***'
                _wl(f"    {_C.DIM}·{_C.RESET} {_C.BYELLOW}{pid:<16}{_C.RESET} {_C.DIM}{masked}{_C.RESET}")
            _wl('')
        return

    if sub == 'show':
        if not _KEYS_FILE.exists():
            _wl(f"\n  {_C.BYELLOW}Brak pliku kluczy: {_KEYS_FILE}{_C.RESET}")
            _wl(f"  {_C.DIM}Wygeneruj go: ai keys generate{_C.RESET}\n")
            return
        _wl(f"\n  {_C.BCYAN}Plik: {_KEYS_FILE}{_C.RESET}\n")
        try:
            content = _KEYS_FILE.read_text(encoding='utf-8')
        except OSError as e:
            _wl(f"  {_C.RED}Błąd odczytu: {e}{_C.RESET}\n")
            return
        import re as _re
        # Maskuj klucze — zastąp wartości api_key = <wartość> (jeśli nie jest placeholder)
        def _mask_key(m: 're.Match') -> str:
            val = m.group(1).strip()
            if val.endswith('...') or not val:
                return m.group(0)
            masked = val[:6] + '...' + val[-3:] if len(val) > 10 else '***'
            return m.group(0).replace(val, masked)
        masked_content = _re.sub(r'api_key\s*=\s*(.+)', _mask_key, content)
        for line in masked_content.splitlines():
            if line.startswith(';'):
                _wl(f"  {_C.GRAY}{line}{_C.RESET}")
            elif line.startswith('['):
                _wl(f"  {_C.BCYAN}{line}{_C.RESET}")
            elif '=' in line:
                k, _, v = line.partition('=')
                _wl(f"  {_C.DIM}{k}={_C.RESET}{_C.BYELLOW}{v}{_C.RESET}")
            else:
                _wl(f"  {line}")
        _wl('')
        return

    if sub == 'path':
        _wl(f"\n  {_KEYS_FILE}\n")
        return

    if sub == 'clear':
        # ai keys clear              — wyczyść wszystkie klucze z pamięci
        # ai keys clear <provider>   — wyczyść konkretny klucz z pamięci
        target = args[1].lower() if len(args) > 1 else None
        if target:
            if target in _loaded_api_keys:
                del _loaded_api_keys[target]
                _wl(f"\n  {_C.BGREEN}✓ Usunięto klucz z pamięci:{_C.RESET} {_C.BYELLOW}{target}{_C.RESET}\n")
            else:
                # szukaj częściowego dopasowania (np. 'ant' → 'anthropic')
                matches = [k for k in _loaded_api_keys if target in k]
                if len(matches) == 1:
                    del _loaded_api_keys[matches[0]]
                    _wl(f"\n  {_C.BGREEN}✓ Usunięto klucz z pamięci:{_C.RESET} {_C.BYELLOW}{matches[0]}{_C.RESET}\n")
                elif len(matches) > 1:
                    _wl(f"\n  {_C.BYELLOW}Niejednoznaczne: {', '.join(matches)}{_C.RESET}")
                    _wl(f"  {_C.DIM}Podaj pełną nazwę providera.{_C.RESET}\n")
                else:
                    _wl(f"\n  {_C.DIM}Nie znaleziono klucza: {target}{_C.RESET}\n")
        else:
            count = len(_loaded_api_keys)
            _loaded_api_keys.clear()
            _wl(f"\n  {_C.BGREEN}✓ Wyczyszczono {count} klucz(y) z pamięci terminala.{_C.RESET}")
            _wl(f"  {_C.DIM}Plik key/api_keys.ini pozostał bez zmian.{_C.RESET}\n")
        return

    # Domyślnie: status
    _wl(f"\n  {_C.BCYAN}{'─' * 50}{_C.RESET}")
    _wl(f"  {_C.BOLD}AI Keys  —  klucze API z pliku{_C.RESET}")
    _wl(f"  {_C.BCYAN}{'─' * 50}{_C.RESET}")
    _wl(f"  Plik : {_C.DIM}{_KEYS_FILE}{_C.RESET}")
    exists_str = f"{_C.BGREEN}istnieje{_C.RESET}" if _KEYS_FILE.exists() else f"{_C.RED}brak{_C.RESET}"
    _wl(f"  Stan : {exists_str}")

    if _loaded_api_keys:
        _wl(f"  Wczytane klucze ({len(_loaded_api_keys)}):")
        for pid, key in _loaded_api_keys.items():
            masked = key[:6] + '...' + key[-3:] if len(key) > 10 else '***'
            _wl(f"    {_C.DIM}·{_C.RESET} {_C.BYELLOW}{pid:<16}{_C.RESET} {_C.DIM}{masked}{_C.RESET}")
    else:
        _wl(f"  {_C.DIM}Brak wczytanych kluczy.{_C.RESET}")

    _wl(f"\n  {_C.DIM}Podkomendy:{_C.RESET}")
    subcmds = [
        ('ai keys generate',         'Wygeneruj plik key/api_keys.ini'),
        ('ai keys generate --force',  'Nadpisz istniejący plik'),
        ('ai keys load',              'Wczytaj / odśwież klucze z pliku'),
        ('ai keys show',              'Pokaż zawartość pliku (z maskowaniem)'),
        ('ai keys path',              'Pokaż ścieżkę do pliku'),
        ('ai keys clear',             'Wyczyść wszystkie klucze z pamięci'),
        ('ai keys clear <provider>',  'Wyczyść konkretny klucz z pamięci'),
    ]
    for cmd, desc in subcmds:
        _wl(f"  {_C.BYELLOW}{cmd:<36}{_C.RESET} {_C.DIM}{desc}{_C.RESET}")
    _wl('')


# ─── AI ASK ──────────────────────────────────────────────────────────────────────

def _cmd_ask(args, terminal=None) -> None:
    if not args:
        _wl(f"{_C.RED}Użycie: ai ask <pytanie>{_C.RESET}")
        return
    question = ' '.join(args)
    profile = _profile_mgr.active()
    if not profile:
        _wl(f"{_C.RED}Brak aktywnego profilu. Ustaw: ai profile use <nazwa>{_C.RESET}")
        return

    prov = profile.get('provider','?')
    mod  = profile.get('model','?')
    _wl(f"{_C.DIM}[{prov} · {mod}] Przetwarzam...{_C.RESET}")

    try:
        reply = send_message(question, use_history=True)
        _wl(f"\n{_C.BGREEN}AI:{_C.RESET}")
        for line in reply.splitlines():
            wrapped = textwrap.fill(line, width=78) if line.strip() else line
            _wl(f"  {wrapped}" if wrapped else "")
        _wl("")
    except Exception as ex:
        _wl(f"{_C.RED}⚠ Błąd: {ex}{_C.RESET}")

# ─── USTAWIENIA ──────────────────────────────────────────────────────────────────

def _cmd_set(args, terminal=None) -> None:
    if len(args) < 2:
        _wl(f"{_C.DIM}Użycie: ai set model <model> | ai set system <tekst>{_C.RESET}")
        return
    field, value = args[0], ' '.join(args[1:])
    name = _profile_mgr.active_name()
    if not name:
        _wl(f"{_C.RED}Brak aktywnego profilu.{_C.RESET}")
        return

    key_map = {'model': 'model', 'system': 'system_prompt', 'url': 'base_url'}
    real_key = key_map.get(field, field)
    if _profile_mgr.set_field(name, real_key, value):
        _wl(f"{_C.BGREEN}✓ Ustawiono {real_key} = {value}{_C.RESET}")
    else:
        _wl(f"{_C.RED}Błąd.{_C.RESET}")

# ─── HISTORIA ────────────────────────────────────────────────────────────────────

def _cmd_history(args, terminal=None) -> None:
    msgs = _history.messages()
    if not msgs:
        _wl(f"{_C.DIM}Historia jest pusta.{_C.RESET}")
        return
    _wl(f"\n{_C.BCYAN}Historia konwersacji ({len(msgs)} wiadomości):{_C.RESET}")
    _wl(f"{_C.BCYAN}{'─'*60}{_C.RESET}")
    for m in msgs:
        role = m.get('role', '?')
        content = m.get('content', '')
        if role == 'user':
            _wl(f"{_C.BYELLOW}You:{_C.RESET} {content[:120]}{'...' if len(content)>120 else ''}")
        else:
            _wl(f"{_C.BGREEN}AI:{_C.RESET} {content[:120]}{'...' if len(content)>120 else ''}")
    _wl(f"{_C.BCYAN}{'─'*60}{_C.RESET}\n")


def _cmd_clear(args, terminal=None) -> None:
    _history.clear()
    _wl(f"{_C.BGREEN}✓ Historia konwersacji wyczyszczona.{_C.RESET}")

# ─── INFO ────────────────────────────────────────────────────────────────────────

def _cmd_info(args, terminal=None) -> None:
    _wl(f"\n{_C.BCYAN}{'═'*60}{_C.RESET}")
    _wl(f"  {_C.BWHITE}CrossTerm AI Module v2.0{_C.RESET}")
    _wl("  Obsługiwani providerzy: Anthropic · OpenAI · Google · OpenAI-Compatible")
    _wl(f"\n{_C.BCYAN}Modele (przykłady):{_C.RESET}")
    for prov, d in PROVIDER_DEFAULTS.items():
        lbl = PROVIDER_LABELS.get(prov, prov)
        mods = ', '.join(d['models'][:3])
        _wl(f"  {lbl:<14} → {_C.DIM}{mods}{_C.RESET}")
    _wl(f"\n{_C.BCYAN}Konfiguracja:{_C.RESET}")
    _wl(f"  Config  : {_C.DIM}{_CONFIG_FILE}{_C.RESET}")
    _wl(f"  AI dir  : {_C.DIM}{_AI_DIR}{_C.RESET}")
    _wl(f"\n{_C.BCYAN}Aktywny profil:{_C.RESET}")
    p = _profile_mgr.active()
    n = _profile_mgr.active_name()
    if p:
        _wl(f"  {_C.BGREEN}{n}{_C.RESET} · {p.get('provider','?')} · {p.get('model','?')}")
    else:
        _wl(f"  {_C.DIM}(brak) — dodaj: ai profile add{_C.RESET}")
    _wl(f"{_C.BCYAN}{'═'*60}{_C.RESET}\n")

# ─── MENU ────────────────────────────────────────────────────────────────────────

def cml_menu():
    _cmd_ai_menu([], None)

def _cmd_ai_menu(args, terminal=None) -> None:
    import re as _re
    _ANSI = _re.compile(r'\x1b\[[0-9;]*[mA-Z]')
    def _vis(s): return len(_ANSI.sub('', s))

    # Szerokość wewnętrzna ramki (widoczne znaki między ║ a ║)
    _W = 82

    def _hline(l, r): return f"{_C.BCYAN}{l}{'─' * _W}{r}{_C.RESET}"

    def _row(content: str) -> None:
        """Wiersz ramki: ║ content <padding> ║ — prawa sciana zawsze w kolumnie _W+2."""
        pad = max(0, _W - _vis(content))
        _wl(f"{_C.BCYAN}│{_C.RESET}{content}{' ' * pad}{_C.BCYAN}│{_C.RESET}")

    def _cmd_row(cmd: str, desc: str) -> None:
        CMD_W = 28
        inner = f"  {_C.BYELLOW}{cmd:<{CMD_W}}{_C.RESET}  {_C.DIM}{desc}{_C.RESET}"
        _row(inner)

    def _section(title: str) -> None:
        _wl(_hline('├', '┤'))
        inner = f"  {_C.BOLD}{_C.BCYAN}{title}{_C.RESET}"
        _row(inner)

    active  = _profile_mgr.active_name()
    p       = _profile_mgr.active()
    act_str = (f"{_C.BGREEN}{active}{_C.RESET} · {p.get('provider','?')}/{p.get('model','?')}"               if p else f"{_C.RED}(brak aktywnego profilu){_C.RESET}")

    _wl('')
    _wl(_hline('╭', '╮'))
    _row(f"  {_C.BOLD}CrossTerm AI{_C.RESET}  {_C.DIM}v2.1{_C.RESET}")
    _row(f"  Profil: {act_str}")

    _section("CZAT / PYTANIA")
    _cmd_row("ai ask <pytanie>",          "Szybkie pytanie → odpowiedź w terminalu")
    _cmd_row("ai chat",                   "Otwórz okno GUI chat (nie blokuje terminala)")
    _cmd_row("ai inline",                 "Tryb chat inline w terminalu")

    _section("PROFILE")
    _cmd_row("ai profile preset",         "Lista 30+ gotowych presetów modeli")
    _cmd_row("ai profile preset <klucz>", "Zainstaluj gotowy preset (pyta tylko o API key)")
    _cmd_row("ai profile add",            "Dodaj własny profil ręcznie (kreator)")
    _cmd_row("ai profile list",           "Lista zapisanych profili")
    _cmd_row("ai profile use <n>",        "Aktywuj profil")
    _cmd_row("ai profile del <n>",        "Usuń profil")
    _cmd_row("ai profile show <n>",       "Pokaż szczegóły profilu")

    _section("USTAWIENIA")
    _cmd_row("ai set model <m>",          "Zmień model aktywnego profilu")
    _cmd_row("ai set system <tekst>",     "Ustaw system prompt")

    _section("HISTORIA")
    _cmd_row("ai history",                "Pokaż historię konwersacji")
    _cmd_row("ai clear",                  "Wyczyść historię")

    _section("KLUCZE API")
    _cmd_row("ai keys",                   "Status kluczy w pamięci")
    _cmd_row("ai keys generate",          "Wygeneruj plik key/api_keys.ini")
    _cmd_row("ai keys load",              "Wczytaj klucze z pliku")
    _cmd_row("ai keys clear [provider]",  "Wyczyść klucze z pamięci")
    _cmd_row("ai info",                   "Szczegóły providerów i konfiguracji")

    _wl(_hline('╰', '╯'))
    _wl('')

# ─── DISPATCHER ─────────────────────────────────────────────────────────────────

def _dispatch(args, terminal=None) -> None:
    sub  = args[0].lower() if args else ''
    rest = args[1:]

    routing = {
        'ask':     _cmd_ask,
        'chat':    _open_gui,
        'gui':     _open_gui,
        'inline':  _inline_chat,
        'profile': _cmd_profile,
        'profiles':_cmd_profile,
        'preset':  _cmd_profile_preset,
        'presets': _cmd_profile_preset,
        'set':     _cmd_set,
        'history': _cmd_history,
        'clear':   _cmd_clear,
        'info':    _cmd_info,
        'keys':    _cmd_keys,
        'help':    _cmd_ai_menu,
        # aliasy providerów → skrót do ask
        'claude':  _cmd_ask,
        'gpt':     _cmd_ask,
        'gemini':  _cmd_ask,
    }

    if not sub:
        _cmd_ai_menu([], terminal)
        return

    fn = routing.get(sub)
    if fn:
        fn(rest, terminal)
    else:
        # Brak podkomendy → traktuj jako pytanie
        _cmd_ask(args, terminal)

# ─── CML COMMANDS ────────────────────────────────────────────────────────────────

def cmd_ai(args, terminal=None):
    _dispatch(args, terminal)

def cmd_chat(args, terminal=None):
    _open_gui(args, terminal)

def cmd_gpt(args, terminal=None):
    _cmd_ask(args, terminal)

def cmd_claude(args, terminal=None):
    _cmd_ask(args, terminal)

def cmd_gemini(args, terminal=None):
    _cmd_ask(args, terminal)

CML_COMMANDS = {
    # Główny wpis modułu
    "ai":                    cmd_ai,
    # Aliasy dla wygody
    "chat":                  cmd_chat,
    "gpt":                   cmd_gpt,
    "claude":                cmd_claude,
    "gemini":                cmd_gemini,
    # Podkomendy bezpośrednie
    "ai.ask":                lambda a, t: _cmd_ask(a, t),
    "ai.chat":               lambda a, t: _open_gui(a, t),
    "ai.gui":                lambda a, t: _open_gui(a, t),
    "ai.inline":             lambda a, t: _inline_chat(a, t),
    "ai.profile":            lambda a, t: _cmd_profile(a, t),
    "ai.profile.add":        lambda a, t: _cmd_profile_add(a, t),
    "ai.profile.list":       lambda a, t: _cmd_profile_list(a, t),
    "ai.profile.use":        lambda a, t: _cmd_profile_use(a, t),
    "ai.profile.del":        lambda a, t: _cmd_profile_del(a, t),
    "ai.profile.show":       lambda a, t: _cmd_profile_show(a, t),
    "ai.profile.preset":     lambda a, t: _cmd_profile_preset(a, t),
    "ai.preset":             lambda a, t: _cmd_profile_preset(a, t),
    "ai.keys":               lambda a, t: _cmd_keys(a, t),
    "ai.history":            lambda a, t: _cmd_history(a, t),
    "ai.clear":              lambda a, t: _cmd_clear(a, t),
    "ai.info":               lambda a, t: _cmd_info(a, t),
}

# ─── ON LOAD ─────────────────────────────────────────────────────────────────────

def on_load():
    global _loaded_api_keys
    _ensure_dirs()
    _history.load()
    # Auto-wczytaj klucze z pliku key/api_keys.ini (cicho przy starcie)
    if _KEYS_FILE.exists():
        _loaded_api_keys = _load_keys_from_file()

# ─── EcoSystem modules integration ───────────────────────────────────────────

MODULE_CMD            = "ai"
MODULE_DESCRIPTION    = "Asystent AI — 30+ modeli, gotowe presety, GUI chat"
MODULE_DESCRIPTION_EN = "AI Assistant — 30+ models, ready presets, GUI chat"
MODULE_VERSION        = "2.1"


def setup(terminal):
    """Rejestruje komendy AI w TerminalX EcoSystem."""
    from . import _integration

    cat = terminal.t("cat_ecosystem")

    def _ai(args):      cmd_ai(args, terminal)
    def _chat(args):    cmd_chat(args, terminal)
    def _gpt(args):     cmd_gpt(args, terminal)
    def _claude(args):  cmd_claude(args, terminal)
    def _gemini(args):  cmd_gemini(args, terminal)

    terminal.register_command(
        "ai", _ai,
        description=terminal.t("cmd_ai"),
        category=cat,
    )
    terminal.register_command(
        "chat", _chat,
        description=terminal.t("cmd_ai_chat"),
        category=cat,
    )
    terminal.register_command(
        "gpt", _gpt,
        description=terminal.t("cmd_ai_gpt"),
        category=cat,
    )
    terminal.register_command(
        "claude", _claude,
        description=terminal.t("cmd_ai_claude"),
        category=cat,
    )
    terminal.register_command(
        "gemini", _gemini,
        description=terminal.t("cmd_ai_gemini"),
        category=cat,
    )

    on_load()

    # Rejestracja publicznego API w rejestrze integracyjnym EcoSystem
    _integration.register("ai", {
        # Wysyłanie wiadomości do aktywnego modelu
        "send_message":     send_message,
        # Pobranie aktywnego profilu (dict) lub None
        "active_profile":   _profile_mgr.active,
        # Pobranie nazwy aktywnego profilu lub None
        "active_name":      _profile_mgr.active_name,
        # Sprawdzenie czy profil jest gotowy do użycia
        "is_ready":         lambda: _profile_mgr.active() is not None,
        # Dostęp do historii konwersacji
        "history_messages": _history.messages,
        "history_clear":    _history.clear,
        # Zarządzanie profilami
        "profile_list":     _profile_mgr.list_profiles,
        "profile_use":      _profile_mgr.use,
        "profile_add":      _profile_mgr.add,
        # Metadane modułu
        "version":          MODULE_VERSION,
        "description":      MODULE_DESCRIPTION_EN,
    })


def teardown(terminal):
    """Wyrejestrowuje komendy AI z TerminalX EcoSystem."""
    from . import _integration
    _integration.unregister("ai")
    for cmd in ("ai", "chat", "gpt", "claude", "gemini"):
        terminal.commands.pop(cmd, None)
