"""Go adapter (tree-sitter-go)."""

from __future__ import annotations

import tree_sitter_go
from tree_sitter import Language, Parser

from fastgraph.parsers.base import CallRef, ImportRef, ParseResult, SymbolInfo
from fastgraph.parsers.registry import register_adapter
from fastgraph.parsers.util import node_text


def _go_calls(node, source: bytes) -> list[CallRef]:
    calls: list[CallRef] = []

    def walk(n, top: bool) -> None:
        if not top and n.type == "function_declaration":
            return
        if n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None:
                target = node_text(fn, source, 160)
                last = target.split(".")[-1]
                calls.append(CallRef(target=last or target, line=n.start_point[0] + 1))
                if "." in target:
                    calls.append(CallRef(target=target, line=n.start_point[0] + 1))
        for c in n.named_children:
            walk(c, False)

    walk(node, True)
    return calls


class GoAdapter:
    lang = "go"
    exts = (".go",)

    _parser: Parser | None = None

    def __init__(self):
        if GoAdapter._parser is None:
            GoAdapter._parser = Parser(Language(tree_sitter_go.language()))

    def parse(self, source: bytes) -> ParseResult:
        tree = self._parser.parse(source)
        symbols: list[SymbolInfo] = []
        imports: list[ImportRef] = []

        def walk(node, stack: list[SymbolInfo], in_struct: bool) -> None:
            t = node.type
            if t == "import_declaration":
                # One row per imported path: storing the whole `import (...)`
                # block as a single row made it classify as an *internal* import
                # as soon as one of its paths resolved, hiding every stdlib
                # sibling from `external_imports` (and losing per-import lines).
                specs: list = []
                pending = list(node.named_children)
                while pending:
                    cur = pending.pop()
                    if cur.type == "import_spec":
                        specs.append(cur)
                    else:
                        pending.extend(cur.named_children)
                if specs:
                    for spec in specs:
                        imports.append(
                            ImportRef(
                                text=node_text(spec, source, 200),
                                line=spec.start_point[0] + 1,
                            )
                        )
                else:  # defensive: unknown grammar shape, keep the raw text
                    imports.append(
                        ImportRef(text=node_text(node, source, 300), line=node.start_point[0] + 1)
                    )
            elif t == "function_declaration":
                name = node_text(node.child_by_field_name("name"), source, 120)
                params = node.child_by_field_name("parameters")
                sym = SymbolInfo(
                    name=name, kind="function", qualified_name=name,
                    signature=f"func {name}({node_text(params, source, 200) if params else ''})",
                    doc="", start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    calls=_go_calls(node, source),
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack, False)
            elif t == "method_declaration":
                name = node_text(node.child_by_field_name("name"), source, 120)
                receiver = node.child_by_field_name("receiver")
                parent = None
                if receiver is not None:
                    # receiver `(s *Service)` -> type_identifier `Service`.
                    # (The naive receiver.named_children[-1] grabbed the whole
                    # parameter_declaration, yielding "s *Service.Run".)
                    def _receiver_type(n):
                        for c in n.named_children:
                            if c.type == "type_identifier":
                                return node_text(c, source, 120)
                            r = _receiver_type(c)
                            if r:
                                return r
                        return None
                    parent = _receiver_type(receiver)
                params = node.child_by_field_name("parameters")
                sym = SymbolInfo(
                    name=name, kind="method",
                    qualified_name=f"{parent}.{name}" if parent else name,
                    signature=f"func ({node_text(receiver, source, 100)}) {name}({node_text(params, source, 200) if params else ''})",
                    doc="", start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent, calls=_go_calls(node, source),
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack, False)
            elif t == "type_declaration":
                for ts in node.named_children:
                    if ts.type == "type_spec":
                        name = node_text(ts.child_by_field_name("name"), source, 120)
                        kind = "struct" if any(c.type == "struct_type" for c in ts.named_children) else "type"
                        sym = SymbolInfo(
                            name=name, kind=kind, qualified_name=name,
                            signature=f"type {name} …", doc="",
                            start_line=ts.start_point[0] + 1, end_line=ts.end_point[0] + 1,
                            start_col=ts.start_point[1], end_col=ts.end_point[1],
                        )
                        symbols.append(sym)
            else:
                for c in node.named_children:
                    walk(c, stack, in_struct)

        walk(tree.root_node, [], False)
        return ParseResult(language=self.lang, symbols=symbols, imports=imports)


register_adapter(GoAdapter())