import os
import tempfile
import unittest

from forge.session import AgentSession
from forge.trace import StepTrace


class TestAgentSession(unittest.TestCase):
    def test_serializes_context_trace_and_change_set(self):
        with tempfile.TemporaryDirectory() as workspace:
            self._write_file(workspace, "app.py", "VALUE = 1\n")
            session = AgentSession(
                workspace_dir=workspace,
                system_prompt="You are a coding agent.",
                test_command="python -m unittest",
            )
            session.start("Update VALUE")
            session.context.add_assistant("I will edit the file.", None)
            step = StepTrace(step_idx=1)
            step.model_text_response = "I will edit the file."
            session.trace.add_step(step)
            session.current_iteration = 1

            self._write_file(workspace, "app.py", "VALUE = 2\n")
            data = session.to_dict()

            restored = AgentSession(
                workspace_dir=workspace,
                system_prompt="Different prompt",
                test_command=None,
            )
            task = restored.restore_from_dict(data)

            self.assertEqual(task, "Update VALUE")
            self.assertEqual(restored.system_prompt, "You are a coding agent.")
            self.assertEqual(restored.test_command, "python -m unittest")
            self.assertEqual(restored.current_iteration, 1)
            self.assertEqual(restored.context.messages, session.context.messages)
            self.assertEqual(restored.trace.steps[0].model_text_response, "I will edit the file.")
            self.assertEqual(
                [(change.path, change.status) for change in restored.change_set.changes()],
                [("app.py", "modified")],
            )

    def _write_file(self, workspace, relative_path, content):
        path = os.path.join(workspace, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
