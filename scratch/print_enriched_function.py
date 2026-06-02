"""
Scratch script: Verify and print details of an AI-enriched function in the Neo4j database.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.neo4j_client import get_client


def main():
    client = get_client()
    
    # Find functions that have been enriched
    result = client.run("""
        MATCH (n:Function)
        WHERE n.how_it_works IS NOT NULL
        RETURN n.name as name, n.file as file, n.how_it_works as how_it_works,
               n.input_spec as input_spec, n.output_spec as output_spec,
               n.edge_cases as edge_cases, n.test_recommendations as test_recommendations,
               n.complexity as complexity, n.raises as raises
        LIMIT 3
    """)
    
    records = [dict(r) for r in result]
    
    if not records:
        print("❌ No enriched functions found in the database yet!")
        return

    print("=" * 80)
    print(f"Found {len(records)} enriched functions. Displaying details for the first one:")
    print("=" * 80)
    
    f = records[0]
    print(f"Name:         {f['name']}")
    print(f"File:         {f['file']}")
    print(f"Complexity:   {f['complexity']}")
    print(f"Raises:       {f['raises']}")
    print("-" * 80)
    print(f"How It Works:\n{f['how_it_works']}")
    print("-" * 80)
    print(f"Input Spec:\n{f['input_spec']}")
    print("-" * 80)
    print(f"Output Spec:\n{f['output_spec']}")
    print("-" * 80)
    print("Edge Cases:")
    try:
        import json
        cases = json.loads(f['edge_cases'])
        for c in cases:
            print(f"  - {c}")
    except Exception:
        print(f"  {f['edge_cases']}")
        
    print("-" * 80)
    print("Test Recommendations:")
    try:
        recs = json.loads(f['test_recommendations'])
        for r in recs:
            print(f"  - {r}")
    except Exception:
        print(f"  {f['test_recommendations']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
