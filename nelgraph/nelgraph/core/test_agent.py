"""
Autonomous TestAgent — Dual-model AI test generation engine.

Commander (DeepSeek-R1): Analyzes the knowledge graph, plans test strategy,
    diagnoses failures during self-healing.
Worker (Qwen3 Coder Next): Generates test code from the Commander's plan,
    fixes test code based on Commander's diagnosis.

Usage:
    from nelgraph.core.test_agent import TestAgent
    agent = TestAgent(target="login", mode="unit")
    report = agent.run()
"""

import os
import sys
import json
import time
import hashlib
import subprocess
import threading
from typing import Optional

import openai

# ─── Lazy config import (allows configure() to work) ───────────────────────
def _cfg():
    import nelgraph.config as c
    return c


# ─── OpenRouter client singletons ──────────────────────────────────────────
_commander_client = None
_planner_client = None
_worker_client = None


def _get_commander():
    global _commander_client
    if _commander_client is None:
        cfg = _cfg()
        _commander_client = openai.OpenAI(
            api_key=cfg.OPENROUTER_API_KEY,
            base_url=cfg.OPENROUTER_BASE_URL,
        )
    return _commander_client


def _get_planner():
    global _planner_client
    if _planner_client is None:
        cfg = _cfg()
        _planner_client = openai.OpenAI(
            api_key=cfg.OPENROUTER_API_KEY,
            base_url=cfg.OPENROUTER_BASE_URL,
        )
    return _planner_client


def _get_worker():
    global _worker_client
    if _worker_client is None:
        cfg = _cfg()
        _worker_client = openai.OpenAI(
            api_key=cfg.OPENROUTER_API_KEY,
            base_url=cfg.OPENROUTER_BASE_URL,
        )
    return _worker_client


def _call_llm_with_retry(client_fn, role: str = None, messages: list = None, max_tokens=None, timeout=None, model=None, **kwargs):
    """Executes chat.completions.create with fallback models and retry on errors."""
    import time
    cfg = _cfg()

    # If role is not explicitly provided, infer it from client_fn or model
    if not role:
        fn_name = getattr(client_fn, "__name__", "")
        if "commander" in fn_name or model == cfg.COMMANDER_MODEL:
            role = "commander"
        elif "planner" in fn_name or model == cfg.PLANNER_MODEL:
            role = "planner"
        else:
            role = "worker"

    # Determine primary model and fallback models for this role
    if role == "commander":
        primary = cfg.COMMANDER_MODEL
        fallbacks = getattr(cfg, "COMMANDER_FALLBACKS", ["meta-llama/llama-3.3-70b-instruct", "google/gemini-2.5-pro"])
    elif role == "planner":
        primary = cfg.PLANNER_MODEL
        fallbacks = getattr(cfg, "PLANNER_FALLBACKS", ["google/gemini-2.5-flash", "deepseek/deepseek-chat", "meta-llama/llama-3.3-70b-instruct"])
    else:
        primary = cfg.WORKER_MODEL
        fallbacks = getattr(cfg, "WORKER_FALLBACKS", ["meta-llama/llama-3.3-70b-instruct", "google/gemini-2.5-flash", "deepseek/deepseek-chat"])

    # If the user passed a specific model, make sure it is the primary model in our list
    if model and model != primary:
        primary = model

    # Combine primary and fallbacks to create a candidate models list
    candidate_models = [primary] + [f for f in fallbacks if f != primary]

    last_error = None
    for candidate in candidate_models:
        # Try up to 2 times for each model
        max_attempts = 2
        delay = 2.0
        for attempt in range(1, max_attempts + 1):
            try:
                client = client_fn()
                # OpenRouter extra_body fallback list
                rem_fallbacks = [m for m in candidate_models if m != candidate]
                extra_body = kwargs.get("extra_body") or {}
                if rem_fallbacks and "models" not in extra_body:
                    extra_body = {**extra_body, "models": rem_fallbacks}

                call_kwargs = {
                    "model": candidate,
                    "messages": messages,
                    "extra_body": extra_body,
                    **{k: v for k, v in kwargs.items() if k not in ("extra_body", "model")}
                }
                if max_tokens is not None:
                    call_kwargs["max_tokens"] = max_tokens
                if timeout is not None:
                    call_kwargs["timeout"] = timeout

                response = client.chat.completions.create(**call_kwargs)

                # Validate response choice to capture OpenRouter-level finish_reason errors
                if response.choices:
                    choice = response.choices[0]
                    finish_reason = getattr(choice, "finish_reason", None)
                    if finish_reason in ("error", "length"):
                        err_info = getattr(choice, "error", None) or f"finish_reason is '{finish_reason}' (truncated)"
                        raise ValueError(f"OpenRouter response truncated or errored: {err_info}")
                
                return response

            except Exception as e:
                last_error = e
                # Print to logs so user/developer sees the fallback triggering
                print(f"[LLM Retry] Model {candidate} (attempt {attempt}/{max_attempts}) failed: {e}")
                if attempt < max_attempts:
                    print(f"[LLM Retry] Retrying {candidate} in {delay}s...")
                    time.sleep(delay)
                    delay *= 2
        
        print(f"[LLM Retry] Model {candidate} failed all attempts. Trying next fallback model...")

    print(f"[LLM Retry] All candidate models failed. Propagating final error: {last_error}")
    raise last_error


