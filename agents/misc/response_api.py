from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


"""
https://platform.openai.com/docs/api-reference/responses/create
"""

client = OpenAI()

response = client.responses.create(
    model="gpt-4.1",
    tools=[{"type": "web_search_preview"}],
    input="오늘 주요 뉴스는 무엇이 있었어?",
)

print(response)