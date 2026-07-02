import tempfile
import unittest

from forge.completion import CompletionGate
from forge.context import Context
from forge.executor import ToolExecutor
from forge.journal import JournalKind, JournalRecorder, TaskJournal
from forge.tool_capabilities import ToolCapabilities
from forge.session import AgentSession
from forge.tools import ToolRegistry, journal_note, read_journal, registry
from forge.trace import ExecutionTrace, StepTrace


class FakeVerifier:
    def __init__(self, passed, report):
        self.passed = passed
        self.report = report

    def verify(self):
        return self.passed, self.report


class TestTaskJournal(unittest.TestCase):
    def test_records_and_formats_entries(self):
        journal = TaskJournal()

        JournalRecorder(journal).note("decision", "Use focused tests", "Sibling test exists.")
        output = journal.format()

        self.assertIn("Entries: 1", output)
        self.assertIn("#1 [decision] Use focused tests", output)
        self.assertIn("Sibling test exists.", output)

    def test_session_checkpoint_persists_journal(self):
        with tempfile.TemporaryDirectory() as workspace:
            session = AgentSession(workspace, "You are a coding agent.")
            session.start("Update app")
            session.journal_recorder.note("plan", "Inspect app.py first")
            session.current_iteration = 1
            data = session.to_dict()

            restored = AgentSession(workspace, "Different prompt")
            restored.restore_from_dict(data)

        self.assertEqual(restored.journal.entries[0].kind, JournalKind.TASK_STARTED)
        self.assertEqual(restored.journal.entries[1].summary, "Inspect app.py first")

    def test_recorder_centralizes_runtime_event_policy(self):
        journal = TaskJournal()
        recorder = JournalRecorder(journal, max_detail_chars=12)

        recorder.task_started("Fix app")
        recorder.tool_finished("run_command", "Command exited with status code 1.")
        recorder.verifier_finished(False, "tests failed with long output")
        recorder.tool_finished("read_file", "abcdefghijklmnopqrstuvwxyz")

        self.assertEqual(journal.entries[0].kind, JournalKind.TASK_STARTED)
        self.assertEqual(journal.entries[1].kind, JournalKind.TOOL_RESULT)
        self.assertEqual(journal.entries[1].summary, "run_command failed")
        self.assertEqual(journal.entries[2].kind, JournalKind.VERIFICATION_BLOCKED)
        self.assertIn("TRUNCATED JOURNAL DETAIL", journal.entries[3].details)

    def test_journal_tools_use_runtime_state(self):
        with tempfile.TemporaryDirectory() as workspace:
            session = AgentSession(workspace, "You are a coding agent.")
            session.start("Update app")
            runtime = ToolCapabilities(
                workspace_dir=workspace,
                session=session,
                journal_recorder=session.journal_recorder,
            )

            result = journal_note(
                kind="decision",
                summary="Patch app.py",
                details="Small localized change.",
                runtime=runtime,
            )
            output = read_journal(runtime=runtime)

        self.assertIn("Recorded journal entry #2 [decision]", result)
        self.assertIn("Patch app.py", output)
        self.assertIn("Small localized change.", output)

    def test_tool_executor_reports_tool_results_to_recorder(self):
        registry = ToolRegistry()

        @registry.register
        def greet(name: str) -> str:
            """Return a greeting."""
            return f"hello {name}"

        with tempfile.TemporaryDirectory() as workspace:
            session = AgentSession(workspace, "You are a coding agent.")
            session.start("Greet")
            context = Context()
            step = StepTrace(step_idx=1)
            executor = ToolExecutor(
                tool_registry=registry,
                session=session,
                journal_recorder=session.journal_recorder,
            )

            executor.execute_tool_calls([
                self._tool_call("call_1", "greet", '{"name": "Forge"}')
            ], context, step)

        self.assertEqual(session.journal.entries[-1].kind, JournalKind.TOOL_RESULT)
        self.assertEqual(session.journal.entries[-1].summary, "greet completed")
        self.assertIn("hello Forge", session.journal.entries[-1].details)

    def test_completion_gate_reports_verifier_results_to_recorder(self):
        journal = TaskJournal()
        recorder = JournalRecorder(journal)
        context = Context()
        trace = ExecutionTrace("Finish task")
        step = StepTrace(step_idx=1)
        step.start_timer()

        CompletionGate(FakeVerifier(False, "tests failed"), journal_recorder=recorder).evaluate(
            "done",
            context,
            trace,
            step,
        )

        self.assertEqual(journal.entries[0].kind, JournalKind.VERIFICATION_BLOCKED)
        self.assertIn("tests failed", journal.entries[0].details)

    def test_journal_tools_are_registered(self):
        self.assertIn("journal_note", registry.tools)
        self.assertIn("read_journal", registry.tools)

    def _tool_call(self, tc_id, name, arguments):
        return {
            "id": tc_id,
            "function": {
                "name": name,
                "arguments": arguments,
            },
        }


if __name__ == "__main__":
    unittest.main()
