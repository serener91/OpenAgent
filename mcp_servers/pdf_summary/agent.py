"""
PDF Summary Agent

This agent parses one or more PDF files, extracts text, generates a summary and key points using LLM (i.e. gpt-4o-mini),
and outputs the result as HTML-compatible text.

"""

import os
from typing import Any, Dict, List, Union

try:
    import json
    import pdfplumber
    from dotenv import load_dotenv
    from openai import AsyncOpenAI, OpenAI
    from PyPDF2 import PdfReader

except ImportError:
    raise ImportError("Packages are not installed. Run pip install -r requirements.txt first!")


load_dotenv(r"C:\Users\gukhwan\OneDrive - (주)스위트케이\바탕 화면\OpenAgent\.env")


def summarize_text(text: str) -> Dict[str, Union[str, List[str]]]:
    """
    Summarize the given text and extract key points using OpenAI API.

    Args:
        text: extracted texts from pdf

    Returns:
        model generated output

    """

    api_key = os.getenv("OPENAI_API_KEY", None)
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable not set.")
    client = OpenAI(api_key=api_key)

    system_msg = """You are an intelligent summarization assistant. Your task is to help users understand the content of a PDF document by providing a concise and informative summary, along with a list of key points to focus on.

You will be given raw text extracted from a PDF. Based on this text, perform the following tasks:

1. **Summary**:  
   Write a clear and concise summary of the document. The goal of this summary is to serve as an introductory guide, helping the user understand the purpose, scope, and major themes of the document before they read it in detail. Avoid unnecessary repetition or overly technical details unless essential to understanding.

2. **Key Points**:  
   Identify the most important takeaways, insights, or sections that the user should pay special attention to. These should help the user know what to focus on when reading the full document.

Output the result as a JSON object with the following structure:
{
  "summary": "A clear and concise introduction to the document.",
  "keypoints": [
    "First major point or section to focus on.",
    "Second key takeaway or insight.",
    "...more key points..."
  ]
}


Do not include any additional commentary or explanations. Your response must be strictly in JSON format.
    """

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Text:\n {text}"},
        ],
        temperature=0.2,
    )

    return summary_parser(model_response=response.choices[0].message.content)


def summary_parser(model_response: str) -> Dict[str, Union[str, List[str]]]:
    """
    Parse the JSON-formatted string from LLM into JSON

    Args:
        model_response: JSON-formatted string from LLM

    Returns:
        python dict with keys: summary and keypoints
    """

    try:
        result = json.loads(model_response, strict=False)
        summary = result.get("summary", "")
        keypoints = result.get("keypoints", [])
        if not isinstance(keypoints, list):
            keypoints = [str(keypoints)]
        return {"summary": summary, "keypoints": keypoints}

    except json.decoder.JSONDecodeError as e:
        print(f"{e}")

    except Exception:
        # Fallback: treat the whole response as summary, no keypoints
        return {"summary": model_response, "keypoints": []}


# def extract_text_from_pdf(pdf_path: str) -> str:
#     """
#     Extract all text from a PDF file using pdfplumber.
#
#     Args:
#         pdf_path: Path to the PDF file.
#
#     Returns:
#         Extracted text as a single string.
#     """
#
#     text = ""
#     with pdfplumber.open(pdf_path) as pdf:
#         for page in pdf.pages:
#             text += page.extract_text() or ""
#             text += "\n"
#     return text


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract all text from a PDF file using PyPDF2.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Extracted text as a single string.
    """

    reader = PdfReader(pdf_path)
    texts = []
    for page_number, page in enumerate(reader.pages, start=1):
        texts.append(page.extract_text())

    return "\n\n".join(texts)


def format_summary_html(summary: str, keypoints: List[str], filename: str = "") -> str:
    """
    Format the summary and key points as HTML.

    Args:
        summary: The summary text.
        keypoints: List of key points.
        filename: Optional filename for display.

    Returns:
        HTML string.
    """
    html = ""
    if filename:
        html += f"<h2>{filename}</h2>\n"
    html += "<h3>Summary</h3>\n"
    html += f"<p>{summary}</p>\n"
    html += "<h3>Key Points</h3>\n<ul>\n"
    for point in keypoints:
        html += f"  <li>{point}</li>\n"
    html += "</ul>\n"
    return html


def summarize_pdfs(pdf_paths: List[str]) -> str:
    """
    Process one or more PDF files, extract text, summarize, and format as HTML.

    Args:
        pdf_paths: List of PDF file paths.

    Returns:
        Combined HTML summary for all PDFs.
    """
    html_results = []
    for pdf_path in pdf_paths:
        filename = os.path.basename(pdf_path)
        text = extract_text_from_pdf(pdf_path)
        summary_data = summarize_text(text)
        html = format_summary_html(
            summary_data["summary"], summary_data["keypoints"], filename
        )
        html_results.append(html)
    return "\n<hr/>\n".join(html_results)