import json
import time
import openai
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, LLM_MODEL

client = openai.OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
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


def clean_and_parse_json(raw_text: str) -> dict:
    """Clean and parse JSON from LLM output using json_repair to handle malformed JSON syntax."""
    import json_repair
    raw_text = raw_text.strip()

    try:
        # Try direct repair and load
        return json_repair.loads(raw_text)
    except Exception:
        pass

    # Extract content between first '{' and last '}'
    start_idx = raw_text.find('{')
    end_idx = raw_text.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        cropped = raw_text[start_idx:end_idx + 1]
        try:
            return json_repair.loads(cropped)
        except Exception:
            pass

    # Final fallback: strip markdown blocks and try to parse
    clean_text = raw_text.replace("```json", "").replace("```", "").strip()
    return json_repair.loads(clean_text)


def extract_entities_from_chunk(chunk_text: str, chunk_meta: dict, retries: int = 4) -> dict:
    """Call LLM to extract entities and relations from a chunk with a self-correction retry loop."""
    messages = [
        {"role": "user", "content": EXTRACTION_PROMPT + chunk_text[:3000]}
    ]

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=4000,
                messages=messages
            )
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("Received empty response from LLM")

            result = clean_and_parse_json(content)
            if not isinstance(result, dict) or "entities" not in result:
                raise ValueError("Parsed JSON does not match expected schema (missing entities/relations)")

            result["source"] = chunk_meta
            return result
        except Exception as e:
            print(f"[Extractor] Attempt {attempt + 1} failed for {chunk_meta.get('file', '')}: {e}")
            if attempt < retries - 1:
                # Append incorrect response and error message for self-correction feedback
                if 'content' in locals() and content:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": f"The previous response is invalid. Error: {e}. Please fix any JSON syntax errors (such as unescaped quotes or missing commas) and return ONLY valid JSON."
                    })
                time.sleep(1)
            else:
                print(f"[Extractor] Error for {chunk_meta.get('file', '')} after {retries} attempts. Skipping chunk.")

    return {"entities": [], "relations": [], "source": chunk_meta}


def extract_from_commit(commit: dict) -> dict:
    """Extract semantic info from a git commit message."""
    prompt = f"""Analyze this git commit and extract:
- Any tasks completed (type: Task, past tense)
- Any bugs fixed (type: Risk that was resolved)
- Any decisions made (type: Decision)

Commit: {commit['message']}
Files changed: {', '.join(commit['files_changed'][:10])}

Return ONLY valid JSON:
{{"entities": [...], "relations": [...]}}"""

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        if content is None:
            return {"entities": [], "relations": []}
        return clean_and_parse_json(content)
    except Exception:
        return {"entities": [], "relations": []}


from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def batch_extract(chunks: list[dict], batch_size: int = 10) -> list[dict]:
    """Extract entities from list of chunks in parallel with progress logging."""
    results = []
    lock = threading.Lock()
    counter = 0
    total = len(chunks)

    # Filter out empty or extremely small chunks first to avoid wasting threads
    valid_chunks = []
    for chunk in chunks:
        text = chunk.get("content") or chunk.get("raw_code", "")
        if len(text.strip()) >= 100:
            valid_chunks.append((text, chunk))

    total_valid = len(valid_chunks)
    print(f"[Extractor] Starting parallel extraction of {total_valid} valid chunks using {batch_size} workers...")

    def worker(text, chunk):
        nonlocal counter
        res = extract_entities_from_chunk(text, chunk)
        with lock:
            counter += 1
            if counter % 5 == 0 or counter == total_valid:
                print(f"[Extractor] Progress: {counter}/{total_valid} chunks extracted...")
        return res

    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        futures = [executor.submit(worker, text, chunk) for text, chunk in valid_chunks]
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception as e:
                print(f"[Extractor] Worker exception: {e}")

    print(f"[Extractor] Finished parallel extraction: {len(results)} results.")
    return results
