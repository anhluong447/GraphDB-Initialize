import json
from nelgraph.graph.neo4j_client import get_client


def build_file_nodes(parsed_files: list[dict]):
    """Create File nodes and Function/Class nodes from AST output with rich metadata."""
    client = get_client()
    total_files = len(parsed_files)
    print(f"[Builder] Starting database ingestion for {total_files} parsed files...")
    
    for idx, parsed in enumerate(parsed_files, 1):
        if idx % 20 == 0 or idx == total_files:
            print(f"[Builder] Processing file {idx}/{total_files}...")
            
        # Create File node
        client.run("""
            MERGE (f:File {path: $path})
            SET f.language = $language
        """, {"path": parsed["file"], "language": parsed["language"]})

        for node in parsed["nodes"]:
            base_label = _node_type_to_label(node["type"])
            is_test = False
            file_name = node["file"].replace("\\", "/").split("/")[-1].lower()
            node_name = node["name"].lower()
            if "test_" in file_name or "_test" in file_name or file_name.startswith("test") or node_name.startswith("test_") or node_name.endswith("_test"):
                is_test = True

            label = base_label
            if is_test:
                if base_label == "Function":
                    label = "Function:TestFunction"
                elif base_label == "Class":
                    label = "Class:TestClass"

            # Create Function/Class node with rich testing metadata
            # raw_code is stored directly in Neo4j so remote clients
            # don't need access to the local file system
            raw_code = node.get("raw_code", "")
            if not raw_code:
                # For tree-sitter nodes, raw_code comes from parsed["raw_code"]
                raw = parsed.get("raw_code", "")
                s = node.get("start_line", 1)
                e = node.get("end_line", s)
                if raw and s and e:
                    raw_lines = raw.splitlines()
                    raw_code = "\n".join(raw_lines[s - 1 : e])

            client.run(f"""
                MERGE (n:{label} {{name: $name, file: $file}})
                SET n.start_line = $start_line,
                    n.end_line = $end_line,
                    n.anchor = $anchor,
                    n.raw_code = $raw_code,
                    n.visibility = $visibility,
                    n.is_async = $is_async,
                    n.class_name = $class_name,
                    n.docstring = $docstring,
                    n.inputs = $inputs,
                    n.output = $output,
                    n.raises = $raises,
                    n.annotations = $annotations,
                    n.superclasses = $superclasses,
                    n.is_test = $is_test,
                    n.complexity = $complexity
            """, {
                "name": node["name"],
                "file": node["file"],
                "start_line": node["start_line"],
                "end_line": node["end_line"],
                "anchor": node.get("anchor", ""),
                "raw_code": raw_code[:15000],  # cap at 15000 chars to avoid Neo4j property size limits
                "visibility": node.get("visibility", "public"),
                "is_async": node.get("is_async", False),
                "class_name": node.get("class_name", None),
                "docstring": node.get("docstring", ""),
                "inputs": node.get("inputs", "[]"),
                "output": node.get("output", ""),
                "raises": node.get("raises", "[]"),
                "complexity": node.get("complexity", 0),
                "annotations": node.get("annotations", "[]"),
                "superclasses": node.get("superclasses", "[]"),
                "is_test": is_test,
            })

            # CONTAINS edge: File -> Function
            client.run(f"""
                MATCH (f:File {{path: $file_path}})
                MATCH (n:{label} {{name: $name, file: $file_path}})
                MERGE (f)-[:CONTAINS]->(n)
            """, {"file_path": node["file"], "name": node["name"]})

            # INHERITS_FROM edges for Class inheritance
            # External base classes (Exception, unittest.TestCase, etc.) are stored as
            # ExternalClass nodes — NOT as bare Class nodes — to avoid junk nodes without file paths.
            if base_label == "Class" and node.get("superclasses"):
                try:
                    superclasses = json.loads(node["superclasses"]) if isinstance(node["superclasses"], str) else node["superclasses"]
                    for base in superclasses:
                        # Check if this base class exists in the graph as a real Class node (has file)
                        existing = client.run("""
                            MATCH (c:Class {name: $parent_name})
                            WHERE c.file IS NOT NULL
                            RETURN c.name LIMIT 1
                        """, {"parent_name": base})
                        if existing:
                            # Link to existing Class node
                            client.run("""
                                MATCH (child:Class {name: $child_name, file: $file})
                                MATCH (parent:Class {name: $parent_name})
                                WHERE parent.file IS NOT NULL
                                MERGE (child)-[:INHERITS_FROM]->(parent)
                            """, {
                                "child_name": node["name"],
                                "file": node["file"],
                                "parent_name": base
                            })
                        else:
                            # External/stdlib base: use ExternalClass label so it won't be treated as junk
                            client.run("""
                                MATCH (child:Class {name: $child_name, file: $file})
                                MERGE (parent:ExternalClass {name: $parent_name})
                                MERGE (child)-[:INHERITS_FROM]->(parent)
                            """, {
                                "child_name": node["name"],
                                "file": node["file"],
                                "parent_name": base
                            })
                except Exception:
                    pass

        # IMPORTS: Create Module nodes and File -[:IMPORTS]-> Module edges
        for imp in parsed.get("imports", []):
            module_name = imp.get("module", "")
            if not module_name:
                continue
            client.run("""
                MERGE (m:Module {name: $module_name})
                SET m.is_external = $is_external,
                    m.is_stdlib = $is_stdlib
                WITH m
                MATCH (f:File {path: $file_path})
                MERGE (f)-[:IMPORTS {full_path: $full_path, alias: $alias, names: $names}]->(m)
            """, {
                "module_name": module_name,
                "is_external": imp.get("is_external", True),
                "is_stdlib": imp.get("is_stdlib", False),
                "file_path": parsed["file"],
                "full_path": imp.get("full_path", ""),
                "alias": imp.get("alias", ""),
                "names": json.dumps(imp.get("names", [])),
            })

            # USES_EXTERNAL: Function -> Module (if function body calls this module)
            if imp.get("is_external"):
                client.run("""
                    MATCH (fn:Function {file: $file_path})
                    WHERE any(call IN fn.calls WHERE call STARTS WITH $module_name)
                    MATCH (m:Module {name: $module_name})
                    MERGE (fn)-[:USES_EXTERNAL]->(m)
                """, {
                    "file_path": parsed["file"],
                    "module_name": module_name,
                })

    # Second pass: Link CALLS relationships using MATCH (no new callee nodes created)
    print("[Builder] Linking call relationships...")
    linked_calls = 0
    for parsed in parsed_files:
        lang = parsed.get("language")
        for node in parsed["nodes"]:
            # Reconstruct the caller label based on type and test status
            caller_label = _node_type_to_label(node["type"])
            is_test = False
            file_name = node["file"].replace("\\", "/").split("/")[-1].lower()
            node_name = node["name"].lower()
            if "test_" in file_name or "_test" in file_name or file_name.startswith("test") or node_name.startswith("test_") or node_name.endswith("_test"):
                is_test = True
            if is_test:
                if caller_label == "Function":
                    caller_label = "Function:TestFunction"
                elif caller_label == "Class":
                    caller_label = "Class:TestClass"

            for called in node.get("calls", []):
                callee_name = called.split(".")[-1]
                if _is_builtin(callee_name, lang):
                    continue

                client.run(f"""
                    MATCH (caller:{caller_label} {{name: $caller, file: $file}})
                    MATCH (callee)
                    WHERE (callee:Function OR callee:Class) AND callee.name = $callee
                    MERGE (caller)-[:CALLS]->(callee)
                """, {
                    "caller": node["name"],
                    "file": node["file"],
                    "callee": callee_name,
                })
                linked_calls += 1

    print(f"[Builder] File and function nodes built ({len(parsed_files)} files). Linked {linked_calls} calls.")


