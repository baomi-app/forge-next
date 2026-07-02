import os
import sys
import tempfile

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.tool_capabilities import ToolCapabilities
from forge.session import AgentSession
from forge.tools import record_human_review, request_human_review


def write_file(workspace, relative_path, content):
    path = os.path.join(workspace, relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    with tempfile.TemporaryDirectory() as workspace:
        write_file(workspace, "app.py", "VALUE = 1\n")
        session = AgentSession(workspace, "You are a coding agent.")
        session.start("Update app value")
        runtime = ToolCapabilities(
            workspace_dir=workspace,
            session=session,
            journal_recorder=session.journal_recorder,
        )

        write_file(workspace, "app.py", "VALUE = 2\n")

        checkpoint = request_human_review(
            stage="diff",
            task_goal="update app value",
            summary="Review the value change before commit.",
            runtime=runtime,
        )
        print(checkpoint.content)

        print()
        print(record_human_review(
            stage="diff",
            decision="approved",
            notes="Looks focused.",
            runtime=runtime,
        ))

        print()
        print(session.journal.format())


if __name__ == "__main__":
    main()
