import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner


class RepoMapMockModel(BaseModel):
    """Demonstrates repository orientation before choosing files to edit."""

    def __init__(self):
        self.step_idx = 0

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1

        if self.step_idx == 1:
            print("[MockModel] Thinking: I should map the repository before editing.")
            return (
                "I will inspect the repository map to find entry points and linked tests.",
                [{"id": "repo_map_1", "type": "function", "function": {
                    "name": "inspect_repo_map",
                    "arguments": json.dumps({
                        "directory": ".",
                        "task_goal": "update app value test",
                        "max_files": 20,
                    }),
                }}],
            )

        if self.step_idx == 2:
            print("[MockModel] Thinking: The map points to app.py and tests/test_app.py.")
            return (
                "I will read the mapped runtime file and test before editing.",
                [
                    {"id": "repo_map_2a", "type": "function", "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"filepath": "app.py"}),
                    }},
                    {"id": "repo_map_2b", "type": "function", "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"filepath": "tests/test_app.py"}),
                    }},
                ],
            )

        if self.step_idx == 3:
            print("[MockModel] Thinking: I will patch the runtime and matching test.")
            return (
                "I will update value() and its linked test.",
                [
                    {"id": "repo_map_3a", "type": "function", "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "app.py",
                            "target": "def value():\n    return 1",
                            "replacement": "def value():\n    return 2",
                        }),
                    }},
                    {"id": "repo_map_3b", "type": "function", "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "tests/test_app.py",
                            "target": "self.assertEqual(value(), 1)",
                            "replacement": "self.assertEqual(value(), 2)",
                        }),
                    }},
                ],
            )

        if self.step_idx == 4:
            print("[MockModel] Thinking: I will run the linked unit test.")
            return (
                "I will run the mapped unit test.",
                [{"id": "repo_map_4", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -m unittest tests.test_app"}),
                }}],
            )

        return ("The repository map identified the entry point, runtime file, and linked test.", None)


def setup_environment(workspace: str):
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(os.path.join(workspace, "tests"))

    print("[Demo Setup] Creating app.py...")
    with open(os.path.join(workspace, "app.py"), "w", encoding="utf-8") as f:
        f.write("""def value():
    return 1


if __name__ == "__main__":
    print(value())
""")

    print("[Demo Setup] Creating tests/test_app.py...")
    with open(os.path.join(workspace, "tests", "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(workspace, "tests", "test_app.py"), "w", encoding="utf-8") as f:
        f.write("""import unittest
from app import value


class TestApp(unittest.TestCase):
    def test_value(self):
        self.assertEqual(value(), 1)
""")


def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing repo map workspace: {workspace}")
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_repo_map")
    setup_environment(workspace)

    try:
        model = RepoMapMockModel()
        runner = AgentRunner(
            model=model,
            workspace_dir=workspace,
            test_command="python -m unittest tests.test_app",
        )
        trace = runner.run(
            "Update app.py after using the repository map to find the matching test.",
            max_iterations=7,
            checkpoint_path="repo_map_checkpoint.json",
        )
        trace.print_summary()
    finally:
        cleanup_environment(workspace)


if __name__ == "__main__":
    main()
