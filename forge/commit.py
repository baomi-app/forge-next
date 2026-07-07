import os
import subprocess
from dataclasses import dataclass
from typing import List

from forge.changes import ChangeSet, FileChange
from forge.llm_decisions import LLMDecisionError
from forge.project import ProjectPolicy


@dataclass
class CommitFileDecision:
    """Staging recommendation for one changed file."""

    path: str
    status: str
    action: str
    reason: str


@dataclass
class CommitPlan:
    """Delivery-oriented plan for turning a transaction into one commit."""

    status: str
    message: str
    files: List[CommitFileDecision]
    risks: List[str]
    next_steps: List[str]


@dataclass
class GitFileState:
    """One file entry from git status."""

    path: str
    index_status: str
    worktree_status: str


@dataclass
class GitState:
    """Current git repository state."""

    is_repo: bool
    branch: str
    files: List[GitFileState]
    error: str = ""


@dataclass
class CommitExecution:
    """Result from staging and creating one commit."""

    status: str
    message: str
    commit_hash: str
    staged_files: List[str]
    committed_files: List[str]
    remaining_files: List[str]
    notes: List[str]


class CommitPlanner:
    """Plans atomic commit boundaries from task-scoped transaction changes."""

    def __init__(self, policy: ProjectPolicy = None, decision_service=None):
        self.policy = policy or ProjectPolicy()
        self.decision_service = decision_service

    def plan(self, change_set: ChangeSet, task_goal: str = "") -> CommitPlan:
        """Build a commit plan for the current task transaction."""
        changes = change_set.changes()
        if not changes:
            return CommitPlan(
                status="BLOCK",
                message="chore: no changes to commit",
                files=[],
                risks=["No transaction changes were found."],
                next_steps=["Make a task-scoped change before planning a commit."],
            )
        if not self.decision_service:
            return CommitPlan(
                status="BLOCK",
                message="chore: commit planning unavailable",
                files=[],
                risks=["LLM commit planning is not configured."],
                next_steps=["Configure an LLMDecisionService, then run plan_commit again."],
            )

        try:
            decision = self.decision_service.plan_commit(
                task_goal=task_goal,
                changes=changes,
                diff=change_set.diff(max_chars=12000),
            )
        except LLMDecisionError as exc:
            return CommitPlan(
                status="BLOCK",
                message="chore: commit planning unavailable",
                files=[],
                risks=[f"LLM commit planning failed: {exc}"],
                next_steps=["Fix the LLM commit planning response, then run plan_commit again."],
            )

        files, guard_risks = self._validated_file_decisions(changes, decision.files, change_set.workspace_dir)
        risks = [*decision.risks, *guard_risks]
        status = "BLOCK" if guard_risks else decision.status
        message = decision.message
        next_steps = decision.next_steps

        return CommitPlan(
            status=status,
            message=message,
            files=files,
            risks=risks,
            next_steps=next_steps,
        )

    def format_plan(self, change_set: ChangeSet, task_goal: str = "") -> str:
        """Render the commit plan for agent-facing output."""
        plan = self.plan(change_set, task_goal=task_goal)
        stage_files = [file for file in plan.files if file.action == "stage"]
        exclude_files = [file for file in plan.files if file.action == "exclude"]

        lines = [
            "Commit orchestration plan:",
            f"Status: {plan.status}",
            f"Suggested commit message: {plan.message}",
            "",
            "Stage these files:",
        ]
        if stage_files:
            lines.extend(f"- {file.status}: {file.path} ({file.reason})" for file in stage_files)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Exclude from commit:")
        if exclude_files:
            lines.extend(f"- {file.status}: {file.path} ({file.reason})" for file in exclude_files)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Risks:")
        if plan.risks:
            lines.extend(f"- {risk}" for risk in plan.risks)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Next steps:")
        lines.extend(f"- {step}" for step in plan.next_steps)

        return "\n".join(lines)

    def _validated_file_decisions(self, changes: List[FileChange], llm_files, workspace_dir: str):
        by_path = {change.path: change for change in changes}
        files: List[CommitFileDecision] = []
        risks: List[str] = []
        seen = set()
        for file in llm_files:
            path = self._normalize_relative_path(file.path)
            if not self._is_safe_relative_path(workspace_dir, path):
                risks.append(f"LLM suggested an unsafe commit path: {file.path}")
                continue
            if path not in by_path:
                risks.append(f"LLM suggested a file outside the current transaction: {path}")
                continue
            if path in seen:
                risks.append(f"LLM repeated a commit file decision: {path}")
                continue
            seen.add(path)
            change = by_path[path]
            files.append(
                CommitFileDecision(
                    path=path,
                    status=change.status,
                    action=file.action,
                    reason=file.reason,
                )
            )
        missing = [path for path in by_path if path not in seen]
        if missing:
            risks.extend(f"LLM did not classify changed file: {path}" for path in missing)
        return files, risks

    def _is_safe_relative_path(self, workspace_dir: str, path: str) -> bool:
        if not path or os.path.isabs(path):
            return False
        root = os.path.abspath(workspace_dir)
        full_path = os.path.abspath(os.path.join(root, path))
        return os.path.commonpath([root, full_path]) == root

    def _normalize_relative_path(self, path: str) -> str:
        normalized = path.strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized


