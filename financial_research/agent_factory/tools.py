from pathlib import Path
from dotenv import load_dotenv
from agents import function_tool
from langfuse import get_client

from ._config import REPORTS_DIR

root_dir = Path(__file__).parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

tracer = get_client()


@function_tool(needs_approval=False, defer_loading=False)
def save_md_file(content: str, file_name: str) -> str:
    """
    Save markdown content to a file in the reports directory.
    Args:
        content: The markdown content to save.
        file_name: The name of the file (with or without .md extension).
    Returns:
        A string confirming the saved file path.
    """
    with tracer.start_as_current_observation(
        as_type="span",
        name="save-md-file-tool",
        input={"file_name": file_name},
    ) as span:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        if not file_name.endswith(".md"):
            file_name = f"{file_name}.md"

        file_path = REPORTS_DIR / file_name
        file_path.write_text(content, encoding="utf-8")

        output = f"Report saved to {file_path}"
        span.update(output={"result": output})
        return output


@function_tool(needs_approval=False, defer_loading=False)
def save_html_file(content: str, file_name: str) -> str:
    """
    Save HTML content to a file in the reports directory.
    Args:
        content: The HTML content to save.
        file_name: The name of the file (with or without .html extension).
    Returns:
        A string confirming the saved file path.
    """
    with tracer.start_as_current_observation(
        as_type="span",
        name="save-html-file-tool",
        input={"file_name": file_name},
    ) as span:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        if not file_name.endswith(".html"):
            file_name = f"{file_name}.html"

        file_path = REPORTS_DIR / file_name
        file_path.write_text(content, encoding="utf-8")

        output = f"Report saved to {file_path}"
        span.update(output={"result": output})
        return output
