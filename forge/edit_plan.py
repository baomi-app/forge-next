import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Set

from forge.command_policy import CommandPolicy
from forge.llm_decisions import LLMDecisionError
from forge.project import ProjectPolicy


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

    def __init__(self, workspace_dir: str, policy: ProjectPolicy = None, decision_service=None, command_policy: CommandPolicy = None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.policy = policy or ProjectPolicy()
        self.decision_service = decision_service
        self.command_policy = command_policy or CommandPolicy()

    def plan(
        self,
        task_goal: str,
        target_files: str = "",
        max_files: int = 8,
    ) -> EditPlan:
        """Return a pre-edit plan from a task goal and optional file hints."""
        goal = task_goal.strip()
        explicit_files = self._parse_target_files(target_files)
        if not self.decision_service:
            return EditPlan(
                status="BLOCK",
                goal=goal,
                files_to_inspect=[],
                planned_edits=[],
                risks=["LLM edit planning is not configured."],
                verification_commands=[],
                next_steps=["Configure an LLMDecisionService, then run plan_edits again."],
            )

        try:
            decision = self.decision_service.plan_edits(
                task_goal=goal,
                target_files=explicit_files,
                workspace_files=self._workspace_files(),
                max_files=max_files,
            )
        except LLMDecisionError as exc:
            return EditPlan(
                status="BLOCK",
                goal=goal,
                files_to_inspect=[],
                planned_edits=[],
                risks=[f"LLM edit planning failed: {exc}"],
                verification_commands=[],
                next_steps=["Fix the LLM edit planning response, then run plan_edits again."],
            )

        risks = list(decision.risks)
        files_to_inspect = self._safe_existing_paths(decision.files_to_inspect, risks)
        planned = self._safe_planned_edits(decision.planned_edits, risks)
        verification_commands = self._safe_verification_commands(decision.verification_commands, risks)
        status = "BLOCK" if risks and decision.status == "READY" and not planned else decision.status

        return EditPlan(
            status=status,
            goal=goal,
            files_to_inspect=files_to_inspect,
            planned_edits=planned,
            risks=risks,
            verification_commands=verification_commands,
            next_steps=decision.next_steps,
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
            path = self._normalize_relative_path(raw)
            if not path:
                continue
            if path not in seen:
                paths.append(path)
                seen.add(path)
        return paths

    def _workspace_files(self) -> List[str]:
        files = []
        if not os.path.exists(self.workspace_dir):
            return files
        for root, dirs, filenames in os.walk(self.workspace_dir):
            dirs[:] = sorted(d for d in dirs if self.policy.should_descend_dir(d))
            for filename in sorted(filenames):
                path = os.path.relpath(os.path.join(root, filename), self.workspace_dir)
                if not self.policy.should_track_file(path):
                    continue
                files.append(path)
        return files

    def _exists(self, path: str) -> bool:
        return os.path.exists(os.path.join(self.workspace_dir, path))

    def _safe_existing_paths(self, paths: List[str], risks: List[str]) -> List[str]:
        safe = []
        for path in paths:
            normalized = self._normalize_relative_path(path)
            if not self._is_safe_relative_path(normalized):
                risks.append(f"LLM suggested an unsafe inspection path: {path}")
                continue
            if self._exists(normalized):
                safe.append(normalized)
            else:
                risks.append(f"LLM suggested a missing inspection path: {normalized}")
        return safe

    def _safe_planned_edits(self, edits, risks: List[str]) -> List[PlannedEdit]:
        planned = []
        for edit in edits:
            path = self._normalize_relative_path(edit.path)
            if not self._is_safe_relative_path(path):
                risks.append(f"LLM suggested an unsafe edit path: {edit.path}")
                continue
            planned.append(
                PlannedEdit(
                    order=edit.order,
                    path=path,
                    action=edit.action,
                    reason=edit.reason,
                )
            )
        planned.sort(key=lambda edit: edit.order)
        return planned

    def _safe_verification_commands(self, commands: List[str], risks: List[str]) -> List[str]:
        safe = []
        for command in commands:
            allowed, reason = self.command_policy.validate(command)
            if not allowed:
                risks.append(f"LLM suggested an unsafe verification command '{command}': {reason}")
                continue
            if command not in safe:
                safe.append(command)
        return safe

    def _is_safe_relative_path(self, path: str) -> bool:
        if not path or os.path.isabs(path):
            return False
        full_path = os.path.abspath(os.path.join(self.workspace_dir, path))
        return os.path.commonpath([self.workspace_dir, full_path]) == self.workspace_dir

    def _normalize_relative_path(self, path: str) -> str:
        normalized = path.strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

    def _lines(self, items: Iterable[str]) -> List[str]:
        item_list = list(items)
        if not item_list:
            return ["- none"]
        return [f"- {item}" for item in item_list]
