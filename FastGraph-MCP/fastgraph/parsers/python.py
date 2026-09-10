"""Python adapter (tree-sitter-python)."""

from __future__ import annotations

import tree_sitter_python
from tree_sitter import Language, Parser

from fastgraph.parsers.base import CallRef, ImportRef, ParseResult, SymbolInfo
from fastgraph.parsers.registry import register_adapter
from fastgraph.parsers.util import call_targets, node_text


def _parse_calls(node, source: bytes) -> list[CallRef]:
    """Collect call_expression targets inside `node`, skipping nested defs."""
    calls: list[CallRef] = []

    def walk(n) -> None:
        if n.type == "function_definition" and n is not node:
            return  # skip nested function bodies (owned by their own symbol)
        if n.type == "call":
            fn = n.child_by_field_name("function")
            if fn is not None:
                for target in call_targets(fn, source):
                    calls.append(CallRef(target=target, line=n.start_point[0] + 1))
            # plain-identifier arguments are references, not calls: captures
            # FastAPI `Depends(get_current_user)`, callbacks, etc., so
            # rename_impact sees them while the call graph stays clean (A6).
            for arg in n.named_children:
                if arg.type == "argument_list":
                    for a in arg.named_children:
                        if a.type == "identifier":
                            name = node_text(a, source, 120)
                        elif a.type == "attribute":
                            # a callable passed as a value (``ex.map(self._parse_only, xs)``,
                            # ``sort(key=self._key)``, ``Thread(target=fn)``): the trailing
                            # attribute name is the referenced symbol, so it must count as
                            # a usage or dead-code detection reports it as unused
                            name = node_text(a, source, 160).rsplit(".", 1)[-1]
                        else:
                            continue
                        if name:
                            calls.append(CallRef(target=name, line=a.start_point[0] + 1, rtype="references"))
        for c in n.named_children:
            walk(c)

    walk(node)
    return calls


def _module_level_calls(node, source: bytes) -> list[CallRef]:
    """Calls executed at import time: module level only.

    Walks the whole file but stops at every ``def``/``class`` (and their
    decorators, which would otherwise contribute noisy ``app.get``-style
    targets), so what remains is the module's own straight-line code —
    registration, wiring and ``if __name__ == "__main__": main()``.
    """
    out: list[CallRef] = []

    def walk(n) -> None:
        if n.type in (
            "function_definition", "class_definition", "decorated_definition", "lambda",
        ):
            return
        if n.type == "call":
            fn = n.child_by_field_name("function")
            if fn is not None:
                for target in call_targets(fn, source):
                    out.append(CallRef(target=target, line=n.start_point[0] + 1))
        for c in n.named_children:
            walk(c)

    walk(node)
    return out


def _docstring(node, source: bytes) -> str:
    body = node.child_by_field_name("body")
    if body is None:
        return ""
    for c in body.named_children:
        if c.type == "expression_statement":
            for s in c.named_children:
                if s.type == "string":
                    return node_text(s, source, 400)
    return ""


def _class_bases(node, source: bytes) -> list[CallRef]:
    bases: list[CallRef] = []
    sc = node.child_by_field_name("superclasses")
    if sc is not None:
        for c in sc.named_children:
            if c.type in ("identifier", "attribute"):
                bases.append(
                    CallRef(
                        target=node_text(c, source, 160),
                        line=c.start_point[0] + 1,
                        rtype="inherits",
                    )
                )
    return bases


class PythonAdapter:
    lang = "python"
    exts = (".py",)

    _parser: Parser | None = None

    def __init__(self):
        if PythonAdapter._parser is None:
            PythonAdapter._parser = Parser(Language(tree_sitter_python.language()))

    def parse(self, source: bytes) -> ParseResult:
        tree = self._parser.parse(source)
        if tree.root_node.has_error:
            raise SyntaxError("python: tree-sitter parse error(s) in root node")
        symbols: list[SymbolInfo] = []
        imports: list[ImportRef] = []
        module_doc = ""

        def walk(node, stack: list[SymbolInfo], decorated: bool = False) -> None:
            nonlocal module_doc
            t = node.type

            if t == "decorated_definition":
                # @app.get("/x") / @staticmethod / @pytest.fixture ...: the
                # wrapped definition is registered by its decorator, never
                # called by name — mark it so dead-code detection skips it
                for c in node.named_children:
                    walk(c, stack, decorated=True)
            elif t == "import_statement":
                imports.append(ImportRef(text=node_text(node, source, 300), line=node.start_point[0] + 1))
            elif t == "import_from_statement":
                imports.append(ImportRef(text=node_text(node, source, 300), line=node.start_point[0] + 1))
            elif t == "class_definition":
                name = node_text(node.child_by_field_name("name"), source, 120)
                parent = stack[-1].qualified_name if stack else None
                sym = SymbolInfo(
                    name=name,
                    kind="class",
                    qualified_name=parent + "." + name if parent else name,
                    signature=f"class {name}",
                    doc=_docstring(node, source),
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1],
                    end_col=node.end_point[1],
                    parent=parent,
                    bases=_class_bases(node, source),
                    decorated=decorated,
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            elif t == "function_definition":
                name = node_text(node.child_by_field_name("name"), source, 120)
                if not name:
                    return
                params = node.child_by_field_name("parameters")
                parent = stack[-1].qualified_name if stack else None
                kind = "method" if parent else "function"
                sym = SymbolInfo(
                    name=name,
                    kind=kind,
                    qualified_name=parent + "." + name if parent else name,
                    signature=f"def {name}{node_text(params, source, 200) if params else '()'}",
                    doc=_docstring(node, source),
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1],
                    end_col=node.end_point[1],
                    parent=parent,
                    calls=_parse_calls(node, source),
                    decorated=decorated,
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            else:
                if t == "expression_statement" and not module_doc and not stack:
                    for s in node.named_children:
                        if s.type == "string":
                            module_doc = node_text(s, source, 500)
                if t == "expression_statement" and not stack:
                    assign = next(
                        (c for c in node.named_children if c.type == "assignment"),
                        None,
                    )
                    if assign is not None:
                        lhs = assign.child_by_field_name("left")
                        if lhs is not None and lhs.type == "identifier":
                            name = node_text(lhs, source, 120)
                            if name:
                                symbols.append(
                                    SymbolInfo(
                                        name=name,
                                        kind="variable",
                                        qualified_name=name,
                                        signature=node_text(node, source, 200),
                                        doc="",
                                        start_line=assign.start_point[0] + 1,
                                        end_line=assign.end_point[0] + 1,
                                        start_col=assign.start_point[1],
                                        end_col=assign.end_point[1],
                                        calls=_parse_calls(assign, source),
                                    )
                                )
                for c in node.named_children:
                    walk(c, stack)

        walk(tree.root_node, [])
        # Module-level calls are carried by the per-file `module` symbol (added
        # by the indexer). Drop those already attributed to a module-level
        # variable symbol so `app = FastAPI()` is not counted twice.
        already = {(c.target, c.line) for s in symbols for c in s.calls}
        module_calls = [
            c for c in _module_level_calls(tree.root_node, source)
            if (c.target, c.line) not in already
        ]
        return ParseResult(
            language=self.lang,
            symbols=symbols,
            imports=imports,
            module_doc=module_doc,
            module_calls=module_calls,
        )


register_adapter(PythonAdapter())