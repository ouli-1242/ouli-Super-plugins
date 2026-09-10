"""TypeScript / JavaScript / JSX adapter (tree-sitter-typescript + javascript)."""

from __future__ import annotations

import re

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Parser

from fastgraph.parsers.base import CallRef, ImportRef, ParseResult, SymbolInfo
from fastgraph.parsers.registry import register_adapter
from fastgraph.parsers.util import call_targets, node_text

_TS_LANGS: dict[str, Language] = {
    "typescript": Language(tree_sitter_typescript.language_typescript()),
    "tsx": Language(tree_sitter_typescript.language_tsx()),
    "javascript": Language(tree_sitter_javascript.language()),
}


def _calls_in(node, source: bytes) -> list[CallRef]:
    calls: list[CallRef] = []

    def walk(n, top: bool) -> None:
        if not top and n.type in (
            "function_declaration", "function_expression", "arrow_function",
            "method_definition", "class_declaration", "lexical_declaration",
        ):
            return
        if n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None:
                for target in call_targets(fn, source):
                    calls.append(CallRef(target=target, line=n.start_point[0] + 1))
        for c in n.named_children:
            walk(c, False)

    walk(node, True)
    return calls


def _module_level_calls(node, source: bytes) -> list[CallRef]:
    """Calls at a module's top level (import-time side effects).

    Skips function/class bodies and variable declarations (whose initialiser
    calls are already carried by the declared symbol), leaving module-scope
    code such as ``registerAdapter(Foo)``, ``app.use(mw)`` or an IIFE — the
    registration/wiring layer that would otherwise be absent from the call
    graph. Mirrors ``parsers.python._module_level_calls``.
    """
    out: list[CallRef] = []

    def walk(n, top: bool) -> None:
        if not top and n.type in (
            "function_declaration", "function_expression", "arrow_function",
            "method_definition", "class_declaration", "lexical_declaration",
            "variable_declaration",
        ):
            return
        if n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None:
                for target in call_targets(fn, source):
                    out.append(CallRef(target=target, line=n.start_point[0] + 1))
        for c in n.named_children:
            walk(c, False)

    walk(node, True)
    return out


def _js_doc(node, source: bytes) -> str:
    for c in node.named_children:
        if c.type == "comment":
            return node_text(c, source, 300)
        if c.type in ("statement_block", "class_body"):
            for inner in c.named_children:
                if inner.type == "comment":
                    return node_text(inner, source, 300)
    return ""


def _ts_bases(node, source: bytes) -> list[CallRef]:
    bases: list[CallRef] = []
    for c in node.named_children:
        if c.type == "class_heritage":
            for h in c.named_children:
                if h.type in ("identifier", "nested_identifier"):
                    bases.append(
                        CallRef(target=node_text(h, source, 160), line=h.start_point[0] + 1, rtype="inherits")
                    )
    return bases


def _module_specifier(node, source: bytes) -> str | None:
    """Static string/template argument of a require()/import() call, dequoted."""
    args = node.child_by_field_name("arguments")
    if args is None:
        return None
    for c in args.named_children:
        if c.type == "string":
            return node_text(c, source, 300).strip("'\"")
        if c.type == "template_string":
            return node_text(c, source, 300).strip("`")
    return None


def _commonjs_imports(node, source: bytes) -> list[ImportRef]:
    """CommonJS `require("...")` and dynamic `import("...")` as imports.

    ES ``import_statement``s are handled in the main walk; this covers the
    CommonJS style WeChat mini-programs and legacy Node modules use.
    """
    imports: list[ImportRef] = []
    seen: set[tuple[int, str]] = set()

    def walk(n) -> None:
        if n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None:
                if node_text(fn, source, 160) == "require":
                    spec = _module_specifier(n, source)
                    text = f'require("{spec}")' if spec else node_text(n, source, 300)
                    key = (n.start_point[0] + 1, text)
                    if key not in seen:
                        seen.add(key)
                        imports.append(ImportRef(text=text, line=n.start_point[0] + 1, kind="require"))
                elif fn.type == "import":
                    spec = _module_specifier(n, source)
                    text = f'import("{spec}")' if spec else node_text(n, source, 300)
                    key = (n.start_point[0] + 1, text)
                    if key not in seen:
                        seen.add(key)
                        imports.append(ImportRef(text=text, line=n.start_point[0] + 1, kind="import"))
        for c in n.named_children:
            walk(c)

    walk(node)
    return imports


