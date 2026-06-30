import os
import inspect
import shlex
import subprocess
from typing import Callable, Dict, Any, List, Optional
from forge.sandbox import BaseSandbox

class ToolRegistry:
    """Manages coding tools registration, schema generation, and dependency injection execution."""

    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []

    def register(self, func: Callable) -> Callable:
        name = func.__name__
        self.tools[name] = func

        # Generate tool schema from signature & docstring
        sig = inspect.signature(func)
        doc = func.__doc__ or ""
        description = doc.strip().split("\n")[0] if doc else "No description provided."

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            # Exclude hidden parameters not exposed to LLM
            if param_name in ("self", "cls", "sandbox"):
                continue

            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == float:
                param_type = "number"
            elif param.annotation == bool:
                param_type = "boolean"

            properties[param_name] = {
                "type": param_type,
                "description": f"Parameter '{param_name}'"
            }

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        definition = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
        self.tool_definitions.append(definition)
        return func

    def execute(self, name: str, args: Dict[str, Any], sandbox: Optional[BaseSandbox] = None) -> str:
        """Executes a registered tool, dynamically injecting the runner's Sandbox instance."""
        if name not in self.tools:
            return f"Error: Tool '{name}' is not registered."
        try:
            # Check tool signature for 'sandbox' and inject if expected
            sig = inspect.signature(self.tools[name])
            if "sandbox" in sig.parameters:
                args["sandbox"] = sandbox

            result = self.tools[name](**args)
            return str(result)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"


# Global registry
registry = ToolRegistry()

def tool(func: Callable) -> Callable:
    """Decorator to register a function as a tool."""
    return registry.register(func)

# --- Define the 7 Core Coding Tools ---

# Exclude list for file/directory walking
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", ".agents", "node_modules", ".gemini"}

@tool
def list_files(directory: str = ".", sandbox: Optional[BaseSandbox] = None) -> str:
    """List all files recursively in the specified directory, excluding build artifacts and version control.

    Args:
        directory (str): The root directory to list files from. Defaults to '.'.
    """
    try:
        if sandbox:
            target_dir = sandbox._validate_path(directory)
        else:
            target_dir = os.path.abspath(directory)

        file_list = []
        for root, dirs, files in os.walk(target_dir):
            # Prune excluded directories in-place so walk doesn't visit them
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), target_dir)
                file_list.append(rel_path)

        if not file_list:
            return "No files found in directory."
        return "\n".join(file_list)
    except Exception as e:
        return f"Error listing files: {str(e)}"


@tool
def search_code(query: str, directory: str = ".", sandbox: Optional[BaseSandbox] = None) -> str:
    """Search for a literal query string in all codebase files.

    Args:
        query (str): The string to search for.
        directory (str): The directory to search in. Defaults to '.'.
    """
    try:
        if sandbox:
            target_dir = sandbox._validate_path(directory)
        else:
            target_dir = os.path.abspath(directory)

        matches = []
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                full_path = os.path.join(root, file)
                # Skip binary files or large files simply by checking extension/try reading
                if file.endswith(('.png', '.jpg', '.jpeg', '.gif', '.pyc', '.pyo', '.db', '.zip', '.tar.gz')):
                    continue
                try:
                    # Leverage sandbox for read boundary checks
                    if sandbox:
                        rel_file = os.path.relpath(full_path, sandbox.workspace_dir)
                        content = sandbox.read_file(rel_file)
                    else:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()

                    for line_num, line in enumerate(content.split('\n'), 1):
                        if query in line:
                            rel_path = os.path.relpath(full_path, target_dir)
                            matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                except Exception:
                    pass # Ignore read errors for binary or unreadable files

        if not matches:
            return f"No matches found for query: '{query}'"
        return "\n".join(matches[:100]) # Cap at 100 results
    except Exception as e:
        return f"Error searching code: {str(e)}"


