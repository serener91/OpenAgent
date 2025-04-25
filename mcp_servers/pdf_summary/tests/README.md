# runner/tests

This directory contains automated tests for the PDF summarization agent and its related interfaces, implemented in `test_runner.py`. These tests are designed to ensure the correctness, robustness, and integration of the PDF summarization workflow, including its core logic, error handling, and external interfaces.

## What does `test_runner.py` test?

The test suite covers the following aspects:

### 1. PDF Summarization Logic

- **Text Extraction and Summarization**: Mocks the PDF text extraction and summarization functions to verify that the agent processes PDF files and produces the expected HTML output, without relying on actual file I/O or external API calls.
- **HTML Formatting**: Checks that the HTML output generated for summaries and key points is correctly structured and contains all expected elements.

### 2. Error Handling

- **Missing Dependencies**: Simulates the absence of required libraries (e.g., `pdfplumber`) to ensure that the agent raises appropriate `ImportError` exceptions.
- **Missing Environment Variables**: Tests the behavior when required environment variables (such as `OPENAI_API_KEY`) are missing, ensuring that the agent fails gracefully with clear error messages.

### 3. Integration with External Interfaces

- **MCP Tool Interface**: Verifies that the agent integrates correctly with the MCP tool interface (`mcp_tool.pdf_summary_tool`), using mocks to simulate the summarization process and checking the output.
- **Command-Line Interface (CLI)**: Tests the CLI entry point (`run_agent.py`) by simulating command-line arguments and capturing standard output, ensuring that the CLI produces the expected HTML output.

## Why are these tests important?

- **Reliability**: By mocking external dependencies and simulating various scenarios, the tests ensure that the core logic works as intended and is resilient to common failure modes.
- **Integration Assurance**: The tests verify that the agent's functionality is correctly exposed through both the MCP tool and CLI, providing confidence that users can interact with the system in different ways.
- **Maintainability**: Comprehensive tests make it easier to refactor or extend the agent's functionality in the future, as regressions or breaking changes will be caught early.
- **Error Transparency**: Explicitly testing error conditions ensures that failures are handled gracefully and with informative messages, improving the user and developer experience.

## How to run the tests

From the root of the project, run:

```bash
pytest pdf_summary/tests/test_runner.py
```

This will execute all tests in the file and report any failures or errors.
