"""Testy systemu tlumaczen (i18n) dla TerminalX.

Modul automatycznie wykrywa i diagnozuje:
  - brakujace klucze (brak klucza w EN lub PL)
  - niezgodnosc klucze EN <-> PL (rozne zestawy)
  - brakujace / nadmiarowe placeholdery {name} miedzy EN i PL
  - puste wartosci (klucz istnieje, ale wartosc == '')
  - niespojne wartosci (PL identyczne z EN dla lancuchow > 30 znakow)
  - klucze uzywane w kodzie ale nieobecne w plikach jezyka
  - bledy formatu (wartosci z nieprawidlowymi {placeholderami})
  - persystencja jezyka (zapis / odczyt lang.json)
  - przelaczanie jezyka w runtime (lang en / lang pl)
  - inicjalizacje terminala z roznym domyslnym jezykiem
  - global _safe_print na roznych OS (UTF-8 fallback)
  - klucze w _refresh_command_descriptions bez pokrycia

Uruchomienie:
    python -m pytest tests/test_i18n.py -v
    # lub
    python tests/test_i18n.py

Autor  : Sebastian Januchowski
Brand  : polsoft.ITS(TM)
Version: 1.0.0
"""

import ast
import importlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import contextlib

# ---------------------------------------------------------------------------
# Sciezka do katalogu glownego projektu
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LANG_EN = os.path.join(ROOT, "lang", "en.py")
LANG_PL = os.path.join(ROOT, "lang", "pl.py")
CORE_DIR = os.path.join(ROOT, "core")
LANG_DIR = os.path.join(ROOT, "lang")


# ===========================================================================
#  Helpers
# ===========================================================================

def _load_T(filepath: str) -> dict:
    """Wczytaj slownik T z pliku jezyka bez importowania modulu."""
    ns: dict = {}
    with open(filepath, encoding="utf-8") as f:
        src = f.read()
    exec(compile(src, filepath, "exec"), ns)
    return ns.get("T", {})


def _load_T_via_import(lang_code: str) -> dict:
    """Importuj lang.<lang_code> i zwroc T (czysci cache importow)."""
    mod_name = f"lang.{lang_code}"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    return mod.T


def _get_placeholders(text: str) -> set:
    """Zwroc zbior nazw placeholderow {name} w tekscie."""
    return set(re.findall(r"\{(\w+)\}", text))


def _scan_t_calls(src_root: str) -> dict:
    """Przeskanuj kod zrodlowy i zwroc slownik {klucz: [(plik, linia), ...]}.

    Rozpoznaje tylko prawdziwe wywolania translatora:
        _t('key')   _t('key', ...)
        terminal.t('key')
        self.t('key')

    Ignoruje dict.get('key') i podobne false-positive.
    """
    PATTERNS = [
        re.compile(r'\b_t\s*\(\s*["\'](\w+)["\']\s*[,)]'),
        re.compile(r'terminal\.t\s*\(\s*["\'](\w+)["\']\s*[,)]'),
        re.compile(r'self\.t\s*\(\s*["\'](\w+)["\']\s*[,)]'),
    ]
    results: dict = {}
    skip_dirs = {"__pycache__", ".git", "lang", "tests"}

    for dirpath, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, src_root)
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


def _supported_langs() -> list:
    """Wykryj wszystkie jezyki na podstawie plikow lang/*.py."""
    langs = []
    for fname in os.listdir(LANG_DIR):
        if fname.endswith(".py") and not fname.startswith("_"):
            langs.append(fname[:-3])
    return sorted(langs)


# ===========================================================================
#  1. Struktura plikow jezykowych
# ===========================================================================

