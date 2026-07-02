import os
import tempfile
import unittest

from forge.tools import inspect_code_symbols, registry
from forge.sandbox import LocalRestrictedSandbox


class TestInspectCodeSymbols(unittest.TestCase):
    def test_summarizes_python_imports_classes_methods_and_functions(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(
                workspace,
                "sample.py",
                '''import os
from typing import List

class Greeter:
    """Friendly greeter."""

    def hello(self):
        """Say hello."""
        return "hello"

async def fetch_name():
    """Fetch a name."""
    return "forge"

def helper():
    return True
''',
            )

            output = inspect_code_symbols(directory=workspace)

        self.assertIn("Language: python", output)
        self.assertIn("File: sample.py", output)
        self.assertIn("- os", output)
        self.assertIn("- from typing import List", output)
        self.assertIn("- Greeter (line 4): Friendly greeter.", output)
        self.assertIn("  - hello (line 7): Say hello.", output)
        self.assertIn("- async fetch_name (line 11): Fetch a name.", output)
        self.assertIn("- helper (line 15)", output)

    def test_reports_parse_errors_without_hiding_valid_modules(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "valid.py", "def ok():\n    return True\n")
            self._write_file(workspace, "broken.py", "def broken(:\n    pass\n")

            output = inspect_code_symbols(directory=workspace)

        self.assertIn("File: valid.py", output)
        self.assertIn("- ok (line 1)", output)
        self.assertIn("Parse Errors:", output)
        self.assertIn("broken.py: syntax error", output)

    def test_sandbox_subdirectory_paths_are_relative_to_requested_directory(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "pkg/module.py", "def inside():\n    return True\n")
            sandbox = LocalRestrictedSandbox(workspace)

            output = inspect_code_symbols(directory="pkg", sandbox=sandbox)

        self.assertIn("File: module.py", output)
        self.assertNotIn("File: pkg/module.py", output)

    def test_is_registered_as_core_tool(self):
        self.assertIn("inspect_code_symbols", registry.tools)
        tool_names = [definition["function"]["name"] for definition in registry.tool_definitions]
        self.assertIn("inspect_code_symbols", tool_names)

    def test_runtime_dependencies_are_hidden_from_core_tool_schemas(self):
        hidden = {"runtime", "runner", "session", "subagent_manager", "sandbox"}
        for definition in registry.tool_definitions:
            name = definition["function"]["name"]
            properties = definition["function"]["parameters"].get("properties", {})
            exposed = hidden.intersection(properties)
            self.assertEqual(exposed, set(), f"{name} exposed hidden runtime dependencies")

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
