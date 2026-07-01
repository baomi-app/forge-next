import os
import tempfile
import unittest

from forge.changes import ChangeSet, FileChange
from forge.focused import FocusedTestSelector
from forge.tools import registry, suggest_tests


class FakeRunner:
    def __init__(self, change_set):
        self.change_set = change_set


class TestFocusedTestSelector(unittest.TestCase):
    def test_finds_mirrored_test_under_tests_directory(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "src/billing/invoice.py", "def total():\n    return 1\n")
            self._write_file(workspace, "tests/billing/test_invoice.py", "")
            selector = FocusedTestSelector(workspace)

            plan = selector.select([FileChange("src/billing/invoice.py", "modified")])

        self.assertEqual(len(plan.checks), 1)
        self.assertEqual(plan.checks[0].command, "python -m unittest tests.billing.test_invoice")
        self.assertIn("Focused tests are suggestions", plan.notes[0])

    def test_suggests_changed_test_file_directly(self):
        selector = FocusedTestSelector(".")

        plan = selector.select([FileChange("tests/test_changes.py", "modified")])

        self.assertEqual(plan.checks[0].command, "python -m unittest tests.test_changes")

    def test_suggests_changed_demo_script(self):
        selector = FocusedTestSelector(".")

        plan = selector.select([FileChange("examples/demo_review.py", "modified")])

        self.assertEqual(plan.checks[0].command, "python examples/demo_review.py")
        self.assertEqual(plan.checks[0].category, "demo")

    def test_docs_only_changes_need_no_focused_tests(self):
        selector = FocusedTestSelector(".")

        plan = selector.select([FileChange("README.md", "modified")])

        self.assertEqual(plan.checks, [])
        self.assertIn("Only documentation", plan.notes[0])

    def test_falls_back_to_unittest_discovery_for_unmapped_code(self):
        selector = FocusedTestSelector(".")

        plan = selector.select([FileChange("custom/module.py", "modified")])

        self.assertEqual(plan.checks[0].command, "python -m unittest discover")

    def test_suggest_tests_tool_uses_transaction_state(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "")
            change_set = ChangeSet(workspace)
            self._write_file(workspace, "app.py", "VALUE = 2\n")
            runner = FakeRunner(change_set)

            output = suggest_tests(runner=runner)

        self.assertIn("Focused verification suggestions", output)
        self.assertIn("python -m unittest test_app", output)

    def test_suggest_tests_is_registered(self):
        self.assertIn("suggest_tests", registry.tools)

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
