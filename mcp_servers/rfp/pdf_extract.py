import json
from PyPDF2 import PdfReader
from tqdm import tqdm
import re


def extract_pdf(pdf_path: str):
    """

    Read PDF file and returns
        source: str: Given path to PDF
        total_pages: int: Total number of pages of PDF
        metadata: dict: metdata recored in PDF such as Author, Creator, CreationDate, ModDate, etc...
        page_numbers: List[int]: Page number starting from 1
        texts: List[str]: Text from each page
    """

    reader = PdfReader(pdf_path)

    page_numbers = []
    texts = []
    for page_number, page in tqdm(enumerate(reader.pages, start=1), desc="extracting pages..."):
        page_numbers.append(page_number)
        texts.append(page.extract_text())

    return {
        "source": pdf_path,
        "total_pages": len(reader.pages),
        "metadata": reader.metadata,  # Extract document metadata (Returns a dictionary)
        "page_numbers": page_numbers,
        "texts": texts
    }


def get_relevant_texts(pdf_data: dict, filter_name: str):

    """
    data : Return of extract_pdf()
    filter_name: mar_summary, sfr_summary, budget_extractor, time_extractor

    returns filtered information based on filter words
        relevant page: list[int]
        texts: str
    """

    # Get list of words used for filter
    with open("./document_filter.json", "r", encoding="utf-8") as f:
        words_to_filter = json.load(f)[filter_name]

    # Remove --page-- from extracted texts & Pair up page number and text
    json_text = [
        json.dumps({
            # "Source": os.path.basename(metadata_info["source"]),
            "Page": pdf_data["page_numbers"][i],
            "Content": re.sub(r'-\s*\d+\s*-', '', pdf_data["texts"][i])
        }, ensure_ascii=False)
        for i in range(pdf_data["total_pages"])
    ]

    # Convert dict of list[str] to Python list
    page_records = json.loads(json.dumps(json_text, ensure_ascii=False), strict=False)

    # Loops through pages
    selected_page = []
    selected_text = ""
    for page_record in page_records:
        record_data = json.loads(page_record)

        # Pick pages and page numbers if they contain filter words and format text
        if any(word in record_data["Content"] for word in words_to_filter):
            selected_text += f"###{json.dumps(record_data, ensure_ascii=False)}, "
            selected_page.append(record_data["Page"])

    return selected_text, selected_page


if __name__ == '__main__':
    src_data = r"C:\Users\gukhwan\OneDrive - (주)스위트케이\바탕 화면\ChatRFP\data\2. 제안요청서_다누림홈페이지.pdf"
    data_info = extract_pdf(src_data)
    print(data_info)
    text_info = get_relevant_texts(data_info, filter_name="time_extractor")
    print(text_info)



