"""Parse result model shared by all language adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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