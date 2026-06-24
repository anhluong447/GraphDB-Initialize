import json
from neo4j import GraphDatabase
from nelgraph.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        global _client
        try:
            self.driver.close()
        except Exception:
            pass
        _client = None

    def run(self, query: str, params: dict = None, retries=10, delay=3):
        import time
        from neo4j.exceptions import ServiceUnavailable, SessionError
        last_err = None
        for attempt in range(retries):
            try:
                with self.driver.session() as session:
                    return list(session.run(query, params or {}))
            except (ServiceUnavailable, SessionError) as e:
                last_err = e
                time.sleep(delay)
        raise last_err

    def create_indexes(self):
        """Create indexes for faster queries."""
        indexes = [
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Function) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Class) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:File) ON (n.path)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Concept) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Feature) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Task) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Community) ON (n.id)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Module) ON (n.name)",
        ]
        for idx in indexes:
            try:
                self.run(idx)
            except Exception as e:
                print(f"[Neo4j] Index warning: {e}")
        print("[Neo4j] Indexes created.")

    def clear_all(self):
        """Delete entire graph (used for rebuild)."""
        self.run("MATCH (n) DETACH DELETE n")
        print("[Neo4j] Graph cleared.")

    def get_functions_for_testing(self, file_path=None):
        """Return enriched Function nodes with parsed test_recommendations."""
        where_clause = "AND f.file = $file_path" if file_path else ""
        query = f"""
            MATCH (f:Function)
            WHERE f.how_it_works IS NOT NULL
            {where_clause}
            RETURN f
        """
        params = {"file_path": file_path} if file_path else {}
        results = self.run(query, params)
        functions = []
        for r in results:
            fn = dict(r["f"])
            try:
                recs = json.loads(fn.get("test_recommendations", "[]"))
                fn["test_recommendations"] = recs if isinstance(recs, list) else [recs]
            except Exception:
                fn["test_recommendations"] = []
            functions.append(fn)
        return functions

    def read_node_code(self, node: dict) -> str:
        """
        Read source code of a node.
        Priority:
          1. raw_code stored directly in Neo4j (works for remote clients)
          2. Read from local file system using start_line/end_line (fallback)
        
        Args:
            node: dict containing file, start_line, end_line, anchor, name, raw_code
        Returns:
            Source code of that node
        """
        import os

        # Priority 1: use raw_code stored in Neo4j (portable, works for remote clients)
        stored_raw = node.get("raw_code", "")
        if stored_raw and stored_raw.strip():
            return stored_raw

        # Priority 2: fallback to reading from local file system
        file_path = node.get("file")
        start_line = node.get("start_line")
        end_line = node.get("end_line")

        if not file_path:
            return ""

        # Try to resolve relative path if not absolute
        if not os.path.isabs(file_path):
            from nelgraph.config import CODEBASE_PATH
            alt_path = os.path.abspath(os.path.join(CODEBASE_PATH, file_path)).replace("\\", "/")
            if os.path.exists(alt_path):
                file_path = alt_path

        if not os.path.exists(file_path):
            return ""

        if start_line is None or end_line is None:
            return ""

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return ""


        # Check if anchor matches
        anchor = node.get("anchor", "")
        if not anchor:
            return "".join(lines[start_line - 1 : end_line])

        actual_line = lines[start_line - 1].strip() if 1 <= start_line <= len(lines) else ""
        
        if actual_line == anchor:
            # Line coordinates are correct, read normally
            return "".join(lines[start_line - 1 : end_line])

        # Anchor does not match — coordinates are stale, let's find the anchor
        new_start = None
        for i, line in enumerate(lines):
            if line.strip() == anchor:
                new_start = i + 1  # 1-indexed
                break

        if new_start is None:
            # Anchor not found (e.g. function deleted or renamed)
            return ""

        # Calculate new end_line using the original offset
        offset = end_line - start_line
        new_end = new_start + offset

        # Update Neo4j with the correct coordinates
        self.run(
            """
            MATCH (n {name: $name, file: $file})
            SET n.start_line = $new_start, n.end_line = $new_end
            """,
            {
                "name": node.get("name"),
                "file": node.get("file"),
                "new_start": new_start,
                "new_end": new_end
            }
        )

        return "".join(lines[new_start - 1 : new_end])


# Singleton
_client = None


def get_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
