import os
from typing import Optional

from forge.sandbox import BaseSandbox
from forge.tool_registry import tool


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
                if file.endswith((".png", ".jpg", ".jpeg", ".gif", ".pyc", ".pyo", ".db", ".zip", ".tar.gz")):
                    continue
                try:
                    if sandbox:
                        rel_file = os.path.relpath(full_path, sandbox.workspace_dir)
                        content = sandbox.read_file(rel_file)
                    else:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                    for line_num, line in enumerate(content.split("\n"), 1):
                        if query in line:
                            rel_path = os.path.relpath(full_path, target_dir)
                            matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                except Exception:
                    pass

        if not matches:
            return f"No matches found for query: '{query}'"
        return "\n".join(matches[:100])
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
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

        if line_numbers:
            lines = content.split("\n")
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
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

        occurrences = content.count(target)
        if occurrences == 0:
            return f"Error: Target text not found in '{filepath}'. Please make sure spacing, indentation, and newlines match exactly."
        if occurrences > 1:
            return f"Error: Target text found {occurrences} times in '{filepath}'. Please provide more context lines to ensure the target is unique."

        new_content = content.replace(target, replacement)

        if sandbox:
            sandbox.write_file(filepath, new_content)
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)

        return f"Success: Applied modification to '{filepath}'."
    except Exception as e:
        return f"Error applying patch to '{filepath}': {str(e)}"


@tool
def edit_file_block(filepath: str, start_line: int, end_line: int, replacement: str, sandbox: Optional[BaseSandbox] = None) -> str:
    """Edits a specific block of text in a file by line numbers (1-indexed, inclusive)."""
    try:
        if sandbox:
            content = sandbox.read_file(filepath)
        else:
            if not os.path.exists(filepath):
                return f"Error: File '{filepath}' does not exist."
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

        lines = content.split("\n")
        total_lines = len(lines)

        if start_line < 1 or end_line > total_lines or start_line > end_line:
            return f"Error: Invalid line range {start_line} to {end_line}. File '{filepath}' has {total_lines} lines."

        replacement_lines = replacement.split("\n")
        lines[start_line - 1 : end_line] = replacement_lines
        new_content = "\n".join(lines)

        if sandbox:
            sandbox.write_file(filepath, new_content)
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)

        return f"Success: Replaced lines {start_line} to {end_line} in '{filepath}'."
    except Exception as e:
        return f"Error editing lines {start_line}-{end_line} in '{filepath}': {str(e)}"
