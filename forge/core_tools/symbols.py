import ast
import os
from typing import Optional

from forge.project import ProjectPolicy
from forge.sandbox import BaseSandbox
from forge.tool_registry import tool


@tool
def inspect_code_symbols(directory: str = ".", sandbox: Optional[BaseSandbox] = None) -> str:
    """Inspect Python files and summarize imports, classes, methods, and functions with line numbers.

    Args:
        directory (str): The directory to inspect. Defaults to '.'.
    """
    try:
        if sandbox:
            target_dir = sandbox._validate_path(directory)
            workspace_root = sandbox.workspace_dir
        else:
            target_dir = os.path.abspath(directory)

        if not os.path.exists(target_dir):
            return f"Error: Directory '{directory}' does not exist."
        if not os.path.isdir(target_dir):
            return f"Error: '{directory}' is not a directory."

        policy = ProjectPolicy()
        summaries = []
        parse_errors = []

        for root, dirs, files in os.walk(target_dir):
            dirs[:] = sorted(d for d in dirs if policy.should_descend_dir(d))
            for file in sorted(files):
                if not file.endswith(".py"):
                    continue

                full_path = os.path.join(root, file)
                display_path = os.path.relpath(full_path, target_dir)
                if not policy.should_track_file(display_path):
                    continue
                sandbox_path = os.path.relpath(full_path, workspace_root) if sandbox else display_path
                try:
                    if sandbox:
                        source = sandbox.read_file(sandbox_path)
                    else:
                        with open(full_path, "r", encoding="utf-8") as f:
                            source = f.read()
                    tree = ast.parse(source, filename=display_path)
                except SyntaxError as e:
                    parse_errors.append(f"{display_path}: syntax error at line {e.lineno}: {e.msg}")
                    continue
                except Exception as e:
                    parse_errors.append(f"{display_path}: failed to inspect: {str(e)}")
                    continue

                summary = _summarize_python_module(display_path, tree)
                if summary:
                    summaries.append(summary)

        if not summaries and not parse_errors:
            return "No Python symbols found."

        output = ["Language: python"]
        if summaries:
            output.extend(summaries)
        if parse_errors:
            output.append("Parse Errors:")
            output.extend(f"- {error}" for error in parse_errors)
        return "\n\n".join(output)
    except Exception as e:
        return f"Error inspecting code symbols: {str(e)}"


def _summarize_python_module(rel_path: str, tree: ast.AST) -> str:
    """Build a compact symbol summary for one Python module AST."""
    imports = []
    classes = []
    functions = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            imported_names = ", ".join(alias.name for alias in node.names)
            imports.append(f"from {module} import {imported_names}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_format_python_function(node))
        elif isinstance(node, ast.ClassDef):
            classes.append(_format_python_class(node))

    if not imports and not classes and not functions:
        return ""

    lines = [f"File: {rel_path}"]
    if imports:
        lines.append("Imports:")
        for item in imports[:20]:
            lines.append(f"- {item}")
        if len(imports) > 20:
            lines.append(f"- ... {len(imports) - 20} more imports")
    if classes:
        lines.append("Classes:")
        lines.extend(classes)
    if functions:
        lines.append("Functions:")
        lines.extend(functions)
    return "\n".join(lines)


def _format_python_class(node: ast.ClassDef) -> str:
    doc = _docstring_summary(node)
    header = f"- {node.name} (line {node.lineno})"
    if doc:
        header += f": {doc}"

    methods = [
        _format_python_function(child, indent="  ")
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if methods:
        return "\n".join([header, "  Methods:", *methods])
    return header


def _format_python_function(node: ast.AST, indent: str = "") -> str:
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    name = getattr(node, "name", "<unknown>")
    lineno = getattr(node, "lineno", "?")
    doc = _docstring_summary(node)
    line = f"{indent}- {prefix}{name} (line {lineno})"
    if doc:
        line += f": {doc}"
    return line


def _docstring_summary(node: ast.AST) -> str:
    docstring = ast.get_docstring(node)
    if not docstring:
        return ""
    return docstring.strip().splitlines()[0]
