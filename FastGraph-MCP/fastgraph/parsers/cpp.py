"""C / C++ adapter (tree-sitter-cpp covers both .c and .cpp).

tree-sitter-cpp grammar accepts C files; we keep one adapter for both.
"""

from __future__ import annotations

import tree_sitter_cpp
from tree_sitter import Language, Parser

from fastgraph.parsers.base import CallRef, ImportRef, ParseResult, SymbolInfo
from fastgraph.parsers.registry import register_adapter
from fastgraph.parsers.util import node_text


def _cpp_calls(node, source: bytes) -> list[CallRef]:
    calls: list[CallRef] = []

    def walk(n, top: bool) -> None:
        if not top and n.type in (
            "function_definition", "function_declarator", "class_specifier",
            "lambda_expression", "declaration", "compound_statement",
        ):
            if n.type == "compound_statement" and n is node:
                pass
            else:
                return
        if n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None:
                target = node_text(fn, source, 160)
                last = target.split("::")[-1].split(".")[-1]
                calls.append(CallRef(target=last or target, line=n.start_point[0] + 1))
        for c in n.named_children:
            walk(c, False)

    walk(node, True)
    return calls


class CppAdapter:
    lang = "cpp"
    exts = (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx")

    _parser: Parser | None = None

    def __init__(self):
        if CppAdapter._parser is None:
            CppAdapter._parser = Parser(Language(tree_sitter_cpp.language()))

    def parse(self, source: bytes) -> ParseResult:
        tree = self._parser.parse(source)
        symbols: list[SymbolInfo] = []
        imports: list[ImportRef] = []

        def walk(node, stack: list[SymbolInfo]) -> None:
            t = node.type
            if t == "preproc_include":
                imports.append(ImportRef(text=node_text(node, source, 300), line=node.start_point[0] + 1))
            elif t == "function_definition":
                name_node = node.child_by_field_name("declarator")
                name = ""
                # Method names inside a class are `field_identifier` nodes
                # (a top-level function's is `identifier`); accept both plus
                # the typedef/struct forms, else class methods are dropped.
                while name_node is not None and name_node.type not in (
                    "identifier", "field_identifier", "type_identifier"
                ):
                    name_node = name_node.child_by_field_name("declarator")
                if name_node is not None:
                    name = node_text(name_node, source, 120)
                if not name:
                    return
                parent = stack[-1].qualified_name if stack else None
                sym = SymbolInfo(
                    name=name, kind="method" if parent else "function",
                    qualified_name=parent + "." + name if parent else name,
                    signature=node_text(node, source, 160).split("{")[0].strip(),
                    doc="", start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent, calls=_cpp_calls(node, source),
                )
                symbols.append(sym)
            elif t in ("class_specifier", "struct_specifier", "union_specifier"):
                kind = {"class_specifier": "class",
                        "struct_specifier": "struct",
                        "union_specifier": "union"}[t]
                name_node = node.child_by_field_name("name")
                name = node_text(name_node, source, 120)
                if not name:
                    # anonymous `struct { ... }` / `typedef struct { ... } Tag`
                    return
                parent = stack[-1].qualified_name if stack else None
                bases: list[CallRef] = []
                for c in node.named_children:
                    if c.type == "base_class_clause":
                        for b in c.named_children:
                            if b.type == "type_identifier":
                                bases.append(CallRef(target=node_text(b, source, 160), line=b.start_point[0] + 1, rtype="inherits"))
                sym = SymbolInfo(
                    name=name, kind=kind,
                    qualified_name=parent + "." + name if parent else name,
                    signature=f"{kind} {name}", doc="",
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent, bases=bases,
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            else:
                for c in node.named_children:
                    walk(c, stack)

        walk(tree.root_node, [])
        return ParseResult(language=self.lang, symbols=symbols, imports=imports)


register_adapter(CppAdapter())