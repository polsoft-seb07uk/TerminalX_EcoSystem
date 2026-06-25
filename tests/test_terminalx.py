"""Unit tests for TerminalX bootstrapper + REPL core.

Tests:
  - TerminalX instance creation
  - register_command + commands dict
  - _dispatch (normal + capture mode)
  - _run_line (simple, pipe, unknown cmd, exit)
  - load_modules / unload_module
  - t() translations

Author  : Sebastian Januchowski
Brand   : polsoft.ITS(TM)
Version : 1.0.0
"""

import io
import sys
import os
import unittest
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import TerminalX, load_modules, unload_module


# ---------------------------------------------------------------------------
#  Fixture
# ---------------------------------------------------------------------------

def _make_terminal(lang: str = "en") -> TerminalX:
    """Tworzy instancje TerminalX bez uruchamiania modulow."""
    return TerminalX(lang=lang)


# ===========================================================================
#  Inicjalizacja
# ===========================================================================

class TestTerminalXInit(unittest.TestCase):
    """Tworzenie instancji TerminalX."""

    def test_instance_created(self):
        t = _make_terminal()
        self.assertIsInstance(t, TerminalX)

    def test_commands_dict_empty_on_init(self):
        t = _make_terminal()
        self.assertIsInstance(t.commands, dict)
        self.assertEqual(len(t.commands), 0)

    def test_loaded_modules_empty_on_init(self):
        t = _make_terminal()
        self.assertIsInstance(t.loaded_modules, dict)
        self.assertEqual(len(t.loaded_modules), 0)

    def test_colors_attribute_exists(self):
        t = _make_terminal()
        self.assertIsNotNone(t.colors)

    def test_lang_attribute_is_string(self):
        t = _make_terminal()
        self.assertIsInstance(t.lang, str)

    def test_t_callable(self):
        t = _make_terminal()
        self.assertTrue(callable(t.t))

    def test_t_returns_string(self):
        t = _make_terminal()
        result = t.t("startup_msg")
        self.assertIsInstance(result, str)

    def test_default_lang_pl(self):
        t = TerminalX(lang="pl")
        self.assertIn(t.lang, ("pl", "en"))


# ===========================================================================
#  register_command
# ===========================================================================

class TestRegisterCommand(unittest.TestCase):
    """Rejestrowanie polecen."""

    def setUp(self):
        self.t = _make_terminal()

    def test_register_adds_command(self):
        fn = MagicMock()
        self.t.register_command("test_cmd", fn, description="opis")
        self.assertIn("test_cmd", self.t.commands)

    def test_registered_func_is_correct(self):
        fn = MagicMock()
        self.t.register_command("mycmd", fn)
        self.assertIs(self.t.commands["mycmd"]["func"], fn)

    def test_registered_description(self):
        fn = MagicMock()
        self.t.register_command("mycmd", fn, description="Test opis")
        self.assertEqual(self.t.commands["mycmd"]["description"], "Test opis")

    def test_registered_default_category(self):
        fn = MagicMock()
        self.t.register_command("mycmd", fn)
        self.assertIn("category", self.t.commands["mycmd"])
        self.assertIsInstance(self.t.commands["mycmd"]["category"], str)

    def test_register_multiple_commands(self):
        for name in ("a", "b", "c"):
            self.t.register_command(name, MagicMock())
        self.assertEqual(len(self.t.commands), 3)

    def test_overwrite_command(self):
        fn1, fn2 = MagicMock(), MagicMock()
        self.t.register_command("cmd", fn1)
        self.t.register_command("cmd", fn2)
        self.assertIs(self.t.commands["cmd"]["func"], fn2)


# ===========================================================================
#  _dispatch
# ===========================================================================

class TestDispatch(unittest.TestCase):
    """Metoda _dispatch."""

    def setUp(self):
        self.t = _make_terminal()

    def _register(self, name, side_effect=None, output=None):
        if output is not None:
            def fn(args):
                print(output)
        else:
            fn = MagicMock(side_effect=side_effect)
        self.t.register_command(name, fn)
        return fn

    # -- normalne wykonanie --------------------------------------------------

    def test_dispatch_calls_function(self):
        fn = MagicMock()
        self.t.register_command("echo", fn)
        self.t._dispatch("echo", ["hello"])
        fn.assert_called_once_with(["hello"])

    def test_dispatch_unknown_command_returns_none(self):
        result = self.t._dispatch("cmd_unknown_xyz", [])
        self.assertIsNone(result)

    def test_dispatch_exception_does_not_propagate(self):
        self._register("bad", side_effect=RuntimeError("boom"))
        try:
            self.t._dispatch("bad", [])
        except Exception as exc:
            self.fail(f"_dispatch propagated exception: {exc}")

    # -- capture mode --------------------------------------------------------

    def test_dispatch_capture_returns_list(self):
        self._register("echo", output="line1")
        result = self.t._dispatch("echo", [], input_lines=[])
        self.assertIsInstance(result, list)

    def test_dispatch_capture_output(self):
        self._register("greet", output="hello")
        result = self.t._dispatch("greet", [], input_lines=[])
        self.assertIn("hello", result)

    def test_dispatch_capture_unknown_returns_none(self):
        result = self.t._dispatch("cmd_unknown_xyz", [], input_lines=[])
        self.assertIsNone(result)

    def test_dispatch_capture_exception_returns_empty_list(self):
        self._register("bad2", side_effect=ValueError("oops"))
        result = self.t._dispatch("bad2", [], input_lines=[])
        self.assertIsInstance(result, list)

    def test_dispatch_injects_input_lines_as_args(self):
        received = []

        def fn(args):
            received.extend(args)

        self.t.register_command("collect", fn)
        self.t._dispatch("collect", [], input_lines=["line_a", "line_b"])
        self.assertIn("line_a", received)
        self.assertIn("line_b", received)


