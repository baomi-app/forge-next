import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class IssuePrContext:
    """Structured issue, PR, CI, or review context for agent work."""

    source: str
    reference: str
    title: str = ""
    body: str = ""
    feedback: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)


class IssuePrWorkflow:
    """Turns external collaboration context into an agent work plan."""

    VALID_SOURCES = {"issue", "pr", "ci", "review", "custom"}

    def build_context(
        self,
        reference: str,
        title: str = "",
        body: str = "",
        feedback: str = "",
        source: str = "issue",
    ) -> IssuePrContext:
        return IssuePrContext(
            source=self._normalize_source(source, reference),
            reference=reference.strip(),
            title=title.strip(),
            body=body.strip(),
            feedback=feedback.strip(),
            acceptance_criteria=self._acceptance_criteria(body),
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

        feedback_items = self._feedback_items(context.feedback)
        lines.append("")
        lines.append("External feedback:")
        if feedback_items:
            lines.extend(f"- {item}" for item in feedback_items)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Recommended agent flow:")
        lines.extend([
            "- inspect repo map and relevant files before editing",
            "- create or update tests matching the acceptance criteria",
            "- run focused verification, then broader project verification",
            "- run change review and request human review before commit or PR update when needed",
            "- prepare one atomic commit or PR response covering only this workflow item",
        ])
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
        items = self._feedback_items(context.feedback)

        lines = [
            "Issue / PR feedback recorded:",
            f"Source: {context.source}",
            f"Reference: {context.reference or 'unspecified'}",
            f"Decision: {normalized_decision}",
            "",
            "Feedback items:",
        ]
        if items:
            lines.extend(f"- {item}" for item in items)
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

    def _acceptance_criteria(self, body: str) -> List[str]:
        criteria = []
        in_section = False
        for raw_line in body.splitlines():
            line = raw_line.strip()
            lower = line.lower().rstrip(":")
            if lower in {"acceptance criteria", "acceptance", "requirements"}:
                in_section = True
                continue
            if in_section and line.startswith("#"):
                in_section = False
            checkbox = re.match(r"^[-*]\s+\[[ xX]\]\s+(.+)$", line)
            bullet = re.match(r"^[-*]\s+(.+)$", line)
            if checkbox:
                criteria.append(checkbox.group(1).strip())
            elif in_section and bullet:
                criteria.append(bullet.group(1).strip())
        return criteria

    def _feedback_items(self, feedback: str) -> List[str]:
        items = []
        for raw_line in feedback.splitlines():
            line = raw_line.strip()
            bullet = re.match(r"^[-*]\s+(.+)$", line)
            if bullet:
                items.append(bullet.group(1).strip())
            elif line and len(line) <= 180:
                items.append(line)
        return items

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
