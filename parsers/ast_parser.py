import os
import re
import sys
import json
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
import tree_sitter_php as tsphp
from config import CODEBASE_PATH, SUPPORTED_LANGUAGES, IGNORE_DIRS

# Python stdlib module names (used for is_stdlib detection)
try:
    _PYTHON_STDLIB = set(sys.stdlib_module_names)
except AttributeError:
    _PYTHON_STDLIB = {
        "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit", "base64",
        "binascii", "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb",
        "cmath", "cmd", "code", "codecs", "collections", "colorsys", "compileall",
        "concurrent", "configparser", "contextlib", "contextvars", "copy", "copyreg",
        "cProfile", "csv", "ctypes", "curses", "dataclasses", "datetime", "dbm",
        "decimal", "difflib", "dis", "distutils", "doctest", "email", "encodings",
        "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
        "fractions", "ftplib", "functools", "gc", "getopt", "getpass", "gettext",
        "glob", "grp", "gzip", "hashlib", "heapq", "hmac", "html", "http",
        "idlelib", "imaplib", "imghdr", "imp", "importlib", "inspect", "io",
        "ipaddress", "itertools", "json", "keyword", "lib2to3", "linecache",
        "locale", "logging", "lzma", "mailbox", "mailcap", "marshal", "math",
        "mimetypes", "mmap", "modulefinder", "multiprocessing", "netrc", "nis",
        "nntplib", "numbers", "operator", "optparse", "os", "ossaudiodev",
        "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
        "plistlib", "poplib", "posixpath", "pprint", "profile", "pstats", "pty",
        "pwd", "py_compile", "pyclbr", "pydoc", "queue", "quopri", "random",
        "re", "readline", "reprlib", "resource", "rlcompleter", "runpy", "sched",
        "secrets", "select", "selectors", "shelve", "shlex", "shutil", "signal",
        "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "sqlite3",
        "ssl", "stat", "statistics", "string", "stringprep", "struct", "subprocess",
        "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny", "tarfile",
        "telnetlib", "tempfile", "termios", "test", "textwrap", "threading", "time",
        "timeit", "tkinter", "token", "tokenize", "tomllib", "trace", "traceback",
        "tracemalloc", "tty", "turtle", "turtledemo", "types", "typing",
        "unicodedata", "unittest", "urllib", "uuid", "venv", "warnings", "wave",
        "weakref", "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib",
        "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib", "_thread",
    }

PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())
PHP_LANGUAGE = Language(tsphp.language_php())

LANGUAGE_MAP = {
    "python": PY_LANGUAGE,
    "javascript": JS_LANGUAGE,
    "typescript": TS_LANGUAGE,
    "php": PHP_LANGUAGE,
}


# Node types trong PHP AST làm tăng complexity
_PHP_COMPLEXITY_NODES = {
    "if_statement",
    "elseif_clause",
    "else_clause",
    "foreach_statement",
    "for_statement",
    "while_statement",
    "do_statement",
    "switch_statement",
    "case_statement",
    "catch_clause",
    "conditional_expression",   # ternary operator
    "match_expression",
    "null_safe_member_access_expression",
}

def _calc_php_complexity(node) -> int:
    """
    Tính cyclomatic complexity của 1 PHP AST node.
    Đếm số nhánh logic (if, foreach, while, catch...) + 1.
    """
    count = 1
    def traverse(n):
        if n.type in _PHP_COMPLEXITY_NODES:
            nonlocal count
            count += 1
        for child in n.children:
            traverse(child)
    traverse(node)
    return count

# PHP function/method names bị skip dù có complexity cao
# (magic methods không cần test, hoặc quá generic)
_PHP_SKIP_NAMES = {
    "__construct", "__destruct", "__clone",
    "__sleep", "__wakeup", "__serialize", "__unserialize",
    "__invoke", "__debugInfo",
    # generic getters/setters — thường trivial
    "getRow", "getRows", "getResult",
}


