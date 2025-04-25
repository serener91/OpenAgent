OpenAI Agents SDK is a framework for building multi-agent workflows.
Compatible with any model providers that support the OpenAI Chat Completions API format

Install
- pip install openai-agents

Core concepts
- Agents: LLMs (configured with instructions, tools, guardrails, and handoffs)
- Handoffs: A specialized tool call used by the Agents SDK for transferring control between agents
- Guardrails: Configurable safety checks for input and output validation
- Tracing: Built-in tracking of agent runs, allowing you to view, debug and optimize your workflows

Agent Loop
- When you call Runner.run(), we run a loop until we get a final output
- "max_turns" parameter that you can use to limit the number of times the loop executes
- Order
  1. We call the LLM, using the model and settings on the agent, and the message history. 
  2. The LLM returns a response, which may include tool calls.
  3. If the response has a final output (see below for more on this), we return it and end the loop.
  4. If the response has a handoff, we set the agent to the new agent and go back to step 1.
  5. We process the tool calls (if any) and append the tool responses messages. Then we go to step 1.

Output
- Can control the format of final output with "output_type" parameter
- If the current agent has an output_type, the loop runs until the agent produces structured output matching that type.
- If the current agent does not have an output_type, the loop runs until the current agent produces a message without any tool calls/handoffs.

