import os
from typing import Optional

from forge.repo_map import RepoMapper
from forge.sandbox import BaseSandbox
from forge.tool_registry import tool


@tool
def inspect_repo_map(
    directory: str = ".",
    task_goal: str = "",
    max_files: int = 40,
    sandbox: Optional[BaseSandbox] = None,
) -> str:
    """Build a project-level map of file roles, entry points, symbols, imports, and tests.

    Args:
        directory (str): The directory to inspect. Defaults to '.'.
        task_goal (str): Optional task goal used to rank suggested files to inspect.
        max_files (int): Maximum file-role entries to render. Defaults to 40.
    """
    try:
        if sandbox:
            target_dir = sandbox._validate_path(directory)
            workspace_dir = sandbox.workspace_dir
            rel_directory = os.path.relpath(target_dir, workspace_dir)
        else:
            workspace_dir = os.path.abspath(directory)
            rel_directory = "."

        return RepoMapper(workspace_dir).format_map(
            directory=rel_directory,
            task_goal=task_goal,
            max_files=max_files,
        )
    except Exception as exc:
        return f"Error inspecting repository map: {str(exc)}"
