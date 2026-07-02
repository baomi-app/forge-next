import os
import subprocess
import tempfile
import unittest

from forge.changes import ChangeSet
from forge.commit import CommitOrchestrator, CommitPlanner, GitStateInspector
from forge.tools import commit_changes, plan_commit, registry


class FakeRunner:
    def __init__(self, change_set):
        self.change_set = change_set


class TestCommitPlanner(unittest.TestCase):
    def test_ready_plan_for_code_test_docs_transaction(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            self._write_file(workspace, "README.md", "old\n")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 2\n")
            self._write_file(workspace, "README.md", "new\n")
            plan = CommitPlanner().plan(change_set, task_goal="add value update")

        self.assertEqual(plan.status, "READY")
        self.assertEqual(plan.message, "feat: add value update")
        self.assertEqual([file.path for file in plan.files], ["README.md", "app.py", "test_app.py"])
        self.assertEqual(plan.risks, [])

    def test_review_plan_warns_for_code_without_tests_or_docs(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            rendered = CommitPlanner().format_plan(change_set)

        self.assertIn("Status: REVIEW", rendered)
        self.assertIn("Code changes have no staged test changes", rendered)
        self.assertIn("Runtime behavior changed without staged docs or examples", rendered)

    def test_blocks_generated_or_local_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            change_set = ChangeSet(workspace)

            self._write_file(workspace, ".vscode/settings.json", "{}\n")
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            plan = CommitPlanner().plan(change_set)

        self.assertEqual(plan.status, "BLOCK")
        excluded = [file for file in plan.files if file.action == "exclude"]
        self.assertEqual(excluded[0].path, ".vscode/settings.json")
        self.assertIn("Excluded files must be removed", plan.risks[0])

    def test_blocks_empty_transaction(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace)

            plan = CommitPlanner().plan(change_set)

        self.assertEqual(plan.status, "BLOCK")
        self.assertIn("No transaction changes", plan.risks[0])

    def test_docs_only_commit_message(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "README.md", "old\n")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "README.md", "new\n")
            plan = CommitPlanner().plan(change_set)

        self.assertEqual(plan.status, "READY")
        self.assertEqual(plan.message, "docs: update documentation")

    def test_plan_commit_tool_uses_transaction_state(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            self._write_file(workspace, "README.md", "old\n")
            runner = FakeRunner(ChangeSet(workspace))

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 2\n")
            self._write_file(workspace, "README.md", "new\n")
            output = plan_commit(task_goal="update app value", runner=runner)

        self.assertIn("Commit orchestration plan", output)
        self.assertIn("Status: READY", output)
        self.assertIn("Suggested commit message: feat: update app value", output)

    def test_plan_commit_is_registered(self):
        self.assertIn("plan_commit", registry.tools)
        self.assertIn("commit_changes", registry.tools)

    def test_inspects_git_index_and_worktree_state(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._git(workspace, "add", "app.py")
            self._git(workspace, "commit", "-m", "init")

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "notes.txt", "new\n")
            self._git(workspace, "add", "notes.txt")
            state = GitStateInspector().inspect(workspace)

        self.assertTrue(state.is_repo)
        by_path = {file.path: file for file in state.files}
        self.assertEqual(by_path["app.py"].worktree_status, "M")
        self.assertEqual(by_path["notes.txt"].index_status, "A")

    def test_commit_orchestrator_stages_and_commits_planned_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            self._write_file(workspace, "README.md", "old\n")
            self._git(workspace, "add", ".")
            self._git(workspace, "commit", "-m", "init")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 2\n")
            self._write_file(workspace, "README.md", "new\n")
            result = CommitOrchestrator().commit(change_set, task_goal="update app value")
            last_message = self._git(workspace, "log", "-1", "--pretty=%s").stdout.strip()
            status = self._git(workspace, "status", "--short").stdout.strip()
            remaining_changes = change_set.changes()

        self.assertEqual(result.status, "COMMITTED")
        self.assertEqual(result.message, "feat: update app value")
        self.assertEqual(last_message, "feat: update app value")
        self.assertEqual(result.committed_files, ["README.md", "app.py", "test_app.py"])
        self.assertEqual(status, "")
        self.assertEqual(remaining_changes, [])

    def test_commit_orchestrator_blocks_existing_staged_files_outside_plan(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            self._write_file(workspace, "README.md", "old\n")
            self._write_file(workspace, "unrelated.txt", "old\n")
            self._git(workspace, "add", ".")
            self._git(workspace, "commit", "-m", "init")
            self._write_file(workspace, "unrelated.txt", "already staged\n")
            self._git(workspace, "add", "unrelated.txt")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 2\n")
            self._write_file(workspace, "README.md", "new\n")
            result = CommitOrchestrator().commit(change_set, task_goal="update app value")

        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("Git index already contains files outside this commit plan.", result.notes)
        self.assertIn("unrelated.txt", result.notes)

    def test_commit_orchestrator_blocks_review_plan_by_default(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._git(workspace, "add", ".")
            self._git(workspace, "commit", "-m", "init")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            result = CommitOrchestrator().commit(change_set, task_goal="update app value")
            status = self._git(workspace, "status", "--short").stdout.strip()

        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("Commit plan needs review before execution.", result.notes)
        self.assertIn("M app.py", status)

    def test_commit_changes_tool_creates_commit(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            self._write_file(workspace, "README.md", "old\n")
            self._git(workspace, "add", ".")
            self._git(workspace, "commit", "-m", "init")
            runner = FakeRunner(ChangeSet(workspace))

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 2\n")
            self._write_file(workspace, "README.md", "new\n")
            output = commit_changes(task_goal="update app value", runner=runner)

        self.assertIn("Commit orchestration result", output)
        self.assertIn("Status: COMMITTED", output)
        self.assertIn("Commit message: feat: update app value", output)

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _init_git_repo(self, workspace):
        self._git(workspace, "init")
        self._git(workspace, "config", "user.email", "forge@example.com")
        self._git(workspace, "config", "user.name", "Forge Test")

    def _git(self, workspace, *args):
        result = subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        return result


if __name__ == "__main__":
    unittest.main()
