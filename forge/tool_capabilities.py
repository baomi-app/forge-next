from dataclasses import dataclass
from typing import Any, Optional

from forge.project import ProjectPolicy


@dataclass
class ToolCapabilities:
    """Narrow runtime capabilities exposed to tools."""

    workspace_dir: str
    sandbox: Optional[Any] = None
    session: Optional[Any] = None
    subagent_manager: Optional[Any] = None
    journal_recorder: Optional[Any] = None
    policy: Optional[ProjectPolicy] = None
    decision_service: Optional[Any] = None

    @property
    def change_set(self):
        if self.session and getattr(self.session, "change_set", None):
            return self.session.change_set
        return None

    @property
    def journal(self):
        if self.session and getattr(self.session, "journal", None):
            return self.session.journal
        return None

    def project_policy(self) -> ProjectPolicy:
        if self.policy:
            return self.policy
        change_set = self.change_set
        if change_set and getattr(change_set, "policy", None):
            return change_set.policy
        return ProjectPolicy()
