import os
import sys
import json
import time
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

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._log.append(entry)
        print(f"[BulkTestOrchestrator] {entry}")

    def run(self, progress_callback=None) -> dict:
        self.log(f"Starting bulk test generation for {len(self.functions)} function(s)...")

        # Step 1: Commander plans strategy 1 time for the entire batch
        self.master_plan = self._commander_plan_batch()
        if progress_callback:
            progress_callback(self.progress, self.results, self.bugs_found)

        # Step 2: Worker processes each function using the master plan guidelines
        skip_list = self.master_plan.get("skip", [])
        for fn in self.functions:
            self.progress["current"] = fn["name"]
            if progress_callback:
                progress_callback(self.progress, self.results, self.bugs_found)

            if fn["name"] in skip_list:
                self.log(f"Skipping function '{fn['name']}' as per Commander's master plan directive.")
                result = {
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
            else:
                try:
                    result = self._worker_run_single(fn)
                except Exception as e:
                    self.log(f"Error processing '{fn['name']}': {e}")
                    result = {
                        "success": False,
                        "target": fn["name"],
                        "mode": self.mode,
                        "error": str(e),
                        "summary": {"total_files": 0, "passed": 0, "failed": 0, "self_healed": 0, "bugs_found": 0},
                        "strategy": "Error during execution",
                        "generated_files": [],
                        "test_results": [],
                        "bugs_found": [],
                        "heal_history": [],
                        "log": [f"Error processing: {e}"]
                    }

            self.results.append(result)
            self.progress["done"] += 1

            if progress_callback:
                progress_callback(self.progress, self.results, self.bugs_found)

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
- `skip`: List functions that are too simple (complexity <= 1, trivial getters/setters, empty methods) or do not require test generation.
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

    def _worker_run_single(self, fn: dict) -> dict:
        """Run Worker to generate and self-heal test for a single function."""
        self.log(f"Worker processing function: {fn['name']} (File: {fn.get('file')})")

        # 1. Find group from master plan
        group = None
        if self.master_plan and "groups" in self.master_plan:
            for g in self.master_plan["groups"]:
                if fn["name"] in g.get("functions", []):
                    group = g
                    break

        # 2. Determine test file path
        import os
        file_path_raw = fn.get("file") or f"{fn['name']}.py"
        base_name = os.path.basename(file_path_raw)
        module_name = os.path.splitext(base_name)[0]
        test_file_path = f"tests/test_{module_name}.py"

        # 3. Build mocks
        mocks = []
        if group and "shared_mocks" in group:
            for sm in group["shared_mocks"]:
                mocks.append({
                    "target": sm,
                    "reason": "Shared mock from master plan",
                    "mock_value": "None"
                })

        test_type = (group.get("test_type") if group else None) or self.mode

        # 4. Construct injected plan
        injected_plan = {
            "strategy_summary": self.master_plan.get("strategy_summary", "Batch plan testing strategy"),
            "test_files": [
                {
                    "file_path": test_file_path,
                    "test_type": test_type,
                    "target_functions": [fn["name"]],
                    "mocks": mocks,
                    "test_cases": [
                        {
                            "name": f"test_{fn['name']}_happy_path",
                            "category": "happy",
                            "description": f"Happy path verification for {fn['name']}",
                            "inputs": "auto-generate",
                            "expected": "auto-generate"
                        },
                        {
                            "name": f"test_{fn['name']}_error_path",
                            "category": "error",
                            "description": f"Error/exception path handling for {fn['name']}",
                            "inputs": "auto-generate",
                            "expected": "auto-generate"
                        },
                        {
                            "name": f"test_{fn['name']}_edge_case",
                            "category": "edge",
                            "description": f"Boundary/edge conditions for {fn['name']}",
                            "inputs": "auto-generate",
                            "expected": "auto-generate"
                        }
                    ]
                }
            ]
        }

        # 5. Initialize TestAgent with injected plan
        agent = TestAgent(
            target=fn["name"],
            mode=test_type,
            file=fn.get("file"),
            class_name=fn.get("class_name"),
            injected_plan=injected_plan,
            bulk_mode=True
        )

        # 6. Run Agent (which runs Worker + Self-healing loop)
        report = agent.run()

        # 7. Collect results
        if agent.bugs_found:
            self.bugs_found.extend(agent.bugs_found)

        success = report.get("success", False)
        self.log(f"Function {fn['name']} test gen outcome: {'PASSED' if success else 'FAILED'}")

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
