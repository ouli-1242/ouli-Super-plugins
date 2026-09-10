"""FastGraph-MCP server: one fixed 13-tool surface over an SQLite code graph.

The same surface is used whether FastGraph runs alone or next to another code
MCP: locate (code_search / symbol_info / file_symbols), read (read_file /
symbol_body), call graph (find_callers / find_callees / impact_analysis),
dependencies (file_deps / module_cycles), change awareness (changed_context)
and the project map (project_overview).

The surface is deliberately small. Every tool definition is re-sent with each
request, so a tool is only exposed when it answers something an LSP-backed tool
cannot answer cheaply: project-wide search, the call and dependency graph,
architecture health, and git-change awareness. Everything else FastGraph can
compute stays available as an internal Python API (`fastgraph.graph` /
`fastgraph.tools.Toolbox`) and stays tested -- see the UNEXPOSED note in
``build_server`` -- but is not advertised to the model.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

_ROOT_DESC = "Optional: another project root, for this one call only."
_LIMIT_DESC = "Max results to return (keep small: 10-20)."
_SYMBOL_DESC = (
    "Symbol name: plain name, Class.method, or a slash name path "
    "(Class/method, optional leading '/' and trailing '[i]')."
)

_INSTRUCTIONS = (
    "FastGraph: project index for locating code, the call graph, dependencies and "
    "recent changes. Results are compact locations/symbols/relationships; source "
    "text comes only from read_file / symbol_body.\n"
    "Workflow:\n"
    "- wrong folder? activate_project(root=\"/abs/path\") once, then everything points there\n"
    "- orient yourself: project_overview()\n"
    "- locate code: code_search(query) — names, comments and strings (CJK ok)\n"
    "- inspect before reading: file_symbols(path) for a file, symbol_info(name) for a symbol\n"
    "- read: symbol_body(name) (preferred) or read_file(path, start_line?, end_line?)\n"
    "- call graph: find_callers(name, depth?) / find_callees(name, depth?); "
    "traced chains: find_callers(depth=3)\n"
    "- empty is not none: find_callers/find_callees may return nothing while "
    "`unresolved_incoming`/`unresolved_outgoing` reports edges whose target is "
    "not statically knowable -- treat that as unknown, never as unused\n"
    "- before changing code: impact_analysis(name); imports and cycles: file_deps(path), module_cycles()\n"
    "- after editing: changed_context()\n"
    "All line numbers are 1-based. Keep limit small (10-20); responses are compact by design."
)


def build_server(root) -> MCPServer:
    db = DB(root)
    indexer = Indexer(root, db)
    tools = Toolbox(root, db, indexer)

    server = MCPServer("fastgraph", instructions=_INSTRUCTIONS)

    # Every FastGraph tool is read-only (it never edits source code) and
    # deterministic for a given index state, so advertise that to the client via
    # MCP tool annotations. This lets clients auto-approve and schedule calls in
    # parallel.
    _READONLY = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def tool(fn):
        """Register a tool with a human-readable title and read-only hints."""
        title = " ".join(w.capitalize() for w in fn.__name__.split("_"))
        return server.tool(title=title, annotations=_READONLY)(fn)

    @tool
    def activate_project(root: Annotated[str, Field(description="Absolute path to the project folder to activate for this session; afterwards all tools run against it.")]) -> dict:
        """Point the server at a project folder for this session; afterwards all tools run against it. Every tool also accepts root=<abs path> for a one-off cross-project query."""
        return tools.activate_project(root)

    @tool
    def project_overview(root: Annotated[str | None, Field(description=_ROOT_DESC)] = None) -> dict:
        """Project map: languages, file/symbol counts, entry points, top-level layout, cross-module dependency direction, parse errors. Worth calling first in an unfamiliar repo."""
        return tools.project_overview(root=root)

    @tool
    def code_search(
        query: Annotated[str, Field(description="Keyword, symbol name, or natural-language query; matches symbol names and comment/string content (CJK ok).")],
        limit: Annotated[int, Field(description=_LIMIT_DESC)] = 10,
        kind: Annotated[str | None, Field(description="Optional symbol kind filter (function/class/...); None = all kinds.")] = None,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Find where code lives by keyword, symbol name, or natural language. First choice when the exact symbol name is unknown. `match` tells which tier hit: name | doc | content | import."""
        return tools.code_search(query, limit=limit, kind=kind, root=root)

    @tool
    def symbol_info(
        symbol: Annotated[str, Field(description=_SYMBOL_DESC)],
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Details for a symbol (plain name or Class.method): file, lines, signature, doc, and what it calls. For a full callee list use find_callees."""
        return tools.symbol_info(symbol, root=root)

    @tool
    def file_symbols(
        path: Annotated[str, Field(description="File path (absolute, or relative to the project root).")],
        limit: Annotated[int, Field(description=_LIMIT_DESC)] = 200,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Symbols in one file (kind, signature, lines) - inspect structure before reading the file. `truncated` reports whether `limit` capped the list."""
        return tools.file_symbols(path, limit=limit, root=root)

    @tool
    def read_file(
        path: Annotated[str, Field(description="File path (absolute, or relative to the project root).")],
        start_line: Annotated[int, Field(description="1-based first line to return.")] = 1,
        end_line: Annotated[int | None, Field(description="1-based last line to return; None = end of file.")] = None,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Read a text file from the project, or a line range of it — source, docs and config alike (not only indexed sources). Without `end_line` the first 400 lines are returned; `total_lines` and `truncated` say whether more remains. Paths outside the project, dot/excluded segments and `.fastgraphignore` matches stay unreadable."""
        return tools.read_file(path, start_line=start_line, end_line=end_line, root=root)

    @tool
    def symbol_body(
        symbol: Annotated[str, Field(description=_SYMBOL_DESC)],
        max_lines: Annotated[int, Field(description="Max source lines to return for the symbol.")] = 200,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Read one symbol's source body - preferred over read_file when you know the symbol, since it returns only that symbol."""
        return tools.symbol_body(symbol, max_lines=max_lines, root=root)

    @tool
    def find_callers(
        symbol: Annotated[str, Field(description=_SYMBOL_DESC)],
        limit: Annotated[int, Field(description=_LIMIT_DESC)] = 30,
        depth: Annotated[int, Field(description="How many levels of callers to traverse (1 = direct callers only).")] = 1,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Who calls this symbol. depth>=2 returns transitive callers. Each entry carries `via`: "resolved" (a stored call edge) or "text" (an unresolved edge whose text merely names the symbol -- a guess). `unresolved_incoming` counts edges that could not be resolved, so an empty caller list is NOT proof that nothing calls it. For change-impact grading use impact_analysis."""
        return tools.find_callers(symbol, limit=limit, depth=depth, root=root)

    @tool
    def find_callees(
        symbol: Annotated[str, Field(description=_SYMBOL_DESC)],
        limit: Annotated[int, Field(description=_LIMIT_DESC)] = 50,
        depth: Annotated[int, Field(description="How many levels of callees to traverse (1 = direct calls only).")] = 1,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """What this symbol calls. depth>=2 returns the downstream call tree. `unresolved_outgoing` counts callees that could not be resolved: the list is incomplete by that many edges."""
        return tools.find_callees(symbol, limit=limit, depth=depth, root=root)

    @tool
    def impact_analysis(
        symbol: Annotated[str, Field(description=_SYMBOL_DESC)],
        max_depth: Annotated[int, Field(description="How many levels of indirect impact to include (1 = direct callers only).")] = 2,
        limit: Annotated[int, Field(description=_LIMIT_DESC)] = 40,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Who is affected if this symbol changes: direct callers (HIGH), indirect (MEDIUM), tests listed separately. For a plain caller list use find_callers."""
        return tools.impact_analysis(symbol, max_depth=max_depth, limit=limit, root=root)

    @tool
    def file_deps(
        path: Annotated[str, Field(description="File path (absolute, or relative to the project root).")],
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """What a file imports (internal resolved, external listed separately) and which files import it. For import cycles across the project use module_cycles."""
        return tools.file_deps(path, root=root)

    @tool
    def module_cycles(
        max_cycles: Annotated[int, Field(description="Max cycles to report (largest first).")] = 10,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Import cycles between files (strongly connected components), largest first. Architecture health check."""
        return tools.module_cycles(max_cycles=max_cycles, root=root)

    @tool
    def changed_context(
        limit: Annotated[int, Field(description=_LIMIT_DESC)] = 50,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """After edits: git diff -> changed files/symbols -> affected callers."""
        return tools.changed_context(limit=limit, root=root)

    # ---- UNEXPOSED: implemented and tested, but not advertised ----
    # Each of these is one call away from being re-exposed; they are held back
    # because every advertised tool costs context on every request and these add
    # nothing that the tools above (or an LSP-backed one) do not already answer:
    #   trace_path     -- same data as find_callers(depth>=2)
    #   rename_impact  -- symbol_info + find_callers carry the data; executing a
    #                     rename is the editor's / LSP tool's job
    #   type_hierarchy -- inheritance is answered per symbol with better precision
    #                     by an LSP-backed tool
    #   unused_symbols -- noisy on a tree-sitter call graph, rarely actionable
    #   hot_symbols    -- project_overview reports entry points and layering
    #   file_metrics   -- low frequency
    #   get_status     -- project_overview reports the same index counts

    return server


def run_stdio(root):
    server = build_server(root)
    server.run()
