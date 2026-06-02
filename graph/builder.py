from graph.neo4j_client import get_client


def build_file_nodes(parsed_files: list[dict]):
    """Create File nodes and Function/Class nodes from AST output with rich metadata."""
    client = get_client()
    for parsed in parsed_files:
        # Create File node
        client.run("""
            MERGE (f:File {path: $path})
            SET f.language = $language
        """, {"path": parsed["file"], "language": parsed["language"]})

        for node in parsed["nodes"]:
            label = _node_type_to_label(node["type"])

            # Create Function/Class node with rich testing metadata
            client.run(f"""
                MERGE (n:{label} {{name: $name, file: $file}})
                SET n.start_line = $start_line,
                    n.end_line = $end_line,
                    n.raw_code = $raw_code,
                    n.visibility = $visibility,
                    n.is_async = $is_async,
                    n.class_name = $class_name,
                    n.docstring = $docstring,
                    n.inputs = $inputs,
                    n.output = $output,
                    n.raises = $raises,
                    n.complexity = $complexity,
                    n.annotations = $annotations
            """, {
                "name": node["name"],
                "file": node["file"],
                "start_line": node["start_line"],
                "end_line": node["end_line"],
                "raw_code": node.get("raw_code", "")[:2000],
                "visibility": node.get("visibility", "public"),
                "is_async": node.get("is_async", False),
                "class_name": node.get("class_name", None),
                "docstring": node.get("docstring", ""),
                "inputs": node.get("inputs", "[]"),
                "output": node.get("output", ""),
                "raises": node.get("raises", "[]"),
                "complexity": node.get("complexity", 0),
                "annotations": node.get("annotations", "[]"),
            })

            # CONTAINS edge: File -> Function
            client.run(f"""
                MATCH (f:File {{path: $file_path}})
                MATCH (n:{label} {{name: $name, file: $file_path}})
                MERGE (f)-[:CONTAINS]->(n)
            """, {"file_path": node["file"], "name": node["name"]})

            # CALLS edges
            for called in node.get("calls", []):
                client.run(f"""
                    MATCH (caller:{label} {{name: $caller, file: $file}})
                    MERGE (callee:Function {{name: $callee}})
                    MERGE (caller)-[:CALLS]->(callee)
                """, {
                    "caller": node["name"],
                    "file": node["file"],
                    "callee": called.split(".")[-1],  # normalize "obj.method" -> "method"
                })

    print(f"[Builder] File and function nodes built ({len(parsed_files)} files).")


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
        for entity in result.get("entities", []):
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
