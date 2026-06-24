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


def _get_worker():
    global _worker_client
    if _worker_client is None:
        cfg = _cfg()
        _worker_client = openai.OpenAI(
            api_key=cfg.OPENROUTER_API_KEY,
            base_url=cfg.OPENROUTER_BASE_URL,
        )
    return _worker_client


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
PLANNER_PROMPT = """You are an expert QA architect. You have access to a codebase knowledge graph.
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

GENERATOR_PROMPT = """You are an expert test code writer. Write complete, runnable test code based on this plan.

## Test Plan
{plan_json}

## Source Code of Target Function(s)
{source_code}

## Testing Framework: {framework}

RULES:
- Write a COMPLETE, RUNNABLE test file. Include all imports.
- Use {framework} syntax and conventions.
- Follow the mock strategy EXACTLY as specified in the plan.
- Each test case from the plan must become a real test function.
- Use descriptive test names matching the plan's test case names.
- Include proper setup/teardown if needed.
- Return ONLY the Python/JS code, no markdown fences, no explanations.
"""

DIAGNOSIS_PROMPT = """You are an expert debugging engineer. A generated test has failed.
Analyze the failure and determine the root cause.

## Original Source Code
{source_code}

## Generated Test Code
{test_code}

## Error Output
{error_output}

## Task
Determine if the failure is caused by:
1. INCORRECT TEST CODE (wrong mock, wrong assertion, import error, syntax error)
2. REAL BUG in the source code (the test correctly caught a defect)

Respond with EXACTLY this JSON:
{{
  "diagnosis": "test_error" | "real_bug",
  "explanation": "Clear explanation of what went wrong",
  "fix_instructions": "Specific instructions for fixing the test code (if diagnosis is test_error) or description of the bug (if diagnosis is real_bug)"
}}

Return ONLY valid JSON, no markdown.
"""

FIX_PROMPT = """You are an expert test code fixer. Fix the following test code based on the diagnosis.

## Original Source Code
{source_code}

## Current Test Code (has errors)
{test_code}

## Error Output
{error_output}

## Diagnosis & Fix Instructions
{fix_instructions}

