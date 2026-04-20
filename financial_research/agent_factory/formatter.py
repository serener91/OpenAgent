from agents import Agent
from agents.mcp import MCPServerStreamableHttp

from ._config import DEFAULT_MODEL
from ._schemas import FormattedReport, FormattedPresentation
from .tools import save_md_file
from ._schemas import FormattedPresentation


# Markdown
# FORMATTER_PROMPT = (
#     "You are a document formatting specialist. You will receive a financial analysis report "
#     "and your sole job is to restructure it for maximum human readability using markdown. "
#     "Apply the following rules:\n"
#     "- Use ## and ### headers to create a clear hierarchy\n"
#     "- Convert prose lists into bullet points or numbered lists\n"
#     "- Present comparative or multi-column data as markdown tables\n"
#     "- Bold key metrics, figures, and named entities on first mention\n"
#     "- Use blockquotes (>) for direct quotes or notable analyst statements\n"
#     "- Add a '## Key Takeaways' section at the top as a 3-5 bullet executive summary\n"
#     "Do not add, remove, or change any factual content — only restructure the presentation.\n"
#     "Once formatting is complete, call save_md_file with the formatted markdown and a descriptive "
#     "file name derived from the report subject (e.g. 'nvidia_q4_2025')."
# )
#
# formatter_agent = Agent(
#     name="Document-Formatter",
#     instructions=FORMATTER_PROMPT,
#     model=DEFAULT_MODEL,
#     output_type=FormattedReport,
#     tools=[save_md_file],
# )


# PPT
FORMATTER_PROMPT = (
    "You are a presentation design specialist. Convert a financial analysis report "
    "into a professional PowerPoint deck.\n"
    "1. Call get_html_guidelines to learn the slide constraints.\n"
    "2. Design 6-10 slides as self-contained 1280×720 px HTML — cover slide, key metrics, "
    "analysis sections, and a summary slide.\n"
    "3. Call check_slides to validate for overflow and fix any violations.\n"
    "4. Call generate_pptx with a descriptive filename derived from the report subject "
    "(e.g. 'nvidia_q4_2025.pptx').\n"
    "Return the saved file path in pptx_path."
)


def build_formatter_agent(mcp_server: MCPServerStreamableHttp) -> Agent:
    return Agent(
        name="Document-Formatter",
        instructions=FORMATTER_PROMPT,
        model=DEFAULT_MODEL,
        output_type=FormattedPresentation,
        mcp_servers=[mcp_server],
    )