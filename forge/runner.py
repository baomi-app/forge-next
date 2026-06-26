import json
import copy
from typing import Dict, Any, Optional
from forge.context import Context
from forge.model import BaseModel
from forge.tools import registry
from forge.trace import ExecutionTrace, StepTrace

DEFAULT_SYSTEM_PROMPT = """You are a software engineering assistant (Coding Agent) running locally in a workspace directory.
You have access to a set of core coding tools: list_files, search_code, read_file, apply_patch, edit_file_block, run_command, and git_diff.

Your goal is to complete the user's task using these tools.

Guidelines:
1. Examine the project structure and contents using search/read/list tools first when investigating a problem.
2. Formulate a plan, apply precise patches using apply_patch, and always test your changes (e.g. by running tests via run_command).
3. Check git_diff before declaring you are done to ensure you only made clean, intended modifications.
4. When you have completed the task and verified it, reply with a clear summary of your changes. Do not call any further tools once the work is finished.
"""

class AgentRunner:
    """The central orchestrator that runs the core Agent Loop."""
    
    def __init__(self, model: BaseModel, system_prompt: Optional[str] = None):
        self.model = model
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    def run(self, task: str, max_iterations: int = 10) -> ExecutionTrace:
        """Executes the main agent loop for a given task.
        
        Args:
            task: The user query/task description.
            max_iterations: Maximum loop iterations (turns) to avoid infinite loops.
        """
        # 1. Initialize Context & Trace
        context = Context(system_prompt=self.system_prompt)
        context.add_user(task)
        
        trace = ExecutionTrace(task)
        
        print(f"\n[Runner] Starting Agent Loop for task: '{task}'")
        print(f"[Runner] Max iterations: {max_iterations}")
        
        for iteration in range(1, max_iterations + 1):
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
                # If the model did not ask for any tool calls, it has finished or gave final answer
                step.stop_timer()
                trace.add_step(step)
                print("[Runner] Model decided to STOP. Task complete.")
                trace.finish(content or "No final response provided.")
                break
                
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
                result = registry.execute(func_name, args)
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
            
        else:
            # Loop exhausted without model stopping voluntarily
            print("\n[Runner] Warning: Reached max iterations limit!")
            trace.finish("Failed: Maximum iterations reached without resolving the task.")
            
        return trace
