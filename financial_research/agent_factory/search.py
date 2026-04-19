from agents import Agent, WebSearchTool

from ._config import DEFAULT_MODEL

SEARCH_PROMPT = (
    "You are a research assistant specializing in financial topics. "
    "Given a search term, use web search to retrieve up-to-date context and "
    "produce a short summary of at most 300 words. Focus on key numbers, events, "
    "or quotes that will be useful to a financial analyst."
)

search_agent = Agent(
    name="Searcher",
    instructions=SEARCH_PROMPT,
    model=DEFAULT_MODEL,
    tools=[WebSearchTool()],
)
