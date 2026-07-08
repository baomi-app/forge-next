import json
import re
from typing import Any, Dict, List, Optional

from forge.changes import FileChange
from forge.llm_decision_specs import (
    CommitPlanSpec,
    EditPlanSpec,
    FocusedTestsSpec,
    IssuePrSpec,
    LLMCommitFileDecision,
    LLMCommitPlanDecision,
    LLMEditPlanDecision,
    LLMFocusedTestsDecision,
    LLMIssuePrDecision,
    LLMPlannedEditDecision,
    LLMProjectProfileDecision,
    LLMProjectVerificationPlanDecision,
    LLMRepoAnnotationDecision,
    LLMRepoFileAnnotationDecision,
    LLMReviewDecision,
    LLMReviewFinding,
    LLMTriageDecision,
    LLMVerificationCommandDecision,
    MemoryRankSpec,
    ProjectProfileSpec,
    ProjectVerificationSpec,
    RepoAnnotationSpec,
    RepoRankSpec,
    ReviewSpec,
    ToolOutputSummarySpec,
    TriageSpec,
)
from forge.model import BaseModel


class LLMDecisionError(RuntimeError):
    """Raised when an LLM decision cannot be produced or validated."""


class LLMDecisionValidator:
    """Validation helpers shared by all LLM decision specs."""

    def fail(self, message: str):
        raise LLMDecisionError(message)

    def require_object(self, value: Any, name: str) -> Dict[str, Any]:
        if not isinstance(value, dict):
            self.fail(f"{name} must be an object.")
        return value

    def require_list(self, value: Any, key: str) -> List[Any]:
        if not isinstance(value, list):
            self.fail(f"Field '{key}' must be a list.")
        return value

    def required_str(self, data: Dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            self.fail(f"Field '{key}' must be a non-empty string.")
        return value.strip()

    def string_list(self, value: Any, key: str) -> List[str]:
        self.require_list(value, key)
        result = []
        for item in value:
            if not isinstance(item, str):
                self.fail(f"Field '{key}' must contain only strings.")
            if item.strip():
                result.append(item.strip())
        return result

    def choice(self, value: Any, choices: set, key: str) -> str:
        if not isinstance(value, str):
            self.fail(f"Field '{key}' must be one of {sorted(choices)}.")
        normalized = value.strip().upper()
        if normalized not in choices:
            self.fail(f"Field '{key}' must be one of {sorted(choices)}.")
        return normalized

    def confidence(self, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.fail("Field 'confidence' must be a number between 0 and 1.")
        confidence = float(value)
        if confidence < 0 or confidence > 1:
            self.fail("Field 'confidence' must be a number between 0 and 1.")
        return confidence

    def schema_version(self, value: Any, expected: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            self.fail(f"Field 'schema_version' must be integer {expected}.")
        if value != expected:
            self.fail(f"Field 'schema_version' must be {expected}.")
        return value


class LLMDecisionService:
    """Gateway for structured LLM decisions."""

    def __init__(self, model: Optional[BaseModel], max_retries: int = 1):
        self.model = model
        self.max_retries = max_retries
        self.validator = LLMDecisionValidator()

    def triage_failure(
        self,
        check: Any,
        output: str,
        exit_code: int,
        task_goal: str = "",
    ) -> LLMTriageDecision:
        payload = {
            "task_goal": task_goal,
            "check": {
                "name": check.name,
                "command": check.command,
                "category": check.category,
                "source": check.source,
            },
            "exit_code": exit_code,
            "output": self._clip(output, 10000),
        }
        return self.decide(TriageSpec, payload)

    def review_changes(
        self,
        task_goal: str,
        changes: List[FileChange],
        diff: str,
    ) -> LLMReviewDecision:
        payload = {
            "task_goal": task_goal,
            "changed_files": [
                {"path": change.path, "status": change.status}
                for change in changes
            ],
            "diff": self._clip(diff, 12000),
        }
        return self.decide(ReviewSpec, payload)

    def plan_edits(
        self,
        task_goal: str,
        target_files: List[str],
        workspace_files: List[str],
        max_files: int,
    ) -> LLMEditPlanDecision:
        payload = {
            "task_goal": task_goal,
            "explicit_target_files": target_files,
            "workspace_files": workspace_files[:400],
            "max_files": max_files,
        }
        return self.decide(EditPlanSpec, payload)

    def rank_repo_files(self, task_goal: str, files: List[Dict[str, Any]], max_files: int = 10) -> List[str]:
        payload = {
            "task_goal": task_goal,
            "files": files[:400],
            "max_files": max_files,
        }
        return self.decide(RepoRankSpec, payload)[:max_files]

    def suggest_focused_tests(
        self,
        changed_files: List[Dict[str, str]],
        workspace_files: List[str],
    ) -> LLMFocusedTestsDecision:
        payload = {
            "changed_files": changed_files,
            "workspace_files": workspace_files[:400],
        }
        return self.decide(FocusedTestsSpec, payload)

    def profile_repository(self, workspace_files: List[Dict[str, Any]]) -> LLMProjectProfileDecision:
        payload = {"workspace_files": workspace_files[:400]}
        return self.decide(ProjectProfileSpec, payload)

    def annotate_repo_files(self, files: List[Dict[str, Any]]) -> LLMRepoAnnotationDecision:
        payload = {"files": files[:400]}
        return self.decide(RepoAnnotationSpec, payload)

    def plan_project_verification(self, workspace_files: List[Dict[str, Any]]) -> LLMProjectVerificationPlanDecision:
        payload = {"workspace_files": workspace_files[:400]}
        return self.decide(ProjectVerificationSpec, payload)

    def plan_commit(
        self,
        task_goal: str,
        changes: List[FileChange],
        diff: str,
    ) -> LLMCommitPlanDecision:
        payload = {
            "task_goal": task_goal,
            "changed_files": [
                {"path": change.path, "status": change.status}
                for change in changes
            ],
            "diff": self._clip(diff, 12000),
        }
        return self.decide(CommitPlanSpec, payload)

    def extract_issue_pr_context(
        self,
        title: str,
        body: str,
        feedback: str,
        source: str,
    ) -> LLMIssuePrDecision:
        payload = {
            "title": title,
            "body": self._clip(body, 10000),
            "feedback": self._clip(feedback, 10000),
            "source": source,
        }
        return self.decide(IssuePrSpec, payload)

    def summarize_tool_output(self, name: str, content: str, max_length: int) -> str:
        payload = {
            "tool_name": name,
            "max_length": max_length,
            "content": self._clip(content, 20000),
        }
        return self.decide(ToolOutputSummarySpec, payload)

    def rank_memory_entries(self, query: str, entries: List[Dict[str, Any]], max_entries: int) -> List[int]:
        payload = {
            "query": query,
            "entries": entries[:200],
            "max_entries": max_entries,
        }
        return self.decide(MemoryRankSpec, payload)[:max_entries]

    def decide(self, spec: Any, payload: Dict[str, Any]) -> Any:
        if not self.model:
            raise LLMDecisionError("LLM decision service requires a model.")
        schema = spec.schema_with_version() if hasattr(spec, "schema_with_version") else spec.schema
        data = self._ask_json(spec, payload, schema)
        return spec.parse(data, self.validator)

    def _ask_json(self, spec: Any, payload: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        last_error = ""
        messages = [
            {"role": "system", "content": spec.system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "decision": {
                            "name": getattr(spec, "name", spec.__name__),
                            "schema_version": getattr(spec, "version", None),
                        },
                        "schema": schema,
                        "input": payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]
        for attempt in range(self.max_retries + 1):
            content, tool_calls = self.model.generate(messages, tools=None)
            if tool_calls:
                raise LLMDecisionError("LLM decision returned tool calls; expected JSON content.")
            try:
                return self._parse_json_object(content or "")
            except LLMDecisionError as exc:
                last_error = str(exc)
                messages.append({"role": "assistant", "content": content or ""})
                messages.append({
                    "role": "user",
                    "content": "The previous response was invalid. Return one valid JSON object only, including the required schema_version.",
                })
                if attempt >= self.max_retries:
                    break
        raise LLMDecisionError(last_error or "LLM decision did not return valid JSON.")

    def _parse_json_object(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMDecisionError(f"Invalid JSON decision: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LLMDecisionError("LLM decision must be a JSON object.")
        return parsed

    def _clip(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n... [TRUNCATED FOR LLM DECISION] ..."
