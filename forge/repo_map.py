import ast
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

from forge.project import ProjectPolicy, ProjectProfiler, RepoProfile


@dataclass
class RepoFile:
    """One file entry in a repository map."""

    path: str
    role: str
    language: str
    symbols: List[str]
    local_imports: List[str]
    entrypoint_reason: str = ""


@dataclass
class RepoMap:
    """Project-level repository orientation for an agent."""

    root: str
    profile: RepoProfile
    files: List[RepoFile]
    suggested_files: List[str]
    test_links: List[Tuple[str, str]]
    parse_errors: List[str]

    def format(self, max_files: int = 40) -> str:
        shown_files = self.files[:max_files] if max_files > 0 else self.files
        omitted = len(self.files) - len(shown_files)
        entrypoints = [entry for entry in self.files if entry.entrypoint_reason]

        lines = [
            "Repository map:",
            f"Root: {self.root}",
            f"Languages: {', '.join(self.profile.languages) if self.profile.languages else 'unknown'}",
            f"Files scanned: {len(self.files)}",
            "",
            "Entry points:",
        ]
        if entrypoints:
            lines.extend(
                f"- {entry.path} ({entry.entrypoint_reason})"
                for entry in entrypoints[:10]
            )
            if len(entrypoints) > 10:
                lines.append(f"- ... {len(entrypoints) - 10} more entry points")
        else:
            lines.append("- none detected")

        lines.extend(["", "Suggested inspection order:"])
        if self.suggested_files:
            lines.extend(f"- {path}" for path in self.suggested_files[:10])
        else:
            lines.append("- none")

        lines.extend(["", "File roles:"])
        if shown_files:
            for entry in shown_files:
                symbols = ", ".join(entry.symbols[:6]) if entry.symbols else "none"
                imports = ", ".join(entry.local_imports[:6]) if entry.local_imports else "none"
                lines.append(
                    f"- {entry.path} [{entry.role}; {entry.language}] "
                    f"symbols: {symbols}; local imports: {imports}"
                )
        else:
            lines.append("- none")
        if omitted > 0:
            lines.append(f"- ... {omitted} more files omitted")

        lines.extend(["", "Test links:"])
        if self.test_links:
            lines.extend(f"- {test} -> {target}" for test, target in self.test_links[:20])
            if len(self.test_links) > 20:
                lines.append(f"- ... {len(self.test_links) - 20} more test links")
        else:
            lines.append("- none detected")

        if self.parse_errors:
            lines.extend(["", "Parse errors:"])
            lines.extend(f"- {error}" for error in self.parse_errors)

        return "\n".join(lines)


