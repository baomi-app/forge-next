import os
import sys
import json
from typing import List, Dict, Any, Tuple, Optional

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner

class CheckpointMockModel(BaseModel):
    """A simulated model that deliberately crashes on the 4th iteration, 
    then successfully completes the task when resumed.
    """
    def __init__(self, is_resumed: bool = False):
        self.is_resumed = is_resumed

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        
        # We calculate which step we are on based on the number of messages in the context.
        # This makes the MockModel stateless and robust to resuming!
        # Step 1: Only system & user message present (len = 2)
        # Step 2: After list_files assistant and tool results are added (len = 4)
        # Step 3: After read_file assistant and tool results are added (len = 6)
        # Step 4: After apply_patch assistant and tool results are added (len = 8)
        msg_count = len(messages)
        
        # Iteration 1
        if msg_count <= 2:
            print("[MockModel] Thinking: Let's list files to find main.py.")
            return (
                "I will list workspace files.",
                [{"id": "c_call_1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]
            )
            
        # Iteration 2
        elif msg_count <= 4:
            print("[MockModel] Thinking: Reading main.py contents.")
            return (
                "I will read main.py.",
                [{"id": "c_call_2", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"filepath": "main.py"})}}]
            )
            
        # Iteration 3
        elif msg_count <= 6:
            print("[MockModel] Thinking: Found division by zero. Applying patch.")
            target = "def divide(a, b):\n    return a / b"
            replacement = "def divide(a, b):\n    if b == 0:\n        raise ValueError('Cannot divide by zero')\n    return a / b"
            return (
                "I will patch main.py to handle division by zero.",
                [{"id": "c_call_3", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "main.py",
                        "target": target,
                        "replacement": replacement
                    })
                }}]
            )
            
        # Iteration 4: Deliberately CRASH if we are in the first run (fresh run)
        elif msg_count <= 8 and not self.is_resumed:
            print("\n!!! [MockModel] CRITICAL ERROR: Simulated API Connection Disconnected !!!")
            raise RuntimeError("API Connection Lost: Network Timeout.")
            
        # Iteration 4: Success if we have resumed; inspect transaction state first
        elif msg_count <= 8 and self.is_resumed:
            print("[MockModel] Thinking: Resumed successfully! I will inspect the restored transaction diff.")
            return (
                "I have resumed the session. I will inspect the restored change transaction first.",
                [{"id": "c_call_4", "type": "function", "function": {
                    "name": "change_summary",
                    "arguments": json.dumps({"include_diff": True})
                }}]
            )

        # Iteration 5: Run tests after confirming the transaction survived resume
        elif msg_count <= 10 and self.is_resumed:
            print("[MockModel] Thinking: Transaction baseline survived resume. Let's run tests.")
            return (
                "The transaction diff is still available after resume. Let me run unit tests.",
                [{"id": "c_call_5", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -m unittest test_main.py"})
                }}]
            )
            
        # Iteration 6
        else:
            print("[MockModel] Thinking: Tests passed. Declaring done.")
            return ("The task is successfully complete. Checkpoint test passed!", None)


def setup_environment(workspace: str):
    if not os.path.exists(workspace):
        os.makedirs(workspace)
        
    print("[Demo Setup] Creating buggy main.py...")
    with open(os.path.join(workspace, "main.py"), "w", encoding="utf-8") as f:
        f.write('''def add(a, b):
    return a + b

def divide(a, b):
    return a / b
''')

    print("[Demo Setup] Creating test_main.py...")
    with open(os.path.join(workspace, "test_main.py"), "w", encoding="utf-8") as f:
        f.write('''import unittest
from main import divide

class TestMath(unittest.TestCase):
    def test_divide(self):
        with self.assertRaises(ValueError):
            divide(5, 0)

if __name__ == '__main__':
    unittest.main()
''')

def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing sandbox workspace: {workspace}")
    import shutil
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_checkpoint")
    setup_environment(workspace)
    
    task = "Fix division by zero in main.py to raise ValueError, and verify."
    checkpoint_file = "checkpoint.json"
    
    try:
        # ==========================================
        # STAGE 1: First Run (Crashes at Iteration 4)
        # ==========================================
        print("\n" + "="*50)
        print(" STAGE 1: FRESH RUN (EXPECTING NETWORK CRASH)")
        print("="*50)
        
        # We pass is_resumed=False
        model_1 = CheckpointMockModel(is_resumed=False)
        runner_1 = AgentRunner(model=model_1, workspace_dir=workspace, test_command="python -m unittest test_main.py")
        
        trace_1 = runner_1.run(task, max_iterations=6, checkpoint_path=checkpoint_file)
        
        # Check if it crashed as expected (Runner catches error and returns it inside trace)
        if trace_1.final_response and "Fatal Error" in trace_1.final_response:
            print(f"\n[System Status] Run 1 caught expected crash: {trace_1.final_response}")
            print(f"[System Status] Verification: Checkpoint file exists at '{os.path.join(workspace, checkpoint_file)}'?")
            exists = os.path.exists(os.path.join(workspace, checkpoint_file))
            print(f"[System Status] Answer: {'YES (State Preserved!)' if exists else 'NO (State Lost!)'}")
            
            if not exists:
                sys.exit(1)
                
            # ==========================================
            # STAGE 2: Second Run (Resuming from Checkpoint)
            # ==========================================
            print("\n" + "="*50)
            print(" STAGE 2: RESUME RUN (RESUMING FROM STEP 4)")
            print("="*50)
            
            # We pass is_resumed=True to simulate restored API connectivity
            model_2 = CheckpointMockModel(is_resumed=True)
            runner_2 = AgentRunner(model=model_2, workspace_dir=workspace, test_command="python -m unittest test_main.py")
            
            trace_2 = runner_2.run(
                task, 
                max_iterations=6, 
                resume_from=checkpoint_file, 
                checkpoint_path=checkpoint_file
            )
            
            # Print summary of the final combined trace
            trace_2.print_summary()
        else:
            print("\n[Error] Stage 1 did not crash as expected.")
        
    finally:
        cleanup_environment(workspace)

if __name__ == "__main__":
    main()
