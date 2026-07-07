from dataclasses import dataclass
from typing import List, Optional

from forge.changes import ChangeSet
from forge.llm_decisions import LLMDecisionError


@dataclass
class ReviewFinding:
    """One change review finding."""

    severity: str
    message: str
    path: Optional[str] = None


class ChangeReviewer:
    """Reviews task-scoped changes for delivery and commit readiness."""

    def __init__(self, decision_service=None):
        self.decision_service = decision_service

    def review(self, change_set: ChangeSet, task_goal: str = "") -> str:
        """Return a human-readable review of the current transaction."""
        changes = change_set.changes()
        status = "BLOCK"
        findings: List[ReviewFinding] = []
        commit_shape: List[str] = []
        commit_message = ""

        if not changes:
            findings = [ReviewFinding("BLOCK", "No transaction changes were found.")]
            commit_shape = ["not ready: no changed files"]
            commit_message = "chore: no changes to review"
        elif not self.decision_service:
            findings = [
                ReviewFinding(
                    "BLOCK",
                    "LLM change review is not configured.",
                )
            ]
            commit_shape = ["not ready: configure LLM change review"]
            commit_message = "chore: review unavailable"
        else:
            try:
                decision = self.decision_service.review_changes(
                    task_goal=task_goal,
                    changes=changes,
                    diff=change_set.diff(max_chars=12000),
                )
                status = decision.status
                findings = [
                    ReviewFinding(
                        severity=finding.severity,
                        message=finding.message,
                        path=finding.path or None,
                    )
                    for finding in decision.findings
                ]
                commit_shape = decision.commit_shape or ["LLM review did not provide commit shape notes."]
                commit_message = decision.suggested_message
            except LLMDecisionError as exc:
                findings = [
                    ReviewFinding(
                        "BLOCK",
                        f"LLM change review returned an invalid or unavailable decision: {exc}",
                    )
                ]
                commit_shape = ["not ready: LLM change review failed"]
                commit_message = "chore: review unavailable"

        lines = [
            f"Status: {status}",
            f"Changed files: {len(changes)}",
        ]
        if task_goal:
            lines.append(f"Task goal: {task_goal}")

        lines.append("")
        lines.append("Files:")
        if changes:
            lines.extend(f"- {change.status}: {change.path}" for change in changes)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Findings:")
        if findings:
            lines.extend(self._format_finding(finding) for finding in findings)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Commit shape:")
        lines.extend(f"- {item}" for item in commit_shape)
        lines.append(f"- suggested message: {commit_message}")

        return "\n".join(lines)

    def _format_finding(self, finding: ReviewFinding) -> str:
        prefix = f"- {finding.severity}: "
        if finding.path:
            return f"{prefix}{finding.path}: {finding.message}"
        return f"{prefix}{finding.message}"