class RepoMapper:
    """Builds a lightweight project map of roles, entry points, symbols, imports, and tests."""

    def __init__(self, workspace_dir: str, policy: ProjectPolicy = None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.policy = policy or ProjectPolicy()

    def map(self, directory: str = ".", task_goal: str = "") -> RepoMap:
        target_dir = self._target_dir(directory)
        files = self._collect_files(target_dir)
        profile = ProjectProfiler(target_dir, policy=self.policy).profile()
        modules = self._python_modules(files)
        entries: List[RepoFile] = []
        parse_errors: List[str] = []

        for path in files:
            full_path = os.path.join(target_dir, path)
            role = self._role(path)
            language = self._language(path)
            symbols: List[str] = []
            imports: List[str] = []
            entrypoint_reason = self._entrypoint_reason(path, "")

            if path.endswith(".py"):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    tree = ast.parse(source, filename=path)
                    symbols = self._symbols(tree)
                    imports = self._local_imports(tree, modules)
                    entrypoint_reason = self._entrypoint_reason(path, source)
                except SyntaxError as exc:
                    parse_errors.append(f"{path}: syntax error at line {exc.lineno}: {exc.msg}")
                except OSError as exc:
                    parse_errors.append(f"{path}: failed to read: {exc}")

            entries.append(
                RepoFile(
                    path=path,
                    role=role,
                    language=language,
                    symbols=symbols,
                    local_imports=imports,
                    entrypoint_reason=entrypoint_reason,
                )
            )

        return RepoMap(
            root=os.path.relpath(target_dir, self.workspace_dir),
            profile=profile,
            files=entries,
            suggested_files=self._suggested_files(entries, task_goal),
            test_links=self._test_links(entries, modules),
            parse_errors=parse_errors,
        )

    def format_map(self, directory: str = ".", task_goal: str = "", max_files: int = 40) -> str:
        return self.map(directory=directory, task_goal=task_goal).format(max_files=max_files)

    def _target_dir(self, directory: str) -> str:
        target_dir = os.path.abspath(os.path.join(self.workspace_dir, directory))
        if os.path.commonpath([self.workspace_dir, target_dir]) != self.workspace_dir:
            raise ValueError(f"Directory '{directory}' is outside workspace.")
        if not os.path.isdir(target_dir):
            raise ValueError(f"Directory '{directory}' does not exist or is not a directory.")
        return target_dir

    def _collect_files(self, target_dir: str) -> List[str]:
        files = []
        for root, dirs, filenames in os.walk(target_dir):
            dirs[:] = sorted(d for d in dirs if self.policy.should_descend_dir(d))
            for filename in sorted(filenames):
                path = os.path.relpath(os.path.join(root, filename), target_dir)
                if not self.policy.should_track_file(path):
                    continue
                files.append(path)
        return files

    def _python_modules(self, paths: Iterable[str]) -> Dict[str, str]:
        modules = {}
        for path in paths:
            if not path.endswith(".py"):
                continue
            module = path[:-3].replace(os.sep, ".")
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
            modules[module] = path
        return modules

    def _symbols(self, tree: ast.AST) -> List[str]:
        symbols = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                symbols.append(f"class {node.name}")
            elif isinstance(node, ast.AsyncFunctionDef):
                symbols.append(f"async def {node.name}")
            elif isinstance(node, ast.FunctionDef):
                symbols.append(f"def {node.name}")
        return symbols

    def _local_imports(self, tree: ast.AST, modules: Dict[str, str]) -> List[str]:
        imports: List[str] = []
        seen: Set[str] = set()
        for module_name in self._imported_modules(tree):
            path = self._module_to_path(module_name, modules)
            if path and path not in seen:
                imports.append(path)
                seen.add(path)
        return imports

    def _imported_modules(self, tree: ast.AST) -> List[str]:
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        return modules

    def _module_to_path(self, module: str, modules: Dict[str, str]) -> str:
        parts = module.split(".")
        for end in range(len(parts), 0, -1):
            candidate = ".".join(parts[:end])
            if candidate in modules:
                return modules[candidate]
        return ""

    def _test_links(self, entries: Iterable[RepoFile], modules: Dict[str, str]) -> List[Tuple[str, str]]:
        runtime_paths = {path for path in modules.values()}
        links: List[Tuple[str, str]] = []
        seen: Set[Tuple[str, str]] = set()

        for entry in entries:
            if entry.role != "test":
                continue

            candidates = list(entry.local_imports)
            candidates.extend(self._conventional_test_targets(entry.path, runtime_paths))
            for target in candidates:
                if target == entry.path or target not in runtime_paths:
                    continue
                pair = (entry.path, target)
                if pair not in seen:
                    links.append(pair)
                    seen.add(pair)

        return links

    def _conventional_test_targets(self, test_path: str, runtime_paths: Set[str]) -> List[str]:
        dirname, filename = os.path.split(test_path)
        stem = filename[:-3] if filename.endswith(".py") else filename
        if stem.startswith("test_"):
            stem = stem[len("test_"):]
        if stem.endswith("_test"):
            stem = stem[:-5]

        candidates = [
            os.path.join(dirname, f"{stem}.py"),
            f"{stem}.py",
        ]
        if dirname.startswith("tests"):
            rest = dirname.split(os.sep)[1:]
            if rest:
                candidates.append(os.path.join(*rest, f"{stem}.py"))

        return [path for path in candidates if path in runtime_paths]

    def _suggested_files(self, entries: List[RepoFile], task_goal: str) -> List[str]:
        tokens = self._tokens(task_goal)
        if not tokens:
            return [entry.path for entry in entries if entry.entrypoint_reason][:5]

        scored = []
        for entry in entries:
            if self._is_low_signal_file(entry):
                continue
            score = self._score_entry(entry, tokens)
            if score > 0:
                scored.append((score, entry.path))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [path for _, path in scored[:10]]

    def _is_low_signal_file(self, entry: RepoFile) -> bool:
        return os.path.basename(entry.path) == "__init__.py" and not entry.symbols

    def _score_entry(self, entry: RepoFile, tokens: Set[str]) -> int:
        haystack = " ".join([entry.path, entry.role, entry.language, *entry.symbols]).lower()
        score = 0
        for token in tokens:
            if token in os.path.basename(entry.path).lower():
                score += 3
            elif token in haystack:
                score += 1
        if entry.role == "test" and {"test", "tests", "verify", "verification"} & tokens:
            score += 2
        return score

    def _entrypoint_reason(self, path: str, source: str) -> str:
        basename = os.path.basename(path)
        if source and 'if __name__ == "__main__"' in source:
            return "__main__ guard"
        if source and "if __name__ == '__main__'" in source:
            return "__main__ guard"
        if path.startswith("examples/demo_"):
            return "demo script"
        if basename in {"main.py", "app.py", "cli.py", "run.py"}:
            return "conventional Python entry file"
        return ""

    def _role(self, path: str) -> str:
        return self.policy.role(path)

    def _is_test(self, path: str) -> bool:
        return self.policy.is_test(path)

    def _language(self, path: str) -> str:
        return self.policy.language(path)

    def _tokens(self, text: str) -> Set[str]:
        return {token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(token) > 2}
