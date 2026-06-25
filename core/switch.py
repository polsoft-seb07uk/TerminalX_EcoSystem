"""Switch module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski

Przełączanie między trybem CLI (TerminalX.py) a GUI (gui/app.py)
bez utraty sesji — GUI uruchamiane jako osobny subprocess, CLI może
się samo zamknąć lub pozostać w tle (tryb `detach`).

Komendy
-------
  switch gui            - uruchom GUI (ten terminal zostaje w tle)
  switch gui --close    - uruchom GUI i zamknij CLI
  switch cli            - (z GUI) otwórz nowe okno CLI obok GUI
  switch status         - pokaż aktualny tryb i procesy GUI
  switch kill           - zakończ wszystkie uruchomione przez nas GUI

Architektura
------------
  * GUI jest uruchamiane jako subprocess.Popen (nieblokowny).
  * Lista PID-ów GUI jest przechowywana w terminal._switch_gui_pids
    i czyszczona ze zmarłych procesów przy każdym wywołaniu.
  * Moduł wykrywa czy sam działa wewnątrz GUI (zmienna środowiskowa
    TERMINALX_GUI=1 ustawiana przez gui/app.py przy starcie) i wtedy
    `switch cli` otwiera nowe okno terminala z TerminalX.py.
  * Nie wymaga żadnych zewnętrznych zależności ponad stdlib.

Author  : Sebastian Januchowski
Brand   : polsoft.ITS(TM) Group
Version : 1.0.0
"""

from __future__ import annotations

import os
import sys
import subprocess
import threading
from typing import Optional

from ._shared import (
    ROOT_DIR, IS_WIN, IS_LIN, IS_MAC, RST, BOLD, DIM, YLW, RED, GRN, CYN, MGT, _w, _pad
)

_VERSION  = "1.0.0"

# Zmienna środowiskowa ustawiana przez gui/app.py – pozwala modułowi
# wykryć w jakim trybie jest aktualnie uruchomiony TerminalX.
_GUI_ENV_KEY = "TERMINALX_GUI"

# ---------------------------------------------------------------------------
# Ścieżki
# ---------------------------------------------------------------------------

def _gui_script() -> str:
    """Pełna ścieżka do gui/app.py."""
    return os.path.join(ROOT_DIR, "gui", "app.py")


def _cli_script() -> str:
    """Pełna ścieżka do TerminalX.py (główny bootstrapper)."""
    return os.path.join(ROOT_DIR, "TerminalX.py")


# ---------------------------------------------------------------------------
# Detekcja trybu
# ---------------------------------------------------------------------------

def _running_in_gui() -> bool:
    """Zwraca True jeśli jesteśmy wewnątrz procesu GUI (gui/app.py)."""
    return os.environ.get(_GUI_ENV_KEY, "") == "1"


# ---------------------------------------------------------------------------
# Uruchamianie subprocess
# ---------------------------------------------------------------------------

