import os
import glob
import sys
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CODEBASE_PATH
from graph.neo4j_client import get_client
from parsers.ast_parser import parse_file
from embeddings.chroma_client import embed_nodes_for_files

def update_db():
    client = get_client()

    print("[Updater] Scanning files in codebase...")
    pattern = os.path.normpath(os.path.join(CODEBASE_PATH, "**/*.py"))
    py_files = glob.glob(pattern, recursive=True)
    # Convert to absolute paths and normalize backslashes
    py_files = [os.path.abspath(f).replace("\\", "/") for f in py_files]
    
    # Filter out ignored dirs relative to CODEBASE_PATH
    from config import IGNORE_DIRS
    filtered_files = []
    for f in py_files:
        rel_path = os.path.relpath(f, CODEBASE_PATH).replace("\\", "/")
        parts = rel_path.split("/")
        if not any(d in parts for d in IGNORE_DIRS):
            filtered_files.append(f)
            
    print(f"[Updater] Found {len(filtered_files)} python files. Parsing classes, inheritance, and attributes...")
    
    affected_files = set()
    for f in filtered_files:
        try:
            parsed = parse_file(f)
            if not parsed:
                continue
            
            for node in parsed.get("nodes", []):
                if node["type"] in ("class_definition", "class_declaration"):
                    class_name = node["name"]
                    file_path = node["file"]
                    
                    # 1. Ensure Class node is created/updated
                    client.run("""
                        MERGE (c:Class {name: $class_name, file: $file})
                        SET c.start_line = $start_line,
                            c.end_line = $end_line,
                            c.anchor = $anchor,
                            c.docstring = $docstring,
                            c.annotations = $annotations,
                            c.superclasses = $superclasses
                    """, {
                        "class_name": class_name,
                        "file": file_path,
                        "start_line": node["start_line"],
                        "end_line": node["end_line"],
                        "anchor": node.get("anchor", ""),
                        "docstring": node.get("docstring", ""),
                        "annotations": node.get("annotations", "[]"),
                        "superclasses": node.get("superclasses", "[]")
                    })
                    
                    # Establish INHERITS_FROM relationship
                    supers = json.loads(node.get("superclasses", "[]"))
                    for parent_name in supers:
                        client.run("""
                            MATCH (c:Class {name: $class_name, file: $file})
                            MERGE (p:Class {name: $parent_name})
                            MERGE (c)-[:INHERITS_FROM]->(p)
                        """, {
                            "class_name": class_name,
                            "file": file_path,
                            "parent_name": parent_name
                        })
                    
                    # 2. Add ClassAttributes
                    attributes = node.get("attributes", [])
                    print(f"  Class: {class_name} in {os.path.basename(file_path)} - found {len(attributes)} attributes.")
                    for attr in attributes:
                        client.run("""
                            MERGE (c:Class {name: $class_name, file: $file})
                            MERGE (a:ClassAttribute {name: $attr_name, file: $file})
                            SET a.type_hint = $type_hint,
                                a.default_value = $default_value,
                                a.is_dataclass_field = $is_dataclass_field
                            MERGE (c)-[:HAS_ATTRIBUTE]->(a)
                        """, {
                            "class_name": class_name,
                            "file": file_path,
                            "attr_name": attr["name"],
                            "type_hint": attr.get("type_hint", ""),
                            "default_value": attr.get("default_value", None),
                            "is_dataclass_field": attr.get("is_dataclass_field", False),
                        })
                    affected_files.add(f)
                    
                elif node["type"] in ("function_definition", "function_declaration", "method_definition"):
                    # Update function is_entry_point property
                    func_name = node["name"]
                    file_path = node["file"]
                    client.run("""
                        MERGE (f:Function {name: $name, file: $file})
                        SET f.is_entry_point = $is_entry_point
                    """, {
                        "name": func_name,
                        "file": file_path,
                        "is_entry_point": node.get("is_entry_point", False)
                    })
                    affected_files.add(f)
        except Exception as e:
            print(f"Error parsing file {f}: {e}")

    # Re-embed nodes for all affected files to ensure attributes and entry points are reflected in ChromaDB
    affected_files = list(affected_files)
    if affected_files:
        print(f"\n[Updater] Re-embedding nodes for {len(affected_files)} affected files in ChromaDB...")
        embed_nodes_for_files(affected_files)
    
    print("\n[SUCCESS] Round 2 synchronization successfully completed!")

if __name__ == "__main__":
    update_db()
