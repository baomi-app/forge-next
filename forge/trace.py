import json
import time
from typing import List, Dict, Any, Optional

class StepTrace:
    """Records the details of a single iteration (turn) in the Agent Loop."""
    
    def __init__(self, step_idx: int):
        self.step_idx = step_idx
        self.timestamp = time.time()
        self.input_messages: List[Dict[str, Any]] = []
        self.model_text_response: Optional[str] = None
        self.tool_calls: List[Dict[str, Any]] = []
        self.tool_results: List[Dict[str, Any]] = []
        self.duration: float = 0.0

    def start_timer(self):
        self.start_time = time.time()

    def stop_timer(self):
        self.duration = time.time() - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_idx,
            "timestamp": self.timestamp,
            "duration_seconds": round(self.duration, 3),
            "input_messages": self.input_messages,
            "model_text_response": self.model_text_response,
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'StepTrace':
        """Reconstruct a StepTrace object from a dictionary."""
        step = StepTrace(step_idx=data["step_index"])
        step.timestamp = data["timestamp"]
        step.duration = data["duration_seconds"]
        step.input_messages = data["input_messages"]
        step.model_text_response = data["model_text_response"]
        step.tool_calls = data["tool_calls"]
        step.tool_results = data["tool_results"]
        return step


class ExecutionTrace:
    """Manages the full execution trace of an agent's run."""
    
    def __init__(self, task: str):
        self.task = task
        self.start_time = time.time()
        self.steps: List[StepTrace] = []
        self.final_response: Optional[str] = None
        self.total_duration: float = 0.0

    def add_step(self, step: StepTrace):
        self.steps.append(step)

    def finish(self, final_response: str):
        self.final_response = final_response
        self.total_duration = time.time() - self.start_time

    def save_to_file(self, filepath: str):
        """Save the trace as a structured JSON file."""
        data = {
            "task": self.task,
            "total_duration_seconds": round(self.total_duration, 3),
            "final_response": self.final_response,
            "steps": [step.to_dict() for step in self.steps]
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\n[Trace] Execution trace successfully saved to {filepath}")
        except Exception as e:
            print(f"Error saving trace: {str(e)}")

    def print_summary(self):
        """Pretty-print the execution summary to CLI."""
        print("\n" + "="*50)
        print(" AGENT EXECUTION TRACE SUMMARY")
        print("="*50)
        print(f"Task: {self.task}")
        print(f"Total Steps: {len(self.steps)}")
        print(f"Total Duration: {self.total_duration:.2f} seconds")
        print("-"*50)
        
        for step in self.steps:
            print(f"\n[Step {step.step_idx}] (Duration: {step.duration:.2f}s)")
            if step.model_text_response:
                print(f"  Model Thought/Response:")
                print(f"    {step.model_text_response.strip()}")
            if step.tool_calls:
                print(f"  Tool Calls Requested:")
                for tc in step.tool_calls:
                    func_name = tc.get("function", {}).get("name")
                    args = tc.get("function", {}).get("arguments")
                    print(f"    -> {func_name}({args})")
            if step.tool_results:
                print(f"  Tool Results:")
                for tr in step.tool_results:
                    # Clip too long outputs to keep console clean
                    output_snippet = tr.get("content", "")
                    if len(output_snippet) > 200:
                        output_snippet = output_snippet[:200] + "\n    ... [TRUNCATED] ..."
                    print(f"    <- {tr.get('name')} (ID: {tr.get('tool_call_id')}):\n    {output_snippet.strip()}")
        
        print("\n" + "="*50)
        print(" FINAL ANSWER")
        print("="*50)
        print(self.final_response)
        print("="*50 + "\n")
