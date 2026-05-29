import os
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
from config import CODEBASE_PATH, SUPPORTED_LANGUAGES, IGNORE_DIRS

PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())

LANGUAGE_MAP = {
    "python": PY_LANGUAGE,
    "javascript": JS_LANGUAGE,
    "typescript": TS_LANGUAGE,
}


def parse_file(file_path: str) -> dict:
    """
    Parse a single file, returns dict with:
    - file: file path
    - language: language name
    - nodes: list[dict] of function/class/variable definitions
    - raw_code: full source code of the file
    """
    ext = Path(file_path).suffix
    lang_name = SUPPORTED_LANGUAGES.get(ext)
    if not lang_name:
        return None

    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
    except Exception:
        return None

    parser = Parser(LANGUAGE_MAP[lang_name])
    tree = parser.parse(source_bytes)

    nodes = []
    _extract_nodes(tree.root_node, source_bytes, file_path, nodes)

    return {
        "file": file_path,
        "language": lang_name,
        "nodes": nodes,
        "raw_code": source_bytes.decode("utf-8", errors="ignore"),
    }


def _extract_nodes(node, source_bytes: bytes, file_path: str, result: list, parent=None):
    """Recursively walk AST and extract function/class definitions."""
    extractable = {
        "function_definition", "function_declaration",
        "class_definition", "class_declaration",
        "method_definition", "arrow_function",
    }

    if node.type in extractable:
        name_node = node.child_by_field_name("name")
        if name_node:
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore")
        else:
            name = "anonymous"
        raw_code = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

        # Extract function calls inside this node
        calls = _extract_calls(node, source_bytes)

        result.append({
            "type": node.type,
            "name": name,
            "file": file_path,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "raw_code": raw_code[:2000],  # limit to 2000 chars
            "calls": calls,
            "parent": parent,
        })
        parent = name

    for child in node.children:
        _extract_nodes(child, source_bytes, file_path, result, parent)


def _extract_calls(node, source_bytes: bytes) -> list[str]:
    """Find all function calls within a node."""
    calls = []
    if node.type == "call":
        func_node = node.child_by_field_name("function")
        if func_node:
            call_name = source_bytes[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="ignore")
            calls.append(call_name)
    for child in node.children:
        calls.extend(_extract_calls(child, source_bytes))
    return list(set(calls))


def parse_codebase(path: str = CODEBASE_PATH) -> list[dict]:
    """Parse entire codebase, returns list of parsed file dicts."""
    results = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            file_path = os.path.join(root, file)
            parsed = parse_file(file_path)
            if parsed:
                results.append(parsed)
    print(f"[Parser] Parsed {len(results)} files.")
    return results
