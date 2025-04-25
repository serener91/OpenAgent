"""
MCP Tool interface for RFP Analyzer Agent.

This exposes the agent as a tool.

"""
import asyncio
from mcp.server.fastmcp import FastMCP
from agent import get_summary

mcp = FastMCP("RFP analyzer MCP Server")

@mcp.tool()
async def rfp_analyzer(pdf_path: str) -> str:
    """
    RFP analyzer extracts and summarizes key information from RFP (Request for Proposal) PDF documents. It automatically identifies and summarizes essential elements such as SFP, MAR, budget, and project duration, and presents both a concise summary

    Args:
        pdf_path: absolute file path of PDF.

    Returns:
        HTML summary for PDF.
    """

    html_summary = await get_summary(pdf_path)

    return html_summary



def main(transport="stdio"):
    if transport == 'sse':
        print("Run the MCP server with sse transport...")
        mcp.run(transport=transport)
    elif transport == "stdio":
        print("un the MCP server with stdio transport...")
        mcp.run(transport=transport)
    else:
        raise NotImplementedError("choose sse or stdio")


if __name__ == "__main__":
    main()
