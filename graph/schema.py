"""
GraphRAG Schema Definitions

Node Labels:
  - Function: code function/method
  - Class: code class
  - File: source file
  - Concept: abstract concept extracted by LLM
  - Feature: product feature
  - Decision: architectural/design decision
  - Risk: identified risk
  - Task: actionable task/TODO
  - Module: code module/package
  - Person: git author
  - Commit: git commit
  - Community: detected community cluster

Relationship Types:
  - CONTAINS: File -> Function/Class
  - CALLS: Function -> Function
  - MODIFIED: Commit -> File
  - AUTHORED_BY: Commit -> Person
  - IMPLEMENTS: entity implements another
  - DEPENDS_ON: entity depends on another
  - RELATES_TO: generic relation
  - CONFLICTS_WITH: conflicting entities
  - BLOCKS: entity blocks another
  - OWNED_BY: entity owned by person
  - INTRODUCES: commit introduces risk/feature
  - BELONGS_TO: node belongs to community
"""

NODE_LABELS = [
    "Function", "Class", "File", "Concept", "Feature",
    "Decision", "Risk", "Task", "Module", "Person",
    "Commit", "Community",
]

RELATION_TYPES = [
    "CONTAINS", "CALLS", "MODIFIED", "AUTHORED_BY",
    "IMPLEMENTS", "DEPENDS_ON", "RELATES_TO", "CONFLICTS_WITH",
    "BLOCKS", "OWNED_BY", "INTRODUCES", "BELONGS_TO",
]
