import tempfile
import unittest

from forge.model import BaseModel
from forge.runner import AgentRunner, build_system_prompt
from forge.tools import ToolRegistry


class IdleModel(BaseModel):
    def generate(self, messages, tools=None):
        return "done", None


class TestAgentRunnerPrompt(unittest.TestCase):
    def test_builds_default_prompt_from_registered_tools(self):
        tool_registry = ToolRegistry()

        @tool_registry.register
        def custom_tool() -> str:
            """Custom tool for prompt rendering."""
            return "ok"

        prompt = build_system_prompt(tool_registry)

        self.assertIn("custom_tool", prompt)

    def test_runner_uses_custom_registry_for_default_prompt(self):
        tool_registry = ToolRegistry()

        @tool_registry.register
        def project_tool() -> str:
            """Project-specific tool."""
            return "ok"

        with tempfile.TemporaryDirectory() as workspace:
            runner = AgentRunner(
                model=IdleModel(),
                workspace_dir=workspace,
                tool_registry=tool_registry,
            )

        self.assertIn("project_tool", runner.system_prompt)


if __name__ == "__main__":
    unittest.main()
