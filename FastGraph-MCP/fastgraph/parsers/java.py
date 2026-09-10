"""Java adapter (tree-sitter-java)."""

from __future__ import annotations

import tree_sitter_java
from tree_sitter import Language, Parser

from fastgraph.parsers.base import CallRef, ImportRef, ParseResult, SymbolInfo
from fastgraph.parsers.registry import register_adapter
from fastgraph.parsers.util import node_text


def _java_calls(node, source: bytes) -> list[CallRef]:
    calls: list[CallRef] = []

    def walk(n, top: bool) -> None:
        if not top and n.type in ("method_declaration", "constructor_declaration", "class_declaration", "lambda_expression"):
            return
        if n.type == "method_invocation":
            fn = n.child_by_field_name("name")
            if fn is not None:
                target = node_text(fn, source, 160)
                obj = n.child_by_field_name("object")
                if obj is not None:
                    obj_text = node_text(obj, source, 120)
                    calls.append(CallRef(target=target, line=n.start_point[0] + 1))
                    calls.append(CallRef(target=f"{obj_text.split('.')[-1]}.{target}", line=n.start_point[0] + 1))
                else:
                    calls.append(CallRef(target=target, line=n.start_point[0] + 1))
        elif n.type == "object_creation_expression":
            # `new BizException(...)`: record the constructed type as a
            # reference so impact_analysis/rename_impact see constructor sites
            # (previously a class used by 100+ `new X()` calls reported 0).
            t = n.child_by_field_name("type")
            if t is not None:
                target = node_text(t, source, 160).split(".")[-1]
                if target:
                    calls.append(CallRef(target=target, line=n.start_point[0] + 1))
        for c in n.named_children:
            walk(c, False)

    walk(node, True)
    return calls


def _has_annotation(node) -> bool:
    """True when a Java declaration carries an annotation (@GetMapping, ...).

    Annotations live inside the `modifiers` child of a declaration; annotated
    methods are registered by the framework (Spring endpoints etc.), so
    dead-code detection must not report them.
    """
    for c in node.named_children:
        if c.type == "annotation":
            return True
        if c.type == "modifiers":
            if any(x.type == "annotation" for x in c.named_children):
                return True
    return False


class JavaAdapter:
    lang = "java"
    exts = (".java",)

    _parser: Parser | None = None

    def __init__(self):
        if JavaAdapter._parser is None:
            JavaAdapter._parser = Parser(Language(tree_sitter_java.language()))

    def parse(self, source: bytes) -> ParseResult:
        tree = self._parser.parse(source)
        symbols: list[SymbolInfo] = []
        imports: list[ImportRef] = []

        def walk(node, stack: list[SymbolInfo]) -> None:
            t = node.type
            if t == "import_declaration":
                imports.append(ImportRef(text=node_text(node, source, 300), line=node.start_point[0] + 1))
            elif t == "class_declaration":
                name = node_text(node.child_by_field_name("name"), source, 120)
                parent = stack[-1].qualified_name if stack else None
                bases: list[CallRef] = []
                supers: list[str] = []
                ifaces: list[str] = []
                for c in node.named_children:
                    if c.type == "superclass":
                        for i in c.named_children:
                            if i.type in ("type_identifier", "scoped_type_identifier", "identifier", "scoped_identifier"):
                                t = node_text(i, source, 160)
                                supers.append(t)
                                bases.append(CallRef(target=t, line=i.start_point[0] + 1, rtype="inherits"))
                    elif c.type == "super_interfaces":
                        for i in c.named_children:
                            if i.type in ("type_identifier", "scoped_type_identifier", "identifier", "scoped_identifier"):
                                t = node_text(i, source, 160)
                                ifaces.append(t)
                                bases.append(CallRef(target=t, line=i.start_point[0] + 1, rtype="inherits"))
                sig = f"class {name}"
                if supers:
                    sig += " extends " + ", ".join(supers)
                if ifaces:
                    sig += " implements " + ", ".join(ifaces)
                sym = SymbolInfo(
                    name=name, kind="class",
                    qualified_name=parent + "." + name if parent else name,
                    signature=sig, doc="",
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent, bases=bases,
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            elif t in ("method_declaration", "constructor_declaration"):
                name = node_text(node.child_by_field_name("name"), source, 120)
                parent = stack[-1].qualified_name if stack else None
                params = node.child_by_field_name("parameters")
                sym = SymbolInfo(
                    name=name, kind="method" if t == "method_declaration" else "constructor",
                    qualified_name=parent + "." + name if parent else name,
                    signature=f"{name}({node_text(params, source, 200) if params else ''})",
                    doc="", start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent, calls=_java_calls(node, source),
                    decorated=_has_annotation(node),
                )
                symbols.append(sym)
            elif t == "interface_declaration":
                name = node_text(node.child_by_field_name("name"), source, 120)
                bases: list[CallRef] = []
                supers: list[str] = []
                for c in node.named_children:
                    if c.type == "super_interfaces":
                        for i in c.named_children:
                            if i.type in ("type_identifier", "scoped_type_identifier", "identifier", "scoped_identifier"):
                                t = node_text(i, source, 160)
                                supers.append(t)
                                bases.append(CallRef(target=t, line=i.start_point[0] + 1, rtype="inherits"))
                sig = f"interface {name}"
                if supers:
                    sig += " extends " + ", ".join(supers)
                sym = SymbolInfo(
                    name=name, kind="interface", qualified_name=name,
                    signature=sig, doc="",
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    bases=bases,
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            else:
                for c in node.named_children:
                    walk(c, stack)

        walk(tree.root_node, [])
        return ParseResult(language=self.lang, symbols=symbols, imports=imports)


register_adapter(JavaAdapter())