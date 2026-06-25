"""Module menu for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski

Komenda '??' - drugie 'help' dla modulow uzytkownika z folderu /modules.
Wyswietla po jednej linii na modul (glowna komenda + opis), identycznie
jak 'help' wyswietla komendy kategorii EcoSystem.

Po wpisaniu komendy modulu (np. 'venv') bez argumentow modul sam
wyswietla swoje rozbudowane menu/pomoc.

Metadane odczytywane z modulu (opcjonalne atrybuty na poziomie pliku):
  MODULE_CMD         - glowna komenda (str); jesli brak - nazwa pliku bez .py
  MODULE_DESCRIPTION - opis jednolinijkowy (str)
  MODULE_VERSION     - wersja (str)

Przyklad modulu /modules/hello.py:
  MODULE_CMD         = "hello"
  MODULE_DESCRIPTION = "Przykladowy modul powitania"
  MODULE_VERSION     = "1.0.0"

  def setup(terminal):
      terminal.register_command("hello", ..., category=terminal.t("cat_modules"))
"""

import importlib.util
import os

from ._shared import ROOT_DIR, RST, BOLD, DIM, YLW, CYN, BCYN, _w, _pad

_MODULES_DIR = os.path.join(ROOT_DIR, "modules")


def _scan_modules() -> list[dict]:
    """Zbierz metadane (MODULE_CMD / MODULE_DESCRIPTION / MODULE_VERSION)
    z kazdego *.py w /modules bez uruchamiania setup()."""
    results = []
    if not os.path.isdir(_MODULES_DIR):
        return results

    for fname in sorted(os.listdir(_MODULES_DIR)):
        if fname.startswith("_"):
            continue

        if fname.endswith(".py"):
            mod_name = fname[:-3]
            mod_path = os.path.join(_MODULES_DIR, fname)
        elif os.path.isdir(os.path.join(_MODULES_DIR, fname)):
            init_path = os.path.join(_MODULES_DIR, fname, "__init__.py")
            if not os.path.isfile(init_path):
                continue
            mod_name = fname
            mod_path = init_path
        else:
            continue
        meta = {
            "cmd":            mod_name,   # fallback
            "description":    "",
            "description_en": "",
            "version":        "",
            "error":          None,
        }

        try:
            spec = importlib.util.spec_from_file_location(
                f"_modmenu_scan_{mod_name}", mod_path
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            meta["cmd"]            = getattr(mod, "MODULE_CMD",            mod_name)
            meta["description"]    = getattr(mod, "MODULE_DESCRIPTION",    "")
            meta["description_en"] = getattr(mod, "MODULE_DESCRIPTION_EN", "")
            meta["version"]        = getattr(mod, "MODULE_VERSION",        "")
        except Exception as exc:
            meta["error"] = str(exc)

        results.append(meta)

    return results


def setup(terminal):
    def _t(key, **kw):
        return terminal.t(key, **kw)

    def modmenu_command(args):
        modules = _scan_modules()

        _w(f"\n{BOLD}{BCYN}  {_t('modmenu_title')}{RST}\n\n")

        if not modules:
            _w(f"  {DIM}{_t('modmenu_empty')}{RST}\n\n")
            return

        # Naglowek kategorii - identyczny styl jak help.py
        hint = _t("modmenu_hint")
        _w(f"  {BOLD}{CYN}{'MODULES'}{RST}  {DIM}{hint}{RST}\n")

        for meta in modules:
            if meta["error"]:
                _w(f"    {YLW}{_pad(meta['cmd'], 14)}{RST}  "
                   f"\x1b[31m{_t('modmenu_load_error', err=meta['error'])}{RST}\n")
                continue

            ver_str = f" {DIM}v{meta['version']}{RST}" if meta["version"] else ""
            lang    = getattr(terminal, "lang", "en").lower()
            desc    = (meta["description_en"] or meta["description"]) \
                      if lang == "en" else meta["description"]
            _w(f"    {YLW}{_pad(meta['cmd'], 14)}{RST}  {DIM}{desc}{RST}{ver_str}\n")

        n = len(modules)
        _w(f"\n  {DIM}{_t('modmenu_total', n=n)}{RST}\n\n")

    terminal.register_command(
        "??", modmenu_command,
        description=_t("cmd_modmenu"),
        category=_t("cat_general"),
    )


def teardown(terminal):
    terminal.commands.pop("??", None)
