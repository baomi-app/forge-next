import os
from dataclasses import dataclass
from typing import Iterable, List

from forge.changes import FileChange
from forge.command_policy import CommandPolicy
from forge.llm_decisions import LLMDecisionError
from forge.project import ProjectPolicy
from forge.verifier import VerificationCheck


@dataclass
class FocusedTestPlan:
    """Suggested verification commands for a set of changed files."""

    checks: List[VerificationCheck]
    notes: List[str]


class FocusedTestSelector:
    """Selects focused verification commands from task-scoped file changes."""

    def __init__(self, workspace_dir: str, policy: ProjectPolicy = None, decision_service=None, command_policy: CommandPolicy = None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.policy = policy or ProjectPolicy()
        self.decision_service = decision_service
        self.command_policy = command_policy or CommandPolicy()

    def select(self, changes: Iterable[FileChange]) -> FocusedTestPlan:
        """Return focused verification checks and explanatory notes."""
        change_list = list(changes)
        changed_paths = [change.path for change in change_list]
        if not changed_paths:
            return FocusedTestPlan(checks=[], notes=["No changed files; no focused tests suggested."])

        if not self.decision_service:
            return FocusedTestPlan(
                checks=[],
                notes=["LLM focused test selection is not configured."],
            )

        try:
            decision = self.decision_service.suggest_focused_tests(
                changed_files=[
                    {"path": change.path, "status": change.status}
                    for change in change_list
                ],
                workspace_files=self._workspace_files(),
            )
        except LLMDecisionError as exc:
            return FocusedTestPlan(checks=[], notes=[f"LLM focused test selection failed: {exc}"])
        notes = list(decision.notes)
        checks = []
        for check in decision.checks:
            allowed, reason = self.command_policy.validate(check.command)
            if not allowed:
                notes.append(f"LLM suggested an unsafe focused command '{check.command}': {reason}")
                continue
            checks.append(
                VerificationCheck(
                    name=check.name,
                    command=check.command,
                    category=check.category,
                    source=check.source,
                )
            )
        return FocusedTestPlan(checks=checks, notes=notes)

    def format_plan(self, changes: Iterable[FileChange]) -> str:
        """Render focused verification suggestions for agent-facing output."""
        change_list = list(changes)
        changed_paths = [change.path for change in change_list]
        plan = self.select(change_list)

        lines = [
            "Focused verification suggestions:",
            f"Changed files: {len(changed_paths)}",
            "Files:",
        ]
        if changed_paths:
            lines.extend(f"- {path}" for path in changed_paths)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Suggested commands:")
        if plan.checks:
            lines.extend(f"- {check.command} ({check.source})" for check in plan.checks)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Notes:")
        if plan.notes:
            lines.extend(f"- {note}" for note in plan.notes)
        else:
            lines.append("- none")

        return "\n".join(lines)

    def _workspace_files(self) -> List[str]:
        files = []
        if not os.path.isdir(self.workspace_dir):
            return files
        for root, dirs, filenames in os.walk(self.workspace_dir):
            dirs[:] = sorted(d for d in dirs if self.policy.should_descend_dir(d))
            for filename in sorted(filenames):
                path = os.path.relpath(os.path.join(root, filename), self.workspace_dir)
                if self.policy.should_track_file(path):
                    files.append(path)
        return files
