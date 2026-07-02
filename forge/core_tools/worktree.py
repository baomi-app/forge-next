from typing import Any, Optional

from forge.tool_registry import tool
from forge.worktree import WorktreeManager


def _workspace_dir(runtime: Optional[Any]) -> Optional[str]:
    return getattr(runtime, "workspace_dir", None) if runtime else None


@tool
def inspect_worktrees(runtime: Optional[Any] = None) -> str:
    """Inspect current git branch, dirty files, and registered worktrees."""
    workspace_dir = _workspace_dir(runtime)
    if not workspace_dir:
        return "Error: Workspace state is not available."
    return WorktreeManager().format_state(workspace_dir)


@tool
def plan_worktree_branch(
    branch_name: str,
    worktree_path: str = "",
    base_ref: str = "HEAD",
    runtime: Optional[Any] = None,
) -> str:
    """Plan a branch worktree for isolated agent work before creating it."""
    workspace_dir = _workspace_dir(runtime)
    if not workspace_dir:
        return "Error: Workspace state is not available."
    return WorktreeManager().format_plan(
        workspace_dir=workspace_dir,
        branch_name=branch_name,
        worktree_path=worktree_path,
        base_ref=base_ref,
    )


@tool
def create_worktree_branch(
    branch_name: str,
    worktree_path: str = "",
    base_ref: str = "HEAD",
    runtime: Optional[Any] = None,
) -> str:
    """Create a new git branch in a separate worktree for isolated work."""
    workspace_dir = _workspace_dir(runtime)
    if not workspace_dir:
        return "Error: Workspace state is not available."
    return WorktreeManager().format_create(
        workspace_dir=workspace_dir,
        branch_name=branch_name,
        worktree_path=worktree_path,
        base_ref=base_ref,
    )


@tool
def remove_worktree(
    worktree_path: str,
    force: bool = False,
    runtime: Optional[Any] = None,
) -> str:
    """Remove a git worktree after isolated work is no longer needed."""
    workspace_dir = _workspace_dir(runtime)
    if not workspace_dir:
        return "Error: Workspace state is not available."
    return WorktreeManager().format_remove(
        workspace_dir=workspace_dir,
        worktree_path=worktree_path,
        force=force,
    )
