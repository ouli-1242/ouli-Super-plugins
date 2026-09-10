"""Shared tree-sitter helpers used across adapters."""

from __future__ import annotations

import re
from typing import Optional

try:
    from tree_sitter import Language, Parser
except ImportError:  # pragma: no cover
    Language = Parser = None  # type: ignore


class TSParser:
    """Cached per-species tree-sitter parser."""

    _parsers: dict[str, Parser] = {}

    @classmethod
    def for_lang(cls, lang) -> Parser:
        key = lang.name
        p = cls._parsers.get(key)
        if p is None:
            p = Parser(lang)
            cls._parsers[key] = p
        return p


def node_text(node, source: bytes, limit: int = 300) -> str:
    if node is None:
        return ""
    try:
        return source[node.start_byte : node.end_byte].decode("utf-8", "replace")[:limit]
    except Exception:
        return ""


def kind_for(node, is_method: bool) -> str:
    if is_method:
        return "method"
    t = node.type
    if "class" in t or t == "struct_specifier" or t == "struct_item":
        return "class"
    return "function"


def walk(node, fn, depth: int = 0) -> None:
    if depth > 100:
        return
    fn(node, depth)
    for child in node.named_children:
        walk(child, fn, depth + 1)


def split_identifier(text: str) -> list[str]:
    """Split identifiers on dots/colons/slashes for resolution."""
    parts = re.split(r"[.:/]", text)
    return [p for p in parts if p]


def call_targets(fn, source: bytes, limit: int = 160) -> list[str]:
    """Resolve a call_expression's function node to readable call targets.

    Returns 1-2 target strings:
    - the bare callee name (always);
    - a dotted path (``a.b.c``) only when it is a *simple* member chain with no
      nested calls and not a ``this.``/``self.`` keyword receiver.

    This kills two classes of index noise:
    - ``this.x()`` / ``self.x()`` previously emitted one edge for the bare name
      and one for the keyword-qualified full path, duplicating every reference
      and inflating rename_impact counts (A1);
    - chained calls like ``db.query(X).filter(Y)`` built the full target from
      inner call *argument* text, producing multi-line garbage that never
      resolves to a symbol (A3).
    """
    text = node_text(fn, source, limit)
    if not text:
        return []
    bare = text.rsplit(".", 1)[-1].split("(")[0].strip()
    if not bare:
        return []
    if "." in text and "(" not in text and not text.startswith(("this.", "self.")):
        return [bare, text]
    return [bare]


def display_line(line: int) -> str:
    return str(line + 1) if line >= 0 else "?"