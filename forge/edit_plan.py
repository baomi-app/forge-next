import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Set

from forge.changes import FileChange
from forge.focused import FocusedTestSelector


@dataclass
class PlannedEdit:
    """One planned file-level edit before patching starts."""

    order: int
    path: str
    action: str
    reason: str


@dataclass
class EditPlan:
    """Pre-edit strategy for one task."""

    status: str
    goal: str
    files_to_inspect: List[str]
    planned_edits: List[PlannedEdit]
    risks: List[str]
    verification_commands: List[str]
    next_steps: List[str]


class EditPlanner:
    """Builds a scoped edit strategy before modifying files."""

    EXCLUDE_DIRS = {".git", "__pycache__", ".venv", ".agents", "node_modules", ".gemini"}
    CODE_SUFFIXES = (".py", ".js", ".ts", ".tsx", ".go", ".rs")
    DOC_SUFFIXES = (".md", ".rst", ".txt")
    CONFIG_FILES = {"pyproject.toml", "package.json", "go.mod", "Cargo.toml", "baomi.json"}

    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)

    def plan(
        self,
        task_goal: str,
        target_files: str = "",
        max_files: int = 8,
    ) -> EditPlan:
        """Return a pre-edit plan from a task goal and optional file hints."""
        goal = task_goal.strip()
        explicit_files = self._parse_target_files(target_files)
        candidates = explicit_files or self._infer_files(goal, max_files=max_files)
        existing = [path for path in candidates if self._exists(path)]
        planned = self._planned_edits(candidates)
        risks = self._risks(goal, candidates, existing, max_files=max_files)
        status = self._status(goal, planned, risks)
        verification = self._verification_commands(candidates)

        return EditPlan(
            status=status,
            goal=goal,
            files_to_inspect=existing,
            planned_edits=planned,
            risks=risks,
            verification_commands=verification,
            next_steps=self._next_steps(status),
        )

    def format_plan(
        self,
        task_goal: str,
        target_files: str = "",
        max_files: int = 8,
    ) -> str:
        """Render the edit strategy for agent-facing output."""
        plan = self.plan(task_goal, target_files=target_files, max_files=max_files)
        lines = [
            "Edit strategy plan:",
            f"Status: {plan.status}",
            f"Goal: {plan.goal or '(missing)'}",
            "",
            "Files to inspect first:",
        ]
        lines.extend(self._lines(plan.files_to_inspect))

        lines.append("")
        lines.append("Planned edits:")
        if plan.planned_edits:
            lines.extend(
                f"- {edit.order}. {edit.action}: {edit.path} ({edit.reason})"
                for edit in plan.planned_edits
            )
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Risks:")
        lines.extend(self._lines(plan.risks))

        lines.append("")
        lines.append("Verification:")
        lines.extend(self._lines(plan.verification_commands))

        lines.append("")
        lines.append("Next steps:")
        lines.extend(f"- {step}" for step in plan.next_steps)

        return "\n".join(lines)

    def _parse_target_files(self, target_files: str) -> List[str]:
        paths = []
        seen: Set[str] = set()
        for raw in re.split(r"[,\n]", target_files):
            path = raw.strip()
            if not path:
                continue
            path = path.lstrip("./")
            if path not in seen:
                paths.append(path)
                seen.add(path)
        return paths

    def _infer_files(self, task_goal: str, max_files: int) -> List[str]:
        tokens = self._tokens(task_goal)
        if not tokens:
            return []

        scored = []
        for path in self._workspace_files():
            score = self._score(path, tokens)
            if score > 0:
                scored.append((score, path))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [path for _, path in scored[:max_files]]

    def _workspace_files(self) -> List[str]:
        files = []
        if not os.path.exists(self.workspace_dir):
            return files
        for root, dirs, filenames in os.walk(self.workspace_dir):
            dirs[:] = sorted(d for d in dirs if d not in self.EXCLUDE_DIRS)
            for filename in sorted(filenames):
                path = os.path.relpath(os.path.join(root, filename), self.workspace_dir)
                files.append(path)
        return files

    def _score(self, path: str, tokens: Set[str]) -> int:
        lowered = path.lower()
        basename = os.path.basename(lowered)
        stem = os.path.splitext(basename)[0]
        score = 0
        for token in tokens:
            if token in stem:
                score += 3
            elif token in basename:
                score += 2
            elif token in lowered:
                score += 1
        if self._is_test(path) and {"test", "tests", "verify", "verification"} & tokens:
            score += 2
        if self._is_doc(path) and {"doc", "docs", "readme", "documentation"} & tokens:
            score += 2
        return score

    def _planned_edits(self, candidates: List[str]) -> List[PlannedEdit]:
        edits = []
        for index, path in enumerate(candidates, start=1):
            exists = self._exists(path)
            action = "modify" if exists else "create"
            reason = self._reason(path, exists)
            edits.append(PlannedEdit(order=index, path=path, action=action, reason=reason))
        return edits

    def _risks(self, goal: str, candidates: List[str], existing: List[str], max_files: int) -> List[str]:
        risks = []
        if not goal:
            risks.append("Task goal is missing; clarify the intended change before editing.")
        if not candidates:
            risks.append("No target files were identified; inspect the repository or provide target files.")
        missing = [path for path in candidates if path not in existing]
        if missing:
            risks.append("Some planned files do not exist yet; confirm they should be created.")
        if len(candidates) > max_files:
            risks.append("Planned edit touches many files; split the task or tighten scope.")
        categories = {self._category(path) for path in candidates}
        if "runtime code" in categories and "project configuration" in categories:
            risks.append("Runtime code and project configuration are both in scope; confirm they serve one change.")
        if "other" in categories and len(categories) > 2:
            risks.append("Uncategorized files are mixed with other edits; review the boundary before patching.")
        return risks

    def _status(self, goal: str, planned: List[PlannedEdit], risks: List[str]) -> str:
        if not goal or not planned:
            return "BLOCK"
        if risks:
            return "REVIEW"
        return "READY"

    def _verification_commands(self, candidates: List[str]) -> List[str]:
        if not candidates:
            return []
        changes = [
            FileChange(path=path, status="modified" if self._exists(path) else "added")
            for path in candidates
        ]
        focused = FocusedTestSelector(self.workspace_dir).select(changes)
        commands = [check.command for check in focused.checks]
        if any(self._is_code(path) for path in candidates) and "python -m unittest discover" not in commands:
            commands.append("python -m unittest discover")
        return commands

    def _next_steps(self, status: str) -> List[str]:
        if status == "BLOCK":
            return [
                "Clarify the task goal or target files.",
                "Run plan_edits again before modifying files.",
            ]
        if status == "REVIEW":
            return [
                "Inspect the listed files before patching.",
                "Resolve or accept the listed risks.",
                "Apply edits in the planned order, then run focused verification.",
            ]
        return [
            "Inspect the listed files.",
            "Apply edits in the planned order.",
            "Run focused verification, then review and commit orchestration.",
        ]

    def _reason(self, path: str, exists: bool) -> str:
        category = self._category(path)
        if not exists:
            return f"new {category}"
        return category

    def _category(self, path: str) -> str:
        if self._is_test(path):
            return "test"
        if self._is_doc(path):
            return "documentation"
        if self._is_code(path):
            return "runtime code"
        if os.path.basename(path) in self.CONFIG_FILES:
            return "project configuration"
        return "other"

    def _exists(self, path: str) -> bool:
        return os.path.exists(os.path.join(self.workspace_dir, path))

    def _is_code(self, path: str) -> bool:
        return path.endswith(self.CODE_SUFFIXES)

    def _is_test(self, path: str) -> bool:
        basename = os.path.basename(path)
        return (
            path.startswith("tests/")
            or "/tests/" in path
            or (basename.startswith("test_") and basename.endswith(".py"))
            or basename.endswith("_test.py")
        )

    def _is_doc(self, path: str) -> bool:
        return path.endswith(self.DOC_SUFFIXES) or os.path.basename(path) in {"README.md", "AGENTS.md", "VERSION.md"}

    def _tokens(self, text: str) -> Set[str]:
        return {token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(token) > 2}

    def _lines(self, items: Iterable[str]) -> List[str]:
        item_list = list(items)
        if not item_list:
            return ["- none"]
        return [f"- {item}" for item in item_list]
