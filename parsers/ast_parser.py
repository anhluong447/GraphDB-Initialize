"""
Backward-compatibility shim for AST parsing.
All core implementation has been moved to `parsers.base_parser`.
"""

from parsers.base_parser import parse_file, parse_codebase

__all__ = [
    "parse_file",
    "parse_codebase",
]
