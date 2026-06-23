import os
import time
import atexit
from config import LOCK_PATH

LOCK_TIMEOUT = 120       # seconds — if a lock is older than 120s, it is considered stale
LOCK_POLL_INTERVAL = 2   # check every 2 seconds when waiting

def acquire_lock(caller: str = "unknown") -> bool:
    """
    Try to acquire the lock. Returns True if successful, False if timeout.
    caller: name of the process/caller for logging/debugging (e.g. "incremental_sync", "git_hook")
    """
    start = time.time()
    while True:
        if not os.path.exists(LOCK_PATH):
            break
        # Check if the lock is stale (previous process crashed without releasing)
        try:
            mtime = os.path.getmtime(LOCK_PATH)
            if time.time() - mtime > LOCK_TIMEOUT:
                print(f"[Lock] Stale lock detected (>{LOCK_TIMEOUT}s), removing.")
                os.remove(LOCK_PATH)
                break
        except Exception:
            break
        elapsed = time.time() - start
        if elapsed > LOCK_TIMEOUT:
            print(f"[Lock] Timeout waiting for lock after {LOCK_TIMEOUT}s. Skipping.")
            return False
        print(f"[Lock] Another sync is running. Waiting... ({int(elapsed)}s)")
        time.sleep(LOCK_POLL_INTERVAL)

    # Write lock file with caller info for debugging
    try:
        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        with open(LOCK_PATH, "w", encoding="utf-8") as f:
            f.write(f"{caller}\n{time.strftime('%Y-%m-%dT%H:%M:%S')}\n{os.getpid()}")
    except Exception as e:
        print(f"[Lock] Warning: Could not create lock file: {e}")
        return False

    # Ensure lock is released even if process crashes
    atexit.register(release_lock)
    return True


def release_lock():
    """Release the lock. Safe to call multiple times."""
    try:
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
    except Exception:
        pass


def is_locked() -> bool:
    """Check if lock exists and is not stale."""
    if not os.path.exists(LOCK_PATH):
        return False
    try:
        mtime = os.path.getmtime(LOCK_PATH)
        return time.time() - mtime <= LOCK_TIMEOUT
    except Exception:
        return False
