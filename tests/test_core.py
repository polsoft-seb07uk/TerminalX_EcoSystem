"""Unit tests for core/ modules of TerminalX.

Tests:
  - _tokenize             (core/__init__.py)
  - TerminalColors        (core/colors.py)
  - alias _load / _save  (core/alias.py)
  - history _load / _save (core/history.py)
  - cache                 (core/cache.py)
  - trash ensure_trash    (core/trash.py)
  - config get / set      (core/config.py)
  - lang load_saved_lang  (core/lang.py)
  - env                   (core/env.py)

Author  : Sebastian Januchowski
Brand   : polsoft.ITS(TM)
Version : 1.0.0
"""

import json
import os
import sys
import tempfile
import unittest
import shutil
import io
import contextlib

# -- ustaw sciezke importow core/* ----------------------------------------
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ===========================================================================
#  core.__init__  --  _tokenize
# ===========================================================================

class TestTokenize(unittest.TestCase):
    """Parser linii polecen (_tokenize)."""

    def setUp(self):
        from core import _tokenize
        self.tok = _tokenize

    def test_simple_words(self):
        self.assertEqual(self.tok("ls -la"), ["ls", "-la"])

    def test_empty_string(self):
        self.assertEqual(self.tok(""), [])

    def test_double_quoted(self):
        result = self.tok('echo "hello world"')
        self.assertEqual(result, ["echo", "hello world"])

    def test_single_quoted(self):
        result = self.tok("echo 'foo bar'")
        self.assertEqual(result, ["echo", "foo bar"])

    def test_pipe_token(self):
        result = self.tok("ls | grep py")
        self.assertEqual(result, ["ls", "|", "grep", "py"])

    def test_unbalanced_quote_fallback(self):
        # nie powinno rzucac wyjatku -- fallback na split()
        result = self.tok('echo "broken')
        self.assertIsInstance(result, list)

    def test_whitespace_only(self):
        self.assertEqual(self.tok("   "), [])

    def test_quoted_pipe_not_split(self):
        """Pipe wewnatrz cudzyslowu nie powinien dzielic segmentow."""
        result = self.tok('echo "a | b"')
        self.assertEqual(result, ["echo", "a | b"])


# ===========================================================================
#  core.colors  --  TerminalColors
# ===========================================================================

class TestTerminalColors(unittest.TestCase):
    """Klasa TerminalColors."""

    def setUp(self):
        from core.colors import TerminalColors
        self.c = TerminalColors()

    def test_bold_wraps_text(self):
        result = self.c.bold("X")
        self.assertIn("X", result)

    def test_red_not_empty(self):
        result = self.c.red("hello")
        self.assertIn("hello", result)

    def test_green_not_empty(self):
        self.assertIn("ok", self.c.green("ok"))

    def test_cyan_not_empty(self):
        self.assertIn("info", self.c.cyan("info"))

    def test_warning_returns_string(self):
        result = self.c.warning("msg")
        self.assertIsInstance(result, str)

    def test_error_returns_string(self):
        result = self.c.error("err")
        self.assertIsInstance(result, str)

    def test_info_returns_string(self):
        result = self.c.info("inf")
        self.assertIsInstance(result, str)

    def test_reset_constant_exists(self):
        self.assertTrue(hasattr(self.c, "RESET"))


# ===========================================================================
#  core.alias  --  _load / _save
# ===========================================================================

