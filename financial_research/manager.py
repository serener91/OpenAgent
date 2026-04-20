from __future__ import annotations

import asyncio
import traceback
from collections.abc import Sequence
from dotenv import load_dotenv

from agents import RunResult, RunResultStreaming
from agents.mcp import MCPServerStreamableHttp
from langfuse import get_client, observe

from financial_research.agent_factory import (
    financials_agent,
    FinancialSearchItem,
    FinancialSearchPlan,
    FormattedPresentation,
    planner_agent,
    risk_agent,
    search_agent,
    VerificationResult,
    verifier_agent,
    FinancialReportData,
    writer_agent,
    build_formatter_agent,
    MCP_URL,
)
from tracing.tracing_utils import traced_runner_run


load_dotenv()
langfuse = get_client()


class FinancialResearchManager:
    """
    Orchestrates the financial research workflow:
        planning, parallel search, report writing, verification, and formatting.
    """

    def __init__(self, max_concurrent_searches: int = 5, max_verification_retries: int = 2) -> None:
        self._search_semaphore = asyncio.Semaphore(max_concurrent_searches)
        self._max_verification_retries = max_verification_retries

    # Main logic
    @observe(name="financial-research-workflow", as_type="agent")
    async def run(self, query: str) -> dict[str, object]:
        search_plan = await self._plan_searches(query)
        search_results = await self._perform_searches(search_plan)
        report = await self._write_report(query, search_results)

        # Feedback Loop
        verification = None
        for attempt in range(1, self._max_verification_retries + 1):
            is_last = attempt == self._max_verification_retries
            verification = await self._verify_report(report, is_last_attempt=is_last)
            if verification.verified:
                print(f"Report verified on attempt {attempt}.")
                break
            print(f"Attempt {attempt}/{self._max_verification_retries} — rewriting with feedback.")
            report = await self._write_report(
                query, search_results,
                feedback=verification.issues,
                is_last_attempt=is_last,
            )

        formatted = await self._format_report(report)

        return {
            "query": query,
            "search_plan": search_plan,
            "search_results": search_results,
            "report": report,
            "verification": verification,
            "final_report": formatted.markdown_report,
        }

    # ------------------------------------------------------------------ #
    # Actions                                                            #
    # ------------------------------------------------------------------ #
    async def _plan_searches(self, query: str) -> FinancialSearchPlan:
        print("Planning searches...")
        result = await traced_runner_run(
            agent=planner_agent,
            input_data=f"Query: {query}",
            observation_name="planner-agent-run",
            metadata={"stage": "planning"},
        )
        search_plan = result.final_output_as(FinancialSearchPlan)
        print(f"Will perform {len(search_plan.searches)} searches")
        return search_plan

    async def _perform_searches(self, search_plan: FinancialSearchPlan) -> Sequence[str]:
        print("Searching...")
        total = len(search_plan.searches)

        tasks = [
            asyncio.create_task(self._search(i, item))
            for i, item in enumerate(search_plan.searches, start=1)
        ]

        results: list[str] = []
        completed = succeeded = failed = 0

        for task in asyncio.as_completed(tasks):
            result = await task
            completed += 1
            if result is None:
                failed += 1
            else:
                results.append(result)
                succeeded += 1

            status = f"Searching... {completed}/{total} finished"
            if failed:
                status += f" ({succeeded} succeeded, {failed} failed)"
            print(status)

        summary = f"Searches finished: {succeeded}/{total} succeeded"
        if failed:
            summary += f", {failed} failed"
        print(summary)
        return results

    async def _search(self, index: int, item: FinancialSearchItem) -> str | None:
        async with self._search_semaphore:
            return await self._search_inner(index, item)

    async def _search_inner(self, index: int, item: FinancialSearchItem) -> str | None:
        try:
            result = await traced_runner_run(
                agent=search_agent,
                input_data=f"Search term: {item.query}\nReason: {item.reason}",
                observation_name="search-agent-run",
                metadata={"stage": "search", "search_index": index, "query": item.query},
            )
            return str(result.final_output)
        except Exception:
            traceback.print_exc()
            return None

    async def _write_report(
        self,
        query: str,
        search_results: Sequence[str],
        feedback: str | None = None,
        is_last_attempt: bool = False,
    ) -> FinancialReportData:
        print("Drafting up a report.." if not feedback else "Rewriting report with verifier feedback...")
        writer = self._build_writer_agent()
        writer_input = (
            f"Original query: {query}\n"
            f"Summarized search results: {search_results}"
        )
        if feedback:
            writer_input += f"\n\nVerifier issues to address:\n{feedback}"
        if is_last_attempt:
            writer_input += (
                "\n\nIMPORTANT: This is your final attempt. "
                "Produce the most complete and polished report possible. "
                "Do not leave any section incomplete or unresolved — deliver a finished report."
            )
        result = await traced_runner_run(
            agent=writer,
            input_data=writer_input,
            observation_name="writer-agent-run",
            metadata={"stage": "writing", "is_last_attempt": is_last_attempt},
        )
        report = result.final_output_as(FinancialReportData)
        print("Finished writing")
        return report

    async def _verify_report(
        self,
        report: FinancialReportData,
        is_last_attempt: bool = False,
    ) -> VerificationResult:
        print("Verifying report...")
        verifier_input = report.markdown_report
        if is_last_attempt:
            verifier_input += (
                "\n\nIMPORTANT: This is the final verification. "
                "The report will be delivered as-is after this check. "
                "Provide a definitive assessment and flag only blockers, not stylistic suggestions."
            )
        result = await traced_runner_run(
            agent=verifier_agent,
            input_data=verifier_input,
            observation_name="verifier-agent-run",
            metadata={"stage": "verification", "is_last_attempt": is_last_attempt},
        )
        verification = result.final_output_as(VerificationResult)
        print("Finished verificiation")
        return verification

    async def _format_report(self, report: FinancialReportData) -> FormattedPresentation:
        print("Formatting report as PowerPoint...")
        async with MCPServerStreamableHttp(
            name="html-to-ppt",
            params={"url": MCP_URL},
            client_session_timeout_seconds=120,
            cache_tools_list=True,
        ) as mcp_server:
            agent = build_formatter_agent(mcp_server)
            result = await traced_runner_run(
                agent=agent,
                input_data=f"Report:\n{report.markdown_report}\n\n",
                observation_name="formatter-agent-run",
                metadata={"stage": "formatting"},
            )
            formatted = result.final_output_as(FormattedPresentation)
        print("Finished formatting")
        return formatted

    # async def _format_report(self, report: FinancialReportData) -> FormattedReport:
    #     print("Formatting report for readability...")
    #     formatter_input = (
    #         f"Report:\n{report.markdown_report}\n\n"
    #     )
    #     result = await traced_runner_run(
    #         agent=formatter_agent,
    #         input_data=formatter_input,
    #         observation_name="formatter-agent-run",
    #         metadata={"stage": "formatting"},
    #     )
    #     formatted = result.final_output_as(FormattedReport)
    #     print("Finished formatting")
    #     return formatted

    # ------------------------------------------------------------------ #
    # Subagent for writer agent                                          #
    # ------------------------------------------------------------------ #
    async def _summary_extractor(self, run_result: RunResult | RunResultStreaming) -> str:
        return str(run_result.final_output.summary)

    def _build_writer_agent(self):
        fundamentals_tool = financials_agent.as_tool(
            tool_name="fundamentals_analysis",
            tool_description="Use to get a short write-up of key financial metrics",
            custom_output_extractor=self._summary_extractor,
        )
        risk_tool = risk_agent.as_tool(
            tool_name="risk_analysis",
            tool_description="Use to get a short write-up of potential red flags",
            custom_output_extractor=self._summary_extractor,
        )
        return writer_agent.clone(tools=[fundamentals_tool, risk_tool])
