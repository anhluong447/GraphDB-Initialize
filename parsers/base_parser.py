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
        from parsers.php_parser import _parse_php_file_treesitter
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


def _extract_class_attributes(class_node, source_bytes: bytes, lang: str, decorators: list[str]) -> list[dict]:
    """Extract attributes defined in class body or within __init__ method."""
    attributes = []
    is_dataclass = "dataclass" in decorators or any("dataclass" in d for d in decorators)

    body = class_node.child_by_field_name("body")
    if not body:
        return []

    def walk(node, in_init=False):
        is_init_method = False
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore")
                if name_text == "__init__":
                    is_init_method = True

        # Extract self.x = ... inside __init__
        if in_init and node.type == "assignment":
            left = node.child_by_field_name("left") or node.child_by_field_name("name")
            right = node.child_by_field_name("right") or node.child_by_field_name("value")
            if left and left.type == "attribute":
                obj = left.child_by_field_name("object")
                attr = left.child_by_field_name("attribute")
                if obj and attr:
                    obj_text = source_bytes[obj.start_byte:obj.end_byte].decode("utf-8", errors="ignore")
                    if obj_text == "self":
                        attr_name = source_bytes[attr.start_byte:attr.end_byte].decode("utf-8", errors="ignore")
                        val_text = ""
                        if right:
                            val_text = source_bytes[right.start_byte:right.end_byte].decode("utf-8", errors="ignore").strip()
                        if not any(a["name"] == attr_name for a in attributes):
                            attributes.append({
                                "name": attr_name,
                                "type_hint": "",
                                "default_value": val_text or None,
                                "is_dataclass_field": False
                            })

        # Extract class-level fields (annotated_assignment or normal assignment)
        elif not in_init and node.parent == body:
            target_node = None
            if node.type == "expression_statement":
                for child in node.children:
                    if child.type in ("assignment", "annotated_assignment"):
                        target_node = child
                        break
            elif node.type in ("assignment", "annotated_assignment"):
                target_node = node

            if target_node:
                left = target_node.child_by_field_name("left") or target_node.child_by_field_name("name")
                if not left and target_node.children:
                    left = target_node.children[0]
                    
                if left and left.type == "identifier":
                    attr_name = source_bytes[left.start_byte:left.end_byte].decode("utf-8", errors="ignore")
                    
                    type_node = target_node.child_by_field_name("type") or target_node.child_by_field_name("annotation")
                    if not type_node:
                        for child in target_node.children:
                            if child.type == "type":
                                type_node = child
                                break
                    
                    type_text = ""
                    if type_node:
                        type_text = source_bytes[type_node.start_byte:type_node.end_byte].decode("utf-8", errors="ignore").strip()
                        
                    right = target_node.child_by_field_name("right") or target_node.child_by_field_name("value")
                    if not right:
                        # Find child after '=' or the last child
                        found_eq = False
                        for child in target_node.children:
                            if child.type == "=":
                                found_eq = True
                                continue
                            if found_eq:
                                right = child
                                break
                                
                    val_text = ""
                    if right and right != left and right != type_node:
                        val_text = source_bytes[right.start_byte:right.end_byte].decode("utf-8", errors="ignore").strip()
                        if val_text == "=":
                            val_text = ""
                            
                    attributes.append({
                        "name": attr_name,
                        "type_hint": type_text,
                        "default_value": val_text or None,
                        "is_dataclass_field": is_dataclass
                    })

        for child in node.children:
            walk(child, in_init=in_init or is_init_method)

    walk(body)
    return attributes


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

        # Extract class attributes, superclasses, and entry point flag
        class_attributes = []
        superclasses = []
        is_entry_point = False
        if not is_func:
            class_attributes = _extract_class_attributes(node, source_bytes, lang, decorators)
            # Extract superclasses (base classes)
            argument_list = node.child_by_field_name("superclasses")
            if not argument_list:
                for child in node.children:
                    if child.type == "argument_list":
                        argument_list = child
                        break
            if argument_list:
                for arg in argument_list.children:
                    if arg.type in ("identifier", "attribute"):
                        superclasses.append(source_bytes[arg.start_byte:arg.end_byte].decode("utf-8", errors="ignore"))
        else:
            is_entry_point = any(name.startswith(p) for p in ['load_', 'on_', 'setup_', 'init_', 'start_', 'register_'])

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
            "attributes": class_attributes,        # Parsed attributes
            "superclasses": json.dumps(superclasses), # JSON string of base classes
            "is_entry_point": is_entry_point,     # Boolean flag for entry point (Fix B)
        })

        # Track parent class name for methods
        new_parent = name if not is_func else parent_class
        for child in node.children:
            _extract_nodes(child, source_bytes, file_path, lang, result, new_parent)
        return

    for child in node.children:
        _extract_nodes(child, source_bytes, file_path, lang, result, parent_class)


def _extract_is_async(node, source_bytes: bytes) -> bool:
    """Check if a function/method is declared as async."""
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

    if lang == "python":
        for child in body.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        raw = source_bytes[sub.start_byte:sub.end_byte].decode("utf-8", errors="ignore")
                        raw = raw.strip()
                        for q in ('"""', "'''"):
                            if raw.startswith(q) and raw.endswith(q):
                                raw = raw[3:-3].strip()
                                break
                        return raw
                break
            elif child.type in ("comment",):
                continue
            else:
                break

    if lang in ("javascript", "typescript"):
        parent = node.parent
        if parent:
            prev_sibling = node.prev_named_sibling
            if prev_sibling and prev_sibling.type == "comment":
                raw = source_bytes[prev_sibling.start_byte:prev_sibling.end_byte].decode("utf-8", errors="ignore")
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
        raw = source_bytes[param_node.start_byte:param_node.end_byte].decode("utf-8", errors="ignore")
        name = raw
    elif param_node.type == "parameter":
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
    boolean_ops = {"and", "or", "&&", "||"}

    count = 1

    def _walk(n):
        nonlocal count
        if n.type in decision_types:
            count += 1
        if n.type in ("boolean_operator", "binary_expression"):
            op_node = n.child_by_field_name("operator")
            if op_node:
                op_text = source_bytes[op_node.start_byte:op_node.end_byte].decode("utf-8", errors="ignore")
                if op_text in boolean_ops:
                    count += 1
        for child in n.children:
            _walk(child)

    _walk(node)
    return count


