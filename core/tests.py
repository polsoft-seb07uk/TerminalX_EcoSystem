"""Tests module for TerminalX - EcoSystem.

Uruchamia testy jednostkowe z poziomu terminala.
Wyniki wyswietlane sa z kolorowymi wskaznikami PASS / FAIL.

Author  : Sebastian Januchowski
Brand   : polsoft.ITS(TM)
Version : 1.0.0
"""

# ============================================================================
#  MODULE METADATA
# ============================================================================

from ._shared import ROOT_DIR, CACHE_DIR, TRASH_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, BCYN, MGT, BLU, WHT, _w, _strip, _pad
METADATA = {
    "name"       : "tests",
    "version"    : "1.0.0",
    "author"     : "Sebastian Januchowski",
    "company"    : "polsoft.ITS(TM) Group",
    "description": "Runner testow jednostkowych EcoSystem",
    "type"       : "tool",
    "depends"    : [],
    "exports"    : [],
    "min_pyterm" : "2.0.0",
}

import os
import sys
import re
import subprocess
import importlib


TESTS_DIR = os.path.join(ROOT_DIR, "tests")


def setup(terminal):

    def _t(key, **kw):
        return terminal.t(key, **kw)

    # -------------------------------------------------------------------------
    #  Pomocnicze - zbieranie plikow testowych
    # -------------------------------------------------------------------------

    def _collect_test_files(subdir: str = "") -> list:
        """Zwraca liste plikow test_*.py w katalogu tests/ (lub podkatalogu)."""
        base = os.path.join(TESTS_DIR, subdir) if subdir else TESTS_DIR
        if not os.path.isdir(base):
            return []
        result = []
        for fname in sorted(os.listdir(base)):
            if fname.startswith("test_") and fname.endswith(".py"):
                result.append(os.path.join(base, fname))
        return result

    def _collect_all_test_files() -> list:
        """Rekurencyjnie zbiera wszystkie test_*.py z tests/ i podkatalogow."""
        result = []
        for root, dirs, files in os.walk(TESTS_DIR):
            # pomin __pycache__
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in sorted(files):
                if fname.startswith("test_") and fname.endswith(".py"):
                    result.append(os.path.join(root, fname))
        return result

    # -------------------------------------------------------------------------
    #  Uruchomienie pliku testowego przez unittest discover
    # -------------------------------------------------------------------------

    def _run_file(filepath: str) -> tuple:
        """Uruchamia jeden plik testowy. Zwraca (ok: bool, output: str)."""
        result = subprocess.run(
            [sys.executable, "-m", "unittest", filepath, "-v"],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
        )
        combined = result.stdout + result.stderr
        ok = result.returncode == 0
        return ok, combined

    # -------------------------------------------------------------------------
    #  Menu (bez argumentow)
    # -------------------------------------------------------------------------

    def tests_menu(args):
        """Wyswietla menu modulu tests."""
        _w(f"\n{BOLD}{BCYN}  +======================================+{RST}\n")
        _w(f"{BOLD}{BCYN}  |   ?  {_t('tests_module_title'):<33}|{RST}\n")
        _w(f"{BOLD}{BCYN}  +======================================+{RST}\n\n")

        cmds = [
            ("tests run",           _t("tests_cmd_run")),
            ("tests run core",      _t("tests_cmd_run_core")),
            ("tests run terminalx", _t("tests_cmd_run_terminalx")),
            ("tests run i18n",      _t("tests_cmd_run_i18n")),
            ("tests run all",       _t("tests_cmd_run_all")),
            ("tests list",          _t("tests_cmd_list")),
            ("tests status",        _t("tests_cmd_status")),
            ("tests lang",          _t("tests_cmd_lang")),
        ]
        for c, d in cmds:
            _w(f"  {YLW}{_pad(c, 28)}{RST} {DIM}{d}{RST}\n")
        _w("\n")

    # -------------------------------------------------------------------------
    #  tests list - pokaz dostepne pliki
    # -------------------------------------------------------------------------

    def tests_list(args):
        """Lista plikow testowych w katalogu tests/."""
        files = _collect_all_test_files()
        _w(f"\n{BOLD}{CYN}  {_t('tests_list_header')}{RST}\n\n")
        if not files:
            _w(f"  {DIM}{_t('tests_none_found')}{RST}\n\n")
            return
        for f in files:
            rel = os.path.relpath(f, ROOT_DIR)
            exists_mark = f"{GRN}[V]{RST}" if os.path.isfile(f) else f"{RED}[X]{RST}"
            _w(f"  {exists_mark}  {YLW}{rel}{RST}\n")
        _w(f"\n  {DIM}{_t('tests_total', n=len(files))}{RST}\n\n")

    # -------------------------------------------------------------------------
    #  tests status - podsumowanie katalogu tests/
    # -------------------------------------------------------------------------

    def tests_status(args):
        """Pokazuje stan katalogu tests/ i subdirektoriow."""
        _w(f"\n{BOLD}{CYN}  {_t('tests_status_header')}{RST}\n\n")
        if not os.path.isdir(TESTS_DIR):
            _w(f"  {RED}{_t('tests_dir_missing')}{RST}\n\n")
            return

        total = 0
        for root, dirs, files in os.walk(TESTS_DIR):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            rel = os.path.relpath(root, ROOT_DIR)
            test_files = [f for f in files if f.startswith("test_") and f.endswith(".py")]
            total += len(test_files)
            if rel == "tests":
                label = f"{BOLD}{CYN}tests/{RST}"
            else:
                label = f"  {CYN}{rel}/{RST}"
            count_str = f"{GRN}{len(test_files)}{RST}" if test_files else f"{DIM}0{RST}"
            _w(f"  {label}  {DIM}({_t('tests_count', n=len(test_files))}){RST}\n")
            for tf in sorted(test_files):
                _w(f"      {YLW}{tf}{RST}\n")

        _w(f"\n  {DIM}{_t('tests_total', n=total)}{RST}\n\n")

    # -------------------------------------------------------------------------
    #  Uruchamianie testow
    # -------------------------------------------------------------------------

    def _run_and_report(files: list, label: str):
        """Uruchamia zestaw plikow i drukuje wyniki."""
        if not files:
            _w(f"  {RED}{_t('tests_none_found')}{RST}\n\n")
            return

        _w(f"\n{BOLD}{CYN}  +======================================+{RST}\n")
        _w(f"{BOLD}{CYN}  |  ?  {_pad(label, 34)}|{RST}\n")
        _w(f"{BOLD}{CYN}  +======================================+{RST}\n\n")

        passed = 0
        failed = 0
        for filepath in files:
            rel = os.path.relpath(filepath, ROOT_DIR)
            _w(f"  {DIM}> {rel}{RST}  ")
            ok, output = _run_file(filepath)
            if ok:
                _w(f"{GRN}{BOLD}PASS{RST}\n")
                passed += 1
            else:
                _w(f"{RED}{BOLD}FAIL{RST}\n")
                failed += 1
                # pokaz skrocone wyjscie (ostatnie 15 linii)
                lines = output.strip().splitlines()
                for ln in lines[-15:]:
                    _w(f"    {DIM}{ln}{RST}\n")
                _w("\n")

        _w(f"\n  {'-' * 38}\n")
        total = passed + failed
        status = f"{GRN}[V] {passed}/{total} PASS{RST}" if failed == 0 \
            else f"{RED}[X] {failed}/{total} FAIL  {GRN}{passed} PASS{RST}"
        _w(f"  {BOLD}{status}{RST}\n\n")

    def tests_run(args):
        """Uruchamia testy wg argumentow."""
        if not args:
            # bez argumentu - uruchamia wszystkie w tests/
            files = _collect_all_test_files()
            _run_and_report(files, _t("tests_run_all_label"))
            return

        scope = args[0].lower()

        if scope == "all":
            files = _collect_all_test_files()
            _run_and_report(files, _t("tests_run_all_label"))

        elif scope == "core":
            f = os.path.join(TESTS_DIR, "test_core.py")
            _run_and_report([f] if os.path.isfile(f) else [], _t("tests_run_core_label"))

        elif scope == "terminalx":
            f = os.path.join(TESTS_DIR, "test_terminalx.py")
            _run_and_report([f] if os.path.isfile(f) else [], _t("tests_run_terminalx_label"))

        elif scope == "i18n":
            f = os.path.join(TESTS_DIR, "test_i18n.py")
            _run_and_report([f] if os.path.isfile(f) else [], _t("tests_run_i18n_label"))

        elif scope == "modules":
            files = _collect_test_files("modules")
            _run_and_report(files, _t("tests_run_modules_label"))

        elif scope == "plugins":
            files = _collect_test_files("plugins")
            _run_and_report(files, _t("tests_run_plugins_label"))

        else:
            # traktuj jako nazwe pliku lub wzorzec
            f = os.path.join(TESTS_DIR, scope)
            if not f.endswith(".py"):
                f += ".py"
            if not os.path.isfile(f):
                f = os.path.join(TESTS_DIR, f"test_{scope}.py")
            if os.path.isfile(f):
                _run_and_report([f], os.path.basename(f))
            else:
                _w(f"  {RED}{_t('tests_file_not_found', name=scope)}{RST}\n\n")

    # -------------------------------------------------------------------------
    #  tests lang - inline diagnostyka systemu tlumaczen
    # -------------------------------------------------------------------------

    def _scan_t_calls_inline() -> dict:
        """Skanuje kod zrodlowy i zwraca {klucz: [(plik, linia), ...]}."""
        import re as _re
        PATTERNS = [
            _re.compile(r'\b_t\s*\(\s*["\'](\w+)["\']\s*[,)]'),
            _re.compile(r'terminal\.t\s*\(\s*["\'](\w+)["\']\s*[,)]'),
            _re.compile(r'self\.t\s*\(\s*["\'](\w+)["\']\s*[,)]'),
        ]
        results: dict = {}
        skip_dirs = {"__pycache__", ".git", "lang", "tests"}
        for dirpath, dirs, files in os.walk(ROOT_DIR):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(dirpath, fname)
                rel   = os.path.relpath(fpath, ROOT_DIR)
                try:
                    lines = open(fpath, encoding="utf-8").readlines()
                except OSError:
                    continue
                for lineno, line in enumerate(lines, 1):
                    for pat in PATTERNS:
                        for m in pat.finditer(line):
                            key = m.group(1)
                            results.setdefault(key, []).append((rel, lineno))
        return results

    def _load_lang_dict(lang_code: str) -> dict:
        """Wczytuje slownik T dla danego jezyka."""
        try:
            mod_name = f"lang.{lang_code}"
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            mod = importlib.import_module(mod_name)
            return mod.T
        except Exception:
            return {}

    def _get_placeholders_inline(text: str) -> set:
        import re as _re
        return set(_re.findall(r"\{(\w+)\}", text))

    def tests_lang(args):
        """Inline diagnostyka systemu tlumaczen - bez uruchamiania subprocess."""
        import re as _re

        _w(f"\n{BOLD}{CYN}  +======================================+{RST}\n")
        _w(f"{BOLD}{CYN}  |  i18n  {_t('tests_lang_header'):<31}|{RST}\n")
        _w(f"{BOLD}{CYN}  +======================================+{RST}\n\n")

        # --- wczytaj jezyki ---
        lang_dir = os.path.join(ROOT_DIR, "lang")
        langs = sorted(
            f[:-3] for f in os.listdir(lang_dir)
            if f.endswith(".py") and not f.startswith("_")
        )
        dicts = {lg: _load_lang_dict(lg) for lg in langs}
        en = dicts.get("en", {})

        # --- skanuj kod ---
        _w(f"  {DIM}{_t('tests_lang_scanning')}{RST}\n")
        used = _scan_t_calls_inline()

        # --- statystyki ---
        _w(f"\n  {DIM}{_t('tests_lang_keys_en', n=len(en))}{RST}\n")
        for lg in langs:
            if lg == "en":
                continue
            _w(f"  {DIM}{_t('tests_lang_keys_pl', n=len(dicts[lg]))}{RST}  [{lg.upper()}]\n")
        _w(f"  {DIM}{_t('tests_lang_code_refs', n=len(used))}{RST}\n\n")

        # --- zbierz problemy ---
        errors: list = []
        warns:  list = []
        infos:  list = []

        ALLOWED_EMPTY = {"cat_general_hint"}

        for lg in langs:
            T = dicts[lg]
            if not T:
                errors.append(f"[{lg.upper()}] Nie mozna wczytac pliku lang/{lg}.py")
                continue

            # brakujace klucze wzgledem EN
            if lg != "en":
                for k in sorted(set(en) - set(T)):
                    errors.append(f"Klucz {k!r} jest w EN ale BRAK w {lg.upper()}")
                for k in sorted(set(T) - set(en)):
                    errors.append(f"Klucz {k!r} jest w {lg.upper()} ale BRAK w EN")

            # puste wartosci
            for k, v in T.items():
                if v == "" and k not in ALLOWED_EMPTY:
                    warns.append(f"[{lg.upper()}] {k!r} ma pusta wartosc")

            # nie-stringowe wartosci
            for k, v in T.items():
                if not isinstance(v, str):
                    errors.append(f"[{lg.upper()}] {k!r} nie jest stringiem: {type(v).__name__}")

            # bledy formatu (zle placeholdery)
            for k, v in T.items():
                if not isinstance(v, str):
                    continue
                phs = _get_placeholders_inline(v)
                if phs:
                    try:
                        v.format(**{p: "X" for p in phs})
                    except Exception as exc:
                        errors.append(f"[{lg.upper()}] {k!r} blad formatu: {exc}")

            # parity placeholderow EN <-> inne jezyki
            if lg != "en":
                for k in sorted(set(en) & set(T)):
                    ep = _get_placeholders_inline(en[k])
                    lp = _get_placeholders_inline(T[k])
                    if ep != lp:
                        errors.append(
                            f"Placeholder: {k!r}  EN={ep}  {lg.upper()}={lp}"
                        )

        # klucze uzywane w kodzie ale brak w EN
        for k, refs in sorted(used.items()):
            if k not in en:
                loc = f"{refs[0][0]}:{refs[0][1]}"
                errors.append(f"Klucz {k!r} uzywany w kodzie ({loc}) ale BRAK w EN")
            for lg in langs:
                if lg == "en":
                    continue
                if k not in dicts[lg]:
                    loc = f"{refs[0][0]}:{refs[0][1]}"
                    errors.append(f"Klucz {k!r} uzywany w kodzie ({loc}) ale BRAK w {lg.upper()}")

        # podejrzane nieprzetlumaczone (PL == EN, dlugie)
        KNOWN_IDENTICAL = {
            "analyser_menu_title", "pkg_module_title", "cat_ecosystem",
            "cfg_type_bool", "cfg_type_str", "cfg_type_choice", "cfg_type_int",
            "dir_home", "dir_lib", "dir_mod", "dir_plug", "go_alias",
            "alias_expands_to", "analyser_field_sha256", "analyser_stats_cache",
            "scripts_find_label_tag",
            "search_ex1", "search_ex2", "search_ex3", "search_ex4",
        }
        for lg in langs:
            if lg == "en":
                continue
            T = dicts[lg]
            for k, v in T.items():
                if (k in en and v == en[k]
                        and len(v) > 30 and k not in KNOWN_IDENTICAL):
                    warns.append(
                        f"[{lg.upper()}] {k!r} identyczne z EN (nieprzet?): {v!r}"
                    )

        # nieuzywane klucze
        unused = set(en) - set(used)
        if unused:
            infos.append(
                f"{len(unused)} kluczy nieuzywanych w kodzie zrodlowym"
            )

        # --- drukuj wyniki ---
        total_issues = len(errors) + len(warns)
        if total_issues == 0:
            _w(f"  {GRN}{BOLD}[V] {_t('tests_lang_no_issues')}{RST}\n")
        else:
            _w(f"  {RED}{BOLD}{_t('tests_lang_issues_found', n=total_issues)}{RST}\n\n")

        if errors:
            _w(f"  {RED}{BOLD}{_t('tests_lang_section_errors')} ({len(errors)}){RST}\n")
            for msg in errors:
                _w(f"    {RED}[X]{RST} {msg}\n")
            _w("\n")

        if warns:
            _w(f"  {YLW}{BOLD}{_t('tests_lang_section_warns')} ({len(warns)}){RST}\n")
            for msg in warns:
                _w(f"    {YLW}[!]{RST} {msg}\n")
            _w("\n")

        if infos:
            _w(f"  {DIM}{BOLD}{_t('tests_lang_section_info')} ({len(infos)}){RST}\n")
            for msg in infos:
                _w(f"    {DIM}[i]{RST} {msg}\n")
            _w("\n")

        # pasek podsumowania
        _w(f"  {'-' * 38}\n")
        if total_issues == 0:
            _w(f"  {GRN}{BOLD}OK  — 0 bledow, 0 ostrzezen{RST}\n\n")
        else:
            err_str  = f"{RED}{len(errors)} error(s){RST}" if errors else f"{DIM}0 errors{RST}"
            warn_str = f"{YLW}{len(warns)} warning(s){RST}" if warns else f"{DIM}0 warnings{RST}"
            _w(f"  {err_str}  {warn_str}\n\n")

    # -------------------------------------------------------------------------
    #  Glowny dispatcher
    # -------------------------------------------------------------------------

    def tests_wrapper(args):
        if not args:
            tests_menu(args)
            return
        subcmd = args[0].lower()
        rest   = args[1:]
        if subcmd == "run":
            tests_run(rest)
        elif subcmd == "list":
            tests_list(rest)
        elif subcmd == "status":
            tests_status(rest)
        elif subcmd == "lang":
            tests_lang(rest)
        else:
            _w(f"  {RED}{_t('tests_unknown_sub', sub=subcmd)}{RST}\n\n")

    terminal.register_command(
        "tests", tests_wrapper,
        description=_t("cmd_tests"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal):
    terminal.commands.pop("tests", None)
