"""Language module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski
Module: lang  v1.2.0

Przelaczanie jezyka interfejsu i wyswietlanie dostepnych jezykow.
Zmiana jezyka jest natychmiastowa (hot-reload) - restart nie jest wymagany.

Komendy:
  lang           - pokaz aktualny jezyk + liste dostepnych
  lang en        - przelacz na angielski
  lang pl        - przelacz na polski
"""

import os
import json

from ._shared import CACHE_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, WHT, _w

_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# Lista dostepnych jezykow EcoSystem
# ---------------------------------------------------------------------------

_AVAILABLE_LANGS: dict[str, str] = {
    "en": "English",
    "pl": "Polski",
}

_LANG_JSON = os.path.join(CACHE_DIR, "global", "lang.json")


def _load_lang_pref() -> str | None:
    """Wczytaj zachowany jezyk z .cache/global/lang.json."""
    try:
        with open(_LANG_JSON, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("lang")
    except Exception:
        return None


# Alias publiczny - importowany przez core/__init__.py
load_saved_lang = _load_lang_pref


def _save_lang_pref(code: str) -> None:
    """Zapisz jezyk do .cache/global/lang.json."""
    try:
        os.makedirs(os.path.dirname(_LANG_JSON), exist_ok=True)
        with open(_LANG_JSON, "w", encoding="utf-8") as f:
            json.dump({"lang": code}, f)
    except Exception:
        pass


def _show_lang_status(terminal) -> None:
    """Wyswietl aktualny jezyk + table dostepnych jezykow EcoSystem."""
    current = terminal.lang.lower()

    _w(f"\n  {BOLD}{CYN}{terminal.t('lang_current', lang=current.upper())}{RST}\n\n")
    _w(f"  {DIM}{terminal.t('lang_available_header')}{RST}\n\n")

    for code, name in sorted(_AVAILABLE_LANGS.items()):
        is_active = (code == current)
        status    = (
            f"{GRN}{terminal.t('lang_available_active')}{RST}"
            if is_active
            else f"{DIM}-{RST}"
        )
        code_col = f"{YLW}{BOLD}{code.upper()}{RST}" if is_active else f"{WHT}{code.upper()}{RST}"
        name_col = f"{BOLD}{name}{RST}"              if is_active else f"{DIM}{name}{RST}"
        _w(f"    {code_col:<20}  {name_col:<30}  {status}\n")

    _w(f"\n  {DIM}{terminal.t('lang_available_hint')}{RST}\n\n")


# ---------------------------------------------------------------------------
# Hot-reload modułów po zmianie języka
# ---------------------------------------------------------------------------

def _reload_all_modules(terminal) -> None:
    """Wywołaj teardown + setup dla wszystkich załadowanych modułów.

    Dzięki temu opisy i kategorie komend są przetłumaczone na nowo
    wybrany język bez konieczności restartu terminala.
    """
    import importlib

    loaded = getattr(terminal, "loaded_modules", {})
    # Kolejność: najpierw teardown wszystkich, potem setup wszystkich.
    # Dzięki temu zależności między modułami pozostają spójne.
    for name, module in list(loaded.items()):
        if hasattr(module, "teardown"):
            try:
                module.teardown(terminal)
            except Exception:
                pass

    for name, module in list(loaded.items()):
        if hasattr(module, "setup"):
            try:
                importlib.reload(module)
                module.setup(terminal)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# setup / teardown
# ---------------------------------------------------------------------------

def setup(terminal) -> None:


    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("lang", {
            "current": lambda: getattr(terminal, "lang", "en"),
        })
    except Exception:
        pass
    def lang_cmd(args: list) -> None:
        if not args:
            _show_lang_status(terminal)
            return

        code = args[0].lower()

        if code not in _AVAILABLE_LANGS:
            _w(f"\n  {RED}{terminal.t('lang_unknown', lang=args[0])}{RST}\n\n")
            return

        if code == terminal.lang.lower():
            _w(f"\n  {DIM}{terminal.t('lang_current', lang=code.upper())}{RST}\n\n")
            return

        terminal.lang = code
        _save_lang_pref(code)

        # Przeladuj slownik tlumaczen po zmianie jezyka
        try:
            import importlib
            mod = importlib.import_module(f"lang.{code}")
            importlib.reload(mod)
            terminal._t = mod.T
        except Exception:
            pass

        # Hot-reload wszystkich modulow aby odswiezec opisy komend
        # (teardown -> setup dla kazdego zaladowanego modulu)
        _reload_all_modules(terminal)

        _w(f"\n  {GRN}{terminal.t('lang_set', lang=code.upper())}{RST}\n\n")

    terminal.register_command(
        "lang", lang_cmd,
        description=terminal.t("cmd_lang"),
        category=terminal.t("cat_ecosystem"),
    )

    # Przywroc jezyk z poprzedniej sesji (jesli cache istnieje)
    saved = _load_lang_pref()
    if saved and saved in _AVAILABLE_LANGS and saved != terminal.lang.lower():
        terminal.lang = saved


def teardown(terminal) -> None:
    try:
        from . import _integration as _intg
        _intg.unregister("lang")
    except Exception:
        pass
    terminal.commands.pop("lang", None)
