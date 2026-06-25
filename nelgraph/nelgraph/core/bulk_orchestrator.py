import os
import sys
import json
import time
import threading
import concurrent.futures
from typing import Optional

from nelgraph.core.test_agent import TestAgent, _get_commander, _cfg
from nelgraph.knowledge_base import mark_tested

# ─── BulkTestOrchestrator ──────────────────────────────────────────
class BulkTestOrchestrator:
    """Orchestrates bulk and incremental test generation for multiple functions."""

    def __init__(self, functions: list[dict], mode: str = "unit"):
        """
        Args:
            functions: List of functions to test. Format:
                       [{"name": str, "file": str, "class_name": str|None, "complexity": int, "community_id": str|None}, ...]
            mode: "unit" | "integration" | "system"
        """
        self.functions = functions
        self.mode = mode
        self.master_plan = None
        self.results = []
        self.bugs_found = []
        self._log = []
        self.progress = {"done": 0, "total": len(functions), "current": None}
        self._lock = threading.Lock()

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._log.append(entry)
        print(f"[BulkTestOrchestrator] {entry}")

    def _make_skip_result(self, fn: dict) -> dict:
        return {
            "success": True,
            "target": fn["name"],
            "mode": self.mode,
            "skipped": True,
            "summary": {"total_files": 0, "passed": 0, "failed": 0, "self_healed": 0, "bugs_found": 0},
            "strategy": "Skipped by Commander directive",
            "generated_files": [],
            "test_results": [],
            "bugs_found": [],
            "heal_history": [],
            "log": ["Skipped by Commander master plan directive."]
        }

    def _make_error_result(self, fn: dict, error: str) -> dict:
        return {
            "success": False,
            "target": fn["name"],
            "mode": self.mode,
            "error": error,
            "summary": {"total_files": 0, "passed": 0, "failed": 0, "self_healed": 0, "bugs_found": 0},
            "strategy": "Error during execution",
            "generated_files": [],
            "test_results": [],
            "bugs_found": [],
            "heal_history": [],
            "log": [f"Error processing: {error}"]
        }

    def run(self, progress_callback=None) -> dict:
        self.log(f"Starting bulk test generation for {len(self.functions)} function(s)...")

        # Step 1: Commander plans strategy 1 time for the entire batch
        self.master_plan = self._commander_plan_batch()
        if progress_callback:
            progress_callback(self.progress, self.results, self.bugs_found)

        # Build lookup: function_name -> group_context
        fn_to_group = {}
        for group in self.master_plan.get("groups", []):
            for fn_name in group.get("functions", []):
                fn_to_group[fn_name] = {
                    "group_name": group.get("group_name"),
                    "test_type": group.get("test_type", self.mode),
                    "shared_mocks": group.get("shared_mocks", []),
                }

        # Sort self.functions according to priority_order
        priority = self.master_plan.get("priority_order", [])
        priority_index = {name: i for i, name in enumerate(priority)}
        self.functions = sorted(
            self.functions,
            key=lambda fn: priority_index.get(fn["name"], len(priority))
        )

        skip_list = self.master_plan.get("skip", [])
        fns_to_run = [fn for fn in self.functions if fn["name"] not in skip_list]
        fns_skipped = [fn for fn in self.functions if fn["name"] in skip_list]

        # Process skipped functions immediately
        for fn in fns_skipped:
            self.log(f"Skipping function '{fn['name']}' as per Commander's master plan directive.")
            self.results.append(self._make_skip_result(fn))
            self.progress["done"] += 1

        if progress_callback:
            progress_callback(self.progress, self.results, self.bugs_found)

        # Step 2: Concurrent worker execution
        cfg = _cfg()
        max_workers = getattr(cfg, "MAX_BULK_WORKERS", 5)
        self.log(f"Starting concurrent test generation with max_workers={max_workers}")

        def _run_one(fn):
            self.progress["current"] = fn["name"]
            if progress_callback:
                progress_callback(self.progress, self.results, self.bugs_found)

            try:
                result = self._worker_run_single(fn, group_context=fn_to_group.get(fn["name"]))
            except Exception as e:
                self.log(f"Error processing '{fn['name']}': {e}")
                result = self._make_error_result(fn, str(e))

            with self._lock:
                self.results.append(result)
                self.progress["done"] += 1
                if progress_callback:
                    progress_callback(self.progress, self.results, self.bugs_found)

            return result

        if fns_to_run:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_run_one, fn): fn for fn in fns_to_run}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        fn = futures[future]
                        self.log(f"Unhandled error in thread for '{fn['name']}': {e}")

        self.log(f"Bulk test run completed: {self.progress['done']}/{self.progress['total']} processed.")
        return self._compile_report()


    def _commander_plan_batch(self) -> dict:
        """Call Commander (DeepSeek-R1) one time to generate a batch master test plan."""
        self.log(f"Commander is planning for {len(self.functions)} function(s)...")
        cfg = _cfg()

        # Prepare metadata to keep prompt small
        metadata_list = []
        for fn in self.functions:
            metadata_list.append({
                "name": fn.get("name"),
                "file": fn.get("file"),
                "class_name": fn.get("class_name"),
                "complexity": fn.get("complexity"),
                "community_id": fn.get("community_id")
            })

        metadata_str = json.dumps(metadata_list, indent=2)

        prompt = f"""You are an expert QA director. You are planning the testing strategy for a batch of functions in the codebase.
Your goal is to organize them into logical test groups, define shared mocks, and determine the priority order.

## Functions to Test
{metadata_str}

## Task
Produce a JSON master test plan with EXACTLY this structure:
{{
  "strategy_summary": "Overall strategy description for this batch",
  "priority_order": ["fn_name_1", "fn_name_2", ...],
  "groups": [
    {{
      "group_name": "group_name_1",
      "functions": ["fn_name_1", "fn_name_3"],
      "test_type": "unit|integration|system",
      "shared_mocks": ["module.class.method", "package.submodule"]
    }}
  ],
  "skip": ["fn_name_to_skip"]
}}

RULES:
- `groups`: Group functions that belong to the same module/community, share dependencies, or should be tested together.
- `shared_mocks`: Define high-level dependencies or resources (e.g. databases, external APIs, time, network) that should be mocked for this group.
- `skip`: List functions that are TRULY trivial — ONLY: empty methods (pass-only body), pure property getters that return a single attribute with no logic, or __repr__/__str__ that only do string formatting.
- NEVER skip: async functions, functions with conditional logic, __init__ with non-trivial setup, functions that call other methods or external dependencies.
- NEVER skip functions whose names start with 'test_' — those are pre-existing test functions being indexed as source code, not generation targets. They should have been filtered before reaching this step.
- Return ONLY valid JSON, no markdown fences.
"""

        fallback_plan = {
            "strategy_summary": "Fallback sequential unit testing.",
            "priority_order": [fn["name"] for fn in self.functions],
            "groups": [
                {
                    "group_name": "default_group",
                    "functions": [fn["name"] for fn in self.functions],
                    "test_type": self.mode,
                    "shared_mocks": []
                }
            ],
            "skip": []
        }

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

            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            try:
                plan = json.loads(raw)
                self.log(f"Commander successfully generated batch master plan with {len(plan.get('groups', []))} groups.")
                return plan
            except json.JSONDecodeError as e:
                self.log(f"Commander invalid JSON, attempting recovery: {e}")
                try:
                    import json_repair
                    plan = json_repair.loads(raw)
                    self.log("Recovered master plan via json_repair.")
                    return plan
                except Exception:
                    self.log("Failed to recover master plan. Falling back to default plan.")
                    return fallback_plan
        except Exception as e:
            self.log(f"Error getting batch plan from Commander: {e}. Falling back to default plan.")
            return fallback_plan

    def _worker_run_single(self, fn: dict, group_context: dict = None) -> dict:
        """Run Worker to generate and self-heal test for a single function."""
        self.log(f"Processing: {fn['name']} ({fn.get('file')})")

        # We do not inject a plan here anymore, so TestAgent can use its Planner layer
        agent = TestAgent(
            target=fn["name"],
            mode=group_context.get("test_type", self.mode) if group_context else self.mode,
            file=fn.get("file"),
            class_name=fn.get("class_name"),
            injected_plan=None,
            group_context=group_context,
        )

        # Run Agent (which runs Planner -> Worker + Self-healing loop)
        report = agent.run()

        # Collect results
        if agent.bugs_found:
            with self._lock:
                self.bugs_found.extend(agent.bugs_found)

        success = report.get("success", False)
        self.log(f"  -> {'PASSED' if success else 'FAILED'}: {fn['name']}")

        # If passed, mark tested in Neo4j
        if success:
            try:
                mark_tested(fn["name"], file=fn.get("file"))
            except Exception as e:
                self.log(f"Error marking '{fn['name']}' as tested: {e}")

        return report

    def _compile_report(self) -> dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get("success", False) and not r.get("skipped", False))
        failed = sum(1 for r in self.results if not r.get("success", False))
        skipped = sum(1 for r in self.results if r.get("skipped", False))

        return {
            "success": failed == 0,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "bugs_found": len(self.bugs_found)
            },
            "strategy": self.master_plan.get("strategy_summary", "") if self.master_plan else "",
            "results": self.results,
            "bugs_found": self.bugs_found,
            "log": self._log
        }
