from typing import Any, Optional

from forge.core_tools.changes import get_change_set
from forge.human_review import HumanReviewLoop
from forge.tool_registry import tool
from forge.tool_result import ToolResult


@tool
def request_human_review(
    stage: str,
    task_goal: str = "",
    summary: str = "",
    include_diff: bool = True,
    runtime: Optional[Any] = None,
) -> ToolResult:
    """Create a human approval checkpoint for plan, diff, commit, or custom review."""
    change_set = get_change_set(runtime=runtime)
    checkpoint = HumanReviewLoop().create_checkpoint(
        stage=stage,
        change_set=change_set,
        task_goal=task_goal,
        summary=summary,
        include_diff=include_diff,
    )
    content = checkpoint.format()
    recorder = getattr(runtime, "journal_recorder", None) if runtime else None
    if recorder:
        recorder.note(
            kind="human_review",
            summary=f"{checkpoint.stage} review requested",
            details=content,
        )
    return ToolResult.blocked(
        content,
        error_type="human_review_required",
        metadata={"stage": checkpoint.stage},
    )


@tool
def record_human_review(
    stage: str,
    decision: str,
    notes: str = "",
    runtime: Optional[Any] = None,
) -> str:
    """Record a human review decision after an approval checkpoint."""
    content = HumanReviewLoop().format_decision(stage=stage, decision=decision, notes=notes)
    recorder = getattr(runtime, "journal_recorder", None) if runtime else None
    if recorder:
        recorder.note(
            kind="human_review",
            summary=f"{stage} review {decision}",
            details=content,
        )
    return content