def build_git_nodes(commits: list[dict]):
    """Create Commit and Person nodes from git history."""
    client = get_client()
    for commit in commits:
        # Person node
        client.run("""
            MERGE (p:Person {name: $name})
            SET p.email = $email
        """, {"name": commit["author"], "email": commit["author_email"]})

        # Commit node
        client.run("""
            MERGE (c:Commit {hash: $hash})
            SET c.message = $message, c.date = $date
        """, {"hash": commit["hash"], "message": commit["message"], "date": commit["date"]})

        # AUTHORED_BY
        client.run("""
            MATCH (c:Commit {hash: $hash})
            MATCH (p:Person {name: $author})
            MERGE (c)-[:AUTHORED_BY]->(p)
        """, {"hash": commit["hash"], "author": commit["author"]})

        # MODIFIED edges: Commit -> File
        for file_path in commit["files_changed"]:
            client.run("""
                MATCH (c:Commit {hash: $hash})
                MERGE (f:File {path: $path})
                MERGE (c)-[:MODIFIED {date: $date}]->(f)
            """, {"hash": commit["hash"], "path": file_path, "date": commit["date"]})

    print(f"[Builder] Git nodes built ({len(commits)} commits).")


def build_semantic_nodes(extraction_results: list[dict]):
    """Create Concept/Feature/Decision/Risk/Task nodes from LLM extraction."""
    client = get_client()
    entity_count = 0
    rel_count = 0

    for result in extraction_results:
        # Protect against non-dictionary results
        if not isinstance(result, dict):
            continue
            
        for entity in result.get("entities", []):
            if not isinstance(entity, dict) or "name" not in entity:
                continue
            label = entity.get("type", "Concept")
            # Sanitize label to prevent injection
            if label not in ("Feature", "Concept", "Decision", "Risk", "Task", "Module"):
                label = "Concept"
            client.run(f"""
                MERGE (n:{label} {{name: $name}})
                SET n.description = $description
            """, {"name": entity["name"], "description": entity.get("description", "")})
            entity_count += 1

        for rel in result.get("relations", []):
            if not isinstance(rel, dict):
                continue
            from_name = rel.get("from", "")
            to_name = rel.get("to", "")
            relation = rel.get("relation", "relates_to").upper()

            # Sanitize relation type
            valid_relations = {"IMPLEMENTS", "DEPENDS_ON", "RELATES_TO", "CONFLICTS_WITH", "BLOCKS", "OWNED_BY", "INTRODUCES"}
            if relation not in valid_relations:
                relation = "RELATES_TO"

            if from_name and to_name:
                client.run(f"""
                    MATCH (a) WHERE a.name = $from_name
                    MATCH (b) WHERE b.name = $to_name
                    MERGE (a)-[:{relation}]->(b)
                """, {"from_name": from_name, "to_name": to_name})
                rel_count += 1

    print(f"[Builder] Semantic nodes built ({entity_count} entities, {rel_count} relations).")


