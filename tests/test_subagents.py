import unittest

from forge.subagents import SubagentManager


class FakeTrace:
    final_response = "child complete"


class FakeVerifier:
    test_command = "python -m unittest"


class FakeParentRunner:
    def __init__(self):
        self.model = object()
        self.workspace_dir = "/tmp/workspace"
        self.verifier = FakeVerifier()
        self.tool_registry = object()
        self.model_lock = object()
        self.tool_lock = object()
        self.sandbox = object()


class FakeChildRunner:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.sandbox = None
        self.run_args = None
        FakeChildRunner.instances.append(self)

    def run(self, **kwargs):
        self.run_args = kwargs
        return FakeTrace()


class TestSubagentManager(unittest.TestCase):
    def setUp(self):
        FakeChildRunner.instances = []

    def test_invokes_child_runner_with_parent_runtime_resources(self):
        parent = FakeParentRunner()
        manager = SubagentManager(parent, runner_cls=FakeChildRunner)

        result = manager.invoke("QATester", "Run tests")

        child = FakeChildRunner.instances[0]
        self.assertEqual(result, "[Subagent 'QATester' Report]:\nchild complete")
        self.assertIs(child.kwargs["model"], parent.model)
        self.assertEqual(child.kwargs["workspace_dir"], parent.workspace_dir)
        self.assertEqual(child.kwargs["test_command"], parent.verifier.test_command)
        self.assertIs(child.kwargs["tool_registry"], parent.tool_registry)
        self.assertIs(child.kwargs["model_lock"], parent.model_lock)
        self.assertIs(child.kwargs["tool_lock"], parent.tool_lock)
        self.assertIs(child.sandbox, parent.sandbox)
        self.assertEqual(child.run_args["task"], "Run tests")
        self.assertEqual(child.run_args["max_iterations"], 4)
        self.assertEqual(child.run_args["checkpoint_path"], "subagent_qatester_checkpoint.json")
        self.assertIn("QATester", child.kwargs["system_prompt"])
        self.assertIn("Run tests", child.kwargs["system_prompt"])


if __name__ == "__main__":
    unittest.main()
