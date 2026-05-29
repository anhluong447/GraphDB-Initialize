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


# Singleton
_client = None


def get_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
