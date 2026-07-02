from dataclasses import dataclass
from typing import List, Optional

from forge.changes import ChangeSet, FileChange


@dataclass
class HumanReviewCheckpoint:
    """A human approval checkpoint requested by the agent."""

    stage: str
    task_goal: str
    summary: str
    changed_files: List[FileChange]
    diff_preview: str = ""

    def format(self) -> str:
        lines = [
            "Human review checkpoint:",
            "Status: AWAITING_APPROVAL",
            f"Stage: {self.stage}",
        ]
        if self.task_goal:
            lines.append(f"Task goal: {self.task_goal}")
        if self.summary:
            lines.append(f"Summary: {self.summary}")

        lines.append("")
        lines.append("Changed files:")
        if self.changed_files:
            lines.extend(f"- {change.status}: {change.path}" for change in self.changed_files)
        else:
            lines.append("- none")

        if self.diff_preview:
            lines.append("")
            lines.append("Diff preview:")
            lines.append(self.diff_preview)

        lines.append("")
        lines.append("Approval required before continuing.")
        lines.append("After the human responds, record the decision with record_human_review.")
        return "\n".join(lines)


class HumanReviewLoop:
    """Creates and records human approval checkpoints."""

    VALID_STAGES = {"plan", "diff", "commit", "custom"}

    def create_checkpoint(
        self,
        stage: str,
        change_set: Optional[ChangeSet] = None,
        task_goal: str = "",
        summary: str = "",
        include_diff: bool = True,
        max_diff_chars: int = 2000,
    ) -> HumanReviewCheckpoint:
        normalized_stage = self._normalize_stage(stage)
        changed_files = change_set.changes() if change_set else []
        diff_preview = ""
        if include_diff and change_set:
            diff_preview = self._clip(change_set.diff(), max_diff_chars)

        return HumanReviewCheckpoint(
            stage=normalized_stage,
            task_goal=task_goal,
            summary=summary,
            changed_files=changed_files,
            diff_preview=diff_preview,
        )

    def format_decision(self, stage: str, decision: str, notes: str = "") -> str:
        normalized_stage = self._normalize_stage(stage)
        normalized_decision = (decision or "").strip().lower()
        if normalized_decision not in {"approved", "rejected", "needs_changes"}:
            normalized_decision = "needs_changes"

        lines = [
            "Human review decision recorded:",
            f"Stage: {normalized_stage}",
            f"Decision: {normalized_decision}",
        ]
        if notes:
            lines.append(f"Notes: {notes}")
        return "\n".join(lines)

    def _normalize_stage(self, stage: str) -> str:
        normalized = (stage or "").strip().lower()
        if normalized in self.VALID_STAGES:
            return normalized
        return "custom"

    def _clip(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n... [TRUNCATED DIFF PREVIEW] ..."
