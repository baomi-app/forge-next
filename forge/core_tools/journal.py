from typing import Any, Optional

from forge.tool_registry import tool


@tool
def journal_note(
    summary: str,
    kind: str = "note",
    details: str = "",
    runtime: Optional[Any] = None,
) -> str:
    """Record a structured task journal note for continuity across checkpoints.

    Args:
        summary (str): Short journal entry summary.
        kind (str): Entry kind such as plan, decision, failure, verification, or next_step.
        details (str): Optional supporting details.
    """
    recorder = get_journal_recorder(runtime=runtime)
    if not recorder:
        return "Error: Task journal is not available."
    entry = recorder.note(kind=kind, summary=summary, details=details)
    return f"Recorded journal entry #{entry.index} [{entry.kind}]: {entry.summary}"


@tool
def read_journal(
    max_entries: int = 20,
    runtime: Optional[Any] = None,
) -> str:
    """Read recent task journal entries."""
    journal = get_journal(runtime=runtime)
    if not journal:
        return "Error: Task journal is not available."
    return journal.format(max_entries=max_entries)


def get_journal(
    runtime: Optional[Any] = None,
    session: Optional[Any] = None,
    runner: Optional[Any] = None,
):
    if runtime and getattr(runtime, "journal", None):
        return runtime.journal
    if session and getattr(session, "journal", None):
        return session.journal
    if runner and getattr(runner, "session", None) and getattr(runner.session, "journal", None):
        return runner.session.journal
    return None


def get_journal_recorder(
    runtime: Optional[Any] = None,
    session: Optional[Any] = None,
    runner: Optional[Any] = None,
):
    if runtime and getattr(runtime, "journal_recorder", None):
        return runtime.journal_recorder
    if session and getattr(session, "journal_recorder", None):
        return session.journal_recorder
    if runner and getattr(runner, "session", None) and getattr(runner.session, "journal_recorder", None):
        return runner.session.journal_recorder
    return None
