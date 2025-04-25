# RFP Analyzer Agent with MCP Integration

This directory contains an RFP Analyzer Agent that extracts and summarizes key information from RFP (Request for Proposal) PDF documents. The agent identifies and summarizes essential elements such as SFR, MAR, budget, and project duration, and outputs the results as HTML. It is designed for seamless integration as an MCP (Model Context Protocol) tool/server and can also be used as a Python module.

---

## Features

- Extracts and summarizes SFR, MAR, budget, and project duration from RFP PDF files.
- Outputs HTML-formatted summaries for easy web integration or reporting.
- Usable as a Python module or as a full MCP server endpoint.
- Integrates with MCP via [FastMCP](https://github.com/modelcontextprotocol/fastmcp).
- Example RFP PDF and summary output included for testing and demonstration under `/data`.

---

## Directory Contents

| File/Folder              | Description                                                                                      |
|--------------------------|--------------------------------------------------------------------------------------------------|
| `agent.py`               | Core logic for PDF extraction, RFP information extraction, and HTML formatting.                  |
| `mcp_server.py`          | Implements an MCP server using FastMCP, registering the RFP analyzer tool as an endpoint.        |
| `pdf_extract.py`         | PDF parsing and filtering utilities for extracting relevant sections.                            |
| `utils.py`               | Utility functions for OpenAI inference and HTML conversion.                                      |
| `prompts.json`           | Prompt templates for LLM-based extraction and summarization.                                     |
| `document_filter.json`   | Filter keywords for extracting relevant RFP sections.                                            |
| `requirements.txt`       | Python dependencies.                                                                             |
| `data/`                  | Example RFP PDF and sample output for testing.                                                   |

---

## MCP Integration Details

### MCP Server (`mcp_server.py`)

- Uses [FastMCP](https://github.com/modelcontextprotocol/fastmcp) to expose the RFP analyzer functionality as an MCP server endpoint.
- Registers the `rfp_analyzer` tool, which can be called by other MCP-compatible clients or agents.
- Example server configuration (see code comments for details):
  ```json
  {
    "mcpServers": {
      "rfp-server": {
        "command": "uv",
        "args": [
          "--directory",
          "Path of Directory where mcp_server.py is located",
          "run",
          "mcp_server.py"
        ],
        "env": {}
      }
    }
  }
  ```
- To run the server:
  ```bash
  python mcp_server.py
  ```
- The server exposes the `rfp_analyzer` tool, which takes a PDF file path and returns an HTML summary.

---

## Installation

1. **Clone the repository** (if not already done):
   ```bash
   git clone https://github.com/serener91/OpenAgent.git
   cd mcp_servers/rfp
   ```

2. **Install dependencies** (preferably in a virtual environment):
   ```bash
   pip install -r requirements.txt
   ```

3. **Set your OpenAI API key** (required for summarization):
   - As an environment variable:
     ```bash
     export OPENAI_API_KEY=your-api-key-here
     ```
   - Or in a `.env` file in the `rfp/` directory:
     ```
     OPENAI_API_KEY=your-api-key-here
     ```

---

## Usage

### 1. As a Python Module

You can use the agent directly in your Python code to summarize an RFP PDF:
```python
import asyncio
from agent import get_summary

result_html = asyncio.run(get_summary("data/2025년 경기관광정보서비스 통합 운영 과업지시서.pdf"))
print(result_html)
```
The output will be an HTML-formatted summary of the RFP.

### 2. MCP Server Usage

Run the agent as an MCP server endpoint:
```bash
python mcp_server.py
```
This starts a FastMCP server exposing the `rfp_analyzer` tool. Other MCP-compatible clients can call this tool with a PDF file path to receive an HTML summary.

---

## Output

- For each RFP PDF, the agent outputs:
  - The filename as a heading
  - Budget and project duration summary
  - MAR and SFR key points as HTML bullet lists
- Output is formatted as HTML for easy embedding in web pages or dashboards.

---

## Dependencies

- `openai` — OpenAI API client
- `PyPDF2` — PDF text extraction
- `python-dotenv` — Environment variable management
- `tqdm` — Progress bar for PDF parsing

Install all dependencies with:
```bash
pip install -r requirements.txt
```

---

## Notes

- The agent requires a valid OpenAI API key with access to the GPT model (e.g., `gpt-4o-mini` or `gpt-4.1`).
- If `PyPDF2` is not installed, PDF extraction will not work.
- The included PDF file in `/data` is for demonstration and testing purposes.
