import copy
from typing import List, Dict, Any, Optional

from forge.llm_decisions import LLMDecisionError

class Context:
    """Manages the conversation history (context) and compiles a token-efficient 
    messages representation dynamically for LLM consumption.
    """
    
    def __init__(self, system_prompt: Optional[str] = None, decision_service=None):
        # Source of Truth: All raw files and command logs are preserved 100% complete
        # to ensure local checkpointing and tracing remain accurate.
        self.messages: List[Dict[str, Any]] = []
        self.decision_service = decision_service
        if system_prompt:
            self.add_system(system_prompt)

    def add_system(self, content: str):
        """Add system instructions to the history."""
        self.messages.append({
            "role": "system",
            "content": content
        })

    def add_user(self, content: str):
        """Add user query/task to the history."""
        self.messages.append({
            "role": "user",
            "content": content
        })

    def add_assistant(self, content: Optional[str], tool_calls: Optional[List[Dict[str, Any]]] = None):
        """Add assistant response to history, including optional tool calls."""
        msg = {"role": "assistant"}
        if content is not None:
            msg["content"] = content
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, name: str, content: str):
        """Add the raw execution output of a tool to the local history."""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content
        })

    def get_messages(self, keep_recent_turns: int = 2) -> List[Dict[str, Any]]:
        """Compiles a truncated and folded copy of the message history.
        
        Args:
            keep_recent_turns: Number of recent turns to keep 100% complete.
              One turn = 1 assistant action + 1 tool result.
        """
        # Deep copy to keep original memory untouched for trace/checkpoint logs
        compiled_messages = copy.deepcopy(self.messages)
        
        # Calculate sliding limit window
        keep_count = keep_recent_turns * 2
        cutoff_index = len(compiled_messages) - keep_count
        
        for idx, msg in enumerate(compiled_messages):
            # 1. Active folding of historical turns (idx < cutoff_index)
            if idx < cutoff_index:
                if msg.get("role") == "tool":
                    original_len = len(msg.get("content", ""))
                    if original_len > 150:
                        msg["content"] = f"[Output of tool '{msg.get('name')}' folded to save tokens. Original length: {original_len} characters.]"
                elif msg.get("role") == "assistant":
                    # Only fold thoughts if the assistant actually invoked tool calls.
                    # If it was a direct text reply to the user, keep it intact to avoid memory loss.
                    if msg.get("content") and msg.get("tool_calls"):
                        msg["content"] = "[Thoughts folded]"
            
            # 2. Smart Truncation for active turns (idx >= cutoff_index)
            else:
                if msg.get("role") == "tool":
                    original_content = msg.get("content", "")
                    msg["content"] = self._compile_smart_truncation(msg.get("name", ""), original_content)
                    
        return compiled_messages

    def _compile_smart_truncation(self, name: str, content: str, max_length: int = 1000) -> str:
        """Compile long tool output through the LLM summarizer for model consumption."""
        original_len = len(content)
        if original_len <= max_length:
            return content

        if not self.decision_service:
            return (
                f"[Long output from tool '{name}' omitted because LLM context summarization "
                f"is not configured. Original length: {original_len} characters.]"
            )
        try:
            summary = self.decision_service.summarize_tool_output(name, content, max_length)
        except LLMDecisionError as exc:
            return (
                f"[Long output from tool '{name}' could not be summarized by LLM: {exc}. "
                f"Original length: {original_len} characters.]"
            )
        compiled = (
            f"[LLM summary of long tool output '{name}'. Original length: {original_len} characters.]\n"
            f"{summary}"
        )
        print(f"[Context Builder] Compiled tool output '{name}' with LLM summary. Compressed {original_len} to {len(compiled)} chars.")
        return compiled

    def clear(self):
        """Reset the conversation context."""
        self.messages = []