# ─── Hash helpers ───────────────────────────────────────────────────────────
def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_registry() -> dict:
    cfg = _cfg()
    if os.path.exists(cfg.TEST_REGISTRY_PATH):
        with open(cfg.TEST_REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"functions": {}}


def _save_registry(registry: dict):
    cfg = _cfg()
    os.makedirs(os.path.dirname(cfg.TEST_REGISTRY_PATH), exist_ok=True)
    with open(cfg.TEST_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


# ─── Prompts ────────────────────────────────────────────────────────────────
COMMANDER_PLANNER_PROMPT = """You are an expert QA architect. You have access to a codebase knowledge graph.
Your task is to create a detailed test strategy for the target function(s).

## Target Information
{context_block}

## Task
Analyze the function(s), their dependencies (callees), and callers (blast radius).
Produce a JSON test plan with EXACTLY this structure:
{{
  "strategy_summary": "Brief description of the testing approach",
  "test_files": [
    {{
      "file_path": "tests/test_<module>.py",
      "test_type": "unit|integration|system",
      "target_functions": ["function_name"],
      "mocks": [
        {{"target": "module.path.to.mock", "reason": "Why this must be mocked", "mock_value": "suggested return value"}}
      ],
      "test_cases": [
        {{"name": "test_case_name", "category": "happy|error|edge", "description": "What to test and assert", "inputs": "example inputs", "expected": "expected outcome"}}
      ]
    }}
  ]
}}

RULES:
- Be SPECIFIC: reference actual function names, parameter names, types from the context.
- For unit tests: mock ALL callees (internal functions this function calls) and external deps.
- For integration tests: only mock external deps (DB, HTTP, filesystem). Let internal calls run.
- For system tests: only mock the outermost I/O boundary.
- Include at least 1 happy path, 1 error path, and 1 edge case per function.
- Return ONLY valid JSON, no markdown fences.
"""

FUNCTION_PLANNER_PROMPT = """You are an expert QA planner. Your task is to create a detailed,
executable test plan for a single function, based on its source code and graph context.

## Function Context
{context_block}
{group_hint}

## Error Feedback (if this is a re-plan after a test failure)
{error_feedback}

## Task
Produce a JSON test plan with EXACTLY this structure:
{{
  "strategy_summary": "Brief description of approach",
  "test_files": [
    {{
      "file_path": "tests/test_<module>.py",
      "test_type": "unit|integration|system",
      "target_functions": ["function_name"],
      "mocks": [
        {{"target": "exact.import.path.to.mock", "reason": "why mock", "mock_value": "return value"}}
      ],
      "test_cases": [
        {{
          "name": "test_case_name",
          "category": "happy|error|edge",
          "description": "Exactly what to test",
          "inputs": "concrete example inputs with real values",
          "expected": "concrete expected output or exception"
        }}
      ]
    }}
  ]
}}

RULES:
- file_path MUST be in the format "tests/test_<module>.py" (where <module> is the name of the source module, e.g. "tests/test_middleware.py"). Do NOT generate or overwrite "tests/conftest.py" or other configuration files.
- mock.target must be the EXACT import path as used in the source code (e.g. "myapp.db.session.get")
- inputs and expected must be CONCRETE values, not "auto-generate"
- CRITICAL FOR EXCEPTION PROPAGATION: Trace the control flow of the source code carefully. If an exception can be raised in a statement that is not enclosed in a try-except block, then that exception is expected to propagate to the caller. Do not assume the function catches it. Update your plan's expected assertions to expect the exception to be raised.
- AVOID UNREALISTIC TEST CASES: Do not plan test cases that hit system or language limits (such as creating hundreds of recursive middleware layers causing RecursionError, or mocking hundreds of objects). Keep unit test cases simple, realistic (e.g., list sizes under 10), and focused on the target function's design.
- CHECK CODEBASE BEHAVIOR VS EXPECTATIONS: Verify if your test expectations align with the codebase's actual implementation. If the codebase has a certain behavior (e.g., it does not clear pre-existing errors in a context), assert that exact behavior instead of assuming it behaves differently.
- If there is error_feedback, adjust the strategy — do not repeat the failed approach.
- Return ONLY valid JSON, no markdown fences.
"""

HEAL_PLANNER_PROMPT = """You are an expert QA planner reviewing a failed test.
A Worker generated test code based on your previous plan, but it failed.
Your job is to analyze the failure and produce a REVISED test plan.

## Original Source Code (from file: {source_file_path})
{source_code}

## Previous Test Plan
{previous_plan}

## Failed Test Code
{test_code}

## Error Output
{error_output}

## Task
Diagnose WHY the test failed (wrong mock path, wrong assertion, import error, real bug, etc.)
Then produce a REVISED plan in the same JSON structure as before.

If diagnosis is "real_bug" — set "real_bug": true at top level and explain in strategy_summary.
Otherwise — fix the plan so Worker can write correct test code.

RULES:
- file_path MUST be in the format "tests/test_<module>.py" (where <module> is the name of the source module, e.g. "tests/test_middleware.py"). Do NOT generate or overwrite "tests/conftest.py" or other configuration files.
- CRITICAL FOR EXCEPTION PROPAGATION: Trace the traceback of the failure carefully. If the error output shows an unhandled exception propagating from a line in the target function, look at the target function's source code. If that line does not have a try-except block enclosing it, then the exception is expected to propagate to the caller. Do not assume the function catches it. Update your plan's expected assertions to expect the exception to be raised.
- AVOID UNREALISTIC TEST CASES: Do not plan test cases that hit system or language limits (such as creating hundreds of recursive middleware layers causing RecursionError, or mocking hundreds of objects). Keep unit test cases simple, realistic (e.g., list sizes under 10), and focused on the target function's design.
- CHECK CODEBASE BEHAVIOR VS EXPECTATIONS: Before concluding that a failure indicates a "real_bug" in the codebase, verify if the failure is simply due to a mismatch between your test plan's assumptions/expectations and the codebase's actual implementation. If so, adjust the test plan's assertions to match the codebase behavior (e.g., if the codebase does not clear pre-existing errors in a context, expect them to persist). Only flag "real_bug": true if the codebase violates its own design or contract.
- Return ONLY valid JSON, no markdown fences.
"""

GENERATOR_PROMPT = """You are an expert test code writer. Write complete, runnable test code based on this plan.

## Test Plan
{plan_json}

## Source Code of Target Function(s) (from file: {source_file_path})
{source_code}

## Testing Framework: {framework}

## Previous Test Run Error (if this is a re-generation after a test failure)
{previous_error}

RULES:
- Write a COMPLETE, RUNNABLE test file. Include all imports.
- Use {framework} syntax and conventions.
- Follow the mock strategy EXACTLY as specified in the plan.
- Each test case from the plan must become a real test function.
- Use descriptive test names matching the plan's test case names.
- Include proper setup/teardown if needed.
- Return ONLY the Python/JS code, no markdown fences, no explanations.
- CRITICAL FOR IMPORTS: The file path of the source code is {source_file_path}. Make sure to import the target classes/functions using the correct module path relative to the repository root (e.g., if the file is src/core/middleware.py, import from src.core.middleware, NOT from source).
- CRITICAL FOR ASYNC MOCKS: When mocking an async method/function that accepts an async callback (like next_call), do NOT use a synchronous lambda as the side_effect or return value. Instead, define an `async def` helper function that properly awaits the callback (e.g., `async def mock_side_effect(ctx, next_call): return await next_call(ctx)`) and assign it to the mock's `side_effect`.
- CRITICAL FOR SYNC VS ASYNC MOCKING: Carefully check how parameters/callables are called in the target function. If a callable parameter (such as a callback like core_eval) is called synchronously (e.g., `core_eval(ctx)` without `await`), you MUST mock it as a regular Mock (or MagicMock/function/lambda), NOT an AsyncMock. Mocking a synchronous callable as AsyncMock will return an unawaited coroutine, causing tests to fail.
- CRITICAL FOR CLASS INSTANTIATION: Avoid monkey patching attributes (using unittest.mock.patch or assigning directly) on class objects. Instead, analyze the class's constructor/initializer (__init__ method) parameters and instantiate the class with the desired dependencies/mock values passed directly to the constructor.
- CRITICAL FOR EXCEPTION TESTING: Analyze the exception handling logic of the source code. If a function lets exceptions propagate without catching them, use appropriate test assertions (e.g., pytest.raises for Python, or expect().toThrow() for JS) to verify the exceptions, rather than asserting that the return value has the error.
- CRITICAL FOR MOCK ASSERTIONS: Python's unittest.mock.Mock does NOT support 'assert_called_before' or 'assert_called_after'. To verify call order, either use a parent Mock/MagicMock and check parent.mock_calls, or check timestamps/call lists, or avoid asserting call order if simple invocation asserts are sufficient.
- CRITICAL: If previous_error is not "None", you must analyze and fix that specific error, and avoid repeating the failed approach.
"""



# ─── TestAgent ──────────────────────────────────────────────────────────────
class TestAgent:
    """Autonomous dual-model test generation agent."""

    def __init__(self, target: str, mode: str = "unit", file: str = None, class_name: str = None, injected_plan: dict = None, group_context: dict = None):
        """
        Args:
            target: Function name or community name to test.
            mode: "unit" | "integration" | "system"
            file: Optional file path for disambiguation.
            class_name: Optional class name for disambiguation.
            injected_plan: Pre-computed plan to bypass Commander planning step.
            group_context: Optional group-level context.
        """
        self.target = target
        self.mode = mode
        self.file = file
        self.class_name = class_name
        self.injected_plan = injected_plan
        self.group_context = group_context
        self.plan = None
        self.generated_files = []
        self.test_results = []
        self.heal_history = []
        self.bugs_found = []
        self._log = []


    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._log.append(entry)
        print(f"[TestAgent] {entry}")

    # ─── MAIN ENTRY POINT ──────────────────────────────────────────────
    def run(self) -> dict:
        """Execute the full autonomous pipeline. Returns a structured report."""
        self.log(f"Starting autonomous test generation: target='{self.target}', mode='{self.mode}'")

        try:
            # Step 1: Gather context from the knowledge graph
            context = self._gather_context()
            if not context:
                return self._error_report("Could not find target in the knowledge graph.")

            # Step 2: Commander plans strategy (or use injected plan)
            if self.injected_plan:
                self.log("Using injected test plan...")
                self.plan = self.injected_plan
            else:
                self.plan = self._plan_function(context)
            if not self.plan:
                return self._error_report("Planner failed to produce a test plan.")

            # Step 3: Worker generates test code
            generated = self._generate_tests(context)
            if not generated:
                return self._error_report("Worker failed to generate test code.")

            # Step 4: Run tests
            results = self._run_tests()

            # Step 5: Self-healing loop
            cfg = _cfg()
            for attempt in range(cfg.MAX_HEAL_RETRIES):
                failed = [r for r in results if r["status"] == "failed"]
                if not failed:
                    break
                self.log(f"Self-healing attempt {attempt + 1}/{cfg.MAX_HEAL_RETRIES}: {len(failed)} failed test(s)")
                healed = self._self_heal(failed, context)
                if not healed:
                    break
                results = self._run_tests()

            # Step 6: Compile report
            return self._compile_report(results)

        except Exception as e:
            self.log(f"Fatal error: {e}")
            return self._error_report(str(e))

    # ─── STEP 1: Gather context ────────────────────────────────────────
    def _gather_context(self) -> Optional[dict]:
        """Read the knowledge graph to build context for the Commander."""
        self.log("Gathering context from knowledge graph...")
        try:
            import nelgraph.knowledge_base as kb

            # Try function context first
            ctx = kb.get_function_context(self.target, class_name=self.class_name, file=self.file)
            if ctx and ctx.get("function"):
                func_info = ctx["function"]
                self.log(f"Found function '{self.target}' in {func_info.get('file', '?')}")
                primary = {
                    "name": func_info.get("name"),
                    "file": func_info.get("file"),
                    "class_name": func_info.get("class_name"),
                    "complexity": func_info.get("complexity"),
                    "is_async": func_info.get("is_async"),
                    "inputs": func_info.get("inputs"),
                    "output": func_info.get("output"),
                    "raises": func_info.get("raises"),
                    "edge_cases": func_info.get("edge_cases"),
                    "test_recommendations": func_info.get("test_recommendations"),
                    "raw_code": func_info.get("source_code") or func_info.get("raw_code"),
                    "callers": ctx.get("called_by", []),
                    "callees": ctx.get("calls_outside", []),
                }
                return {"type": "function", "primary": primary}

            # Try class context
            ctx = kb.get_class_context(self.target)
            if ctx and ctx.get("class"):
                self.log(f"Found class '{self.target}'")
                return {"type": "class", "primary": ctx}

            # Try semantic search
            results = kb.search(self.target, top_k=5)
            if results:
                self.log(f"Found {len(results)} related functions via semantic search")
                contexts = []
                for r in results[:3]:
                    c = kb.get_function_context(r["name"], file=r.get("file"))
                    if c and c.get("function"):
                        func_info = c["function"]
                        primary = {
                            "name": func_info.get("name"),
                            "file": func_info.get("file"),
                            "class_name": func_info.get("class_name"),
                            "complexity": func_info.get("complexity"),
                            "is_async": func_info.get("is_async"),
                            "inputs": func_info.get("inputs"),
                            "output": func_info.get("output"),
                            "raises": func_info.get("raises"),
                            "edge_cases": func_info.get("edge_cases"),
                            "test_recommendations": func_info.get("test_recommendations"),
                            "raw_code": func_info.get("source_code") or func_info.get("raw_code"),
                            "callers": c.get("called_by", []),
                            "callees": c.get("calls_outside", []),
                        }
                        contexts.append(primary)
                if contexts:
                    return {"type": "search", "primary": contexts[0], "related": contexts[1:]}

            return None
        except Exception as e:
            self.log(f"Error gathering context: {e}")
            return None

    # ─── STEP 2: Commander plans strategy ──────────────────────────────
    def _plan_strategy(self, context: dict) -> Optional[dict]:
        """Commander (DeepSeek-R1) analyzes the graph and produces a test plan."""
        self.log("Commander is analyzing dependencies and planning test strategy...")
        cfg = _cfg()

        context_block = self._format_context_for_prompt(context)

        prompt = COMMANDER_PLANNER_PROMPT.format(context_block=context_block)

        try:
            response = _call_llm_with_retry(
                _get_commander,
                model=cfg.COMMANDER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                timeout=300.0,
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from Commander")

            # Parse JSON from response (strip markdown fences if present)
            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            plan = json.loads(raw)
            self.log(f"Commander produced plan: {len(plan.get('test_files', []))} test file(s)")
            return plan

        except json.JSONDecodeError as e:
            self.log(f"Commander returned invalid JSON: {e}")
            # Try json_repair
            try:
                import json_repair
                plan = json_repair.loads(raw)
                self.log("Recovered plan via json_repair")
                return plan
            except Exception:
                return None
        except Exception as e:
            self.log(f"Commander error: {e}")
            return None

    def _plan_function(self, context: dict, error_feedback: str = "") -> Optional[dict]:
        """Planner (V4 Flash) reads source + graph context and produces detailed per-function plan."""
        self.log("Planner reading context and generating detailed test plan...")
        cfg = _cfg()
        context_block = self._format_context_for_prompt(context)

        group_hint = ""
        if self.group_context:
            shared_mocks = self.group_context.get("shared_mocks", [])
            if shared_mocks:
                group_hint = f"\n\n## Group-Level Shared Mocks (from Commander)\nThese mocks are shared across the module — include them in your plan:\n{json.dumps(shared_mocks, indent=2)}\n"

        prompt = FUNCTION_PLANNER_PROMPT.format(
            context_block=context_block,
            group_hint=group_hint,
            error_feedback=error_feedback or "None — this is the initial plan."
        )

        try:
            response = _call_llm_with_retry(
                _get_planner,
                model=cfg.PLANNER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                timeout=180.0,
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from Planner")

            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            plan = json.loads(raw)
            self.log(f"Planner produced plan: {len(plan.get('test_files', []))} file(s)")
            return plan

        except json.JSONDecodeError as e:
            self.log(f"Planner returned invalid JSON: {e}")
            try:
                import json_repair
                plan = json_repair.loads(raw)
                self.log("Recovered plan via json_repair.")
                return plan
            except Exception:
                return None
        except Exception as e:
            self.log(f"Planner error: {e}")
            return None

    def _replan_after_failure(self, context: dict, previous_plan: dict,
                               test_code: str, error_output: str) -> Optional[dict]:
        """Planner re-plans after Worker failure — new strategy, not just patching."""
        self.log("Planner re-planning after Worker failure...")
        cfg = _cfg()
        source_code = self._extract_source_code(context)
        source_file_path = context.get("primary", {}).get("file", "unknown")

        prompt = HEAL_PLANNER_PROMPT.format(
            source_file_path=source_file_path,
            source_code=source_code[:4000],
            previous_plan=json.dumps(previous_plan, indent=2)[:2000],
            test_code=test_code[:3000],
            error_output=error_output[:2000],
        )

        try:
            response = _call_llm_with_retry(
                _get_planner,
                model=cfg.PLANNER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                timeout=180.0,
            )
            content = response.choices[0].message.content
            if not content:
                return None

            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            try:
                new_plan = json.loads(raw)
            except json.JSONDecodeError as e:
                self.log(f"Planner returned invalid JSON in re-plan, attempting recovery: {e}")
                try:
                    import json_repair
                    new_plan = json_repair.loads(raw)
                    self.log("Recovered revised plan via json_repair.")
                except Exception:
                    raise e

            if new_plan.get("real_bug"):
                self.log(f"REAL BUG DETECTED by Planner: {new_plan.get('strategy_summary')}")
                self.bugs_found.append({
                    "file": self.file,
                    "explanation": new_plan.get("strategy_summary", ""),
                    "fix_suggestion": "",
                })
                return None  # Stop healing, không fix test nữa

            self.log("Planner produced revised plan.")
            return new_plan

        except Exception as e:
            self.log(f"Re-plan error: {e}")
            return None

    # ─── STEP 3: Worker generates test code ────────────────────────────
    def _generate_tests(self, context: dict, force: bool = False, previous_error: str = "") -> list:
        """Worker writes test code from the plan."""
        cfg = _cfg()
        self.log(f"Worker is generating test code with model: {cfg.WORKER_MODEL}...")
        registry = _load_registry()
        generated = []

        source_code = self._extract_source_code(context)

        for test_file_plan in self.plan.get("test_files", []):
            file_path = test_file_plan.get("file_path", "tests/test_generated.py")

            # Check registry: skip if source hasn't changed
            registry_key = f"{self.target}::{self.file or ''}"
            source_hash = _sha256(source_code)
            existing = registry.get("functions", {}).get(registry_key)

            if not force and existing and existing.get("function_hash") == source_hash:
                # Check if user has customized the test file
                abs_test_path = os.path.join(cfg.CODEBASE_PATH, file_path).replace("\\", "/")
                if os.path.exists(abs_test_path):
                    with open(abs_test_path, "r", encoding="utf-8") as f:
                        current_test_content = f.read()
                    if _sha256(current_test_content) != existing.get("test_file_hash"):
                        self.log(f"Skipping {file_path}: user has customized the test file")
                        generated.append({
                            "file_path": file_path,
                            "abs_path": abs_test_path,
                            "test_code": current_test_content,
                            "plan": test_file_plan,
                        })
                        continue
                    else:
                        self.log(f"Skipping {file_path}: source unchanged, test up to date")
                        generated.append({
                            "file_path": file_path,
                            "abs_path": abs_test_path,
                            "test_code": current_test_content,
                            "plan": test_file_plan,
                        })
                        continue

            source_file_path = context.get("primary", {}).get("file", "unknown")
            prompt = GENERATOR_PROMPT.format(
                plan_json=json.dumps(test_file_plan, indent=2),
                source_file_path=source_file_path,
                source_code=source_code,
                framework=cfg.TEST_FRAMEWORK,
                previous_error=previous_error or "None — this is the initial generation.",
            )

            try:
                max_gen_attempts = 3
                test_code = None
                for gen_attempt in range(1, max_gen_attempts + 1):
                    try:
                        response = _call_llm_with_retry(
                            _get_worker,
                            model=cfg.WORKER_MODEL,
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=8000,
                            timeout=300.0,
                        )
                        
                        # Validate response structure
                        if not response.choices:
                            raise ValueError(f"Worker API returned no choices. Check WORKER_MODEL='{cfg.WORKER_MODEL}' is valid on OpenRouter.")
                        
                        choice = response.choices[0]
                        finish_reason = getattr(choice, "finish_reason", None)
                        if finish_reason in ("error", "length"):
                            err_info = getattr(choice, "error", None) or f"finish_reason is '{finish_reason}' (truncated)"
                            raise ValueError(f"OpenRouter response truncated or errored: {err_info}")
                            
                        raw_content = choice.message.content
                        if not raw_content:
                            raise ValueError(f"Worker returned empty content for model '{cfg.WORKER_MODEL}'")
                        
                        # Strip markdown fences if present
                        raw_content = raw_content.strip()
                        if raw_content.startswith("```"):
                            raw_content = raw_content.split("\n", 1)[1] if "\n" in raw_content else raw_content[3:]
                            if raw_content.endswith("```"):
                                raw_content = raw_content[:-3]
                            raw_content = raw_content.strip()
                        
                        # Syntax validation for Python files
                        if file_path.endswith(".py"):
                            import ast
                            try:
                                ast.parse(raw_content)
                            except SyntaxError as se:
                                raise ValueError(f"Generated Python code has a syntax error: {se}")
                                
                        test_code = raw_content
                        break  # Success!
                    except Exception as e:
                        if gen_attempt == max_gen_attempts:
                            raise e
                        self.log(f"Worker generation attempt {gen_attempt} failed: {e}. Retrying generation...")

                # Write test file
                abs_test_path = os.path.join(cfg.CODEBASE_PATH, file_path).replace("\\", "/")
                os.makedirs(os.path.dirname(abs_test_path), exist_ok=True)
                with open(abs_test_path, "w", encoding="utf-8") as f:
                    f.write(test_code)

                # Update registry
                test_hash = _sha256(test_code)
                registry.setdefault("functions", {})[registry_key] = {
                    "test_file_path": file_path,
                    "function_hash": source_hash,
                    "test_file_hash": test_hash,
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "mode": self.mode,
                    "customized": False,
                }

                generated.append({
                    "file_path": file_path,
                    "abs_path": abs_test_path,
                    "test_code": test_code,
                    "plan": test_file_plan,
                })
                self.log(f"Generated {file_path} ({len(test_code)} chars)")

            except Exception as e:
                self.log(f"Worker error generating {file_path}: {e}")

        _save_registry(registry)
        self.generated_files = generated
        return generated

    def _ensure_async_dependencies(self):
        """Checks if generated tests have async test cases and ensures pytest-asyncio is installed in target env."""
        cfg = _cfg()
        if cfg.TEST_FRAMEWORK != "pytest":
            return

        has_async = False
        for gen in self.generated_files:
            test_code = gen.get("test_code", "")
            if "async def " in test_code or "@pytest.mark.asyncio" in test_code:
                has_async = True
                break

        if not has_async:
            return

        pip_path = None
        # Check standard virtualenv locations
        windows_pip = os.path.join(cfg.CODEBASE_PATH, ".venv", "Scripts", "pip.exe")
        unix_pip = os.path.join(cfg.CODEBASE_PATH, ".venv", "bin", "pip")

        if os.path.exists(windows_pip):
            pip_path = windows_pip
        elif os.path.exists(unix_pip):
            pip_path = unix_pip
        else:
            if cfg.PYTEST_PATH:
                dir_name = os.path.dirname(cfg.PYTEST_PATH)
                for name in ("pip.exe", "pip"):
                    p = os.path.join(dir_name, name)
                    if os.path.exists(p):
                        pip_path = p
                        break
            if not pip_path:
                dir_name = os.path.dirname(sys.executable)
                for name in ("pip.exe", "pip"):
                    p = os.path.join(dir_name, name)
                    if os.path.exists(p):
                        pip_path = p
                        break

        if not pip_path:
            pip_path = "pip"

        try:
            res = subprocess.run([pip_path, "show", "pytest-asyncio"], capture_output=True, text=True)
            if res.returncode != 0:
                self.log(f"Async tests detected but pytest-asyncio is missing. Installing pytest-asyncio via {pip_path}...")
                install_res = subprocess.run([pip_path, "install", "pytest-asyncio"], capture_output=True, text=True)
                if install_res.returncode == 0:
                    self.log("Successfully installed pytest-asyncio.")
                else:
                    self.log(f"Warning: Failed to install pytest-asyncio: {install_res.stderr}")
        except Exception as e:
            self.log(f"Warning: Error checking/installing pytest-asyncio: {e}")

    # ─── STEP 4: Run tests ─────────────────────────────────────────────
    def _run_tests(self) -> list:
        """Execute generated test files and parse results."""
        self.log("Running generated tests...")
        cfg = _cfg()
        self._ensure_async_dependencies()
        results = []

        for gen in self.generated_files:
            abs_path = gen["abs_path"]
            result = self._execute_single_test(abs_path)
            result["file_path"] = gen["file_path"]
            result["test_code"] = gen["test_code"]
            results.append(result)

        self.test_results = results
        passed = sum(1 for r in results if r["status"] == "passed")
        failed = sum(1 for r in results if r["status"] == "failed")
        self.log(f"Test results: {passed} passed, {failed} failed")
        return results

    def _execute_single_test(self, test_file_path: str) -> dict:
        """Run a single test file and return structured results."""
        cfg = _cfg()

        # Try to resolve virtual environment executables inside the codebase
        win_venv_pytest = os.path.join(cfg.CODEBASE_PATH, ".venv", "Scripts", "pytest.exe")
        unix_venv_pytest = os.path.join(cfg.CODEBASE_PATH, ".venv", "bin", "pytest")
        win_venv_python = os.path.join(cfg.CODEBASE_PATH, ".venv", "Scripts", "python.exe")
        unix_venv_python = os.path.join(cfg.CODEBASE_PATH, ".venv", "bin", "python")

        local_pytest = win_venv_pytest if os.path.exists(win_venv_pytest) else (unix_venv_pytest if os.path.exists(unix_venv_pytest) else None)
        local_python = win_venv_python if os.path.exists(win_venv_python) else (unix_venv_python if os.path.exists(unix_venv_python) else None)

        if cfg.TEST_FRAMEWORK == "pytest":
            import shutil
            pytest_exe = cfg.PYTEST_PATH or local_pytest or shutil.which("pytest")
            if pytest_exe:
                cmd = [pytest_exe, test_file_path, "-v", "--tb=short", "--no-header", "-q"]
            else:
                python_exe = local_python or sys.executable
                cmd = [
                    python_exe, "-m", "pytest", test_file_path,
                    "-v", "--tb=short", "--no-header", "-q"
                ]
        elif cfg.TEST_FRAMEWORK in ("jest", "vitest"):
            cmd = ["npx", cfg.TEST_FRAMEWORK, test_file_path, "--no-coverage"]
        else:
            import shutil
            pytest_exe = cfg.PYTEST_PATH or local_pytest or shutil.which("pytest")
            if pytest_exe:
                cmd = [pytest_exe, test_file_path, "-v", "--tb=short"]
            else:
                python_exe = local_python or sys.executable
                cmd = [python_exe, "-m", "pytest", test_file_path, "-v", "--tb=short"]

        # Prepare environment with PYTHONPATH set to the codebase root
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        codebase_abs = os.path.abspath(cfg.CODEBASE_PATH)
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{codebase_abs}{os.pathsep}{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = codebase_abs

        try:
            proc = subprocess.run(
                cmd,
                cwd=cfg.CODEBASE_PATH,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            output = (proc.stdout or "") + (proc.stderr or "")

            if proc.returncode == 0:
                return {"status": "passed", "output": output, "returncode": 0}
            else:
                return {"status": "failed", "output": output, "returncode": proc.returncode}

        except subprocess.TimeoutExpired:
            return {"status": "failed", "output": "Test execution timed out (60s)", "returncode": -1}
        except Exception as e:
            return {"status": "failed", "output": str(e), "returncode": -1}

    # ─── STEP 5: Self-healing ──────────────────────────────────────────
    def _self_heal(self, failed_results: list, context: dict) -> bool:
        """Planner re-plans after failures, Worker re-generates test code."""
        any_fixed = False

        for result in failed_results:
            test_code = result.get("test_code", "")
            error_output = result.get("output", "")[:3000]

            self.log(f"Planner re-planning after failure in {result.get('file_path', '?')}...")

            new_plan = self._replan_after_failure(
                context=context,
                previous_plan=self.plan,
                test_code=test_code,
                error_output=error_output,
            )

            if not new_plan:
                self.log("Planner could not produce new plan (real bug or error). Skipping.")
                continue

            self.plan = new_plan

            self.log(f"Worker re-generating test for {result.get('file_path', '?')} with new plan...")
            regenerated = self._generate_tests(context, force=True, previous_error=error_output)

            if regenerated:
                any_fixed = True
                self.log(f"Worker re-generated test file {result.get('file_path')} with revised plan. Re-running tests to verify.")

        return any_fixed

    # ─── STEP 6: Compile report ────────────────────────────────────────
    def _compile_report(self, results: list) -> dict:
        """Produce the final structured report."""
        passed = [r for r in results if r["status"] == "passed"]
        failed = [r for r in results if r["status"] == "failed"]

        report = {
            "success": len(failed) == 0,
            "target": self.target,
            "mode": self.mode,
            "summary": {
                "total_files": len(results),
                "passed": len(passed),
                "failed": len(failed),
                "self_healed": len(self.heal_history),
                "bugs_found": len(self.bugs_found),
            },
            "strategy": self.plan.get("strategy_summary", "") if self.plan else "",
            "generated_files": [g["file_path"] for g in self.generated_files],
            "test_results": [
                {
                    "file": r.get("file_path"),
                    "status": r["status"],
                    "output": r.get("output", "")[:2000],
                }
                for r in results
            ],
            "bugs_found": self.bugs_found,
            "heal_history": self.heal_history,
            "log": self._log,
        }

        self.log(f"Report compiled: {report['summary']}")
        return report

    def _error_report(self, message: str) -> dict:
        return {
            "success": False,
            "target": self.target,
            "mode": self.mode,
            "error": message,
            "summary": {"total_files": 0, "passed": 0, "failed": 0, "self_healed": 0, "bugs_found": 0},
            "log": self._log,
        }

    # ─── Helpers ───────────────────────────────────────────────────────
    def _format_context_for_prompt(self, context: dict) -> str:
        """Format gathered graph context into a text block for the Commander prompt."""
        parts = []
        primary = context.get("primary", {})

        if context["type"] == "function":
            parts.append(f"Function: {primary.get('name', '?')}")
            parts.append(f"File: {primary.get('file', '?')}")
            parts.append(f"Class: {primary.get('class_name', 'None')}")
            parts.append(f"Complexity: {primary.get('complexity', '?')}")
            parts.append(f"Is Async: {primary.get('is_async', False)}")
            parts.append(f"Inputs: {json.dumps(primary.get('inputs', []))}")
            parts.append(f"Output: {primary.get('output', '?')}")
            parts.append(f"Raises: {json.dumps(primary.get('raises', []))}")
            parts.append(f"Edge Cases: {json.dumps(primary.get('edge_cases', []))}")
            parts.append(f"Test Recommendations: {json.dumps(primary.get('test_recommendations', []))}")
            parts.append(f"Callers (blast radius): {json.dumps(primary.get('callers', []))}")
            parts.append(f"Callees (dependencies to mock): {json.dumps(primary.get('callees', []))}")
            parts.append(f"\nSource code:\n```\n{primary.get('raw_code', '')[:5000]}\n```")

        elif context["type"] == "class":
            cls = primary.get("class", {})
            parts.append(f"Class: {cls.get('name', '?')}")
            parts.append(f"File: {cls.get('file', '?')}")
            methods = primary.get("methods", [])
            parts.append(f"Methods: {json.dumps([m.get('name') for m in methods])}")
            parts.append(f"Parent classes: {json.dumps(primary.get('parent_classes', []))}")

        elif context["type"] == "search":
            parts.append(f"Primary match: {primary.get('name', '?')} in {primary.get('file', '?')}")
            parts.append(f"Source:\n```\n{primary.get('raw_code', '')[:3000]}\n```")
            for i, rel in enumerate(context.get("related", [])):
                parts.append(f"\nRelated #{i+1}: {rel.get('name', '?')} in {rel.get('file', '?')}")

        parts.append(f"\nTest mode: {self.mode}")
        return "\n".join(parts)

    def _extract_source_code(self, context: dict) -> str:
        """Extract source code from context for use in prompts. Uses the full file if available on disk."""
        primary = context.get("primary", {})
        file_path = primary.get("file")
        if file_path:
            cfg = _cfg()
            abs_path = os.path.join(cfg.CODEBASE_PATH, file_path).replace("\\", "/")
            if os.path.exists(abs_path):
                try:
                    if os.path.getsize(abs_path) < 150 * 1024:
                        with open(abs_path, "r", encoding="utf-8") as f:
                            return f.read()
                except Exception as e:
                    self.log(f"Warning: Failed to read full file {file_path} from disk: {e}")

        if context["type"] == "function":
            return primary.get("raw_code", "")
        elif context["type"] == "class":
            cls = primary.get("class", {})
            return cls.get("raw_code", "")
        elif context["type"] == "search":
            return primary.get("raw_code", "")
        return ""

