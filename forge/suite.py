import os
import shutil
import time
from typing import List, Dict, Any, Callable
from forge.runner import AgentRunner
from forge.model import BaseModel
from forge.verifier import Verifier

class CodingTask:
    """Represents an isolated coding task in the evaluation suite."""
    
    def __init__(
        self, 
        name: str, 
        description: str, 
        setup_func: Callable[[str], None], 
        test_command: str
    ):
        self.name = name
        self.description = description
        self.setup_func = setup_func
        self.test_command = test_command

    def setup_workspace(self, workspace_path: str):
        """Prepare the initial workspace files for the task."""
        if not os.path.exists(workspace_path):
            os.makedirs(workspace_path)
        self.setup_func(workspace_path)


# --- Predefined Tasks Setup Functions ---

def setup_math_bug(workspace: str):
    """Task 1: Fix division by zero to raise ValueError instead of ZeroDivisionError."""
    # Buggy file
    with open(os.path.join(workspace, "math_helper.py"), "w", encoding="utf-8") as f:
        f.write('''def add(a, b):
    return a + b

def divide(a, b):
    return a / b
''')
    # Test suite
    with open(os.path.join(workspace, "test_math.py"), "w", encoding="utf-8") as f:
        f.write('''import unittest
from math_helper import divide

class TestMath(unittest.TestCase):
    def test_divide_by_zero(self):
        # We expect divide(x, 0) to raise ValueError, not ZeroDivisionError
        with self.assertRaises(ValueError):
            divide(10, 0)

if __name__ == '__main__':
    unittest.main()
''')


def setup_reverse_words(workspace: str):
    """Task 2: Complete the reverse_words function so that it passes assertions."""
    # Missing implementation template
    with open(os.path.join(workspace, "string_tool.py"), "w", encoding="utf-8") as f:
        f.write('''def reverse_words(s: str) -> str:
    # TODO: Complete the function to reverse the order of words in a string.
    # Example: "hello world" -> "world hello"
    pass
''')
    # Test suite
    with open(os.path.join(workspace, "test_string.py"), "w", encoding="utf-8") as f:
        f.write('''import unittest
from string_tool import reverse_words

class TestString(unittest.TestCase):
    def test_reverse(self):
        self.assertEqual(reverse_words("hello world"), "world hello")
        self.assertEqual(reverse_words("forge agent suite"), "suite agent forge")
        self.assertEqual(reverse_words("single"), "single")

if __name__ == '__main__':
    unittest.main()
''')


# The defined evaluation list
DEFINED_TASKS = [
    CodingTask(
        name="math_bug_fix",
        description="Fix the divide-by-zero bug in math_helper.py so that divide(a, b) raises ValueError when b is 0. Check your fix using test_math.py.",
        setup_func=setup_math_bug,
        test_command="python -m unittest test_math.py"
    ),
    CodingTask(
        name="reverse_words_complete",
        description="Complete the reverse_words(s: str) function in string_tool.py so that it reverses the order of words in the string (words separated by single spaces). Verify your code passes test_string.py.",
        setup_func=setup_reverse_words,
        test_command="python -m unittest test_string.py"
    )
]


class TaskSuite:
    """Manages workspace preparation, execution of tasks, and scoring results."""
    
    def __init__(self, tasks: List[CodingTask] = DEFINED_TASKS, base_temp_dir: str = "temp_tasks"):
        self.tasks = tasks
        self.base_temp_dir = os.path.abspath(base_temp_dir)

    def run_all(self, model: BaseModel, max_iterations: int = 6) -> List[Dict[str, Any]]:
        """Run all suite tasks and return evaluation reports."""
        results = []
        
        # Clean up any leftover temp directories before running
        if os.path.exists(self.base_temp_dir):
            shutil.rmtree(self.base_temp_dir)
            
        print(f"\n[TaskSuite] Starting Evaluation Run on {len(self.tasks)} tasks.")
        print(f"[TaskSuite] Workspace Sandboxing Dir: {self.base_temp_dir}")
        
        for idx, task in enumerate(self.tasks, 1):
            print(f"\n" + "="*60)
            print(f" Running Task {idx}/{len(self.tasks)}: {task.name}")
            print("="*60)
            
            task_workspace = os.path.join(self.base_temp_dir, task.name)
            
            # 1. Setup sandboxed workspace
            task.setup_workspace(task_workspace)
            
            # 2. Run agent with workspace locked to the sandbox
            runner = AgentRunner(
                model=model,
                workspace_dir=task_workspace,
                test_command=task.test_command
            )
            
            start_time = time.time()
            trace = runner.run(task.description, max_iterations=max_iterations)
            duration = time.time() - start_time
            
            # 3. Verify outcome
            # We run verifier independently in the sandboxed workspace to confirm final state
            verifier = Verifier(workspace_dir=task_workspace, test_command=task.test_command)
            passed, report = verifier.verify()
            
            results.append({
                "task_name": task.name,
                "passed": passed,
                "steps": len(trace.steps),
                "duration_seconds": round(duration, 2),
                "report": report
            })
            
            # Save the individual run trace JSON to the sandbox before cleanup (or keep it if requested)
            trace.save_to_file(os.path.join(task_workspace, f"{task.name}_trace.json"))
            
            # Clean up the sandbox workspace for this task
            try:
                shutil.rmtree(task_workspace)
            except Exception as e:
                print(f"[Warning] Failed to clean up directory {task_workspace}: {str(e)}")
                
        # Clean up base temp dir if empty
        if os.path.exists(self.base_temp_dir) and not os.listdir(self.base_temp_dir):
            os.rmdir(self.base_temp_dir)
            
        return results
