"""Trash system module for TerminalX."""

import os
import shutil
from datetime import datetime

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad
from . import _integration


def ensure_trash():
    """Ensure trash directory exists."""
    if not os.path.exists(TRASH_DIR):
        os.makedirs(TRASH_DIR, exist_ok=True)


def move_to_trash(path: str) -> bool:
    """Przenieś plik/katalog do .trash/. Zwraca True przy sukcesie.

    Publiczna funkcja używana przez inne moduły przez _integration.
    Obsługuje kolizje nazw (dopisuje ~timestamp), nie rzuca wyjątków.
    """
    ensure_trash()
    if not os.path.exists(path):
        return False
    name = os.path.basename(path)
    dst  = os.path.join(TRASH_DIR, name)
    if os.path.exists(dst):
        base, ext = os.path.splitext(name)
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(TRASH_DIR, f"{base}~{ts}{ext}")
    try:
        shutil.move(path, dst)
        return True
    except Exception:
        return False


def list_trash() -> list:
    """Zwróć listę wpisów w .trash/ jako [{name, path, size, is_dir}]."""
    ensure_trash()
    out = []
    for entry in sorted(os.listdir(TRASH_DIR)):
        full   = os.path.join(TRASH_DIR, entry)
        is_dir = os.path.isdir(full)
        size   = 0 if is_dir else os.path.getsize(full)
        out.append({"name": entry, "path": full, "size": size, "is_dir": is_dir})
    return out


def setup(terminal):
    ensure_trash()

    # Rejestracja w _integration - inne moduly moga korzystac z trash
    # bez bezposredniego importu (np. docs.py -> _move_to_trash)
    try:
        _integration.register("trash", {
            "ensure_trash":  ensure_trash,
            "move_to_trash": move_to_trash,
            "list_trash":    list_trash,
        })
    except Exception:
        pass

    def _t(key, **kw):
        return terminal.t(key, **kw)

    def trash_menu(args):
        """Show trash menu."""

        _w(f"\n{BOLD}{BCYN}  ╭──────────────────────────────────────╮{RST}\n")
        _w(f"{BOLD}{BCYN}  │   🗑  {_t('trash_module_title')}           │{RST}\n")
        _w(f"{BOLD}{BCYN}  ╰──────────────────────────────────────╯{RST}\n\n")

        cmds = [
            ("bin",                  _t("trash_cmd_bin")),
            ("trash restore <name>", _t("trash_cmd_restore")),
            ("trash restore all",    _t("trash_cmd_restore_all")),
            ("trash empty",          _t("trash_cmd_empty")),
            ("trash remove <name>",  _t("trash_cmd_remove")),
        ]
        for c, d in cmds:
            _w(f"  {YLW}{_pad(c, 28)}{RST} {DIM}{d}{RST}\n")
        _w("\n")

    def bin_command(args):
        """Show trash contents."""
        ensure_trash()
        entries = os.listdir(TRASH_DIR)
        if not entries:
            print(_t("trash_empty_msg"))
            return

        print()
        print(_t("trash_contents"))
        for entry in sorted(entries):
            full_path = os.path.join(TRASH_DIR, entry)
            if os.path.isdir(full_path):
                print(f"  [DIR]  {entry}")
            else:
                size = os.path.getsize(full_path)
                print(f"  [FILE] {entry} ({size} B)")
        print()

    def trash_wrapper(args):
        """Handle trash subcommands."""
        if not args:
            trash_menu([])
            return

        subcmd = args[0]
        subargs = args[1:] if len(args) > 1 else []

        if subcmd == "restore":
            trash_restore(subargs)
        elif subcmd == "empty":
            trash_empty(subargs)
        elif subcmd == "remove":
            trash_remove(subargs)
        else:
            print(_t("trash_unknown_sub", sub=subcmd))

    def trash_restore(args):
        """Restore file or all files."""
        ensure_trash()
        if not args:
            print(_t("trash_restore_usage"))
            return

        if args[0] == "all":
            entries = os.listdir(TRASH_DIR)
            if not entries:
                print(_t("trash_empty_msg"))
                return
            for entry in entries:
                src = os.path.join(TRASH_DIR, entry)
                dst = os.path.join(os.getcwd(), entry)
                try:
                    shutil.move(src, dst)
                    print(_t("trash_restored", name=entry))
                except Exception as exc:
                    print(_t("trash_restore_error", name=entry, exc=exc))
        else:
            name = args[0]
            src = os.path.join(TRASH_DIR, name)
            if not os.path.exists(src):
                print(_t("trash_not_found", name=name))
                return
            dst = os.path.join(os.getcwd(), name)
            try:
                shutil.move(src, dst)
                print(_t("trash_restored", name=name))
            except Exception as exc:
                print(_t("trash_restore_error", name=name, exc=exc))

    def trash_empty(args):
        """Empty trash."""
        ensure_trash()
        try:
            shutil.rmtree(TRASH_DIR)
            os.makedirs(TRASH_DIR, exist_ok=True)
            print(_t("trash_emptied"))
            _integration.notify_event(
                terminal, _t("trash_emptied"), kind="ok", title="TRASH",
            )
        except Exception as exc:
            print(_t("trash_empty_error", exc=exc))
            _integration.notify_event(
                terminal, f"{_t('trash_empty_error', exc=exc)}", kind="err", title="TRASH",
            )

    def trash_remove(args):
        """Permanently remove file from trash."""
        if not args:
            print(_t("trash_remove_usage"))
            return

        name = args[0]
        path = os.path.join(TRASH_DIR, name)
        if not os.path.exists(path):
            print(_t("trash_not_found", name=name))
            return

        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            print(_t("trash_removed", name=name))
        except Exception as exc:
            print(_t("trash_remove_error", exc=exc))

    terminal.register_command("trash", trash_wrapper, description=_t("cmd_trash"), category=_t("cat_ecosystem"))
    terminal.register_command("bin",   bin_command,   description=_t("cmd_bin"),   category=_t("cat_ecosystem"))


def teardown(terminal):
    terminal.commands.pop("trash", None)
    terminal.commands.pop("bin", None)
    try:
        _integration.unregister("trash")
    except Exception:
        pass
