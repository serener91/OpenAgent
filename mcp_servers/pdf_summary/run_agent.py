"""
CLI entry point for PDF Summary Agent.

"""

import os
import sys

# Ensure the agent module is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import summarize_pdfs


def main():
    # Example usage (for CLI or testing)
    """
    sys.argv in Python is a list that stores command-line arguments passed to a Python script
    The first element of the list, sys.argv[0], is always the name of the script itself. Subsequent elements, sys.argv[1], sys.argv[2], and so on

    If a Python script named my_script.py is executed with the command python my_script.py arg1 arg2 arg3, then inside the script:
    sys.argv[0] would be "my_script.py"
    sys.argv[1] would be "arg1"
    """

    if len(sys.argv) < 2:
        print("Usage: python run_agent.py <pdf1>, <pdf2> ...")
        exit(1)
    pdf_files = sys.argv[1:]
    html_output = summarize_pdfs(pdf_files)
    print(html_output)


if __name__ == "__main__":
    main()
