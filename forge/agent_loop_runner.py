import copy
from threading import RLock
from typing import Callable, Optional

from forge.checkpoint import CheckpointStore
from forge.completion import CompletionGate
from forge.context import Context
from forge.executor import ToolExecutor
from forge.model import BaseModel
from forge.tools import ToolRegistry
from forge.trace import ExecutionTrace, StepTrace


class AgentLoopRunner:
    """Advances the agent loop for a prepared session."""

    def __init__(
        self,
        model: BaseModel,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        completion_gate: CompletionGate,
        model_lock: Optional[RLock] = None,
        checkpoint_saver: Optional[Callable[[str, int, Context, ExecutionTrace], None]] = None,
        checkpoint_store: Optional[CheckpointStore] = None,
    ):
        self.model = model
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.completion_gate = completion_gate
        self.model_lock = model_lock or RLock()
        self.checkpoint_saver = checkpoint_saver
        self.checkpoint_store = checkpoint_store or CheckpointStore()

    def run_loop(
        self,
        context: Context,
        trace: ExecutionTrace,
        start_iteration: int,
        max_iterations: int,
        checkpoint_path: str,
    ) -> ExecutionTrace:
        """Run model/tool iterations until completion or max iteration exhaustion."""
        for iteration in range(start_iteration + 1, max_iterations + 1):
            print(f"\n[Runner] === Iteration {iteration} ===")

            should_stop = self.run_iteration(
                iteration=iteration,
                context=context,
                trace=trace,
                checkpoint_path=checkpoint_path,
            )
            if should_stop:
                break
        else:
            print("\n[Runner] Warning: Reached max iterations limit!")
            trace.finish("Failed: Maximum iterations reached without resolving the task.")

        return trace

    def run_iteration(
        self,
        iteration: int,
        context: Context,
        trace: ExecutionTrace,
        checkpoint_path: str,
    ) -> bool:
        """Run one model turn and return true when the loop should stop."""
        step = StepTrace(step_idx=iteration)
        step.start_timer()

        messages = context.get_messages()
        step.input_messages = copy.deepcopy(messages)
        tool_definitions = self.tool_registry.tool_definitions

        try:
            with self.model_lock:
                content, tool_calls = self.model.generate(messages, tool_definitions)
        except Exception as e:
            err_msg = f"Fatal Error calling model: {str(e)}"
            print(f"[Runner] {err_msg}")
            trace.finish(err_msg)
            return True

        step.model_text_response = content
        if tool_calls:
            step.tool_calls = tool_calls

        if content:
            print(f"[Model Thought/Message]: {content.strip()}")

        if not tool_calls:
            result = self.completion_gate.evaluate(content, context, trace, step)
            if result.passed:
                self._remove_checkpoint(checkpoint_path)
                return True

            self._save_checkpoint(checkpoint_path, iteration, context, trace)
            return False

        context.add_assistant(content, tool_calls)
        self.tool_executor.execute_tool_calls(tool_calls, context, step)

        step.stop_timer()
        trace.add_step(step)
        self._save_checkpoint(checkpoint_path, iteration, context, trace)
        return False

    def _save_checkpoint(
        self,
        checkpoint_path: str,
        iteration: int,
        context: Context,
        trace: ExecutionTrace,
    ) -> None:
        if self.checkpoint_saver:
            self.checkpoint_saver(checkpoint_path, iteration, context, trace)

    def _remove_checkpoint(self, checkpoint_path: str) -> None:
        if self.checkpoint_store.delete(checkpoint_path):
            print(f"[Checkpoint] Cleaned up temporary checkpoint file: {checkpoint_path}")
