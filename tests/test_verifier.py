import json
import os
import sys
import tempfile
import unittest

from forge.llm_decisions import LLMTriageDecision
from forge.verifier import Verifier, VerificationCheck


class FakeTriageService:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def triage_failure(self, check, output, exit_code):
        self.calls.append((check, output, exit_code))
        return self.decision


class TestProjectAwareVerifier(unittest.TestCase):
    def test_explicit_test_command_takes_priority(self):
        with tempfile.TemporaryDirectory() as workspace:
            verifier = Verifier(workspace_dir=workspace, test_command="python -m unittest")

            profile = verifier.discover_project()

        self.assertEqual(len(profile.checks), 1)
        self.assertEqual(profile.checks[0].command, "python -m unittest")
        self.assertEqual(profile.checks[0].source, "runner configuration")
        self.assertIn("explicitly configured", profile.notes[0])

    def test_discovers_python_unittest_files(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "def ok():\n    return True\n")
            self._write_file(
                workspace,
                "test_app.py",
                "import unittest\n\nclass TestApp(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
            )

            profile = Verifier(workspace_dir=workspace).discover_project()

        self.assertEqual(profile.languages, ["python"])
        self.assertEqual(len(profile.checks), 1)
        self.assertEqual(profile.checks[0].name, "unittest discovery")
        self.assertIn("-m unittest discover", profile.checks[0].command)

    def test_discovers_node_package_scripts(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(
                workspace,
                "package.json",
                json.dumps(
                    {
                        "scripts": {
                            "lint": "eslint .",
                            "typecheck": "tsc --noEmit",
                            "test": "node test.js",
                        }
                    }
                ),
            )

            profile = Verifier(workspace_dir=workspace).discover_project()

        commands = [check.command for check in profile.checks]
        categories = [check.category for check in profile.checks]
        self.assertEqual(profile.languages, ["node"])
        self.assertEqual(commands, ["npm run lint", "npm run typecheck", "npm test"])
        self.assertEqual(categories, ["lint", "typecheck", "test"])

    def test_discovers_go_and_rust_checks(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "go.mod", "module example.com/demo\n")
            self._write_file(workspace, "Cargo.toml", "[package]\nname = \"demo\"\nversion = \"0.1.0\"\n")

            profile = Verifier(workspace_dir=workspace).discover_project()

        commands = {check.command for check in profile.checks}
        self.assertIn("go", profile.languages)
        self.assertIn("rust", profile.languages)
        self.assertEqual(commands, {"go test ./...", "cargo test"})

    def test_run_tests_returns_structured_report_for_explicit_command(self):
        with tempfile.TemporaryDirectory() as workspace:
            command = f"{sys.executable} -c \"print('verified')\""
            passed, report = Verifier(workspace_dir=workspace, test_command=command).run_tests()

        self.assertTrue(passed)
        self.assertIn("[Project Verification]", report)
        self.assertIn("configured test command", report)
        self.assertIn("verified", report)
        self.assertIn("PASS [test]", report)

    def test_failure_classification_uses_llm_triage_decision(self):
        service = FakeTriageService(
            LLMTriageDecision(
                kind="dependency_resolution_failure",
                summary="The test could not import a required package.",
                root_cause="requests is unavailable in the environment.",
                evidence=["ModuleNotFoundError: No module named 'requests'"],
                next_step="Install requests or adjust the import path.",
                confidence=0.93,
            )
        )
        verifier = Verifier(decision_service=service)

        self.assertEqual(
            verifier._classify_failure(
                VerificationCheck("pytest", "python -m pytest", "test", "pytest configuration"),
                "ModuleNotFoundError: No module named 'requests'",
                1,
            ),
            "dependency_resolution_failure",
        )
        self.assertEqual(len(service.calls), 1)

    def test_failure_classification_reports_unavailable_llm_without_rule_fallback(self):
        verifier = Verifier()

        self.assertEqual(
            verifier._classify_failure(
                VerificationCheck("unittest", "python -m unittest", "test", "Python test files"),
                "AssertionError: 1 != 2",
                1,
            ),
            "llm_unavailable",
        )

    def test_failed_unittest_report_includes_actionable_triage(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "def value():\n    return 1\n")
            self._write_file(
                workspace,
                "test_app.py",
                "import unittest\nfrom app import value\n\n"
                "class TestApp(unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        self.assertEqual(value(), 2)\n",
            )

            service = FakeTriageService(
                LLMTriageDecision(
                    kind="assertion_failure",
                    summary="The implementation returns a value that does not match the test expectation.",
                    root_cause="value() returns 1 while the test expects 2.",
                    evidence=["AssertionError: 1 != 2"],
                    next_step="Read the failing test expectation and update value() to return the expected result.",
                    confidence=0.9,
                )
            )
            passed, report = Verifier(
                workspace_dir=workspace,
                test_command=f"{sys.executable} -m unittest test_app",
                decision_service=service,
            ).run_tests()

        self.assertFalse(passed)
        self.assertIn("[Failure Triage]", report)
        self.assertIn("kind: assertion_failure", report)
        self.assertIn("next step:", report)
        self.assertIn("failing test expectation", report)
        self.assertIn("AssertionError: 1 != 2", report)
        self.assertNotIn("  - F\n", report)

    def test_syntax_failure_report_includes_triage(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "broken.py", "def broken()\n    return 1\n")

            passed, report = Verifier(workspace_dir=workspace).verify()

        self.assertFalse(passed)
        self.assertIn("[Failure Triage]", report)
        self.assertIn("kind: syntax_error", report)
        self.assertIn("Fix the reported file and line", report)

    def test_syntax_verification_uses_project_policy_exclusions(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "def ok():\n    return True\n")
            self._write_file(workspace, "run_checkpoint.json", "not python\n")
            self._write_file(workspace, "__pycache__/broken.py", "def broken()\n    return 1\n")

            passed, report = Verifier(workspace_dir=workspace).verify()

        self.assertTrue(passed)
        self.assertIn("[VERIFIER PASSED]", report)

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