def _parse_php_file_treesitter(file_path: str, source_bytes: bytes) -> dict:
    """
    Parse PHP file using Tree-Sitter for accurate AST.
    Filters out trivial functions (complexity=1, line_count<4).
    """
    try:
        PHP_LANGUAGE = LANGUAGE_MAP["php"]
    except KeyError:
        # Fallback nếu PHP_LANGUAGE chưa được khởi tạo
        import tree_sitter_php as tsphp
        PHP_LANGUAGE = Language(tsphp.language_php())

    parser = Parser(PHP_LANGUAGE)
    tree = parser.parse(source_bytes)
    code = source_bytes.decode("utf-8", errors="ignore")
    lines = code.splitlines()

    nodes = []
    imports = []
    current_class = None

    # --- FILTER THRESHOLDS ---
    MIN_LINES = 4         # function phải có ít nhất 4 dòng
    MIN_COMPLEXITY = 2    # phải có ít nhất 1 nhánh logic (if/foreach/...)

    def get_line(node_obj):
        return node_obj.start_point[0] + 1  # 1-indexed

    def get_text(node_obj):
        return node_obj.text.decode("utf-8", errors="ignore").strip()

    def extract_params(params_node):
        """Extract parameter list từ AST node."""
        inputs = []
        if params_node is None:
            return inputs
        for child in params_node.children:
            if child.type in ("simple_parameter", "variadic_parameter",
                              "property_promotion_parameter"):
                param_name = ""
                param_type = ""
                for sub in child.children:
                    if sub.type == "variable_name":
                        param_name = get_text(sub)
                    elif sub.type in ("named_type", "union_type",
                                      "nullable_type", "intersection_type"):
                        param_type = get_text(sub)
                if param_name:
                    inputs.append({"name": param_name, "type": param_type})
        return inputs

    def extract_calls(func_node):
        """Extract function/method calls bên trong body của function."""
        calls = set()
        def walk(n):
            if n.type in ("function_call_expression", "method_call_expression",
                          "static_method_call_expression"):
                for child in n.children:
                    if child.type == "name":
                        calls.add(get_text(child))
            for c in n.children:
                walk(c)
        walk(func_node)
        return list(calls)

    def extract_imports_from_use(node_obj):
        """Extract use statements (imports)."""
        for child in node_obj.children:
            if child.type == "namespace_use_declaration":
                for clause in child.children:
                    if clause.type == "namespace_use_clause":
                        full_path = get_text(clause)
                        parts = full_path.split("\\")
                        root_mod = parts[0] if parts else ""
                        imports.append({
                            "module": root_mod,
                            "full_path": full_path,
                            "alias": "",
                            "names": [parts[-1]] if parts else [],
                            "is_external": True,
                            "is_stdlib": False,
                            "source_file": file_path,
                        })

    def process_function(func_node, class_name=None):
        """Process 1 function/method node, apply filters, add to nodes list."""
        func_name = ""
        params_node = None
        visibility = "public"
        is_static = False
        return_type = ""

        for child in func_node.children:
            if child.type == "name":
                func_name = get_text(child)
            elif child.type == "formal_parameters":
                params_node = child
            elif child.type in ("public", "protected", "private"):
                visibility = child.type
            elif child.type == "static":
                is_static = True
            elif child.type == "named_type":
                return_type = get_text(child)

        if not func_name:
            return

        # Skip nếu trong danh sách đen
        if func_name in _PHP_SKIP_NAMES:
            return

        start_line = get_line(func_node)
        end_line = func_node.end_point[0] + 1
        line_count = end_line - start_line + 1
        complexity = _calc_php_complexity(func_node)

        # FILTER: bỏ qua function quá đơn giản
        if line_count < MIN_LINES or complexity < MIN_COMPLEXITY:
            return

        # Build anchor (dòng đầu tiên của function)
        anchor = lines[start_line - 1].strip() if start_line <= len(lines) else ""

        # Parse inputs
        inputs = extract_params(params_node)

        # Extract calls
        calls = extract_calls(func_node)

        nodes.append({
            "type": "method_definition" if class_name else "function_definition",
            "name": func_name,
            "file": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "anchor": anchor,
            "calls": calls,
            "parent": class_name,
            "is_async": False,
            "visibility": visibility,
            "class_name": class_name,
            "docstring": "",
            "inputs": json.dumps(inputs),
            "output": return_type,
            "raises": "[]",
            "complexity": complexity,
            "annotations": "[]",
        })

    def walk_tree(node_obj, class_ctx=None):
        nonlocal current_class

        if node_obj.type == "class_declaration":
            # Extract class name
            cls_name = ""
            for child in node_obj.children:
                if child.type == "name":
                    cls_name = get_text(child)
                    break
            if cls_name:
                # Add class node (không filter class)
                start_line = get_line(node_obj)
                end_line = node_obj.end_point[0] + 1
                anchor = lines[start_line - 1].strip() if start_line <= len(lines) else ""
                nodes.append({
                    "type": "class_definition",
                    "name": cls_name,
                    "file": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "anchor": anchor,
                    "calls": [],
                    "parent": None,
                    "is_async": False,
                    "visibility": "public",
                    "class_name": None,
                    "docstring": "",
                    "inputs": "[]",
                    "output": "",
                    "raises": "[]",
                    "complexity": 1,
                    "annotations": "[]",
                })
                current_class = cls_name
                for child in node_obj.children:
                    walk_tree(child, class_ctx=cls_name)
                current_class = None
                return

        elif node_obj.type in ("function_definition", "method_declaration"):
            process_function(node_obj, class_name=class_ctx)
            return  # Không walk sâu vào bên trong function

        elif node_obj.type == "namespace_use_declaration":
            extract_imports_from_use(node_obj.parent or node_obj)

        for child in node_obj.children:
            walk_tree(child, class_ctx=class_ctx)

    walk_tree(tree.root_node)

    return {
        "file": file_path,
        "language": "php",
        "nodes": nodes,
        "imports": imports,
        "raw_code": code,
    }


