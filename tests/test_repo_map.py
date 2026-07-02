import os
import tempfile
import unittest

from forge.repo_map import RepoMapper
from forge.sandbox import LocalRestrictedSandbox
from forge.tools import inspect_repo_map, registry


class TestRepoMap(unittest.TestCase):
    def test_maps_roles_symbols_entrypoints_imports_and_test_links(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(
                workspace,
                "pkg/app.py",
                """def value():
    return 1
""",
            )
            self._write_file(
                workspace,
                "pkg/cli.py",
                """from pkg.app import value


def main():
    print(value())


if __name__ == "__main__":
    main()
""",
            )
            self._write_file(
                workspace,
                "tests/test_app.py",
                """import unittest
from pkg.app import value


class TestApp(unittest.TestCase):
    def test_value(self):
        self.assertEqual(value(), 1)
""",
            )
            self._write_file(workspace, "tests/__init__.py", "")
            self._write_file(workspace, "README.md", "# Demo\n")

            output = RepoMapper(workspace).format_map(task_goal="update app value tests")

        self.assertIn("Repository map:", output)
        self.assertIn("pkg/cli.py (__main__ guard)", output)
        self.assertIn("pkg/app.py [runtime; python] symbols: def value", output)
        self.assertIn("pkg/cli.py [runtime; python] symbols: def main; local imports: pkg/app.py", output)
        self.assertIn("README.md [documentation; markdown]", output)
        self.assertIn("tests/test_app.py -> pkg/app.py", output)
        self.assertIn("Suggested inspection order:", output)
        self.assertIn("- pkg/app.py", output)
        self.assertNotIn("- tests/__init__.py", output.split("File roles:")[0])

    def test_reports_parse_errors_without_hiding_valid_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "good.py", "def ok():\n    return True\n")
            self._write_file(workspace, "broken.py", "def nope(:\n    pass\n")

            output = RepoMapper(workspace).format_map()

        self.assertIn("good.py [runtime; python] symbols: def ok", output)
        self.assertIn("Parse errors:", output)
        self.assertIn("broken.py: syntax error", output)

    def test_suggests_entrypoints_when_task_goal_is_missing(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "def value():\n    return 1\n")
            self._write_file(workspace, "helper.py", "def helper():\n    return True\n")

            output = RepoMapper(workspace).format_map()

        self.assertIn("Entry points:", output)
        self.assertIn("app.py (conventional Python entry file)", output)
        self.assertIn("Suggested inspection order:\n- app.py", output)

    def test_tool_respects_sandbox_subdirectory(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "pkg/module.py", "def inside():\n    return True\n")
            self._write_file(workspace, "outside.py", "def outside():\n    return True\n")
            sandbox = LocalRestrictedSandbox(workspace)

            output = inspect_repo_map(directory="pkg", sandbox=sandbox)

        self.assertIn("module.py [runtime; python]", output)
        self.assertNotIn("outside.py", output)

    def test_is_registered_as_core_tool(self):
        self.assertIn("inspect_repo_map", registry.tools)
        tool_names = [definition["function"]["name"] for definition in registry.tool_definitions]
        self.assertIn("inspect_repo_map", tool_names)

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