class TestAlias(unittest.TestCase):
    """Persistencja aliasow."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        )
        self.tmp.write("{}")
        self.tmp.close()
        self.path = self.tmp.name

        import core.alias as alias_mod
        self._orig_path = alias_mod.ALIAS_FILE
        alias_mod.ALIAS_FILE = self.path
        self.mod = alias_mod

    def tearDown(self):
        self.mod.ALIAS_FILE = self._orig_path
        os.unlink(self.path)

    def test_load_empty_file(self):
        result = self.mod._load()
        self.assertEqual(result, {})

    def test_save_and_load_roundtrip(self):
        data = {"ll": "ls -la", "g": "go root"}
        self.mod._save(data)
        result = self.mod._load()
        self.assertEqual(result, data)

    def test_load_invalid_json_returns_empty(self):
        with open(self.path, "w") as f:
            f.write("NOT JSON {{")
        result = self.mod._load()
        self.assertEqual(result, {})

    def test_load_non_dict_returns_empty(self):
        with open(self.path, "w") as f:
            json.dump([1, 2, 3], f)
        result = self.mod._load()
        self.assertEqual(result, {})

    def test_save_creates_dirs(self):
        nested = os.path.join(tempfile.gettempdir(), "tx_test_alias_dir", "aliases.json")
        self.mod.ALIAS_FILE = nested
        try:
            self.mod._save({"x": "y"})
            self.assertTrue(os.path.isfile(nested))
        finally:
            import shutil
            shutil.rmtree(os.path.dirname(nested), ignore_errors=True)
            self.mod.ALIAS_FILE = self.path


# ===========================================================================
#  core.history  --  _load / _save
# ===========================================================================

class TestHistory(unittest.TestCase):
    """Persistencja historii polecen."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        )
        self.tmp.write("[]")
        self.tmp.close()
        self.path = self.tmp.name

        import core.history as hist_mod
        self._orig_path = hist_mod.HISTORY_FILE
        hist_mod.HISTORY_FILE = self.path
        self.mod = hist_mod

    def tearDown(self):
        self.mod.HISTORY_FILE = self._orig_path
        os.unlink(self.path)

    def test_load_empty_returns_list(self):
        result = self.mod._load()
        self.assertIsInstance(result, list)

    def test_save_and_load(self):
        cmds = ["ls", "cd core", "help"]
        self.mod._save(cmds)
        result = self.mod._load()
        self.assertEqual(result, cmds)

    def test_load_invalid_json(self):
        with open(self.path, "w") as f:
            f.write("BROKEN")
        self.assertEqual(self.mod._load(), [])

    def test_max_entries_limit(self):
        """Historia nie moze przekroczyc limitu max_entries."""
        big = [f"cmd_{i}" for i in range(600)]
        self.mod._save(big)
        result = self.mod._load()
        self.assertLessEqual(len(result), 500)


# ===========================================================================
#  core.trash  --  ensure_trash / TRASH_DIR
# ===========================================================================

class TestTrash(unittest.TestCase):
    """Modul trash."""

    def setUp(self):
        import core.trash as trash_mod
        self.mod = trash_mod
        self._orig_dir = trash_mod.TRASH_DIR
        self.tmp_trash = os.path.join(tempfile.mkdtemp(), ".trash_test")
        trash_mod.TRASH_DIR = self.tmp_trash

    def tearDown(self):
        import shutil
        self.mod.TRASH_DIR = self._orig_dir
        shutil.rmtree(self.tmp_trash, ignore_errors=True)

    def test_ensure_trash_creates_dir(self):
        self.assertFalse(os.path.isdir(self.tmp_trash))
        self.mod.ensure_trash()
        self.assertTrue(os.path.isdir(self.tmp_trash))

    def test_ensure_trash_idempotent(self):
        self.mod.ensure_trash()
        self.mod.ensure_trash()  # nie powinno rzucac
        self.assertTrue(os.path.isdir(self.tmp_trash))


# ===========================================================================
#  core.command  --  podstawowe operacje na plikach
# ===========================================================================

