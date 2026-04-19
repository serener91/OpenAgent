from agents import Agent

from ._config import DEFAULT_MODEL
from ._schemas import FinancialReportData

WRITER_PROMPT = (
    "You are a senior financial analyst. You will be provided with the original query and "
    "a set of raw search summaries. Your task is to synthesize these into a long-form markdown "
    "report (at least several paragraphs) including a short executive summary and follow-up "
    "questions. If needed, you can call the available analysis tools (e.g. fundamentals_analysis, "
    "risk_analysis) to get short specialist write-ups to incorporate. "
    "If you are given a list of issues from a previous verification, address each issue explicitly "
    "before finalizing the report."
)

# Note: tools (fundamentals_analysis, risk_analysis) are attached at runtime in the manager.
writer_agent = Agent(
    name="Writer",
    instructions=WRITER_PROMPT,
    model=DEFAULT_MODEL,
    output_type=FinancialReportData,
)
