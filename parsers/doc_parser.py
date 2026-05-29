import os
import re
from config import CODEBASE_PATH, IGNORE_DIRS


def parse_docs(path: str = CODEBASE_PATH) -> list[dict]:
    """Parse all markdown/text files and extract chunks."""
    docs = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            if file.endswith((".md", ".mdx", ".txt", ".rst")):
                file_path = os.path.join(root, file)
                chunks = _chunk_doc(file_path)
                docs.extend(chunks)
    print(f"[DocParser] Parsed {len(docs)} doc chunks.")
    return docs


def _chunk_doc(file_path: str, chunk_size: int = 1000) -> list[dict]:
    """Split a doc file into chunks by heading or size."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return []

    # Split by headings (## or ###)
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
