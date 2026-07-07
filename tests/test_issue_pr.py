import os
import subprocess
import tempfile
import unittest

from forge.issue_pr import IssuePrWorkflow
from forge.llm_decisions import LLMIssuePrDecision
from forge.memory import CodebaseMemory
from forge.tool_capabilities import ToolCapabilities
from forge.session import AgentSession
from forge.tools import plan_issue_pr_workflow, record_pr_feedback, registry


class FakeIssuePrService:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def extract_issue_pr_context(self, title, body, feedback, source):
        self.calls.append((title, body, feedback, source))
        return self.decision


class TestIssuePrWorkflow(unittest.TestCase):
    def test_plans_workflow_from_issue_context(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)
            body = """Implement checkout validation.

Acceptance Criteria
- [ ] rejects empty carts
- [ ] updates checkout tests
"""

            service = FakeIssuePrService(
                LLMIssuePrDecision(
                    acceptance_criteria=["rejects empty carts", "updates checkout tests"],
                    feedback_items=[],
                    recommended_flow=["inspect checkout files", "run checkout tests", "run change review"],
                )
            )
            output = IssuePrWorkflow(decision_service=service).format_plan(
                workspace_dir=workspace,
                reference="#42",
                title="Validate checkout",
                body=body,
                source="issue",
            )

        self.assertIn("Source: issue", output)
        self.assertIn("Reference: #42", output)
        self.assertIn("current branch:", output)
        self.assertIn("rejects empty carts", output)
        self.assertIn("updates checkout tests", output)
        self.assertIn("run change review", output)
        self.assertEqual(service.calls[0][0], "Validate checkout")

    def test_records_feedback_to_journal_and_memory(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)
            session = AgentSession(workspace, "You are a coding agent.")
            session.start("Address PR feedback")
            service = FakeIssuePrService(
                LLMIssuePrDecision(
                    acceptance_criteria=[],
                    feedback_items=["test failure in checkout", "reviewer asked for docs"],
                    recommended_flow=["fix feedback"],
                )
            )
            runtime = ToolCapabilities(
                workspace_dir=workspace,
                session=session,
                journal_recorder=session.journal_recorder,
                decision_service=service,
            )

            output = record_pr_feedback(
                reference="PR #7",
                feedback="- test failure in checkout\n- reviewer asked for docs",
                source="review",
                decision="needs_changes",
                runtime=runtime,
            )
            memory = CodebaseMemory(workspace).format()

        self.assertIn("Decision: needs_changes", output)
        self.assertIn("test failure in checkout", output)
        self.assertEqual(session.journal.entries[-1].kind, "external_feedback")
        self.assertIn("test failure in checkout", memory)

    def test_plan_tool_uses_runtime_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._init_git_repo(workspace)
            service = FakeIssuePrService(
                LLMIssuePrDecision(
                    acceptance_criteria=["add regression test"],
                    feedback_items=[],
                    recommended_flow=["inspect failure", "add regression test"],
                )
            )
            runtime = ToolCapabilities(workspace_dir=workspace, decision_service=service)

            output = plan_issue_pr_workflow(
                reference="https://github.com/example/repo/pull/5",
                title="Fix checkout",
                body="- [ ] add regression test",
                source="pr",
                runtime=runtime,
            )

        self.assertIn("Source: pr", output)
        self.assertIn("add regression test", output)

    def test_issue_pr_tools_are_registered(self):
        self.assertIn("plan_issue_pr_workflow", registry.tools)
        self.assertIn("record_pr_feedback", registry.tools)

    def _init_git_repo(self, workspace):
        self._write_file(workspace, "app.py", "VALUE = 1\n")
        self._git(workspace, "init")
        self._git(workspace, "config", "user.email", "forge@example.com")
        self._git(workspace, "config", "user.name", "Forge Test")
        self._git(workspace, "add", ".")
        self._git(workspace, "commit", "-m", "init")

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _git(self, workspace, *args):
        result = subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        return result


if __name__ == "__main__":
    unittest.main()
