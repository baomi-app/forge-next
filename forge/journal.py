import re
import time
from dataclasses import dataclass
from typing import Dict, List


class JournalKind:
    """Stable task journal event kinds."""

    TASK_STARTED = "task_started"
    TOOL_RESULT = "tool_result"
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_BLOCKED = "verification_blocked"
    NOTE = "note"


@dataclass
class JournalEntry:
    """One structured task journal event."""

    index: int
    kind: str
    summary: str
    details: str
    timestamp: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "index": self.index,
            "kind": self.kind,
            "summary": self.summary,
            "details": self.details,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: Dict[str, object]) -> "JournalEntry":
        return JournalEntry(
            index=int(data["index"]),
            kind=str(data["kind"]),
            summary=str(data["summary"]),
            details=str(data.get("details", "")),
            timestamp=float(data.get("timestamp", 0.0)),
        )


class TaskJournal:
    """Persistent structured memory for one agent task."""

    def __init__(self):
        self.entries: List[JournalEntry] = []

    def record(self, kind: str, summary: str, details: str = "") -> JournalEntry:
        """Append one journal entry."""
        entry = JournalEntry(
            index=len(self.entries) + 1,
            kind=kind.strip() or "note",
            summary=summary.strip(),
            details=details.strip(),
            timestamp=time.time(),
        )
        self.entries.append(entry)
        return entry

    def to_dict(self) -> Dict[str, object]:
        return {"entries": [entry.to_dict() for entry in self.entries]}

    def restore_from_dict(self, data: Dict[str, object]):
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("Invalid journal checkpoint: entries must be a list.")
        self.entries = [JournalEntry.from_dict(entry) for entry in entries]

    def format(self, max_entries: int = 20) -> str:
        """Render recent journal entries for agent-facing output."""
        entries = self.entries[-max_entries:] if max_entries > 0 else self.entries
        lines = [
            "Task journal:",
            f"Entries: {len(self.entries)}",
        ]
        if not entries:
            lines.append("- none")
            return "\n".join(lines)

        for entry in entries:
            lines.append(f"- #{entry.index} [{entry.kind}] {entry.summary}")
            if entry.details:
                lines.append(f"  {entry.details}")
        return "\n".join(lines)


class JournalRecorder:
    """Converts runtime events into task journal entries.

    Runtime components should report domain events to this recorder instead of
    knowing journal entry kinds, summaries, truncation rules, or failure rules.
    """

    def __init__(self, journal: TaskJournal, max_detail_chars: int = 500):
        self.journal = journal
        self.max_detail_chars = max_detail_chars

    def task_started(self, task: str) -> JournalEntry:
        return self.journal.record(JournalKind.TASK_STARTED, task)

    def note(self, kind: str, summary: str, details: str = "") -> JournalEntry:
        return self.journal.record(kind or JournalKind.NOTE, summary, details)

    def tool_finished(self, tool_name: str, result) -> JournalEntry:
        content = getattr(result, "content", str(result))
        status = "failed" if self._is_failure_result(result) else "completed"
        return self.journal.record(
            JournalKind.TOOL_RESULT,
            f"{tool_name} {status}",
            self._clip(content),
        )

    def verifier_finished(self, passed: bool, report: str) -> JournalEntry:
        if passed:
            return self.journal.record(
                JournalKind.VERIFICATION_PASSED,
                "Completion verifier passed.",
                report,
            )
        return self.journal.record(
            JournalKind.VERIFICATION_BLOCKED,
            "Completion verifier blocked task completion.",
            report,
        )

    def _clip(self, text: str) -> str:
        if len(text) <= self.max_detail_chars:
            return text
        return text[:self.max_detail_chars] + "\n... [TRUNCATED JOURNAL DETAIL] ..."

    def _is_failure_result(self, result) -> bool:
        if getattr(result, "status", None) == "error":
            return True
        text = str(result).strip().lower()
        if text.startswith(("error", "[security error]", "[timeout error]")):
            return True

        match = re.search(r"command exited with status code (-?\d+)", text)
        if match:
            return match.group(1) != "0"
        return False
