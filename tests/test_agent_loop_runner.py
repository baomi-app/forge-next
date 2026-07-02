import os
import tempfile
import unittest

from forge.completion import CompletionResult
from forge.checkpoint import CheckpointStore
from forge.context import Context
from forge.executor import ToolExecutor
from forge.model import BaseModel
from forge.agent_loop_runner import AgentLoopRunner
from forge.tools import ToolRegistry
from forge.trace import ExecutionTrace


class ScriptedModel(BaseModel):
    def __init__(self, responses):
        self.responses = list(responses)

    def generate(self, messages, tools=None):
        return self.responses.pop(0)


class PassingCompletionGate:
    def evaluate(self, content, context, trace, step):
        step.stop_timer()
        trace.add_step(step)
        trace.finish(content or "")
        return CompletionResult(passed=True, report="ok")


class TestAgentLoopRunner(unittest.TestCase):
    def test_executes_tool_turn_and_saves_checkpoint(self):
        registry = ToolRegistry()

        @registry.register
        def greet(name: str) -> str:
            """Return a greeting."""
            return f"hello {name}"

        tool_call = {
            "id": "call_1",
            "function": {
                "name": "greet",
                "arguments": '{"name": "Forge"}',
            },
        }
        saved_iterations = []
        runtime = AgentLoopRunner(
            model=ScriptedModel([
                ("I will call a tool.", [tool_call]),
                ("done", None),
            ]),
            tool_registry=registry,
            tool_executor=ToolExecutor(tool_registry=registry),
            completion_gate=PassingCompletionGate(),
            checkpoint_saver=lambda path, iteration, context, trace: saved_iterations.append(iteration),
        )
        context = Context(system_prompt="system")
        context.add_user("say hello")
        trace = ExecutionTrace("say hello")

        runtime.run_loop(
            context=context,
            trace=trace,
            start_iteration=0,
            max_iterations=2,
            checkpoint_path="checkpoint.json",
        )

        self.assertEqual(saved_iterations, [1])
        self.assertEqual(context.messages[-1]["content"], "hello Forge")
        self.assertEqual(trace.final_response, "done")

    def test_removes_checkpoint_when_completion_passes(self):
        with tempfile.TemporaryDirectory() as workspace:
            checkpoint_path = os.path.join(workspace, "checkpoint.json")
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                f.write("{}")

            runtime = AgentLoopRunner(
                model=ScriptedModel([("done", None)]),
                tool_registry=ToolRegistry(),
                tool_executor=ToolExecutor(tool_registry=ToolRegistry()),
                completion_gate=PassingCompletionGate(),
                checkpoint_store=CheckpointStore(workspace),
            )
            context = Context(system_prompt="system")
            context.add_user("finish")
            trace = ExecutionTrace("finish")

            runtime.run_loop(
                context=context,
                trace=trace,
                start_iteration=0,
                max_iterations=1,
                checkpoint_path=checkpoint_path,
            )

            self.assertFalse(os.path.exists(checkpoint_path))
            self.assertEqual(trace.final_response, "done")


if __name__ == "__main__":
    unittest.main()