def _open_terminal_with_cli() -> Optional[subprocess.Popen]:
    """Otwórz nowe okno terminala systemowego z CLI TerminalX.

    Strategia platformowa:
      Windows  – `start` cmd z python TerminalX.py w nowym oknie
      macOS    – AppleScript otwierający Terminal.app
      Linux    – próba xterm / gnome-terminal / konsole / xfce4-terminal
    """
    script = _cli_script()
    py     = sys.executable

    try:
        if IS_WIN:
            # `start` + `cmd /k` żeby okno zostało po zakończeniu
            proc = subprocess.Popen(
                ["cmd", "/c", "start", "cmd", "/k",
                 py, script],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        elif IS_MAC:
            apple_script = (
                f'tell application "Terminal" to do script '
                f'"{py} {script}"'
            )
            proc = subprocess.Popen(
                ["osascript", "-e", apple_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # Linux – próba popularnych emulatorów terminala
            emulators = [
                ["x-terminal-emulator", "-e"],
                ["xterm", "-e"],
                ["gnome-terminal", "--"],
                ["konsole", "-e"],
                ["xfce4-terminal", "-e"],
                ["lxterminal", "-e"],
                ["urxvt", "-e"],
            ]
            import shutil
            for emu_cmd in emulators:
                if shutil.which(emu_cmd[0]):
                    proc = subprocess.Popen(
                        emu_cmd + [py, script],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return proc
            # Fallback: uruchom w tle bez nowego okna
            proc = subprocess.Popen(
                [py, script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return proc
    except Exception as exc:
        _w(f"  {RED}[switch] Nie można otworzyć terminala: {exc}{RST}\n")
        return None


def _launch_gui() -> Optional[subprocess.Popen]:
    """Uruchom GUI jako nieblokowny subprocess.

    Ustawia TERMINALX_GUI=1 w środowisku GUI żeby inne moduły
    (np. switch cli uruchamiane z GUI) wiedziały gdzie są.
    """
    script = _gui_script()
    if not os.path.isfile(script):
        _w(f"  {RED}[switch] Brak pliku: {script}{RST}\n")
        return None

    env = os.environ.copy()
    env[_GUI_ENV_KEY] = "1"

    try:
        kwargs: dict = dict(
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if IS_WIN:
            # Nowy proces odłączony od aktualnej konsoli
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
            )
        else:
            kwargs["start_new_session"] = True

        proc = subprocess.Popen(
            [sys.executable, script],
            **kwargs,
        )
        return proc
    except Exception as exc:
        _w(f"  {RED}[switch] Nie można uruchomić GUI: {exc}{RST}\n")
        return None


# ---------------------------------------------------------------------------
# Zarządzanie listą procesów GUI
# ---------------------------------------------------------------------------

def _prune_dead(pids: list) -> list:
    """Usuń z listy procesy, które już zakończyły działanie."""
    alive = []
    for proc in pids:
        try:
            if proc.poll() is None:
                alive.append(proc)
        except Exception:
            pass
    return alive


# ---------------------------------------------------------------------------
# Sub-komendy
# ---------------------------------------------------------------------------

def _cmd_gui(terminal, _t, close_cli: bool) -> None:
    """Uruchom GUI; opcjonalnie zamknij CLI."""
    if _running_in_gui():
        _w(f"  {YLW}[switch] Już działasz wewnątrz GUI.{RST}\n")
        _w(f"  {DIM}Użyj 'switch cli' żeby otworzyć nowe okno CLI.{RST}\n\n")
        return

    _w(f"\n  {BOLD}{CYN}[switch]{RST} Uruchamianie GUI…\n")

    proc = _launch_gui()
    if proc is None:
        return

    # Zachowaj referencję do procesu
    pids: list = getattr(terminal, "_switch_gui_pids", [])
    pids = _prune_dead(pids)
    pids.append(proc)
    terminal._switch_gui_pids = pids

    _w(f"  {GRN}[V]{RST}  GUI uruchomione  {DIM}(PID {proc.pid}){RST}\n")
    _w(f"  {DIM}Procesy GUI aktywne: {len(pids)}{RST}\n\n")

    if close_cli:
        _w(f"  {YLW}[switch]{RST} Zamykanie CLI…\n\n")
        # Krótkie opóźnienie żeby GUI zdążyło się zainicjalizować
        def _delayed_exit():
            import time
            time.sleep(0.8)
            raise SystemExit(0)

        t = threading.Thread(target=_delayed_exit, daemon=True,
                             name="switch-close-cli")
        t.start()


def _cmd_cli(terminal, _t) -> None:
    """Otwórz nowe okno CLI (przydatne gdy działamy wewnątrz GUI lub chcemy CLI obok)."""
    _w(f"\n  {BOLD}{CYN}[switch]{RST} Otwieranie nowego okna CLI…\n")

    proc = _open_terminal_with_cli()
    if proc is None:
        return

    # Przechowaj PID żeby można było go zbić przez 'switch kill'
    pids: list = getattr(terminal, "_switch_gui_pids", [])
    pids = _prune_dead(pids)
    pids.append(proc)
    terminal._switch_gui_pids = pids

    _w(f"  {GRN}[V]{RST}  Nowe okno CLI otwarte  "
       f"{DIM}(PID {proc.pid}){RST}\n\n")

    if _running_in_gui():
        _w(f"  {DIM}Ten GUI pozostaje otwarty.{RST}\n\n")


def _cmd_status(terminal, _t) -> None:
    """Pokaż aktualny tryb i stan uruchomionych procesów."""
    mode = f"{MGT}GUI{RST}" if _running_in_gui() else f"{CYN}CLI{RST}"
    _w(f"\n  {BOLD}switch{RST}  v{_VERSION}  —  tryb: {BOLD}{mode}{RST}\n\n")

    pids: list = getattr(terminal, "_switch_gui_pids", [])
    pids = _prune_dead(pids)
    terminal._switch_gui_pids = pids

    if not pids:
        _w(f"  {DIM}Brak uruchomionych procesów (GUI/CLI) przez ten moduł.{RST}\n\n")
        return

    _w(f"  {DIM}{'PID':<10} {'STATUS':<12} {'SKRYPT'}{RST}\n")
    _w(f"  {DIM}{'-'*10} {'-'*12} {'-'*30}{RST}\n")
    for proc in pids:
        alive = proc.poll() is None
        status_str = f"{GRN}działa{RST}" if alive else f"{RED}zakończony{RST}"
        # Spróbuj ustalić co to za skrypt
        try:
            args = proc.args if isinstance(proc.args, list) else [str(proc.args)]
            label = os.path.basename(args[-1]) if args else "?"
        except Exception:
            label = "?"
        _w(f"  {YLW}{str(proc.pid):<10}{RST} {status_str:<12}  {DIM}{label}{RST}\n")

    _w("\n")


def _cmd_kill(terminal, _t) -> None:
    """Zakończ wszystkie uruchomione przez nas GUI/CLI."""
    pids: list = getattr(terminal, "_switch_gui_pids", [])
    if not pids:
        _w(f"  {DIM}Brak procesów do zatrzymania.{RST}\n")
        return

    killed = 0
    for proc in pids:
        if proc.poll() is None:
            try:
                proc.terminate()
                killed += 1
            except Exception as exc:
                _w(f"  {RED}[switch] kill PID {proc.pid}: {exc}{RST}\n")

    terminal._switch_gui_pids = []
    _w(f"  {GRN}[V]{RST}  Zatrzymano {killed} proces(y).{RST}\n\n")


def _show_help(_t) -> None:
    _w(f"\n  {BOLD}{CYN}switch{RST}  v{_VERSION}  "
       f"— przełącznik CLI ↔ GUI\n\n")
    rows = [
        ("switch gui",          _t("switch_help_gui")),
        ("switch gui --close",  _t("switch_help_gui_close")),
        ("switch cli",          _t("switch_help_cli")),
        ("switch status",       _t("switch_help_status")),
        ("switch kill",         _t("switch_help_kill")),
    ]
    for cmd, desc in rows:
        _w(f"  {YLW}{_pad(cmd, 24)}{RST} {desc}\n")

    mode = f"{MGT}GUI{RST}" if _running_in_gui() else f"{CYN}CLI{RST}"
    _w(f"\n  {DIM}Aktualny tryb: {RST}{BOLD}{mode}{RST}\n\n")


# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------

def setup(terminal) -> None:
    _t = terminal.t

    # Rejestr PID-ów uruchomionych procesów (GUI lub CLI)
    if not hasattr(terminal, "_switch_gui_pids"):
        terminal._switch_gui_pids = []

    def switch_command(args: list[str]) -> None:
        if not args:
            _show_help(_t)
            return

        sub  = args[0].lower()
        rest = args[1:]

        if sub == "gui":
            close = "--close" in rest or "-c" in rest
            _cmd_gui(terminal, _t, close_cli=close)

        elif sub == "cli":
            _cmd_cli(terminal, _t)

        elif sub == "status":
            _cmd_status(terminal, _t)

        elif sub == "kill":
            _cmd_kill(terminal, _t)

        else:
            _w(f"  {RED}[switch]{RST} Nieznana podkomenda: {sub}\n")
            _show_help(_t)

    terminal.register_command(
        "switch", switch_command,
        description=_t("cmd_switch"),
        category=_t("cat_ecosystem"),
    )

    # Zarejestruj w _integration – inne moduły mogą sprawdzić tryb
    try:
        from . import _integration as _intg
        _intg.register("switch", {
            "running_in_gui": _running_in_gui,
            "launch_gui":     _launch_gui,
        })
    except Exception:
        pass


def teardown(terminal) -> None:
    try:
        from . import _integration as _intg
        _intg.unregister("switch")
    except Exception:
        pass
    terminal.commands.pop("switch", None)