class TestLangFilesExist(unittest.TestCase):
    """Pliki jezykowe musza istniec i byc parsowalne."""

    def test_en_file_exists(self):
        self.assertTrue(os.path.isfile(LANG_EN), f"Brak pliku: {LANG_EN}")

    def test_pl_file_exists(self):
        self.assertTrue(os.path.isfile(LANG_PL), f"Brak pliku: {LANG_PL}")

    def test_en_file_parseable(self):
        try:
            _load_T(LANG_EN)
        except SyntaxError as e:
            self.fail(f"SyntaxError w lang/en.py: {e}")

    def test_pl_file_parseable(self):
        try:
            _load_T(LANG_PL)
        except SyntaxError as e:
            self.fail(f"SyntaxError w lang/pl.py: {e}")

    def test_en_T_is_dict(self):
        T = _load_T(LANG_EN)
        self.assertIsInstance(T, dict, "lang/en.py: T nie jest slownikiem")

    def test_pl_T_is_dict(self):
        T = _load_T(LANG_PL)
        self.assertIsInstance(T, dict, "lang/pl.py: T nie jest slownikiem")

    def test_en_T_not_empty(self):
        T = _load_T(LANG_EN)
        self.assertGreater(len(T), 0, "lang/en.py: T jest pusty")

    def test_pl_T_not_empty(self):
        T = _load_T(LANG_PL)
        self.assertGreater(len(T), 0, "lang/pl.py: T jest pusty")

    def test_all_lang_files_importable(self):
        """Kazdy plik lang/*.py musi byc importowalny."""
        for lang in _supported_langs():
            with self.subTest(lang=lang):
                T = _load_T_via_import(lang)
                self.assertIsInstance(T, dict)


# ===========================================================================
#  2. Kompletnosc kluczy miedzy jezykami
# ===========================================================================

class TestKeyCompleteness(unittest.TestCase):
    """Wszystkie jezyki musza miec dokladnie ten sam zestaw kluczy."""

    def setUp(self):
        self.en = _load_T(LANG_EN)
        self.pl = _load_T(LANG_PL)

    def test_no_keys_only_in_en(self):
        only_en = set(self.en) - set(self.pl)
        if only_en:
            detail = "\n  ".join(sorted(only_en))
            self.fail(
                f"Klucze obecne w EN ale BRAKUJACE w PL ({len(only_en)}):\n  {detail}"
            )

    def test_no_keys_only_in_pl(self):
        only_pl = set(self.pl) - set(self.en)
        if only_pl:
            detail = "\n  ".join(sorted(only_pl))
            self.fail(
                f"Klucze obecne w PL ale BRAKUJACE w EN ({len(only_pl)}):\n  {detail}"
            )

    def test_all_langs_same_key_count(self):
        """Wszystkie wykryte jezyki maja taka sama liczbe kluczy jak EN."""
        en_keys = set(self.en)
        for lang in _supported_langs():
            if lang == "en":
                continue
            with self.subTest(lang=lang):
                T = _load_T_via_import(lang)
                missing = en_keys - set(T)
                extra = set(T) - en_keys
                msgs = []
                if missing:
                    msgs.append(f"brakuje {len(missing)} kluczy: {sorted(missing)[:10]}")
                if extra:
                    msgs.append(f"nadmiarowe {len(extra)} klucze: {sorted(extra)[:10]}")
                if msgs:
                    self.fail(f"lang/{lang}.py: " + "; ".join(msgs))

    def test_key_ordering_consistent(self):
        """Kolejnosc kluczy w EN i PL powinna byc identyczna (latwiejsza diff/merge)."""
        en_order = [k for k in re.findall(r'"(\w+)":', open(LANG_EN).read()) if k in self.en]
        pl_order = [k for k in re.findall(r'"(\w+)":', open(LANG_PL).read()) if k in self.pl]
        mismatches = [
            (i, ek, pk)
            for i, (ek, pk) in enumerate(zip(en_order, pl_order))
            if ek != pk
        ]
        if mismatches:
            sample = mismatches[:5]
            detail = "\n  ".join(f"pos {i}: EN={ek!r}  PL={pk!r}" for i, ek, pk in sample)
            self.fail(
                f"Niezgodna kolejnosc kluczy ({len(mismatches)} miejsc):\n  {detail}"
            )


