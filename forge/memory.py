import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MemoryEntry:
    """One durable codebase memory item."""

    index: int
    kind: str
    summary: str
    details: str = ""
    tags: List[str] = field(default_factory=list)
    source: str = "agent"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, object]:
        return {
            "index": self.index,
            "kind": self.kind,
            "summary": self.summary,
            "details": self.details,
            "tags": self.tags,
            "source": self.source,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "MemoryEntry":
        return cls(
            index=int(data.get("index", 0)),
            kind=str(data.get("kind", "note")),
            summary=str(data.get("summary", "")),
            details=str(data.get("details", "")),
            tags=[str(tag) for tag in data.get("tags", [])],
            source=str(data.get("source", "agent")),
            created_at=float(data.get("created_at", time.time())),
        )


class CodebaseMemory:
    """Persistent project memory for conventions, decisions, and architecture notes."""

    VALID_KINDS = {"architecture", "convention", "decision", "testing", "workflow", "note"}

    def __init__(self, workspace_dir: str, memory_path: str = ".forge/memory.json"):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.memory_path = self._resolve(memory_path)

    def add(
        self,
        summary: str,
        kind: str = "note",
        details: str = "",
        tags: str = "",
        source: str = "agent",
    ) -> MemoryEntry:
        entries = self.entries()
        entry = MemoryEntry(
            index=self._next_index(entries),
            kind=self._normalize_kind(kind),
            summary=summary.strip(),
            details=details.strip(),
            tags=self._parse_tags(tags),
            source=(source or "agent").strip() or "agent",
        )
        if not entry.summary:
            raise ValueError("Memory summary is required.")
        entries.append(entry)
        self._save(entries)
        return entry

    def entries(self) -> List[MemoryEntry]:
        if not os.path.exists(self.memory_path):
            return []
        with open(self.memory_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw_entries = data.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValueError("Invalid codebase memory: entries must be a list.")
        return [MemoryEntry.from_dict(entry) for entry in raw_entries]

    def search(self, query: str = "", max_entries: int = 20) -> List[MemoryEntry]:
        entries = self.entries()
        normalized_query = query.strip().lower()
        if normalized_query:
            entries = [
                entry for entry in entries
                if normalized_query in self._search_text(entry)
            ]
        return entries[-max_entries:]

    def format(self, query: str = "", max_entries: int = 20) -> str:
        entries = self.search(query=query, max_entries=max_entries)
        title = "Codebase memory"
        if query:
            title += f" matching '{query}'"
        lines = [
            f"{title}:",
            f"Entries: {len(entries)}",
        ]
        if not entries:
            lines.append("- none")
            return "\n".join(lines)

        for entry in entries:
            tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
            lines.append(f"- #{entry.index} [{entry.kind}]{tags} {entry.summary}")
            if entry.details:
                lines.append(f"  {entry.details}")
        return "\n".join(lines)

    def _save(self, entries: List[MemoryEntry]) -> None:
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        data = {
            "version": 1,
            "entries": [entry.to_dict() for entry in entries],
        }
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _resolve(self, memory_path: str) -> str:
        if os.path.isabs(memory_path):
            return memory_path
        return os.path.join(self.workspace_dir, memory_path)

    def _next_index(self, entries: List[MemoryEntry]) -> int:
        if not entries:
            return 1
        return max(entry.index for entry in entries) + 1

    def _normalize_kind(self, kind: str) -> str:
        normalized = (kind or "note").strip().lower()
        if normalized in self.VALID_KINDS:
            return normalized
        return "note"

    def _parse_tags(self, tags: str) -> List[str]:
        return [
            tag.strip().lower()
            for tag in tags.replace("\n", ",").split(",")
            if tag.strip()
        ]

    def _search_text(self, entry: MemoryEntry) -> str:
        return " ".join([
            entry.kind,
            entry.summary,
            entry.details,
            " ".join(entry.tags),
            entry.source,
        ]).lower()