Write the COMPLETE fixed test file. Include all imports. Return ONLY code, no markdown fences.
"""


# ─── TestAgent ──────────────────────────────────────────────────────────────
class TestAgent:
    """Autonomous dual-model test generation agent."""

    def __init__(self, target: str, mode: str = "unit", file: str = None, class_name: str = None):
        """
        Args:
            target: Function name or community name to test.
            mode: "unit" | "integration" | "system"
            file: Optional file path for disambiguation.
            class_name: Optional class name for disambiguation.
        """
        self.target = target
        self.mode = mode
        self.file = file
        self.class_name = class_name
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

            # Step 2: Commander plans strategy
            self.plan = self._plan_strategy(context)
            if not self.plan:
                return self._error_report("Commander failed to produce a test plan.")

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

        prompt = PLANNER_PROMPT.format(context_block=context_block)

        try:
            response = _get_commander().chat.completions.create(
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

    # ─── STEP 3: Worker generates test code ────────────────────────────
    def _generate_tests(self, context: dict) -> list:
        """Worker (Qwen3 Coder Next) writes test code from the plan."""
        self.log("Worker is generating test code...")
        cfg = _cfg()
        registry = _load_registry()
        generated = []

        source_code = self._extract_source_code(context)

        for test_file_plan in self.plan.get("test_files", []):
            file_path = test_file_plan.get("file_path", "tests/test_generated.py")

            # Check registry: skip if source hasn't changed
            registry_key = f"{self.target}::{self.file or ''}"
            source_hash = _sha256(source_code)
            existing = registry.get("functions", {}).get(registry_key)

            if existing and existing.get("function_hash") == source_hash:
                # Check if user has customized the test file
                abs_test_path = os.path.join(cfg.CODEBASE_PATH, file_path).replace("\\", "/")
                if os.path.exists(abs_test_path):
                    with open(abs_test_path, "r", encoding="utf-8") as f:
                        current_test_content = f.read()
                    if _sha256(current_test_content) != existing.get("test_file_hash"):
                        self.log(f"Skipping {file_path}: user has customized the test file")
                        continue
                    else:
                        self.log(f"Skipping {file_path}: source unchanged, test up to date")
                        continue

            prompt = GENERATOR_PROMPT.format(
                plan_json=json.dumps(test_file_plan, indent=2),
                source_code=source_code,
                framework=cfg.TEST_FRAMEWORK,
            )

            try:
                response = _get_worker().chat.completions.create(
                    model=cfg.WORKER_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8000,
                    timeout=300.0,
                )
                test_code = response.choices[0].message.content
                if not test_code:
                    raise ValueError("Empty response from Worker")

                # Strip markdown fences if present
                test_code = test_code.strip()
                if test_code.startswith("```"):
                    test_code = test_code.split("\n", 1)[1] if "\n" in test_code else test_code[3:]
                    if test_code.endswith("```"):
                        test_code = test_code[:-3]
                    test_code = test_code.strip()

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

    # ─── STEP 4: Run tests ─────────────────────────────────────────────
    def _run_tests(self) -> list:
        """Execute generated test files and parse results."""
        self.log("Running generated tests...")
        cfg = _cfg()
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

        if cfg.TEST_FRAMEWORK == "pytest":
            cmd = [
                sys.executable, "-m", "pytest", test_file_path,
                "-v", "--tb=short", "--no-header", "-q"
            ]
        elif cfg.TEST_FRAMEWORK in ("jest", "vitest"):
            cmd = ["npx", cfg.TEST_FRAMEWORK, test_file_path, "--no-coverage"]
        else:
            cmd = [sys.executable, "-m", "pytest", test_file_path, "-v", "--tb=short"]

        try:
            proc = subprocess.run(
                cmd,
                cwd=cfg.CODEBASE_PATH,
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
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
        """Commander diagnoses failures, Worker fixes the code."""
        cfg = _cfg()
        source_code = self._extract_source_code(context)
        any_fixed = False

        for result in failed_results:
            test_code = result.get("test_code", "")
            error_output = result.get("output", "")[:3000]  # Truncate long outputs

            # Commander diagnoses
            self.log(f"Commander diagnosing failure in {result.get('file_path', '?')}...")
            diagnosis = self._diagnose(source_code, test_code, error_output)

            if not diagnosis:
                self.log("Commander failed to diagnose. Skipping.")
                continue

            self.heal_history.append({
                "file": result.get("file_path"),
                "diagnosis": diagnosis,
            })

            if diagnosis.get("diagnosis") == "real_bug":
                self.log(f"REAL BUG DETECTED: {diagnosis.get('explanation', '')}")
                self.bugs_found.append({
                    "file": result.get("file_path"),
                    "explanation": diagnosis.get("explanation", ""),
                    "fix_suggestion": diagnosis.get("fix_instructions", ""),
                })
                continue

            # Worker fixes
            self.log(f"Worker fixing test code for {result.get('file_path', '?')}...")
            fixed_code = self._fix_test(source_code, test_code, error_output, diagnosis)

            if fixed_code:
                # Find the corresponding generated file and update it
                for gen in self.generated_files:
                    if gen["file_path"] == result.get("file_path"):
                        abs_path = gen["abs_path"]
                        with open(abs_path, "w", encoding="utf-8") as f:
                            f.write(fixed_code)
                        gen["test_code"] = fixed_code
                        result["test_code"] = fixed_code

                        # Update registry hash
                        registry = _load_registry()
                        registry_key = f"{self.target}::{self.file or ''}"
                        if registry_key in registry.get("functions", {}):
                            registry["functions"][registry_key]["test_file_hash"] = _sha256(fixed_code)
                            _save_registry(registry)

                        any_fixed = True
                        self.log(f"Fixed and saved {result.get('file_path')}")
                        break

        return any_fixed

    def _diagnose(self, source_code: str, test_code: str, error_output: str) -> Optional[dict]:
        """Commander analyzes a test failure."""
        cfg = _cfg()
        prompt = DIAGNOSIS_PROMPT.format(
            source_code=source_code[:4000],
            test_code=test_code[:4000],
            error_output=error_output[:3000],
        )

        try:
            response = _get_commander().chat.completions.create(
                model=cfg.COMMANDER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
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

            return json.loads(raw)
        except Exception as e:
            self.log(f"Diagnosis error: {e}")
            return None

    def _fix_test(self, source_code: str, test_code: str, error_output: str, diagnosis: dict) -> Optional[str]:
        """Worker rewrites the test code based on Commander's diagnosis."""
        cfg = _cfg()
        prompt = FIX_PROMPT.format(
            source_code=source_code[:4000],
            test_code=test_code[:4000],
            error_output=error_output[:2000],
            fix_instructions=diagnosis.get("fix_instructions", "Fix the failing test."),
        )

        try:
            response = _get_worker().chat.completions.create(
                model=cfg.WORKER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8000,
                timeout=300.0,
            )
            code = response.choices[0].message.content
            if not code:
                return None

            code = code.strip()
            if code.startswith("```"):
                code = code.split("\n", 1)[1] if "\n" in code else code[3:]
                if code.endswith("```"):
                    code = code[:-3]
                code = code.strip()

            return code
        except Exception as e:
            self.log(f"Fix error: {e}")
            return None

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
        """Extract source code from context for use in prompts."""
        primary = context.get("primary", {})
        if context["type"] == "function":
            return primary.get("raw_code", "")
        elif context["type"] == "class":
            cls = primary.get("class", {})
            return cls.get("raw_code", "")
        elif context["type"] == "search":
            return primary.get("raw_code", "")
        return ""
