import openai
import os
import json
from dotenv import load_dotenv

load_dotenv()

client = openai.OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

EXTRACTION_PROMPT = """You are a code knowledge graph builder.

Given the following code/documentation chunk, extract:
1. High-level entities (NOT the functions themselves, those are already captured).
   Entity types: Feature, Concept, Decision, Risk, Task, Module
2. Relations between entities AND between entities and code elements.

RULES:
- Entity names must be concise (2-5 words max)
- Be consistent with naming across chunks (use canonical names)
- Only extract entities that are genuinely meaningful, not every variable
- Tasks must be actionable (e.g. "Implement refresh token", "Fix null check in payment")
- Risks must be concrete (e.g. "No rate limiting on auth endpoint")

Return ONLY valid JSON in this exact format:
{
  "entities": [
    {"name": "string", "type": "Feature|Concept|Decision|Risk|Task|Module", "description": "string (max 100 chars)"}
  ],
  "relations": [
    {"from": "string", "relation": "implements|depends_on|relates_to|conflicts_with|blocks|owned_by|introduces", "to": "string"}
  ]
}

Chunk to analyze:
"""

with open("D:/GraphRAG/demo_project/A20-App-083/backend/create_admin.py", "r", encoding="utf-8") as f:
    code = f.read()

try:
    response = client.chat.completions.create(
        model="google/gemini-2.5-flash",
        messages=[{"role": "user", "content": EXTRACTION_PROMPT + code}],
        max_tokens=4000
    )
    print("Content:")
    print(response.choices[0].message.content)
except Exception as e:
    print("Error:", e)
