"""Shared tree-sitter helpers used across adapters."""

from __future__ import annotations

import re


def node_text(node, source: bytes, limit: int = 300) -> str:
    if node is None:
        return ""
    try:
        return source[node.start_byte : node.end_byte].decode("utf-8", "replace")[:limit]
    except Exception:
        return ""


# Names that wrap a real type instead of being one: taking the first
# identifier of `Optional[UserService]` / `Array<UserService>` would record
# the wrapper, not the receiver's type.
_TYPE_WRAPPER_RE = re.compile(r"[A-Za-z_$][\w$]*")
_TYPE_WRAPPERS = {
    # Python typing / builtins used as wrappers
    "Optional", "Union", "List", "Dict", "Set", "Tuple", "FrozenSet",
    "Sequence", "Iterable", "Callable", "Any", "Type", "Final", "ClassVar",
    "Annotated", "Literal", "list", "dict", "set", "tuple", "type",
    # TS utility / builtin wrappers
    "Array", "Promise", "Record", "Partial", "Readonly", "ReadonlyArray",
    "Map", "Set", "Pick", "Omit", "NonNullable", "string", "number",
    "boolean", "any", "unknown", "never", "void", "object", "symbol",
    "bigint",
}


def first_type_ident(text: str) -> str:
    """First meaningful identifier of a type annotation's text.

    ``Optional[UserService]`` -> ``UserService``; ``NS.UserService`` -> ``NS``
    (harmless: it simply never matches a candidate owner). Empty when only
    wrapper names remain.
    """
    for m in _TYPE_WRAPPER_RE.finditer(text or ""):
        if m.group(0) not in _TYPE_WRAPPERS:
            return m.group(0)
    return ""


def param_types_of(params_node, source: bytes) -> dict[str, str]:
    """Parameter-name -> type-name for one language-agnostic parameter list.

    Shared by the Python and TS/JS adapters, which both name the annotation
    field ``type``; the parameter name is taken from the ``pattern`` field
    when present (TS) or from the first identifier child (Python's
    ``typed_parameter``).
    """
    out: dict[str, str] = {}
    if params_node is None:
        return out

    def add(name: str, type_text: str) -> None:
        if name and name not in ("self", "cls") and re.fullmatch(r"[A-Za-z_$][\w$]*", name):
            t = first_type_ident(type_text)
            if t:
                out[name] = t

    for p in params_node.named_children:
        if p.type in ("required_parameter", "optional_parameter"):
            pat = p.child_by_field_name("pattern")
            tann = p.child_by_field_name("type")
            if pat is None or tann is None:
                continue
            add(node_text(pat, source, 120), node_text(tann, source, 200))
        elif p.type == "typed_parameter":
            kids = p.named_children
            if len(kids) >= 2 and kids[0].type == "identifier":
                add(node_text(kids[0], source, 120), node_text(kids[1], source, 200))
    return out


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
