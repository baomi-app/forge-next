import os
import tempfile
import unittest

from forge.changes import ChangeSet
from forge.tool_capabilities import ToolCapabilities
from forge.tools import change_summary, revert_changes, review_changes, registry


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

    def test_change_tools_use_runtime_transaction_state(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            runtime = ToolCapabilities(workspace_dir=workspace, session=FakeSession(ChangeSet(workspace)))
            self._write_file(workspace, "app.py", "VALUE = 2\n")

            summary = change_summary(include_diff=False, runtime=runtime)
            result = revert_changes(runtime=runtime)

        self.assertIn("modified: app.py", summary)
        self.assertIn("Reverted 1 file change(s)", result)

    def test_change_tools_use_registry_runtime_state(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            session = FakeSession(ChangeSet(workspace))
            runtime = ToolCapabilities(workspace_dir=workspace, session=session)
            self._write_file(workspace, "app.py", "VALUE = 2\n")

            summary = registry.execute(
                "change_summary",
                {"include_diff": False},
                runtime=runtime,
            )
            result = registry.execute("revert_changes", {}, runtime=runtime)

        self.assertIn("modified: app.py", summary)
        self.assertIn("Reverted 1 file change(s)", result)

    def test_review_changes_blocks_empty_transactions(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            runtime = ToolCapabilities(workspace_dir=workspace, session=FakeSession(ChangeSet(workspace)))

            review = review_changes(runtime=runtime)

        self.assertIn("Status: BLOCK", review)
        self.assertIn("No transaction changes were found", review)

    def test_review_changes_blocks_local_editor_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            change_set = ChangeSet(workspace)
            self._write_file(workspace, ".vscode/settings.json", "{}\n")
            runtime = ToolCapabilities(workspace_dir=workspace, session=FakeSession(change_set))

            review = review_changes(runtime=runtime)

        self.assertIn("Status: BLOCK", review)
        self.assertIn(".vscode/settings.json", review)

    def test_review_changes_warns_when_code_lacks_test_changes(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            runtime = ToolCapabilities(workspace_dir=workspace, session=FakeSession(ChangeSet(workspace)))
            self._write_file(workspace, "app.py", "VALUE = 2\n")

            review = review_changes(task_goal="update app value", runtime=runtime)

        self.assertIn("Status: WARN", review)
        self.assertIn("Code changed but no test files changed", review)
        self.assertIn("suggested message: feat: update app value", review)

    def test_review_changes_passes_code_with_tests(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            runtime = ToolCapabilities(workspace_dir=workspace, session=FakeSession(ChangeSet(workspace)))
            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 2\n")

            review = review_changes(runtime=runtime)

        self.assertIn("Status: PASS", review)
        self.assertIn("atomic candidate", review)

    def test_transaction_tools_are_registered(self):
        self.assertIn("change_summary", registry.tools)
        self.assertIn("revert_changes", registry.tools)
        self.assertIn("review_changes", registry.tools)

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
