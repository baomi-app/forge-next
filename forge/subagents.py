from typing import Any, Optional


class SubagentManager:
    """Creates and runs specialized child agents for a parent runner."""

    def __init__(
        self,
        parent_runner: Any,
        runner_cls: Optional[Any] = None,
        max_iterations: int = 4,
    ):
        self.parent_runner = parent_runner
        self.runner_cls = runner_cls
        self.max_iterations = max_iterations

    def invoke(self, role: str, task: str) -> str:
        """Run a specialized subagent in the parent runner's workspace."""
        parent = self.parent_runner
        runner_cls = self.runner_cls or self._load_runner_cls()

        print(f"\n[Parent Agent] Spawning subagent '{role}' to solve task: '{task}'")

        sub_runner = runner_cls(
            model=parent.model,
            system_prompt=self._build_system_prompt(role, task),
            workspace_dir=parent.workspace_dir,
            test_command=parent.verifier.test_command,
            tool_registry=parent.tool_registry,
            model_lock=parent.model_lock,
            tool_lock=parent.tool_lock,
        )

        sub_runner.sandbox = parent.sandbox
        sub_checkpoint = f"subagent_{role.lower()}_checkpoint.json"

        try:
            sub_trace = sub_runner.run(
                task=task,
                max_iterations=self.max_iterations,
                checkpoint_path=sub_checkpoint,
            )
            print(f"[Parent Agent] Subagent '{role}' finished execution.")
            return f"[Subagent '{role}' Report]:\n{sub_trace.final_response}"
        except Exception as e:
            return f"Error executing subagent '{role}': {str(e)}"

    def _build_system_prompt(self, role: str, task: str) -> str:
        return (
            f"You are a specialized subagent acting as: '{role}'.\n"
            f"Your task is: '{task}'.\n"
            "Perform your tasks and return a concise summary of your work when done."
        )

    def _load_runner_cls(self):
        from forge.runner import AgentRunner

        return AgentRunner
