import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner


class ChangeTransactionMockModel(BaseModel):
    """Demonstrates inspecting and reverting a task-scoped change transaction."""

    def __init__(self):
        self.step_idx = 0

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1

        if self.step_idx == 1:
            print("[MockModel] Thinking: I will inspect the target file first.")
            return (
                "I will read app.py to understand the current greeting implementation.",
                [{"id": "chg_1", "type": "function", "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"filepath": "app.py"})
                }}]
            )

        if self.step_idx == 2:
            print("[MockModel] Thinking: I will intentionally make a bad change to demonstrate rollback.")
            return (
                "I will apply an intentionally wrong edit so the transaction diff can show it.",
                [{"id": "chg_2", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "app.py",
                        "target": '    return "hi"',
                        "replacement": '    return "goodbye"'
                    })
                }}]
            )

        if self.step_idx == 3:
            print("[MockModel] Thinking: I should inspect the transaction diff before proceeding.")
            return (
                "I will inspect the current transaction to verify exactly what changed.",
                [{"id": "chg_3", "type": "function", "function": {
                    "name": "change_summary",
                    "arguments": json.dumps({"include_diff": True})
                }}]
            )

        if self.step_idx == 4:
            print("[MockModel] Thinking: The diff shows the wrong behavior. I will revert it.")
            return (
                "That change is wrong. I will roll back the current transaction to the baseline.",
                [{"id": "chg_4", "type": "function", "function": {
                    "name": "revert_changes",
                    "arguments": "{}"
                }}]
            )

        if self.step_idx == 5:
            print("[MockModel] Thinking: Now I will apply the correct fix from the clean baseline.")
            return (
                "I will apply the correct greeting expected by the tests.",
                [{"id": "chg_5", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "app.py",
                        "target": '    return "hi"',
                        "replacement": '    return "hello"'
                    })
                }}]
            )

        if self.step_idx == 6:
            print("[MockModel] Thinking: I will inspect the final transaction diff.")
            return (
                "I will inspect the transaction one more time before finishing.",
                [{"id": "chg_6", "type": "function", "function": {
                    "name": "change_summary",
                    "arguments": json.dumps({"include_diff": True})
                }}]
            )

        return ("The transaction was inspected, the bad edit was reverted, and the correct fix is now in place.", None)


def setup_environment(workspace: str):
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace)

    print("[Demo Setup] Creating app.py...")
    with open(os.path.join(workspace, "app.py"), "w", encoding="utf-8") as f:
        f.write('''def greeting():
    return "hi"
''')

    print("[Demo Setup] Creating test_app.py...")
    with open(os.path.join(workspace, "test_app.py"), "w", encoding="utf-8") as f:
        f.write('''import unittest
from app import greeting

class TestGreeting(unittest.TestCase):
    def test_greeting(self):
        self.assertEqual(greeting(), "hello")

if __name__ == '__main__':
    unittest.main()
''')


def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing change transaction workspace: {workspace}")
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_changes")
    setup_environment(workspace)

    try:
        model = ChangeTransactionMockModel()
        runner = AgentRunner(
            model=model,
            workspace_dir=workspace,
            test_command="python -m unittest test_app.py"
        )
        trace = runner.run(
            "Fix greeting() to return hello, using change transactions to inspect and revert mistakes.",
            max_iterations=8,
            checkpoint_path="changes_checkpoint.json"
        )
        trace.print_summary()
    finally:
        cleanup_environment(workspace)


if __name__ == "__main__":
    main()
