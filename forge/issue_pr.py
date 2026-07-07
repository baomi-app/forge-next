import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from forge.llm_decisions import LLMDecisionError


@dataclass
class IssuePrContext:
    """Structured issue, PR, CI, or review context for agent work."""

    source: str
    reference: str
    title: str = ""
    body: str = ""
    feedback: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)
    feedback_items: List[str] = field(default_factory=list)
    recommended_flow: List[str] = field(default_factory=list)


class IssuePrWorkflow:
    """Turns external collaboration context into an agent work plan."""

    VALID_SOURCES = {"issue", "pr", "ci", "review", "custom"}

    def __init__(self, decision_service=None):
        self.decision_service = decision_service

    def build_context(
        self,
        reference: str,
        title: str = "",
        body: str = "",
        feedback: str = "",
        source: str = "issue",
    ) -> IssuePrContext:
        normalized_source = self._normalize_source(source, reference)
        acceptance_criteria: List[str] = []
        feedback_items: List[str] = []
        recommended_flow: List[str] = []
        if self.decision_service:
            try:
                decision = self.decision_service.extract_issue_pr_context(
                    title=title,
                    body=body,
                    feedback=feedback,
                    source=normalized_source,
                )
                acceptance_criteria = decision.acceptance_criteria
                feedback_items = decision.feedback_items
                recommended_flow = decision.recommended_flow
            except LLMDecisionError as exc:
                feedback_items = [f"LLM issue/PR extraction failed: {exc}"]
        else:
            feedback_items = ["LLM issue/PR extraction is not configured."]

        return IssuePrContext(
            source=normalized_source,
            reference=reference.strip(),
            title=title.strip(),
            body=body.strip(),
            feedback=feedback.strip(),
            acceptance_criteria=acceptance_criteria,
            feedback_items=feedback_items,
            recommended_flow=recommended_flow,
        )

    def format_plan(
        self,
        workspace_dir: str,
        reference: str,
        title: str = "",
        body: str = "",
        feedback: str = "",
        source: str = "issue",
    ) -> str:
        context = self.build_context(
            reference=reference,
            title=title,
            body=body,
            feedback=feedback,
            source=source,
        )
        local = self._local_context(workspace_dir)
        lines = [
            "Issue / PR workflow plan:",
            f"Source: {context.source}",
            f"Reference: {context.reference or 'unspecified'}",
        ]
        if context.title:
            lines.append(f"Title: {context.title}")

        lines.append("")
        lines.append("Local context:")
        lines.extend(f"- {item}" for item in local)

        lines.append("")
        lines.append("Acceptance criteria:")
        if context.acceptance_criteria:
            lines.extend(f"- {item}" for item in context.acceptance_criteria)
        else:
            lines.append("- infer from issue or PR body before editing")

        lines.append("")
        lines.append("External feedback:")
        if context.feedback_items:
            lines.extend(f"- {item}" for item in context.feedback_items)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Recommended agent flow:")
        if context.recommended_flow:
            lines.extend(f"- {item}" for item in context.recommended_flow)
        else:
            lines.append("- none")
        return "\n".join(lines)

    def format_feedback_record(
        self,
        reference: str,
        feedback: str,
        source: str = "review",
        decision: str = "needs_changes",
    ) -> str:
        normalized_decision = self._normalize_decision(decision)
        context = self.build_context(reference=reference, feedback=feedback, source=source)

        lines = [
            "Issue / PR feedback recorded:",
            f"Source: {context.source}",
            f"Reference: {context.reference or 'unspecified'}",
            f"Decision: {normalized_decision}",
            "",
            "Feedback items:",
        ]
        if context.feedback_items:
            lines.extend(f"- {item}" for item in context.feedback_items)
        else:
            lines.append("- none")
        return "\n".join(lines)

    def _normalize_source(self, source: str, reference: str) -> str:
        normalized = (source or "").strip().lower()
        if normalized in self.VALID_SOURCES:
            return normalized
        ref = reference.lower()
        if "/pull/" in ref or ref.startswith("pr"):
            return "pr"
        if "/issues/" in ref or ref.startswith("#"):
            return "issue"
        return "custom"

    def _normalize_decision(self, decision: str) -> str:
        normalized = (decision or "").strip().lower()
        if normalized in {"approved", "needs_changes", "blocked", "comment"}:
            return normalized
        return "needs_changes"

    def _local_context(self, workspace_dir: str) -> List[str]:
        branch = self._git(workspace_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
        status = self._git(workspace_dir, ["status", "--porcelain"])
        if branch.returncode != 0:
            return ["not inside a git repository"]
        dirty_count = len([line for line in status.stdout.splitlines() if line.strip()]) if status.returncode == 0 else 0
        return [
            f"current branch: {branch.stdout.strip()}",
            f"dirty files: {dirty_count}",
        ]

    def _git(self, workspace_dir: str, args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
        )
