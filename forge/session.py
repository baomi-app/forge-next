import json
import os
from typing import Any, Dict, Optional

from forge.changes import ChangeSet
from forge.context import Context
from forge.trace import ExecutionTrace, StepTrace


class AgentSession:
    """Owns per-run agent state and checkpoint serialization."""

    def __init__(
        self,
        workspace_dir: str,
        system_prompt: str,
        test_command: Optional[str] = None,
        change_set: Optional[ChangeSet] = None,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.system_prompt = system_prompt
        self.test_command = test_command
        self.change_set = change_set or ChangeSet(self.workspace_dir)
        self.context = Context(system_prompt=self.system_prompt)
        self.trace: Optional[ExecutionTrace] = None
        self.current_iteration = 0

    def start(self, task: str) -> None:
        """Start a fresh task while keeping the current transaction baseline."""
        self.current_iteration = 0
        self.context = Context(system_prompt=self.system_prompt)
        self.context.add_user(task)
        self.trace = ExecutionTrace(task)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the current session state for checkpointing."""
        if self.trace is None:
            raise ValueError("Cannot checkpoint a session before it has started.")

        return {
            "task": self.trace.task,
            "current_iteration": self.current_iteration,
            "system_prompt": self.system_prompt,
            "messages": self.context.messages,
            "test_command": self.test_command,
            "change_set": self.change_set.to_dict(),
            "trace_steps": [step.to_dict() for step in self.trace.steps],
        }

    def restore_from_dict(self, data: Dict[str, Any]) -> str:
        """Restore a session from checkpoint data and return the task."""
        task = data["task"]
        context = Context(system_prompt=None)
        context.messages = data["messages"]

        trace = ExecutionTrace(task)
        for step_data in data["trace_steps"]:
            trace.add_step(StepTrace.from_dict(step_data))

        change_set = ChangeSet(self.workspace_dir)
        if data.get("change_set"):
            change_set.restore_from_dict(data["change_set"])

        self.system_prompt = data.get("system_prompt", self.system_prompt)
        self.test_command = data.get("test_command", self.test_command)
        self.current_iteration = data["current_iteration"]
        self.context = context
        self.trace = trace
        self.change_set = change_set
        return task

    def save_checkpoint(self, filepath: str) -> None:
        """Write the current session state to a checkpoint file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def load_checkpoint(self, filepath: str) -> Dict[str, Any]:
        """Read checkpoint data from disk."""
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def restore_checkpoint(self, filepath: str) -> str:
        """Restore this session from a checkpoint file and return the task."""
        return self.restore_from_dict(self.load_checkpoint(filepath))
