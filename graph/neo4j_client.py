import json
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    def run(self, query: str, params: dict = None):
        with self.driver.session() as session:
            return list(session.run(query, params or {}))

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


# Singleton
_client = None


def get_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
