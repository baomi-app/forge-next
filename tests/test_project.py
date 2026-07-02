import os
import tempfile
import unittest

from forge.changes import ChangeSet
from forge.project import ProjectPolicy, ProjectProfiler


class TestProjectPolicy(unittest.TestCase):
    def test_classifies_common_project_files(self):
        policy = ProjectPolicy()

        self.assertEqual(policy.role("app.py"), "runtime")
        self.assertEqual(policy.role("tests/test_app.py"), "test")
        self.assertEqual(policy.role("examples/demo_app.py"), "example")
        self.assertEqual(policy.role("README.md"), "documentation")
        self.assertEqual(policy.role("package.json"), "config")
        self.assertEqual(policy.commit_category("app.py"), "runtime code")
        self.assertEqual(policy.commit_category("pyproject.toml"), "project configuration")

    def test_excludes_checkpoint_and_generated_files(self):
        policy = ProjectPolicy()

        self.assertFalse(policy.should_track_file("checkpoint.json"))
        self.assertFalse(policy.should_track_file("run_checkpoint.json"))
        self.assertTrue(policy.is_generated_file(".vscode/settings.json"))
        self.assertTrue(policy.should_descend_dir("src"))
        self.assertFalse(policy.should_descend_dir("__pycache__"))

    def test_profiler_detects_languages_files_and_entrypoints(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "pyproject.toml", "[project]\nname = 'demo'\n")
            self._write_file(workspace, "app.py", "def value():\n    return 1\n")
            self._write_file(workspace, "tests/test_app.py", "")
            self._write_file(workspace, "README.md", "# Demo\n")
            self._write_file(workspace, "checkpoint.json", "{}\n")

            profile = ProjectProfiler(workspace).profile()

        self.assertEqual(profile.languages, ["python"])
        self.assertIn("pyproject.toml", profile.config_files)
        self.assertIn("app.py", profile.source_files)
        self.assertIn("tests/test_app.py", profile.test_files)
        self.assertIn("app.py", profile.entrypoints)
        self.assertNotIn("checkpoint.json", profile.source_files)

    def test_changeset_persists_policy_rules_compatibly(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            change_set = ChangeSet(workspace, exclude_file_patterns={"*.local"})
            data = change_set.to_dict()

            restored = ChangeSet(workspace)
            restored.restore_from_dict(data)

        self.assertIn("exclude_dirs", data)
        self.assertIn("exclude_file_patterns", data)
        self.assertFalse(restored.policy.should_track_file("debug.local"))

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