# ===========================================================================
#  3. Jakos wartosci
# ===========================================================================

class TestValueQuality(unittest.TestCase):
    """Kontrola jakosci wartosci w plikach tlumaczen."""

    def setUp(self):
        self.en = _load_T(LANG_EN)
        self.pl = _load_T(LANG_PL)

    # --- 3a. Puste wartosci ------------------------------------------------

    def test_no_empty_values_en(self):
        # cat_general_hint moze byc pusty (celowo) - tylko taki wyjatek
        ALLOWED_EMPTY = {"cat_general_hint"}
        empty = {k for k, v in self.en.items() if v == "" and k not in ALLOWED_EMPTY}
        if empty:
            self.fail(f"Puste wartosci w EN ({len(empty)}): {sorted(empty)}")

    def test_no_empty_values_pl(self):
        ALLOWED_EMPTY = {"cat_general_hint"}
        empty = {k for k, v in self.pl.items() if v == "" and k not in ALLOWED_EMPTY}
        if empty:
            self.fail(f"Puste wartosci w PL ({len(empty)}): {sorted(empty)}")

    # --- 3b. Wszystkie wartosci musza byc stringami -----------------------

    def test_all_values_are_strings_en(self):
        non_str = {k: type(v).__name__ for k, v in self.en.items() if not isinstance(v, str)}
        if non_str:
            self.fail(f"Nie-stringowe wartosci w EN: {non_str}")

    def test_all_values_are_strings_pl(self):
        non_str = {k: type(v).__name__ for k, v in self.pl.items() if not isinstance(v, str)}
        if non_str:
            self.fail(f"Nie-stringowe wartosci w PL: {non_str}")

    # --- 3c. Podejrzane nieprzetlumaczone PL (identyczne z EN > 30 zn.) ---

    def test_pl_not_literally_identical_to_en_long(self):
        """Dluzsze ciagi (>30 zn.) nie powinny byc identyczne w EN i PL."""
        KNOWN_IDENTICAL = {
            # technicalia - celowo nie tlumaczone
            "analyser_menu_title", "pkg_module_title",
            "cat_ecosystem", "cfg_type_bool", "cfg_type_str",
            "cfg_type_choice", "cfg_type_int",
            "dir_home", "dir_lib", "dir_mod", "dir_plug",
            "go_alias", "alias_expands_to",
            "analyser_field_sha256", "analyser_stats_cache",
            "scripts_find_label_tag",
            "search_ex1", "search_ex2", "search_ex3", "search_ex4",
        }
        suspects = {
            k: v
            for k, v in self.pl.items()
            if k in self.en
            and v == self.en[k]
            and len(v) > 30
            and k not in KNOWN_IDENTICAL
        }
        if suspects:
            detail = "\n  ".join(f"{k!r}: {v!r}" for k, v in sorted(suspects.items()))
            self.fail(
                f"PL wartosci podejrzanie identyczne z EN ({len(suspects)}):\n  {detail}"
            )


# ===========================================================================
#  4. Spójnosc placeholderow {name}
# ===========================================================================