@tool
def read_file(filepath: str, line_numbers: bool = True, sandbox: Optional[BaseSandbox] = None) -> str:
    """Read and return the complete contents of a file, optionally prefixed with line numbers.

    Args:
        filepath (str): The path of the file to read.
        line_numbers (bool): Prefix each line with its 1-indexed line number. Defaults to True.
    """
    try:
        if sandbox:
            content = sandbox.read_file(filepath)
        else:
            if not os.path.exists(filepath):
                return f"Error: File '{filepath}' does not exist."
            if os.path.isdir(filepath):
                return f"Error: '{filepath}' is a directory. Use list_files to see its content."
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

        if line_numbers:
            lines = content.split('\n')
            formatted = [f"{i}: {line}" for i, line in enumerate(lines, 1)]
            return "\n".join(formatted)
        return content
    except Exception as e:
        return f"Error reading file '{filepath}': {str(e)}"


@tool
def apply_patch(filepath: str, target: str, replacement: str, sandbox: Optional[BaseSandbox] = None) -> str:
    """Modify a file by replacing a single unique target block of text with a replacement block.

    Args:
        filepath (str): The path of the file to modify.
        target (str): The exact text block to search for and replace.
        replacement (str): The new text block to insert in place of the target block.
    """
    try:
        if sandbox:
            content = sandbox.read_file(filepath)
        else:
            if not os.path.exists(filepath):
                return f"Error: File '{filepath}' does not exist."
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

        occurrences = content.count(target)
        if occurrences == 0:
            return f"Error: Target text not found in '{filepath}'. Please make sure spacing, indentation, and newlines match exactly."
        elif occurrences > 1:
            return f"Error: Target text found {occurrences} times in '{filepath}'. Please provide more context lines to ensure the target is unique."

        new_content = content.replace(target, replacement)

        if sandbox:
            sandbox.write_file(filepath, new_content)
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)

        return f"Success: Applied modification to '{filepath}'."
    except Exception as e:
        return f"Error applying patch to '{filepath}': {str(e)}"


@tool
def edit_file_block(filepath: str, start_line: int, end_line: int, replacement: str, sandbox: Optional[BaseSandbox] = None) -> str:
    """Edits a specific block of text in a file by line numbers (1-indexed, inclusive).
    Replaces lines from start_line to end_line with the replacement content.

    Args:
        filepath (str): The path of the file to modify.
        start_line (int): Starting line number of the block to replace (1-indexed).
        end_line (int): Ending line number of the block to replace (1-indexed).
        replacement (str): The new lines of text to insert.
    """
    try:
        if sandbox:
            content = sandbox.read_file(filepath)
        else:
            if not os.path.exists(filepath):
                return f"Error: File '{filepath}' does not exist."
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

        lines = content.split('\n')
        total_lines = len(lines)

        if start_line < 1 or end_line > total_lines or start_line > end_line:
            return f"Error: Invalid line range {start_line} to {end_line}. File '{filepath}' has {total_lines} lines."

        replacement_lines = replacement.split('\n')
        lines[start_line - 1 : end_line] = replacement_lines
        new_content = "\n".join(lines)

        if sandbox:
            sandbox.write_file(filepath, new_content)
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)

        return f"Success: Replaced lines {start_line} to {end_line} in '{filepath}'."
    except Exception as e:
        return f"Error editing lines {start_line}-{end_line} in '{filepath}': {str(e)}"

@tool
def run_command(command: str, sandbox: Optional[BaseSandbox] = None) -> str:
    """Run a shell command in the local workspace and return stdout and stderr.

    Args:
        command (str): The shell command to run.
    """
    try:
        if sandbox:
            # Delegate command execution to sandbox with a default 10 seconds limit
            return sandbox.execute_command(command, timeout_seconds=10)
        else:
            try:
                argv = shlex.split(command)
            except ValueError as exc:
                return f"Error parsing command: {str(exc)}"

            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=10
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
def git_diff(sandbox: Optional[BaseSandbox] = None) -> str:
    """Show the git diff of the current workspace to inspect modifications."""
    try:
        if sandbox:
            return sandbox.execute_command("git diff")
        else:
            result = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                # Try to see if git is initialized
                if not os.path.exists(".git"):
                    return "Error: Not a git repository."
                return f"Error running git diff: {result.stderr}"
            diff_output = result.stdout
            if not diff_output.strip():
                return "No changes detected in git workspace."
            return diff_output
    except Exception as e:
        return f"Error executing git diff: {str(e)}"
