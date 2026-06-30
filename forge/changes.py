import difflib
import fnmatch
import base64
import os
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class FileChange:
    """Represents one file difference from a captured workspace baseline."""

    path: str
    status: str


class ChangeSet:
    """Tracks a workspace baseline and the file changes made during one agent task."""

    def __init__(
        self,
        workspace_dir: str,
        exclude_dirs: Optional[set] = None,
        exclude_file_patterns: Optional[set] = None
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.exclude_dirs = exclude_dirs or {".git", "__pycache__", ".venv", ".agents", "node_modules", ".gemini"}
        self.exclude_file_patterns = exclude_file_patterns or {"checkpoint.json", "*_checkpoint.json"}
        self._baseline: Dict[str, bytes] = {}
        self.capture_baseline()

    def capture_baseline(self):
        """Capture the current workspace file contents as the transaction baseline."""
        self._baseline = {}
        for rel_path in self._iter_files():
            full_path = self._full_path(rel_path)
            with open(full_path, "rb") as f:
                self._baseline[rel_path] = f.read()

    def to_dict(self) -> Dict[str, object]:
        """Serialize the transaction baseline for checkpoint persistence."""
        return {
            "baseline": {
                path: base64.b64encode(content).decode("ascii")
                for path, content in self._baseline.items()
            },
            "exclude_dirs": sorted(self.exclude_dirs),
            "exclude_file_patterns": sorted(self.exclude_file_patterns),
        }

    def restore_from_dict(self, data: Dict[str, object]):
        """Restore a previously checkpointed transaction baseline."""
        baseline = data.get("baseline", {})
        if not isinstance(baseline, dict):
            raise ValueError("Invalid changeset checkpoint: baseline must be an object.")
        self._baseline = {
            path: base64.b64decode(encoded)
            for path, encoded in baseline.items()
        }
        exclude_dirs = data.get("exclude_dirs")
        if isinstance(exclude_dirs, list):
            self.exclude_dirs = set(exclude_dirs)
        exclude_file_patterns = data.get("exclude_file_patterns")
        if isinstance(exclude_file_patterns, list):
            self.exclude_file_patterns = set(exclude_file_patterns)

    def changes(self) -> List[FileChange]:
        """Return files that differ from the captured baseline."""
        current_paths = set(self._iter_files())
        baseline_paths = set(self._baseline)
        changes = []

        for path in sorted(current_paths - baseline_paths):
            changes.append(FileChange(path=path, status="added"))
        for path in sorted(baseline_paths - current_paths):
            changes.append(FileChange(path=path, status="deleted"))
        for path in sorted(current_paths & baseline_paths):
            with open(self._full_path(path), "rb") as f:
                current_content = f.read()
            if current_content != self._baseline[path]:
                changes.append(FileChange(path=path, status="modified"))

        return changes

    def summary(self) -> str:
        """Format a concise status summary for the current transaction."""
        changes = self.changes()
        if not changes:
            return "No changes in current transaction."

        counts = {"added": 0, "modified": 0, "deleted": 0}
        for change in changes:
            counts[change.status] += 1

        lines = [
            "Current transaction changes:",
            f"- added: {counts['added']}",
            f"- modified: {counts['modified']}",
            f"- deleted: {counts['deleted']}",
            "Files:",
        ]
        lines.extend(f"- {change.status}: {change.path}" for change in changes)
        return "\n".join(lines)

    def diff(self, max_chars: int = 6000) -> str:
        """Format a unified diff for text file changes in the current transaction."""
        changes = self.changes()
        if not changes:
            return "No changes in current transaction."

        parts = [self.summary()]
        for change in changes:
            before = self._baseline.get(change.path)
            after = self._read_current(change.path) if change.status != "deleted" else None

            if not self._is_text(before) or not self._is_text(after):
                parts.append(f"\n[Binary or non-text change omitted: {change.path}]")
                continue

            before_text = self._decode(before).splitlines(keepends=True) if before is not None else []
            after_text = self._decode(after).splitlines(keepends=True) if after is not None else []
            parts.append(
                "".join(
                    difflib.unified_diff(
                        before_text,
                        after_text,
                        fromfile=f"a/{change.path}",
                        tofile=f"b/{change.path}",
                    )
                )
            )

            rendered = "\n".join(parts)
            if len(rendered) > max_chars:
                return rendered[:max_chars] + "\n... [TRUNCATED CHANGESET DIFF] ..."

        return "\n".join(parts)

    def revert(self) -> str:
        """Restore the workspace to the captured baseline."""
        changes = self.changes()
        if not changes:
            return "No changes to revert."

        for change in changes:
            full_path = self._full_path(change.path)
            if change.status == "added":
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                elif os.path.exists(full_path):
                    os.remove(full_path)
                self._remove_empty_parents(os.path.dirname(full_path))
            else:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "wb") as f:
                    f.write(self._baseline[change.path])

        self.capture_baseline()
        return f"Reverted {len(changes)} file change(s) and refreshed the transaction baseline."

    def _iter_files(self) -> List[str]:
        files = []
        for root, dirs, filenames in os.walk(self.workspace_dir):
            dirs[:] = sorted(d for d in dirs if d not in self.exclude_dirs)
            for filename in sorted(filenames):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, self.workspace_dir)
                if self._is_excluded_file(rel_path):
                    continue
                files.append(rel_path)
        return files

    def _full_path(self, rel_path: str) -> str:
        return os.path.join(self.workspace_dir, rel_path)

    def _read_current(self, rel_path: str) -> Optional[bytes]:
        full_path = self._full_path(rel_path)
        if not os.path.exists(full_path):
            return None
        with open(full_path, "rb") as f:
            return f.read()

    def _is_text(self, content: Optional[bytes]) -> bool:
        if content is None:
            return True
        if b"\x00" in content:
            return False
        try:
            content.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    def _decode(self, content: Optional[bytes]) -> str:
        if content is None:
            return ""
        return content.decode("utf-8", errors="replace")

    def _is_excluded_file(self, rel_path: str) -> bool:
        basename = os.path.basename(rel_path)
        return any(
            fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(basename, pattern)
            for pattern in self.exclude_file_patterns
        )

    def _remove_empty_parents(self, directory: str):
        while os.path.commonpath([self.workspace_dir, directory]) == self.workspace_dir:
            if directory == self.workspace_dir or not os.path.isdir(directory):
                return
            try:
                os.rmdir(directory)
            except OSError:
                return
            directory = os.path.dirname(directory)
