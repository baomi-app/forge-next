import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner


class FailureTriageMockModel(BaseModel):
    """Demonstrates verifier failure triage guiding self-correction."""

    def __init__(self):
        self.step_idx = 0

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1

        if self.step_idx == 1:
            print("[MockModel] Thinking: I will patch app.py, but accidentally choose the wrong value.")
            return (
                "I will update app.py to return the requested value.",
                [{"id": "triage_1", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "app.py",
                        "target": "def value():\n    return 1",
                        "replacement": "def value():\n    return 20",
                    })
                }}]
            )

        if self.step_idx == 2:
            print("[MockModel] Thinking: I think the change is done, so I will finish.")
            return ("I updated app.py and the task is complete.", None)

        if self.step_idx == 3:
            print("[MockModel] Thinking: The verifier triaged this as an assertion failure. I should fix the value.")
            return (
                "The failure triage says the test expectation differs from the implementation. I will correct the value.",
                [{"id": "triage_3", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "app.py",
                        "target": "def value():\n    return 20",
                        "replacement": "def value():\n    return 2",
                    })
                }}]
            )

        return ("The assertion failure was triaged and fixed.", None)


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
    print(f"\n[Demo Cleanup] Removing failure triage workspace: {workspace}")
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_failure_triage")
    setup_environment(workspace)

    try:
        model = FailureTriageMockModel()
        runner = AgentRunner(
            model=model,
            workspace_dir=workspace,
            test_command="python -m unittest test_app",
        )
        trace = runner.run(
            "Update app.py so value() returns 2 and use verifier feedback if a check fails.",
            max_iterations=6,
            checkpoint_path="failure_triage_checkpoint.json",
        )
        trace.print_summary()
    finally:
        cleanup_environment(workspace)


if __name__ == "__main__":
    main()
