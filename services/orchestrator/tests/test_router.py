"""Tests for LLM router."""

import httpx
from unittest.mock import AsyncMock, patch

import pytest

from app.core.router import AgentCapability, LLMRouter, RoutingDecision


class TestAgentCapability:
    """Tests for AgentCapability dataclass."""

    def test_agent_capability_creation(self):
        """Test basic AgentCapability creation."""
        agent = AgentCapability(
            name="test-agent",
            description="A test agent",
            capabilities=["coding", "testing"],
        )
        assert agent.name == "test-agent"
        assert agent.description == "A test agent"
        assert agent.capabilities == ["coding", "testing"]

    def test_agent_capability_defaults(self):
        """Test AgentCapability with default capabilities."""
        agent = AgentCapability(name="simple-agent", description="A simple agent")
        assert agent.capabilities == []


class TestRoutingDecision:
    """Tests for RoutingDecision model."""

    def test_routing_decision_creation(self):
        """Test basic RoutingDecision creation."""
        decision = RoutingDecision(
            agent_name="agent-1",
            task_description="Test task",
            priority=2,
            reasoning="Good match",
        )
        assert decision.agent_name == "agent-1"
        assert decision.task_description == "Test task"
        assert decision.priority == 2
        assert decision.reasoning == "Good match"


class TestLLMRouter:
    """Tests for LLMRouter."""

    @pytest.fixture
    def router(self):
        """Create a router instance."""
        return LLMRouter()

    @pytest.fixture
    def sample_agent(self):
        """Create a sample agent capability."""
        return AgentCapability(
            name="code-agent",
            description="Agent for coding tasks",
            capabilities=["python", "javascript", "refactoring"],
        )

    @pytest.fixture
    def second_agent(self):
        """Create a second agent capability."""
        return AgentCapability(
            name="docs-agent",
            description="Agent for documentation tasks",
            capabilities=["writing", "reviewing", "formatting"],
        )

    def test_register_agent(self, router, sample_agent):
        """Test registering an agent."""
        assert len(router.agents) == 0
        router.register_agent(sample_agent)
        assert len(router.agents) == 1
        assert router.agents[0].name == "code-agent"

    def test_register_multiple_agents(self, router, sample_agent, second_agent):
        """Test registering multiple agents."""
        router.register_agent(sample_agent)
        router.register_agent(second_agent)
        assert len(router.agents) == 2
        assert router.agents[0].name == "code-agent"
        assert router.agents[1].name == "docs-agent"

    def test_build_routing_prompt(self, router, sample_agent):
        """Test building routing prompt."""
        router.register_agent(sample_agent)

        user_message = "Write a Python function"
        conversation_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        prompt = router._build_routing_prompt(user_message, conversation_history)

        assert "code-agent" in prompt
        assert "Python function" in prompt
        assert "user: Hello" in prompt
        assert "assistant: Hi there" in prompt

    def test_build_routing_prompt_empty_history(self, router, sample_agent):
        """Test building prompt with empty conversation history."""
        router.register_agent(sample_agent)

        prompt = router._build_routing_prompt("Test message", [])

        assert "No previous messages" in prompt
        assert "code-agent" in prompt

    def test_build_routing_prompt_truncates_to_five_messages(self, router, sample_agent):
        """Test that prompt only includes last 5 messages."""
        router.register_agent(sample_agent)

        conversation_history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(10)
        ]

        prompt = router._build_routing_prompt("Latest message", conversation_history)

        # Should only have messages 5-9 (last 5)
        assert "Message 5" in prompt
        assert "Message 9" in prompt
        assert "Message 0" not in prompt
        assert "Message 4" not in prompt

    @pytest.mark.asyncio
    async def test_route_success(self, router, sample_agent):
        """Test successful routing with mocked httpx."""
        router.register_agent(sample_agent)

        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": '{"agent_name": "code-agent", "task_description": "Write Python code", "priority": 2, "reasoning": "Code task detected"}'
                    }
                }
            ]
        }

        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.raise_for_status = AsyncMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            decision = await router.route("Write a Python function", [])

        assert decision.agent_name == "code-agent"
        assert decision.task_description == "Write Python code"
        assert decision.priority == 2
        assert "Code task detected" in decision.reasoning

    @pytest.mark.asyncio
    async def test_route_fallback_on_error(self, router, sample_agent):
        """Test fallback to first agent on HTTP error."""
        router.register_agent(sample_agent)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Connection timeout"))
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            decision = await router.route("Any message", [])

        assert decision.agent_name == "code-agent"
        assert "Fallback" in decision.reasoning
        assert decision.priority == 3

    @pytest.mark.asyncio
    async def test_route_fallback_on_json_parse_error(self, router, sample_agent, second_agent):
        """Test fallback when LLM returns invalid JSON."""
        router.register_agent(sample_agent)
        router.register_agent(second_agent)

        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": "This is not valid JSON"
                    }
                }
            ]
        }

        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.raise_for_status = AsyncMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            decision = await router.route("Any message", [])

        assert decision.agent_name == "code-agent"  # First agent
        assert "Fallback" in decision.reasoning

    @pytest.mark.asyncio
    async def test_route_raises_when_no_agents(self, router):
        """Test that route raises error when no agents registered."""
        with pytest.raises(ValueError, match="No agents registered"):
            await router.route("Any message", [])

    @pytest.mark.asyncio
    async def test_route_with_json_in_markdown(self, router, sample_agent):
        """Test parsing JSON wrapped in markdown code blocks."""
        router.register_agent(sample_agent)

        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"agent_name": "code-agent", "task_description": "Test", "priority": 1, "reasoning": "Test"}\n```'
                    }
                }
            ]
        }

        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.raise_for_status = AsyncMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            decision = await router.route("Test", [])

        assert decision.agent_name == "code-agent"
        assert decision.priority == 1