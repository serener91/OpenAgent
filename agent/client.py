import requests
import json

def generate_text(prompt):
    url = "http://localhost:8000/generate"
    headers = {"Content-Type": "application/json"}
    data = {"prompt": prompt}
    response = requests.post(url, headers=headers, data=json.dumps(data))
    response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
    return response.json()["text"]


if __name__ == "__main__":
    prompt = input("Enter your prompt: ")
    generated_text = generate_text(prompt)
    print(generated_text)
