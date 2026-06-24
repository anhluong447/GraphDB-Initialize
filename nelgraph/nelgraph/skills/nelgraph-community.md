---
name: nelgraph-community
description: >
  Manage, inspect, and update community clusters in the nelgraph knowledge graph.
  Use this skill when working with community detection, snapshot diffing, or
  diagnosing stale/missing community summaries. Implements the membership snapshot
  diff approach — only re-summarizes communities that actually changed.
---

# nelgraph — Community Management Skill

## What is a community?

After parsing a codebase, nelgraph clusters all nodes (Function, Class, Module)
into communities using the Leiden algorithm. Each community gets an LLM-generated
name and summary describing its purpose (e.g. "Auth & Session Management",
"Order Processing Pipeline").

Communities are stored in:
- **Neo4j**: `:Community` nodes with `id`, `name`, `summary` properties
- **ChromaDB**: `community_summaries` collection (embedded for semantic search)
- **Snapshot file**: `<GRAPHRAG_DATA_DIR>/community_snapshot.json` (for diff)

---

## Snapshot Diff — How It Works

The snapshot file stores the membership of each community after every cluster run:

```json
{
  "generated_at": "2026-06-23T10:00:00",
  "communities": {
    "0": ["login::src/auth.py", "logout::src/auth.py", "validate_token::src/auth.py"],
    "1": ["create_order::src/orders.py", "cancel_order::src/orders.py"]
  }
}
```

Key format per member: `"<function_name>::<file_path>"`

On next sync, the diff compares by **member set** (not by ID, since Leiden IDs
are unstable between runs):

```python
old_sets = {frozenset(members) for members in old_snapshot["communities"].values()}

to_summarize = []
for cid, members in new_snapshot["communities"].items():
    if frozenset(members) not in old_sets:
        to_summarize.append(cid)   # changed or brand new → needs LLM
```

Communities whose member set is identical are skipped — their existing
`:Community` node in Neo4j is kept as-is.

---

## Files to Modify (from refactor plan)

### `community/detector.py`

After saving `community_id` to all Neo4j nodes, add snapshot save:

```python
def _save_community_snapshot(result: dict, client):
    """
    result: {neo4j_node_id: community_id}
    Builds {community_id: ["name::file", ...]} and saves to JSON.
    """
    import json, time
    from config import GRAPHRAG_DATA_DIR
    import os

    # Query name + file for each node in result
    community_members = {}  # {community_id: [member_key, ...]}
    for node_id, cid in result.items():
        rows = client.run(
            "MATCH (n) WHERE elementId(n) = $id RETURN n.name as name, n.file as file",
            {"id": node_id}
        )
        if rows:
            name = rows[0]["name"] or ""
            file = rows[0]["file"] or ""
            key = f"{name}::{file}"
            community_members.setdefault(str(cid), []).append(key)

    snapshot = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "communities": community_members,
    }

    path = os.path.join(GRAPHRAG_DATA_DIR, "community_snapshot.json")
    os.makedirs(GRAPHRAG_DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    print(f"[Community] Snapshot saved: {len(community_members)} communities → {path}")
```

Call at the end of `detect_communities()`:
```python
_save_community_snapshot(result, client)
return result
```

### `community/summarizer.py`

Add snapshot load + diff helpers:

```python
def _load_community_snapshot() -> dict | None:
    import json, os
    from config import GRAPHRAG_DATA_DIR
    path = os.path.join(GRAPHRAG_DATA_DIR, "community_snapshot.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _build_current_snapshot() -> dict:
    """Query Neo4j for current community membership (post-cluster)."""
    client = get_client()
    rows = client.run("""
        MATCH (n)
        WHERE n.community_id IS NOT NULL AND n.name IS NOT NULL AND NOT n:Community
        RETURN n.community_id as cid, n.name as name, n.file as file
    """)
    communities = {}
    for r in rows:
        key = f"{r['name']}::{r['file'] or ''}"
        communities.setdefault(str(r["cid"]), []).append(key)
    return {"communities": communities}

def _diff_communities(old_snapshot: dict, new_snapshot: dict) -> list[int]:
    """Return community IDs that changed or are brand new."""
    old_sets = {frozenset(v) for v in old_snapshot["communities"].values()}
    to_summarize = []
    for cid, members in new_snapshot["communities"].items():
        if frozenset(members) not in old_sets:
            to_summarize.append(int(cid))
    return to_summarize
```

Modify `summarize_all_communities()` to use diff:

```python
def summarize_all_communities():
    client = get_client()

    # Clean up stale :Community nodes before rebuild
    client.run("MATCH (c:Community) WHERE NOT (()-[:BELONGS_TO]->(c)) DETACH DELETE c")

    # Determine which communities need LLM summarization
    old_snapshot = _load_community_snapshot()
    new_snapshot = _build_current_snapshot()

    if old_snapshot is None:
        print("[Community] No snapshot found — summarizing all communities.")
        result = client.run(
            "MATCH (n) WHERE n.community_id IS NOT NULL RETURN DISTINCT n.community_id as cid ORDER BY cid"
        )
        to_summarize = set(r["cid"] for r in result)
    else:
        changed = _diff_communities(old_snapshot, new_snapshot)
        print(f"[Community] Snapshot diff: {len(changed)} communities changed or new.")
        to_summarize = set(changed)

    # ... rest of existing loop, but add condition:
    for cid in community_ids:
        if cid not in to_summarize:
            print(f"  Community {cid}: unchanged, skipping LLM.")
            continue
        # ... existing LLM summarize logic
```

---

## CLI Commands

```bash
# Run community detection + summarization manually
nelgraph --community

# Check how many communities exist
python -c "
import nelgraph
snap = nelgraph.get_snapshot()
print(f'{len(snap[\"communities\"])} communities, {snap[\"total\"]} total nodes')
for c in snap['communities'][:5]:
    print(f'  [{c[\"id\"]}] {c[\"name\"]}: {len(c[\"functions\"])} functions')
"
```

---

## Diagnosing Community Issues

### Communities not updating after sync
Check if snapshot file exists and is recent:
```python
import json, os
from config import GRAPHRAG_DATA_DIR
path = os.path.join(GRAPHRAG_DATA_DIR, "community_snapshot.json")
with open(path) as f:
    snap = json.load(f)
print(snap["generated_at"])
print(f"{len(snap['communities'])} communities in snapshot")
```

### Force re-summarize all communities
Delete the snapshot file to force full re-run:
```python
import os
from config import GRAPHRAG_DATA_DIR
os.remove(os.path.join(GRAPHRAG_DATA_DIR, "community_snapshot.json"))
# Then run: nelgraph --community
```

### Orphan Community nodes in Neo4j
```cypher
MATCH (c:Community) WHERE NOT (()-[:BELONGS_TO]->(c))
RETURN c.id, c.name
```
These are cleaned up automatically at the start of `summarize_all_communities()`.

---

## Rules

1. **Never delete the snapshot manually** unless you want to force full re-summarize.
2. **Compare by member frozenset, not by ID** — Leiden IDs are unstable.
3. **New community = frozenset not in old_sets** — will always be caught by diff.
4. **Cleanup stale :Community nodes before rebuild** — run the orphan cleanup Cypher first.
5. **Small communities (< 3 members) skip LLM** — handled by auto-summarize fallback in existing code.