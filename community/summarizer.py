import openai
import re
from graph.neo4j_client import get_client

_client_ai = None

def _get_client_ai():
    global _client_ai
    if _client_ai is None:
        import config
        _client_ai = openai.OpenAI(
            api_key=config.OPENROUTER_API_KEY,
            base_url=config.OPENROUTER_BASE_URL,
        )
    return _client_ai


def get_community_members(community_id: int) -> list[dict]:
    """Get all nodes belonging to a community."""
    client = get_client()
    result = client.run("""
        MATCH (n) WHERE n.community_id = $cid AND n.name IS NOT NULL
        RETURN labels(n) as labels, n.name as name, n.description as description
        LIMIT 50
    """, {"cid": community_id})

    return [{"type": r["labels"][0], "name": r["name"], "description": r["description"]} for r in result]


def summarize_community(community_id: int) -> str:
    """Use LLM to create a brief summary (~200 tokens) for a community."""
    members = get_community_members(community_id)
    if not members:
        return ""

    members_text = "\n".join([f"- [{m['type']}] {m['name']}: {m['description'] or ''}" for m in members[:30]])

    prompt = f"""You are summarizing a cluster of related code elements for a developer knowledge graph.

Community members:
{members_text}

Write a 2-3 sentence summary of this community that answers:
1. What is the main purpose/theme of this group?
2. What are the key elements?
3. Any notable risks, tasks, or decisions?

Keep it under 200 words. Be specific, not generic."""

    import config
    response = _get_client_ai().chat.completions.create(
        model=config.LLM_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()


def infer_community_name(community_id: int, summary: str) -> str:
    """Use LLM to give a short name to a community."""
    import config
    response = _get_client_ai().chat.completions.create(
        model=config.LLM_MODEL,
        max_tokens=20,
        messages=[{"role": "user", "content": f"Give a 2-4 word name for this code community. Return ONLY the name:\n\n{summary}"}]
    )
    return response.choices[0].message.content.strip()


def _load_community_snapshot() -> dict | None:
    import json, os
    from config import GRAPHRAG_DATA_DIR
    path = os.path.join(GRAPHRAG_DATA_DIR, "community_snapshot_old.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


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
        cid = str(r["cid"])
        name = r["name"] or ""
        file = r["file"] or ""
        key = f"{name}::{file}"
        communities.setdefault(cid, []).append(key)
    
    # Sort member lists for stable comparison
    for cid in communities:
        communities[cid].sort()
        
    return {"communities": communities}


def _diff_communities(old_snapshot: dict, new_snapshot: dict) -> list[int]:
    """Return community IDs that changed or are brand new."""
    old_sets = {frozenset(v) for v in old_snapshot.get("communities", {}).values()}
    to_summarize = []
    for cid, members in new_snapshot.get("communities", {}).items():
        if frozenset(members) not in old_sets:
            to_summarize.append(int(cid))
    return to_summarize


def _get_old_community_summaries() -> dict:
    """Query Neo4j for all existing Community nodes: id -> {name, summary}"""
    client = get_client()
    rows = client.run("MATCH (c:Community) RETURN c.id as cid, c.name as name, c.summary as summary")
    return {r["cid"]: {"name": r["name"], "summary": r["summary"]} for r in rows}


def summarize_all_communities():
    """Summarize all communities and save to Neo4j and ChromaDB."""
    client = get_client()

    import chromadb
    from config import CHROMA_PATH
    from embeddings.embedder import embed_texts

    # 1. Load old summaries and snapshots
    old_summaries = _get_old_community_summaries()
    old_snapshot = _load_community_snapshot()
    new_snapshot = _build_current_snapshot()

    # 2. Map old member sets to their name/summary
    set_to_summary = {}
    if old_snapshot and old_summaries:
        for old_cid, members in old_snapshot.get("communities", {}).items():
            try:
                old_cid_int = int(old_cid)
            except ValueError:
                continue
            if old_cid_int in old_summaries:
                members_set = frozenset(members)
                set_to_summary[members_set] = old_summaries[old_cid_int]

    # 3. Clean up existing Community nodes
    client.run("MATCH (c:Community) DETACH DELETE c")

    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        chroma.delete_collection("community_summaries")
    except Exception:
        pass
    comm_collection = chroma.get_or_create_collection("community_summaries")

    # Get list of community IDs
    result = client.run("MATCH (n) WHERE n.community_id IS NOT NULL RETURN DISTINCT n.community_id as cid ORDER BY cid")
    community_ids = [r["cid"] for r in result]

    print(f"[Community] Summarizing {len(community_ids)} communities...")

    llm_count = 0
    auto_count = 0
    reused_count = 0

    batch_ids, batch_docs, batch_metas = [], [], []

    for cid in community_ids:
        members = get_community_members(cid)
        if not members:
            continue

        size = len(members)
        new_members_list = new_snapshot.get("communities", {}).get(str(cid), [])
        new_set = frozenset(new_members_list)

        name = None
        summary = None

        if size < 3:
            # Auto summarization for small communities
            if size == 1:
                name = f"Node: {members[0]['name']}"
                summary = f"Isolated cluster containing element: {members[0]['name']} ({members[0]['type']})."
            else:
                name = f"Pair: {members[0]['name']} & {members[1]['name']}"
                summary = f"Small cluster containing elements: {members[0]['name']} ({members[0]['type']}) and {members[1]['name']} ({members[1]['type']})."
            auto_count += 1
        elif new_set in set_to_summary and set_to_summary[new_set].get("name") and set_to_summary[new_set].get("summary"):
            # Reuse existing summary!
            name = set_to_summary[new_set]["name"]
            summary = set_to_summary[new_set]["summary"]
            reused_count += 1
        else:
            # LLM summarization for significant communities
            members_text = "\n".join([f"- [{m['type']}] {m['name']}: {m['description'] or ''}" for m in members[:30]])
            prompt = f"""You are summarizing a cluster of related code elements for a developer knowledge graph.

Community members:
{members_text}

Task:
1. Write a 2-3 sentence summary of this community that describes its main purpose/theme, key elements, and any notable risks, tasks, or decisions.
2. Provide a short, 2-4 word name for this community.

Return your response in the following format:
NAME: <your 2-4 word name>
SUMMARY: <your 2-3 sentence summary>"""

            try:
                import config
                response = _get_client_ai().chat.completions.create(
                    model=config.LLM_MODEL,
                    max_tokens=350,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.choices[0].message.content.strip()

                # Parse the name and summary
                name = f"Community {cid}"
                summary = ""

                # Extract NAME
                name_match = re.search(r"NAME:\s*(.*)", text, re.IGNORECASE)
                if name_match:
                    name = name_match.group(1).strip()
                    name = name.strip('"\'*` ')

                # Extract SUMMARY
                summary_match = re.search(r"SUMMARY:\s*([\s\S]*)", text, re.IGNORECASE)
                if summary_match:
                    summary = summary_match.group(1).strip()
                else:
                    # Fallback parser
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    summary_lines = [l for l in lines if not l.upper().startswith("NAME:")]
                    summary = " ".join(summary_lines)

                if not summary:
                    summary = text

            except Exception as e:
                name = f"Community {cid}"
                summary = f"Cluster of related code elements including {members[0]['name']}."
            llm_count += 1

        # Create Community node in Neo4j
        client.run("""
            MERGE (c:Community {id: $cid})
            SET c.name = $name, c.summary = $summary
        """, {"cid": cid, "name": name, "summary": summary})

        # Create BELONGS_TO edges
        client.run("""
            MATCH (c:Community {id: $cid})
            MATCH (n) WHERE n.community_id = $cid AND NOT n:Community
            MERGE (n)-[:BELONGS_TO]->(c)
        """, {"cid": cid})

        # Queue for ChromaDB embedding
        batch_ids.append(str(cid))
        batch_docs.append(summary)
        batch_metas.append({"id": cid, "name": name})

        if size < 3:
            print(f"  Community {cid} (Auto): '{name}'")
        elif new_set in set_to_summary and set_to_summary[new_set].get("name") and set_to_summary[new_set].get("summary"):
            print(f"  Community {cid} (Reused): '{name}'")
        else:
            print(f"  Community {cid} (LLM): '{name}'")

    # Embed and upsert in ChromaDB using batches
    if batch_docs:
        print(f"[Chroma] Embedding {len(batch_docs)} community summaries...")
        try:
            all_vectors = []
            for i in range(0, len(batch_docs), 50):
                slice_docs = batch_docs[i:i+50]
                vectors = embed_texts(slice_docs)
                all_vectors.extend(vectors)

            comm_collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas,
                embeddings=all_vectors
            )
            print("[Chroma] All community summaries embedded.")
        except Exception as e:
            print(f"[Chroma] Error embedding community summaries: {e}")

    print(f"[Community] Summarization done. LLM calls: {llm_count}, Reused: {reused_count}, Auto: {auto_count}.")