# ===========================================================================
#  _run_line
# ===========================================================================

class TestRunLine(unittest.TestCase):
    """Parsowanie i wykonanie linii polecen."""

    def setUp(self):
        self.t = _make_terminal()

    def _reg(self, name, output=None):
        if output is not None:
            def fn(args):
                print(output)
            self.t.register_command(name, fn)
        else:
            fn = MagicMock()
            self.t.register_command(name, fn)
            return fn

    # -- podstawowe ----------------------------------------------------------

    def test_empty_line_does_nothing(self):
        self.t._run_line("")

    def test_whitespace_only_does_nothing(self):
        self.t._run_line("   ")

    def test_simple_command_called(self):
        fn = self._reg("cmd")
        self.t._run_line("cmd")
        fn.assert_called_once()

    def test_command_with_args(self):
        fn = self._reg("greet")
        self.t._run_line("greet Alice Bob")
        fn.assert_called_once_with(["Alice", "Bob"])

    def test_unknown_command_no_crash(self):
        # Polskie znaki nie moga byc w komunikacie bledu przez charmap na Windows
        try:
            self.t._run_line("cmd_unknown_ascii_only_xyz")
        except UnicodeEncodeError:
            pass  # akceptowalne na Windows bez UTF-8 stdout
        except Exception as exc:
            self.fail(f"_run_line raised unexpected exception: {exc}")

    # -- exit ----------------------------------------------------------------

    def test_exit_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            self.t._run_line("exit")

    # -- pipe ----------------------------------------------------------------

    def test_pipe_two_commands(self):
        self._reg("src", output="data_line")
        fn2 = MagicMock()
        self.t.register_command("sink", fn2)
        self.t._run_line("src | sink")
        fn2.assert_called_once()

    def test_pipe_capture_then_inject(self):
        """_dispatch capture mode: wyjscie src trafia do sink przez input_lines."""
        self._reg("produce", output="hello_world")
        captured = self.t._dispatch("produce", [], input_lines=[])
        self.assertIsInstance(captured, list)
        self.assertIn("hello_world", captured)

        received = []

        def sink(args):
            received.extend(args)

        self.t.register_command("sink", sink)
        self.t._dispatch("sink", [], input_lines=captured)
        self.assertIn("hello_world", received)

    def test_pipe_chain_three_no_crash(self):
        """Pipe trojki polecen nie moze rzucic wyjatku."""
        self._reg("a", output="line")
        self._reg("b", output="processed")
        fn_c = MagicMock()
        self.t.register_command("c", fn_c)
        try:
            self.t._run_line("a | b | c")
        except Exception as exc:
            self.fail(f"Pipe chain raised exception: {exc}")

    # -- historia ------------------------------------------------------------

    def test_history_record_called_if_present(self):
        recorder = MagicMock()
        self.t._history_record = recorder
        fn = self._reg("cmd")
        self.t._run_line("cmd arg1")
        recorder.assert_called_once_with("cmd arg1")


# ===========================================================================
#  load_modules / unload_module
# ===========================================================================

class TestModuleLoading(unittest.TestCase):
    """Dynamiczne ladowanie i rozladowywanie modulow."""

    def test_load_modules_returns_dict(self):
        t = _make_terminal()
        loaded = load_modules(t)
        self.assertIsInstance(loaded, dict)

    def test_load_modules_populates_commands(self):
        t = _make_terminal()
        load_modules(t)
        self.assertGreater(len(t.commands), 0)

    def test_load_modules_includes_known_commands(self):
        t = _make_terminal()
        load_modules(t)
        expected = {"ls", "cd", "help", "history", "alias", "trash"}
        found = expected & set(t.commands.keys())
        self.assertTrue(
            len(found) > 0,
            f"None of {expected} found in commands"
        )

    def test_unload_module_removes_from_dict(self):
        t = _make_terminal()
        loaded = load_modules(t)
        if not loaded:
            self.skipTest("No modules loaded")
        name = next(iter(loaded))
        unload_module(name, loaded, t)
        self.assertNotIn(name, loaded)

    def test_unload_unknown_module_no_crash(self):
        t = _make_terminal()
        loaded = {}
        try:
            unload_module("nonexistent_module", loaded, t)
        except Exception as exc:
            self.fail(f"unload_module raised exception: {exc}")

    def test_double_load_no_crash(self):
        """Dwukrotne zaladowanie nie powinno rzucac."""
        t = _make_terminal()
        try:
            load_modules(t)
            load_modules(t)
        except Exception as exc:
            self.fail(f"Double load raised: {exc}")


# ===========================================================================
#  t() -- tlumaczenia
# ===========================================================================

class TestTranslations(unittest.TestCase):
    """Mechanizm tlumaczen t()."""

    def test_t_known_key_en(self):
        t = TerminalX(lang="en")
        result = t.t("startup_msg")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "")

    def test_t_known_key_pl(self):
        t = TerminalX(lang="pl")
        result = t.t("startup_msg")
        self.assertIsInstance(result, str)

    def test_t_missing_key_returns_key(self):
        t = _make_terminal()
        key = "key_that_does_not_exist_xyz"
        result = t.t(key)
        self.assertEqual(result, key)

    def test_t_with_kwargs_formats(self):
        t = _make_terminal()
        result = t.t("module_load_error", name="mymod", exc="err")
        self.assertIsInstance(result, str)


# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