def _extract_decorators(node, source_bytes: bytes, lang: str) -> list[str]:
    """Extract Python decorators or JS/TS annotations."""
    decorators = []
    if lang == "python":
        parent = node.parent
        if parent and parent.type == "decorated_definition":
            for child in parent.children:
                if child.type == "decorator":
                    raw = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
                    decorators.append(raw.strip("@").strip())
    return decorators


def _extract_calls(node, source_bytes: bytes) -> list[str]:
    """Extract all function/method call names inside this node."""
    calls = set()
    def _walk(n):
        if n.type == "call":
            func = n.child_by_field_name("function")
            if func:
                # Handle direct calls: foo()
                if func.type == "identifier":
                    name = source_bytes[func.start_byte:func.end_byte].decode("utf-8", errors="ignore")
                    calls.add(name)
                # Handle method calls: obj.foo()
                elif func.type == "attribute":
                    attribute = func.child_by_field_name("attribute")
                    if attribute:
                        name = source_bytes[attribute.start_byte:attribute.end_byte].decode("utf-8", errors="ignore")
                        calls.add(name)
        for child in n.children:
            _walk(child)
    _walk(node)
    return sorted(list(calls))


def _extract_imports(root_node, source_bytes: bytes, file_path: str, lang: str) -> list[dict]:
    """Extract import statements from JS, TS, or Python AST."""
    imports = []

    def _walk(node):
        if lang == "python":
            if node.type == "import_statement":
                # import foo, bar
                for child in node.children:
                    if child.type == "dotted_name":
                        name = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
                        mod = name.split(".")[0]
                        imports.append({
                            "module": mod,
                            "full_path": name,
                            "alias": "",
                            "names": [],
                            "is_external": mod not in _PYTHON_STDLIB,
                            "is_stdlib": mod in _PYTHON_STDLIB,
                            "source_file": file_path,
                        })
            elif node.type == "import_from_statement":
                # from foo import bar
                module_node = node.child_by_field_name("module_name")
                if module_node:
                    mod_path = source_bytes[module_node.start_byte:module_node.end_byte].decode("utf-8", errors="ignore")
                    root_mod = mod_path.split(".")[0]
                    # Names imported
                    names = []
                    names_node = node.child_by_field_name("name")
                    if names_node:
                        if names_node.type == "dotted_name":
                            names.append(source_bytes[names_node.start_byte:names_node.end_byte].decode("utf-8", errors="ignore"))
                        elif names_node.type == "wildcard_import":
                            names.append("*")
                    for child in node.children:
                        if child.type == "aliased_import":
                            name_child = child.child_by_field_name("name")
                            if name_child:
                                names.append(source_bytes[name_child.start_byte:name_child.end_byte].decode("utf-8", errors="ignore"))
                        elif child.type == "dotted_name" and child != module_node:
                            names.append(source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore"))

                    imports.append({
                        "module": root_mod,
                        "full_path": mod_path,
                        "alias": "",
                        "names": names,
                        "is_external": root_mod not in _PYTHON_STDLIB,
                        "is_stdlib": root_mod in _PYTHON_STDLIB,
                        "source_file": file_path,
                    })

        elif lang in ("javascript", "typescript"):
            if node.type == "import_statement":
                # import { foo } from 'bar' or import foo from 'bar'
                source_node = node.child_by_field_name("source")
                if source_node:
                    full_path = source_bytes[source_node.start_byte:source_node.end_byte].decode("utf-8", errors="ignore").strip("'\";")
                    root_mod = full_path.split("/")[0] if "/" in full_path else full_path
                    is_external = not (full_path.startswith(".") or full_path.startswith("/"))
                    
                    names = []
                    clause = node.child_by_field_name("clause")
                    if clause:
                        # Named imports
                        for child in clause.children:
                            if child.type == "named_imports":
                                for sub in child.children:
                                    if sub.type == "import_specifier":
                                        name_node = sub.child_by_field_name("name")
                                        if name_node:
                                            names.append(source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore"))
                            elif child.type == "identifier":
                                names.append(source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore"))
                            elif child.type == "namespace_import":
                                for sub in child.children:
                                    if sub.type == "identifier":
                                        names.append(source_bytes[sub.start_byte:sub.end_byte].decode("utf-8", errors="ignore"))
                                        
                    imports.append({
                        "module": root_mod,
                        "full_path": full_path,
                        "alias": "",
                        "names": names,
                        "is_external": is_external,
                        "is_stdlib": False,
                        "source_file": file_path,
                    })

        for child in node.children:
            _walk(child)

    _walk(root_node)
    return imports


def parse_codebase(path: str = CODEBASE_PATH) -> list[dict]:
    """Walk directories, parse all supported codebase files, return results."""
    parsed_files = []
    for root, dirs, files in os.walk(path):
        # Skip ignored dirs
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            ext = Path(file).suffix
            if ext in SUPPORTED_LANGUAGES:
                file_path = os.path.join(root, file).replace("\\", "/")
                res = parse_file(file_path)
                if res:
                    parsed_files.append(res)
    return parsed_files