class GitStateInspector:
    """Reads git working tree and index state for commit orchestration."""

    def inspect(self, workspace_dir: str) -> GitState:
        repo_check = self._git(workspace_dir, ["rev-parse", "--is-inside-work-tree"])
        if repo_check.returncode != 0 or repo_check.stdout.strip() != "true":
            return GitState(
                is_repo=False,
                branch="",
                files=[],
                error=(repo_check.stderr or repo_check.stdout or "Not inside a git work tree.").strip(),
            )

        branch = self._git(workspace_dir, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        status = self._git(workspace_dir, ["status", "--porcelain"])
        if status.returncode != 0:
            return GitState(
                is_repo=True,
                branch=branch,
                files=[],
                error=(status.stderr or status.stdout).strip(),
            )

        return GitState(
            is_repo=True,
            branch=branch,
            files=self._parse_status(status.stdout),
        )

    def staged_paths(self, state: GitState) -> List[str]:
        return [file.path for file in state.files if file.index_status != " " and file.index_status != "?"]

    def remaining_paths(self, state: GitState) -> List[str]:
        return [file.path for file in state.files]

    def _parse_status(self, output: str) -> List[GitFileState]:
        files = []
        for line in output.splitlines():
            if not line:
                continue
            index_status = line[0]
            worktree_status = line[1]
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            files.append(
                GitFileState(
                    path=path,
                    index_status=index_status,
                    worktree_status=worktree_status,
                )
            )
        return files

    def _git(self, workspace_dir: str, args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
        )


class CommitOrchestrator:
    """Stages planned files, creates one commit, and verifies the result."""

    def __init__(self, decision_service=None):
        self.planner = CommitPlanner(decision_service=decision_service)
        self.git = GitStateInspector()

    def commit(
        self,
        change_set: ChangeSet,
        task_goal: str = "",
        allow_review: bool = False,
    ) -> CommitExecution:
        """Create one git commit from the current transaction when the plan is safe."""
        plan = self.planner.plan(change_set, task_goal=task_goal)
        stage_files = [file.path for file in plan.files if file.action == "stage"]
        excluded_files = {file.path for file in plan.files if file.action == "exclude"}
        notes = []

        if plan.status == "BLOCK":
            return self._blocked(plan.message, stage_files, ["Commit plan is blocked.", *plan.risks])
        if plan.status == "REVIEW" and not allow_review:
            return self._blocked(
                plan.message,
                stage_files,
                ["Commit plan needs review before execution.", *plan.risks],
            )
        if not stage_files:
            return self._blocked(plan.message, stage_files, ["No files are approved for staging."])

        state = self.git.inspect(change_set.workspace_dir)
        if not state.is_repo:
            return self._blocked(plan.message, stage_files, [f"Workspace is not a git repository: {state.error}"])
        if state.error:
            return self._blocked(plan.message, stage_files, [f"Could not inspect git state: {state.error}"])

        staged_before = set(self.git.staged_paths(state))
        stage_set = set(stage_files)
        staged_outside_plan = sorted(staged_before - stage_set)
        if staged_outside_plan:
            return self._blocked(
                plan.message,
                stage_files,
                ["Git index already contains files outside this commit plan.", *staged_outside_plan],
            )
        staged_excluded = sorted(staged_before & excluded_files)
        if staged_excluded:
            return self._blocked(
                plan.message,
                stage_files,
                ["Git index contains excluded files.", *staged_excluded],
            )

        add_result = self._git(change_set.workspace_dir, ["add", "--", *stage_files])
        if add_result.returncode != 0:
            return self._blocked(
                plan.message,
                stage_files,
                ["Failed to stage planned files.", self._command_output(add_result)],
            )

        staged_state = self.git.inspect(change_set.workspace_dir)
        staged_after = set(self.git.staged_paths(staged_state))
        unexpected_staged = sorted(staged_after - stage_set)
        if unexpected_staged:
            self._git(change_set.workspace_dir, ["reset", "--", *stage_files])
            return self._blocked(
                plan.message,
                stage_files,
                ["Staging introduced files outside the commit plan; planned files were unstaged.", *unexpected_staged],
            )
        if not staged_after:
            return self._blocked(plan.message, stage_files, ["No staged changes remain after staging planned files."])

        commit_result = self._git(change_set.workspace_dir, ["commit", "-m", plan.message])
        if commit_result.returncode != 0:
            return self._blocked(
                plan.message,
                sorted(staged_after),
                ["Git commit failed.", self._command_output(commit_result)],
            )

        commit_hash = self._git(change_set.workspace_dir, ["rev-parse", "--short", "HEAD"]).stdout.strip()
        committed_files = self._committed_files(change_set.workspace_dir)
        remaining_state = self.git.inspect(change_set.workspace_dir)
        remaining_files = self.git.remaining_paths(remaining_state)

        if set(committed_files) != set(staged_after):
            notes.append("Committed file set differs from staged plan; inspect the commit before pushing.")
        if remaining_files:
            notes.append("Uncommitted files remain after commit; keep them out of this delivery unless intentional.")
        else:
            change_set.capture_baseline()

        return CommitExecution(
            status="COMMITTED",
            message=plan.message,
            commit_hash=commit_hash,
            staged_files=sorted(staged_after),
            committed_files=committed_files,
            remaining_files=remaining_files,
            notes=notes or ["Commit created successfully."],
        )

    def format_commit(
        self,
        change_set: ChangeSet,
        task_goal: str = "",
        allow_review: bool = False,
    ) -> str:
        """Render commit execution result for agent-facing output."""
        result = self.commit(change_set, task_goal=task_goal, allow_review=allow_review)
        lines = [
            "Commit orchestration result:",
            f"Status: {result.status}",
            f"Commit message: {result.message}",
        ]
        if result.commit_hash:
            lines.append(f"Commit: {result.commit_hash}")

        lines.append("")
        lines.append("Staged files:")
        lines.extend(self._file_lines(result.staged_files))

        lines.append("")
        lines.append("Committed files:")
        lines.extend(self._file_lines(result.committed_files))

        lines.append("")
        lines.append("Remaining files:")
        lines.extend(self._file_lines(result.remaining_files))

        lines.append("")
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in result.notes)

        return "\n".join(lines)

    def _blocked(self, message: str, stage_files: List[str], notes: List[str]) -> CommitExecution:
        return CommitExecution(
            status="BLOCKED",
            message=message,
            commit_hash="",
            staged_files=stage_files,
            committed_files=[],
            remaining_files=[],
            notes=notes,
        )

    def _committed_files(self, workspace_dir: str) -> List[str]:
        result = self._git(workspace_dir, ["show", "--name-only", "--format=", "HEAD"])
        return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())

    def _file_lines(self, files: List[str]) -> List[str]:
        if not files:
            return ["- none"]
        return [f"- {file}" for file in files]

    def _command_output(self, result: subprocess.CompletedProcess) -> str:
        output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        return output or f"exit code {result.returncode}"

    def _git(self, workspace_dir: str, args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
        )
