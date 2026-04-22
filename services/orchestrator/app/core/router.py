"""LLM-powered task router."""

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import get_settings


class RoutingDecision(BaseModel):
    """Routing decision from LLM."""

    agent_name: str
    task_description: str
    priority: int
    reasoning: str


@dataclass
class AgentCapability:
    """Agent capability description."""

    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)


class LLMRouter:
    """LLM-powered task router."""

    def __init__(self):
        """Initialize the router."""
        self.agents: list[AgentCapability] = []
        self._settings = get_settings()

    def register_agent(self, agent: AgentCapability) -> None:
        """Register an agent.

        Args:
            agent: Agent capability to register.
        """
        self.agents.append(agent)

    def _build_routing_prompt(
        self, user_message: str, conversation_history: list[dict[str, Any]]
    ) -> str:
        """Build routing prompt for LLM.

        Args:
            user_message: Current user message.
            conversation_history: Recent conversation context.

        Returns:
            Formatted prompt string.
        """
        # Use last 5 messages from conversation history
        recent_history = conversation_history[-5:] if conversation_history else []

        history_lines = []
        for msg in recent_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            history_lines.append(f"{role}: {content}")

        history_text = "\n".join(history_lines) if history_lines else "No previous messages"

        agent_descriptions = []
        for agent in self.agents:
            caps = ", ".join(agent.capabilities) if agent.capabilities else "general assistance"
            agent_descriptions.append(f"- {agent.name}: {agent.description} (capabilities: {caps})")

        agents_text = "\n".join(agent_descriptions) if agent_descriptions else "No agents registered"

        return f"""You are a task routing assistant. Given the conversation history and current user message,
determine which agent should handle the request.

Conversation History (last 5 messages):
{history_text}

Current User Message: {user_message}

Available Agents:
{agents_text}

Respond ONLY with valid JSON in this exact format:
{{"agent_name": "name of selected agent", "task_description": "brief description of the task", "priority": 1-5, "reasoning": "brief explanation of routing decision"}}

Priority scale: 1=critical, 2=high, 3=medium, 4=low, 5=trivial"""

    async def route(
        self, user_message: str, conversation_history: list[dict[str, Any]]
    ) -> RoutingDecision:
        """Route user message to appropriate agent.

        Args:
            user_message: Current user message.
            conversation_history: Recent conversation context.

        Returns:
            Routing decision with selected agent and reasoning.
        """
        if not self.agents:
            raise ValueError("No agents registered for routing")

        prompt = self._build_routing_prompt(user_message, conversation_history)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._settings.llm.base_url}/chat/completions",
                    json={
                        "model": self._settings.llm.model,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                response.raise_for_status()
                data = await response.json()

            # Parse the LLM response for routing decision
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Try to extract JSON from the response
            try:
                # Handle case where LLM wraps JSON in markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                decision_data = json.loads(content.strip())
                return RoutingDecision(**decision_data)

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                # Fallback to first registered agent on parse error
                return self._fallback_decision(f"Parse error: {e}")

        except (httpx.HTTPError, httpx.TimeoutException) as e:
            # Fallback to first registered agent on network error
            return self._fallback_decision(f"HTTP error: {e}")

    def _fallback_decision(self, reason: str) -> RoutingDecision:
        """Create fallback routing decision.

        Args:
            reason: Reason for fallback.

        Returns:
            RoutingDecision using first registered agent.
        """
        first_agent = self.agents[0]
        return RoutingDecision(
            agent_name=first_agent.name,
            task_description="Fallback task - original routing failed",
            priority=3,
            reasoning=f"Fallback to {first_agent.name} due to: {reason}",
        )