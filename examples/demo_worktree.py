import os
import shutil
import subprocess
import sys
import tempfile

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.tool_capabilities import ToolCapabilities
from forge.tools import create_worktree_branch, inspect_worktrees, plan_worktree_branch, remove_worktree


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
    temp_root = tempfile.mkdtemp(prefix="forge_worktree_demo_")
    repo = os.path.join(temp_root, "repo")
    worktree = os.path.join(temp_root, "repo-isolated")
    try:
        os.makedirs(repo)
        write_file(repo, "app.py", "VALUE = 1\n")
        git(repo, "init")
        git(repo, "config", "user.email", "forge@example.com")
        git(repo, "config", "user.name", "Forge Demo")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "init")

        runtime = ToolCapabilities(workspace_dir=repo)
        print(plan_worktree_branch(
            branch_name="codex/isolated-demo",
            worktree_path=worktree,
            runtime=runtime,
        ))
        print()
        print(create_worktree_branch(
            branch_name="codex/isolated-demo",
            worktree_path=worktree,
            runtime=runtime,
        ))
        print()
        print(inspect_worktrees(runtime=runtime))
        print()
        print(remove_worktree(worktree_path=worktree, runtime=runtime))
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
