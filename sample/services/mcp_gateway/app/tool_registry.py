"""Tool registry for MCP Gateway."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import structlog


@dataclass
class ToolDefinition:
    """Definition of a tool in the registry."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any] | None = None
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
        handler: Callable[..., Any] | None = None,
    ) -> None:
        """Register a tool with the registry.

        Args:
            name: The tool name
            description: Description of what the tool does
            input_schema: JSON schema for tool input
            handler: The callable that executes the tool (optional)
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

# Tool handlers dict for direct function references
TOOL_HANDLERS: dict[str, Callable[..., Any]] = {}


async def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Execute a tool by name with arguments.

    Args:
        name: The tool name
        arguments: Dictionary of arguments to pass to the tool

    Returns:
        The result of the tool execution

    Raises:
        ValueError: If the tool is not found or has no handler
    """
    tool = registry.get_tool(name)
    if not tool:
        raise ValueError(f"Tool not found: {name}")

    if not tool.handler:
        raise ValueError(f"Tool has no handler registered: {name}")

    return await tool.handler(**arguments)


async def read_file_handler(path: str, max_lines: int | None = None) -> dict[str, Any]:
    """Read file contents handler.

    Args:
        path: Path to the file to read
        max_lines: Maximum number of lines to read (optional)

    Returns:
        Dictionary with file contents or error
    """
    try:
        file_path = Path(path).resolve()
        if not file_path.exists():
            return {"error": f"File not found: {path}"}
        if not file_path.is_file():
            return {"error": f"Path is not a file: {path}"}

        contents = file_path.read_text()
        if max_lines is not None:
            lines = contents.splitlines()
            contents = "\n".join(lines[:max_lines])

        return {
            "success": True,
            "path": str(file_path),
            "contents": contents,
            "size": len(contents),
        }
    except PermissionError:
        return {"error": f"Permission denied: {path}"}
    except Exception as e:
        return {"error": f"Error reading file: {str(e)}"}


async def list_directory_handler(path: str) -> dict[str, Any]:
    """List directory contents handler.

    Args:
        path: Path to the directory to list

    Returns:
        Dictionary with directory contents or error
    """
    try:
        dir_path = Path(path).resolve()
        if not dir_path.exists():
            return {"error": f"Directory not found: {path}"}
        if not dir_path.is_dir():
            return {"error": f"Path is not a directory: {path}"}

        entries = []
        for entry in dir_path.iterdir():
            stat = entry.stat()
            entries.append(
                {
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat.st_size if entry.is_file() else None,
                }
            )

        return {"success": True, "path": str(dir_path), "entries": entries}
    except PermissionError:
        return {"error": f"Permission denied: {path}"}
    except Exception as e:
        return {"error": f"Error listing directory: {str(e)}"}


def register_file_tools() -> None:
    """Register file tool handlers with the registry."""
    handlers = {
        "read_file": read_file_handler,
        "list_directory": list_directory_handler,
    }
    TOOL_HANDLERS.update(handlers)

    registry.register_tool(
        name="read_file",
        description="Read the contents of a file",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read"},
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (optional)",
                },
            },
            "required": ["path"],
        },
        handler=read_file_handler,
    )

    registry.register_tool(
        name="list_directory",
        description="List contents of a directory",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the directory to list"},
            },
            "required": ["path"],
        },
        handler=list_directory_handler,
    )