import openai
import os
from dotenv import load_dotenv

load_dotenv()

client = openai.OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

print("Testing OpenRouter with deepseek/deepseek-v4-flash...")
try:
    response = client.chat.completions.create(
        model="deepseek/deepseek-v4-flash",
        messages=[{"role": "user", "content": "Say hello"}],
        max_tokens=10
    )
    print("Response:", response.choices[0].message.content)
except Exception as e:
    print("Error:", e)
