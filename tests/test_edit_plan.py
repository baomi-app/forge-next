import os
import tempfile
import unittest

from forge.changes import ChangeSet
from forge.edit_plan import EditPlanner
from forge.tools import plan_edits, registry


class FakeRunner:
    def __init__(self, change_set):
        self.change_set = change_set
        self.workspace_dir = change_set.workspace_dir


class TestEditPlanner(unittest.TestCase):
    def test_plans_explicit_target_files_before_editing(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            planner = EditPlanner(workspace)

            plan = planner.plan(
                task_goal="update app value",
                target_files="app.py, test_app.py",
            )

        self.assertEqual(plan.status, "READY")
        self.assertEqual(plan.files_to_inspect, ["app.py", "test_app.py"])
        self.assertEqual([edit.path for edit in plan.planned_edits], ["app.py", "test_app.py"])
        self.assertIn("python -m unittest test_app", plan.verification_commands)

    def test_blocks_missing_goal_or_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            plan = EditPlanner(workspace).plan(task_goal="")

        self.assertEqual(plan.status, "BLOCK")
        self.assertIn("Task goal is missing", plan.risks[0])
        self.assertIn("No target files", plan.risks[1])

    def test_infers_candidate_files_from_goal(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "billing.py", "def total():\n    return 1\n")
            self._write_file(workspace, "test_billing.py", "")
            self._write_file(workspace, "README.md", "Billing docs\n")

            plan = EditPlanner(workspace).plan(task_goal="update billing tests")

        self.assertEqual(plan.status, "READY")
        self.assertIn("billing.py", plan.files_to_inspect)
        self.assertIn("test_billing.py", plan.files_to_inspect)

    def test_missing_target_file_requires_review(self):
        with tempfile.TemporaryDirectory() as workspace:
            plan = EditPlanner(workspace).plan(
                task_goal="add journal support",
                target_files="forge/journal.py",
            )

        self.assertEqual(plan.status, "REVIEW")
        self.assertEqual(plan.planned_edits[0].action, "create")
        self.assertIn("Some planned files do not exist yet", plan.risks[0])

    def test_plan_edits_tool_uses_runner_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            runner = FakeRunner(ChangeSet(workspace))

            output = plan_edits(
                task_goal="update app value",
                target_files="app.py,test_app.py",
                runner=runner,
            )

        self.assertIn("Edit strategy plan", output)
        self.assertIn("Status: READY", output)
        self.assertIn("modify: app.py", output)

    def test_plan_edits_is_registered(self):
        self.assertIn("plan_edits", registry.tools)

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
