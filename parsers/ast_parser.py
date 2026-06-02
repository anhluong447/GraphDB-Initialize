import os
import re
import json
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
    _extract_nodes(tree.root_node, source_bytes, file_path, lang_name, nodes)

    return {
        "file": file_path,
        "language": lang_name,
        "nodes": nodes,
        "raw_code": source_bytes.decode("utf-8", errors="ignore"),
    }


def _extract_nodes(node, source_bytes: bytes, file_path: str, lang: str, result: list, parent_class=None):
    """Recursively walk AST and extract function/class definitions with rich metadata."""
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

        # ── Rich metadata extraction ──
        is_func = node.type not in ("class_definition", "class_declaration")

        is_async = _extract_is_async(node, source_bytes)
        visibility = _extract_visibility(name, lang)
        docstring = _extract_docstring(node, source_bytes, lang) if is_func else ""
        inputs = _extract_parameters(node, source_bytes, lang) if is_func else []
        return_type = _extract_return_type(node, source_bytes, lang) if is_func else ""
        raises = _extract_raises(node, source_bytes, lang) if is_func else []
        complexity = _compute_complexity(node, source_bytes) if is_func else 0
        decorators = _extract_decorators(node, source_bytes, lang)

        result.append({
            "type": node.type,
            "name": name,
            "file": file_path,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "raw_code": raw_code[:2000],  # limit to 2000 chars
            "calls": calls,
            "parent": parent_class,
            # ── New rich properties ──
            "is_async": is_async,
            "visibility": visibility,
            "class_name": parent_class,
            "docstring": docstring[:500],
            "inputs": json.dumps(inputs),         # JSON string for Neo4j storage
            "output": return_type,
            "raises": json.dumps(raises),          # JSON string for Neo4j storage
            "complexity": complexity,
            "annotations": json.dumps(decorators), # JSON string for Neo4j storage
        })

        # Track parent class name for methods
        new_parent = name if not is_func else parent_class
        for child in node.children:
            _extract_nodes(child, source_bytes, file_path, lang, result, new_parent)
        return

    for child in node.children:
        _extract_nodes(child, source_bytes, file_path, lang, result, parent_class)


# ═══════════════════════════════════════════════════════════
# Helper functions for rich metadata extraction
# ═══════════════════════════════════════════════════════════

def _extract_is_async(node, source_bytes: bytes) -> bool:
    """Check if a function/method is declared as async."""
    # In Tree-sitter, async functions may have an 'async' keyword as a child token
    for child in node.children:
        text = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
        if text == "async":
            return True
        if child.type == "async":
            return True
    return False


def _extract_visibility(name: str, lang: str) -> str:
    """Determine visibility based on naming conventions."""
    if lang == "python":
        if name.startswith("__") and not name.endswith("__"):
            return "private"
        elif name.startswith("_"):
            return "protected"
        return "public"
    elif lang in ("javascript", "typescript"):
        if name.startswith("#"):
            return "private"
        if name.startswith("_"):
            return "protected"
        return "public"
    return "public"


def _extract_docstring(node, source_bytes: bytes, lang: str) -> str:
    """Extract docstring from first string literal in function body."""
    body = node.child_by_field_name("body")
    if not body:
        return ""

    # For Python: look for expression_statement > string as first non-trivial child
    if lang == "python":
        for child in body.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        raw = source_bytes[sub.start_byte:sub.end_byte].decode("utf-8", errors="ignore")
                        # Strip triple quotes
                        raw = raw.strip()
                        for q in ('"""', "'''"):
                            if raw.startswith(q) and raw.endswith(q):
                                raw = raw[3:-3].strip()
                                break
                        return raw
                break  # Only check first statement
            elif child.type in ("comment",):
                continue
            else:
                break

    # For JS/TS: look for a preceding comment node (JSDoc)
    if lang in ("javascript", "typescript"):
        # Check for comment node right before the function in the parent
        parent = node.parent
        if parent:
            prev_sibling = node.prev_named_sibling
            if prev_sibling and prev_sibling.type == "comment":
                raw = source_bytes[prev_sibling.start_byte:prev_sibling.end_byte].decode("utf-8", errors="ignore")
                # Strip /** */ markers
                raw = raw.strip()
                if raw.startswith("/**") and raw.endswith("*/"):
                    raw = raw[3:-2].strip()
                elif raw.startswith("//"):
                    raw = raw[2:].strip()
                return raw

    return ""


def _extract_parameters(node, source_bytes: bytes, lang: str) -> list[dict]:
    """Extract function parameters with name, type annotation, and default value."""
    params_node = node.child_by_field_name("parameters")
    if not params_node:
        return []

    params = []
    for child in params_node.children:
        if child.type in ("identifier", "typed_parameter", "default_parameter",
                          "typed_default_parameter", "required_parameter",
                          "optional_parameter", "formal_parameters",
                          "rest_parameter"):
            param_info = _parse_single_param(child, source_bytes, lang)
            if param_info and param_info["name"] not in ("self", "cls"):
                params.append(param_info)
        # For patterns like (a, b, c) — children may be identifiers directly
        elif child.type == "parameter":
            param_info = _parse_single_param(child, source_bytes, lang)
            if param_info and param_info["name"] not in ("self", "cls"):
                params.append(param_info)

    return params