class TestPlaceholders(unittest.TestCase):
    """Placeholdery {name} musza byc identyczne w EN i PL dla danego klucza."""

    def setUp(self):
        self.en = _load_T(LANG_EN)
        self.pl = _load_T(LANG_PL)

    def test_placeholder_parity_en_pl(self):
        """Kazdy klucz ma te same placeholdery w EN i PL."""
        errors = []
        for key in set(self.en) & set(self.pl):
            ep = _get_placeholders(self.en[key])
            pp = _get_placeholders(self.pl[key])
            if ep != pp:
                errors.append(
                    f"  {key!r}\n"
                    f"    EN {ep}  ->  {self.en[key]!r}\n"
                    f"    PL {pp}  ->  {self.pl[key]!r}"
                )
        if errors:
            self.fail(
                f"Niezgodne placeholdery ({len(errors)} kluczy):\n" + "\n".join(errors)
            )

    def test_format_strings_valid_en(self):
        """Wszystkie wartosci EN daja sie sformatowac z dummy argumentami."""
        errors = []
        for key, val in self.en.items():
            phs = _get_placeholders(val)
            if phs:
                try:
                    val.format(**{p: "X" for p in phs})
                except Exception as e:
                    errors.append(f"  {key!r}: {e}  [{val!r}]")
        if errors:
            self.fail(f"Bledy formatu w EN ({len(errors)}):\n" + "\n".join(errors))

    def test_format_strings_valid_pl(self):
        """Wszystkie wartosci PL daja sie sformatowac z dummy argumentami."""
        errors = []
        for key, val in self.pl.items():
            phs = _get_placeholders(val)
            if phs:
                try:
                    val.format(**{p: "X" for p in phs})
                except Exception as e:
                    errors.append(f"  {key!r}: {e}  [{val!r}]")
        if errors:
            self.fail(f"Bledy formatu w PL ({len(errors)}):\n" + "\n".join(errors))

    def test_no_orphaned_braces(self):
        """Wykryj niedomkniete klamry {{ lub pojedyncze { nie bedace placeholderem."""
        BRACE_RE = re.compile(r"(?<!\{)\{(?!\{)(?!\w+\})")
        errors = []
        for lang, T in [("EN", self.en), ("PL", self.pl)]:
            for key, val in T.items():
                if BRACE_RE.search(val):
                    errors.append(f"  [{lang}] {key!r}: {val!r}")
        if errors:
            self.fail(
                f"Podejrzane klamry w wartosciach ({len(errors)}):\n" + "\n".join(errors)
            )


# ===========================================================================
#  5. Pokrycie kluczy uzywanych w kodzie
# ===========================================================================

class TestCodeCoverage(unittest.TestCase):
    """Klucze uzywane w kodzie zrodlowym musza byc obecne w obu jezykach."""

    @classmethod
    def setUpClass(cls):
        cls.en = _load_T(LANG_EN)
        cls.pl = _load_T(LANG_PL)
        cls.used = _scan_t_calls(ROOT)

    def test_no_missing_keys_in_en(self):
        """Zadne wywolanie _t('key') w kodzie nie moze miec brakujacego klucza w EN."""
        missing = {k: v for k, v in self.used.items() if k not in self.en}
        if missing:
            lines = []
            for k, refs in sorted(missing.items()):
                loc = f"{refs[0][0]}:{refs[0][1]}"
                lines.append(f"  {k!r}  (pierwsze uzycie: {loc})")
            self.fail(
                f"Klucze uzywane w kodzie ale BRAKUJACE w EN ({len(missing)}):\n"
                + "\n".join(lines)
            )

    def test_no_missing_keys_in_pl(self):
        """Zadne wywolanie _t('key') w kodzie nie moze miec brakujacego klucza w PL."""
        missing = {k: v for k, v in self.used.items() if k not in self.pl}
        if missing:
            lines = []
            for k, refs in sorted(missing.items()):
                loc = f"{refs[0][0]}:{refs[0][1]}"
                lines.append(f"  {k!r}  (pierwsze uzycie: {loc})")
            self.fail(
                f"Klucze uzywane w kodzie ale BRAKUJACE w PL ({len(missing)}):\n"
                + "\n".join(lines)
            )

    def test_refresh_cmd_map_keys_exist(self):
        """Wszystkie klucze z _CMD_MAP w core/lang.py musza byc w EN i PL."""
        lang_src = open(os.path.join(CORE_DIR, "lang.py"), encoding="utf-8").read()
        # Extract (desc_key, cat_key) tuples from _CMD_MAP
        desc_keys = set(re.findall(r'"(cmd_\w+|colors_cmd_\w+)"', lang_src))
        cat_keys  = set(re.findall(r'"(cat_\w+)"', lang_src))
        all_keys  = desc_keys | cat_keys

        missing_en = all_keys - set(self.en)
        missing_pl = all_keys - set(self.pl)
        msgs = []
        if missing_en:
            msgs.append(f"brakuje w EN: {sorted(missing_en)}")
        if missing_pl:
            msgs.append(f"brakuje w PL: {sorted(missing_pl)}")
        if msgs:
            self.fail("_CMD_MAP w lang.py odwoluje sie do brakujacych kluczy: " + "; ".join(msgs))

    def test_report_unused_keys(self):
        """Informacyjny: klucze nieuzywane w kodzie (nie fail, tylko ostrzezenie)."""
        unused = set(self.en) - set(self.used)
        # Nie failujemy - klucze moga byc uzywane przez modul zewnetrzny / GUI
        # Ale rejestrujemy jako info jesli jest ich wiele
        if len(unused) > 200:
            self.fail(
                f"Zbyt wiele kluczy nieuzywanych w kodzie ({len(unused)}) - "
                "prawdopodobnie blad skanowania lub niesprzatniete klucze."
            )


