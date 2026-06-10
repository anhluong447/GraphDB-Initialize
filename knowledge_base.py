"""
GraphRAG Knowledge Base — Python Interface

Team test gen dùng file này để truy cập graph trực tiếp.
Không cần HTTP, không cần server, không cần port.

Usage:
    from knowledge_base import get_function_context, get_snapshot, get_changes, mark_tested
"""

import json
from graph.neo4j_client import get_client


def get_function_context(function_name: str, file_path: str = None) -> dict:
    """
    Lấy full context của 1 function để gen test.

    Returns:
        {
            "function": { name, file, how_it_works, input_spec, output_spec,
                          edge_cases, test_recommendations, complexity,
                          source_code },
            "community": { id, name, summary },
            "calls_outside": [ {name, file} ],   # functions được gọi
            "called_by":    [ {name, file} ],   # functions gọi vào đây
        }
    """
    client = get_client()

    where_clause = "WHERE f.file = $file" if file_path else "WHERE f.file IS NOT NULL"
    result = client.run(f"""
        MATCH (f:Function {{name: $name}})
        {where_clause}
        OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
        RETURN f, c.id as cid, c.name as cname, c.summary as csummary
        LIMIT 1
    """, {"name": function_name, "file": file_path})

    if not result:
        return {}

    record = result[0]
    func_data = dict(record["f"])

    # Đọc source code từ file thật (dùng start_line/end_line/anchor)
    func_data["source_code"] = client.read_node_code(func_data)

    # Parse JSON fields
    for field in ["test_recommendations", "inputs", "raises", "edge_cases", "annotations"]:
        val = func_data.get(field)
        if isinstance(val, str):
            try:
                func_data[field] = json.loads(val)
            except Exception:
                pass

    community = None
    if record["cid"] is not None:
        community = {
            "id": record["cid"],
            "name": record["cname"],
            "summary": record["csummary"],
        }

    where_clause_f = "AND f.file = $file" if file_path else ""
    calls_outside = client.run(f"""
        MATCH (f:Function {{name: $name}})-[:CALLS]->(callee)
        WHERE callee.name IS NOT NULL {where_clause_f}
        RETURN callee.name as name, callee.file as file
    """, {"name": function_name, "file": file_path})

    called_by = client.run(f"""
        MATCH (caller)-[:CALLS]->(f:Function {{name: $name}})
        WHERE caller.name IS NOT NULL {where_clause_f}
        RETURN caller.name as name, caller.file as file
    """, {"name": function_name, "file": file_path})

    return {
        "function": func_data,
        "community": community,
        "calls_outside": [dict(r) for r in calls_outside],
        "called_by": [dict(r) for r in called_by],
    }


def get_class_context(class_name: str, file_path: str = None) -> dict:
    """
    Lấy full context của 1 class kèm attributes để gen test hoặc hiển thị.
    """
    client = get_client()

    where_clause = "WHERE c.file = $file" if file_path else "WHERE c.file IS NOT NULL"
    result = client.run(f"""
        MATCH (c:Class {{name: $name}})
        {where_clause}
        OPTIONAL MATCH (c)-[:HAS_ATTRIBUTE]->(attr:ClassAttribute)
        WITH c, collect({{
            name: attr.name,
            type: attr.type_hint,
            default: attr.default_value,
            is_field: attr.is_dataclass_field
        }}) AS attributes
        RETURN c, attributes
        LIMIT 1
    """, {"name": class_name, "file": file_path})

    if not result:
        return {}

    record = result[0]
    class_data = dict(record["c"])
    
    raw_attrs = record.get("attributes", [])
    attributes = [a for a in raw_attrs if a.get("name") is not None]
    class_data["attributes"] = attributes

    # Đọc source code từ file thật (dùng start_line/end_line/anchor)
    class_data["source_code"] = client.read_node_code(class_data)

    return class_data


