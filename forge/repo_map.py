import ast
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

from forge.llm_decisions import LLMDecisionError
from forge.project import ProjectFileCollector, ProjectPolicy, ProjectProfiler, RepoProfile


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

    def __init__(self, workspace_dir: str, policy: ProjectPolicy = None, decision_service=None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.policy = policy or ProjectPolicy()
        self.decision_service = decision_service

    def map(self, directory: str = ".", task_goal: str = "") -> RepoMap:
        target_dir = self._target_dir(directory)
        files = self._collect_files(target_dir)
        profile = ProjectProfiler(target_dir, policy=self.policy, decision_service=self.decision_service).profile()
        modules = self._python_modules(files)
        entries: List[RepoFile] = []
        parse_errors: List[str] = []
        file_facts = []

        for path in files:
            full_path = os.path.join(target_dir, path)
            symbols: List[str] = []
            imports: List[str] = []
            has_main_guard = False

            if path.endswith(".py"):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    tree = ast.parse(source, filename=path)
                    symbols = self._symbols(tree)
                    imports = self._local_imports(tree, modules)
                    has_main_guard = self._has_main_guard(source)
                except SyntaxError as exc:
                    parse_errors.append(f"{path}: syntax error at line {exc.lineno}: {exc.msg}")
                except OSError as exc:
                    parse_errors.append(f"{path}: failed to read: {exc}")

            file_facts.append(
                {
                    **ProjectFileCollector(target_dir, policy=self.policy).file_fact(path),
                    "symbols": symbols[:12],
                    "local_imports": imports[:12],
                    "has_main_guard": has_main_guard,
                }
            )
            entries.append(
                RepoFile(
                    path=path,
                    role="unknown",
                    language="unknown",
                    symbols=symbols,
                    local_imports=imports,
                    entrypoint_reason="",
                )
            )

        self._annotate_entries(entries, file_facts, parse_errors)

        return RepoMap(
            root=os.path.relpath(target_dir, self.workspace_dir),
            profile=profile,
            files=entries,
            suggested_files=self._suggested_files(entries, task_goal, parse_errors),
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
        return ProjectFileCollector(target_dir, policy=self.policy).files()

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
            for target in candidates:
                if target == entry.path or target not in runtime_paths:
                    continue
                pair = (entry.path, target)
                if pair not in seen:
                    links.append(pair)
                    seen.add(pair)

        return links

    def _suggested_files(self, entries: List[RepoFile], task_goal: str, parse_errors: List[str]) -> List[str]:
        if not task_goal.strip() or not self.decision_service:
            return []
        try:
            ranked = self.decision_service.rank_repo_files(
                task_goal=task_goal,
                files=[self._entry_payload(entry) for entry in entries],
                max_files=10,
            )
        except LLMDecisionError as exc:
            parse_errors.append(f"LLM repo rerank failed: {exc}")
            return []

        known_paths = {entry.path for entry in entries}
        safe = []
        for path in ranked:
            if path in known_paths and path not in safe:
                safe.append(path)
        return safe

    def _entry_payload(self, entry: RepoFile) -> Dict[str, object]:
        return {
            "path": entry.path,
            "role": entry.role,
            "language": entry.language,
            "symbols": entry.symbols[:12],
            "local_imports": entry.local_imports[:12],
            "entrypoint_reason": entry.entrypoint_reason,
        }

    def _annotate_entries(self, entries: List[RepoFile], file_facts: List[Dict[str, object]], parse_errors: List[str]):
        if not self.decision_service:
            parse_errors.append("LLM repo file annotation is not configured.")
            return
        try:
            decision = self.decision_service.annotate_repo_files(file_facts)
        except LLMDecisionError as exc:
            parse_errors.append(f"LLM repo file annotation failed: {exc}")
            return

        by_path = {annotation.path: annotation for annotation in decision.files}
        for entry in entries:
            annotation = by_path.get(entry.path)
            if not annotation:
                continue
            entry.role = annotation.role
            entry.language = annotation.language
            entry.entrypoint_reason = annotation.entrypoint_reason

    def _has_main_guard(self, source: str) -> bool:
        return 'if __name__ == "__main__"' in source or "if __name__ == '__main__'" in source
