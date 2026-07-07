import json
import unittest

from forge.changes import FileChange
from forge.llm_decisions import LLMDecisionError, LLMDecisionService
from forge.model import BaseModel
from forge.verifier import VerificationCheck


class ScriptedDecisionModel(BaseModel):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, messages, tools=None):
        self.calls.append((messages, tools))
        if not self.responses:
            return "{}", None
        return self.responses.pop(0), None


class TestLLMDecisionService(unittest.TestCase):
    def test_triage_failure_parses_structured_json(self):
        model = ScriptedDecisionModel([
            json.dumps({
                "kind": "assertion_failure",
                "summary": "The behavior differs from the test expectation.",
                "root_cause": "value() returns 1 while the test expects 2.",
                "evidence": ["AssertionError: 1 != 2"],
                "next_step": "Update value() or the expectation so they agree.",
                "confidence": 0.91,
            })
        ])
        service = LLMDecisionService(model)

        decision = service.triage_failure(
            VerificationCheck("unittest", "python -m unittest", "test", "Python test files"),
            "AssertionError: 1 != 2",
            1,
        )

        self.assertEqual(decision.kind, "assertion_failure")
        self.assertEqual(decision.evidence, ["AssertionError: 1 != 2"])
        self.assertEqual(decision.confidence, 0.91)

    def test_review_changes_retries_invalid_json_once(self):
        model = ScriptedDecisionModel([
            "not json",
            json.dumps({
                "status": "WARN",
                "findings": [
                    {
                        "severity": "WARN",
                        "message": "The change needs matching test evidence.",
                        "path": "app.py",
                    }
                ],
                "commit_shape": ["review needed: coverage gap"],
                "suggested_message": "feat: update app behavior",
            }),
        ])
        service = LLMDecisionService(model, max_retries=1)

        decision = service.review_changes(
            task_goal="update app behavior",
            changes=[FileChange("app.py", "modified")],
            diff="--- a/app.py\n+++ b/app.py\n",
        )

        self.assertEqual(decision.status, "WARN")
        self.assertEqual(decision.findings[0].path, "app.py")
        self.assertEqual(len(model.calls), 2)

    def test_rejects_invalid_schema_without_rule_fallback(self):
        model = ScriptedDecisionModel([
            json.dumps({
                "kind": "assertion_failure",
                "summary": "Missing required fields.",
                "evidence": [],
                "next_step": "Try again.",
                "confidence": 1.2,
            })
        ])
        service = LLMDecisionService(model, max_retries=0)

        with self.assertRaises(LLMDecisionError):
            service.triage_failure(
                VerificationCheck("unittest", "python -m unittest", "test", "Python test files"),
                "AssertionError",
                1,
            )


if __name__ == "__main__":
    unittest.main()
