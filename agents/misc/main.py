import asyncio

from agents import (
    Agent,
    AgentsException,
    GuardrailFunctionOutput,
    InputGuardrail,
    InputGuardrailTripwireTriggered,
    Runner,
    enable_verbose_stdout_logging,
    function_tool,
    set_default_openai_api,
    set_default_openai_client,
    set_default_openai_key,
    set_tracing_disabled,
)
from dotenv import load_dotenv
from openai.types.responses import ResponseTextDeltaEvent
from pydantic import BaseModel

load_dotenv()

# set_default_openai_key("sk-...")
set_default_openai_api(api="chat_completions")
set_tracing_disabled(True)
enable_verbose_stdout_logging()

# Using OpenAI Compatible API
# custom_client = AsyncOpenAI(
#     base_url="http://175.196.78.7:30000/v1", api_key="codeassist194"
# )
# set_default_openai_client(custom_client)


@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."


async def use_function(model: str = "gpt-4o"):
    agent = Agent(
        model=model,
        name="Hello world",
        instructions="You are a helpful agent.",
        handoff_description="A description of the agent. This is used when the agent is used as a handoff, so that an LLM knows what it does and when to invoke it.",
        tools=[get_weather],
        mcp_servers=[], # Every time the agent runs, it will include tools from these servers in the list of available tools

    )
    result = await Runner.run(agent, input="What's the weather in Tokyo?")
    return result.final_output


async def stream_agent(model: str = "gpt-4o"):
    agent = Agent(
        model=model,
        name="Joker",
        instructions="You are a helpful assistant. Use the provided tool to answer the question.",
    )

    result = Runner.run_streamed(agent, input="Please tell me 5 jokes.")
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(
            event.data, ResponseTextDeltaEvent
        ):
            print(event.data.delta, end="", flush=True)


class HomeworkOutput(BaseModel):
    is_homework: bool
    reasoning: str


guardrail_agent = Agent(
    name="Guardrail check",
    instructions="Check if the user is asking about homework.",
    output_type=HomeworkOutput,
)

math_tutor_agent = Agent(
    name="Math Tutor",
    handoff_description="Specialist agent for math questions",
    instructions="You provide help with math problems. Explain your reasoning at each step and include examples",
)

history_tutor_agent = Agent(
    name="History Tutor",
    handoff_description="Specialist agent for historical questions",
    instructions="You provide assistance with historical queries. Explain important events and context clearly.",
)


async def homework_guardrail(ctx, agent, input_data):
    result = await Runner.run(guardrail_agent, input_data, context=ctx.context)
    final_output = result.final_output_as(HomeworkOutput)
    return GuardrailFunctionOutput(
        output_info=final_output, tripwire_triggered=not final_output.is_homework
    )


triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine which agent to use based on the user's homework question",
    handoffs=[history_tutor_agent, math_tutor_agent],
    input_guardrails=[InputGuardrail(guardrail_function=homework_guardrail)],
)


async def main():
    try:
        # result = await Runner.run(triage_agent, "what is a function?")
        # print(result.final_output)

        result = await Runner.run(triage_agent, "I want to play MarioKart")
        print(result.final_output)
    except InputGuardrailTripwireTriggered:
        print("Ask about homework!")
        return "Invalid request!"


if __name__ == "__main__":
    asyncio.run(main())
