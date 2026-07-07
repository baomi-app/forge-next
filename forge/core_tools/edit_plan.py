from typing import Any, Optional

from forge.core_tools.changes import get_change_set
from forge.edit_plan import EditPlanner
from forge.tool_registry import tool


@tool
def plan_edits(
    task_goal: str,
    target_files: str = "",
    max_files: int = 8,
    runtime: Optional[Any] = None,
) -> str:
    """Plan file edits before modifying the workspace.

    Args:
        task_goal (str): The intended task or change.
        target_files (str): Optional comma- or newline-separated file paths.
        max_files (int): Maximum inferred files when target_files is omitted.
    """
    change_set = get_change_set(runtime=runtime)
    workspace_dir = None
    if change_set:
        workspace_dir = change_set.workspace_dir
    elif runtime and getattr(runtime, "workspace_dir", None):
        workspace_dir = runtime.workspace_dir
    if not workspace_dir:
        return "Error: Workspace state is not available."
    decision_service = getattr(runtime, "decision_service", None) if runtime else None
    return EditPlanner(workspace_dir, decision_service=decision_service).format_plan(
        task_goal=task_goal,
        target_files=target_files,
        max_files=max_files,
    )