# ===========================================================================
#  6. Persystencja jezyka
# ===========================================================================

class TestLangPersistence(unittest.TestCase):
    """Zapis i odczyt wybranego jezyka do/z pliku .cache/global/lang.json."""

    def setUp(self):
        from core import lang as lang_mod
        self.mod = lang_mod
        self.tmp_dir = tempfile.mkdtemp(prefix="tx_lang_test_")
        self.orig_path = lang_mod._LANG_FILE
        self.tmp_file = os.path.join(self.tmp_dir, "lang.json")
        lang_mod._LANG_FILE = self.tmp_file

    def tearDown(self):
        from core import lang as lang_mod
        lang_mod._LANG_FILE = self.orig_path
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_load_saved_lang_no_file_returns_none(self):
        result = self.mod.load_saved_lang()
        self.assertIsNone(result)

    def test_save_and_load_en(self):
        self.mod._save_lang("en")
        result = self.mod.load_saved_lang()
        self.assertEqual(result, "en")

    def test_save_and_load_pl(self):
        self.mod._save_lang("pl")
        result = self.mod.load_saved_lang()
        self.assertEqual(result, "pl")

    def test_invalid_lang_code_returns_none(self):
        with open(self.tmp_file, "w", encoding="utf-8") as f:
            json.dump({"lang": "xx"}, f)
        result = self.mod.load_saved_lang()
        self.assertIsNone(result)

    def test_corrupt_json_returns_none(self):
        with open(self.tmp_file, "w", encoding="utf-8") as f:
            f.write("NOT{JSON}")
        result = self.mod.load_saved_lang()
        self.assertIsNone(result)

    def test_empty_json_returns_none(self):
        with open(self.tmp_file, "w", encoding="utf-8") as f:
            json.dump({}, f)
        result = self.mod.load_saved_lang()
        self.assertIsNone(result)

    def test_save_creates_missing_directories(self):
        deep = os.path.join(self.tmp_dir, "a", "b", "lang.json")
        self.mod._LANG_FILE = deep
        self.mod._save_lang("pl")
        self.assertTrue(os.path.isfile(deep))

    def test_load_after_save_roundtrip_both_langs(self):
        for code in ("en", "pl"):
            with self.subTest(code=code):
                self.mod._save_lang(code)
                self.assertEqual(self.mod.load_saved_lang(), code)


# ===========================================================================
#  7. Runtime: przelaczanie jezyka w TerminalX
# ===========================================================================

