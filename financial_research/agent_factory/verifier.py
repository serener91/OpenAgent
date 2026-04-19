from agents import Agent

from ._config import DEFAULT_MODEL
from ._schemas import VerificationResult

VERIFIER_PROMPT = (
    "You are a meticulous auditor. You have been handed a financial analysis report. "
    "Your job is to verify the report is internally consistent, clearly sourced, and makes "
    "no unsupported claims. Point out any issues or uncertainties."
)

verifier_agent = Agent(
    name="Auditor",
    instructions=VERIFIER_PROMPT,
    model=DEFAULT_MODEL,
    output_type=VerificationResult,
)
