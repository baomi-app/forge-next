import os
import sys
import tempfile

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.tool_capabilities import ToolCapabilities
from forge.tools import read_codebase_memory, remember_codebase


def main():
    with tempfile.TemporaryDirectory() as workspace:
        runtime = ToolCapabilities(workspace_dir=workspace)

        print(remember_codebase(
            kind="convention",
            summary="Use standard-library Python unless a dependency is already required.",
            details="This keeps examples and core runtime easy to run in isolated workspaces.",
            tags="python,dependencies",
            runtime=runtime,
        ))
        print(remember_codebase(
            kind="architecture",
            summary="Core tools receive ToolCapabilities instead of AgentRunner.",
            details="This keeps tool implementations narrow and easier to test.",
            tags="runtime,tools",
            runtime=runtime,
        ))
        print()
        print(read_codebase_memory(query="runtime", runtime=runtime))


if __name__ == "__main__":
    main()
