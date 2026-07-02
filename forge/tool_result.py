from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ToolResult:
    """Structured result produced by a tool execution."""

    content: str
    status: str = "success"
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, content: Any, metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        return cls(content=str(content), status="success", metadata=metadata or {})

    @classmethod
    def error(
        cls,
        content: Any,
        error_type: str = "error",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ToolResult":
        return cls(
            content=str(content),
            status="error",
            error_type=error_type,
            metadata=metadata or {},
        )

    @classmethod
    def from_value(cls, value: Any) -> "ToolResult":
        if isinstance(value, cls):
            return value
        return cls.success(value)

    @property
    def is_error(self) -> bool:
        return self.status == "error"

    def to_trace_dict(self) -> Dict[str, Any]:
        data = {
            "status": self.status,
            "content": self.content,
        }
        if self.error_type:
            data["error_type"] = self.error_type
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    def __str__(self) -> str:
        return self.content

    def __contains__(self, item: str) -> bool:
        return item in self.content

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.content == other
        return super().__eq__(other)
