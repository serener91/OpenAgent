"""
MCP Tool interface for PDF Summary Agent.

This exposes the agent as a tool.

Example MCP configuration file

{
  "mcpServers": {
    "pdf-summary-server": {
      "command": "uv",
      "args": [
        "--directory",
        "Path of Directory where has pdf_summary_mcp_server.py",
        "run",
        "mcp_server.py"
        ],
      "env": {}
    }
}

"""

from mcp.server.fastmcp import FastMCP
from agent import summarize_pdfs

mcp = FastMCP("PDF Summary MCP Server")


@mcp.tool()
def pdf_summary(pdf_paths: list[str]) -> str:
    """
    Summarize one or more PDF files and return an HTML summary.

    Args:
        pdf_paths: List of absolute file path of PDFs.

    Returns:
        HTML summary for all PDFs.
    """
    # Validate input files
    import os

    for path in pdf_paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")
    return summarize_pdfs(pdf_paths)


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