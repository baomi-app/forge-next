from typing import Any, Optional

from forge.tool_registry import tool


@tool
def journal_note(
    summary: str,
    kind: str = "note",
    details: str = "",
    session: Optional[Any] = None,
    runner: Optional[Any] = None,
) -> str:
    """Record a structured task journal note for continuity across checkpoints.

    Args:
        summary (str): Short journal entry summary.
        kind (str): Entry kind such as plan, decision, failure, verification, or next_step.
        details (str): Optional supporting details.
    """
    recorder = get_journal_recorder(session=session, runner=runner)
    if not recorder:
        return "Error: Task journal is not available."
    entry = recorder.note(kind=kind, summary=summary, details=details)
    return f"Recorded journal entry #{entry.index} [{entry.kind}]: {entry.summary}"


@tool
def read_journal(
    max_entries: int = 20,
    session: Optional[Any] = None,
    runner: Optional[Any] = None,
) -> str:
    """Read recent task journal entries."""
    journal = get_journal(session=session, runner=runner)
    if not journal:
        return "Error: Task journal is not available."
    return journal.format(max_entries=max_entries)


def get_journal(session: Optional[Any] = None, runner: Optional[Any] = None):
    if session and getattr(session, "journal", None):
        return session.journal
    if runner and getattr(runner, "session", None) and getattr(runner.session, "journal", None):
        return runner.session.journal
    return None


def get_journal_recorder(session: Optional[Any] = None, runner: Optional[Any] = None):
    if session and getattr(session, "journal_recorder", None):
        return session.journal_recorder
    if runner and getattr(runner, "session", None) and getattr(runner.session, "journal_recorder", None):
        return runner.session.journal_recorder
    return None
