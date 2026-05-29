# System Architecture: GraphRAG for Codebases

This document outlines the architecture, data flow, and components of the GraphRAG (Graph-based Retrieval-Augmented Generation) system optimized for local codebases.

---

## 1. High-Level Architecture Overview

The system is designed to parse codebases, build a hybrid Knowledge Graph (combining AST syntax nodes, git commit history, and LLM-extracted semantic features), index them semantically, and expose a visual explorer and a retrieval engine.

```mermaid
graph TD
    A[Codebase & Git History] --> B[AST & Git Parsers]
    B --> C[Neo4j Graph Database]
    B --> D[LLM Semantic Extractor]
    D --> C
    C --> E[Community Detector]
    C --> F[ChromaDB Vector Store]
    E --> G[Community Summarizer]
    G --> F
    
    H[Query Engine] -->|Hybrid Retrieval| C
    H -->|Semantic Search| F
    H -->|Synthesize Response| I[DeepSeek LLM]
    
    J[Web Explorer UI] -->|REST API| K[FastAPI Backend]
    K --> C
    K --> F
```

---

## 2. Key Components

### 2.1 Workspace & Database Isolation
The system supports multi-project isolation managed through `.env` configurations.
- **Project Identifier (`PROJECT_NAME`)**: Separates data storages.
- **Neo4j Storage**: Mapped via bind mounts to `./data/${PROJECT_NAME}/neo4j/data` to keep databases isolated.
- **ChromaDB Storage**: Placed dynamically inside `./data/${PROJECT_NAME}/chroma_db` to separate vector spaces.

### 2.2 AST Code Parser (`parsers/ast_parser.py`)
- **Engine**: Tree-Sitter parsing Python (`.py`), JavaScript (`.js`/`.jsx`), and TypeScript (`.ts`/`.tsx`) files.
- **Nodes**: Maps file structures to `Class` and `Function` nodes.
- **Relations**: Scans function call syntax inside bodies to create `CALLS` relations between nodes.
- **Bug Prevention**: Processes files using raw `bytes` slicing prior to UTF-8 decoding. This prevents character-indexing offsets caused by multi-byte Vietnamese characters in comments or code strings.

### 2.3 Incremental Synchronizer (`updater/`)
Avoids rebuilding the graph from scratch on every change:
- **File Watcher (`watcher.py`)**: A background service that listens to filesystem save events. It parses only the modified files and updates their AST nodes/relationships in Neo4j and ChromaDB instantly without calling LLMs.
- **Git Hook (`git_hook.py`)**: Installed in the target codebase (`.git/hooks/post-commit`). Automatically parses the latest git commit on commit events, extracting features and linking commit history to code nodes.

### 2.4 Semantic Extractor & Community Manager (`extractors/`, `community/`)
- **LLM Extractor (`llm_extractor.py`)**: Leverages DeepSeek-V4 (via OpenRouter) to extract human-level abstractions (Concepts, Features, Risks, Decisions, Tasks) from raw code and commits.
- **Community Detector (`detector.py`)**: Clusters graph nodes into hierarchical communities using Neo4j APOC/Leiden algorithms.
- **Community Summarizer (`summarizer.py`)**: Summarizes the role of each community. It automatically bypasses LLM summarization for small communities (< 3 nodes) to minimize token consumption and runtime, and upserts summaries to ChromaDB in batches.

### 2.5 Hybrid Query Engine (`query/engine.py`)
Provides context for LLM answering:
1. **Vector Stage**: Search ChromaDB for the closest code nodes, features, and community summaries.
2. **Graph Stage**: Perform multi-hop Cypher queries in Neo4j starting from the vector matches to gather relational context (e.g. what calls what, what features depend on what code).
3. **Synthesis Stage**: Merges the retrieved context and feeds it to DeepSeek-V4 to generate a final answer.

### 2.6 Visualization & API (`visualization/`, `mcp/`)
- **Backend API**: A FastAPI server exposing endpoints for graph queries, search, node details, and community graphs.
- **Frontend Dashboard**: A React application using `react-force-graph-2d` and D3 Force layout. Includes edge filtering to prevent rendering crashes on dangling graph connections.
- **MCP Server**: Implements the Model Context Protocol (MCP), allowing external AI assistants (like Claude Desktop) to use this GraphRAG system as a tool server.

---

## 3. Directory Structure

```text
D:\GraphRAG\
├── config.py                 # System configuration and environment loader
├── docker-compose.yml        # Multi-container orchestration (Neo4j, ChromaDB)
├── start_all.bat             # 1-Click launcher script for Windows developers
├── .env                      # Local environment configurations (ignored in git)
├── data/
│   └── <PROJECT_NAME>/       # Isolated storage directory per codebase
│       ├── neo4j/            # Neo4j database files
│       └── chroma_db/        # ChromaDB vector collections
├── parsers/                  # Code and Git history parsers
├── extractors/               # Entity and semantic relation extractors
├── community/                # Graph clustering and community summarization
├── query/                    # Hybrid search and context synthesis engine
├── updater/                  # Filesystem Watcher and Git Hooks
├── visualization/            # FastAPI Backend & React Frontend Dashboard
├── mcp/                      # Model Context Protocol TS/JS server
└── scratch/                  # Test scripts and development playground
```

---

## 4. Operational Workflows

### Starting the System
Double-click `start_all.bat` or run:
```powershell
.\start_all.bat
```
This boots up the databases in Docker, runs the FastAPI backend on port `8080`, launches the React explorer on port `5173`, and turns on the background file change watcher.

### Adding a New Project
1. Update `PROJECT_NAME` and `CODEBASE_PATH` in `.env`.
2. Run `python main.py` to index the new codebase.
3. Launch via `start_all.bat`.
