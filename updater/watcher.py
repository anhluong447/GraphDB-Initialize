import sys
import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CODEBASE_PATH, SUPPORTED_LANGUAGES


class CodeChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.pending = set()
        self.last_process = 0

    def on_modified(self, event):
        if event.is_directory:
            return
        from pathlib import Path
        if Path(event.src_path).suffix in SUPPORTED_LANGUAGES:
            self.pending.add(event.src_path)
            self._debounced_process()

    def _debounced_process(self):
        now = time.time()
        if now - self.last_process > 5:  # 5 second debounce
            self.last_process = now
            files = list(self.pending)
            self.pending.clear()
            self._reindex_files(files)

    def _reindex_files(self, files: list[str]):
        print(f"[Watcher] Re-indexing {len(files)} changed files...")
        from parsers.ast_parser import parse_file
        from graph.builder import build_file_nodes
        from embeddings.chroma_client import embed_all_nodes

        parsed = [parse_file(f) for f in files]
        parsed = [p for p in parsed if p is not None]
        if parsed:
            build_file_nodes(parsed)
            embed_all_nodes()
            print(f"[Watcher] Re-indexed: {[p['file'] for p in parsed]}")


def start_watcher():
    handler = CodeChangeHandler()
    observer = Observer()
    observer.schedule(handler, CODEBASE_PATH, recursive=True)
    observer.start()
    print(f"[Watcher] Watching {CODEBASE_PATH} for changes...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    start_watcher()
