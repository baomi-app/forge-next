import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner


class ChangeReviewMockModel(BaseModel):
    """Demonstrates reviewing task-scoped changes before finishing."""

    def __init__(self):
        self.step_idx = 0

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1

        if self.step_idx == 1:
            print("[MockModel] Thinking: I will change the pricing behavior first.")
            return (
                "I will implement the requested discount logic in shop.py.",
                [{"id": "rvw_1", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "shop.py",
                        "target": "def discounted_price(price):\n    return price",
                        "replacement": "def discounted_price(price):\n    return price * 0.9",
                    })
                }}]
            )

        if self.step_idx == 2:
            print("[MockModel] Thinking: I should review the transaction before declaring done.")
            return (
                "I will review the current transaction to check delivery readiness.",
                [{"id": "rvw_2", "type": "function", "function": {
                    "name": "review_changes",
                    "arguments": json.dumps({"task_goal": "add discounted price behavior"})
                }}]
            )

        if self.step_idx == 3:
            print("[MockModel] Thinking: Review warned that tests did not change. I will update them.")
            return (
                "The review warned that code changed without tests. I will update the unit test.",
                [{"id": "rvw_3", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "test_shop.py",
                        "target": "        self.assertEqual(discounted_price(100), 100)",
                        "replacement": "        self.assertEqual(discounted_price(100), 90)",
                    })
                }}]
            )

        if self.step_idx == 4:
            print("[MockModel] Thinking: I will review again after updating tests.")
            return (
                "I will run the change review again now that tests were updated.",
                [{"id": "rvw_4", "type": "function", "function": {
                    "name": "review_changes",
                    "arguments": json.dumps({"task_goal": "add discounted price behavior"})
                }}]
            )

        if self.step_idx == 5:
            print("[MockModel] Thinking: Review passed. I will run tests.")
            return (
                "The change review is clean, so I will run the focused tests.",
                [{"id": "rvw_5", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -m unittest test_shop.py"})
                }}]
            )

        return ("The discount behavior was implemented, reviewed, and verified with tests.", None)


def setup_environment(workspace: str):
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace)

    print("[Demo Setup] Creating shop.py...")
    with open(os.path.join(workspace, "shop.py"), "w", encoding="utf-8") as f:
        f.write("""def discounted_price(price):
    return price
""")

    print("[Demo Setup] Creating test_shop.py...")
    with open(os.path.join(workspace, "test_shop.py"), "w", encoding="utf-8") as f:
        f.write("""import unittest
from shop import discounted_price


class TestShop(unittest.TestCase):
    def test_discounted_price(self):
        self.assertEqual(discounted_price(100), 100)


if __name__ == '__main__':
    unittest.main()
""")


def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing change review workspace: {workspace}")
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_review")
    setup_environment(workspace)

    try:
        model = ChangeReviewMockModel()
        runner = AgentRunner(
            model=model,
            workspace_dir=workspace,
            test_command="python -m unittest test_shop.py"
        )
        trace = runner.run(
            "Add discounted price behavior and ensure the final transaction is review-ready.",
            max_iterations=8,
            checkpoint_path="review_checkpoint.json"
        )
        trace.print_summary()
    finally:
        cleanup_environment(workspace)


if __name__ == "__main__":
    main()
