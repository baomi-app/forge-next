import os
import subprocess
import sys
import tempfile

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.tool_capabilities import ToolCapabilities
from forge.session import AgentSession
from forge.tools import plan_issue_pr_workflow, read_codebase_memory, record_pr_feedback


def write_file(workspace, relative_path, content):
    path = os.path.join(workspace, relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def git(workspace, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return result


def main():
    with tempfile.TemporaryDirectory() as workspace:
        write_file(workspace, "app.py", "VALUE = 1\n")
        git(workspace, "init")
        git(workspace, "config", "user.email", "forge@example.com")
        git(workspace, "config", "user.name", "Forge Demo")
        git(workspace, "add", ".")
        git(workspace, "commit", "-m", "init")

        session = AgentSession(workspace, "You are a coding agent.")
        session.start("Handle issue #42")
        runtime = ToolCapabilities(
            workspace_dir=workspace,
            session=session,
            journal_recorder=session.journal_recorder,
        )

        body = """Checkout validation is missing.

Acceptance Criteria
- [ ] reject empty carts
- [ ] add checkout regression tests
"""
        print(plan_issue_pr_workflow(
            reference="#42",
            title="Validate checkout",
            body=body,
            source="issue",
            runtime=runtime,
        ))
        print()
        print(record_pr_feedback(
            reference="PR #42",
            feedback="- CI failed in checkout tests\n- reviewer requested docs",
            source="review",
            decision="needs_changes",
            runtime=runtime,
        ))
        print()
        print(read_codebase_memory(query="checkout", runtime=runtime))


if __name__ == "__main__":
    main()
