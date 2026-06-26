import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional

class BaseModel(ABC):
    """Abstract base class for LLM client wrappers."""
    
    @abstractmethod
    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """Sends messages to the model and returns (content, tool_calls).
        
        Args:
            messages: List of messages in OpenAI format.
            tools: List of tool definition schemas.
            
        Returns:
            Tuple containing:
            - content: Optional text response from the model.
            - tool_calls: Optional list of tool calls requested by the model.
              Format: [{"id": "...", "type": "function", "function": {"name": "...", "arguments": "{...}"}}]
        """
        pass


class MockModel(BaseModel):
    """A simulated model to demonstrate the agent's multi-step execution loop 
    without needing actual API keys or internet connection.
    """
    
    def __init__(self):
        # We track which step we are in the mock interactive session
        self.step_idx = 0
        
    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        
        self.step_idx += 1
        
        # Step 1: List files in workspace
        if self.step_idx == 1:
            print("[MockModel] Thinking: I need to locate the files in the workspace first.")
            return (
                "I will list all files in the current workspace to understand the codebase structure.",
                [{
                    "id": "mock_call_1",
                    "type": "function",
                    "function": {
                        "name": "list_files",
                        "arguments": json.dumps({"directory": "."})
                    }
                }]
            )
            
        # Step 2: Search code for syntax errors or read main.py
        elif self.step_idx == 2:
            print("[MockModel] Thinking: I see main.py. Let me read its contents.")
            return (
                "I see 'main.py' in the list. I will read its content to locate the bug.",
                [{
                    "id": "mock_call_2",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"filepath": "main.py"})
                    }
                }]
            )
            
        # Step 3: Apply a patch to fix the bug
        elif self.step_idx == 3:
            print("[MockModel] Thinking: Found a bug (division by zero error). Let's fix it with apply_patch.")
            # Note: We simulate patching main.py
            target_code = "def divide(a, b):\n    return a / b"
            replacement_code = "def divide(a, b):\n    if b == 0:\n        raise ValueError('Cannot divide by zero')\n    return a / b"
            return (
                "I found the issue in divide(). It doesn't handle division by zero. I will patch it.",
                [{
                    "id": "mock_call_3",
                    "type": "function",
                    "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "main.py",
                            "target": target_code,
                            "replacement": replacement_code
                        })
                    }
                }]
            )
            
        # Step 4: Run tests to verify the fix
        elif self.step_idx == 4:
            print("[MockModel] Thinking: Patch applied. I should run tests now to verify it.")
            return (
                "I have patched the divide function. Now I will run the test suite to make sure it passes and no other tests are broken.",
                [{
                    "id": "mock_call_4",
                    "type": "function",
                    "function": {
                        "name": "run_command",
                        "arguments": json.dumps({"command": "python -m unittest test_main.py"})
                    }
                }]
            )
            
        # Step 5: Check git diff
        elif self.step_idx == 5:
            print("[MockModel] Thinking: Tests passed! Let's check git diff for clean code changes.")
            return (
                "The test suite passed successfully. Let me run git diff to double-check my changes before wrapping up.",
                [{
                    "id": "mock_call_5",
                    "type": "function",
                    "function": {
                        "name": "git_diff",
                        "arguments": json.dumps({})
                    }
                }]
            )
            
        # Step 6: Complete the task
        else:
            print("[MockModel] Thinking: Changes verified. I can finish the task now.")
            return (
                "I have successfully found the division by zero bug in main.py, fixed it using `apply_patch`, verified it by running the tests (which now pass), and confirmed the changes via `git_diff`. The task is complete!",
                None
            )


class OpenAIModel(BaseModel):
    """Wrapper for real OpenAI-compatible LLM endpoints."""
    
    def __init__(self, model_name: str = "gpt-4o", api_key: Optional[str] = None, base_url: Optional[str] = None):
        # Only import openai when initialized to keep mock mode zero-dependency
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        
        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            
        try:
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            
            content = message.content
            tool_calls = None
            
            if message.tool_calls:
                tool_calls = []
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
                    
            return content, tool_calls
        except Exception as e:
            raise RuntimeError(f"Error during OpenAI API call: {str(e)}")
