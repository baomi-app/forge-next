import os
import tempfile
import unittest

from forge.checkpoint import CheckpointStore
from forge.session import AgentSession


class TestCheckpointStore(unittest.TestCase):
    def test_saves_and_restores_session_relative_to_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            store = CheckpointStore(workspace)
            session = AgentSession(
                workspace_dir=workspace,
                system_prompt="You are a coding agent.",
            )
            session.start("Remember me")
            session.current_iteration = 2

            store.save("checkpoint.json", session)

            restored = AgentSession(
                workspace_dir=workspace,
                system_prompt="You are a coding agent.",
            )
            task = store.restore("checkpoint.json", restored)

        self.assertEqual(task, "Remember me")
        self.assertEqual(restored.current_iteration, 2)
        self.assertEqual(restored.context.messages[1]["content"], "Remember me")

    def test_resolves_paths_and_deletes_checkpoint(self):
        with tempfile.TemporaryDirectory() as workspace:
            store = CheckpointStore(workspace)
            session = AgentSession(workspace_dir=workspace, system_prompt="system")
            session.start("Task")

            store.save("nested/checkpoint.json", session)
            path = os.path.join(workspace, "nested", "checkpoint.json")

            self.assertEqual(store.resolve("nested/checkpoint.json"), path)
            self.assertTrue(store.exists("nested/checkpoint.json"))
            self.assertTrue(store.delete("nested/checkpoint.json"))
            self.assertFalse(store.exists("nested/checkpoint.json"))
            self.assertFalse(store.delete("nested/checkpoint.json"))


if __name__ == "__main__":
    unittest.main()
