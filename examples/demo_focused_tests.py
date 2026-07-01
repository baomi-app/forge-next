import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner


class FocusedTestsMockModel(BaseModel):
    """Demonstrates choosing focused verification from changed files."""

    def __init__(self):
        self.step_idx = 0

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1

        if self.step_idx == 1:
            print("[MockModel] Thinking: I will patch the app behavior.")
            return (
                "I will update app.py to return the expected value.",
                [{"id": "focus_1", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "app.py",
                        "target": "def value():\n    return 1",
                        "replacement": "def value():\n    return 2",
                    })
                }}]
            )

        if self.step_idx == 2:
            print("[MockModel] Thinking: I should ask for focused verification suggestions.")
            return (
                "I will ask Forge which focused tests match this transaction.",
                [{"id": "focus_2", "type": "function", "function": {
                    "name": "suggest_tests",
                    "arguments": "{}",
                }}]
            )

        if self.step_idx == 3:
            print("[MockModel] Thinking: The selector should recommend the sibling unit test.")
            return (
                "I will run the suggested focused unit test.",
                [{"id": "focus_3", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -m unittest test_app"}),
                }}]
            )

        return ("The focused test was selected from the changed file and passed.", None)


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
        self.assertEqual(value(), 2)


if __name__ == '__main__':
    unittest.main()
""")


def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing focused test workspace: {workspace}")
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_focused_tests")
    setup_environment(workspace)

    try:
        model = FocusedTestsMockModel()
        runner = AgentRunner(
            model=model,
            workspace_dir=workspace,
            test_command="python -m unittest test_app",
        )
        trace = runner.run(
            "Update app.py and use focused test selection to choose verification.",
            max_iterations=6,
            checkpoint_path="focused_checkpoint.json",
        )
        trace.print_summary()
    finally:
        cleanup_environment(workspace)


if __name__ == "__main__":
    main()
