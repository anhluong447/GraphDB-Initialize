"""
Git Hook Setup

This module provides a function to install a post-commit hook
that auto-updates the GraphRAG graph after each git commit.
"""

import os
import sys
import stat

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CODEBASE_PATH


HOOK_SCRIPT = """#!/bin/bash
# GraphRAG post-commit hook
# Auto-update graph after each commit

GRAPHRAG_PATH="{graphrag_path}"
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
"""


def install_hook():
    """Install post-commit hook in the target codebase."""
    hooks_dir = os.path.join(CODEBASE_PATH, ".git", "hooks")
    if not os.path.exists(hooks_dir):
        print(f"[GitHook] No .git/hooks directory found at {hooks_dir}")
        return False

    hook_path = os.path.join(hooks_dir, "post-commit")
    graphrag_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HOOK_SCRIPT.format(graphrag_path=graphrag_path))

    # Make executable
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)

    print(f"[GitHook] Post-commit hook installed at {hook_path}")
    return True


if __name__ == "__main__":
    install_hook()
