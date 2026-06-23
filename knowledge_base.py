"""
GraphRAG Knowledge Base — Python Interface

Team test gen dùng file này để truy cập graph trực tiếp.
Không cần HTTP, không cần server, không cần port.

Usage:
    from knowledge_base import get_function_context, get_snapshot, get_changes, mark_tested
"""

import json
from graph.neo4j_client import get_client

_auto_sync_checked = False

def _assert_configured():
    import config
    if not config.CODEBASE_PATH or config.CODEBASE_PATH == "/path/to/your/codebase":
        raise RuntimeError(
            "[nelgraph] Chưa configure. Gọi nelgraph.configure() trước:\n"
            "  import nelgraph\n"
            "  nelgraph.configure(\n"
            "      codebase_path='/path/to/project',\n"
            "      openrouter_api_key='sk-or-...'\n"
            "  )"
        )

def _check_and_auto_sync():
    """
    Tự động chạy sync ngầm một lần ở đầu phiên làm việc nếu phát hiện codebase có thay đổi (git status/diff).
    """
    global _auto_sync_checked
    if _auto_sync_checked:
        return
    _auto_sync_checked = True

    try:
        import os
        import config
        codebase_path = getattr(config, "CODEBASE_PATH", None)
        if not codebase_path or not os.path.exists(codebase_path):
            return

        import git
        try:
            repo = git.Repo(codebase_path)
        except Exception:
            # Not a git repo, skip auto-sync
            return

        # Load last sync commit
        from core.init_pipeline import _load_sync_state
        state = _load_sync_state()
        if not state:
            return  # Not initialized

        last_sync_commit = state.get("last_synced_commit")
        current_head = repo.head.commit.hexsha

        has_changes = False
        if last_sync_commit != current_head:
            has_changes = True
        elif repo.is_dirty(untracked_files=True):
            has_changes = True

        if has_changes:
            print("\n[AutoSync] Changes detected in codebase. Running incremental sync...")
            from initialize_graph import run_incremental_sync
            run_incremental_sync()
            print("[AutoSync] Sync complete.\n")
    except Exception:
        pass


def get_function_context(function_name: str, class_name: str = None, file: str = None) -> dict:
    """
    Lấy full context của 1 function để gen test.
    Có hỗ trợ lọc theo class_name và file path nếu có sự trùng lặp tên function.

    Returns:
        {
            "function": { name, file, how_it_works, input_spec, output_spec,
                          edge_cases, test_recommendations, complexity,
                          source_code, class_name },
            "community": { id, name, summary },
            "calls_outside": [ {name, file} ],   # functions được gọi
            "called_by":    [ {name, file} ],   # functions gọi vào đây
        }
    """
    _assert_configured()
    _check_and_auto_sync()
    client = get_client()

    result = client.run("""
        MATCH (f:Function {name: $name})
        WHERE f.file IS NOT NULL
          AND ($class_name IS NULL OR f.class_name = $class_name)
          AND ($file IS NULL OR f.file = $file OR f.file ENDS WITH $file)
        OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
        RETURN f, c.id as cid, c.name as cname, c.summary as csummary
        LIMIT 1
    """, {"name": function_name, "class_name": class_name, "file": file})

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

    element_id = record["f"].element_id

    calls_outside = client.run("""
        MATCH (f) WHERE elementId(f) = $element_id
        MATCH (f)-[:CALLS]->(callee)
        WHERE callee.name IS NOT NULL
        RETURN callee.name as name, callee.file as file
    """, {"element_id": element_id})

    called_by = client.run("""
        MATCH (caller)-[:CALLS]->(f)
        WHERE elementId(f) = $element_id AND caller.name IS NOT NULL
        RETURN caller.name as name, caller.file as file
    """, {"element_id": element_id})

    return {
        "function": func_data,
        "community": community,
        "calls_outside": [dict(r) for r in calls_outside],
        "called_by": [dict(r) for r in called_by],
    }


