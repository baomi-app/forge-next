from typing import Any, Optional

from forge.issue_pr import IssuePrWorkflow
from forge.memory import CodebaseMemory
from forge.tool_registry import tool


def _workspace_dir(runtime: Optional[Any]) -> Optional[str]:
    return getattr(runtime, "workspace_dir", None) if runtime else None


@tool
def plan_issue_pr_workflow(
    reference: str,
    title: str = "",
    body: str = "",
    feedback: str = "",
    source: str = "issue",
    runtime: Optional[Any] = None,
) -> str:
    """Turn issue, PR, CI, or review context into an agent implementation workflow."""
    workspace_dir = _workspace_dir(runtime)
    if not workspace_dir:
        return "Error: Workspace state is not available."
    decision_service = getattr(runtime, "decision_service", None) if runtime else None
    return IssuePrWorkflow(decision_service=decision_service).format_plan(
        workspace_dir=workspace_dir,
        reference=reference,
        title=title,
        body=body,
        feedback=feedback,
        source=source,
    )


@tool
def record_pr_feedback(
    reference: str,
    feedback: str,
    source: str = "review",
    decision: str = "needs_changes",
    remember: bool = True,
    runtime: Optional[Any] = None,
) -> str:
    """Record PR, review, or CI feedback in the task journal and optional codebase memory."""
    workspace_dir = _workspace_dir(runtime)
    if not workspace_dir:
        return "Error: Workspace state is not available."

    decision_service = getattr(runtime, "decision_service", None) if runtime else None
    output = IssuePrWorkflow(decision_service=decision_service).format_feedback_record(
        reference=reference,
        feedback=feedback,
        source=source,
        decision=decision,
    )
    recorder = getattr(runtime, "journal_recorder", None) if runtime else None
    if recorder:
        recorder.note(
            kind="external_feedback",
            summary=f"{source} feedback for {reference or 'workflow'}",
            details=output,
        )
    if remember:
        CodebaseMemory(workspace_dir, decision_service=decision_service).add(
            kind="workflow",
            summary=f"{source} feedback for {reference or 'workflow'}",
            details=feedback,
            tags="issue-pr,feedback",
            source="issue_pr_workflow",
        )
    return output
