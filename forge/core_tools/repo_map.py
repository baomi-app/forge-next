import os
from typing import Any, Optional

from forge.repo_map import RepoMapper
from forge.sandbox import BaseSandbox
from forge.tool_registry import tool


@tool
def inspect_repo_map(
    directory: str = ".",
    task_goal: str = "",
    max_files: int = 40,
    runtime: Optional[Any] = None,
    sandbox: Optional[BaseSandbox] = None,
) -> str:
    """Build a project-level map of file roles, entry points, symbols, imports, and tests.

    Args:
        directory (str): The directory to inspect. Defaults to '.'.
        task_goal (str): Optional task goal used to rank suggested files to inspect.
        max_files (int): Maximum file-role entries to render. Defaults to 40.
    """
    try:
        sandbox = sandbox or (runtime.sandbox if runtime else None)
        if sandbox:
            target_dir = sandbox._validate_path(directory)
            workspace_dir = sandbox.workspace_dir
            rel_directory = os.path.relpath(target_dir, workspace_dir)
        else:
            workspace_dir = os.path.abspath(directory)
            rel_directory = "."

        policy = runtime.project_policy() if runtime else None
        decision_service = getattr(runtime, "decision_service", None) if runtime else None
        return RepoMapper(workspace_dir, policy=policy, decision_service=decision_service).format_map(
            directory=rel_directory,
            task_goal=task_goal,
            max_files=max_files,
        )
    except Exception as exc:
        return f"Error inspecting repository map: {str(exc)}"
