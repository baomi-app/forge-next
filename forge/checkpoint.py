import json
import os
from typing import Any, Dict

from forge.session import AgentSession


class CheckpointStore:
    """Persists and restores agent session checkpoints."""

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = os.path.abspath(workspace_dir)

    def resolve(self, filepath: str) -> str:
        """Resolve checkpoint paths relative to the workspace."""
        if os.path.isabs(filepath):
            return filepath
        return os.path.join(self.workspace_dir, filepath)

    def exists(self, filepath: str) -> bool:
        return os.path.exists(self.resolve(filepath))

    def save(self, filepath: str, session: AgentSession) -> None:
        path = self.resolve(filepath)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)

    def load(self, filepath: str) -> Dict[str, Any]:
        with open(self.resolve(filepath), "r", encoding="utf-8") as f:
            return json.load(f)

    def restore(self, filepath: str, session: AgentSession) -> str:
        return session.restore_from_dict(self.load(filepath))

    def delete(self, filepath: str) -> bool:
        path = self.resolve(filepath)
        if not os.path.exists(path):
            return False
        os.remove(path)
        return True
