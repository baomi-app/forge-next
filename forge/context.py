import copy
import re
from typing import List, Dict, Any, Optional

class Context:
    """Manages the conversation history (context) and compiles a token-efficient 
    messages representation dynamically for LLM consumption.
    """
    
    def __init__(self, system_prompt: Optional[str] = None):
        # Source of Truth: All raw files and command logs are preserved 100% complete
        # to ensure local checkpointing and tracing remain accurate.
        self.messages: List[Dict[str, Any]] = []
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
        """Helper to extract critical runtime exceptions / tracebacks from long outputs."""
        original_len = len(content)
        if original_len <= max_length:
            return content
            
        # Try to locate Python Tracebacks
        traceback_match = re.search(r"(Traceback \(most recent call last\):.*)", content, re.DOTALL)
        if traceback_match:
            traceback_block = traceback_match.group(1)
            
            # If the traceback block itself is extremely long, keep only its final 15 lines (usually contains the core exception)
            tb_lines = traceback_block.split("\n")
            if len(tb_lines) > 15:
                traceback_block = "\n".join(tb_lines[-15:])
                
            head = content[:200]
            trunc_msg = f"\n\n... [TRUNCATED BY CONTEXT BUILDER (ORIGINAL LENGTH: {original_len} CHARS)] ...\n\n"
            compiled = head + trunc_msg + "[Extracted Traceback Exception]:\n" + traceback_block
            print(f"[Context Builder] Compiled tool output '{name}' by extracting Traceback. Compressed {original_len} to {len(compiled)} chars.")
            return compiled
            
        # Fallback to standard head-tail truncation if no Traceback is found
        head = content[:400]
        tail = content[-400:]
        trunc_msg = f"\n\n... [TRUNCATED BY CONTEXT BUILDER (ORIGINAL LENGTH: {original_len} CHARS)] ...\n\n"
        compiled = head + trunc_msg + tail
        print(f"[Context Builder] Compiled tool output '{name}' via head-tail truncation. Compressed {original_len} to {len(compiled)} chars.")
        return compiled

    def clear(self):
        """Reset the conversation context."""
        self.messages = []
