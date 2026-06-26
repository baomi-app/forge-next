import os
import sys
import json
import argparse
from typing import List, Dict, Any, Tuple, Optional

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel, OpenAIModel
from forge.suite import TaskSuite

class SuiteMockModel(BaseModel):
    """A simulated model that dynamically adapts its responses to solve 
    multiple tasks in the Task Suite offline.
    """
    
    def __init__(self):
        # We track state per task. Since the suite runs tasks sequentially,
        # we can reset the step index whenever we detect a new task.
        self.current_task: Optional[str] = None
        self.step_idx = 0

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        
        # Determine the task from the first user message
        user_task_prompt = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_task_prompt = msg.get("content", "")
                break
                
        # Detect task switch
        task_id = "math" if "math_helper" in user_task_prompt else "string"
        if self.current_task != task_id:
            self.current_task = task_id
            self.step_idx = 0
            
        self.step_idx += 1
        
        if self.current_task == "math":
            return self._solve_math_task()
        else:
            return self._solve_string_task()

    def _solve_math_task(self) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        # 1. list files
        if self.step_idx == 1:
            return (
                "Let me list the workspace files to find math_helper.py.",
                [{"id": "s_math_1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]
            )
        # 2. read file
        elif self.step_idx == 2:
            return (
                "I see math_helper.py. Let me read it.",
                [{"id": "s_math_2", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"filepath": "math_helper.py"})}}]
            )
        # 3. patch file
        elif self.step_idx == 3:
            target = "def divide(a, b):\n    return a / b"
            replacement = "def divide(a, b):\n    if b == 0:\n        raise ValueError('Cannot divide by zero')\n    return a / b"
            return (
                "I will modify divide() to raise ValueError on b==0.",
                [{"id": "s_math_3", "type": "function", "function": {"name": "apply_patch", "arguments": json.dumps({
                    "filepath": "math_helper.py",
                    "target": target,
                    "replacement": replacement
                })}}]
            )
        # 4. Done
        else:
            return ("I have successfully fixed the division bug and verified it.", None)

    def _solve_string_task(self) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        # 1. list files
        if self.step_idx == 1:
            return (
                "I will scan the files in the workspace.",
                [{"id": "s_str_1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]
            )
        # 2. read file
        elif self.step_idx == 2:
            return (
                "I will read string_tool.py to see the reverse_words template.",
                [{"id": "s_str_2", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"filepath": "string_tool.py"})}}]
            )
        # 3. patch file
        elif self.step_idx == 3:
            target = "def reverse_words(s: str) -> str:\n    # TODO: Complete the function to reverse the order of words in a string.\n    # Example: " + '"hello world" -> "world hello"\n    pass'
            replacement = "def reverse_words(s: str) -> str:\n    # Split words, reverse the list, and join with space\n    return ' '.join(s.strip().split()[::-1])"
            return (
                "I will replace the pass with the correct word reversing logic.",
                [{"id": "s_str_3", "type": "function", "function": {"name": "apply_patch", "arguments": json.dumps({
                    "filepath": "string_tool.py",
                    "target": target,
                    "replacement": replacement
                })}}]
            )
        # 4. Done
        else:
            return ("I have successfully completed reverse_words and verified it with tests.", None)


def print_ascii_table(results: List[Dict[str, Any]]):
    """Utility to print evaluation results in a neat console table."""
    print("\n" + "="*70)
    print(" TASK SUITE BENCHMARK RESULTS")
    print("="*70)
    
    header = f"{'Task Name':<30} | {'Status':<10} | {'Steps':<8} | {'Duration (s)':<12}"
    print(header)
    print("-"*70)
    
    passed_count = 0
    for res in results:
        status_str = "PASS" if res["passed"] else "FAIL"
        if res["passed"]:
            passed_count += 1
            
        row = f"{res['task_name']:<30} | {status_str:<10} | {res['steps']:<8} | {res['duration_seconds']:<12.2f}"
        print(row)
        
    print("-"*70)
    success_rate = (passed_count / len(results)) * 100 if results else 0.0
    print(f"Summary: {passed_count}/{len(results)} Tasks Passed ({success_rate:.1f}% Success Rate)")
    print("="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Forge: Run Evaluation Task Suite.")
    parser.add_argument("--mock", action="store_true", help="Run in zero-dependency offline mock mode (default).")
    parser.add_argument("--model", type=str, default="gpt-4o", help="Real model to run (if not in mock mode).")
    parser.add_argument("--max-iterations", type=int, default=6, help="Max turns allowed per task (default: 6).")
    args = parser.parse_args()

    # Determine model choice
    if args.mock:
        print("Running Task Suite in [MOCK MODE]...")
        model = SuiteMockModel()
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("\n[Error] OPENAI_API_KEY is not set!")
            print("Please set it, or run with --mock for offline demonstration:")
            print("  python examples/run_suite.py --mock")
            sys.exit(1)
        print(f"Running Task Suite in [REAL MODE] with model: {args.model}")
        model = OpenAIModel(model_name=args.model, api_key=api_key, base_url=os.environ.get("OPENAI_BASE_URL"))

    # Initialize and execute suite
    suite = TaskSuite()
    
    try:
        results = suite.run_all(model=model, max_iterations=args.max_iterations)
        print_ascii_table(results)
    except KeyboardInterrupt:
        print("\nEvaluation interrupted by user. Exiting.")
        sys.exit(1)

if __name__ == "__main__":
    main()
