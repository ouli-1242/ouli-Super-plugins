"""Rust adapter (tree-sitter-rust)."""

from __future__ import annotations

import tree_sitter_rust
from tree_sitter import Language, Parser

from fastgraph.parsers.base import CallRef, ImportRef, ParseResult, SymbolInfo
from fastgraph.parsers.registry import register_adapter
from fastgraph.parsers.util import node_text


def _rust_calls(node, source: bytes) -> list[CallRef]:
    calls: list[CallRef] = []

    def walk(n, top: bool) -> None:
        if not top and n.type in ("function_item", "impl_item", "trait_item", "mod_item"):
            return
        if n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None:
                target = node_text(fn, source, 160)
                last = target.split("::")[-1].split(".")[-1]
                calls.append(CallRef(target=last or target, line=n.start_point[0] + 1))
                if "::" in target or "." in target:
                    calls.append(CallRef(target=target, line=n.start_point[0] + 1))
        for c in n.named_children:
            walk(c, False)

    walk(node, True)
    return calls


class RustAdapter:
    lang = "rust"
    exts = (".rs",)

    _parser: Parser | None = None

    def __init__(self):
        if RustAdapter._parser is None:
            RustAdapter._parser = Parser(Language(tree_sitter_rust.language()))

    def parse(self, source: bytes) -> ParseResult:
        tree = self._parser.parse(source)
        symbols: list[SymbolInfo] = []
        imports: list[ImportRef] = []

        def walk(node, stack: list[SymbolInfo], in_impl: str | None) -> None:
            t = node.type
            if t in ("use_declaration", "extern_crate_declaration", "mod_item"):
                if t == "use_declaration":
                    imports.append(ImportRef(text=node_text(node, source, 300), line=node.start_point[0] + 1))
            elif t == "function_item":
                name = node_text(node.child_by_field_name("name"), source, 120)
                params = node.child_by_field_name("parameters")
                parent = stack[-1].qualified_name if stack else (in_impl or None)
                kind = "method" if in_impl or parent else "function"
                sym = SymbolInfo(
                    name=name, kind=kind,
                    qualified_name=f"{in_impl}::{name}" if in_impl else (name if not parent else f"{parent}.{name}"),
                    signature=f"fn {name}({node_text(params, source, 200) if params else ''})",
                    doc="", start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=in_impl or parent, calls=_rust_calls(node, source),
                )
                symbols.append(sym)
            elif t == "struct_item" or t == "enum_item" or t == "union_item":
                name = node_text(node.child_by_field_name("name"), source, 120)
                kind = "struct" if t == "struct_item" else t.split("_")[0]
                sym = SymbolInfo(
                    name=name, kind=kind, qualified_name=name,
                    signature=f"{kind} {name}", doc="",
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack, in_impl)
            elif t == "impl_item":
                ty = node.child_by_field_name("type")
                ty_name = node_text(ty, source, 120) if ty else ""
                for c in node.named_children:
                    walk(c, stack, ty_name or in_impl)
            elif t == "trait_item":
                name = node_text(node.child_by_field_name("name"), source, 120)
                sym = SymbolInfo(
                    name=name, kind="trait", qualified_name=name,
                    signature=f"trait {name}", doc="",
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack, in_impl)
            else:
                for c in node.named_children:
                    walk(c, stack, in_impl)

        walk(tree.root_node, [], None)
        return ParseResult(language=self.lang, symbols=symbols, imports=imports)


register_adapter(RustAdapter())