from typing import Any, Optional

from forge.core_tools.changes import get_change_set
from forge.review import ChangeReviewer
from forge.tool_registry import tool


@tool
def review_changes(
    task_goal: str = "",
    runtime: Optional[Any] = None,
) -> str:
    """Review current task transaction changes for commit readiness and delivery risks.

    Args:
        task_goal (str): Optional concise description of the intended task.
    """
    change_set = get_change_set(runtime=runtime)
    if not change_set:
        return "Error: Change transaction state is not available."
    decision_service = getattr(runtime, "decision_service", None) if runtime else None
    return ChangeReviewer(decision_service=decision_service).review(change_set, task_goal=task_goal)
