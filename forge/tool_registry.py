import copy
import inspect
from typing import Any, Callable, Dict, List, Optional

from forge.sandbox import BaseSandbox


class ToolRegistry:
    """Manages coding tools registration, schema generation, and dependency injection execution."""

    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []
        self._definition_indexes: Dict[str, int] = {}

    def register(self, func: Callable) -> Callable:
        name = func.__name__
        self.tools[name] = func

        sig = inspect.signature(func)
        doc = func.__doc__ or ""
        description = doc.strip().split("\n")[0] if doc else "No description provided."

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls", "sandbox", "runner", "session", "subagent_manager"):
                continue

            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == float:
                param_type = "number"
            elif param.annotation == bool:
                param_type = "boolean"

            properties[param_name] = {
                "type": param_type,
                "description": f"Parameter '{param_name}'",
            }

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        self._upsert_definition(name, {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
        return func

    def register_mcp_tool(self, name: str, description: str, input_schema: Dict[str, Any], execute_callback: Callable):
        """Dynamically registers an external MCP tool definition and maps its call logic."""
        self.tools[name] = execute_callback
        self._upsert_definition(name, {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": input_schema,
            },
        })
        print(f"[Tool Registry] Dynamically registered external MCP tool: '{name}'")

    def clone(self) -> "ToolRegistry":
        """Return an isolated copy of this registry for one runner or demo."""
        cloned = ToolRegistry()
        cloned.tools = dict(self.tools)
        cloned.tool_definitions = copy.deepcopy(self.tool_definitions)
        cloned._definition_indexes = dict(self._definition_indexes)
        return cloned

    def _upsert_definition(self, name: str, definition: Dict[str, Any]):
        """Insert or replace a tool schema by name so repeated loads stay idempotent."""
        if name in self._definition_indexes:
            self.tool_definitions[self._definition_indexes[name]] = definition
            return
        self._definition_indexes[name] = len(self.tool_definitions)
        self.tool_definitions.append(definition)

    def execute(
        self,
        name: str,
        args: Dict[str, Any],
        sandbox: Optional[BaseSandbox] = None,
        runner: Optional[Any] = None,
        session: Optional[Any] = None,
        subagent_manager: Optional[Any] = None,
    ) -> str:
        """Executes a registered tool, dynamically injecting hidden runtime dependencies."""
        if name not in self.tools:
            return f"Error: Tool '{name}' is not registered."
        try:
            try:
                sig = inspect.signature(self.tools[name])
                if "sandbox" in sig.parameters:
                    args["sandbox"] = sandbox
                if "runner" in sig.parameters:
                    args["runner"] = runner
                if "session" in sig.parameters:
                    args["session"] = session
                if "subagent_manager" in sig.parameters:
                    args["subagent_manager"] = subagent_manager
            except (ValueError, TypeError):
                pass

            result = self.tools[name](**args)
            return str(result)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"


registry = ToolRegistry()


def tool(func: Callable) -> Callable:
    """Decorator to register a function as a tool."""
    return registry.register(func)
