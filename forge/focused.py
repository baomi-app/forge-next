import os
from dataclasses import dataclass
from typing import Iterable, List, Set

from forge.changes import FileChange
from forge.project import ProjectPolicy
from forge.verifier import VerificationCheck


@dataclass
class FocusedTestPlan:
    """Suggested verification commands for a set of changed files."""

    checks: List[VerificationCheck]
    notes: List[str]


class FocusedTestSelector:
    """Selects focused verification commands from task-scoped file changes."""

    def __init__(self, workspace_dir: str, policy: ProjectPolicy = None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.policy = policy or ProjectPolicy()

    def select(self, changes: Iterable[FileChange]) -> FocusedTestPlan:
        """Return focused verification checks and explanatory notes."""
        changed_paths = [change.path for change in changes]
        checks: List[VerificationCheck] = []
        notes: List[str] = []
        seen_commands: Set[str] = set()

        if not changed_paths:
            return FocusedTestPlan(checks=[], notes=["No changed files; no focused tests suggested."])

        for path in changed_paths:
            for check in self._checks_for_path(path):
                if check.command in seen_commands:
                    continue
                checks.append(check)
                seen_commands.add(check.command)

        code_paths = [path for path in changed_paths if self._is_code(path)]
        if code_paths and not checks:
            checks.append(
                VerificationCheck(
                    name="unittest discovery",
                    command="python -m unittest discover",
                    category="test",
                    source="fallback for changed code files",
                )
            )

        if not code_paths and not checks:
            notes.append("Only documentation or non-code files changed; no focused tests required.")

        if code_paths:
            notes.append("Focused tests are suggestions; run broader verification before finishing larger changes.")

        return FocusedTestPlan(checks=checks, notes=notes)

    def format_plan(self, changes: Iterable[FileChange]) -> str:
        """Render focused verification suggestions for agent-facing output."""
        change_list = list(changes)
        changed_paths = [change.path for change in change_list]
        plan = self.select(change_list)

        lines = [
            "Focused verification suggestions:",
            f"Changed files: {len(changed_paths)}",
            "Files:",
        ]
        if changed_paths:
            lines.extend(f"- {path}" for path in changed_paths)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Suggested commands:")
        if plan.checks:
            lines.extend(f"- {check.command} ({check.source})" for check in plan.checks)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Notes:")
        if plan.notes:
            lines.extend(f"- {note}" for note in plan.notes)
        else:
            lines.append("- none")

        return "\n".join(lines)

    def _checks_for_path(self, path: str) -> List[VerificationCheck]:
        if self.policy.is_test(path) and path.endswith(".py") and os.path.basename(path) != "__init__.py":
            module = path[:-3].replace("/", ".")
            return [self._unittest_module(module, f"changed test file {path}")]

        if self.policy.is_example(path) and os.path.basename(path).startswith("demo_") and path.endswith(".py"):
            return [
                VerificationCheck(
                    name=f"demo {os.path.basename(path)}",
                    command=f"python {path}",
                    category="demo",
                    source=f"changed demo {path}",
                )
            ]

        sibling_test = self._sibling_test_module(path)
        if sibling_test:
            return [self._unittest_module(sibling_test, f"sibling test for {path}")]

        return []

    def _sibling_test_module(self, path: str) -> str:
        if not path.endswith(".py") or path.startswith("tests/"):
            return ""

        dirname, filename = os.path.split(path)
        stem = filename[:-3]
        candidates = [
            os.path.join(dirname, f"test_{stem}.py"),
            os.path.join(dirname, f"{stem}_test.py"),
            os.path.join("tests", f"test_{stem}.py"),
        ]
        path_parts = dirname.split(os.sep) if dirname else []
        if path_parts:
            candidates.append(os.path.join("tests", dirname, f"test_{stem}.py"))
            candidates.append(os.path.join("tests", *path_parts[1:], f"test_{stem}.py"))

        for candidate in candidates:
            if os.path.exists(os.path.join(self.workspace_dir, candidate)):
                return candidate[:-3].replace("/", ".")
        return ""

    def _unittest_module(self, module: str, source: str) -> VerificationCheck:
        return VerificationCheck(
            name=f"unittest {module}",
            command=f"python -m unittest {module}",
            category="test",
            source=source,
        )

    def _is_code(self, path: str) -> bool:
        return self.policy.is_code(path)