def get_snapshot(exclude_tests: bool = True) -> dict:
    """
    Lấy toàn bộ functions hiện tại, nhóm theo community, kèm priority score.
    Dùng cho first run — biết toàn bộ codebase cần gen test gì.

    priority_score = complexity*0.3 + in_degree*0.4 + commit_count*0.3
    """
    _assert_configured()
    _check_and_auto_sync()
    client = get_client()

    functions = client.run("""
        MATCH (f:Function)
        WHERE f.file IS NOT NULL AND f.name IS NOT NULL
          AND ($exclude_tests = false OR NOT f:TestFunction)
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
    """, {"exclude_tests": exclude_tests})

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
    _assert_configured()
    _check_and_auto_sync()
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


def get_class_context(class_name: str) -> dict:
    """
    Lấy thông tin của một Class: các phương thức, docstring, class cha/con, và source code.
    """
    _assert_configured()
    _check_and_auto_sync()
    client = get_client()

    result = client.run("""
        MATCH (c:Class {name: $name})
        RETURN c
        LIMIT 1
    """, {"name": class_name})

    if not result:
        return {}

    record = result[0]
    class_data = dict(record["c"])

    # Đọc source code của class
    class_data["source_code"] = client.read_node_code(class_data)

    # Parse superclasses
    if "superclasses" in class_data and isinstance(class_data["superclasses"], str):
        try:
            class_data["superclasses"] = json.loads(class_data["superclasses"])
        except Exception:
            pass

    # Lấy danh sách methods
    methods_result = client.run("""
        MATCH (f:Function {class_name: $class_name, file: $file})
        RETURN f.name as name, f.start_line as start_line, f.end_line as end_line, f.complexity as complexity, f.docstring as docstring
        ORDER BY start_line
    """, {"class_name": class_name, "file": class_data["file"]})

    methods = [dict(r) for r in methods_result]

    # Lấy class cha
    parents_result = client.run("""
        MATCH (c:Class {name: $name})-[:INHERITS_FROM]->(parent)
        RETURN parent.name as name, parent.file as file
    """, {"name": class_name})
    parents = [dict(r) for r in parents_result]

    # Lấy class con
    children_result = client.run("""
        MATCH (child)-[:INHERITS_FROM]->(c:Class {name: $name})
        RETURN child.name as name, child.file as file
    """, {"name": class_name})
    children = [dict(r) for r in children_result]

    return {
        "class": class_data,
        "methods": methods,
        "parent_classes": parents,
        "child_classes": children,
    }


