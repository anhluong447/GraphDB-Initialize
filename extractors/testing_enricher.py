"""
AI Testing Enricher — Enrich Function nodes in Neo4j with LLM-generated test specs.

This module queries all Function nodes from Neo4j, sends their code + metadata to
the LLM in parallel batches, and writes back rich testing properties:
  - how_it_works: Plain English description of logic and side effects
  - input_spec: Valid ranges, constraints, nullable states for each parameter
  - output_spec: Returned value description and constraints
  - edge_cases: High-risk scenarios, boundaries, error inputs
  - test_recommendations: Step-by-step instructions for mocking, test cases, and mock data
"""

import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import openai
from graph.neo4j_client import get_client
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, LLM_MODEL

client_ai = openai.OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)

ENRICHMENT_PROMPT = """You are an expert software testing engineer. Analyze the following function and produce a comprehensive testing specification.

Function metadata:
- Name: {name}
- File: {file}
- Class: {class_name}
- Visibility: {visibility}
- Async: {is_async}
- Parameters: {inputs}
- Return type: {output}
- Docstring: {docstring}
- Raises: {raises}
- Complexity: {complexity}
- Decorators: {annotations}

Source code:
```
{raw_code}
```

Produce a JSON response with EXACTLY these keys:
{{
  "how_it_works": "2-3 sentence description of what the function does, including side effects (DB writes, API calls, file I/O, etc.)",
  "input_spec": "For each parameter: valid ranges, types, constraints, nullable, edge values. Be specific.",
  "output_spec": "What is returned, under what conditions. Include None/null/error cases.",
  "edge_cases": ["list of specific edge case scenarios that could cause bugs or unexpected behavior"],
  "test_recommendations": [
    {{"type": "mock", "target": "exact.import.path", "reason": "Why this must be mocked"}},
    {{"type": "test_case", "name": "test_name", "path": "happy|error|edge", "description": "What to test and assert"}}
  ]
}}

RULES:
- Be SPECIFIC, not generic. Reference actual parameter names, types, and code patterns.
- If the function interacts with a database, specify exactly what tables/collections and what mock data shape to use.
- If the function calls external APIs, specify what to mock and what response shape to simulate.
- If the function reads environment variables or config, list them explicitly.
- CRITICAL: test_recommendations MUST be a JSON array. Each item MUST have a "type" field: either "mock" or "test_case".
  - If "mock": include "target" (exact import path to mock) and "reason".
  - If "test_case": include "name", "path" (happy/error/edge), and "description".
  - Never return a plain string for test_recommendations.
- Return ONLY valid JSON, no markdown.
"""


def _enrich_single_function(func: dict, retries: int = 4) -> dict | None:
    """Call LLM to generate test specifications for a single function with self-correction retry loop."""
    prompt = ENRICHMENT_PROMPT.format(
        name=func.get("name", ""),
        file=func.get("file", ""),
        class_name=func.get("class_name", "None"),
        visibility=func.get("visibility", "public"),
        is_async=func.get("is_async", False),
        inputs=func.get("inputs", "[]"),
        output=func.get("output", ""),
        docstring=func.get("docstring", ""),
        raises=func.get("raises", "[]"),
        complexity=func.get("complexity", 0),
        annotations=func.get("annotations", "[]"),
        raw_code=func.get("raw_code", "")[:3000],
    )

    messages = [{"role": "user", "content": prompt}]

    for attempt in range(retries):
        try:
            response = client_ai.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=2000,
                messages=messages,
            )
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("Received empty response from LLM")

            raw = content.strip()
            from extractors.llm_extractor import clean_and_parse_json
            result = clean_and_parse_json(raw)

            # Schema validation
            required_keys = ["how_it_works", "input_spec", "output_spec", "edge_cases", "test_recommendations"]
            if not isinstance(result, dict) or not all(k in result for k in required_keys):
                raise ValueError("Parsed JSON is missing required schema keys (how_it_works, input_spec, output_spec, edge_cases, test_recommendations)")

            result["_name"] = func["name"]
            result["_file"] = func["file"]
            return result

        except Exception as e:
            print(f"[Enricher] Attempt {attempt + 1} failed for function {func.get('name', '?')}: {e}")
            if attempt < retries - 1:
                # Append incorrect response and error message for self-correction feedback
                if 'content' in locals() and content:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": f"The previous response is invalid. Error: {e}. Please fix any JSON syntax errors or missing keys and return ONLY valid JSON matching the requested schema."
                    })
                time.sleep(1)
            else:
                print(f"[Enricher] Error for function {func.get('name', '?')} after {retries} attempts. Skipping.")

    return None


def _normalize_property(val) -> str:
    """Ensure value is a primitive string or JSON serialized string to avoid Neo4j errors."""
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return str(val) if val is not None else ""


