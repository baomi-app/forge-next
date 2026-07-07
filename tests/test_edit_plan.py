import os
import tempfile
import unittest

from forge.changes import ChangeSet
from forge.edit_plan import EditPlanner
from forge.llm_decisions import LLMEditPlanDecision, LLMPlannedEditDecision
from forge.tool_capabilities import ToolCapabilities
from forge.tools import plan_edits, registry


class FakeSession:
    def __init__(self, change_set):
        self.change_set = change_set


class FakeEditPlanService:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def plan_edits(self, task_goal, target_files, workspace_files, max_files):
        self.calls.append((task_goal, target_files, workspace_files, max_files))
        return self.decision


class TestEditPlanner(unittest.TestCase):
    def test_plans_explicit_target_files_before_editing(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            service = FakeEditPlanService(
                LLMEditPlanDecision(
                    status="READY",
                    files_to_inspect=["app.py", "test_app.py"],
                    planned_edits=[
                        LLMPlannedEditDecision(1, "app.py", "modify", "Update runtime value."),
                        LLMPlannedEditDecision(2, "test_app.py", "modify", "Update matching expectation."),
                    ],
                    risks=[],
                    verification_commands=["python -m unittest test_app"],
                    next_steps=["Inspect files.", "Apply edits.", "Run tests."],
                )
            )
            planner = EditPlanner(workspace, decision_service=service)

            plan = planner.plan(
                task_goal="update app value",
                target_files="app.py, test_app.py",
            )

        self.assertEqual(plan.status, "READY")
        self.assertEqual(plan.files_to_inspect, ["app.py", "test_app.py"])
        self.assertEqual([edit.path for edit in plan.planned_edits], ["app.py", "test_app.py"])
        self.assertIn("python -m unittest test_app", plan.verification_commands)
        self.assertEqual(service.calls[0][1], ["app.py", "test_app.py"])

    def test_blocks_missing_goal_or_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            plan = EditPlanner(workspace).plan(task_goal="")

        self.assertEqual(plan.status, "BLOCK")
        self.assertIn("LLM edit planning is not configured", plan.risks[0])

    def test_uses_llm_candidate_files_from_goal(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "billing.py", "def total():\n    return 1\n")
            self._write_file(workspace, "test_billing.py", "")
            self._write_file(workspace, "README.md", "Billing docs\n")
            service = FakeEditPlanService(
                LLMEditPlanDecision(
                    status="READY",
                    files_to_inspect=["billing.py", "test_billing.py"],
                    planned_edits=[
                        LLMPlannedEditDecision(1, "billing.py", "modify", "Change billing behavior."),
                        LLMPlannedEditDecision(2, "test_billing.py", "modify", "Cover billing behavior."),
                    ],
                    risks=[],
                    verification_commands=["python -m unittest test_billing"],
                    next_steps=["Read billing files."],
                )
            )

            plan = EditPlanner(workspace, decision_service=service).plan(task_goal="update billing tests")

        self.assertEqual(plan.status, "READY")
        self.assertIn("billing.py", plan.files_to_inspect)
        self.assertIn("test_billing.py", plan.files_to_inspect)

    def test_filters_unsafe_llm_paths(self):
        with tempfile.TemporaryDirectory() as workspace:
            service = FakeEditPlanService(
                LLMEditPlanDecision(
                    status="READY",
                    files_to_inspect=["../secret.py"],
                    planned_edits=[
                        LLMPlannedEditDecision(1, "../secret.py", "modify", "Unsafe path."),
                    ],
                    risks=[],
                    verification_commands=[],
                    next_steps=["Do not edit unsafe path."],
                )
            )
            plan = EditPlanner(workspace, decision_service=service).plan(task_goal="update secret")

        self.assertEqual(plan.status, "BLOCK")
        self.assertEqual(plan.planned_edits, [])
        self.assertIn("unsafe", plan.risks[0])

    def test_filters_unsafe_llm_verification_commands(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            service = FakeEditPlanService(
                LLMEditPlanDecision(
                    status="READY",
                    files_to_inspect=["app.py"],
                    planned_edits=[
                        LLMPlannedEditDecision(1, "app.py", "modify", "Update runtime value."),
                    ],
                    risks=[],
                    verification_commands=[
                        "python -m unittest test_app",
                        "rm -rf .",
                        "python -m unittest test_app",
                    ],
                    next_steps=["Patch app.py."],
                )
            )

            plan = EditPlanner(workspace, decision_service=service).plan(task_goal="update app")

        self.assertEqual(plan.verification_commands, ["python -m unittest test_app"])
        self.assertTrue(any("unsafe verification command" in risk for risk in plan.risks))

    def test_plan_edits_tool_uses_runtime_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            self._write_file(workspace, "test_app.py", "EXPECTED = 1\n")
            service = FakeEditPlanService(
                LLMEditPlanDecision(
                    status="READY",
                    files_to_inspect=["app.py"],
                    planned_edits=[
                        LLMPlannedEditDecision(1, "app.py", "modify", "Update runtime value."),
                    ],
                    risks=[],
                    verification_commands=["python -m unittest test_app"],
                    next_steps=["Patch app.py."],
                )
            )
            runtime = ToolCapabilities(
                workspace_dir=workspace,
                session=FakeSession(ChangeSet(workspace)),
                decision_service=service,
            )

            output = plan_edits(
                task_goal="update app value",
                target_files="app.py,test_app.py",
                runtime=runtime,
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
