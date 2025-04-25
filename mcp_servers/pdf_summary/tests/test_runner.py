import os
import sys
from unittest import mock

import pytest

# Ensure the agent module is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runner import pdf_summary_agent


@pytest.fixture
def sample_pdf_path(tmp_path):
    # Create a dummy PDF file (content doesn't matter, will be mocked)
    pdf_file = tmp_path / "dummy.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%EOF")
    return str(pdf_file)


def mock_extract_text_from_pdf(pdf_path):
    # Return fixed text regardless of input
    return "This is a test PDF content for summarization."


def mock_summarize_text(text):
    # Return a fixed summary and keypoints
    return {
        "summary": "This is a summary.",
        "keypoints": ["Point 1", "Point 2", "Point 3"],
    }


def test_process_pdfs_html_output(sample_pdf_path):
    # Patch extract_text_from_pdf and summarize_text to avoid real file and API calls
    with (
        mock.patch.object(
            pdf_summary_agent,
            "extract_text_from_pdf",
            side_effect=mock_extract_text_from_pdf,
        ),
        mock.patch.object(
            pdf_summary_agent, "summarize_text", side_effect=mock_summarize_text
        ),
    ):
        html = pdf_summary_agent.summarize_pdfs([sample_pdf_path])
        # Check that the HTML contains expected sections
        assert "<h2>" in html
        assert "<h3>Summary</h3>" in html
        assert "<h3>Key Points</h3>" in html
        assert "<li>Point 1</li>" in html
        assert "This is a summary." in html


def test_format_summary_html():
    html = pdf_summary_agent.format_summary_html(
        "Summary text", ["A", "B"], filename="file.pdf"
    )
    assert "<h2>file.pdf</h2>" in html
    assert "<p>Summary text</p>" in html
    assert "<li>A</li>" in html
    assert "<li>B</li>" in html


def test_extract_text_from_pdf_importerror(monkeypatch):
    # Simulate pdfplumber not installed
    monkeypatch.setattr(pdf_summary_agent, "pdfplumber", None)
    with pytest.raises(ImportError):
        pdf_summary_agent.extract_text_from_pdf("anyfile.pdf")


def test_summarize_text_env_error(monkeypatch):
    # Simulate missing OPENAI_API_KEY
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(EnvironmentError):
        pdf_summary_agent.summarize_text("text")


def test_pdf_summary_tool_integration(sample_pdf_path):
    # Test the MCP tool interface with mocks
    from runner import mcp_tool

    with (
        mock.patch.object(
            pdf_summary_agent,
            "extract_text_from_pdf",
            side_effect=mock_extract_text_from_pdf,
        ),
        mock.patch.object(
            pdf_summary_agent, "summarize_text", side_effect=mock_summarize_text
        ),
    ):
        html = mcp_tool.pdf_summary_tool([sample_pdf_path])
        assert "This is a summary." in html
        assert "<li>Point 2</li>" in html


def test_run_agent_cli(monkeypatch, tmp_path, capsys):
    # Test the CLI entry point in run_agent.py
    test_pdf = tmp_path / "cli_test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n%EOF")
    # Patch process_pdfs to return a known string
    monkeypatch.setattr(
        pdf_summary_agent, "process_pdfs", lambda paths: "CLI HTML OUTPUT"
    )
    sys_argv = ["run_agent.py", str(test_pdf)]
    monkeypatch.setattr(sys, "argv", sys_argv)
    from runner import run_agent

    run_agent.main()
    captured = capsys.readouterr()
    assert "CLI HTML OUTPUT" in captured.out
