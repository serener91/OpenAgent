"""Tool registry for MCP Gateway."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import structlog


@dataclass
class ToolDefinition:
    """Definition of a tool in the registry."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    registered_at: datetime


class ToolRegistry:
    """Registry for managing MCP tools."""

    def __init__(self):
        """Initialize the tool registry."""
        self._tools: dict[str, ToolDefinition] = {}
        self.logger = structlog.get_logger(__name__)

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        """Register a tool with the registry.

        Args:
            name: The tool name
            description: Description of what the tool does
            input_schema: JSON schema for tool input
            handler: The callable that executes the tool
        """
        if name in self._tools:
            self.logger.warning("tool already registered, overwriting", name=name)

        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            registered_at=datetime.now(timezone.utc),
        )
        self.logger.info("tool registered", name=name)

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get a tool by name.

        Args:
            name: The tool name

        Returns:
            The tool definition or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools.

        Returns:
            List of all tool definitions
        """
        return list(self._tools.values())

    async def execute_tool(self, name: str, **kwargs) -> Any:
        """Execute a tool by name.

        Args:
            name: The tool name
            **kwargs: Arguments to pass to the tool handler

        Returns:
            The result of the tool execution

        Raises:
            ValueError: If the tool is not found
        """
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool not found: {name}")

        self.logger.info("executing tool", name=name, kwargs=kwargs)
        result = await tool.handler(**kwargs)
        self.logger.info("tool execution completed", name=name)
        return result


# Global registry instance
registry = ToolRegistry()