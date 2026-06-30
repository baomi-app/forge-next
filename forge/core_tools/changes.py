from typing import Any, Optional

from forge.tool_registry import tool


@tool
def change_summary(
    include_diff: bool = True,
    session: Optional[Any] = None,
    runner: Optional[Any] = None,
) -> str:
    """Show the current task transaction changes, optionally including a unified diff.

    Args:
        include_diff (bool): Include a unified diff when true. Defaults to True.
    """
    change_set = get_change_set(session=session, runner=runner)
    if not change_set:
        return "Error: Change transaction state is not available."
    if include_diff:
        return change_set.diff()
    return change_set.summary()


@tool
def revert_changes(
    session: Optional[Any] = None,
    runner: Optional[Any] = None,
) -> str:
    """Revert all file changes made since the current task transaction baseline."""
    change_set = get_change_set(session=session, runner=runner)
    if not change_set:
        return "Error: Change transaction state is not available."
    return change_set.revert()


def get_change_set(session: Optional[Any] = None, runner: Optional[Any] = None):
    if session and getattr(session, "change_set", None):
        return session.change_set
    if runner and getattr(runner, "change_set", None):
        return runner.change_set
    return None