def _parse_single_param(param_node, source_bytes: bytes, lang: str) -> dict | None:
    """Parse a single parameter node into {name, type, default}."""
    name = ""
    type_str = ""
    default_str = ""

    if param_node.type == "identifier":
        name = source_bytes[param_node.start_byte:param_node.end_byte].decode("utf-8", errors="ignore")
    elif param_node.type in ("typed_parameter", "typed_default_parameter",
                              "required_parameter", "optional_parameter"):
        name_child = param_node.child_by_field_name("name") or param_node.child_by_field_name("pattern")
        # Fallback: for Python typed_parameter, name is the first identifier child
        if not name_child:
            for sub in param_node.children:
                if sub.type == "identifier":
                    name_child = sub
                    break
        if name_child:
            name = source_bytes[name_child.start_byte:name_child.end_byte].decode("utf-8", errors="ignore")

        type_child = param_node.child_by_field_name("type")
        if type_child:
            type_str = source_bytes[type_child.start_byte:type_child.end_byte].decode("utf-8", errors="ignore").strip(": ")

        value_child = param_node.child_by_field_name("value")
        if value_child:
            default_str = source_bytes[value_child.start_byte:value_child.end_byte].decode("utf-8", errors="ignore")
    elif param_node.type == "default_parameter":
        name_child = param_node.child_by_field_name("name")
        if name_child:
            name = source_bytes[name_child.start_byte:name_child.end_byte].decode("utf-8", errors="ignore")
        value_child = param_node.child_by_field_name("value")
        if value_child:
            default_str = source_bytes[value_child.start_byte:value_child.end_byte].decode("utf-8", errors="ignore")
    elif param_node.type == "rest_parameter":
        # *args or **kwargs in Python, ...rest in JS/TS
        raw = source_bytes[param_node.start_byte:param_node.end_byte].decode("utf-8", errors="ignore")
        name = raw
    elif param_node.type == "parameter":
        # Generic parameter node
        raw = source_bytes[param_node.start_byte:param_node.end_byte].decode("utf-8", errors="ignore")
        name = raw

    if not name:
        return None

    result = {"name": name}
    if type_str:
        result["type"] = type_str
    if default_str:
        result["default"] = default_str
    return result


def _extract_return_type(node, source_bytes: bytes, lang: str) -> str:
    """Extract return type annotation."""
    ret_type = node.child_by_field_name("return_type")
    if ret_type:
        raw = source_bytes[ret_type.start_byte:ret_type.end_byte].decode("utf-8", errors="ignore")
        return raw.strip(": ->").strip()
    return ""


def _extract_raises(node, source_bytes: bytes, lang: str) -> list[str]:
    """Extract all raise/throw statements from function body."""
    raises = set()
    _collect_raises(node, source_bytes, lang, raises)
    return sorted(raises)


def _collect_raises(node, source_bytes: bytes, lang: str, raises: set):
    """Recursively find raise/throw statements."""
    if lang == "python" and node.type == "raise_statement":
        # Get the exception type being raised
        for child in node.children:
            if child.type == "call":
                func = child.child_by_field_name("function")
                if func:
                    name = source_bytes[func.start_byte:func.end_byte].decode("utf-8", errors="ignore")
                    raises.add(name)
            elif child.type == "identifier":
                name = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
                raises.add(name)

    if lang in ("javascript", "typescript") and node.type == "throw_statement":
        for child in node.children:
            if child.type == "new_expression":
                cons = child.child_by_field_name("constructor")
                if cons:
                    name = source_bytes[cons.start_byte:cons.end_byte].decode("utf-8", errors="ignore")
                    raises.add(name)
            elif child.type == "identifier":
                name = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
                raises.add(name)

    for child in node.children:
        _collect_raises(child, source_bytes, lang, raises)


def _compute_complexity(node, source_bytes: bytes) -> int:
    """
    Compute Cyclomatic Complexity for a function node.
    CC = 1 + number of decision points (if, for, while, except, case, and, or, elif, catch, ternary).
    """
    decision_types = {
        "if_statement", "elif_clause", "for_statement", "for_in_statement",
        "while_statement", "except_clause", "catch_clause",
        "case_clause", "conditional_expression", "ternary_expression",
    }
    # Boolean operators also add branches
    boolean_ops = {"and", "or", "&&", "||"}

    count = 1  # Base complexity

    def _walk(n):
        nonlocal count
        if n.type in decision_types:
            count += 1
        # Check for boolean operators
        if n.type in ("boolean_operator", "binary_expression"):
            op_node = n.child_by_field_name("operator")
            if op_node:
                op_text = source_bytes[op_node.start_byte:op_node.end_byte].decode("utf-8", errors="ignore")
                if op_text in boolean_ops:
                    count += 1
            else:
                # Fallback: check raw text for operators
                raw = source_bytes[n.start_byte:n.end_byte].decode("utf-8", errors="ignore")
                for op in boolean_ops:
                    if f" {op} " in raw:
                        count += raw.count(f" {op} ")
                        break
        for child in n.children:
            _walk(child)

    _walk(node)
    return count


def _extract_decorators(node, source_bytes: bytes, lang: str) -> list[str]:
    """Extract decorators/annotations applied to a function or class."""
    decorators = []
    if lang == "python":
        # Decorators are sibling nodes before the function in the decorated_definition
        parent = node.parent
        if parent and parent.type == "decorated_definition":
            for child in parent.children:
                if child.type == "decorator":
                    raw = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
                    decorators.append(raw.strip())
    elif lang in ("javascript", "typescript"):
        # Check for decorator nodes (TC39 proposal / TypeScript experimental)
        prev = node.prev_named_sibling
        while prev and prev.type == "decorator":
            raw = source_bytes[prev.start_byte:prev.end_byte].decode("utf-8", errors="ignore")
            decorators.append(raw.strip())
            prev = prev.prev_named_sibling

    return decorators


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
