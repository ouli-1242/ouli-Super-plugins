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
    "FastGraph is the project's code index: the real call graph, project-wide "
    "search, dependencies and change awareness. Text search cannot tell a "
    "definition from a call site and cannot follow a method to its callers — "
    "these tools can. Reach for them at these triggers:\n"
    "- looking for where code lives / where a name is used -> code_search(query), "
    "not grep\n"
    "- about to open a file you have not seen -> file_symbols(path) first\n"
    "- asked 'who calls X' / 'where is X used' -> find_callers(name): real call "
    "edges. Empty list + unresolved_incoming>0 means callers exist but could not "
    "be pinned — never conclude 'unused'\n"
    "- about to edit a function/class -> impact_analysis(name) first\n"
    "- about to change imports or module structure -> file_deps(path), "
    "module_cycles()\n"
    "- want one symbol's source -> symbol_body(name); read_file only for whole "
    "files or non-code text\n"
    "- finished a round of edits -> changed_context() to re-check the blast "
    "radius; pass base=\"main\" to cover a whole branch\n"
    "- unfamiliar repo -> project_overview() once, then navigate\n"
    "wrong folder? activate_project(root=\"/abs/path\") once, then everything "
    "points there; every tool also takes root=<abs path> for a one-off "
    "cross-project query. All line numbers are 1-based. Responses are compact "
    "by design: locations + relationships, source text only via read_file / "
    "symbol_body."
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
        """Call this FIRST in an unfamiliar repo: languages, file/symbol counts, entry points, top-level layout, cross-module dependency direction, parse errors. One call replaces a dozen exploratory greps."""
        return tools.project_overview(root=root)

    @tool
    def code_search(
        query: Annotated[str, Field(description="Keyword, symbol name, or natural-language query; matches symbol names and comment/string content (CJK ok).")],
        limit: Annotated[int, Field(description=_LIMIT_DESC)] = 10,
        kind: Annotated[str | None, Field(description="Optional symbol kind filter (function/class/...); None = all kinds.")] = None,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Use INSTEAD of grep/glob to locate code: matches symbol names, docstrings, comments and string content (CJK ok), and ranks real definitions above text noise. First choice when the exact symbol name is unknown; `match` tells which tier hit: name | doc | content | import."""
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
        """Use BEFORE reading a file you have not seen: returns its symbol list (kind, signature, lines) so you can jump straight to the part you need instead of scanning the body. `truncated` reports whether `limit` capped the list."""
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
        """Read one symbol's source body - PREFER this over read_file when you know the symbol's name, since it returns exactly that symbol instead of a file window."""
        return tools.symbol_body(symbol, max_lines=max_lines, root=root)

    @tool
    def find_callers(
        symbol: Annotated[str, Field(description=_SYMBOL_DESC)],
        limit: Annotated[int, Field(description=_LIMIT_DESC)] = 30,
        depth: Annotated[int, Field(description="How many levels of callers to traverse (1 = direct callers only).")] = 1,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Use for 'who calls X' / 'where is X used': real call edges, not text matches — grep hits comments and unrelated names, this follows actual invocations. depth>=2 returns transitive callers. Each entry carries `via`: "resolved" (a stored call edge) or "text" (an unresolved edge whose text merely names the symbol -- a guess). `unresolved_incoming` counts edges that could not be resolved, so an empty caller list is NOT proof that nothing calls it. For change-impact grading use impact_analysis."""
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
        """Run BEFORE editing a symbol to see who is affected: direct callers (HIGH), indirect (MEDIUM), tests listed separately, plus files that import its module without calling it (`import_dependents`). For a plain caller list use find_callers."""
        return tools.impact_analysis(symbol, max_depth=max_depth, limit=limit, root=root)

    @tool
    def file_deps(
        path: Annotated[str, Field(description="File path (absolute, or relative to the project root).")],
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Check BEFORE changing a file's imports or its public surface: what it imports (internal resolved, external listed separately) and which files import it. For import cycles across the project use module_cycles."""
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
        base: Annotated[str | None, Field(description="Optional git rev (branch, tag, HEAD~3): diff that ref against the working tree to cover a whole branch instead of uncommitted changes only.")] = None,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Run AFTER finishing edits: git diff -> changed files/symbols -> affected callers, so you can verify the blast radius before declaring done. Pass base (e.g. "main") to see a whole branch's footprint, not just uncommitted changes."""
        return tools.changed_context(limit=limit, base=base, root=root)

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

    # A pullable resource mirror of project_overview: clients that list
    # resources can fetch the project map without spending a tool slot, and
    # it refreshes through the same lazy incremental path.
    @server.resource(
        "fastgraph://overview",
        name="Project Overview",
        title="Project Overview",
        description="Project map: languages, file/symbol counts, entry points, "
        "top-level layout, cross-module dependency direction, parse errors.",
        mime_type="application/json",
    )
    def overview_resource() -> dict:
        return tools.project_overview()

    # A user/client-invocable prompt that loads the navigation workflow into
    # the conversation — useful with clients that do not surface server
    # instructions to the model.
    @server.prompt(
        name="fastgraph-workflow",
        title="FastGraph navigation workflow",
        description="Loads the when-to-use-which-tool decision list for "
        "FastGraph into the conversation.",
    )
    def workflow_prompt() -> str:
        return _INSTRUCTIONS

    # Kept for run_stdio's teardown: release the SQLite handles (main root and
    # any cross-project caches) when the server stops, so a killed session does
    # not leave -wal/-shm files behind on every project it touched.
    server._fastgraph_tools = tools  # type: ignore[attr-defined]

    return server


def run_stdio(root):
    server = build_server(root)
    try:
        server.run()
    finally:
        tools = getattr(server, "_fastgraph_tools", None)
        if tools is not None:
            tools.close()
            try:
                tools.db.close()
            except Exception:
                pass
