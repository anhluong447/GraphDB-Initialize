import sys
import os
import json

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from query.engine import query

print("Testing hybrid query engine for: 'admin creation'")
res = query("admin creation")

print("\n--- Summary of Retrieved Context ---")
print(res["summary"])

print("\n--- Top Relevant Nodes ---")
for i, n in enumerate(res["relevant_nodes"][:3]):
    meta = n["metadata"]
    print(f"{i+1}. [{meta.get('type')}] {meta.get('name')} in {meta.get('file')}")
