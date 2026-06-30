import json
import os
import sys
import tempfile
import unittest

from forge.verifier import Verifier, VerificationCheck


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

    def test_classifies_common_failure_types(self):
        verifier = Verifier()

        self.assertEqual(
            verifier._classify_failure(
                VerificationCheck("pytest", "python -m pytest", "test", "pytest configuration"),
                "ModuleNotFoundError: No module named 'requests'",
                1,
            ),
            "missing_dependency",
        )
        self.assertEqual(
            verifier._classify_failure(
                VerificationCheck("lint", "npm run lint", "lint", "package.json"),
                "Unexpected trailing whitespace",
                1,
            ),
            "lint_failure",
        )
        self.assertEqual(
            verifier._classify_failure(
                VerificationCheck("typecheck", "npm run typecheck", "typecheck", "package.json"),
                "Type 'string' is not assignable to type 'number'",
                1,
            ),
            "typecheck_failure",
        )

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
