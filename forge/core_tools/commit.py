from typing import Any, Optional

from forge.commit import CommitOrchestrator, CommitPlanner
from forge.core_tools.changes import get_change_set
from forge.tool_registry import tool


@tool
def plan_commit(
    task_goal: str = "",
    runtime: Optional[Any] = None,
) -> str:
    """Plan an atomic commit from the current task transaction."""
    change_set = get_change_set(runtime=runtime)
    if not change_set:
        return "Error: Change transaction state is not available."
    decision_service = getattr(runtime, "decision_service", None) if runtime else None
    return CommitPlanner(decision_service=decision_service).format_plan(change_set, task_goal=task_goal)


@tool
def commit_changes(
    task_goal: str = "",
    allow_review: bool = False,
    runtime: Optional[Any] = None,
) -> str:
    """Stage planned transaction files and create one git commit when the plan is safe.

    Args:
        task_goal (str): Optional concise description used for the commit message.
        allow_review (bool): Allow committing a REVIEW plan after explicit acceptance.
    """
    change_set = get_change_set(runtime=runtime)
    if not change_set:
        return "Error: Change transaction state is not available."
    decision_service = getattr(runtime, "decision_service", None) if runtime else None
    return CommitOrchestrator(decision_service=decision_service).format_commit(
        change_set,
        task_goal=task_goal,
        allow_review=allow_review,
    )
