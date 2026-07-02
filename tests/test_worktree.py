import os
import subprocess
import tempfile
import unittest

from forge.tool_capabilities import ToolCapabilities
from forge.tools import create_worktree_branch, inspect_worktrees, plan_worktree_branch, registry, remove_worktree
from forge.worktree import WorktreeManager


class TestWorktreeManager(unittest.TestCase):
    def test_plans_branch_worktree_with_default_sibling_path(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)

            output = WorktreeManager().format_plan(workspace, "codex/test-feature")

        self.assertIn("Status: READY", output)
        self.assertIn("Branch: codex/test-feature", output)
        self.assertIn("Path:", output)
        self.assertIn("Base ref: HEAD", output)

    def test_creates_and_removes_branch_worktree(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = os.path.join(temp_root, "repo")
            worktree_path = os.path.join(temp_root, "repo-isolated")
            os.makedirs(workspace)
            self._init_git_repo(workspace)

            created = WorktreeManager().create_branch(
                workspace_dir=workspace,
                branch_name="codex/isolated",
                worktree_path=worktree_path,
            )
            state = WorktreeManager().inspect(workspace)
            removed = WorktreeManager().remove_worktree(workspace, worktree_path)

        self.assertEqual(created.status, "CREATED")
        self.assertEqual(created.branch, "codex/isolated")
        self.assertTrue(any(worktree.path == os.path.realpath(worktree_path) for worktree in state.worktrees))
        self.assertEqual(removed.status, "REMOVED")

    def test_blocks_invalid_branch_names(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)

            result = WorktreeManager().plan_branch(workspace, "../bad")

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("Branch name is required", result.notes[0])

    def test_tools_use_runtime_workspace(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = os.path.join(temp_root, "repo")
            worktree_path = os.path.join(temp_root, "repo-tool")
            os.makedirs(workspace)
            self._init_git_repo(workspace)
            runtime = ToolCapabilities(workspace_dir=workspace)

            plan = plan_worktree_branch(
                branch_name="codex/tool",
                worktree_path=worktree_path,
                runtime=runtime,
            )
            created = create_worktree_branch(
                branch_name="codex/tool",
                worktree_path=worktree_path,
                runtime=runtime,
            )
            state = inspect_worktrees(runtime=runtime)
            removed = remove_worktree(worktree_path=worktree_path, runtime=runtime)

        self.assertIn("Status: READY", plan)
        self.assertIn("Status: CREATED", created)
        self.assertIn("codex/tool", state)
        self.assertIn("Status: REMOVED", removed)

    def test_worktree_tools_are_registered(self):
        self.assertIn("inspect_worktrees", registry.tools)
        self.assertIn("plan_worktree_branch", registry.tools)
        self.assertIn("create_worktree_branch", registry.tools)
        self.assertIn("remove_worktree", registry.tools)

    def _init_git_repo(self, workspace):
        self._write_file(workspace, "app.py", "VALUE = 1\n")
        self._git(workspace, "init")
        self._git(workspace, "config", "user.email", "forge@example.com")
        self._git(workspace, "config", "user.name", "Forge Test")
        self._git(workspace, "add", ".")
        self._git(workspace, "commit", "-m", "init")

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

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
