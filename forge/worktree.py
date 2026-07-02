import os
import re
import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class WorktreeInfo:
    """One git worktree entry."""

    path: str
    branch: str = ""
    head: str = ""
    detached: bool = False
    bare: bool = False


@dataclass
class WorktreeState:
    """Git worktree state for a repository."""

    is_repo: bool
    branch: str
    dirty_files: List[str]
    worktrees: List[WorktreeInfo]
    error: str = ""


@dataclass
class WorktreeOperation:
    """Result from a worktree operation."""

    status: str
    branch: str
    path: str
    notes: List[str]


class WorktreeManager:
    """Plans and manages git branch worktrees for isolated agent attempts."""

    def inspect(self, workspace_dir: str) -> WorktreeState:
        repo_check = self._git(workspace_dir, ["rev-parse", "--is-inside-work-tree"])
        if repo_check.returncode != 0 or repo_check.stdout.strip() != "true":
            return WorktreeState(
                is_repo=False,
                branch="",
                dirty_files=[],
                worktrees=[],
                error=(repo_check.stderr or repo_check.stdout or "Not inside a git work tree.").strip(),
            )

        branch = self._git(workspace_dir, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        status = self._git(workspace_dir, ["status", "--porcelain"])
        if status.returncode != 0:
            return WorktreeState(
                is_repo=True,
                branch=branch,
                dirty_files=[],
                worktrees=[],
                error=(status.stderr or status.stdout).strip(),
            )

        worktrees_result = self._git(workspace_dir, ["worktree", "list", "--porcelain"])
        worktrees = []
        if worktrees_result.returncode == 0:
            worktrees = self._parse_worktrees(worktrees_result.stdout)

        return WorktreeState(
            is_repo=True,
            branch=branch,
            dirty_files=self._parse_dirty_files(status.stdout),
            worktrees=worktrees,
        )

    def format_state(self, workspace_dir: str) -> str:
        state = self.inspect(workspace_dir)
        lines = [
            "Worktree state:",
            f"Is git repo: {state.is_repo}",
        ]
        if state.error:
            lines.append(f"Error: {state.error}")
        if not state.is_repo:
            return "\n".join(lines)

        lines.extend([
            f"Current branch: {state.branch}",
            "",
            "Dirty files:",
        ])
        if state.dirty_files:
            lines.extend(f"- {path}" for path in state.dirty_files)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Worktrees:")
        if state.worktrees:
            for worktree in state.worktrees:
                label = worktree.branch or ("detached" if worktree.detached else "unknown")
                lines.append(f"- {label}: {worktree.path}")
        else:
            lines.append("- none")
        return "\n".join(lines)

    def plan_branch(
        self,
        workspace_dir: str,
        branch_name: str,
        worktree_path: str = "",
        base_ref: str = "HEAD",
    ) -> WorktreeOperation:
        branch = self._normalize_branch(branch_name)
        if not branch:
            return WorktreeOperation("BLOCK", "", "", ["Branch name is required."])

        state = self.inspect(workspace_dir)
        path = self._default_path(workspace_dir, branch) if not worktree_path else self._resolve_path(workspace_dir, worktree_path)
        notes = []

        if not state.is_repo:
            return WorktreeOperation("BLOCK", branch, path, [f"Workspace is not a git repository: {state.error}"])
        if state.error:
            return WorktreeOperation("BLOCK", branch, path, [f"Could not inspect git state: {state.error}"])
        if state.dirty_files:
            notes.append("Current workspace has uncommitted files; new worktree will start from committed state only.")
        if os.path.exists(path):
            notes.append("Target worktree path already exists; creation will be blocked unless it is removed first.")

        notes.extend([
            f"Base ref: {base_ref or 'HEAD'}",
            "Run create_worktree_branch after reviewing the target path and branch name.",
        ])
        return WorktreeOperation("READY", branch, path, notes)

    def format_plan(
        self,
        workspace_dir: str,
        branch_name: str,
        worktree_path: str = "",
        base_ref: str = "HEAD",
    ) -> str:
        plan = self.plan_branch(workspace_dir, branch_name, worktree_path, base_ref)
        return self._format_operation("Worktree branch plan", plan)

    def create_branch(
        self,
        workspace_dir: str,
        branch_name: str,
        worktree_path: str = "",
        base_ref: str = "HEAD",
    ) -> WorktreeOperation:
        plan = self.plan_branch(workspace_dir, branch_name, worktree_path, base_ref)
        if plan.status != "READY":
            return plan
        if os.path.exists(plan.path):
            return WorktreeOperation(
                "BLOCK",
                plan.branch,
                plan.path,
                ["Target worktree path already exists."],
            )

        result = self._git(
            workspace_dir,
            ["worktree", "add", "-b", plan.branch, plan.path, base_ref or "HEAD"],
        )
        if result.returncode != 0:
            return WorktreeOperation(
                "BLOCK",
                plan.branch,
                plan.path,
                ["Failed to create worktree.", self._command_output(result)],
            )

        return WorktreeOperation(
            "CREATED",
            plan.branch,
            plan.path,
            ["Worktree created successfully.", *plan.notes],
        )

    def format_create(
        self,
        workspace_dir: str,
        branch_name: str,
        worktree_path: str = "",
        base_ref: str = "HEAD",
    ) -> str:
        result = self.create_branch(workspace_dir, branch_name, worktree_path, base_ref)
        return self._format_operation("Worktree branch creation", result)

    def remove_worktree(self, workspace_dir: str, worktree_path: str, force: bool = False) -> WorktreeOperation:
        path = self._resolve_path(workspace_dir, worktree_path)
        if os.path.abspath(path) == os.path.abspath(workspace_dir):
            return WorktreeOperation("BLOCK", "", path, ["Refusing to remove the current workspace."])

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(path)
        result = self._git(workspace_dir, args)
        if result.returncode != 0:
            return WorktreeOperation(
                "BLOCK",
                "",
                path,
                ["Failed to remove worktree.", self._command_output(result)],
            )
        return WorktreeOperation("REMOVED", "", path, ["Worktree removed successfully."])

    def format_remove(self, workspace_dir: str, worktree_path: str, force: bool = False) -> str:
        result = self.remove_worktree(workspace_dir, worktree_path, force=force)
        return self._format_operation("Worktree removal", result)

    def _normalize_branch(self, branch_name: str) -> str:
        branch = (branch_name or "").strip()
        if not branch:
            return ""
        if not re.match(r"^[A-Za-z0-9._/-]+$", branch):
            return ""
        if branch.startswith(("-", "/", ".")) or branch.endswith(("/", ".")):
            return ""
        if ".." in branch or "@{" in branch or "//" in branch:
            return ""
        return branch

    def _default_path(self, workspace_dir: str, branch: str) -> str:
        repo_name = os.path.basename(os.path.abspath(workspace_dir))
        safe_branch = branch.replace("/", "-")
        return os.path.realpath(os.path.abspath(os.path.join(workspace_dir, "..", f"{repo_name}-{safe_branch}")))

    def _resolve_path(self, workspace_dir: str, path: str) -> str:
        if os.path.isabs(path):
            return os.path.realpath(path)
        return os.path.realpath(os.path.abspath(os.path.join(workspace_dir, path)))

    def _parse_dirty_files(self, output: str) -> List[str]:
        files = []
        for line in output.splitlines():
            if not line:
                continue
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            files.append(path)
        return files

    def _parse_worktrees(self, output: str) -> List[WorktreeInfo]:
        entries: List[WorktreeInfo] = []
        current = None
        for line in output.splitlines():
            if line.startswith("worktree "):
                if current:
                    entries.append(current)
                current = WorktreeInfo(path=os.path.realpath(line.split(" ", 1)[1]))
            elif current and line.startswith("HEAD "):
                current.head = line.split(" ", 1)[1]
            elif current and line.startswith("branch "):
                branch = line.split(" ", 1)[1]
                current.branch = branch.removeprefix("refs/heads/")
            elif current and line == "detached":
                current.detached = True
            elif current and line == "bare":
                current.bare = True
        if current:
            entries.append(current)
        return entries

    def _format_operation(self, title: str, operation: WorktreeOperation) -> str:
        lines = [
            f"{title}:",
            f"Status: {operation.status}",
        ]
        if operation.branch:
            lines.append(f"Branch: {operation.branch}")
        if operation.path:
            lines.append(f"Path: {operation.path}")
        lines.append("")
        lines.append("Notes:")
        if operation.notes:
            lines.extend(f"- {note}" for note in operation.notes)
        else:
            lines.append("- none")
        return "\n".join(lines)

    def _command_output(self, result: subprocess.CompletedProcess) -> str:
        output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        return output or f"git exited with status {result.returncode}"

    def _git(self, workspace_dir: str, args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
        )
