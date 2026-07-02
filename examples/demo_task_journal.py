import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner


class TaskJournalMockModel(BaseModel):
    """Demonstrates persistent task journal notes during a coding task."""

    def __init__(self):
        self.step_idx = 0

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1

        if self.step_idx == 1:
            print("[MockModel] Thinking: I should record the plan before editing.")
            return (
                "I will record my plan and then build an edit strategy.",
                [
                    {"id": "journal_1a", "type": "function", "function": {
                        "name": "journal_note",
                        "arguments": json.dumps({
                            "kind": "plan",
                            "summary": "Update value behavior with matching test coverage.",
                            "details": "Touch app.py and test_app.py, then run the focused unit test.",
                        }),
                    }},
                    {"id": "journal_1b", "type": "function", "function": {
                        "name": "plan_edits",
                        "arguments": json.dumps({
                            "task_goal": "update app value",
                            "target_files": "app.py,test_app.py",
                        }),
                    }},
                ],
            )

        if self.step_idx == 2:
            print("[MockModel] Thinking: I will apply the planned edit and record the decision.")
            return (
                "I will apply the planned edits and record the implementation decision.",
                [
                    {"id": "journal_2a", "type": "function", "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "app.py",
                            "target": "def value():\n    return 1",
                            "replacement": "def value():\n    return 2",
                        }),
                    }},
                    {"id": "journal_2b", "type": "function", "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "test_app.py",
                            "target": "self.assertEqual(value(), 1)",
                            "replacement": "self.assertEqual(value(), 2)",
                        }),
                    }},
                    {"id": "journal_2c", "type": "function", "function": {
                        "name": "journal_note",
                        "arguments": json.dumps({
                            "kind": "decision",
                            "summary": "Kept change scoped to value() and its test.",
                            "details": "No unrelated files needed for this task.",
                        }),
                    }},
                ],
            )

        if self.step_idx == 3:
            print("[MockModel] Thinking: I will verify and record the outcome.")
            return (
                "I will run the focused test and record the verification outcome.",
                [
                    {"id": "journal_3a", "type": "function", "function": {
                        "name": "run_command",
                        "arguments": json.dumps({"command": "python -m unittest test_app"}),
                    }},
                    {"id": "journal_3b", "type": "function", "function": {
                        "name": "journal_note",
                        "arguments": json.dumps({
                            "kind": "verification",
                            "summary": "Focused unittest passed.",
                            "details": "python -m unittest test_app",
                        }),
                    }},
                ],
            )

        if self.step_idx == 4:
            print("[MockModel] Thinking: I will read the journal before finishing.")
            return (
                "I will read the task journal so the final state is visible.",
                [{"id": "journal_4", "type": "function", "function": {
                    "name": "read_journal",
                    "arguments": json.dumps({"max_entries": 20}),
                }}],
            )

        return ("The task journal captured the plan, decision, verification, and tool history.", None)


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


def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing task journal workspace: {workspace}")
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_task_journal")
    setup_environment(workspace)

    try:
        model = TaskJournalMockModel()
        runner = AgentRunner(
            model=model,
            workspace_dir=workspace,
            test_command="python -m unittest test_app",
        )
        trace = runner.run(
            "Update app.py while preserving a persistent task journal.",
            max_iterations=7,
            checkpoint_path="task_journal_checkpoint.json",
        )
        trace.print_summary()
    finally:
        cleanup_environment(workspace)


if __name__ == "__main__":
    main()