class TestLangRuntime(unittest.TestCase):
    """Testy przelaczania jezyka przez komende 'lang' w runtime."""

    def setUp(self):
        """Izoluj od globalnego pliku lang.json - kazdy test dostaje czysty stan."""
        import core.lang as lang_mod
        self._orig_lang_file = lang_mod._LANG_FILE
        self._tmp_dir = tempfile.mkdtemp(prefix="tx_rt_lang_")
        lang_mod._LANG_FILE = os.path.join(self._tmp_dir, "lang.json")

    def tearDown(self):
        import core.lang as lang_mod
        lang_mod._LANG_FILE = self._orig_lang_file
        import shutil
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _make_terminal(self, lang="pl"):
        """Tworzy TerminalX z zaladowanym modulem lang (bez pelnego run())."""
        from core import TerminalX
        import core.lang as lang_mod
        t = TerminalX(lang=lang)
        lang_mod.setup(t)
        return t

    def test_terminal_boots_pl(self):
        t = self._make_terminal("pl")
        self.assertEqual(t.lang, "pl")

    def test_terminal_boots_en(self):
        t = self._make_terminal("en")
        self.assertEqual(t.lang, "en")

    def test_t_returns_translation_pl(self):
        t = self._make_terminal("pl")
        result = t.t("startup_msg")
        # Wartosc nie moze byc kluczem (oznaczaloby brak translacji)
        self.assertNotEqual(result, "startup_msg")
        self.assertIsInstance(result, str)

    def test_t_returns_translation_en(self):
        t = self._make_terminal("en")
        result = t.t("startup_msg")
        self.assertNotEqual(result, "startup_msg")
        self.assertIn("TerminalX", result)

    def test_switch_pl_to_en(self):
        t = self._make_terminal("pl")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            t.commands["lang"]["func"](["en"])
        self.assertEqual(t.lang, "en")
        result = t.t("startup_msg")
        self.assertIn("TerminalX", result)

    def test_switch_en_to_pl(self):
        t = self._make_terminal("en")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            t.commands["lang"]["func"](["pl"])
        self.assertEqual(t.lang, "pl")
        result = t.t("startup_msg")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "startup_msg")

    def test_switch_back_and_forth(self):
        """Wielokrotne przelaczanie nie powoduje bledu."""
        t = self._make_terminal("pl")
        buf = io.StringIO()
        for code in ["en", "pl", "en", "pl"]:
            with contextlib.redirect_stdout(buf):
                t.commands["lang"]["func"]([code])
            self.assertEqual(t.lang, code)

    def test_switch_to_unknown_lang_prints_error(self):
        t = self._make_terminal("pl")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            t.commands["lang"]["func"](["xx"])
        # Jezyk nie zmienil sie
        self.assertEqual(t.lang, "pl")
        # Komunikat o bledzie zostal wyswietlony
        self.assertGreater(len(buf.getvalue().strip()), 0)

    def test_switch_updates_all_command_descriptions(self):
        """Po przelaczeniu opisy komend sa w nowym jezyku."""
        t = self._make_terminal("pl")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            t.commands["lang"]["func"](["en"])
        if "lang" in t.commands:
            desc = t.commands["lang"]["description"]
            en_T = _load_T(LANG_EN)
            self.assertEqual(desc, en_T.get("cmd_lang", desc))

    def test_show_current_lang_no_args(self):
        """lang bez argumentow wypisuje aktualny jezyk."""
        t = self._make_terminal("en")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            t.commands["lang"]["func"]([])
        output = buf.getvalue()
        self.assertGreater(len(output.strip()), 0)

    def test_t_function_with_kwargs(self):
        """t('key', name='val') poprawnie formatuje wartosc."""
        t = self._make_terminal("en")
        result = t.t("module_load_error", name="test_mod", exc="err")
        self.assertIn("test_mod", result)
        self.assertIn("err", result)

    def test_t_missing_key_returns_key_itself(self):
        """Nieistniejacy klucz zwraca klucz jako fallback (brak wyjatku)."""
        t = self._make_terminal("en")
        result = t.t("__nonexistent_key_xyz__")
        self.assertEqual(result, "__nonexistent_key_xyz__")

    def test_lang_command_registered(self):
        t = self._make_terminal("pl")
        self.assertIn("lang", t.commands)

    def test_lang_registered_has_description(self):
        t = self._make_terminal("pl")
        self.assertIn("description", t.commands.get("lang", {}))
        self.assertIsInstance(t.commands["lang"]["description"], str)