class TestCommandModule(unittest.TestCase):
    """Podstawowe komendy plikowe z core.command."""

    def setUp(self):
        from core import TerminalX
        import core.command as command_mod
        import core.trash as trash_mod
        import core.config as config_mod

        self.command_mod = command_mod
        self.trash_mod = trash_mod
        self.config_mod = config_mod
        self.terminal = TerminalX(lang="pl")

        self.tmp_root = tempfile.mkdtemp(prefix="tx_cmd_")
        self.tmp_trash = os.path.join(self.tmp_root, ".trash")
        self.orig_cwd = os.getcwd()
        self.orig_cmd_trash = command_mod.TRASH_DIR
        self.orig_mod_trash = trash_mod.TRASH_DIR
        self.orig_store = dict(getattr(config_mod, "_store", {}))

        os.chdir(self.tmp_root)
        command_mod.TRASH_DIR = self.tmp_trash
        trash_mod.TRASH_DIR = self.tmp_trash
        config_mod._store = config_mod._defaults()
        config_mod._store["confirm.rm"] = False
        config_mod._store["confirm.overwrite"] = False

        command_mod.setup(self.terminal)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        self.command_mod.TRASH_DIR = self.orig_cmd_trash
        self.trash_mod.TRASH_DIR = self.orig_mod_trash
        self.config_mod._store = self.orig_store
        shutil.rmtree(self.tmp_root, ignore_errors=True)

    def test_registers_basic_file_commands(self):
        for name in ("mkdir", "touch", "cp", "mv", "cat", "del"):
            self.assertIn(name, self.terminal.commands)

    def test_mkdir_touch_and_cat(self):
        self.terminal.commands["mkdir"]["func"](["docs"])
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_root, "docs")))

        self.terminal.commands["touch"]["func"](["docs\\note.txt"])
        note_path = os.path.join(self.tmp_root, "docs", "note.txt")
        self.assertTrue(os.path.isfile(note_path))

        with open(note_path, "w", encoding="utf-8") as f:
            f.write("hello from TerminalX")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.terminal.commands["cat"]["func"](["docs\\note.txt"])
        self.assertIn("hello from TerminalX", buf.getvalue())

    def test_cp_and_mv(self):
        src = os.path.join(self.tmp_root, "src.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("abc")

        self.terminal.commands["cp"]["func"](["src.txt", "copy.txt"])
        copy_path = os.path.join(self.tmp_root, "copy.txt")
        self.assertTrue(os.path.isfile(copy_path))
        with open(copy_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "abc")

        self.terminal.commands["mv"]["func"](["copy.txt", "moved.txt"])
        moved_path = os.path.join(self.tmp_root, "moved.txt")
        self.assertFalse(os.path.exists(copy_path))
        self.assertTrue(os.path.isfile(moved_path))

    def test_del_moves_file_to_ecosystem_trash(self):
        victim = os.path.join(self.tmp_root, "victim.txt")
        with open(victim, "w", encoding="utf-8") as f:
            f.write("delete me")

        self.terminal.commands["del"]["func"](["victim.txt"])

        self.assertFalse(os.path.exists(victim))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp_trash, "victim.txt")))


# ===========================================================================
#  core.config  --  get / set
# ===========================================================================

class TestConfig(unittest.TestCase):
    """Modul config (get/set z dot-notation)."""

    def setUp(self):
        from core import config
        self.cfg = config

    def test_get_existing_key(self):
        """get() zwraca wartosc dla klucza istniejacego w schemacie."""
        val = self.cfg.get("prompt.symbol", "> ")
        self.assertIsNotNone(val)

    def test_get_missing_key_returns_default(self):
        result = self.cfg.get("nonexistent.key.xyz", "DEFAULT")
        self.assertEqual(result, "DEFAULT")

    def test_get_returns_bool_for_bool_keys(self):
        val = self.cfg.get("on_startup.clear", False)
        self.assertIsInstance(val, bool)

    def test_color_code_returns_string_or_none(self):
        result = self.cfg.color_code("yellow")
        self.assertTrue(result is None or isinstance(result, str))


# ===========================================================================
#  core.lang  --  load_saved_lang
# ===========================================================================

class TestLang(unittest.TestCase):
    """Modul lang (ladowanie zapisanego jezyka)."""

    def setUp(self):
        from core import lang as lang_mod
        self.mod = lang_mod

    def test_load_saved_lang_returns_str_or_none(self):
        result = self.mod.load_saved_lang()
        self.assertTrue(result is None or isinstance(result, str))

    def test_load_saved_lang_valid_code(self):
        result = self.mod.load_saved_lang()
        if result is not None:
            self.assertIn(result, ("pl", "en"))


# ===========================================================================
#  core.cache  --  obecnosc API
# ===========================================================================

class TestCache(unittest.TestCase):
    """Modul cache."""

    def setUp(self):
        from core import cache as cache_mod
        self.mod = cache_mod

    def test_module_importable(self):
        self.assertIsNotNone(self.mod)

    def test_has_expected_symbols(self):
        """cache.py powinien zawierac funkcje _get/_set lub setup."""
        api = dir(self.mod)
        has_api = any(x in api for x in (
            "_get", "_set", "_read_index", "_write_index", "get", "set", "setup"
        ))
        self.assertTrue(has_api, "core.cache: brak oczekiwanych symboli API")


# ===========================================================================
#  core.env  --  srodowisko zmiennych
# ===========================================================================

class TestEnv(unittest.TestCase):
    """Modul env."""

    def setUp(self):
        from core import env as env_mod
        self.mod = env_mod

    def test_module_importable(self):
        self.assertIsNotNone(self.mod)

    def test_has_setup(self):
        self.assertTrue(
            hasattr(self.mod, "setup"),
            "core.env: brak funkcji setup(terminal)"
        )


# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