def dump_context_to_file(name: str, path: str, format: str = "markdown") -> bool:
    """
    Xuất thông tin của function hoặc class ra file Markdown hoặc JSON.
    Hữu ích cho các agent chạy trên Windows để tránh lỗi encoding CP1252 khi print ra console.
    """
    _assert_configured()
    # Try class first, then function
    data = get_class_context(name)
    is_class = True

    if not data:
        data = get_function_context(name)
        if not data:
            return False
        is_class = False

    try:
        import os
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        if format.lower() == "json":
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True

        # Format as Markdown
        md = []
        if not is_class:
            func = data["function"]
            md.append(f"# Function: `{func.get('name')}`")
            md.append(f"- **File**: `{func.get('file')}`")
            md.append(f"- **Class**: `{func.get('class_name') or 'N/A'}`")
            md.append(f"- **Complexity**: `{func.get('complexity')}`")
            md.append(f"- **Async**: `{func.get('is_async')}`")
            md.append(f"- **Visibility**: `{func.get('visibility')}`")
            md.append("")

            if func.get("docstring"):
                md.append("## Docstring")
                md.append(f"> {func.get('docstring')}")
                md.append("")

            if func.get("inputs"):
                try:
                    inputs = json.loads(func["inputs"]) if isinstance(func["inputs"], str) else func["inputs"]
                except Exception:
                    inputs = func["inputs"]
                if isinstance(inputs, list):
                    md.append("## Parameters")
                    for p in inputs:
                        default_part = f" = {p['default']}" if "default" in p else ""
                        type_part = f": {p['type']}" if "type" in p else ""
                        md.append(f"- `{p['name']}{type_part}{default_part}`")
                    md.append("")

            if func.get("output"):
                md.append(f"## Return Type: `{func.get('output')}`")
                md.append("")

            if func.get("raises"):
                try:
                    raises = json.loads(func["raises"]) if isinstance(func["raises"], str) else func["raises"]
                except Exception:
                    raises = func["raises"]
                if isinstance(raises, list):
                    md.append("## Raises")
                    for r in raises:
                        md.append(f"- `{r}`")
                    md.append("")

            if func.get("test_recommendations"):
                md.append("## Test Recommendations")
                recs = func.get("test_recommendations")
                if isinstance(recs, list):
                    for r in recs:
                        md.append(f"- {r}")
                elif isinstance(recs, dict):
                    for k, v in recs.items():
                        md.append(f"### {k}")
                        if isinstance(v, list):
                            for item in v:
                                md.append(f"- {item}")
                        else:
                            md.append(str(v))
                md.append("")

            if data.get("calls_outside"):
                md.append("## Calls Outside")
                for c in data["calls_outside"]:
                    md.append(f"- Calls `{c['name']}` in `{c['file']}`")
                md.append("")

            if data.get("called_by"):
                md.append("## Called By")
                for c in data["called_by"]:
                    md.append(f"- Called by `{c['name']}` in `{c['file']}`")
                md.append("")

            if func.get("source_code"):
                md.append("## Source Code")
                md.append("```python")
                md.append(func.get("source_code"))
                md.append("```")
        else:
            cls = data["class"]
            md.append(f"# Class: `{cls.get('name')}`")
            md.append(f"- **File**: `{cls.get('file')}`")
            md.append("")

            if cls.get("docstring"):
                md.append("## Docstring")
                md.append(f"> {cls.get('docstring')}")
                md.append("")

            if data.get("parent_classes"):
                md.append("## Parent Classes")
                for p in data["parent_classes"]:
                    md.append(f"- `{p['name']}` (in `{p['file']}`)")
                md.append("")

            if data.get("child_classes"):
                md.append("## Child Classes")
                for c in data["child_classes"]:
                    md.append(f"- `{c['name']}` (in `{c['file']}`)")
                md.append("")

            if data.get("methods"):
                md.append("## Methods")
                for m in data["methods"]:
                    md.append(f"- `{m['name']}` (lines {m['start_line']}-{m['end_line']}, Complexity: {m['complexity']})")
                    if m.get("docstring"):
                        md.append(f"  > *{m['docstring'].strip()}*")
                md.append("")

            if cls.get("source_code"):
                md.append("## Source Code")
                md.append("```python")
                md.append(cls.get("source_code"))
                md.append("```")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        return True
    except Exception:
        return False


def mark_tested(function_name: str, file: str = None) -> bool:
    """
    Đánh dấu function đã có test (has_test = true và tested = true).
    Gọi sau khi gen test xong và test pass.

    Returns: True nếu thành công, False nếu không tìm thấy function.
    """
    _assert_configured()
    client = get_client()

    if file:
        result = client.run("""
            MATCH (f:Function)
            WHERE f.name = $name AND f.file = $file
            SET f.tested = true, f.has_test = true
            RETURN f.name
        """, {"name": function_name, "file": file})
    else:
        result = client.run("""
            MATCH (f:Function)
            WHERE f.name = $name
            SET f.tested = true, f.has_test = true
            RETURN f.name
        """, {"name": function_name})

    if not result:
        print(f"[Warning] mark_tested: function '{function_name}' not found in graph")
        return False
    return True


def search(query_text: str, top_k: int = 10, exclude_tests: bool = True) -> list[dict]:
    """
    Semantic search trong graph.
    Tìm functions/nodes liên quan đến query bằng vector similarity.

    Returns: list of { name, file, type, score, description }
    """
    _assert_configured()
    _check_and_auto_sync()
    from embeddings.chroma_client import semantic_search
    return semantic_search(query_text, top_k=top_k, exclude_tests=exclude_tests)


def run_init(codebase_path: str = None):
    """
    Chạy full initialization pipeline.
    Nếu không truyền path, dùng CODEBASE_PATH trong .env.
    """
    _assert_configured()
    if codebase_path:
        import os
        os.environ["CODEBASE_PATH"] = codebase_path
    from initialize_graph import run_full_init
    run_full_init()


def run_sync():
    """Chạy incremental sync dựa trên git diff."""
    _assert_configured()
    from initialize_graph import run_incremental_sync
    run_incremental_sync()
