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
    """Clean and parse JSON from LLM output, handling common issues like markdown wrappers,
    conversational leading/trailing text, and unescaped newline control characters inside strings.
    """
    raw_text = raw_text.strip()
    
    # 1. Try to extract JSON structure between first '{' and last '}'
    start_idx = raw_text.find('{')
    end_idx = raw_text.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        raw_text = raw_text[start_idx:end_idx + 1]
        
    # 2. Fix unescaped control characters (newlines, tabs) inside JSON string values
    in_string = False
    escape = False
    chars = []
    for char in raw_text:
        if char == '"' and not escape:
            in_string = not in_string
            chars.append(char)
        elif in_string:
            if char == '\n':
                chars.append('\\n')
            elif char == '\r':
                chars.append('\\r')
            elif char == '\t':
                chars.append('\\t')
            else:
                chars.append(char)
        else:
            chars.append(char)
            
        if char == '\\' and not escape:
            escape = True
        else:
            escape = False
            
    clean_text = "".join(chars)
    return json.loads(clean_text)


def extract_entities_from_chunk(chunk_text: str, chunk_meta: dict, retries: int = 2) -> dict:
    """Call LLM to extract entities and relations from a chunk."""
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=4000,
                messages=[{
                    "role": "user",
                    "content": EXTRACTION_PROMPT + chunk_text[:3000]
                }]
            )
            content = response.choices[0].message.content
            if content is None:
                if attempt < retries:
                    time.sleep(1)
                    continue
                print(f"[Extractor] Empty response for {chunk_meta.get('file', '')}")
                return {"entities": [], "relations": [], "source": chunk_meta}
            
            result = clean_and_parse_json(content)
            result["source"] = chunk_meta
            return result
        except (json.JSONDecodeError, Exception) as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"[Extractor] Error for {chunk_meta.get('file', '')} after {attempt + 1} attempts: {e}")
            return {"entities": [], "relations": [], "source": chunk_meta}
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