def _parse_php_file_regex_DEPRECATED(file_path: str, source_bytes: bytes) -> dict:
    """
    Fallback regex parser for PHP files.
    Extracts classes, methods, functions, and function calls.
    """
    code = source_bytes.decode("utf-8", errors="ignore")
    lines = code.splitlines()
    
    nodes = []
    imports = []
    
    # 1. Extract imports (use, require, include)
    use_matches = re.finditer(r'^\s*use\s+([^;]+);', code, re.MULTILINE)
    for m in use_matches:
        full_path = m.group(1).strip()
        parts = full_path.split('\\')
        root_mod = parts[0] if parts else ""
        imports.append({
            "module": root_mod,
            "full_path": full_path,
            "alias": "",
            "names": [parts[-1]] if parts else [],
            "is_external": True,
            "is_stdlib": False,
            "source_file": file_path,
        })
        
    # 2. Extract classes and functions
    # Regex to find class declarations
    class_matches = list(re.finditer(r'(?:abstract\s+|final\s+)?class\s+(\w+)', code))
    
    # Regex to find functions / methods: function name(args)
    # Handles visibility modifiers (public, private, protected, static)
    func_regex = r'(?:(public|protected|private)\s+)?(?:static\s+)?function\s+(\w+)\s*\(([^)]*)\)'
    func_matches = list(re.finditer(func_regex, code))
    
    # Map index to line numbers for fast lookup
    line_starts = []
    curr = 0
    for line in lines:
        line_starts.append(curr)
        curr += len(line) + 1 # +1 for newline
        
    def get_line_num(char_idx):
        import bisect
        return bisect.bisect_right(line_starts, char_idx)
        
    # Find all function calls in the code (e.g. $this->someMethod( or Class::someMethod()
    # Extracts name of functions called
    call_regex = r'(?:\$this->|(\w+)::)(\w+)\s*\('
    all_calls = []
    for m in re.finditer(call_regex, code):
        all_calls.append(m.group(2))
    # Standard standalone function calls: func_name(
    for m in re.finditer(r'\b(\w+)\s*\((?!\s*function\b)', code):
        func_called = m.group(1)
        if func_called not in ("if", "for", "while", "foreach", "switch", "catch", "array", "isset", "empty", "unset", "count"):
            all_calls.append(func_called)
            
    # Process classes
    classes_info = []
    for m in class_matches:
        c_name = m.group(1)
        start_idx = m.start()
        start_line = get_line_num(start_idx)
        classes_info.append({
            "name": c_name,
            "start_line": start_line,
            "start_idx": start_idx
        })
        nodes.append({
            "type": "class_definition",
            "name": c_name,
            "file": file_path,
            "start_line": start_line,
            "end_line": start_line + 5, # fallback length
            "anchor": f"class {c_name}",
            "calls": [],
            "parent": None,
            "is_async": False,
            "visibility": "public",
            "class_name": None,
            "docstring": "",
            "inputs": "[]",
            "output": "",
            "raises": "[]",
            "complexity": 1,
            "annotations": "[]",
        })
        
    # Process functions/methods
    for m in func_matches:
        visibility = m.group(1) or "public"
        f_name = m.group(2)
        args_raw = m.group(3) or ""
        
        # Determine parent class if inside a class scope
        parent_class = None
        start_idx = m.start()
        start_line = get_line_num(start_idx)
        
        for c in reversed(classes_info):
            if start_idx > c["start_idx"]:
                parent_class = c["name"]
                break
                
        # Parse inputs
        inputs = []
        for arg in args_raw.split(','):
            arg = arg.strip()
            if arg:
                parts = arg.split()
                p_name = parts[-1] if parts else ""
                p_type = " ".join(parts[:-1]) if len(parts) > 1 else ""
                inputs.append({"name": p_name, "type": p_type})
                
        # Approximate raw code (from function declaration to end of method or next function)
        raw_code = code[start_idx:start_idx + 1000] # preview limit
        next_matches = [x.start() for x in func_matches if x.start() > start_idx]
        if next_matches:
            raw_code = code[start_idx:min(next_matches)]
            
        # Extract calls within this function's raw code
        local_calls = []
        for c in all_calls:
            if c in raw_code and c != f_name:
                local_calls.append(c)
                
        nodes.append({
            "type": "method_definition" if parent_class else "function_definition",
            "name": f_name,
            "file": file_path,
            "start_line": start_line,
            "end_line": start_line + len(raw_code.splitlines()),
            "anchor": m.group(0),
            "calls": list(set(local_calls)),
            "parent": parent_class,
            "is_async": False,
            "visibility": visibility,
            "class_name": parent_class,
            "docstring": f"PHP Function {f_name}",
            "inputs": json.dumps(inputs),
            "output": "",
            "raises": "[]",
            "complexity": 1 + raw_code.count("if") + raw_code.count("foreach") + raw_code.count("while"),
            "annotations": "[]",
        })
        
    return {
        "file": file_path,
        "language": "php",
        "nodes": nodes,
        "imports": imports,
        "raw_code": code,
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

    # Handle PHP via Tree-Sitter (accurate AST + noise filtering)
    if lang_name == "php":
        return _parse_php_file_treesitter(file_path, source_bytes)

    parser = Parser(LANGUAGE_MAP[lang_name])
    tree = parser.parse(source_bytes)

    nodes = []
    _extract_nodes(tree.root_node, source_bytes, file_path, lang_name, nodes)

    imports = _extract_imports(tree.root_node, source_bytes, file_path, lang_name)

    return {
        "file": file_path,
        "language": lang_name,
        "nodes": nodes,
        "imports": imports,
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
        first_line = raw_code.splitlines()[0].strip() if raw_code else ""

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
            "anchor": first_line,
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


def _extract_imports(root_node, source_bytes: bytes, file_path: str, lang: str) -> list[dict]:
    """
    Extract all import statements from a file's AST.
    Returns list of dicts with: module, full_path, alias, names, is_external, is_stdlib, source_file.
    """
    imports = []

    def _get_text(node):
        return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

    def _walk_imports(node):
        # ── Python ──
        if lang == "python":
            # import X / import X as Y / import X, Y
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        module_name = _get_text(child)
                        root_mod = module_name.split(".")[0]
                        imports.append({
                            "module": root_mod,
                            "full_path": module_name,
                            "alias": "",
                            "names": [],
                            "is_external": root_mod not in _PYTHON_STDLIB,
                            "is_stdlib": root_mod in _PYTHON_STDLIB,
                            "source_file": file_path,
                        })
                    elif child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        alias_node = child.child_by_field_name("alias")
                        if name_node:
                            module_name = _get_text(name_node)
                            root_mod = module_name.split(".")[0]
                            imports.append({
                                "module": root_mod,
                                "full_path": module_name,
                                "alias": _get_text(alias_node) if alias_node else "",
                                "names": [],
                                "is_external": root_mod not in _PYTHON_STDLIB,
                                "is_stdlib": root_mod in _PYTHON_STDLIB,
                                "source_file": file_path,
                            })

            # from X import Y / from X import Y as Z
            elif node.type == "import_from_statement":
                module_node = node.child_by_field_name("module_name")
                module_name = _get_text(module_node) if module_node else ""
                root_mod = module_name.split(".")[0] if module_name else ""

                # Check for relative imports (from . import / from .. import)
                is_relative = False
                for child in node.children:
                    if _get_text(child) in (".", ".."):
                        is_relative = True
                        break

                names = []
                alias = ""
                for child in node.children:
                    if child.type == "dotted_name" and child != module_node:
                        names.append(_get_text(child))
                    elif child.type == "aliased_import":
                        name_n = child.child_by_field_name("name")
                        alias_n = child.child_by_field_name("alias")
                        if name_n:
                            names.append(_get_text(name_n))
                        if alias_n:
                            alias = _get_text(alias_n)

                if is_relative:
                    is_ext = False
                    is_std = False
                else:
                    is_ext = root_mod not in _PYTHON_STDLIB and root_mod != ""
                    is_std = root_mod in _PYTHON_STDLIB

                if module_name or names:
                    imports.append({
                        "module": root_mod,
                        "full_path": module_name,
                        "alias": alias,
                        "names": names,
                        "is_external": is_ext,
                        "is_stdlib": is_std,
                        "source_file": file_path,
                    })

        # ── JavaScript / TypeScript ──
        elif lang in ("javascript", "typescript"):
            # import X from 'Y' / import { A, B } from 'Y'
            if node.type == "import_statement":
                source_node = node.child_by_field_name("source")
                module_name = ""
                if source_node:
                    module_name = _get_text(source_node).strip("'\"")

                root_mod = module_name.split("/")[0] if module_name else ""
                # Relative imports start with . or ..
                is_relative = module_name.startswith(".")
                names = []
                alias = ""
                for child in node.children:
                    if child.type == "import_clause":
                        for sub in child.children:
                            if sub.type == "identifier":
                                alias = _get_text(sub)
                            elif sub.type == "named_imports":
                                for spec in sub.children:
                                    if spec.type == "import_specifier":
                                        name_n = spec.child_by_field_name("name")
                                        if name_n:
                                            names.append(_get_text(name_n))

                if module_name:
                    imports.append({
                        "module": root_mod,
                        "full_path": module_name,
                        "alias": alias,
                        "names": names,
                        "is_external": not is_relative,
                        "is_stdlib": False,
                        "source_file": file_path,
                    })

            # const X = require('Y')
            if node.type == "lexical_declaration" or node.type == "variable_declaration":
                raw = _get_text(node)
                req_match = re.search(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", raw)
                if req_match:
                    module_name = req_match.group(1)
                    root_mod = module_name.split("/")[0]
                    is_relative = module_name.startswith(".")
                    imports.append({
                        "module": root_mod,
                        "full_path": module_name,
                        "alias": "",
                        "names": [],
                        "is_external": not is_relative,
                        "is_stdlib": False,
                        "source_file": file_path,
                    })

        for child in node.children:
            _walk_imports(child)

    _walk_imports(root_node)

    # Post-process: mark internal imports (module exists inside codebase)
    codebase_modules = set()
    try:
        for item in os.listdir(CODEBASE_PATH):
            name = item.replace(".py", "").replace(".js", "").replace(".ts", "")
            codebase_modules.add(name)
    except Exception:
        pass

    for imp in imports:
        if imp["module"] in codebase_modules:
            imp["is_external"] = False
            imp["is_stdlib"] = False

    return imports


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
