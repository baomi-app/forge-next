import json
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

from forge.context import Context
from forge.sandbox import BaseSandbox
from forge.tools import ToolRegistry
from forge.tool_result import ToolResult
from forge.trace import StepTrace


class ToolExecutor:
    """Executes model-requested tool calls and records their results."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        sandbox: Optional[BaseSandbox] = None,
        runner: Optional[Any] = None,
        session: Optional[Any] = None,
        subagent_manager: Optional[Any] = None,
        tool_lock: Optional[RLock] = None,
        journal_recorder: Optional[Any] = None,
        runtime: Optional[Any] = None,
    ):
        self.tool_registry = tool_registry
        self.sandbox = sandbox
        self.runner = runner
        self.session = session
        self.subagent_manager = subagent_manager
        self.tool_lock = tool_lock or RLock()
        self.journal_recorder = journal_recorder
        self.runtime = runtime

    def execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        context: Context,
        step: StepTrace,
    ) -> None:
        """Execute tool calls, updating both conversation context and trace step."""
        subagent_calls, standard_calls = self._partition_tool_calls(tool_calls)
        self._execute_subagent_calls(subagent_calls, context, step)
        self._execute_standard_calls(standard_calls, context, step)

    def _partition_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        subagent_calls = []
        standard_calls = []
        for tool_call in tool_calls:
            func_name = tool_call.get("function", {}).get("name", "")
            if func_name == "invoke_subagent":
                subagent_calls.append(tool_call)
            else:
                standard_calls.append(tool_call)
        return subagent_calls, standard_calls

    def _execute_subagent_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        context: Context,
        step: StepTrace,
    ) -> None:
        if not tool_calls:
            return

        tool_results_futures = {}
        with ThreadPoolExecutor() as executor:
            for tool_call in tool_calls:
                parsed = self._parse_tool_call(tool_call, context, step, mode="Async Launch")
                if not parsed:
                    continue

                tc_id, func_name, args = parsed
                future = executor.submit(
                    self.tool_registry.execute,
                    func_name,
                    args,
                    self.sandbox,
                    self.runner,
                    self.session,
                    self.subagent_manager,
                    self.runtime,
                )
                tool_results_futures[future] = (tc_id, func_name)

            for future, (tc_id, func_name) in tool_results_futures.items():
                try:
                    result = future.result()
                except Exception as exc:
                    result = ToolResult.error(
                        f"Error executing tool '{func_name}' dynamically: {str(exc)}",
                        error_type="executor_exception",
                        metadata={
                            "tool_name": func_name,
                            "exception_type": type(exc).__name__,
                        },
                    )
                self._record_tool_result(context, step, tc_id, func_name, result)

    def _execute_standard_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        context: Context,
        step: StepTrace,
    ) -> None:
        for tool_call in tool_calls:
            parsed = self._parse_tool_call(tool_call, context, step, mode="Sequential")
            if not parsed:
                continue

            tc_id, func_name, args = parsed
            with self.tool_lock:
                result = self.tool_registry.execute(
                    func_name,
                    args,
                    sandbox=self.sandbox,
                    runner=self.runner,
                    session=self.session,
                    subagent_manager=self.subagent_manager,
                    runtime=self.runtime,
                )
            self._record_tool_result(context, step, tc_id, func_name, result)

    def _parse_tool_call(
        self,
        tool_call: Dict[str, Any],
        context: Context,
        step: StepTrace,
        mode: str,
    ) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        tc_id = tool_call.get("id", "")
        func_name = tool_call.get("function", {}).get("name", "")
        args_str = tool_call.get("function", {}).get("arguments", "{}")

        print(f"[Runner] Requesting Tool ({mode}): {func_name} with args: {args_str}")
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError as je:
            error_output = f"Error: Failed to parse tool arguments as JSON: {str(je)}"
            print(f"[Runner] {error_output}")
            self._record_tool_result(
                context,
                step,
                tc_id,
                func_name,
                ToolResult.error(
                    error_output,
                    error_type="invalid_json",
                    metadata={"exception_type": type(je).__name__},
                ),
            )
            return None

        return tc_id, func_name, args

    def _record_tool_result(
        self,
        context: Context,
        step: StepTrace,
        tc_id: str,
        func_name: str,
        result: ToolResult,
    ) -> None:
        result = ToolResult.from_value(result)
        content = result.content
        print(f"[Tool Output Snippet]: {content[:120]}..." if len(content) > 120 else f"[Tool Output]: {content}")
        context.add_tool_result(tc_id, func_name, content)
        trace_result = {
            "tool_call_id": tc_id,
            "name": func_name,
            **result.to_trace_dict(),
        }
        step.tool_results.append(trace_result)
        if self.journal_recorder:
            self.journal_recorder.tool_finished(func_name, result)
