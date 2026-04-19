from agents import Agent

from ._config import DEFAULT_MODEL
from ._schemas import AnalysisSummary

FINANCIALS_PROMPT = (
    "You are a financial analyst focused on company fundamentals such as revenue, "
    "profit, margins and growth trajectory. Given a collection of web (and optional file) "
    "search results about a company, write a concise analysis of its recent financial "
    "performance. Pull out key metrics or quotes. Keep it under 2 paragraphs."
)

financials_agent = Agent(
    name="Fundamentals-Analyst",
    instructions=FINANCIALS_PROMPT,
    model=DEFAULT_MODEL,
    output_type=AnalysisSummary,
)

RISK_PROMPT = (
    "You are a risk analyst looking for potential red flags in a company's outlook. "
    "Given background research, produce a short analysis of risks such as competitive threats, "
    "regulatory issues, supply chain problems, or slowing growth. Keep it under 2 paragraphs."
)

risk_agent = Agent(
    name="Risk-Analyst",
    instructions=RISK_PROMPT,
    model=DEFAULT_MODEL,
    output_type=AnalysisSummary,
)
