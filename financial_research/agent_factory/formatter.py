from agents import Agent

from ._config import DEFAULT_MODEL
from ._schemas import FormattedReport
from .tools import save_md_file

FORMATTER_PROMPT = (
    "You are a document formatting specialist. You will receive a financial analysis report "
    "and your sole job is to restructure it for maximum human readability using markdown. "
    "Apply the following rules:\n"
    "- Use ## and ### headers to create a clear hierarchy\n"
    "- Convert prose lists into bullet points or numbered lists\n"
    "- Present comparative or multi-column data as markdown tables\n"
    "- Bold key metrics, figures, and named entities on first mention\n"
    "- Use blockquotes (>) for direct quotes or notable analyst statements\n"
    "- Add a '## Key Takeaways' section at the top as a 3-5 bullet executive summary\n"
    "Do not add, remove, or change any factual content — only restructure the presentation.\n"
    "Once formatting is complete, call save_md_file with the formatted markdown and a descriptive "
    "file name derived from the report subject (e.g. 'nvidia_q4_2025')."
)

formatter_agent = Agent(
    name="Document-Formatter",
    instructions=FORMATTER_PROMPT,
    model=DEFAULT_MODEL,
    output_type=FormattedReport,
    tools=[save_md_file],
)
