from typing import Any, Optional

from forge.tool_registry import tool


@tool
def invoke_subagent(
    role: str,
    task: str,
    runtime: Optional[Any] = None,
) -> str:
    """Spawns a specialized subagent to perform a specific sub-task in the same workspace.

    Args:
        role (str): The specialized role of the subagent (e.g. 'SecurityExpert', 'QATester').
        task (str): The specific query/sub-task for the subagent to solve.
    """
    if runtime and getattr(runtime, "subagent_manager", None):
        return runtime.subagent_manager.invoke(role=role, task=task)
    return "Error: Subagent manager was not injected."
