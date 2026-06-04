"""
Server State Manager — Manages FIRST_RUN / ONGOING modes and commit queue.

This module is the central brain that coordinates the server's operational state,
tracks pipeline job progress, and manages the commit queue for deferred webhook
delivery during the FIRST_RUN phase.
"""

import os
import json
import time
import uuid
import threading
import requests as http_requests

from config import GRAPHRAG_DATA_DIR, WEBHOOK_URL


# ═══════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════

MODE_IDLE = "IDLE"
MODE_FIRST_RUN = "FIRST_RUN"
MODE_ONGOING = "ONGOING"

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"

STATE_FILE = os.path.join(GRAPHRAG_DATA_DIR, "server_state.json").replace("\\", "/")


# ═══════════════════════════════════════════════════════════
# ServerState — Singleton
# ═══════════════════════════════════════════════════════════

class ServerState:
    """
    Thread-safe singleton managing server operational state.

    Tracks:
    - mode: IDLE → FIRST_RUN → ONGOING
    - current_job: Pipeline job progress (step, message, progress %)
    - commit_queue: Commits received during FIRST_RUN, flushed on transition
    - total_functions: Count of indexed functions
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._state_lock = threading.RLock()

        # Default state
        self.mode = MODE_IDLE
        self.total_functions = 0
        self.commit_queue = []
        self.current_job = None
        self.last_sync = None
        self.codebase_path = None

        # Try to restore from disk
        self._load()

    # ───────────────────────────────────────────────────
    # Persistence
    # ───────────────────────────────────────────────────

    def _load(self):
        """Load state from disk if available."""
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.mode = data.get("mode", MODE_IDLE)
            self.total_functions = data.get("total_functions", 0)
            self.commit_queue = data.get("commit_queue", [])
            self.last_sync = data.get("last_sync", None)
            self.codebase_path = data.get("codebase_path", None)
            # Don't restore current_job — it's ephemeral (lost on restart)
            print(f"[State] Restored state: mode={self.mode}, functions={self.total_functions}")
        except Exception as e:
            print(f"[State] Warning: Could not load state file: {e}")

    def _save(self):
        """Persist state to disk."""
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        try:
            data = {
                "mode": self.mode,
                "total_functions": self.total_functions,
                "commit_queue": self.commit_queue,
                "last_sync": self.last_sync,
                "codebase_path": self.codebase_path,
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[State] Warning: Could not save state file: {e}")

    # ───────────────────────────────────────────────────
    # Job Management
    # ───────────────────────────────────────────────────

    def create_job(self, total_steps: int = 9) -> str:
        """Create a new pipeline job and return its ID."""
        with self._state_lock:
            job_id = f"job-{uuid.uuid4().hex[:8]}"
            self.current_job = {
                "job_id": job_id,
                "step": 0,
                "total_steps": total_steps,
                "status": JOB_QUEUED,
                "progress": 0,
                "message": "Queued",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            return job_id

    def update_job(self, step: int, message: str):
        """Update current job progress."""
        with self._state_lock:
            if self.current_job is None:
                return
            self.current_job["step"] = step
            self.current_job["status"] = JOB_RUNNING
            self.current_job["message"] = message
            total = self.current_job["total_steps"]
            self.current_job["progress"] = int((step / total) * 100) if total > 0 else 0
            print(f"[Pipeline] Step {step}/{total}: {message}")

    def complete_job(self, success: bool = True, message: str = ""):
        """Mark current job as done or failed."""
        with self._state_lock:
            if self.current_job is None:
                return
            self.current_job["status"] = JOB_DONE if success else JOB_FAILED
            self.current_job["progress"] = 100 if success else self.current_job["progress"]
            self.current_job["message"] = message or ("Pipeline complete" if success else "Pipeline failed")
            self.current_job["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    def get_job_status(self, job_id: str) -> dict | None:
        """Get status of a job by ID."""
        with self._state_lock:
            if self.current_job and self.current_job.get("job_id") == job_id:
                return dict(self.current_job)
        return None

    # ───────────────────────────────────────────────────
    # Mode Transitions
    # ───────────────────────────────────────────────────

    def set_first_run(self, total_functions: int, codebase_path: str):
        """Transition to FIRST_RUN mode after pipeline completes."""
        with self._state_lock:
            self.mode = MODE_FIRST_RUN
            self.total_functions = total_functions
            self.codebase_path = codebase_path
            self._save()
            print(f"[State] Mode → FIRST_RUN (total_functions={total_functions})")

    def complete_first_run(self, generated_count: int) -> dict:
        """
        Transition from FIRST_RUN → ONGOING.
        Flush the commit queue and return queued commits.
        """
        with self._state_lock:
            self.mode = MODE_ONGOING
            queued = list(self.commit_queue)
            self.commit_queue = []
            self._save()
            print(f"[State] Mode → ONGOING (generated={generated_count}, flushing {len(queued)} queued commits)")

        # Flush queued commits via webhook (in background)
        if queued and WEBHOOK_URL:
            threading.Thread(target=self._flush_webhooks, args=(queued,), daemon=True).start()

        return {
            "mode": MODE_ONGOING,
            "flushed_commits": len(queued),
        }

    def _flush_webhooks(self, commits: list):
        """Send queued commit webhooks to Auto-Test Agent."""
        for commit_event in commits:
            try:
                http_requests.post(WEBHOOK_URL, json=commit_event, timeout=10)
                print(f"[Webhook] Flushed commit {commit_event.get('commit', '?')[:8]}")
            except Exception as e:
                print(f"[Webhook] Failed to flush commit: {e}")
            time.sleep(0.5)  # Rate limit

    # ───────────────────────────────────────────────────
    # Commit Queue
    # ───────────────────────────────────────────────────

    def enqueue_commit(self, commit_hash: str, changed_functions: list[str], risk_level: str = "medium"):
        """
        Handle a new commit event.
        - FIRST_RUN: queue it for later delivery
        - ONGOING: send webhook immediately
        """
        event = {
            "commit": commit_hash,
            "changed_functions": changed_functions,
            "risk_level": risk_level,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        with self._state_lock:
            if self.mode == MODE_FIRST_RUN:
                self.commit_queue.append(event)
                self._save()
                print(f"[State] Commit {commit_hash[:8]} queued (FIRST_RUN mode, queue size={len(self.commit_queue)})")
                return

        # ONGOING mode — send webhook immediately
        if WEBHOOK_URL:
            try:
                http_requests.post(WEBHOOK_URL, json=event, timeout=10)
                print(f"[Webhook] Sent commit event {commit_hash[:8]}")
            except Exception as e:
                print(f"[Webhook] Failed to send commit event: {e}")
        else:
            print(f"[State] Commit {commit_hash[:8]} processed (no webhook URL configured)")

    # ───────────────────────────────────────────────────
    # Sync Tracking
    # ───────────────────────────────────────────────────

    def update_last_sync(self, commit_hash: str):
        """Record the last synced commit."""
        with self._state_lock:
            self.last_sync = {
                "commit": commit_hash,
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            self._save()

    # ───────────────────────────────────────────────────
    # Health / Status
    # ───────────────────────────────────────────────────

    def get_health(self) -> dict:
        """Return server health summary."""
        with self._state_lock:
            return {
                "status": "ok",
                "mode": self.mode,
                "total_functions": self.total_functions,
                "queued_commits": len(self.commit_queue),
                "last_sync": self.last_sync,
                "current_job": self.current_job,
                "codebase_path": self.codebase_path,
            }


# ═══════════════════════════════════════════════════════════
# Module-level singleton accessor
# ═══════════════════════════════════════════════════════════

def get_state() -> ServerState:
    """Get the singleton ServerState instance."""
    return ServerState()
