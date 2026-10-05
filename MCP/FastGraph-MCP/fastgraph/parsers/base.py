"""Parse result model shared by all language adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


_WS_RE = re.compile(r"\s+")
# padding a collapsed line break leaves beside a parenthesis: `f(\n    a,\n) `
_SIG_PAD_RE = re.compile(r"\(\s+|\s+\)")


def normalize_signature(sig: str) -> str:
    """Collapse a declaration to a single line, at index time.

    Parsers store the declaration verbatim (CRLF and continuation lines
    included), and signatures ride along in every list payload --
    ``code_search`` / ``file_symbols`` / ``find_callers`` / ``impact_analysis``.
    A six-parameter function therefore spent ~120 bytes of whitespace on every
    row: ``file_symbols`` on black/nodes.py cost 11k characters for 40 symbols.
    Normalizing once here fixes all of them, instead of in each consumer.
    """
    collapsed = _WS_RE.sub(" ", sig or "").strip()
    return _SIG_PAD_RE.sub(lambda m: m.group(0).strip(), collapsed)


@dataclass
class CallRef:
    """A call/reference made inside a symbol: resolved later."""

    target: str            # as written in code, e.g. "foo" or "self.bar"
    line: int              # 1-based source line
    rtype: str = "calls"   # calls | references


@dataclass
class SymbolInfo:
    name: str
    kind: str                     # class | function | method | struct | interface | impl ...
    qualified_name: str           # e.g. "package.module.ClassName.method"
    signature: str
    doc: str
    start_line: int               # 1-based, inclusive
    end_line: int
    start_col: int
    end_col: int
    parent: Optional[str] = None  # qualified parent name
    calls: list[CallRef] = field(default_factory=list)   # calls inside this symbol
    bases: list[CallRef] = field(default_factory=list)    # inherited types
    decorated: bool = False       # registered via a decorator/annotation
                                  # (FastAPI @app.get, Spring @GetMapping, ...)
    param_types: dict = field(default_factory=dict)
    """Declared parameter types, ``param_name -> type_name``.

    Only *explicit annotations* are recorded (Python ``svc: UserService``, TS
    ``function f(svc: UserService)``) — no inference. The resolver uses them
    as receiver evidence: ``svc.run(...)`` with a declared type pins the
    owner, turning otherwise-unresolvable member calls into resolved edges."""


@dataclass
class ImportRef:
    """Module-level import statement."""

    text: str      # raw import text, e.g. "from .service import AuthService"
    line: int
    kind: str = ""


@dataclass
class ParseResult:
    language: str
    symbols: list[SymbolInfo]
    imports: list[ImportRef]
    module_doc: str = ""
    template_refs: list[str] = field(default_factory=list)
    module_calls: list[CallRef] = field(default_factory=list)
    """Calls executed at import time (module level), i.e. outside any symbol.

    Registration/wiring code such as ``register_adapter(PythonAdapter())`` or
    ``app.include_router(...)`` lives here; without it the call graph and the
    dead-code analysis would be blind to every module-level call site.
    Carried by the per-file ``module`` symbol (see Indexer._store_file)."""