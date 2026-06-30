import os
import tempfile
import unittest

from forge.changes import ChangeSet
from forge.tools import change_summary, revert_changes, registry


class FakeRunner:
    def __init__(self, change_set):
        self.change_set = change_set


class FakeSession:
    def __init__(self, change_set):
        self.change_set = change_set


class TestChangeSet(unittest.TestCase):
    def test_tracks_added_modified_and_deleted_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "keep.py", "VALUE = 1\n")
            self._write_file(workspace, "remove.py", "gone = True\n")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "keep.py", "VALUE = 2\n")
            self._write_file(workspace, "new.py", "created = True\n")
            os.remove(os.path.join(workspace, "remove.py"))

            changes = [(change.path, change.status) for change in change_set.changes()]

        self.assertEqual(
            changes,
            [
                ("new.py", "added"),
                ("remove.py", "deleted"),
                ("keep.py", "modified"),
            ],
        )

    def test_formats_diff_and_summary(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            summary = change_set.summary()
            diff = change_set.diff()

        self.assertIn("modified: app.py", summary)
        self.assertIn("--- a/app.py", diff)
        self.assertIn("+++ b/app.py", diff)
        self.assertIn("-VALUE = 1", diff)
        self.assertIn("+VALUE = 2", diff)

    def test_reverts_workspace_and_refreshes_baseline(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "new.py", "created = True\n")
            result = change_set.revert()

            with open(os.path.join(workspace, "app.py"), "r", encoding="utf-8") as f:
                restored = f.read()
            new_exists = os.path.exists(os.path.join(workspace, "new.py"))
            remaining_changes = change_set.changes()

        self.assertIn("Reverted 2 file change(s)", result)
        self.assertEqual(restored, "VALUE = 1\n")
        self.assertFalse(new_exists)
        self.assertEqual(remaining_changes, [])

    def test_revert_removes_empty_directories_created_for_added_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "new_pkg/module.py", "VALUE = 1\n")
            change_set.revert()

            directory_exists = os.path.exists(os.path.join(workspace, "new_pkg"))

        self.assertFalse(directory_exists)

    def test_serialized_baseline_survives_resume(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            original = ChangeSet(workspace)
            self._write_file(workspace, "app.py", "VALUE = 2\n")

            restored = ChangeSet(workspace)
            restored.restore_from_dict(original.to_dict())
            changes = [(change.path, change.status) for change in restored.changes()]
            restored.revert()

            with open(os.path.join(workspace, "app.py"), "r", encoding="utf-8") as f:
                content = f.read()

        self.assertEqual(changes, [("app.py", "modified")])
        self.assertEqual(content, "VALUE = 1\n")

    def test_ignores_framework_checkpoint_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "checkpoint.json", "{}\n")
            self._write_file(workspace, "plan_checkpoint.json", "{}\n")

            changes = change_set.changes()

        self.assertEqual(changes, [])

    def test_change_tools_use_runner_transaction_state(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            runner = FakeRunner(ChangeSet(workspace))
            self._write_file(workspace, "app.py", "VALUE = 2\n")

            summary = change_summary(include_diff=False, runner=runner)
            result = revert_changes(runner=runner)

        self.assertIn("modified: app.py", summary)
        self.assertIn("Reverted 1 file change(s)", result)

    def test_change_tools_use_session_transaction_state(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            session = FakeSession(ChangeSet(workspace))
            self._write_file(workspace, "app.py", "VALUE = 2\n")

            summary = registry.execute(
                "change_summary",
                {"include_diff": False},
                session=session,
            )
            result = registry.execute("revert_changes", {}, session=session)

        self.assertIn("modified: app.py", summary)
        self.assertIn("Reverted 1 file change(s)", result)

    def test_transaction_tools_are_registered(self):
        self.assertIn("change_summary", registry.tools)
        self.assertIn("revert_changes", registry.tools)

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
