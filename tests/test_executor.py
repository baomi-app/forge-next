import unittest

from forge.context import Context
from forge.executor import ToolExecutor
from forge.tool_result import ToolResult
from forge.tools import ToolRegistry
from forge.trace import StepTrace


class FakeSession:
    value = "session-value"


class FakeRuntime:
    value = "runtime-value"


class FakeSubagentManager:
    def __init__(self):
        self.calls = []

    def invoke(self, role, task):
        self.calls.append((role, task))
        return f"{role}: {task}"


class TestToolExecutor(unittest.TestCase):
    def test_executes_standard_tool_and_records_result(self):
        registry = ToolRegistry()

        @registry.register
        def greet(name: str) -> str:
            """Return a greeting."""
            return f"hello {name}"

        context = Context()
        step = StepTrace(step_idx=1)
        executor = ToolExecutor(tool_registry=registry)

        executor.execute_tool_calls([
            self._tool_call("call_1", "greet", '{"name": "Forge"}')
        ], context, step)

        self.assertEqual(context.messages[-1]["role"], "tool")
        self.assertEqual(context.messages[-1]["content"], "hello Forge")
        self.assertEqual(step.tool_results[0]["name"], "greet")
        self.assertEqual(step.tool_results[0]["status"], "success")
        self.assertEqual(step.tool_results[0]["content"], "hello Forge")

    def test_registry_returns_structured_tool_result(self):
        registry = ToolRegistry()

        @registry.register
        def greet(name: str) -> str:
            """Return a greeting."""
            return f"hello {name}"

        result = registry.execute("greet", {"name": "Forge"})

        self.assertIsInstance(result, ToolResult)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.content, "hello Forge")

    def test_registry_wraps_tool_exceptions_as_error_results(self):
        registry = ToolRegistry()

        @registry.register
        def explode() -> str:
            """Raise an error."""
            raise RuntimeError("boom")

        result = registry.execute("explode", {})

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_type, "tool_exception")
        self.assertIn("boom", result.content)
        self.assertEqual(result.metadata["exception_type"], "RuntimeError")

    def test_registry_preserves_explicit_tool_result(self):
        registry = ToolRegistry()

        @registry.register
        def structured() -> ToolResult:
            """Return a structured result."""
            return ToolResult.error("blocked", error_type="policy_block")

        result = registry.execute("structured", {})

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_type, "policy_block")
        self.assertEqual(result.content, "blocked")

    def test_records_json_argument_errors_without_executing_tool(self):
        registry = ToolRegistry()

        @registry.register
        def greet(name: str) -> str:
            """Return a greeting."""
            return f"hello {name}"

        context = Context()
        step = StepTrace(step_idx=1)
        executor = ToolExecutor(tool_registry=registry)

        executor.execute_tool_calls([
            self._tool_call("call_1", "greet", '{"name":')
        ], context, step)

        self.assertIn("Failed to parse tool arguments as JSON", context.messages[-1]["content"])
        self.assertEqual(step.tool_results[0]["tool_call_id"], "call_1")
        self.assertEqual(step.tool_results[0]["name"], "greet")
        self.assertEqual(step.tool_results[0]["status"], "error")
        self.assertEqual(step.tool_results[0]["error_type"], "invalid_json")

    def test_injects_session_into_tool_execution(self):
        registry = ToolRegistry()

        @registry.register
        def read_session(session=None) -> str:
            """Read injected session state."""
            return session.value

        context = Context()
        step = StepTrace(step_idx=1)
        executor = ToolExecutor(tool_registry=registry, session=FakeSession())

        executor.execute_tool_calls([
            self._tool_call("call_1", "read_session", "{}")
        ], context, step)

        self.assertEqual(context.messages[-1]["content"], "session-value")
        definition = registry.tool_definitions[0]["function"]["parameters"]
        self.assertNotIn("session", definition["properties"])

    def test_injects_runtime_in_preference_to_legacy_dependencies(self):
        registry = ToolRegistry()

        @registry.register
        def read_runtime(runtime=None, session=None) -> str:
            """Read injected runtime state."""
            if runtime:
                return runtime.value
            return session.value

        context = Context()
        step = StepTrace(step_idx=1)
        executor = ToolExecutor(
            tool_registry=registry,
            session=FakeSession(),
            runtime=FakeRuntime(),
        )

        executor.execute_tool_calls([
            self._tool_call("call_1", "read_runtime", "{}")
        ], context, step)

        self.assertEqual(context.messages[-1]["content"], "runtime-value")
        definition = registry.tool_definitions[0]["function"]["parameters"]
        self.assertNotIn("runtime", definition["properties"])
        self.assertNotIn("session", definition["properties"])

    def test_injects_subagent_manager_into_subagent_tool(self):
        registry = ToolRegistry()

        @registry.register
        def invoke_subagent(role: str, task: str, subagent_manager=None) -> str:
            """Invoke a subagent."""
            return subagent_manager.invoke(role=role, task=task)

        manager = FakeSubagentManager()
        context = Context()
        step = StepTrace(step_idx=1)
        executor = ToolExecutor(tool_registry=registry, subagent_manager=manager)

        executor.execute_tool_calls([
            self._tool_call("call_1", "invoke_subagent", '{"role": "QA", "task": "test it"}')
        ], context, step)

        self.assertEqual(manager.calls, [("QA", "test it")])
        self.assertEqual(context.messages[-1]["content"], "QA: test it")
        definition = registry.tool_definitions[0]["function"]["parameters"]
        self.assertNotIn("subagent_manager", definition["properties"])

    def _tool_call(self, tc_id, name, arguments):
        return {
            "id": tc_id,
            "function": {
                "name": name,
                "arguments": arguments,
            },
        }


if __name__ == "__main__":
    unittest.main()
