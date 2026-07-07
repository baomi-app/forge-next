from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class LLMTriageDecision:
    kind: str
    summary: str
    root_cause: str
    evidence: List[str]
    next_step: str
    confidence: float


@dataclass
class LLMReviewFinding:
    severity: str
    message: str
    path: str = ""


@dataclass
class LLMReviewDecision:
    status: str
    findings: List[LLMReviewFinding]
    commit_shape: List[str]
    suggested_message: str


@dataclass
class LLMPlannedEditDecision:
    order: int
    path: str
    action: str
    reason: str


@dataclass
class LLMEditPlanDecision:
    status: str
    files_to_inspect: List[str]
    planned_edits: List[LLMPlannedEditDecision]
    risks: List[str]
    verification_commands: List[str]
    next_steps: List[str]


@dataclass
class LLMVerificationCommandDecision:
    name: str
    command: str
    category: str
    source: str


@dataclass
class LLMFocusedTestsDecision:
    checks: List[LLMVerificationCommandDecision]
    notes: List[str]


@dataclass
class LLMCommitFileDecision:
    path: str
    action: str
    reason: str


@dataclass
class LLMCommitPlanDecision:
    status: str
    message: str
    files: List[LLMCommitFileDecision]
    risks: List[str]
    next_steps: List[str]


@dataclass
class LLMIssuePrDecision:
    acceptance_criteria: List[str]
    feedback_items: List[str]
    recommended_flow: List[str]


class TriageSpec:
    system_prompt = "You diagnose failed software verification commands. Return only JSON matching the requested schema."
    schema = {
        "kind": "short snake_case failure type",
        "summary": "one sentence diagnosis",
        "root_cause": "specific likely cause",
        "evidence": ["important output lines"],
        "next_step": "one concrete repair step",
        "confidence": 0.0,
    }

    @staticmethod
    def parse(data: Dict[str, Any], validator: Any) -> LLMTriageDecision:
        return LLMTriageDecision(
            kind=validator.required_str(data, "kind"),
            summary=validator.required_str(data, "summary"),
            root_cause=validator.required_str(data, "root_cause"),
            evidence=validator.string_list(data.get("evidence", []), "evidence"),
            next_step=validator.required_str(data, "next_step"),
            confidence=validator.confidence(data.get("confidence")),
        )


class ReviewSpec:
    system_prompt = "You review task-scoped code changes for delivery readiness. Return only JSON matching the requested schema."
    schema = {
        "status": "PASS | WARN | BLOCK",
        "findings": [
            {
                "severity": "INFO | WARN | BLOCK",
                "message": "actionable review finding",
                "path": "optional file path",
            }
        ],
        "commit_shape": ["atomicity and delivery readiness notes"],
        "suggested_message": "conventional commit message",
    }

    @staticmethod
    def parse(data: Dict[str, Any], validator: Any) -> LLMReviewDecision:
        status = validator.choice(data.get("status"), {"PASS", "WARN", "BLOCK"}, "status")
        raw_findings = data.get("findings", [])
        validator.require_list(raw_findings, "findings")
        findings = []
        for raw in raw_findings:
            validator.require_object(raw, "finding")
            findings.append(
                LLMReviewFinding(
                    severity=validator.choice(raw.get("severity"), {"INFO", "WARN", "BLOCK"}, "severity"),
                    message=validator.required_str(raw, "message"),
                    path=str(raw.get("path", "") or ""),
                )
            )
        return LLMReviewDecision(
            status=status,
            findings=findings,
            commit_shape=validator.string_list(data.get("commit_shape", []), "commit_shape"),
            suggested_message=validator.required_str(data, "suggested_message"),
        )


class EditPlanSpec:
    system_prompt = "You plan code edits for a local coding agent. Return only JSON matching the requested schema."
    schema = {
        "status": "READY | REVIEW | BLOCK",
        "files_to_inspect": ["existing files to read first"],
        "planned_edits": [
            {
                "order": 1,
                "path": "file path",
                "action": "modify | create | delete",
                "reason": "why this edit belongs in the task",
            }
        ],
        "risks": ["semantic risks or unknowns"],
        "verification_commands": ["commands to run"],
        "next_steps": ["agent next steps"],
    }

    @staticmethod
    def parse(data: Dict[str, Any], validator: Any) -> LLMEditPlanDecision:
        raw_edits = data.get("planned_edits", [])
        validator.require_list(raw_edits, "planned_edits")
        planned_edits = []
        for raw in raw_edits:
            validator.require_object(raw, "planned edit")
            order = raw.get("order")
            if isinstance(order, bool) or not isinstance(order, int) or order < 1:
                validator.fail("Planned edit 'order' must be a positive integer.")
            planned_edits.append(
                LLMPlannedEditDecision(
                    order=order,
                    path=validator.required_str(raw, "path"),
                    action=validator.choice(raw.get("action"), {"modify", "create", "delete"}, "action").lower(),
                    reason=validator.required_str(raw, "reason"),
                )
            )
        return LLMEditPlanDecision(
            status=validator.choice(data.get("status"), {"READY", "REVIEW", "BLOCK"}, "status"),
            files_to_inspect=validator.string_list(data.get("files_to_inspect", []), "files_to_inspect"),
            planned_edits=planned_edits,
            risks=validator.string_list(data.get("risks", []), "risks"),
            verification_commands=validator.string_list(data.get("verification_commands", []), "verification_commands"),
            next_steps=validator.string_list(data.get("next_steps", []), "next_steps"),
        )