def _node_type_to_label(node_type: str) -> str:
    mapping = {
        "function_definition": "Function",
        "function_declaration": "Function",
        "method_definition": "Function",
        "arrow_function": "Function",
        "class_definition": "Class",
        "class_declaration": "Class",
    }
    return mapping.get(node_type, "Function")


def link_commits_to_functions(commits: list[dict], parsed_files: list[dict], repo_path: str):
    """
    Create Commit -[:CHANGED]-> Function relationships by overlapping
    commit diff line ranges with function start_line/end_line.
    """
    from nelgraph.parsers.git_parser import parse_commit_diff
    client = get_client()

    # Build lookup: file_path -> list of {name, start_line, end_line}
    file_functions = {}
    for pf in parsed_files:
        for node in pf.get("nodes", []):
            fp = node.get("file", "")
            if fp not in file_functions:
                file_functions[fp] = []
            file_functions[fp].append({
                "name": node["name"],
                "start_line": node["start_line"],
                "end_line": node["end_line"],
            })

    linked = 0
    for commit in commits:
        commit_hash = commit.get("full_hash") or commit.get("hash", "")
        if not commit_hash:
            continue

        diff_data = parse_commit_diff(repo_path, commit_hash)
        changed_ranges = diff_data.get("changed_ranges", {})

        for file_rel_path, ranges in changed_ranges.items():
            # Try to match file_rel_path to our parsed file paths
            matching_files = [
                fp for fp in file_functions
                if fp.replace("\\", "/").endswith(file_rel_path.replace("\\", "/"))
            ]

            for fp in matching_files:
                for func in file_functions[fp]:
                    # Check overlap: not (func.end < range_start or func.start > range_end)
                    for r_start, r_end in ranges:
                        if not (func["end_line"] < r_start or func["start_line"] > r_end):
                            client.run("""
                                MATCH (c:Commit {hash: $hash})
                                MATCH (f:Function {name: $func_name, file: $file_path})
                                MERGE (c)-[:CHANGED {date: $date}]->(f)
                            """, {
                                "hash": commit["hash"],
                                "func_name": func["name"],
                                "file_path": fp,
                                "date": commit.get("date", ""),
                            })
                            linked += 1
                            break  # One link per function per commit is enough

    print(f"[Builder] Linked {linked} commit-function relationships.")


