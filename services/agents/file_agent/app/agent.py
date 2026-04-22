"""File agent implementation extending AgentWorker."""

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from app.config import settings
from app.worker import AgentWorker


class FileAgent(AgentWorker):
    """File agent that processes file-related tasks."""

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

        # Stub implementation - actual file processing will be added in later tasks
        task_type = data.get("task_type", "unknown")

        if task_type == "read_file":
            await self._handle_read_file(data)
        elif task_type == "list_directory":
            await self._handle_list_directory(data)
        else:
            self.logger.warning("unknown task type", task_type=task_type)

    async def _handle_read_file(self, data: dict[str, Any]) -> None:
        """Handle read file task."""
        self.logger.info("read file task completed", path=data.get("path"))

    async def _handle_list_directory(self, data: dict[str, Any]) -> None:
        """Handle list directory task."""
        self.logger.info(
            "list directory task completed",
            path=data.get("path"),
        )


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