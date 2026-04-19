import asyncio
from agents import set_tracing_disabled

from financial_research.manager import FinancialResearchManager

# Disable Agents SDK tracing -- Replace with Langfuse
set_tracing_disabled(disabled=True)


# Entrypoint
async def main() -> dict[str, object]:
    query = "Write up an analysis of NVIDIA's fourth quarter of fiscal 2025. Final report must be written in Korean."
    mgr = FinancialResearchManager()
    return await mgr.run(query)


if __name__ == "__main__":
    print(asyncio.run(main()))
