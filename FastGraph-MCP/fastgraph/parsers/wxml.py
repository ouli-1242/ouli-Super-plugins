"""Native WeChat mini-program WXML template adapter.

Extracts event-handler and data-binding identifiers from .wxml templates so
page .js handlers bound via `bindtap="goMemory"` are not reported as dead
code, and the template text becomes searchable content. Symbol-less: the
identifier list is consumed by unused_symbols via the sibling .js file.
"""

from __future__ import annotations

import re

from fastgraph.parsers.base import ParseResult
from fastgraph.parsers.registry import register_adapter

# event bindings: bindtap / catchtap / bind:tap / catch:tap / mut-bind:tap
_EVENT_RE = re.compile(
    r"""(?:bind|catch|mut-bind)[:\w-]*\s*=\s*"([\w.]+)"|(?:bind|catch|mut-bind)[:\w-]*\s*=\s*'([\w.]+)'"""
)
# mustache interpolation + wx: directives
_EXPR_RE = re.compile(
    r"""\{\{\s*([^{}]+?)\s*\}\}
    |wx:(?:if|elif|else|for|for-item|for-index|key)\s*=\s*"([^"]*)"
    |wx:(?:if|elif|else|for|for-item|for-index|key)\s*=\s*'([^']*)'
    """,
    re.VERBOSE,
)
# wx:for introduces loop variables; framework keywords are not members
_SKIP = {"true", "false", "null", "undefined", "this", "item", "index", "key"}


class WxmlAdapter:
    lang = "wxml"
    exts = (".wxml",)

    def parse(self, source: bytes) -> ParseResult:
        text = source.decode("utf-8", "replace")
        refs: set[str] = set()
        for m in _EVENT_RE.finditer(text):
            name = next((g for g in m.groups() if g), "")
            refs.add(name.rsplit(".", 1)[-1])
        for m in _EXPR_RE.finditer(text):
            expr = next((g for g in m.groups() if g), "")
            for ident in re.findall(r"[A-Za-z_$][\w$]*", expr):
                if ident not in _SKIP:
                    refs.add(ident)
        return ParseResult(
            language=self.lang,
            symbols=[],
            imports=[],
            template_refs=sorted(refs),
        )


register_adapter(WxmlAdapter())