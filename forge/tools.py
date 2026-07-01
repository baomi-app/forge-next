"""Compatibility exports for the default tool registry and built-in tools."""

import importlib
import pkgutil

from forge import core_tools
from forge.tool_registry import ToolRegistry, registry, tool


def load_core_tools() -> None:
    """Import all built-in tool modules so they register themselves."""
    for module in pkgutil.iter_modules(core_tools.__path__, f"{core_tools.__name__}."):
        importlib.import_module(module.name)


load_core_tools()


def __getattr__(name: str):
    if name in registry.tools:
        return registry.tools[name]
    raise AttributeError(f"module 'forge.tools' has no attribute '{name}'")


__all__ = ["ToolRegistry", "registry", "tool", *registry.tools]
