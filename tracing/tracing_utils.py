from __future__ import annotations

from typing import Any
from pathlib import Path
from dotenv import load_dotenv
from agents import Agent, Runner
from langfuse import get_client


root_dir = Path(__file__).parent.parent
load_dotenv(dotenv_path=root_dir / ".env")
langfuse = get_client()


async def traced_runner_run(
    *,
    agent: Agent,
    input_data: Any,
    observation_name: str,
    metadata: dict[str, Any] | None = None,
):
    with langfuse.start_as_current_observation(
        name=observation_name,
        as_type="generation",
        input=input_data,
    ) as observation:
        try:
            result = await Runner.run(agent, input_data)
            observation.update(
                output={"final_output": str(result.final_output)},
                metadata={
                    "agent_name": agent.name,
                    **(metadata or {}),
                },
            )
            return result
        except Exception as exc:
            observation.update(
                level="ERROR",
                status_message=str(exc),
                metadata={
                    "agent_name": agent.name,
                    **(metadata or {}),
                },
            )
            raise
