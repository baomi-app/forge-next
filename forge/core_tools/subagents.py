from typing import Any, Optional

from forge.tool_registry import tool


@tool
def invoke_subagent(
    role: str,
    task: str,
    subagent_manager: Optional[Any] = None,
    runner: Optional[Any] = None,
) -> str:
    """Spawns a specialized subagent to perform a specific sub-task in the same workspace.

    Args:
        role (str): The specialized role of the subagent (e.g. 'SecurityExpert', 'QATester').
        task (str): The specific query/sub-task for the subagent to solve.
    """
    if subagent_manager:
        return subagent_manager.invoke(role=role, task=task)
    if runner:
        from forge.subagents import SubagentManager

        return SubagentManager(runner).invoke(role=role, task=task)
    return "Error: Subagent manager was not injected."
