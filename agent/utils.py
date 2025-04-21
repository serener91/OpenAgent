from langfuse import Langfuse
from langfuse.openai import OpenAI, AsyncOpenAI
# from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv
import os
import asyncio
from litellm import acompletion


load_dotenv()


async def llm_router(system_msg, user_msg):
    messages = [
        {
            "role": "system",
            "content": system_msg,
        },
        {
            "role": "user",
            "content": user_msg
        },
    ]

    # openai call
    response = await acompletion(model="openai/gpt-4o-mini", messages=messages, stream=True)
    async for part in response:
        print(part.choices[0].delta.content or "", end="")


async def inference(system_msg=" ", user_msg=" ", stream=True, use_gpt=False):
    """
    Call OpenAI-compatiable server
    """
    client = AsyncOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", None) if use_gpt else "test123",
        base_url=None if use_gpt else "http://175.196.78.7:30000/v1"
    )

    if system_msg == "":
        system_msg = " "

    message = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg}
    ]

    chat_response = await client.chat.completions.create(
        model="gpt-4o-mini" if use_gpt else "vllm",
        messages=message,
        temperature=0.75,
        # top_p=0.8,
        # frequency_penalty=1.05,
        # presence_penalty=1.05,
        max_completion_tokens=512,
        stream=stream
    )

    if stream:
        async for chunk in chat_response:
            if chunk:
                text = chunk.choices[0].delta.content
                if text is not None:
                    print(text, end="")

    else:
        response = chat_response.choices[0].message.content
        print(response)


def get_client():
    langfuse_client = Langfuse(
        host="http://localhost:10030"
    )

    return langfuse_client


def upload_prompt(prompt_id: str, prompt_text: str, prompt_config: dict = None, commit_msg: str = None):
    langfuse = get_client()
    langfuse.create_prompt(
        name=prompt_id,
        prompt=prompt_text,
        config=prompt_config,
        commit_message=commit_msg
    )
    print(f"Prompt Uploaded: {prompt_id}")


def fetch_prompt(prompt_id: str, label: str = "latest", version: int = None):
    """

    dev only

    """
    langfuse = get_client()
    if version is None:
        return langfuse.get_prompt(prompt_id, label=label).compile()

    else:
        return langfuse.get_prompt(prompt_id, version=version).compile()


if __name__ == '__main__':
    # asyncio.run(
    #     inference(
    #         use_gpt=True, system_msg="Follow user's instruction and respond in Korean.", user_msg="Explain what sugar crash is"
    #     )
    # )

    asyncio.run(
        llm_router(
            system_msg="Follow user's instruction and respond in Korean.", user_msg="Explain what sugar crash is"
        )
    )

    # upload_prompt(
    #     prompt_id="RAG",
    #     prompt_text="""You are an AI that answers questions using only the provided text chunks. Follow these rules:
    #     1.	Carefully analyze both the question and the provided text chunks.
    #     2.	Generate a well-structured, coherent answer strictly based on the provided text—do not use external knowledge.
    #     3.	Ensure the response is informative and sufficiently detailed, avoiding overly short or vague answers.
    #     4.	If multiple text chunks are provided, cite the sources by embedding the provided links in superscript format.
    #     •	Each source has a unique identifier and a corresponding link (e.g., source_link: https://example.com).
    #     •	Use the link in HTML format like this: text... <sup><a href="https://example.com">1</a></sup>.
    #     •	If multiple sources contribute to the same part, list them together: text... <sup><a href="https://source1.com">1</a>, <a href="https://source2.com">2</a></sup>.
    #     5.	Output only the answer with properly formatted citations—do not include any extra words or explanations.
    #     """,
    #     commit_msg="baseline"
    # )