def _parse_test_recommendations(raw) -> str:
    """
    Normalize test_recommendations to a consistent JSON array string.
    Handles: JSON array, JSON object, plain string, or parse failure.
    Each item should have: type (mock|test_case), and relevant fields.
    """
    if isinstance(raw, list):
        # Already a list, validate items
        normalized = []
        for item in raw:
            if isinstance(item, dict) and "type" in item:
                normalized.append(item)
            elif isinstance(item, str):
                normalized.append({"type": "note", "description": item})
            elif isinstance(item, dict):
                item.setdefault("type", "test_case")
                normalized.append(item)
        return json.dumps(normalized)
    elif isinstance(raw, dict):
        raw.setdefault("type", "test_case")
        return json.dumps([raw])
    elif isinstance(raw, str):
        # Try to parse as JSON using json_repair
        try:
            import json_repair
            parsed = json_repair.loads(raw)
            return _parse_test_recommendations(parsed)
        except Exception:
            if raw.strip():
                return json.dumps([{"type": "note", "description": raw}])
            return "[]"
    return "[]"


def enrich_all_functions(batch_size: int = 8):
    """
    Query all Function nodes from Neo4j that have raw_code (user-defined functions),
    enrich them with LLM-generated test specs, and write back to Neo4j.
    """
    client = get_client()

    # Only enrich functions that have raw_code and file, and haven't been enriched yet (resumable)
    result = client.run("""
        MATCH (n:Function)
        WHERE n.file IS NOT NULL AND n.raw_code IS NOT NULL AND size(n.raw_code) > 50
          AND n.how_it_works IS NULL
        RETURN n.name as name, n.file as file, n.raw_code as raw_code,
               n.visibility as visibility, n.is_async as is_async,
               n.class_name as class_name, n.docstring as docstring,
               n.inputs as inputs, n.output as output,
               n.raises as raises, n.complexity as complexity,
               n.annotations as annotations
    """)

    functions = [dict(r) for r in result]

    if not functions:
        print("[Enricher] No enrichable functions found.")
        return

    print(f"[Enricher] Enriching {len(functions)} functions with AI test specs using {batch_size} workers...")

    lock = threading.Lock()
    counter = 0
    enriched_count = 0

    def worker(func):
        nonlocal counter, enriched_count
        res = _enrich_single_function(func)
        with lock:
            counter += 1
            if counter % 5 == 0 or counter == len(functions):
                print(f"[Enricher] Progress: {counter}/{len(functions)}")
        return res

    results = []
    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        futures = [executor.submit(worker, f) for f in functions]
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception as e:
                print(f"[Enricher] Worker exception: {e}")

    # Write enriched data back to Neo4j
    print(f"[Enricher] Writing {len(results)} enriched specs back to Neo4j...")
    for r in results:
        try:
            client.run("""
                MATCH (n:Function {name: $name, file: $file})
                SET n.how_it_works = $how_it_works,
                    n.input_spec = $input_spec,
                    n.output_spec = $output_spec,
                    n.edge_cases = $edge_cases,
                    n.test_recommendations = $test_recommendations
            """, {
                "name": r["_name"],
                "file": r["_file"],
                "how_it_works": _normalize_property(r.get("how_it_works", "")),
                "input_spec": _normalize_property(r.get("input_spec", "")),
                "output_spec": _normalize_property(r.get("output_spec", "")),
                "edge_cases": json.dumps(r.get("edge_cases", [])),
                "test_recommendations": _parse_test_recommendations(r.get("test_recommendations", [])),
            })
            enriched_count += 1
        except Exception as e:
            print(f"[Enricher] Error writing {r.get('_name', '?')}: {e}")

    print(f"[Enricher] Done. Enriched {enriched_count}/{len(functions)} functions.")


def enrich_functions_for_files(file_paths: list[str], batch_size: int = 4):
    """
    Incremental enrichment: only enrich functions belonging to specific files.
    Used by the watcher for fast incremental updates.
    """
    client = get_client()

    result = client.run("""
        MATCH (n:Function)
        WHERE n.file IN $files AND n.raw_code IS NOT NULL AND size(n.raw_code) > 50
        RETURN n.name as name, n.file as file, n.raw_code as raw_code,
               n.visibility as visibility, n.is_async as is_async,
               n.class_name as class_name, n.docstring as docstring,
               n.inputs as inputs, n.output as output,
               n.raises as raises, n.complexity as complexity,
               n.annotations as annotations
    """, {"files": file_paths})

    functions = [dict(r) for r in result]

    if not functions:
        return

    print(f"[Enricher] Incrementally enriching {len(functions)} functions...")

    results = []
    for func in functions:
        res = _enrich_single_function(func)
        if res:
            results.append(res)

    for r in results:
        try:
            client.run("""
                MATCH (n:Function {name: $name, file: $file})
                SET n.how_it_works = $how_it_works,
                    n.input_spec = $input_spec,
                    n.output_spec = $output_spec,
                    n.edge_cases = $edge_cases,
                    n.test_recommendations = $test_recommendations
            """, {
                "name": r["_name"],
                "file": r["_file"],
                "how_it_works": _normalize_property(r.get("how_it_works", "")),
                "input_spec": _normalize_property(r.get("input_spec", "")),
                "output_spec": _normalize_property(r.get("output_spec", "")),
                "edge_cases": json.dumps(r.get("edge_cases", [])),
                "test_recommendations": _parse_test_recommendations(r.get("test_recommendations", [])),
            })
        except Exception as e:
            print(f"[Enricher] Error writing {r.get('_name', '?')}: {e}")

    print(f"[Enricher] Incremental enrichment complete: {len(results)} functions.")
