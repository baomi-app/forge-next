import os
import json
import copy
from typing import List, Dict, Any, Optional
from forge.context import Context
from forge.model import BaseModel
from forge.tools import registry
from forge.trace import ExecutionTrace, StepTrace
from forge.verifier import Verifier
from forge.sandbox import LocalRestrictedSandbox

DEFAULT_SYSTEM_PROMPT = """You are a software engineering assistant (Coding Agent) running locally in a workspace directory.
You have access to a set of core coding tools: list_files, search_code, read_file, apply_patch, edit_file_block, run_command, and git_diff.

Your goal is to complete the user's task using these tools.

To work effectively, you must follow a structured reasoning process. Every response you output must adhere strictly to the following formatting blocks:

Plan:
- [ ] List out your high-level steps here. Use markdown checkboxes.
- Use `[x]` for finished steps, `[/]` for the current active step, and `[ ]` for future remaining steps.
- IMPORTANT: If you encounter an unexpected error, a blocked dependency, or new findings, you must dynamically edit (re-plan) this list to resolve the roadblocks.

Thought:
Describe your observations, findings, and decisions. Explain what you learned from the last tool's output and what your logic is for the next action.

Action:
State what you are doing. If you need to invoke tools, output the tool calls immediately following this response. If the task is finished and verified, summarize your final solution here and output no tool calls.
"""

