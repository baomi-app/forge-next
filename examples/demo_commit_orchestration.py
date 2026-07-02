import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner


class CommitOrchestrationMockModel(BaseModel):
    """Demonstrates planning, staging, and creating an atomic commit."""

    def __init__(self):
        self.step_idx = 0

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1

        if self.step_idx == 1:
            print("[MockModel] Thinking: I will update behavior, tests, and docs.")
            return (
                "I will make a task-scoped code, test, and README update.",
                [
                    {"id": "commit_1a", "type": "function", "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "app.py",
                            "target": "def value():\n    return 1",
                            "replacement": "def value():\n    return 2",
                        }),
                    }},
                    {"id": "commit_1b", "type": "function", "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "test_app.py",
                            "target": "self.assertEqual(value(), 1)",
                            "replacement": "self.assertEqual(value(), 2)",
                        }),
                    }},
                    {"id": "commit_1c", "type": "function", "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "README.md",
                            "target": "value() returns 1.",
                            "replacement": "value() returns 2.",
                        }),
                    }},
                ],
            )

        if self.step_idx == 2:
            print("[MockModel] Thinking: I should ask for a commit plan before delivery.")
            return (
                "I will plan the commit boundary before declaring the work done.",
                [{"id": "commit_2", "type": "function", "function": {
                    "name": "plan_commit",
                    "arguments": json.dumps({"task_goal": "update app value"}),
                }}],
            )

        if self.step_idx == 3:
            print("[MockModel] Thinking: The commit plan should be ready, so I will run tests.")
            return (
                "The commit plan is ready. I will run the focused unit test.",
                [{"id": "commit_3", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -m unittest test_app"}),
                }}],
            )

        if self.step_idx == 4:
            print("[MockModel] Thinking: Tests passed, so I can create the atomic commit.")
            return (
                "Tests passed. I will create the planned atomic commit.",
                [{"id": "commit_4", "type": "function", "function": {
                    "name": "commit_changes",
                    "arguments": json.dumps({"task_goal": "update app value"}),
                }}],
            )

        return ("The code, test, docs, and atomic commit are complete.", None)


def setup_environment(workspace: str):
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace)

    print("[Demo Setup] Creating app.py...")
    with open(os.path.join(workspace, "app.py"), "w", encoding="utf-8") as f:
        f.write("""def value():
    return 1
""")

    print("[Demo Setup] Creating test_app.py...")
    with open(os.path.join(workspace, "test_app.py"), "w", encoding="utf-8") as f:
        f.write("""import unittest
from app import value


class TestApp(unittest.TestCase):
    def test_value(self):
        self.assertEqual(value(), 1)


if __name__ == '__main__':
    unittest.main()
""")

    print("[Demo Setup] Creating README.md...")
    with open(os.path.join(workspace, "README.md"), "w", encoding="utf-8") as f:
        f.write("value() returns 1.\n")

    print("[Demo Setup] Creating initial git commit...")
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "forge@example.com")
    _git(workspace, "config", "user.name", "Forge Demo")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "init")


def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing commit orchestration workspace: {workspace}")
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def _git(workspace: str, *args: str):
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def main():
    workspace = os.path.abspath("temp_commit_orchestration")
    setup_environment(workspace)

    try:
        model = CommitOrchestrationMockModel()
        runner = AgentRunner(
            model=model,
            workspace_dir=workspace,
            test_command="python -m unittest test_app",
        )
        trace = runner.run(
            "Update app.py and plan an atomic commit for the task-scoped changes.",
            max_iterations=6,
            checkpoint_path="commit_orchestration_checkpoint.json",
        )
        trace.print_summary()
    finally:
        cleanup_environment(workspace)


if __name__ == "__main__":
    main()
