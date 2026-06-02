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
  "test_recommendations": ["list of specific test cases to write, including: what to mock, what input to use, what output to assert, and why"]
}}

RULES:
- Be SPECIFIC, not generic. Reference actual parameter names, types, and code patterns.
- If the function interacts with a database, specify exactly what tables/collections and what mock data shape to use.
- If the function calls external APIs, specify what to mock and what response shape to simulate.
- If the function reads environment variables or config, list them explicitly.
- Return ONLY valid JSON, no markdown.
"""


def _enrich_single_function(func: dict, retries: int = 2) -> dict | None:
    """Call LLM to generate test specifications for a single function."""
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

    for attempt in range(retries + 1):
        try:
            response = client_ai.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            if content is None:
                if attempt < retries:
                    time.sleep(1)
                    continue
                return None

            raw = content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
            result["_name"] = func["name"]
            result["_file"] = func["file"]
            return result

        except json.JSONDecodeError:
            if attempt < retries:
                time.sleep(1)
                continue
            return None
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"[Enricher] Error for {func.get('name', '?')}: {e}")
            return None

    return None


def enrich_all_functions(batch_size: int = 8):
    """
    Query all Function nodes from Neo4j that have raw_code (user-defined functions),
    enrich them with LLM-generated test specs, and write back to Neo4j.
    """
    client = get_client()

    # Only enrich functions that have raw_code and file (user-defined, not placeholder nodes)
    result = client.run("""
        MATCH (n:Function)
        WHERE n.file IS NOT NULL AND n.raw_code IS NOT NULL AND size(n.raw_code) > 50
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
                "how_it_works": r.get("how_it_works", ""),
                "input_spec": r.get("input_spec", ""),
                "output_spec": r.get("output_spec", ""),
                "edge_cases": json.dumps(r.get("edge_cases", [])),
                "test_recommendations": json.dumps(r.get("test_recommendations", [])),
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
                "how_it_works": r.get("how_it_works", ""),
                "input_spec": r.get("input_spec", ""),
                "output_spec": r.get("output_spec", ""),
                "edge_cases": json.dumps(r.get("edge_cases", [])),
                "test_recommendations": json.dumps(r.get("test_recommendations", [])),
            })
        except Exception as e:
            print(f"[Enricher] Error writing {r.get('_name', '?')}: {e}")

    print(f"[Enricher] Incremental enrichment complete: {len(results)} functions.")