# --- Language Built-ins Lists ---

PYTHON_BUILTINS = {
    "abs", "aiter", "all", "any", "anext", "ascii", "bin", "bool", "breakpoint", "bytearray",
    "bytes", "callable", "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir",
    "divmod", "enumerate", "eval", "exec", "filter", "float", "format", "frozenset", "getattr",
    "globals", "hasattr", "hash", "help", "hex", "id", "input", "int", "isinstance", "issubclass",
    "iter", "len", "list", "locals", "map", "max", "memoryview", "min", "next", "object", "oct",
    "open", "ord", "pow", "print", "property", "range", "repr", "reversed", "round", "set",
    "setattr", "slice", "sorted", "staticmethod", "str", "sum", "super", "tuple", "type", "vars",
    "zip", "__import__", "BaseException", "Exception", "TypeError", "ValueError", "KeyError",
    "IndexError", "AttributeError", "NameError", "RuntimeError", "StopIteration", "AssertionError",
}

JS_TS_BUILTINS = {
    "console", "log", "error", "warn", "info", "debug", "alert", "prompt", "confirm",
    "require", "define", "module", "exports", "import", "eval", "parseInt", "parseFloat",
    "isNaN", "isFinite", "decodeURI", "decodeURIComponent", "encodeURI", "encodeURIComponent",
    "Object", "Function", "Boolean", "Symbol", "Error", "EvalError", "InternalError",
    "RangeError", "ReferenceError", "SyntaxError", "TypeError", "URIError", "Number",
    "Math", "Date", "String", "RegExp", "Array", "Int8Array", "Uint8Array", "Uint8ClampedArray",
    "Int16Array", "Uint16Array", "Int32Array", "Uint32Array", "Float32Array", "Float64Array",
    "Map", "Set", "WeakMap", "WeakSet", "Promise", "Generator", "GeneratorFunction",
    "AsyncFunction", "JSON", "Proxy", "Reflect", "setTimeout", "clearTimeout", "setInterval",
    "clearInterval", "setImmediate", "clearImmediate", "requestAnimationFrame", "cancelAnimationFrame",
}

PHP_BUILTINS = {
    "echo", "print", "die", "exit", "isset", "empty", "unset", "include", "include_once",
    "require", "require_once", "array", "eval", "list", "var_dump", "print_r",
    "strlen", "strpos", "substr", "in_array", "array_key_exists", "count", "is_array",
    "explode", "implode", "sprintf", "trim", "strtolower", "strtoupper", "define",
    "defined", "function_exists", "class_exists", "method_exists", "property_exists",
}

def _is_builtin(name: str, language: str) -> bool:
    if not name:
        return False
    if language == "python" and name in PYTHON_BUILTINS:
        return True
    if language in ("javascript", "typescript") and name in JS_TS_BUILTINS:
        return True
    if language == "php" and name in PHP_BUILTINS:
        return True
    return False
