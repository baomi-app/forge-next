from typing import Any, Optional

from forge.memory import CodebaseMemory
from forge.tool_registry import tool


def _memory(runtime: Optional[Any]) -> Optional[CodebaseMemory]:
    workspace_dir = getattr(runtime, "workspace_dir", None) if runtime else None
    if not workspace_dir:
        return None
    decision_service = getattr(runtime, "decision_service", None) if runtime else None
    return CodebaseMemory(workspace_dir, decision_service=decision_service)


@tool
def remember_codebase(
    summary: str,
    kind: str = "note",
    details: str = "",
    tags: str = "",
    source: str = "agent",
    runtime: Optional[Any] = None,
) -> str:
    """Record durable project memory such as conventions, decisions, architecture, or testing notes."""
    memory = _memory(runtime)
    if not memory:
        return "Error: Workspace state is not available."
    try:
        entry = memory.add(
            summary=summary,
            kind=kind,
            details=details,
            tags=tags,
            source=source,
        )
    except ValueError as e:
        return f"Error: {str(e)}"
    return f"Recorded codebase memory #{entry.index} [{entry.kind}]: {entry.summary}"


@tool
def read_codebase_memory(
    query: str = "",
    max_entries: int = 20,
    runtime: Optional[Any] = None,
) -> str:
    """Read durable project memory, optionally filtered by a query."""
    memory = _memory(runtime)
    if not memory:
        return "Error: Workspace state is not available."
    return memory.format(query=query, max_entries=max_entries)