class TSAdapter:
    lang = "typescript"
    exts = (".ts", ".mts", ".cts")

    def __init__(self, jsx: bool = False, lang: str = "typescript", exts=(".ts", ".mts", ".cts")):
        self.lang = lang
        self.exts = exts
        self._parser = Parser(_TS_LANGS[lang])

    def parse(self, source: bytes) -> ParseResult:
        tree = self._parser.parse(source)
        symbols: list[SymbolInfo] = []
        imports: list[ImportRef] = []

        def walk(node, stack: list[SymbolInfo]) -> None:
            t = node.type

            if t == "import_statement":
                imports.append(ImportRef(text=node_text(node, source, 300), line=node.start_point[0] + 1))
            elif t == "class_declaration":
                name_node = node.child_by_field_name("name")
                name = node_text(name_node, source, 120)
                parent = stack[-1].qualified_name if stack else None
                sym = SymbolInfo(
                    name=name, kind="class",
                    qualified_name=parent + "." + name if parent else name,
                    signature=f"class {name}", doc=_js_doc(node, source),
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent, bases=_ts_bases(node, source),
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            elif t == "method_definition":
                name = node_text(node.child_by_field_name("name"), source, 120)
                parent = stack[-1].qualified_name if stack else None
                params = node.child_by_field_name("parameters")
                sig = f"{name}({node_text(params, source, 200) if params else ''})"
                sym = SymbolInfo(
                    name=name, kind="method",
                    qualified_name=parent + "." + name if parent else name,
                    signature=sig, doc=_js_doc(node, source),
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent, calls=_calls_in(node, source),
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            elif t == "function_declaration":
                name = node_text(node.child_by_field_name("name"), source, 120)
                parent = stack[-1].qualified_name if stack else None
                params = node.child_by_field_name("parameters")
                sym = SymbolInfo(
                    name=name, kind="function",
                    qualified_name=parent + "." + name if parent else name,
                    signature=f"function {name}({node_text(params, source, 200) if params else ''})",
                    doc=_js_doc(node, source),
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent, calls=_calls_in(node, source),
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            elif t in ("interface_declaration", "type_alias_declaration", "enum_declaration"):
                kind = {"interface_declaration": "interface",
                        "type_alias_declaration": "type",
                        "enum_declaration": "enum"}[t]
                name = node_text(node.child_by_field_name("name"), source, 120)
                parent = stack[-1].qualified_name if stack else None
                sym = SymbolInfo(
                    name=name, kind=kind,
                    qualified_name=parent + "." + name if parent else name,
                    signature=f"{kind} {name}", doc=_js_doc(node, source),
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent,
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            elif t in ("module", "namespace_declaration", "internal_module"):
                name = node_text(node.child_by_field_name("name"), source, 120)
                parent = stack[-1].qualified_name if stack else None
                sym = SymbolInfo(
                    name=name, kind="namespace",
                    qualified_name=parent + "." + name if parent else name,
                    signature=f"namespace {name}", doc="",
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    parent=parent,
                )
                symbols.append(sym)
                for c in node.named_children:
                    walk(c, stack + [sym])
            elif t in ("lexical_declaration", "variable_declaration"):
                for v in node.named_children:
                    if v.type != "variable_declarator":
                        continue
                    vname = node_text(v.child_by_field_name("name"), source, 120)
                    value = v.child_by_field_name("value")
                    parent = stack[-1].qualified_name if stack else None
                    is_fn = value is not None and value.type in ("arrow_function", "function_expression")
                    if re.fullmatch(r"[A-Za-z_$][\w$]*", vname) is None:
                        # destructuring `const { a, b } = ...`: no meaningful
                        # symbol name — fold any calls into the enclosing symbol
                        if stack and value is not None:
                            stack[-1].calls.extend(_calls_in(value, source))
                        continue
                    if (
                        stack
                        and not is_fn
                        and stack[-1].kind in ("function", "method", "constructor")
                    ):
                        # inner local inside a method/function body (e.g.
                        # `const res = getDB()`): implementation detail — fold
                        # its calls into the enclosing symbol so find_callers
                        # reports the method, not a noisy `fn.res` variable
                        # node. Class/namespace members are kept (they are part
                        # of the type's surface, e.g. `NS.v`).
                        if value is not None:
                            stack[-1].calls.extend(_calls_in(value, source))
                        continue
                    sym = SymbolInfo(
                        name=vname, kind="function" if is_fn else "variable",
                        qualified_name=parent + "." + vname if parent else vname,
                        signature=f"const {vname}" + (" = (…)" if is_fn else ""),
                        doc="",
                        start_line=v.start_point[0] + 1, end_line=v.end_point[0] + 1,
                        start_col=v.start_point[1], end_col=v.end_point[1],
                        parent=parent,
                        calls=_calls_in(value, source) if value is not None else [],
                    )
                    symbols.append(sym)
            else:
                for c in node.named_children:
                    walk(c, stack)

        walk(tree.root_node, [])
        imports.extend(_commonjs_imports(tree.root_node, source))
        # module-scope calls (registration/wiring) are carried by the per-file
        # `module` symbol; drop any already counted on a declared symbol
        already = {(c.target, c.line) for s in symbols for c in s.calls}
        module_calls = [
            c for c in _module_level_calls(tree.root_node, source)
            if (c.target, c.line) not in already
        ]
        return ParseResult(
            language=self.lang, symbols=symbols, imports=imports, module_calls=module_calls
        )


register_adapter(TSAdapter(lang="typescript", exts=(".ts", ".mts", ".cts")))
register_adapter(TSAdapter(lang="tsx", exts=(".tsx",)))
register_adapter(TSAdapter(lang="javascript", exts=(".js", ".mjs", ".cjs", ".jsx")))