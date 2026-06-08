# Hướng dẫn triển khai Full GraphRAG (Mức 3)

> Tài liệu này dành cho AI agent tự động triển khai hệ thống Knowledge Graph kết hợp vector search,
> community detection, và visualization cho một codebase bất kỳ.

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Cấu trúc thư mục](#2-cấu-trúc-thư-mục)
3. [Phase 1 — Multi-source Parser](#3-phase-1--multi-source-parser)
4. [Phase 2 — LLM-assisted Entity Extraction](#4-phase-2--llm-assisted-entity-extraction)
5. [Phase 3 — Graph Store (Neo4j)](#5-phase-3--graph-store-neo4j)
6. [Phase 4 — Embedding](#6-phase-4--embedding)
7. [Phase 5 — Community Detection](#7-phase-5--community-detection)
8. [Phase 6 — Query Engine](#8-phase-6--query-engine)
9. [Phase 7 — MCP Interface](#9-phase-7--mcp-interface)
10. [Phase 8 — Incremental Updater](#10-phase-8--incremental-updater)
11. [Phase 9 — Visualization](#11-phase-9--visualization)
12. [Chạy toàn bộ hệ thống](#12-chạy-toàn-bộ-hệ-thống)
13. [Checklist kiểm tra](#13-checklist-kiểm-tra)

---

## 1. Tổng quan kiến trúc

```
Codebase + Docs + Git History + GitHub Issues
                    │
           [Phase 1] Multi-source Parser
                    │
           [Phase 2] LLM Entity Extractor
                    │
           [Phase 3] Neo4j Graph Store
                    │
           [Phase 4] Embedder (vector gắn vào node)
                    │
           [Phase 5] Community Detection (Leiden)
                    │
           [Phase 6] Query Engine (hybrid: graph + vector + summary)
                    │
           [Phase 7] MCP Interface (tools cho agent)
                    │
           [Phase 8] Incremental Updater (file watcher + git hook)
                    │
           [Phase 9] Visualization Dashboard (web UI)
```

**Stack chính:**

| Thành phần | Công nghệ |
|---|---|
| Parser | `tree-sitter`, `gitpython`, `remark` |
| LLM Extraction | Anthropic Claude API (claude-sonnet-4-20250514) |
| Graph DB | Neo4j 5.x (local Docker) |
| Vector Store | ChromaDB |
| Embedding Model | `text-embedding-3-small` (OpenAI) hoặc `nomic-embed` (local) |
| Community Detection | `graspologic` (Leiden algorithm) |
| Backend API | FastAPI (Python) |
| MCP Server | `@modelcontextprotocol/sdk` (Node.js) |
| Visualization | React + `react-force-graph` + Tailwind CSS |

---

## 2. Cấu trúc thư mục

Tạo cấu trúc sau trước khi bắt đầu:

```
graphrag/
├── parsers/
│   ├── ast_parser.py          # tree-sitter, parse source code
│   ├── doc_parser.py          # parse markdown, comments
│   ├── git_parser.py          # parse git history
│   └── github_parser.py       # parse PR, issues (optional)
├── extractors/
│   └── llm_extractor.py       # LLM-assisted entity extraction
├── graph/
│   ├── neo4j_client.py        # kết nối và query Neo4j
│   ├── schema.py              # định nghĩa node labels, relation types
│   └── builder.py             # build graph từ parser output
├── embeddings/
│   ├── embedder.py            # tạo vector cho mỗi node
│   └── chroma_client.py       # lưu và query vector
├── community/
│   ├── detector.py            # Leiden algorithm
│   └── summarizer.py          # LLM summarize mỗi community
├── query/
│   └── engine.py              # hybrid query: vector + graph + summary
├── mcp/
│   ├── server.ts              # MCP server
│   └── tools.ts               # định nghĩa tools
├── updater/
│   ├── watcher.py             # file watcher
│   └── git_hook.py            # post-commit hook
├── visualization/
│   ├── backend/
│   │   └── api.py             # FastAPI endpoints cho viz
│   └── frontend/
│       ├── index.html
│       ├── App.jsx
│       └── components/
│           ├── GraphCanvas.jsx
│           ├── NodeDetail.jsx
│           ├── CommunityPanel.jsx
│           └── SearchBar.jsx
├── config.py                  # cấu hình toàn cục
├── initialize_graph.py        # entry point, chạy full pipeline
└── docker-compose.yml         # Neo4j (ChromaDB chạy cục bộ)
```

---

## 3. Phase 1 — Multi-source Parser

### 3.1 Cài đặt dependencies

```bash
pip install tree-sitter tree-sitter-python tree-sitter-javascript \
            tree-sitter-typescript gitpython requests python-dotenv
```

### 3.2 `config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

CODEBASE_PATH = os.getenv("CODEBASE_PATH", "./target_project")
SUPPORTED_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
}
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")  # format: "owner/repo"
```

### 3.3 `parsers/ast_parser.py`

```python
import os
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
from config import CODEBASE_PATH, SUPPORTED_LANGUAGES, IGNORE_DIRS

PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())

LANGUAGE_MAP = {
    "python": PY_LANGUAGE,
    "javascript": JS_LANGUAGE,
    "typescript": JS_LANGUAGE,
}

def parse_file(file_path: str) -> dict:
    """
    Parse một file, trả về dict gồm:
    - file: đường dẫn file
    - language: ngôn ngữ
    - nodes: list[dict] các function/class/variable
    - raw_code: toàn bộ source code của file
    """
    ext = Path(file_path).suffix
    lang_name = SUPPORTED_LANGUAGES.get(ext)
    if not lang_name:
        return None

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        source = f.read()

    parser = Parser(LANGUAGE_MAP[lang_name])
    tree = parser.parse(bytes(source, "utf-8"))

    nodes = []
    _extract_nodes(tree.root_node, source, file_path, nodes)

    return {
        "file": file_path,
        "language": lang_name,
        "nodes": nodes,
        "raw_code": source,
    }

def _extract_nodes(node, source: str, file_path: str, result: list, parent=None):
    """Đệ quy qua AST, extract function/class definitions."""
    extractable = {
        "function_definition", "function_declaration",
        "class_definition", "class_declaration",
        "method_definition", "arrow_function",
    }

    if node.type in extractable:
        name_node = node.child_by_field_name("name")
        name = source[name_node.start_byte:name_node.end_byte] if name_node else "anonymous"
        raw_code = source[node.start_byte:node.end_byte]

        # Extract function calls bên trong
        calls = _extract_calls(node, source)

        result.append({
            "type": node.type,
            "name": name,
            "file": file_path,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "raw_code": raw_code[:2000],  # giới hạn 2000 ký tự
            "calls": calls,
            "parent": parent,
        })
        parent = name

    for child in node.children:
        _extract_nodes(child, source, file_path, result, parent)

def _extract_calls(node, source: str) -> list[str]:
    """Tìm tất cả function calls trong một node."""
    calls = []
    if node.type == "call":
        func_node = node.child_by_field_name("function")
        if func_node:
            calls.append(source[func_node.start_byte:func_node.end_byte])
    for child in node.children:
        calls.extend(_extract_calls(child, source))
    return list(set(calls))

def parse_codebase(path: str = CODEBASE_PATH) -> list[dict]:
    """Parse toàn bộ codebase, trả về list các file đã parse."""
    results = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            file_path = os.path.join(root, file)
            parsed = parse_file(file_path)
            if parsed:
                results.append(parsed)
    print(f"Parsed {len(results)} files.")
    return results
```

### 3.4 `parsers/git_parser.py`

```python
import git
from config import CODEBASE_PATH

def parse_git_history(path: str = CODEBASE_PATH, max_commits: int = 500) -> list[dict]:
    """
    Parse git history, trả về list commits gồm:
    - hash, author, date, message, files_changed
    """
    try:
        repo = git.Repo(path)
    except git.InvalidGitRepositoryError:
        print("Không tìm thấy git repo.")
        return []

    commits = []
    for commit in list(repo.iter_commits())[:max_commits]:
        try:
            files_changed = list(commit.stats.files.keys())
        except Exception:
            files_changed = []

        commits.append({
            "hash": commit.hexsha[:8],
            "author": commit.author.name,
            "author_email": commit.author.email,
            "date": commit.committed_datetime.isoformat(),
            "message": commit.message.strip(),
            "files_changed": files_changed,
        })

    print(f"Parsed {len(commits)} commits.")
    return commits

def parse_git_blame(file_path: str, repo_path: str = CODEBASE_PATH) -> dict:
    """Trả về map từ line number → author cho một file."""
    try:
        repo = git.Repo(repo_path)
        blame = repo.blame("HEAD", file_path)
        blame_map = {}
        line_num = 1
        for commit, lines in blame:
            for _ in lines:
                blame_map[line_num] = commit.author.name
                line_num += 1
        return blame_map
    except Exception:
        return {}
```

### 3.5 `parsers/doc_parser.py`

```python
import os
import re
from pathlib import Path
from config import CODEBASE_PATH, IGNORE_DIRS

def parse_docs(path: str = CODEBASE_PATH) -> list[dict]:
    """Parse tất cả markdown files và extract chunks."""
    docs = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            if file.endswith((".md", ".mdx", ".txt", ".rst")):
                file_path = os.path.join(root, file)
                chunks = _chunk_doc(file_path)
                docs.extend(chunks)
    print(f"Parsed {len(docs)} doc chunks.")
    return docs

def _chunk_doc(file_path: str, chunk_size: int = 1000) -> list[dict]:
    """Chia một doc file thành chunks theo heading hoặc kích thước."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Split theo headings (## hoặc ###)
    sections = re.split(r'\n(?=#{1,3} )', content)
    chunks = []
    for i, section in enumerate(sections):
        if len(section.strip()) < 50:
            continue
        # Extract heading
        heading_match = re.match(r'^#{1,3} (.+)', section)
        heading = heading_match.group(1) if heading_match else f"Section {i}"

        chunks.append({
            "file": file_path,
            "type": "doc_chunk",
            "heading": heading,
            "content": section[:chunk_size],
        })
    return chunks
```

---

## 4. Phase 2 — LLM-assisted Entity Extraction

### 4.1 `extractors/llm_extractor.py`

```python
import json
import anthropic
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

EXTRACTION_PROMPT = """You are a code knowledge graph builder.

Given the following code/documentation chunk, extract:
1. High-level entities (NOT the functions themselves, those are already captured).
   Entity types: Feature, Concept, Decision, Risk, Task, Module
2. Relations between entities AND between entities and code elements.

RULES:
- Entity names must be concise (2-5 words max)
- Be consistent with naming across chunks (use canonical names)
- Only extract entities that are genuinely meaningful, not every variable
- Tasks must be actionable (e.g. "Implement refresh token", "Fix null check in payment")
- Risks must be concrete (e.g. "No rate limiting on auth endpoint")

Return ONLY valid JSON in this exact format:
{
  "entities": [
    {"name": "string", "type": "Feature|Concept|Decision|Risk|Task|Module", "description": "string (max 100 chars)"}
  ],
  "relations": [
    {"from": "string", "relation": "implements|depends_on|relates_to|conflicts_with|blocks|owned_by|introduces", "to": "string"}
  ]
}

Chunk to analyze:
"""

def extract_entities_from_chunk(chunk_text: str, chunk_meta: dict) -> dict:
    """Gọi LLM để extract entities và relations từ một chunk."""
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT + chunk_text[:3000]
            }]
        )
        raw = response.content[0].text.strip()
        # Strip markdown nếu có
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        result["source"] = chunk_meta
        return result
    except (json.JSONDecodeError, Exception) as e:
        print(f"Extraction error for chunk {chunk_meta.get('file', '')}: {e}")
        return {"entities": [], "relations": [], "source": chunk_meta}

def extract_from_commit(commit: dict) -> dict:
    """Extract semantic info từ git commit message."""
    prompt = f"""Analyze this git commit and extract:
- Any tasks completed (type: Task, past tense)
- Any bugs fixed (type: Risk that was resolved)
- Any decisions made (type: Decision)

Commit: {commit['message']}
Files changed: {', '.join(commit['files_changed'][:10])}

Return ONLY valid JSON:
{{"entities": [...], "relations": [...]}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception:
        return {"entities": [], "relations": []}

def batch_extract(chunks: list[dict], batch_size: int = 10) -> list[dict]:
    """Extract entities từ list chunks, có cache đơn giản."""
    results = []
    for i, chunk in enumerate(chunks):
        print(f"Extracting {i+1}/{len(chunks)}...")
        text = chunk.get("content") or chunk.get("raw_code", "")
        if len(text.strip()) < 100:
            continue
        result = extract_entities_from_chunk(text, chunk)
        results.append(result)
    return results
```

---

## 5. Phase 3 — Graph Store (Neo4j)

### 5.1 Docker setup

Tạo file `docker-compose.yml`:

```yaml
version: "3.8"
services:
  neo4j:
    image: neo4j:5.15-community
    ports:
      - "7474:7474"   # HTTP (Neo4j Browser)
      - "7687:7687"   # Bolt
    environment:
      NEO4J_AUTH: neo4j/password
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
      NEO4J_dbms_security_procedures_unrestricted: "apoc.*,gds.*"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
```

Khởi động: `docker-compose up -d`

### 5.2 `graph/neo4j_client.py`

```python
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    def run(self, query: str, params: dict = None):
        with self.driver.session() as session:
            return list(session.run(query, params or {}))

    def create_indexes(self):
        """Tạo indexes để query nhanh hơn."""
        indexes = [
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Function) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Class) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:File) ON (n.path)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Concept) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Feature) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Task) ON (n.name)",
            "CREATE INDEX node_name IF NOT EXISTS FOR (n:Community) ON (n.id)",
        ]
        for idx in indexes:
            try:
                self.run(idx)
            except Exception as e:
                print(f"Index warning: {e}")
        print("Indexes created.")

    def clear_all(self):
        """Xóa toàn bộ graph (dùng khi rebuild)."""
        self.run("MATCH (n) DETACH DELETE n")
        print("Graph cleared.")

# Singleton
_client = None
def get_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
```

### 5.3 `graph/builder.py`

```python
from graph.neo4j_client import get_client

def build_file_nodes(parsed_files: list[dict]):
    """Tạo File nodes và Function/Class nodes từ AST output."""
    client = get_client()
    for parsed in parsed_files:
        # Tạo File node
        client.run("""
            MERGE (f:File {path: $path})
            SET f.language = $language
        """, {"path": parsed["file"], "language": parsed["language"]})

        for node in parsed["nodes"]:
            label = _node_type_to_label(node["type"])

            # Tạo Function/Class node
            client.run(f"""
                MERGE (n:{label} {{name: $name, file: $file}})
                SET n.start_line = $start_line,
                    n.end_line = $end_line,
                    n.raw_code = $raw_code
            """, {
                "name": node["name"],
                "file": node["file"],
                "start_line": node["start_line"],
                "end_line": node["end_line"],
                "raw_code": node.get("raw_code", "")[:1000],
            })

            # CONTAINS edge: File → Function
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
                    "callee": called.split(".")[-1],  # normalize "obj.method" → "method"
                })

    print("File and function nodes built.")

def build_git_nodes(commits: list[dict]):
    """Tạo Commit và Person nodes từ git history."""
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

        # MODIFIED edges: Commit → File
        for file_path in commit["files_changed"]:
            client.run("""
                MATCH (c:Commit {hash: $hash})
                MERGE (f:File {path: $path})
                MERGE (c)-[:MODIFIED {date: $date}]->(f)
            """, {"hash": commit["hash"], "path": file_path, "date": commit["date"]})

    print("Git nodes built.")

def build_semantic_nodes(extraction_results: list[dict]):
    """Tạo Concept/Feature/Decision/Risk/Task nodes từ LLM extraction."""
    client = get_client()
    for result in extraction_results:
        for entity in result.get("entities", []):
            label = entity["type"]  # Feature, Concept, Decision, Risk, Task, Module
            client.run(f"""
                MERGE (n:{label} {{name: $name}})
                SET n.description = $description
            """, {"name": entity["name"], "description": entity.get("description", "")})

        for rel in result.get("relations", []):
            from_name = rel["from"]
            to_name = rel["to"]
            relation = rel["relation"].upper()

            # Tìm node từ tên (bất kể label)
            client.run(f"""
                MATCH (a) WHERE a.name = $from_name
                MATCH (b) WHERE b.name = $to_name
                MERGE (a)-[:{relation}]->(b)
            """, {"from_name": from_name, "to_name": to_name})

    print("Semantic nodes built.")

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
```

---

## 6. Phase 4 — Embedding

### 6.1 Cài đặt

```bash
pip install openai chromadb
```

### 6.2 `embeddings/embedder.py`

```python
import openai
from config import OPENAI_API_KEY
from graph.neo4j_client import get_client

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

def build_node_text(node_record: dict) -> str:
    """
    Tổng hợp text biểu diễn đầy đủ một node, bao gồm quan hệ trong graph.
    Đây là bước quan trọng — vector cần mang thông tin quan hệ, không chỉ nội dung.
    """
    name = node_record.get("name", "")
    node_type = node_record.get("type", "")
    description = node_record.get("description", "")
    raw_code = node_record.get("raw_code", "")[:500]

    client = get_client()

    # Lấy neighbors từ graph
    result = client.run("""
        MATCH (n) WHERE n.name = $name
        OPTIONAL MATCH (n)-[r]->(neighbor)
        RETURN type(r) as rel_type, neighbor.name as neighbor_name
        LIMIT 20
    """, {"name": name})

    outgoing = [f"{r['rel_type']} → {r['neighbor_name']}" for r in result if r['neighbor_name']]

    result2 = client.run("""
        MATCH (n) WHERE n.name = $name
        OPTIONAL MATCH (neighbor)-[r]->(n)
        RETURN type(r) as rel_type, neighbor.name as neighbor_name
        LIMIT 10
    """, {"name": name})

    incoming = [f"{r['neighbor_name']} → {r['rel_type']}" for r in result2 if r['neighbor_name']]

    text = f"""
{node_type}: {name}
Description: {description}
Outgoing relations: {', '.join(outgoing) if outgoing else 'none'}
Incoming relations: {', '.join(incoming) if incoming else 'none'}
Code preview: {raw_code}
""".strip()

    return text

def embed_text(text: str) -> list[float]:
    """Embed một đoạn text thành vector."""
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],
    )
    return response.data[0].embedding
```

### 6.3 `embeddings/chroma_client.py`

```python
import chromadb
from embeddings.embedder import build_node_text, embed_text
from graph.neo4j_client import get_client
from config import CHROMA_PATH

chroma = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma.get_or_create_collection("graphrag_nodes")

def embed_all_nodes():
    """Embed tất cả nodes trong Neo4j và lưu vào Chroma."""
    client = get_client()

    labels = ["Function", "Class", "Concept", "Feature", "Decision", "Risk", "Task"]
    total = 0

    for label in labels:
        nodes = client.run(f"MATCH (n:{label}) RETURN n")
        batch_ids, batch_docs, batch_metas, batch_embeds = [], [], [], []

        for record in nodes:
            node = dict(record["n"])
            node["type"] = label
            node_id = f"{label}:{node.get('name', '')}:{node.get('file', '')}"

            text = build_node_text(node)
            vector = embed_text(text)

            batch_ids.append(node_id)
            batch_docs.append(text)
            batch_metas.append({"type": label, "name": node.get("name", ""), "file": node.get("file", "")})
            batch_embeds.append(vector)

            if len(batch_ids) >= 50:
                collection.upsert(ids=batch_ids, documents=batch_docs,
                                  metadatas=batch_metas, embeddings=batch_embeds)
                total += len(batch_ids)
                batch_ids, batch_docs, batch_metas, batch_embeds = [], [], [], []

        if batch_ids:
            collection.upsert(ids=batch_ids, documents=batch_docs,
                              metadatas=batch_metas, embeddings=batch_embeds)
            total += len(batch_ids)

    print(f"Embedded {total} nodes.")

def semantic_search(query: str, top_k: int = 10, filter_type: str = None) -> list[dict]:
    """Tìm các nodes liên quan nhất đến query bằng cosine similarity."""
    query_vector = embed_text(query)
    where = {"type": filter_type} if filter_type else None

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for i in range(len(results["ids"][0])):
        output.append({
            "id": results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "score": 1 - results["distances"][0][i],
        })
    return output
```

---

## 7. Phase 5 — Community Detection

### 7.1 Cài đặt

```bash
pip install graspologic networkx
```

### 7.2 `community/detector.py`

```python
import networkx as nx
from graspologic.partition import leiden
from graph.neo4j_client import get_client

def build_networkx_graph() -> nx.Graph:
    """Chuyển đổi Neo4j graph thành NetworkX graph để chạy thuật toán."""
    client = get_client()

    G = nx.Graph()

    # Lấy tất cả nodes
    nodes = client.run("MATCH (n) WHERE n.name IS NOT NULL RETURN id(n) as id, labels(n) as labels, n.name as name")
    for record in nodes:
        G.add_node(record["id"], name=record["name"], label=record["labels"][0] if record["labels"] else "Unknown")

    # Lấy tất cả edges
    edges = client.run("MATCH (a)-[r]->(b) WHERE a.name IS NOT NULL AND b.name IS NOT NULL RETURN id(a) as from_id, id(b) as to_id, type(r) as rel_type")
    for record in edges:
        G.add_edge(record["from_id"], record["to_id"], rel_type=record["rel_type"])

    print(f"NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G

def detect_communities() -> dict:
    """
    Chạy Leiden algorithm, trả về mapping node_id → community_id.
    Lưu community_id vào Neo4j.
    """
    G = build_networkx_graph()
    if G.number_of_nodes() == 0:
        print("Empty graph, skipping community detection.")
        return {}

    # Leiden algorithm
    partition = leiden(G)  # returns dict: node_id → community_id
    print(f"Detected {len(set(partition.values()))} communities.")

    # Lưu community vào Neo4j
    client = get_client()
    for node_id, community_id in partition.items():
        client.run("""
            MATCH (n) WHERE id(n) = $node_id
            SET n.community_id = $community_id
        """, {"node_id": node_id, "community_id": community_id})

    return partition
```

### 7.3 `community/summarizer.py`

```python
import anthropic
from graph.neo4j_client import get_client
from config import ANTHROPIC_API_KEY

client_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def get_community_members(community_id: int) -> list[dict]:
    """Lấy tất cả nodes thuộc một community."""
    client = get_client()
    result = client.run("""
        MATCH (n) WHERE n.community_id = $cid AND n.name IS NOT NULL
        RETURN labels(n) as labels, n.name as name, n.description as description
        LIMIT 50
    """, {"cid": community_id})

    return [{"type": r["labels"][0], "name": r["name"], "description": r["description"]} for r in result]

def summarize_community(community_id: int) -> str:
    """Dùng LLM để tạo summary ngắn gọn (~200 token) cho một community."""
    members = get_community_members(community_id)
    if not members:
        return ""

    members_text = "\n".join([f"- [{m['type']}] {m['name']}: {m['description'] or ''}" for m in members[:30]])

    prompt = f"""You are summarizing a cluster of related code elements for a developer knowledge graph.

Community members:
{members_text}

Write a 2-3 sentence summary of this community that answers:
1. What is the main purpose/theme of this group?
2. What are the key elements?
3. Any notable risks, tasks, or decisions?

Keep it under 200 words. Be specific, not generic."""

    response = client_ai.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()

def infer_community_name(community_id: int, summary: str) -> str:
    """Dùng LLM để đặt tên ngắn cho community."""
    response = client_ai.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=20,
        messages=[{"role": "user", "content": f"Give a 2-4 word name for this code community. Return ONLY the name:\n\n{summary}"}]
    )
    return response.content[0].text.strip()

def summarize_all_communities():
    """Summarize tất cả communities và lưu vào Neo4j."""
    client = get_client()

    # Lấy danh sách community IDs
    result = client.run("MATCH (n) WHERE n.community_id IS NOT NULL RETURN DISTINCT n.community_id as cid ORDER BY cid")
    community_ids = [r["cid"] for r in result]

    print(f"Summarizing {len(community_ids)} communities...")

    for cid in community_ids:
        summary = summarize_community(cid)
        name = infer_community_name(cid, summary) if summary else f"Community {cid}"

        # Tạo Community node
        client.run("""
            MERGE (c:Community {id: $cid})
            SET c.name = $name, c.summary = $summary
        """, {"cid": cid, "name": name, "summary": summary})

        # Tạo BELONGS_TO edges
        client.run("""
            MATCH (c:Community {id: $cid})
            MATCH (n) WHERE n.community_id = $cid AND NOT n:Community
            MERGE (n)-[:BELONGS_TO]->(c)
        """, {"cid": cid})

        print(f"  Community {cid}: '{name}'")

    print("All communities summarized.")
```

---

## 8. Phase 6 — Query Engine

### 8.1 `query/engine.py`

```python
from embeddings.chroma_client import semantic_search
from graph.neo4j_client import get_client

def query(question: str, top_k: int = 5) -> dict:
    """
    Hybrid query gồm 4 layers, tự động cascade từ nhanh/rẻ đến chậm/đắt.
    Trả về dict gồm community_context, relevant_nodes, subgraph_summary.
    """

    # Layer 1: Community lookup
    communities = _find_relevant_communities(question)

    # Layer 2: Semantic search trong communities liên quan
    relevant_nodes = semantic_search(question, top_k=top_k)

    # Layer 3: Graph expansion — lấy thêm neighbors
    expanded_nodes = _expand_neighbors(relevant_nodes)

    # Layer 4: Assemble context
    context = _assemble_context(communities, relevant_nodes, expanded_nodes)

    return {
        "question": question,
        "communities": communities,
        "relevant_nodes": relevant_nodes,
        "expanded_context": expanded_nodes,
        "summary": context,
    }

def _find_relevant_communities(question: str) -> list[dict]:
    """Tìm communities liên quan nhất dựa trên semantic search trong community summaries."""
    from embeddings.embedder import embed_text
    import chromadb
    from config import CHROMA_PATH

    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        comm_collection = chroma.get_collection("community_summaries")
        query_vector = embed_text(question)
        results = comm_collection.query(
            query_embeddings=[query_vector],
            n_results=3,
            include=["documents", "metadatas"],
        )
        communities = []
        for i in range(len(results["ids"][0])):
            communities.append({
                "id": results["ids"][0][i],
                "summary": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
            })
        return communities
    except Exception:
        return []

def _expand_neighbors(nodes: list[dict], hops: int = 1) -> list[dict]:
    """Mở rộng subgraph: lấy neighbors của top nodes."""
    client = get_client()
    expanded = []

    for node in nodes[:3]:  # Chỉ expand top-3 để tránh quá nhiều token
        name = node["metadata"].get("name", "")
        if not name:
            continue

        result = client.run("""
            MATCH (n) WHERE n.name = $name
            MATCH (n)-[r*1..2]-(neighbor)
            WHERE neighbor.name IS NOT NULL
            RETURN DISTINCT neighbor.name as name,
                   labels(neighbor)[0] as type,
                   neighbor.description as description
            LIMIT 10
        """, {"name": name})

        for record in result:
            expanded.append({
                "name": record["name"],
                "type": record["type"],
                "description": record["description"],
                "source_node": name,
            })

    return expanded

def _assemble_context(communities, nodes, expanded) -> str:
    """Tổng hợp context thành text ngắn gọn để đưa cho agent."""
    parts = []

    if communities:
        parts.append("## Relevant Areas")
        for c in communities:
            meta = c.get("metadata", {})
            parts.append(f"**{meta.get('name', 'Community')}**: {c['summary']}")

    if nodes:
        parts.append("\n## Key Elements")
        for n in nodes[:5]:
            meta = n.get("metadata", {})
            parts.append(f"- [{meta.get('type', '?')}] **{meta.get('name', '?')}**: {n.get('document', '')[:200]}")

    if expanded:
        parts.append("\n## Related Context")
        seen = set()
        for n in expanded[:8]:
            if n["name"] not in seen:
                parts.append(f"- [{n['type']}] {n['name']}: {n.get('description', '') or ''}")
                seen.add(n["name"])

    return "\n".join(parts)

def get_node_detail(name: str) -> dict:
    """Lấy toàn bộ thông tin của một node cụ thể."""
    client = get_client()
    result = client.run("""
        MATCH (n) WHERE n.name = $name
        OPTIONAL MATCH (n)-[r]->(neighbor)
        OPTIONAL MATCH (caller)-[r2]->(n)
        RETURN n,
               collect(DISTINCT {type: type(r), target: neighbor.name}) as outgoing,
               collect(DISTINCT {type: type(r2), source: caller.name}) as incoming
        LIMIT 1
    """, {"name": name})

    if not result:
        return {}

    record = result[0]
    return {
        "node": dict(record["n"]),
        "outgoing": record["outgoing"],
        "incoming": record["incoming"],
    }

def list_open_tasks() -> list[dict]:
    """Liệt kê tất cả Task nodes chưa được mark là done."""
    client = get_client()
    result = client.run("""
        MATCH (t:Task)
        WHERE NOT EXISTS(t.status) OR t.status <> 'done'
        OPTIONAL MATCH (t)-[:BLOCKS]->(blocked)
        RETURN t.name as name, t.description as description,
               collect(blocked.name) as blocks
        ORDER BY t.name
    """)
    return [dict(r) for r in result]
```

---

## 9. Phase 7 — MCP Interface

### 9.1 Cài đặt

```bash
npm install @modelcontextprotocol/sdk
```

### 9.2 `mcp/server.ts`

```typescript
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const API_BASE = process.env.GRAPHRAG_API || "http://localhost:8080";

const server = new Server(
  { name: "graphrag", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "ask_codebase",
      description: "Hỏi bất kỳ điều gì về dự án: tính năng, kiến trúc, luồng logic, dependencies. Trả về context đã được tóm tắt.",
      inputSchema: {
        type: "object",
        properties: { query: { type: "string", description: "Câu hỏi về codebase" } },
        required: ["query"],
      },
    },
    {
      name: "get_node_context",
      description: "Lấy toàn bộ thông tin chi tiết của một function, class, hoặc concept cụ thể.",
      inputSchema: {
        type: "object",
        properties: { name: { type: "string", description: "Tên của node" } },
        required: ["name"],
      },
    },
    {
      name: "get_community_summary",
      description: "Lấy tóm tắt một vùng chức năng trong dự án (ví dụ: Authentication, Payment).",
      inputSchema: {
        type: "object",
        properties: { community_name: { type: "string" } },
        required: ["community_name"],
      },
    },
    {
      name: "find_owner",
      description: "Tìm ai là người có nhiều đóng góp nhất vào một phần code.",
      inputSchema: {
        type: "object",
        properties: { query: { type: "string" } },
        required: ["query"],
      },
    },
    {
      name: "list_open_tasks",
      description: "Liệt kê các task, TODO, và rủi ro chưa được giải quyết trong dự án.",
      inputSchema: {
        type: "object",
        properties: { filter: { type: "string", description: "Lọc theo từ khóa (optional)" } },
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  const endpoints: Record<string, string> = {
    ask_codebase: `/query?q=${encodeURIComponent(args?.query as string)}`,
    get_node_context: `/node/${encodeURIComponent(args?.name as string)}`,
    get_community_summary: `/community/${encodeURIComponent(args?.community_name as string)}`,
    find_owner: `/owner?q=${encodeURIComponent(args?.query as string)}`,
    list_open_tasks: `/tasks${args?.filter ? `?filter=${encodeURIComponent(args.filter as string)}` : ""}`,
  };

  const url = `${API_BASE}${endpoints[name]}`;
  const res = await fetch(url);
  const data = await res.json();

  return {
    content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
  };
});

const transport = new StdioServerTransport();
await server.connect(transport);
```

---

## 10. Phase 8 — Incremental Updater

### 10.1 `updater/watcher.py`

```python
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from config import CODEBASE_PATH, SUPPORTED_LANGUAGES

class CodeChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.pending = set()
        self.last_process = 0

    def on_modified(self, event):
        if event.is_directory:
            return
        from pathlib import Path
        if Path(event.src_path).suffix in SUPPORTED_LANGUAGES:
            self.pending.add(event.src_path)
            self._debounced_process()

    def _debounced_process(self):
        now = time.time()
        if now - self.last_process > 5:  # 5 giây debounce
            self.last_process = now
            files = list(self.pending)
            self.pending.clear()
            self._reindex_files(files)

    def _reindex_files(self, files: list[str]):
        print(f"Re-indexing {len(files)} changed files...")
        from parsers.ast_parser import parse_file
        from graph.builder import build_file_nodes
        from embeddings.chroma_client import embed_all_nodes

        parsed = [parse_file(f) for f in files if parse_file(f)]
        if parsed:
            build_file_nodes(parsed)
            embed_all_nodes()
            print(f"Re-indexed: {[p['file'] for p in parsed]}")

def start_watcher():
    handler = CodeChangeHandler()
    observer = Observer()
    observer.schedule(handler, CODEBASE_PATH, recursive=True)
    observer.start()
    print(f"Watching {CODEBASE_PATH} for changes...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

### 10.2 `updater/git_hook.py`

Tạo file `post-commit` hook tại `{CODEBASE_PATH}/.git/hooks/post-commit`:

```bash
#!/bin/bash
# GraphRAG post-commit hook
# Tự động update graph sau mỗi commit

GRAPHRAG_PATH="/path/to/your/graphrag"
cd "$GRAPHRAG_PATH" && python -c "
from parsers.git_parser import parse_git_history
from extractors.llm_extractor import extract_from_commit
from graph.builder import build_git_nodes

commits = parse_git_history(max_commits=1)
if commits:
    extracted = [extract_from_commit(c) for c in commits]
    build_git_nodes(commits)
    print('GraphRAG: Git graph updated.')
" &
```

```bash
chmod +x {CODEBASE_PATH}/.git/hooks/post-commit
```

---

## 11. Phase 9 — Visualization

### 11.1 Backend API

```bash
pip install fastapi uvicorn
```

`visualization/backend/api.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from graph.neo4j_client import get_client
from query.engine import query, get_node_detail, list_open_tasks

app = FastAPI(title="GraphRAG Visualization API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/graph/full")
def get_full_graph(limit: int = 200):
    """Trả về toàn bộ graph data cho visualization."""
    client = get_client()

    nodes_result = client.run("""
        MATCH (n) WHERE n.name IS NOT NULL
        RETURN id(n) as id, labels(n)[0] as type, n.name as name,
               n.description as description, n.community_id as community_id,
               n.raw_code as raw_code
        LIMIT $limit
    """, {"limit": limit})

    edges_result = client.run("""
        MATCH (a)-[r]->(b) WHERE a.name IS NOT NULL AND b.name IS NOT NULL
        RETURN id(a) as source, id(b) as target, type(r) as label
        LIMIT $limit
    """, {"limit": limit * 3})

    return {
        "nodes": [dict(n) for n in nodes_result],
        "edges": [dict(e) for e in edges_result],
    }

@app.get("/graph/community/{community_id}")
def get_community_subgraph(community_id: int):
    """Trả về subgraph của một community."""
    client = get_client()

    nodes = client.run("""
        MATCH (n) WHERE n.community_id = $cid AND n.name IS NOT NULL
        RETURN id(n) as id, labels(n)[0] as type, n.name as name,
               n.description as description
    """, {"cid": community_id})

    edges = client.run("""
        MATCH (a)-[r]->(b)
        WHERE a.community_id = $cid AND b.community_id = $cid
        RETURN id(a) as source, id(b) as target, type(r) as label
    """, {"cid": community_id})

    return {
        "nodes": [dict(n) for n in nodes],
        "edges": [dict(e) for e in edges],
    }

@app.get("/communities")
def get_communities():
    """Liệt kê tất cả communities."""
    client = get_client()
    result = client.run("""
        MATCH (c:Community)
        OPTIONAL MATCH (n)-[:BELONGS_TO]->(c)
        RETURN c.id as id, c.name as name, c.summary as summary,
               count(n) as member_count
        ORDER BY member_count DESC
    """)
    return [dict(r) for r in result]

@app.get("/query")
def search_query(q: str):
    return query(q)

@app.get("/node/{name}")
def node_detail(name: str):
    return get_node_detail(name)

@app.get("/tasks")
def tasks(filter: str = None):
    tasks = list_open_tasks()
    if filter:
        tasks = [t for t in tasks if filter.lower() in t.get("name", "").lower()]
    return tasks

@app.get("/graph/search")
def search_nodes(q: str, limit: int = 20):
    """Full-text search trong graph."""
    client = get_client()
    result = client.run("""
        MATCH (n) WHERE n.name IS NOT NULL
        AND (toLower(n.name) CONTAINS toLower($q)
             OR toLower(coalesce(n.description, '')) CONTAINS toLower($q))
        RETURN id(n) as id, labels(n)[0] as type, n.name as name,
               n.description as description, n.community_id as community_id
        LIMIT $limit
    """, {"q": q, "limit": limit})
    return [dict(r) for r in result]
```

Chạy: `uvicorn visualization.backend.api:app --host 0.0.0.0 --port 8080 --reload`

### 11.2 Frontend Visualization

```bash
npm create vite@latest graphrag-viz -- --template react
cd graphrag-viz
npm install react-force-graph-2d d3 tailwindcss axios
```

`visualization/frontend/src/App.jsx`:

```jsx
import { useState, useEffect, useRef, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import axios from "axios";

const API = "http://localhost:8080";

// Màu sắc cho từng loại node
const NODE_COLORS = {
  Function:  "#60a5fa",  // blue
  Class:     "#a78bfa",  // purple
  File:      "#94a3b8",  // gray
  Concept:   "#34d399",  // green
  Feature:   "#fbbf24",  // yellow
  Decision:  "#f97316",  // orange
  Risk:      "#f87171",  // red
  Task:      "#fb923c",  // amber
  Person:    "#e879f9",  // pink
  Commit:    "#6b7280",  // dark gray
  Community: "#14b8a6",  // teal
};

const NODE_SIZE = {
  Community: 12, Feature: 10, Concept: 9,
  Class: 8, Risk: 8, Function: 6, File: 5,
  Decision: 7, Task: 7, Person: 8, Commit: 4,
};

export default function App() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [communities, setCommunities] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [activeFilter, setActiveFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [highlightNodes, setHighlightNodes] = useState(new Set());
  const graphRef = useRef();

  useEffect(() => {
    loadFullGraph();
    loadCommunities();
  }, []);

  const loadFullGraph = async () => {
    setLoading(true);
    const { data } = await axios.get(`${API}/graph/full?limit=300`);
    setGraphData({
      nodes: data.nodes.map(n => ({ ...n, id: String(n.id) })),
      links: data.edges.map(e => ({
        source: String(e.source),
        target: String(e.target),
        label: e.label,
      })),
    });
    setLoading(false);
  };

  const loadCommunities = async () => {
    const { data } = await axios.get(`${API}/communities`);
    setCommunities(data);
  };

  const loadCommunitySubgraph = async (communityId) => {
    setLoading(true);
    const { data } = await axios.get(`${API}/graph/community/${communityId}`);
    setGraphData({
      nodes: data.nodes.map(n => ({ ...n, id: String(n.id) })),
      links: data.edges.map(e => ({
        source: String(e.source),
        target: String(e.target),
        label: e.label,
      })),
    });
    setLoading(false);
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    const { data } = await axios.get(`${API}/graph/search?q=${encodeURIComponent(searchQuery)}`);
    setSearchResults(data);
    const ids = new Set(data.map(n => String(n.id)));
    setHighlightNodes(ids);
  };

  const handleNodeClick = async (node) => {
    const { data } = await axios.get(`${API}/node/${encodeURIComponent(node.name)}`);
    setSelectedNode({ ...node, detail: data });
  };

  const filteredData = {
    nodes: activeFilter === "all"
      ? graphData.nodes
      : graphData.nodes.filter(n => n.type === activeFilter),
    links: graphData.links,
  };

  const nodeColor = useCallback((node) => {
    if (highlightNodes.size > 0) {
      return highlightNodes.has(String(node.id))
        ? (NODE_COLORS[node.type] || "#999")
        : "#1e293b";
    }
    return NODE_COLORS[node.type] || "#999";
  }, [highlightNodes]);

  const nodeVal = useCallback((node) => NODE_SIZE[node.type] || 5, []);

  return (
    <div className="flex h-screen bg-gray-950 text-white overflow-hidden">

      {/* Sidebar trái — Communities */}
      <div className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <h1 className="text-lg font-bold text-white">GraphRAG</h1>
          <p className="text-xs text-gray-400 mt-1">Knowledge Graph Explorer</p>
        </div>

        {/* Search */}
        <div className="p-3 border-b border-gray-800">
          <div className="flex gap-2">
            <input
              className="flex-1 bg-gray-800 text-sm rounded px-3 py-2 text-white placeholder-gray-500 outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Tìm kiếm..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
            />
            <button
              onClick={handleSearch}
              className="bg-blue-600 hover:bg-blue-500 px-3 py-2 rounded text-sm font-medium"
            >
              ↵
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="mt-2 text-xs text-gray-400">{searchResults.length} kết quả</div>
          )}
        </div>

        {/* Filter theo loại node */}
        <div className="p-3 border-b border-gray-800">
          <p className="text-xs text-gray-500 uppercase mb-2">Lọc theo loại</p>
          <div className="flex flex-wrap gap-1">
            {["all", ...Object.keys(NODE_COLORS)].map(type => (
              <button
                key={type}
                onClick={() => setActiveFilter(type)}
                className={`text-xs px-2 py-1 rounded transition-colors ${
                  activeFilter === type
                    ? "bg-blue-600 text-white"
                    : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                }`}
                style={type !== "all" ? { borderLeft: `3px solid ${NODE_COLORS[type]}` } : {}}
              >
                {type}
              </button>
            ))}
          </div>
        </div>

        {/* Communities list */}
        <div className="flex-1 overflow-y-auto p-3">
          <p className="text-xs text-gray-500 uppercase mb-2">Communities</p>
          <button
            onClick={loadFullGraph}
            className="w-full text-left text-xs bg-gray-800 hover:bg-gray-700 rounded px-3 py-2 mb-2 text-gray-300"
          >
            🌐 Xem toàn bộ graph
          </button>
          {communities.map(c => (
            <button
              key={c.id}
              onClick={() => loadCommunitySubgraph(c.id)}
              className="w-full text-left bg-gray-800 hover:bg-gray-700 rounded px-3 py-2 mb-1 transition-colors"
            >
              <div className="text-sm font-medium text-teal-400">{c.name}</div>
              <div className="text-xs text-gray-500 mt-0.5">{c.member_count} nodes</div>
            </button>
          ))}
        </div>
      </div>

      {/* Graph chính */}
      <div className="flex-1 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950 bg-opacity-80 z-10">
            <div className="text-gray-400 text-sm">Đang tải graph...</div>
          </div>
        )}

        {/* Legend */}
        <div className="absolute top-4 left-4 z-10 bg-gray-900 bg-opacity-90 rounded-lg p-3 text-xs">
          {Object.entries(NODE_COLORS).slice(0, 6).map(([type, color]) => (
            <div key={type} className="flex items-center gap-2 mb-1">
              <div className="w-3 h-3 rounded-full" style={{ background: color }} />
              <span className="text-gray-400">{type}</span>
            </div>
          ))}
        </div>

        <ForceGraph2D
          ref={graphRef}
          graphData={filteredData}
          nodeColor={nodeColor}
          nodeVal={nodeVal}
          nodeLabel={node => `[${node.type}] ${node.name}`}
          linkColor={() => "#374151"}
          linkWidth={0.5}
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={1}
          backgroundColor="#030712"
          onNodeClick={handleNodeClick}
          cooldownTicks={100}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const label = node.name;
            const fontSize = Math.max(8 / globalScale, 3);
            const r = NODE_SIZE[node.type] || 5;
            const color = nodeColor(node);

            // Draw node circle
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.fill();

            // Draw label (chỉ khi zoom đủ)
            if (globalScale > 1.5) {
              ctx.font = `${fontSize}px Sans-Serif`;
              ctx.fillStyle = "#e2e8f0";
              ctx.textAlign = "center";
              ctx.fillText(label?.slice(0, 20), node.x, node.y + r + fontSize);
            }
          }}
        />
      </div>

      {/* Panel phải — Node detail */}
      {selectedNode && (
        <div className="w-80 bg-gray-900 border-l border-gray-800 overflow-y-auto">
          <div className="p-4 border-b border-gray-800 flex items-start justify-between">
            <div>
              <div
                className="text-xs font-semibold uppercase tracking-wider mb-1"
                style={{ color: NODE_COLORS[selectedNode.type] || "#999" }}
              >
                {selectedNode.type}
              </div>
              <h2 className="text-base font-bold text-white">{selectedNode.name}</h2>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-gray-600 hover:text-gray-400 text-lg leading-none"
            >×</button>
          </div>

          {selectedNode.detail && (
            <div className="p-4 space-y-4">
              {selectedNode.description && (
                <div>
                  <p className="text-xs text-gray-500 uppercase mb-1">Mô tả</p>
                  <p className="text-sm text-gray-300">{selectedNode.description}</p>
                </div>
              )}

              {selectedNode.detail?.node?.raw_code && (
                <div>
                  <p className="text-xs text-gray-500 uppercase mb-1">Code</p>
                  <pre className="text-xs bg-gray-800 rounded p-3 overflow-x-auto text-green-400 whitespace-pre-wrap">
                    {selectedNode.detail.node.raw_code?.slice(0, 500)}
                  </pre>
                </div>
              )}

              {selectedNode.detail?.outgoing?.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase mb-1">Liên kết ra ({selectedNode.detail.outgoing.length})</p>
                  {selectedNode.detail.outgoing.slice(0, 8).map((rel, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-gray-400 mb-1">
                      <span className="text-blue-400">{rel.type}</span>
                      <span>→</span>
                      <button
                        className="text-gray-300 hover:text-white underline"
                        onClick={() => handleNodeClick({ name: rel.target, type: "?" })}
                      >
                        {rel.target}
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {selectedNode.detail?.incoming?.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase mb-1">Liên kết vào ({selectedNode.detail.incoming.length})</p>
                  {selectedNode.detail.incoming.slice(0, 8).map((rel, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-gray-400 mb-1">
                      <button
                        className="text-gray-300 hover:text-white underline"
                        onClick={() => handleNodeClick({ name: rel.source, type: "?" })}
                      >
                        {rel.source}
                      </button>
                      <span>→</span>
                      <span className="text-blue-400">{rel.type}</span>
                    </div>
                  ))}
                </div>
              )}

              {selectedNode.detail?.node?.community_id !== undefined && (
                <div>
                  <p className="text-xs text-gray-500 uppercase mb-1">Community</p>
                  <button
                    onClick={() => loadCommunitySubgraph(selectedNode.detail.node.community_id)}
                    className="text-xs text-teal-400 hover:text-teal-300 underline"
                  >
                    Xem community #{selectedNode.detail.node.community_id}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

Chạy frontend: `npm run dev` (mở tại `http://localhost:5173`)

---

## 12. Chạy toàn bộ hệ thống

### 12.1 `main.py` — Full pipeline

```python
import sys
from config import CODEBASE_PATH

def run_full_pipeline():
    print("=" * 60)
    print("GraphRAG Full Pipeline — Mức 3")
    print("=" * 60)

    # 1. Khởi động Neo4j + Chroma
    print("\n[1/8] Starting databases...")
    import subprocess
    subprocess.run(["docker-compose", "up", "-d"], check=True)
    import time; time.sleep(5)

    # 2. Init graph indexes
    print("\n[2/8] Initializing graph schema...")
    from graph.neo4j_client import get_client
    client = get_client()
    client.create_indexes()

    # 3. Parse codebase
    print("\n[3/8] Parsing codebase...")
    from parsers.ast_parser import parse_codebase
    from parsers.doc_parser import parse_docs
    from parsers.git_parser import parse_git_history

    parsed_files = parse_codebase(CODEBASE_PATH)
    docs = parse_docs(CODEBASE_PATH)
    commits = parse_git_history(CODEBASE_PATH, max_commits=200)

    # 4. Build structural graph
    print("\n[4/8] Building structural graph...")
    from graph.builder import build_file_nodes, build_git_nodes
    build_file_nodes(parsed_files)
    build_git_nodes(commits)

    # 5. LLM extraction
    print("\n[5/8] Extracting semantic entities (LLM)...")
    from extractors.llm_extractor import batch_extract
    from graph.builder import build_semantic_nodes

    all_chunks = []
    for pf in parsed_files[:50]:  # giới hạn 50 files để tiết kiệm API cost
        all_chunks.append({"content": pf.get("raw_code", ""), "file": pf["file"]})
    all_chunks.extend(docs)

    extracted = batch_extract(all_chunks)
    build_semantic_nodes(extracted)

    # 6. Embed nodes
    print("\n[6/8] Embedding nodes...")
    from embeddings.chroma_client import embed_all_nodes
    embed_all_nodes()

    # 7. Community detection
    print("\n[7/8] Detecting communities...")
    from community.detector import detect_communities
    from community.summarizer import summarize_all_communities
    detect_communities()
    summarize_all_communities()

    # 8. Start servers
    print("\n[8/8] Starting API server...")
    print("\n✅ Pipeline complete!")
    print(f"   Neo4j Browser:     http://localhost:7474")
    print(f"   GraphRAG API:      http://localhost:8080")
    print(f"   Visualization UI:  http://localhost:5173")
    print("\nRun API server:  uvicorn visualization.backend.api:app --port 8080")
    print("Run Frontend:    cd visualization/frontend && npm run dev")
    print("Run MCP Server:  node mcp/server.js")

if __name__ == "__main__":
    run_full_pipeline()
```

### 12.2 `.env` template

```bash
# Target project
CODEBASE_PATH=/path/to/your/project

# AI APIs
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Vector DB
CHROMA_PATH=./chroma_db

# GitHub (optional)
GITHUB_TOKEN=ghp_...
GITHUB_REPO=owner/repo

# GraphRAG API (cho MCP)
GRAPHRAG_API=http://localhost:8080
```

### 12.3 Thứ tự chạy

```bash
# 1. Clone và setup
git clone <this-repo>
cd graphrag
pip install -r requirements.txt
cp .env.example .env
# → Điền CODEBASE_PATH và API keys vào .env

# 2. Khởi động databases
docker-compose up -d

# 3. Chạy full pipeline (lần đầu ~10-30 phút tuỳ codebase)
python main.py

# 4. Start API server (terminal 2)
uvicorn visualization.backend.api:app --host 0.0.0.0 --port 8080 --reload

# 5. Start frontend (terminal 3)
cd visualization/frontend && npm install && npm run dev

# 6. Start MCP server (terminal 4, nếu dùng Claude Code)
node mcp/server.js

# 7. Start file watcher để auto-update (terminal 5, optional)
python -m updater.watcher
```

---

## 13. Checklist kiểm tra

Sau khi chạy xong, kiểm tra từng bước:

```
Phase 1 — Parser
  □ parse_codebase() trả về > 0 files
  □ Mỗi file có nodes (functions/classes)
  □ parse_git_history() trả về commits
  □ parse_docs() trả về doc chunks

Phase 2 — LLM Extraction
  □ batch_extract() trả về entities có type hợp lệ
  □ Relations có from/to tồn tại trong graph
  □ Không có JSON parse errors (kiểm tra log)

Phase 3 — Neo4j
  □ Mở http://localhost:7474, login neo4j/password
  □ Query: MATCH (n) RETURN count(n) → > 0
  □ Query: MATCH ()-[r]->() RETURN count(r) → > 0
  □ Có đủ các label: Function, Class, File, Concept, Feature, Task

Phase 4 — Embedding
  □ Chroma collection "graphrag_nodes" có documents
  □ semantic_search("authentication") trả về kết quả liên quan

Phase 5 — Community
  □ Query Neo4j: MATCH (n) WHERE n.community_id IS NOT NULL RETURN count(n) → > 0
  □ Community nodes tồn tại với name và summary
  □ GET /communities trả về list > 0

Phase 6 — Query Engine
  □ GET /query?q=authentication trả về context có nghĩa
  □ GET /node/{function_name} trả về detail đúng
  □ GET /tasks trả về list tasks từ code

Phase 7 — MCP
  □ MCP server start không lỗi
  □ Tool ask_codebase hoạt động trong Claude Code

Phase 8 — Updater
  □ Sửa một file, watcher log ra "Re-indexing..."
  □ Git commit trigger post-commit hook

Phase 9 — Visualization
  □ http://localhost:5173 hiện graph có nodes và edges
  □ Click node hiện detail panel bên phải
  □ Community panel bên trái có list
  □ Search tìm được nodes theo tên
  □ Filter theo loại node hoạt động
```

---

> **Ghi chú cho agent:** Triển khai tuần tự từ Phase 1 → 9. Sau mỗi phase, chạy phần kiểm tra tương ứng trước khi tiếp tục. Nếu gặp lỗi Neo4j connection, kiểm tra Docker đang chạy. Nếu LLM extraction trả về JSON không hợp lệ, kiểm tra lại ANTHROPIC_API_KEY và thêm retry logic.
