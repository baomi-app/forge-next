import os
import tempfile
import unittest

from forge.memory import CodebaseMemory
from forge.tool_capabilities import ToolCapabilities
from forge.tools import read_codebase_memory, registry, remember_codebase


class FakeMemoryRankService:
    def __init__(self, indexes):
        self.indexes = indexes
        self.calls = []

    def rank_memory_entries(self, query, entries, max_entries):
        self.calls.append((query, entries, max_entries))
        return self.indexes


class TestCodebaseMemory(unittest.TestCase):
    def test_records_and_reads_memory_entries(self):
        with tempfile.TemporaryDirectory() as workspace:
            memory = CodebaseMemory(workspace)

            entry = memory.add(
                kind="convention",
                summary="Use standard-library Python by default.",
                details="Avoid dependencies unless already required.",
                tags="python,dependencies",
            )
            output = memory.format()

        self.assertEqual(entry.index, 1)
        self.assertEqual(entry.kind, "convention")
        self.assertIn("#1 [convention] tags=python,dependencies Use standard-library Python by default.", output)
        self.assertIn("Avoid dependencies", output)

    def test_search_filters_memory_entries(self):
        with tempfile.TemporaryDirectory() as workspace:
            service = FakeMemoryRankService([1])
            memory = CodebaseMemory(workspace, decision_service=service)
            memory.add(summary="Use unittest for Python checks.", kind="testing", tags="python")
            memory.add(summary="Keep commits atomic.", kind="workflow", tags="git")

            output = memory.format(query="unittest")

        self.assertIn("Entries: 1", output)
        self.assertIn("Use unittest", output)
        self.assertNotIn("Keep commits atomic", output)
        self.assertEqual(service.calls[0][0], "unittest")

    def test_query_without_llm_returns_no_semantic_results(self):
        with tempfile.TemporaryDirectory() as workspace:
            memory = CodebaseMemory(workspace)
            memory.add(summary="Use unittest for Python checks.", kind="testing", tags="python")

            output = memory.format(query="unittest")

        self.assertIn("Entries: 0", output)
        self.assertIn("- none", output)

    def test_memory_tools_use_runtime_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            service = FakeMemoryRankService([1])
            runtime = ToolCapabilities(workspace_dir=workspace, decision_service=service)

            recorded = remember_codebase(
                kind="architecture",
                summary="ToolCapabilities injects narrow capabilities.",
                details="Core tools should avoid depending on AgentRunner.",
                tags="runtime,tools",
                runtime=runtime,
            )
            output = read_codebase_memory(query="ToolCapabilities", runtime=runtime)
            memory_path = os.path.join(workspace, ".forge", "memory.json")
            memory_exists = os.path.exists(memory_path)

        self.assertIn("Recorded codebase memory #1 [architecture]", recorded)
        self.assertIn("ToolCapabilities injects narrow capabilities", output)
        self.assertTrue(memory_exists)

    def test_memory_tools_are_registered(self):
        self.assertIn("remember_codebase", registry.tools)
        self.assertIn("read_codebase_memory", registry.tools)


if __name__ == "__main__":
    unittest.main()
