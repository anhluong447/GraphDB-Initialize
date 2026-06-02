"""
Scratch script: Upgrade existing database nodes with new rich testing metadata.
Bypasses the expensive general semantic extraction (Step 5) to save API costs.
Run: python scratch/upgrade_db_metadata.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CODEBASE_PATH
from parsers.ast_parser import parse_codebase
from graph.builder import build_file_nodes
from extractors.testing_enricher import enrich_all_functions


def main():
    print("=" * 60)
    print("GraphRAG DB Metadata Upgrader")
    print("=" * 60)
    print(f"Target codebase: {CODEBASE_PATH}")

    # 1. Parse codebase statically (100% Free - Local CPU)
    print("\n[1/2] Re-parsing codebase and updating static properties...")
    parsed_files = parse_codebase(CODEBASE_PATH)
    
    print("\nWriting new properties (inputs, output, raises, complexity, docstring) to Neo4j...")
    build_file_nodes(parsed_files)
    print("Static properties successfully merged into existing nodes!")

    # 2. AI Testing Enrichment
    print("\n[2/2] Running AI testing enricher to generate mock blueprints...")
    enrich_all_functions()

    print("\n" + "=" * 60)
    print("✅ Database upgrade completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
