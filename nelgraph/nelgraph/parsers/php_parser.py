import re
import json
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_php as tsphp

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
    class_matches = list(re.finditer(r'(?:abstract\s+|final\s+)?class\s+(\w+)', code))
    func_regex = r'(?:(public|protected|private)\s+)?(?:static\s+)?function\s+(\w+)\s*\(([^)]*)\)'
    func_matches = list(re.finditer(func_regex, code))
    
    line_starts = []
    curr = 0
    for line in lines:
        line_starts.append(curr)
        curr += len(line) + 1
        
    def get_line_num(char_idx):
        import bisect
        return bisect.bisect_right(line_starts, char_idx)
        
    call_regex = r'(?:\$this->|(\w+)::)(\w+)\s*\('
    all_calls = []
    for m in re.finditer(call_regex, code):
        all_calls.append(m.group(2))
    for m in re.finditer(r'\b(\w+)\s*\((?!\s*function\b)', code):
        func_called = m.group(1)
        if func_called not in ("if", "for", "while", "foreach", "switch", "catch", "array", "isset", "empty", "unset", "count"):
            all_calls.append(func_called)
            
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
            "end_line": start_line + 5,
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
        
    for m in func_matches:
        visibility = m.group(1) or "public"
        f_name = m.group(2)
        args_raw = m.group(3) or ""
        
        parent_class = None
        start_idx = m.start()
        start_line = get_line_num(start_idx)
        
        for c in reversed(classes_info):
            if start_idx > c["start_idx"]:
                parent_class = c["name"]
                break
                
        inputs = []
        for arg in args_raw.split(','):
            arg = arg.strip()
            if arg:
                parts = arg.split()
                p_name = parts[-1] if parts else ""
                p_type = " ".join(parts[:-1]) if len(parts) > 1 else ""
                inputs.append({"name": p_name, "type": p_type})
                
        raw_code = code[start_idx:start_idx + 1000]
        next_matches = [x.start() for x in func_matches if x.start() > start_idx]
        if next_matches:
            raw_code = code[start_idx:min(next_matches)]
            
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
