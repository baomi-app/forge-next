from typing import List, Dict, Any, Optional

class Context:
    """Manages the conversation history (context) for the Agent."""
    
    def __init__(self, system_prompt: Optional[str] = None):
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
        """Add the execution output of a tool back to the history."""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content
        })

    def get_messages(self) -> List[Dict[str, Any]]:
        """Return the current message list ready for LLM consumption."""
        return self.messages

    def clear(self):
        """Reset the conversation context."""
        self.messages = []
