import unittest

from forge.completion import CompletionGate
from forge.context import Context
from forge.trace import ExecutionTrace, StepTrace


class FakeVerifier:
    def __init__(self, passed, report):
        self.passed = passed
        self.report = report

    def verify(self):
        return self.passed, self.report


class TestCompletionGate(unittest.TestCase):
    def test_passed_completion_finishes_trace(self):
        context = Context()
        trace = ExecutionTrace("Finish task")
        step = StepTrace(step_idx=1)
        step.start_timer()
        gate = CompletionGate(FakeVerifier(True, "ok"))

        result = gate.evaluate("done", context, trace, step)

        self.assertTrue(result.passed)
        self.assertEqual(result.report, "ok")
        self.assertEqual(trace.final_response, "done")
        self.assertEqual(len(trace.steps), 1)
        self.assertEqual(context.messages, [])

    def test_blocked_completion_feeds_report_back_to_context_and_trace(self):
        context = Context()
        trace = ExecutionTrace("Finish task")
        step = StepTrace(step_idx=1)
        step.start_timer()
        gate = CompletionGate(FakeVerifier(False, "tests failed"))

        result = gate.evaluate("done", context, trace, step)

        self.assertFalse(result.passed)
        self.assertEqual(result.report, "tests failed")
        self.assertIsNone(trace.final_response)
        self.assertEqual(len(trace.steps), 1)
        self.assertEqual(context.messages[0]["role"], "assistant")
        self.assertEqual(context.messages[0]["content"], "done")
        self.assertEqual(context.messages[1]["role"], "user")
        self.assertEqual(context.messages[1]["content"], "tests failed")
        self.assertEqual(step.tool_results[0]["tool_call_id"], "verifier_check")
        self.assertEqual(step.tool_results[0]["name"], "auto_verifier")
        self.assertEqual(step.tool_results[0]["status"], "error")
        self.assertEqual(step.tool_results[0]["error_type"], "verification_failed")
        self.assertEqual(step.tool_results[0]["content"], "tests failed")


if __name__ == "__main__":
    unittest.main()
