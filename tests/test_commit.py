import os
import subprocess
import tempfile
import unittest

from forge.changes import ChangeSet
from forge.commit import CommitOrchestrator, CommitPlanner, GitStateInspector
from forge.llm_decisions import LLMCommitFileDecision, LLMCommitPlanDecision
from forge.tool_capabilities import ToolCapabilities
from forge.tools import commit_changes, plan_commit, registry


class FakeSession:
    def __init__(self, change_set):
        self.change_set = change_set


class FakeCommitService:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def plan_commit(self, task_goal, changes, diff):
        self.calls.append((task_goal, changes, diff))
        return self.decision


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
            service = self._commit_service(
                message="feat: add value update",
                files=["README.md", "app.py", "test_app.py"],
            )
            plan = CommitPlanner(decision_service=service).plan(change_set, task_goal="add value update")

        self.assertEqual(plan.status, "READY")
        self.assertEqual(plan.message, "feat: add value update")
        self.assertEqual([file.path for file in plan.files], ["README.md", "app.py", "test_app.py"])
        self.assertEqual(plan.risks, [])
        self.assertEqual(service.calls[0][0], "add value update")

    def test_review_plan_uses_llm_risks(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            service = self._commit_service(
                status="REVIEW",
                message="feat: update app value",
                files=["app.py"],
                risks=["LLM says test coverage needs confirmation."],
                next_steps=["Run focused tests before staging."],
            )
            rendered = CommitPlanner(decision_service=service).format_plan(change_set)

        self.assertIn("Status: REVIEW", rendered)
        self.assertIn("test coverage needs confirmation", rendered)

    def test_blocks_missing_llm_commit_planning(self):
        with tempfile.TemporaryDirectory() as workspace:
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 1\n")
            plan = CommitPlanner().plan(change_set)

        self.assertEqual(plan.status, "BLOCK")
        self.assertIn("LLM commit planning is not configured", plan.risks[0])

    def test_blocks_empty_transaction(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace)

            plan = CommitPlanner().plan(change_set)

        self.assertEqual(plan.status, "BLOCK")
        self.assertIn("No transaction changes", plan.risks[0])

    def test_filters_file_outside_current_transaction(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace)

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            service = self._commit_service(
                message="feat: update app value",
                files=["app.py", "unrelated.txt"],
            )
            plan = CommitPlanner(decision_service=service).plan(change_set)

        self.assertEqual(plan.status, "BLOCK")
        self.assertIn("outside the current transaction", "\n".join(plan.risks))

    def test_plan_commit_tool_uses_transaction_state(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            self._write_file(workspace, "README.md", "old\n")
            service = self._commit_service(
                message="feat: update app value",
                files=["README.md", "app.py", "test_app.py"],
            )
            runtime = ToolCapabilities(
                workspace_dir=workspace,
                session=FakeSession(ChangeSet(workspace)),
                decision_service=service,
            )

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 2\n")
            self._write_file(workspace, "README.md", "new\n")
            output = plan_commit(task_goal="update app value", runtime=runtime)

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
            service = self._commit_service(
                message="feat: update app value",
                files=["README.md", "app.py", "test_app.py"],
            )
            result = CommitOrchestrator(decision_service=service).commit(change_set, task_goal="update app value")
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
            service = self._commit_service(
                message="feat: update app value",
                files=["README.md", "app.py", "test_app.py"],
            )
            result = CommitOrchestrator(decision_service=service).commit(change_set, task_goal="update app value")

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
            service = self._commit_service(
                status="REVIEW",
                message="feat: update app value",
                files=["app.py"],
                risks=["LLM requested human review before commit."],
                next_steps=["Review before staging."],
            )
            result = CommitOrchestrator(decision_service=service).commit(change_set, task_goal="update app value")
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
            service = self._commit_service(
                message="feat: update app value",
                files=["README.md", "app.py", "test_app.py"],
            )
            runtime = ToolCapabilities(
                workspace_dir=workspace,
                session=FakeSession(ChangeSet(workspace)),
                decision_service=service,
            )

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 2\n")
            self._write_file(workspace, "README.md", "new\n")
            output = commit_changes(task_goal="update app value", runtime=runtime)

        self.assertIn("Commit orchestration result", output)
        self.assertIn("Status: COMMITTED", output)
        self.assertIn("Commit message: feat: update app value", output)

    def _commit_service(
        self,
        message="feat: update app value",
        files=None,
        status="READY",
        risks=None,
        next_steps=None,
    ):
        files = files or ["app.py"]
        risks = risks or []
        next_steps = next_steps or ["Stage the LLM-approved files.", "Commit with the suggested message."]
        return FakeCommitService(
            LLMCommitPlanDecision(
                status=status,
                message=message,
                files=[
                    LLMCommitFileDecision(path=path, action="stage", reason="LLM selected this file.")
                    for path in files
                ],
                risks=risks,
                next_steps=next_steps,
            )
        )

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
