import os
from typing import Any, Dict, Optional

from forge.changes import ChangeSet
from forge.context import Context
from forge.journal import JournalRecorder, TaskJournal
from forge.trace import ExecutionTrace, StepTrace


class AgentSession:
    """Owns per-run agent state and checkpoint serialization."""

    def __init__(
        self,
        workspace_dir: str,
        system_prompt: str,
        test_command: Optional[str] = None,
        change_set: Optional[ChangeSet] = None,
        decision_service=None,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.system_prompt = system_prompt
        self.test_command = test_command
        self.decision_service = decision_service
        self.change_set = change_set or ChangeSet(self.workspace_dir)
        self.journal = TaskJournal()
        self.journal_recorder = JournalRecorder(self.journal)
        self.context = Context(system_prompt=self.system_prompt, decision_service=self.decision_service)
        self.trace: Optional[ExecutionTrace] = None
        self.current_iteration = 0

    def start(self, task: str) -> None:
        """Start a fresh task while keeping the current transaction baseline."""
        self.current_iteration = 0
        self.journal = TaskJournal()
        self.journal_recorder = JournalRecorder(self.journal)
        self.journal_recorder.task_started(task)
        self.context = Context(system_prompt=self.system_prompt, decision_service=self.decision_service)
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
            "journal": self.journal.to_dict(),
            "trace_steps": [step.to_dict() for step in self.trace.steps],
        }

    def restore_from_dict(self, data: Dict[str, Any]) -> str:
        """Restore a session from checkpoint data and return the task."""
        task = data["task"]
        context = Context(system_prompt=None, decision_service=self.decision_service)
        context.messages = data["messages"]

        trace = ExecutionTrace(task)
        for step_data in data["trace_steps"]:
            trace.add_step(StepTrace.from_dict(step_data))

        change_set = ChangeSet(self.workspace_dir)
        if data.get("change_set"):
            change_set.restore_from_dict(data["change_set"])
        journal = TaskJournal()
        if data.get("journal"):
            journal.restore_from_dict(data["journal"])

        self.system_prompt = data.get("system_prompt", self.system_prompt)
        self.test_command = data.get("test_command", self.test_command)
        self.current_iteration = data["current_iteration"]
        self.context = context
        self.trace = trace
        self.change_set = change_set
        self.journal = journal
        self.journal_recorder = JournalRecorder(self.journal)
        return task