class AgentRunner:
    """The central orchestrator that runs the core Agent Loop with Checkpointing support."""

    def __init__(
        self,
        model: BaseModel,
        system_prompt: Optional[str] = None,
        workspace_dir: str = ".",
        test_command: Optional[str] = None
    ):
        self.model = model
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.verifier = Verifier(workspace_dir=self.workspace_dir, test_command=test_command)
        self.sandbox = LocalRestrictedSandbox(self.workspace_dir)

    def save_checkpoint(self, filepath: str, current_iteration: int, context: Context, trace: ExecutionTrace):
        """Serialize current run memory to disk."""
        data = {
            "task": trace.task,
            "current_iteration": current_iteration,
            "system_prompt": self.system_prompt,
            "messages": context.messages,
            "test_command": self.verifier.test_command,
            "trace_steps": [step.to_dict() for step in trace.steps]
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[Checkpoint] Successfully saved session state to {filepath}")
        except Exception as e:
            print(f"[Warning] Failed to save checkpoint to {filepath}: {str(e)}")

    def load_checkpoint(self, filepath: str) -> Dict[str, Any]:
        """Deserialize checkpoint state from disk."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"[Checkpoint] Successfully loaded session state from {filepath}")
        return data

    def run(
        self,
        task: str,
        max_iterations: int = 10,
        resume_from: Optional[str] = None,
        checkpoint_path: str = "checkpoint.json"
    ) -> ExecutionTrace:
        """Executes the main agent loop for a given task, supporting crash recovery from checkpoint.

        Args:
            task: The user query/task description.
            max_iterations: Maximum loop iterations (turns).
            resume_from: Optional path to a checkpoint JSON file to resume from.
            checkpoint_path: Filename to save iteration checkpoints to.
        """
        # Save original working directory to restore later
        original_cwd = os.getcwd()

        # Determine starting index and reconstruct state if resuming
        start_iteration = 0
        context = Context(system_prompt=self.system_prompt)
        trace = None

        # If resume_from is requested, we change CWD to the workspace to find the file
        try:
            os.chdir(self.workspace_dir)

            if resume_from and os.path.exists(resume_from):
                data = self.load_checkpoint(resume_from)
                task = data["task"]
                start_iteration = data["current_iteration"]

                # Restore messages history
                context.messages = data["messages"]

                # Reconstruct execution trace
                trace = ExecutionTrace(task)
                for step_data in data["trace_steps"]:
                    trace.add_step(StepTrace.from_dict(step_data))

                print(f"[Runner] Resuming agent loop from Iteration {start_iteration + 1}...")
        except Exception as e:
            print(f"[Warning] Failed to load resume file. Starting fresh: {str(e)}")
            os.chdir(original_cwd) # Fallback CWD reset

        # If starting fresh
        if trace is None:
            context.add_user(task)
            trace = ExecutionTrace(task)
            print(f"\n[Runner] Starting fresh Agent Loop for task: '{task}'")

        print(f"[Runner] Max iterations: {max_iterations}")
        print(f"[Runner] Workspace isolated to: {self.workspace_dir}")

        try:
            # Always ensure cwd is switched to workspace
            os.chdir(self.workspace_dir)

            for iteration in range(start_iteration + 1, max_iterations + 1):
                print(f"\n[Runner] === Iteration {iteration} ===")

                step = StepTrace(step_idx=iteration)
                step.start_timer()

                # 2. Get current history & tool schemas
                messages = context.get_messages()
                # Deep copy messages for tracing to keep a clean snapshot of context state at this step
                step.input_messages = copy.deepcopy(messages)

                # Fetch tool schemas from registry
                tool_definitions = registry.tool_definitions

                # 3. Model call (Context -> Model)
                try:
                    content, tool_calls = self.model.generate(messages, tool_definitions)
                except Exception as e:
                    err_msg = f"Fatal Error calling model: {str(e)}"
                    print(f"[Runner] {err_msg}")
                    trace.finish(err_msg)
                    return trace

                step.model_text_response = content
                if tool_calls:
                    step.tool_calls = tool_calls

                # Print thoughts if any
                if content:
                    print(f"[Model Thought/Message]: {content.strip()}")

                # 4. Handle tool execution / continuation decision
                if not tool_calls:
                    # When the model attempts to finish, execute automated verification checks
                    is_passed, report = self.verifier.verify()
                    if is_passed:
                        step.stop_timer()
                        trace.add_step(step)
                        print("[Runner] Verifier PASSED! Task complete.")
                        trace.finish(content or "No final response provided.")

                        # Clean up checkpoint on final success
                        if os.path.exists(checkpoint_path):
                            os.remove(checkpoint_path)
                            print(f"[Checkpoint] Cleaned up temporary checkpoint file: {checkpoint_path}")
                        break
                    else:
                        print(f"[Runner] Verifier BLOCKED termination. Report:\n{report}")
                        # Feed verification error back to assistant and user
                        context.add_assistant(content, None)
                        context.add_user(report)

                        # Record verifier failure as a pseudo-tool result for tracing
                        step.tool_results.append({
                            "tool_call_id": "verifier_check",
                            "name": "auto_verifier",
                            "content": report
                        })
                        step.stop_timer()
                        trace.add_step(step)

                        # Save checkpoint even on blocked verification
                        self.save_checkpoint(checkpoint_path, iteration, context, trace)
                        continue

                # If tool calls are requested, we must add the assistant response to the conversation history.
                # Tool-calling chat APIs require matching tool results to their respective assistant tool calls.
                context.add_assistant(content, tool_calls)

                # 5. Tool Executor / Sandbox (Tool Executor)
                for tool_call in tool_calls:
                    tc_id = tool_call.get("id", "")
                    func_name = tool_call.get("function", {}).get("name", "")
                    args_str = tool_call.get("function", {}).get("arguments", "{}")

                    print(f"[Runner] Requesting Tool: {func_name} with args: {args_str}")

                    # Parse arguments
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError as je:
                        error_output = f"Error: Failed to parse tool arguments as JSON: {str(je)}"
                        print(f"[Runner] {error_output}")
                        context.add_tool_result(tc_id, func_name, error_output)
                        step.tool_results.append({"tool_call_id": tc_id, "name": func_name, "content": error_output})
                        continue
                    # Execute tool
                    result = registry.execute(func_name, args, sandbox=self.sandbox)
                    print(f"[Tool Output Snippet]: {result[:120]}..." if len(result) > 120 else f"[Tool Output]: {result}")

                    # Add tool result back to context history
                    context.add_tool_result(tc_id, func_name, result)
                    step.tool_results.append({
                        "tool_call_id": tc_id,
                        "name": func_name,
                        "content": result
                    })

                step.stop_timer()
                trace.add_step(step)

                # Save checkpoint at the end of each successful iteration
                self.save_checkpoint(checkpoint_path, iteration, context, trace)

            else:
                # Loop exhausted without model stopping voluntarily
                print("\n[Runner] Warning: Reached max iterations limit!")
                trace.finish("Failed: Maximum iterations reached without resolving the task.")

        finally:
            # Always restore the original working directory
            os.chdir(original_cwd)

        return trace