class RepoRankSpec:
    system_prompt = "You rank repository files for a coding task. Return only JSON matching the requested schema."
    schema = {"suggested_files": ["file paths in recommended inspection order"]}

    @staticmethod
    def parse(data: Dict[str, Any], validator: Any) -> List[str]:
        return validator.string_list(data.get("suggested_files", []), "suggested_files")


class FocusedTestsSpec:
    system_prompt = "You suggest focused verification commands for a coding task. Return only JSON matching the requested schema."
    schema = {
        "checks": [
            {
                "name": "short check name",
                "command": "shell-free command string for the agent to run",
                "category": "test | lint | typecheck | demo | other",
                "source": "why this command is relevant",
            }
        ],
        "notes": ["important verification notes"],
    }

    @staticmethod
    def parse(data: Dict[str, Any], validator: Any) -> LLMFocusedTestsDecision:
        raw_checks = data.get("checks", [])
        validator.require_list(raw_checks, "checks")
        checks = []
        for raw in raw_checks:
            validator.require_object(raw, "check")
            checks.append(
                LLMVerificationCommandDecision(
                    name=validator.required_str(raw, "name"),
                    command=validator.required_str(raw, "command"),
                    category=validator.choice(raw.get("category"), {"test", "lint", "typecheck", "demo", "other"}, "category").lower(),
                    source=validator.required_str(raw, "source"),
                )
            )
        return LLMFocusedTestsDecision(checks=checks, notes=validator.string_list(data.get("notes", []), "notes"))


class CommitPlanSpec:
    system_prompt = "You plan atomic git commits for a coding agent. Return only JSON matching the requested schema."
    schema = {
        "status": "READY | REVIEW | BLOCK",
        "message": "conventional commit message",
        "files": [
            {
                "path": "changed file path",
                "action": "stage | exclude",
                "reason": "why this file belongs or does not belong",
            }
        ],
        "risks": ["commit boundary risks"],
        "next_steps": ["agent next steps before commit"],
    }

    @staticmethod
    def parse(data: Dict[str, Any], validator: Any) -> LLMCommitPlanDecision:
        raw_files = data.get("files", [])
        validator.require_list(raw_files, "files")
        files = []
        for raw in raw_files:
            validator.require_object(raw, "commit file decision")
            files.append(
                LLMCommitFileDecision(
                    path=validator.required_str(raw, "path"),
                    action=validator.choice(raw.get("action"), {"stage", "exclude"}, "action").lower(),
                    reason=validator.required_str(raw, "reason"),
                )
            )
        return LLMCommitPlanDecision(
            status=validator.choice(data.get("status"), {"READY", "REVIEW", "BLOCK"}, "status"),
            message=validator.required_str(data, "message"),
            files=files,
            risks=validator.string_list(data.get("risks", []), "risks"),
            next_steps=validator.string_list(data.get("next_steps", []), "next_steps"),
        )


class IssuePrSpec:
    system_prompt = (
        "You extract implementation requirements and feedback from issue, PR, CI, or review text. "
        "Return only JSON matching the requested schema."
    )
    schema = {
        "acceptance_criteria": ["requirements to satisfy"],
        "feedback_items": ["external feedback or CI action items"],
        "recommended_flow": ["agent workflow steps"],
    }

    @staticmethod
    def parse(data: Dict[str, Any], validator: Any) -> LLMIssuePrDecision:
        return LLMIssuePrDecision(
            acceptance_criteria=validator.string_list(data.get("acceptance_criteria", []), "acceptance_criteria"),
            feedback_items=validator.string_list(data.get("feedback_items", []), "feedback_items"),
            recommended_flow=validator.string_list(data.get("recommended_flow", []), "recommended_flow"),
        )


class ToolOutputSummarySpec:
    system_prompt = "You summarize long tool output for an LLM coding agent. Return only JSON."
    schema = {"summary": "compressed output preserving errors, paths, commands, and next useful clues"}

    @staticmethod
    def parse(data: Dict[str, Any], validator: Any) -> str:
        return validator.required_str(data, "summary")


class MemoryRankSpec:
    system_prompt = "You rank durable codebase memory entries by semantic relevance. Return only JSON."
    schema = {"entry_indexes": [1]}

    @staticmethod
    def parse(data: Dict[str, Any], validator: Any) -> List[int]:
        raw_indexes = data.get("entry_indexes", [])
        validator.require_list(raw_indexes, "entry_indexes")
        indexes = []
        for item in raw_indexes:
            if isinstance(item, bool) or not isinstance(item, int):
                validator.fail("Field 'entry_indexes' must contain integers.")
            indexes.append(item)
        return indexes
