"""File agent implementation using OpenAI Agents SDK."""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import structlog
from agents import Agent, function_tool

from app.config import settings
from app.worker import AgentWorker


def create_file_tools() -> list:
    """Create file operation tools using @function_tool decorator.

    Returns:
        List of function tools for file operations.
    """

    @function_tool
    def read_file(path: str, max_lines: int = 100) -> str:
        """Read contents of a file.

        Args:
            path: The path to the file to read.
            max_lines: Maximum number of lines to read (default 100).

        Returns:
            The file contents as a string, truncated if necessary.
        """
        try:
            with open(path, "r") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        return "".join(lines) + f"\n... (truncated at {max_lines} lines)"
                    lines.append(line)
                return "".join(lines)
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error reading file: {e}"

    @function_tool
    def list_directory(path: str = ".") -> str:
        """List contents of a directory.

        Args:
            path: The path to the directory to list (default current directory).

        Returns:
            A string listing the directory contents.
        """
        try:
            entries = os.listdir(path)
            result = [f"Directory: {path}"]
            for entry in sorted(entries):
                full_path = os.path.join(path, entry)
                if os.path.isdir(full_path):
                    result.append(f"  [DIR]  {entry}/")
                else:
                    size = os.path.getsize(full_path)
                    result.append(f"  [FILE] {entry} ({size} bytes)")
            return "\n".join(result)
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except FileNotFoundError:
            return f"Error: Directory not found: {path}"
        except Exception as e:
            return f"Error listing directory: {e}"

    return [read_file, list_directory]


class FileAgent(AgentWorker):
    """File agent that processes file-related tasks using OpenAI Agents SDK."""

    def __init__(self):
        """Initialize the file agent with Agent SDK."""
        super().__init__()
        self.capabilities = ["read_file", "list_directory"]
        file_tools = create_file_tools()
        self.agent = Agent(
            name="file_agent",
            instructions="You are a helpful file operations assistant. Use the available tools to read files and list directories.",
            tools=file_tools,
        )
        self.logger.info(
            "file agent initialized",
            capabilities=self.capabilities,
        )

    async def process_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Process a task using the Agent SDK.

        Args:
            task: The task data containing conversation history and instructions.

        Returns:
            The agent's response.
        """
        self.logger.info("processing task with agent", task=task)

        conversation_history = task.get("history", [])
        user_message = task.get("message", "")

        # Build messages for the agent
        messages = []
        for msg in conversation_history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })
        if user_message:
            messages.append({"role": "user", "content": user_message})

        try:
            response = await self.agent.run("\n".join([m["content"] for m in messages]))
            return {"status": "success", "response": response}
        except Exception as e:
            self.logger.error("agent run failed", error=str(e))
            return {"status": "error", "error": str(e)}

    async def process_message(self, message_id: str, data: dict[str, Any]) -> None:
        """Process a file task message.

        Args:
            message_id: The Redis stream message ID
            data: The message data containing task details
        """
        self.logger.info(
            "processing file task",
            message_id=message_id,
            data=data,
        )

        task_type = data.get("task_type", "unknown")

        if task_type == "agent_task":
            result = await self.process_task(data)
            self.logger.info("agent task completed", result=result)
        elif task_type == "read_file":
            await self._handle_read_file(data)
        elif task_type == "list_directory":
            await self._handle_list_directory(data)
        else:
            self.logger.warning("unknown task type", task_type=task_type)

    async def _handle_read_file(self, data: dict[str, Any]) -> None:
        """Handle read file task."""
        path = data.get("path", "")
        max_lines = data.get("max_lines", 100)

        @function_tool
        def read_file_impl(path: str, max_lines: int = 100) -> str:
            try:
                with open(path, "r") as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            return "".join(lines) + f"\n... (truncated at {max_lines} lines)"
                        lines.append(line)
                    return "".join(lines)
            except FileNotFoundError:
                return f"Error: File not found: {path}"
            except PermissionError:
                return f"Error: Permission denied: {path}"
            except Exception as e:
                return f"Error reading file: {e}"

        result = read_file_impl(path, max_lines)
        self.logger.info("read file task completed", path=path, result=result[:100])

    async def _handle_list_directory(self, data: dict[str, Any]) -> None:
        """Handle list directory task."""
        path = data.get("path", ".")

        @function_tool
        def list_directory_impl(path: str = ".") -> str:
            try:
                entries = os.listdir(path)
                result = [f"Directory: {path}"]
                for entry in sorted(entries):
                    full_path = os.path.join(path, entry)
                    if os.path.isdir(full_path):
                        result.append(f"  [DIR]  {entry}/")
                    else:
                        size = os.path.getsize(full_path)
                        result.append(f"  [FILE] {entry} ({size} bytes)")
                return "\n".join(result)
            except PermissionError:
                return f"Error: Permission denied: {path}"
            except FileNotFoundError:
                return f"Error: Directory not found: {path}"
            except Exception as e:
                return f"Error listing directory: {e}"

        result = list_directory_impl(path)
        self.logger.info("list directory task completed", path=path)


async def main():
    """Main entry point for the file agent."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level=20),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )

    agent = FileAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())