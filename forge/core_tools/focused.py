from typing import Any, Optional

from forge.core_tools.changes import get_change_set
from forge.focused import FocusedTestSelector
from forge.tool_registry import tool


@tool
def suggest_tests(
    runtime: Optional[Any] = None,
) -> str:
    """Suggest focused verification commands for the current task transaction."""
    change_set = get_change_set(runtime=runtime)
    if not change_set:
        return "Error: Change transaction state is not available."
    selector = FocusedTestSelector(change_set.workspace_dir)
    return selector.format_plan(change_set.changes())