# ===========================================================================
#  8. _safe_print -- UTF-8 fallback (cross-OS)
# ===========================================================================

class TestSafePrint(unittest.TestCase):
    """_safe_print musi dzialac na kazdym sys.stdout (rowniez nie-UTF-8)."""

    def _get_safe_print(self):
        from core import _safe_print
        return _safe_print

    def test_safe_print_ascii(self):
        _safe_print = self._get_safe_print()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _safe_print("Hello TerminalX")
        self.assertIn("Hello TerminalX", buf.getvalue())

    def test_safe_print_unicode_pl(self):
        _safe_print = self._get_safe_print()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _safe_print("Zażółć gęślą jaźń")
        self.assertGreater(len(buf.getvalue()), 0)

    def test_safe_print_unicode_special(self):
        _safe_print = self._get_safe_print()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _safe_print("ANSI: \x1b[92mOK\x1b[0m")
        self.assertIn("OK", buf.getvalue())

    def test_safe_print_on_narrow_encoding_stream(self):
        """Symulacja cp1250 - znaki polskie maja byc zastapione '?' zamiast bledu."""
        _safe_print = self._get_safe_print()

        class NarrowStream(io.StringIO):
            encoding = "ascii"

            def write(self, text):
                # Symuluj UnicodeEncodeError dla nie-ASCII
                try:
                    text.encode("ascii")
                except UnicodeEncodeError:
                    # Fallback: zastap nieznane znaki
                    text = text.encode("ascii", errors="replace").decode("ascii")
                return super().write(text)

        narrow = NarrowStream()
        with contextlib.redirect_stdout(narrow):
            # Nie moze rzucic wyjatku
            try:
                _safe_print("Zażółć gęślą jaźń - test")
            except Exception as e:
                self.fail(f"_safe_print rzucil wyjatek na narrow stream: {e}")

    def test_safe_print_empty_string(self):
        _safe_print = self._get_safe_print()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _safe_print("")
        # Pusty string + newline
        self.assertEqual(buf.getvalue(), "\n")

    def test_safe_print_multiline(self):
        _safe_print = self._get_safe_print()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _safe_print("linia1\nlinia2\nlinia3")
        output = buf.getvalue()
        self.assertIn("linia1", output)
        self.assertIn("linia3", output)


# ===========================================================================
#  9. Import modulu lang (load_translations)
# ===========================================================================

class TestLoadTranslations(unittest.TestCase):
    """Wewnetrzna funkcja _load_translations z core/lang.py."""

    def setUp(self):
        from core.lang import _load_translations
        self.load = _load_translations

    def test_load_en_returns_dict(self):
        T = self.load("en")
        self.assertIsInstance(T, dict)
        self.assertGreater(len(T), 0)

    def test_load_pl_returns_dict(self):
        T = self.load("pl")
        self.assertIsInstance(T, dict)
        self.assertGreater(len(T), 0)

    def test_load_unknown_returns_empty_dict(self):
        T = self.load("xx")
        self.assertEqual(T, {})

    def test_load_en_has_startup_msg(self):
        T = self.load("en")
        self.assertIn("startup_msg", T)

    def test_load_pl_has_startup_msg(self):
        T = self.load("pl")
        self.assertIn("startup_msg", T)

    def test_en_pl_same_keys(self):
        en = self.load("en")
        pl = self.load("pl")
        self.assertEqual(set(en.keys()), set(pl.keys()))


# ===========================================================================
#  10. Diagnostyczny raport (uruchamiany gdy test_i18n jest glownym skryptem)
# ===========================================================================

