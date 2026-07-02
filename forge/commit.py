import os
import subprocess
from dataclasses import dataclass
from typing import List

from forge.changes import ChangeSet, FileChange
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

    def __init__(self, policy: ProjectPolicy = None):
        self.policy = policy or ProjectPolicy()

    def plan(self, change_set: ChangeSet, task_goal: str = "") -> CommitPlan:
        """Build a commit plan for the current task transaction."""
        changes = change_set.changes()
        files = [self._file_decision(change) for change in changes]
        risks = self._risks(changes, files)
        status = self._status(files, risks)
        message = self._message(changes, files, task_goal)
        next_steps = self._next_steps(status, files, risks)

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

    def _file_decision(self, change: FileChange) -> CommitFileDecision:
        if self.policy.is_generated_file(change.path):
            return CommitFileDecision(
                path=change.path,
                status=change.status,
                action="exclude",
                reason="local, generated, or temporary file",
            )
        return CommitFileDecision(
            path=change.path,
            status=change.status,
            action="stage",
            reason=self._category(change.path),
        )

    def _risks(self, changes: List[FileChange], files: List[CommitFileDecision]) -> List[str]:
        risks = []
        if not changes:
            return ["No transaction changes were found."]

        if any(file.action == "exclude" for file in files):
            risks.append("Excluded files must be removed or left unstaged before committing.")

        staged = [file for file in files if file.action == "stage"]
        if not staged:
            risks.append("No committable files remain after exclusions.")
            return risks

        code = [file for file in staged if self._is_code(file.path)]
        tests = [file for file in staged if self._is_test(file.path)]
        docs = [file for file in staged if self._is_doc(file.path)]
        examples = [file for file in staged if self._is_example(file.path)]

        if code and not tests:
            risks.append("Code changes have no staged test changes; verify existing coverage is enough.")
        if code and not (docs or examples):
            risks.append("Runtime behavior changed without staged docs or examples.")
        if len(staged) > 12:
            risks.append("Large staging set; confirm this is still one atomic feature or fix.")

        categories = {self._category(file.path) for file in staged}
        if "runtime code" in categories and "project configuration" in categories:
            risks.append("Runtime code and project configuration changed together; confirm they serve one goal.")
        if "other" in categories and len(categories) > 2:
            risks.append("Mixed uncategorized files with other changes; review the commit boundary.")

        return risks

    def _status(self, files: List[CommitFileDecision], risks: List[str]) -> str:
        if not files:
            return "BLOCK"
        if any("No committable files" in risk or "No transaction changes" in risk for risk in risks):
            return "BLOCK"
        if any(file.action == "exclude" for file in files):
            return "BLOCK"
        if risks:
            return "REVIEW"
        return "READY"

    def _next_steps(self, status: str, files: List[CommitFileDecision], risks: List[str]) -> List[str]:
        if status == "BLOCK":
            steps = []
            if any(file.action == "exclude" for file in files):
                steps.append("Remove or leave excluded files unstaged before committing.")
            if risks:
                steps.append("Resolve blocking risks, then run plan_commit again.")
            if not steps:
                steps.append("Make a task-scoped change before planning a commit.")
            return steps
        if status == "REVIEW":
            return [
                "Resolve or explicitly accept the listed risks.",
                "Run focused and project verification before staging.",
                "Stage only the files listed in the staging section.",
            ]
        return [
            "Run focused and project verification if not already done.",
            "Stage the listed files.",
            "Commit with the suggested message or a more specific equivalent.",
        ]

    def _message(self, changes: List[FileChange], files: List[CommitFileDecision], task_goal: str) -> str:
        staged = [file for file in files if file.action == "stage"]
        if task_goal:
            return f"{self._commit_type(staged)}: {self._summary(task_goal)}"
        if staged and all(self._is_doc(file.path) for file in staged):
            return "docs: update documentation"
        if staged and any(file.status == "deleted" for file in staged):
            return "fix: remove obsolete code"
        if staged and any(self._is_code(file.path) for file in staged):
            return "feat: update coding agent behavior"
        if changes:
            return "chore: update project files"
        return "chore: no changes to commit"

    def _commit_type(self, files: List[CommitFileDecision]) -> str:
        if files and all(self._is_doc(file.path) for file in files):
            return "docs"
        if files and any(file.status == "deleted" for file in files):
            return "fix"
        if files and not any(self._is_code(file.path) for file in files):
            return "chore"
        return "feat"

    def _summary(self, task_goal: str) -> str:
        summary = task_goal.strip().splitlines()[0].strip().rstrip(".")
        return summary[:72] if summary else "update project"

    def _category(self, path: str) -> str:
        return self.policy.commit_category(path)

    def _is_code(self, path: str) -> bool:
        return self.policy.is_code(path)

    def _is_test(self, path: str) -> bool:
        return self.policy.is_test(path)

    def _is_doc(self, path: str) -> bool:
        return self.policy.is_doc(path)

    def _is_example(self, path: str) -> bool:
        return self.policy.is_example(path)


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

    def __init__(self):
        self.planner = CommitPlanner()
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