def get_snapshot() -> dict:
    """
    Lấy toàn bộ functions hiện tại, nhóm theo community, kèm priority score.
    Dùng cho first run — biết toàn bộ codebase cần gen test gì.

    priority_score = complexity*0.3 + in_degree*0.4 + commit_count*0.3 + entry_point_boost
    """
    client = get_client()

    functions = client.run("""
        MATCH (f:Function)
        WHERE f.file IS NOT NULL AND f.name IS NOT NULL
        OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
        WITH f, c,
             size([(caller:Function)-[:CALLS]->(f) | caller]) as in_degree,
             size([(commit:Commit)-[:CHANGED]->(f) | commit]) as commit_count
        RETURN f.name as name,
               f.file as file,
               f.class_name as class_name,
               coalesce(f.complexity, 1) as complexity,
               in_degree,
               commit_count,
               coalesce(f.has_test, false) as has_test,
               c.id as community_id,
               c.name as community_name,
               c.summary as community_summary
        ORDER BY community_id, name
    """)

    communities_map = {}
    uncategorized = {"id": -1, "name": "Uncategorized", "summary": "", "functions": []}

    for r in functions:
        complexity = r["complexity"] or 1
        in_degree = r["in_degree"] or 0
        commit_count = r["commit_count"] or 0
        priority_score = round(complexity * 0.3 + in_degree * 0.4 + commit_count * 0.3, 1)

        func_data = {
            "name": r["name"],
            "file": r["file"],
            "class_name": r["class_name"],
            "complexity": complexity,
            "priority_score": priority_score,
            "has_test": r["has_test"] or False,
        }

        cid = r["community_id"]
        if cid is not None:
            if cid not in communities_map:
                communities_map[cid] = {
                    "id": cid,
                    "name": r["community_name"] or f"Community {cid}",
                    "summary": r["community_summary"] or "",
                    "functions": [],
                }
            communities_map[cid]["functions"].append(func_data)
        else:
            uncategorized["functions"].append(func_data)

    for comm in communities_map.values():
        comm["functions"].sort(key=lambda f: f["priority_score"], reverse=True)

    communities_list = sorted(communities_map.values(), key=lambda c: c["id"])
    if uncategorized["functions"]:
        communities_list.append(uncategorized)

    return {
        "total": sum(len(c["functions"]) for c in communities_list),
        "communities": communities_list,
    }


def get_changes(commit_hash: str) -> dict:
    """
    Lấy danh sách functions bị thay đổi trong 1 commit.
    Dùng cho ongoing mode sau mỗi git push.

    Returns:
        {
            "commit": "abc123",
            "changed_functions": [ {name, file, complexity, has_test} ],
            "affected_services": [ {id, name} ],
            "risk_level": "low|medium|high"
        }
    """
    client = get_client()

    result = client.run("""
        MATCH (c:Commit)-[:CHANGED]->(f:Function)
        WHERE c.hash STARTS WITH $hash
        RETURN f.name as name,
               f.file as file,
               coalesce(f.complexity, 1) as complexity,
               coalesce(f.has_test, false) as has_test
    """, {"hash": commit_hash})

    changed = [dict(r) for r in result]

    max_complexity = max((f["complexity"] for f in changed), default=1)
    risk_level = "high" if max_complexity >= 10 else "medium" if max_complexity >= 5 else "low"

    affected = []
    if changed:
        names = [f["name"] for f in changed]
        comm_result = client.run("""
            MATCH (f:Function)-[:BELONGS_TO]->(c:Community)
            WHERE f.name IN $names
            RETURN DISTINCT c.id as id, c.name as name
        """, {"names": names})
        affected = [dict(r) for r in comm_result]

    return {
        "commit": commit_hash,
        "changed_functions": changed,
        "affected_services": affected,
        "risk_level": risk_level,
    }


def mark_tested(function_name: str, file: str = None) -> bool:
    """
    Đánh dấu function đã có test (has_test = true).
    Gọi sau khi gen test xong và test pass.

    Returns: True nếu thành công, False nếu không tìm thấy function.
    """
    client = get_client()

    if file:
        result = client.run("""
            MATCH (f:Function {name: $name, file: $file})
            SET f.has_test = true
            RETURN f.name
        """, {"name": function_name, "file": file})
    else:
        result = client.run("""
            MATCH (f:Function {name: $name})
            SET f.has_test = true
            RETURN f.name
        """, {"name": function_name})

    return len(result) > 0


def search(query_text: str, top_k: int = 10) -> list[dict]:
    """
    Semantic search trong graph.
    Tìm functions/nodes liên quan đến query bằng vector similarity.

    Returns: list of { name, file, type, score, description }
    """
    from embeddings.chroma_client import semantic_search
    return semantic_search(query_text, top_k=top_k)


def run_init(codebase_path: str = None):
    """
    Chạy full initialization pipeline.
    Nếu không truyền path, dùng CODEBASE_PATH trong .env.
    """
    if codebase_path:
        import os
        os.environ["CODEBASE_PATH"] = codebase_path
    from initialize_graph import run_full_init
    run_full_init()


def run_sync():
    """Chạy incremental sync dựa trên git diff."""
    from initialize_graph import run_incremental_sync
    run_incremental_sync()