class TestI18nDiagnosticReport(unittest.TestCase):
    """Generuje pelny raport diagnostyczny systemu tlumaczen."""

    @classmethod
    def setUpClass(cls):
        cls.en = _load_T(LANG_EN)
        cls.pl = _load_T(LANG_PL)
        cls.used_in_code = _scan_t_calls(ROOT)

    def _collect_all_issues(self) -> list:
        """Zbiera wszystkie problemy i zwraca liste tupli (severity, kategoria, opis)."""
        issues = []
        en, pl = self.en, self.pl

        # Brakujace klucze
        for k in sorted(set(en) - set(pl)):
            issues.append(("ERROR", "missing_key", f"Klucz {k!r} jest w EN ale NIE w PL"))
        for k in sorted(set(pl) - set(en)):
            issues.append(("ERROR", "missing_key", f"Klucz {k!r} jest w PL ale NIE w EN"))

        # Placeholdery
        for k in sorted(set(en) & set(pl)):
            ep = _get_placeholders(en[k])
            pp = _get_placeholders(pl[k])
            if ep != pp:
                issues.append(("ERROR", "placeholder",
                    f"{k!r}: EN ma {ep}, PL ma {pp}"))

        # Puste wartosci (poza dozwolonymi)
        ALLOWED_EMPTY = {"cat_general_hint"}
        for lang, T in [("EN", en), ("PL", pl)]:
            for k, v in T.items():
                if v == "" and k not in ALLOWED_EMPTY:
                    issues.append(("WARN", "empty_value",
                        f"[{lang}] {k!r} ma pusta wartosc"))

        # Klucze w kodzie bez pokrycia
        for k, refs in sorted(self.used_in_code.items()):
            if k not in en:
                loc = f"{refs[0][0]}:{refs[0][1]}"
                issues.append(("ERROR", "code_missing",
                    f"{k!r} uzywany w {loc} ale brak w EN"))
            if k not in pl:
                loc = f"{refs[0][0]}:{refs[0][1]}"
                issues.append(("ERROR", "code_missing",
                    f"{k!r} uzywany w {loc} ale brak w PL"))

        # Bledy formatu
        for lang, T in [("EN", en), ("PL", pl)]:
            for k, v in T.items():
                phs = _get_placeholders(v)
                if phs:
                    try:
                        v.format(**{p: "X" for p in phs})
                    except Exception as e:
                        issues.append(("ERROR", "format_error",
                            f"[{lang}] {k!r}: {e}"))

        # Nieuzywane klucze
        unused = set(en) - set(self.used_in_code)
        if unused:
            issues.append(("INFO", "unused_keys",
                f"{len(unused)} kluczy nie jest uzywanych w kodzie zrodlowym"))

        return issues

    def test_full_diagnostic_report(self):
        """Uruchamia pelna diagnoze i raportuje wszystkie problemy naraz."""
        issues = self._collect_all_issues()
        errors  = [i for i in issues if i[0] == "ERROR"]
        warns   = [i for i in issues if i[0] == "WARN"]
        infos   = [i for i in issues if i[0] == "INFO"]

        report_lines = [
            "",
            "=" * 70,
            "  TerminalX i18n - Raport diagnostyczny",
            "=" * 70,
            f"  Klucze EN : {len(self.en)}",
            f"  Klucze PL : {len(self.pl)}",
            f"  Uzywane w kodzie: {len(self.used_in_code)}",
            f"  ERRORS   : {len(errors)}",
            f"  WARNINGS : {len(warns)}",
            f"  INFO     : {len(infos)}",
            "-" * 70,
        ]
        if errors:
            report_lines.append("ERRORS:")
            for _, cat, msg in errors:
                report_lines.append(f"  [{cat}] {msg}")
        if warns:
            report_lines.append("WARNINGS:")
            for _, cat, msg in warns:
                report_lines.append(f"  [{cat}] {msg}")
        if infos:
            report_lines.append("INFO:")
            for _, cat, msg in infos:
                report_lines.append(f"  [{cat}] {msg}")
        report_lines.append("=" * 70)

        report = "\n".join(report_lines)

        if errors:
            self.fail(report)
        else:
            # Drukuj raport nawet gdy brak bledow (dla przejrzystosci)
            print(report)


# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
