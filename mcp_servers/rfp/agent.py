from pdf_extract import get_relevant_texts, extract_pdf
from utils import convert_to_html, ainference
import asyncio
import os
import json


async def get_summary(pdf_path: str):
   
    data = extract_pdf(pdf_path)
    budget_texts, budget_ids = get_relevant_texts(data, filter_name="budget_extractor")
    time_texts, time_ids = get_relevant_texts(data, filter_name="time_extractor")
    mar_points, mar_ids = get_relevant_texts(data, filter_name="mar_summary")
    sfr_points, sfr_ids = get_relevant_texts(data, filter_name="sfr_summary")


    with open("./prompts.json", "r", encoding="utf-8") as f:
        fetch_prompt = json.load(f)

    budget_info, time_info, mar_text, sfr_text = await asyncio.gather(
        ainference(system_msg=fetch_prompt["budget_extractor"], query=budget_texts),
        ainference(system_msg=fetch_prompt["time_extractor"], query=time_texts),
        ainference(model="gpt-4.1", system_msg=fetch_prompt["mar_summary"], query=mar_points),
        ainference(model="gpt-4.1", system_msg=fetch_prompt["sfr_summary"], query=sfr_points),
    )

    return convert_to_html(
        file_name=os.path.basename(pdf_path),
        budget_text=budget_info,
        time_text=time_info,
        mar_text=mar_text,
        sfr_text=sfr_text
    )


if __name__ == "__main__":
    print(asyncio.run(get_summary(pdf_path=r"C:\Users\gukhwan\OneDrive - (주)스위트케이\바탕 화면\ChatRFP\data\2025년 경기관광정보서비스 통합 운영 과업지시서.pdf")))