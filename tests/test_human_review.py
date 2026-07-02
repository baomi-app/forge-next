import os
import tempfile
import unittest

from forge.changes import ChangeSet
from forge.human_review import HumanReviewLoop
from forge.tool_capabilities import ToolCapabilities
from forge.session import AgentSession
from forge.tools import record_human_review, registry, request_human_review


class FakeSession:
    def __init__(self, change_set):
        self.change_set = change_set


class TestHumanReviewLoop(unittest.TestCase):
    def test_creates_checkpoint_with_changed_files_and_diff(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace)
            self._write_file(workspace, "app.py", "VALUE = 2\n")

            checkpoint = HumanReviewLoop().create_checkpoint(
                stage="diff",
                change_set=change_set,
                task_goal="update value",
                summary="Review app change",
            )
            output = checkpoint.format()

        self.assertIn("Status: AWAITING_APPROVAL", output)
        self.assertIn("Stage: diff", output)
        self.assertIn("modified: app.py", output)
        self.assertIn("-VALUE = 1", output)
        self.assertIn("+VALUE = 2", output)

    def test_request_human_review_returns_blocked_tool_result_and_records_journal(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            session = AgentSession(workspace, "You are a coding agent.")
            session.start("Update app")
            runtime = ToolCapabilities(
                workspace_dir=workspace,
                session=session,
                journal_recorder=session.journal_recorder,
            )
            self._write_file(workspace, "app.py", "VALUE = 2\n")

            result = request_human_review(
                stage="commit",
                task_goal="update app value",
                summary="Ready to commit",
                runtime=runtime,
            )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.error_type, "human_review_required")
        self.assertEqual(result.metadata["stage"], "commit")
        self.assertIn("Approval required before continuing.", result.content)
        self.assertEqual(session.journal.entries[-1].kind, "human_review")
        self.assertEqual(session.journal.entries[-1].summary, "commit review requested")

    def test_record_human_review_records_decision(self):
        with tempfile.TemporaryDirectory() as workspace:
            session = AgentSession(workspace, "You are a coding agent.")
            session.start("Update app")
            runtime = ToolCapabilities(
                workspace_dir=workspace,
                session=session,
                journal_recorder=session.journal_recorder,
            )

            output = record_human_review(
                stage="plan",
                decision="approved",
                notes="Proceed.",
                runtime=runtime,
            )

        self.assertIn("Decision: approved", output)
        self.assertIn("Proceed.", output)
        self.assertEqual(session.journal.entries[-1].kind, "human_review")
        self.assertEqual(session.journal.entries[-1].summary, "plan review approved")

    def test_human_review_tools_are_registered(self):
        self.assertIn("request_human_review", registry.tools)
        self.assertIn("record_human_review", registry.tools)

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
