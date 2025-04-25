# PDF Summary Agent with MCP Integration

This directory contains a PDF Summary Agent that extracts text from a single or multiple PDF files, generates concise summaries and key points using LLM, and outputs the results as HTML. The agent is designed for both standalone command-line use and seamless integration as an MCP (Model Context Protocol) tool or server.

---

## Features

- Summarizes single or multiple PDF files.
- Outputs HTML-formatted summaries and key points for easy web integration.
- Usable as a CLI tool, or as a full MCP server endpoint.
- Integrates with MCP via [FastMCP](https://github.com/modelcontextprotocol/fastmcp).
- Example PDF and summary output included for testing and demonstration. under /data

---

## Directory Contents

| File/Folder         | Description                                                                                      |
|---------------------|--------------------------------------------------------------------------------------------------|
| `agent.py`          | Core logic for PDF extraction, summarization, and HTML formatting.                  |
| `run_agent.py`      | CLI entry point for running the agent on PDF files.                                              |
| `mcp_server.py`     | Implements an MCP server using FastMCP, registering the PDF summary tool as an endpoint.         |
| `requirements.txt`  | Python dependencies.                                                                             |
| `data/LightRAG.pdf` | Example PDF file for testing.                                                                    |
| `data/summary.html` | Example summary output (HTML/Markdown).                                                          |
| `tests/`            | Pytest scripts for validating functionality.                                                       |

---

## MCP Integration Details

### MCP Server (`mcp_server.py`)

- Uses [FastMCP](https://github.com/modelcontextprotocol/fastmcp) to expose the PDF summary functionality as an MCP server endpoint.
- Registers the `pdf_summary-server` tool, which can be called by other MCP-compatible clients or agents.
- Example server configuration (see code comments for details):
  ```json
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
  ```
- To run the server:
  ```bash
  python mcp_server.py
  ```
- The server exposes the `pdf-summary-server` tool, which takes a list of PDF file paths and returns an HTML summary.

---

## Installation

1. **Clone the repository** (if not already done):
   ```bash
   git clone https://github.com/serener91/OpenAgent.git
   cd mcp_servers/pdf_summary
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
   - Or in a `.env` file in the `pdf_summary/` directory:
     ```
     OPENAI_API_KEY=your-api-key-here
     ```

---

## Usage

### 1. Command-Line Interface (CLI)

Run the agent directly on one or more PDF files:
```bash
python run_agent.py <pdf1>, <pdf2>, ... 
```
**Example:**
```bash
python run_agent.py data/Lost_in_the_Middle.pdf
```
The output will be an HTML-formatted summary and key points for each PDF.

### 2. MCP Server Usage

Run the agent as an MCP server endpoint:
```bash
python mcp_server.py
```
This starts a FastMCP server exposing the `pdf_summary-server` tool. Other MCP-compatible clients can call this tool with a list of PDF file paths to receive HTML summaries.

---

## Output

- For each PDF, the agent outputs:
  - The filename as a heading
  - A concise summary paragraph
  - 3–7 key points as a bullet list
- Output is formatted as HTML for easy embedding in web pages or dashboards.

---

## Dependencies

- `pdfplumber` — PDF text extraction
- `PyPDF2` — PDF text extraction (Recommended)
- `openai` — OpenAI API client
- `requests` — HTTP requests (for API calls)

Install all dependencies with:
```bash
uv sync
```

---

## Notes

- The agent requires a valid OpenAI API key with access to the GPT model (i.e. `gpt-4o-mini`).
- If `PyPDF2` is not installed, PDF extraction will not work.
- The included PDF file is for demonstration and testing purposes.
