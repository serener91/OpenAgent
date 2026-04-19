from agents import Agent

from ._config import DEFAULT_MODEL
from ._schemas import FinancialSearchPlan

PLANNER_PROMPT = (
    "You are a financial research planner. Given a request for financial analysis, "
    "produce a set of web searches to gather the context needed. Aim for recent "
    "headlines, earnings calls or 10-K snippets, analyst commentary, and industry background. "
    "Output between 3 and 10 search terms to query for."
)

planner_agent = Agent(
    name="Planner",
    instructions=PLANNER_PROMPT,
    model=DEFAULT_MODEL,
    output_type=FinancialSearchPlan,
)
