from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv
import os


load_dotenv()

async def ainference(system_msg="", query="", model="gpt-4o-mini", temperature=0.2):
    
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY", None),
    )

    message = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": query}
    ]

    # Await the response
    chat_response = await client.chat.completions.create(
        model=model,
        messages=message,
        temperature=temperature,
        max_completion_tokens=8192,
        stream=False
    )

    return chat_response.choices[0].message.content


def convert_to_html(filepath="./sample.html", file_name=None, budget_text=None, time_text=None, mar_text=None, sfr_text=None):

    """
    Convert final output as formatted html

    """

    text_style = """
    <style>
            body {
                font-family: sans-serif;
                line-height: 1.6;
                margin: 20px;
            }
            h2 {
                color: #333;
                border-bottom: 2px solid #eee;
                padding-bottom: 10px;
            }
            ul {
                list-style-type: disc;
                margin-left: 20px;
            }
            li {
                margin-bottom: 8px;
            }
            .summary {
                background-color: #f9f9f9;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }
        </style>
    """

    html_text = f"""
            <!DOCTYPE html>
            <html lang="ko">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                {text_style}
            </head>
            <body>

                <h2>RFP Summary</h2>

                <div class="summary">
                    <p>문서명: {file_name}</p>
                    <p>{budget_text}</p>
                    <p>{time_text}</p>
                </div>

                <h2>MAR 핵심 사항</h2>

                <ul>
                    {mar_text}
                </ul>

                <h2>SFR 핵심 사항</h2>

                <ul>
                    {sfr_text}
                </ul>

            </body>
            </html>
            """

    # with open(filepath, "w", encoding="utf-8") as f:
    #     f.write(html_text)

    print("HTML converted!")

    return html_text


