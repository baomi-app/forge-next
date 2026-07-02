import os
import shlex
import subprocess
from typing import Any, Optional

from forge.sandbox import BaseSandbox
from forge.tool_registry import tool


@tool
def run_command(
    command: str,
    runtime: Optional[Any] = None,
    sandbox: Optional[BaseSandbox] = None,
) -> str:
    """Run a shell command in the local workspace and return stdout and stderr.

    Args:
        command (str): The shell command to run.
    """
    try:
        sandbox = sandbox or (runtime.sandbox if runtime else None)
        if sandbox:
            return sandbox.execute_command(command, timeout_seconds=10)

        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return f"Error parsing command: {str(exc)}"

        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = []
        if result.stdout:
            output.append("[Stdout]\n" + result.stdout)
        if result.stderr:
            output.append("[Stderr]\n" + result.stderr)
        output.append(f"Command exited with status code {result.returncode}.")
        return "\n\n".join(output)
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 10 seconds."
    except Exception as e:
        return f"Error running command: {str(e)}"


@tool
def git_diff(runtime: Optional[Any] = None, sandbox: Optional[BaseSandbox] = None) -> str:
    """Show the git diff of the current workspace to inspect modifications."""
    try:
        sandbox = sandbox or (runtime.sandbox if runtime else None)
        if sandbox:
            return sandbox.execute_command("git diff")

        result = subprocess.run(
            ["git", "diff"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            if not os.path.exists(".git"):
                return "Error: Not a git repository."
            return f"Error running git diff: {result.stderr}"
        diff_output = result.stdout
        if not diff_output.strip():
            return "No changes detected in git workspace."
        return diff_output
    except Exception as e:
        return f"Error executing git diff: {str(e)}"
