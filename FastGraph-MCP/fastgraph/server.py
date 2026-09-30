"""FastGraph-MCP server: a small advertised surface over an SQLite code graph.

Alone (``FASTGRAPH_PROFILE=full``, the default) it is a complete navigator:
locate (code_search / symbol_info), read (read_code), call graph (call_graph /
impact_analysis), dependencies (file_deps / module_cycles), change awareness
(changes), the project map (project_overview), plus the anchored memory layer.
Next to another code server (``FASTGRAPH_PROFILE=lean``) the three tools that
duplicate it -- code_search, symbol_info, read_code -- are not advertised, and
what is left is the axis nobody else answers: graph aggregation, the change view
and cross-session memory. Lean withholds announcements, not capability; every
tool stays callable from Python.

The surface is deliberately small. Every tool definition is re-sent with each
request, so a tool is only exposed when it answers something an LSP-backed tool
cannot answer cheaply: project-wide search, the call and dependency graph,
architecture health, and git-change awareness. Everything else FastGraph can
compute stays available as an internal Python API (`fastgraph.graph` /
`fastgraph.tools.Toolbox`) and stays tested -- see the UNEXPOSED note in
``build_server`` -- but is not advertised to the model. Whichever profile runs,
nothing in the advertised text may name a tool that profile did not register,
nor mention another server (pinned by tests/test_symbol_name_paths.py).
"""

from __future__ import annotations

from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from fastgraph import __version__
from fastgraph.config import memory_enabled, navigation_enabled
from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

_ROOT_DESC = "Optional: another project root, for this one call only."
# Not "keep small: 10-20": that advice contradicted the defaults it was attached to
# (40 and 50), and an agent that cannot tell what a cap does with the leftover items
# will read a capped list as a complete one.
_LIMIT_DESC = "Max items to return."
_TRUNC_LIMIT_DESC = (
    "Max items per section (or per side). `truncated: true` on a section means there "
    "is more -- raise this or narrow the query before concluding a list is complete."
)
_SYMBOL_DESC = (
    "Symbol name: plain name, Class.method (Rust/C++ Class::method is accepted "
    "too), or a slash name path (Class/method, optional leading '/' and "
    "trailing '[i]'). Copy a qualified_name from code_search when unsure."
)
# Module level, like the descriptions above: `from __future__ import annotations`
# means the annotation string is evaluated against this module's globals when the
# tool is registered, so a local constant would raise NameError there.
_ANCHOR_DESC = (
    "What the note is about. Canonical forms: "
    "\"symbol:<rel_path>#<qualified_name>\", \"file:<rel_path>\", "
    "\"module:<dir>\", \"project:\" for repo-wide notes. A bare name "
    "(e.g. AuthService.login) is resolved against the index; it must match "
    "exactly one symbol, otherwise the candidates come back and you should "
    "re-call with the canonical anchor."
)

_INSTRUCTIONS = (
    "FastGraph is the project's code index: the call graph, project-wide search, "
    "dependencies and change awareness. A text search cannot tell a definition "
    "from a call site or follow a method to its callers; these tools can. Reach "
    "for them at these triggers:\n"
    "- about to edit a function/class -> impact_analysis(name) first\n"
    "- asked 'who calls X' / 'what does X call' -> call_graph(name, direction=…): "
    "real call edges. Empty list + unresolved_incoming>0 means callers exist but "
    "could not be pinned — never conclude 'unused'\n"
    "- about to change imports or module structure -> file_deps(path), "
    "module_cycles()\n"
    "- finished a round of edits -> changes() to re-check the blast radius; "
    "base=\"main\" covers a whole branch\n"
    "- unfamiliar repo -> project_overview() once, then navigate\n"
    "- an answer carrying pending_files + hint came from a still-building index: "
    "'not found' there means unknown, not absent -- re-run or call reindex() to "
    "finish the build\n"
)

# Appended last so the list stays one list: it used to sit in the middle of the
# bullet block, which read as a bullet that ended with two more bullets.
_INSTRUCTIONS_FOOT = (
    "\nWrong folder or empty-looking answers everywhere? "
    "activate_project(root=\"/abs/path\") once, then everything points there; "
    "every tool also takes root=<abs path> for a one-off cross-project query. "
    "All line numbers are 1-based. Responses carry locations and relationships, "
    "not file dumps.\n"
)

# Only appended when those tools are actually registered (the default profile):
# telling the model about a tool it cannot call is worse than telling it nothing.
_NAV_INSTRUCTIONS = (
    "- looking for where code lives / where a name is used -> code_search(query), "
    "not grep\n"
    "- about to open a file you have not seen -> read_code(path, structure=true) "
    "first, then read_code(path, start_line=…, end_line=…) for the part you need\n"
    "- want one symbol's source -> read_code(name); source text comes only from "
    "read_code, every other tool returns locations and relationships\n"
)


def surface_instructions(navigation: bool, memory: bool) -> str:
    """The guidance for exactly the tools this process registered.

    Order matters for something a model reads once: triggers first (they decide the
    next call), the profile-gated locate/read triggers next, memory after that, and
    the standing conventions last so they cannot break the list apart.
    """
    return (
        _INSTRUCTIONS
        + (_NAV_INSTRUCTIONS if navigation else "")
        + (_MEMORY_INSTRUCTIONS if memory else "")
        + _INSTRUCTIONS_FOOT
    )


_MEMORY_INSTRUCTIONS = (
    "\n\nProject memory — this server also remembers things across sessions, "
    "anchored to code rather than to free text (off with FASTGRAPH_MEMORY=0):\n"
    "- learned a non-obvious reason (why this algorithm, why this workaround, what "
    "was tried and rejected) -> remember(anchor=\"symbol:<file>#<qualified_name>\", "
    "body=..., kind=\"decision\"). Pass an exact canonical anchor; a bare name that "
    "matches several symbols is refused with the candidates listed, because writing "
    "it under the wrong one makes it unrecallable\n"
    "- before editing something -> recall(anchor=...) returns the notes on it; the "
    "read tools also attach matching notes to their top hits\n"
    "- finished a chunk of work -> checkpoint(label=\"...\") records the call-graph "
    "snapshot as a baseline (needs a fully built index; it will tell you if it "
    "refused)\n"
    "- next session, or reviewing a branch -> changes(since=\"that label\") "
    "diffs symbols, call edges and module cycles against it, and lists notes whose "
    "anchor no longer resolves\n"
    "- a note that turned out wrong -> forget(id=…): a wrong note steers every "
    "later session, because recall is what runs before an edit; the deleted body "
    "comes back as the undo\n"
    "nothing is written automatically: notes and baselines only appear when you call "
    "remember / checkpoint, and they live in .fastgraph/memory.sqlite.\n"
)


def build_server(root) -> MCPServer:
    db = DB(root)
    indexer = Indexer(root, db)
    tools = Toolbox(root, db, indexer)
    memory_on = memory_enabled()
    nav_on = navigation_enabled()

    server = MCPServer(
        "fastgraph",
        instructions=surface_instructions(nav_on, memory_on),
        version=__version__,
    )

    # Every read tool is read-only (it never edits source code) and
    # deterministic for a given index state, so advertise that to the client via
    # MCP tool annotations. This lets clients auto-approve and schedule calls in
    # parallel. The memory layer's two writers get their own set below -- nothing
    # here may claim read-only for a call that inserts a row.
    _READONLY = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    # The memory layer's writes must NOT inherit the read-only hints: claiming
    # read_only_hint=True is what tells a client it may auto-approve the call and
    # run it in parallel with others. A note insert, a snapshot insert and a note
    # delete are none of those three things. They still never touch project source --
    # only .fastgraph/.
    _WRITE = ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )

    def tool(fn):
        """Register a tool with a human-readable title and read-only hints."""
        title = " ".join(w.capitalize() for w in fn.__name__.split("_"))
        return server.tool(title=title, annotations=_READONLY)(fn)

    def writable_tool(fn):
        title = " ".join(w.capitalize() for w in fn.__name__.split("_"))
        return server.tool(title=title, annotations=_WRITE)(fn)

    # In lean mode the locate/read tools stay defined (the Python API and the tests
    # keep using them) but are not registered -- same treatment as the UNEXPOSED
    # list below, and it is why the instructions are composed rather than fixed:
    # guidance naming a tool the client cannot call is a wrong-tool invitation.
    advertise_nav = tool if nav_on else (lambda fn: fn)

    @tool
    def activate_project(root: Annotated[str, Field(description="Absolute path to the project folder to activate for this session; afterwards all tools run against it.")]) -> dict:
        """Point the server at a project folder for this session; afterwards all tools run against it. Call it when results look empty or clearly belong to another repo -- the server starts from its launch folder, and refuses to scan a home directory rather than guess. Every tool also accepts root=<abs path> for a one-off cross-project query."""
        return tools.activate_project(root)

    @tool
    def reindex(
        full: Annotated[bool, Field(description="true = drop the existing index and rebuild from scratch (after editing .fastgraphignore, or when results look stale).")] = False,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Finish building the index in one call: other tools stop at a time budget and report `pending_files`, this one loops until nothing is left. Can take minutes on a big repo (batches are durable, so a client timeout or an interrupt loses nothing and any later call resumes)."""
        return tools.reindex(full=full, root=root)

    @tool
    def project_overview(root: Annotated[str | None, Field(description=_ROOT_DESC)] = None) -> dict:
        """Call this FIRST in an unfamiliar repo: languages, file/symbol counts, entry points, top-level layout, cross-module dependency direction, parse errors. Read it before navigating."""
        return tools.project_overview(root=root)

    @advertise_nav
    def code_search(
        query: Annotated[str, Field(description="Keyword, symbol name, or natural-language query; matches symbol names and comment/string content (CJK ok).")],
        limit: Annotated[int, Field(description="Max results (default 10). Not paginated: narrow the query to see more rather than raising this.")] = 10,
        kind: Annotated[str | None, Field(description="Optional symbol kind filter (function/class/...); None = all kinds.")] = None,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Locate code instead of grepping for it: matches symbol names, docstrings, comments and string content (CJK ok) and ranks real definitions above text noise. First choice when the exact symbol name is unknown; `match` on each hit tells which tier found it: name | doc | content | import. Take the `qualified_name` from a hit and feed it to read_code / call_graph / impact_analysis. `count: 0` on a repo whose index reports pending_files means "not indexed yet", not "absent"."""
        return tools.code_search(query, limit=limit, kind=kind, root=root)

    @advertise_nav
    def symbol_info(
        symbol: Annotated[str, Field(description=_SYMBOL_DESC)],
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Details for a symbol (plain name or Class.method): file, lines, signature, doc, and what it calls. For the full callee list use call_graph(direction="out")."""
        return tools.symbol_info(symbol, root=root)

    @advertise_nav
    def read_code(
        target: Annotated[str, Field(description="A file path (absolute, or relative to the project root) or a symbol name (`top`, `Class.method`, `Class/method`, Rust/C++ `Class::method`).")],
        start_line: Annotated[int | None, Field(description="1-based first line; with end_line reads a window. None on a file target = the first 400 lines.")] = None,
        end_line: Annotated[int | None, Field(description="1-based last line to return.")] = None,
        structure: Annotated[bool, Field(description="true on a file target = return only its symbol list (kind, signature, lines) instead of text. Use this before reading a file you have not seen, then re-read the range you need.")] = False,
        max_lines: Annotated[int, Field(description="Max source lines when the target resolves to a symbol.")] = 200,
        limit: Annotated[int, Field(description="With structure=true: max symbols to list; `truncated` reports whether it capped.")] = 200,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Read code — by file, by line window, by symbol, or just a file's structure. The response says which branch ran in `mode`: lines | structure | symbol_body. A symbol target returns exactly that symbol's body, so prefer it over a file window once you know the name. Docs and configs are readable too, not only indexed sources; paths outside the project, dot/excluded segments and `.fastgraphignore` matches stay unreadable. `total_lines`/`truncated` report when more remains."""
        return tools.read_code(
            target, start_line=start_line, end_line=end_line, structure=structure,
            max_lines=max_lines, limit=limit, root=root,
        )

    @tool
    def call_graph(
        symbol: Annotated[str, Field(description=_SYMBOL_DESC)],
        direction: Annotated[str, Field(description='"in" = who calls it, "out" = what it calls, "both" = both (default).')] = "both",
        depth: Annotated[int, Field(description="Levels to traverse (1 = direct neighbours only); applies to the direction asked for.")] = 1,
        limit: Annotated[int | None, Field(description="Max entries per side; None = 30 callers / 50 callees. `truncated` per side is not reported -- raise this if a list looks short.")] = None,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Use for 'who calls X' and 'what does X call': stored call edges, not text matches — grep hits comments and unrelated names, this follows actual invocations. direction="both" returns them nested as `in` / `out`, each with its own `hint` and unresolved counts. `via` on callers: "resolved" (a stored edge) or "text" (an unresolved edge whose text merely names the symbol -- a guess). `evidence` on callees: "same_file"/"imported" (file-level proof) or "name_only" (name alone -- a guess). `unresolved_incoming`/`unresolved_outgoing` count what the name-based resolver could not link, so an empty list is NOT proof that nothing calls it. For change-impact grading use impact_analysis."""
        return tools.call_graph(symbol, direction=direction, depth=depth, limit=limit, root=root)

    @tool
    def impact_analysis(
        symbol: Annotated[str, Field(description=_SYMBOL_DESC)],
        max_depth: Annotated[int, Field(description="How many levels of indirect impact to include (1 = direct callers only).")] = 2,
        limit: Annotated[int, Field(description="Max symbols per tier.")] = 40,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Run BEFORE editing a symbol to see who is affected: direct callers (HIGH), indirect (MEDIUM), tests listed separately, plus files that import its module without calling it (`import_dependents`). Check `error`: an unresolved name comes back as `error: "not_found"` with HIGH and MEDIUM both empty, which is NOT "nothing depends on it" -- it is the name. For a plain caller list use call_graph(direction="in")."""
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
        max_cycles: Annotated[int, Field(description="Max cycles to report, largest first.")] = 10,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """Architecture health check: which files import each other in a circle (strongly connected components), largest first. Run it before splitting or re-layering a package -- a cycle means the split you plan is already entangled. `count: 0` means no cycle was found in the current index, so check `pending_files` before treating it as clean."""
        return tools.module_cycles(max_cycles=max_cycles, root=root)

    @tool
    def changes(
        since: Annotated[str | None, Field(description="Label of a saved baseline (recorded by checkpoint): compares the call graph's TOPOLOGY against it (symbols added/removed, call edges broken, cycles appeared, notes whose anchor no longer resolves).")] = None,
        to: Annotated[str | None, Field(description="With `since`: a second baseline to compare two snapshots, so the answer does not depend on the current index. None = compare against the live index.")] = None,
        base: Annotated[str | None, Field(description="Without `since`: git rev (branch, tag, HEAD~3) to diff against the working tree, covering a whole branch instead of only uncommitted changes. Omit both = uncommitted changes.")] = None,
        limit: Annotated[int, Field(description=_TRUNC_LIMIT_DESC)] = 50,
        root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
    ) -> dict:
        """'What moved?' -- the parameter you set picks the time base. `since=<baseline label>` gives a call-graph topology diff of a checkpoint baseline; `base=<git rev>` or nothing gives the git view of the current edits (changed files/symbols -> affected callers). Run it AFTER finishing edits. Each section caps at `limit` and says `truncated`. Topology mode needs complete indexes on both sides and refuses otherwise; its edge differences are the name-based resolver's VIEW, not proof a call broke — verify with call_graph(direction="in"). Notes whose anchor no longer resolves come back with `moved_to` when a git rename explains it. With the memory layer off, `since` is refused rather than silently answered as the git view."""
        return tools.changes(since=since, to=to, base=base, limit=limit, root=root)

    # ---- 项目记忆层：默认注册，FASTGRAPH_MEMORY=0 时整层消失 ----
    # Advertised rather than held back because the memory tools answer questions
    # no read-only navigation tool can (what was decided, and what moved since).
    # On by default: the cost is these five schemas and nothing else -- no file is
    # created until something is written, so a project that never uses notes gains
    # nothing but the option. Off, the surface is the read-only set alone.
    if memory_on:
        @writable_tool
        def remember(
            anchor: Annotated[str, Field(description=_ANCHOR_DESC)],
            body: Annotated[str, Field(description="The note itself: the decision, warning, todo or context, in your own words. Max 20k chars.")],
            kind: Annotated[str, Field(description="decision | warning | todo | context | adr. 'decision' = why the code is this way.")] = "context",
            source: Annotated[str, Field(description="Optional where-it-came-from reference: URL, file path, ticket id.")] = "",
            root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
        ) -> dict:
            """Pin a durable note (a decision, warning, todo, context) to a symbol / file / module / the project. Use it when you learn a reason that is not in the code ('why PBKDF2 not bcrypt', what was tried and rejected) — the next session starts with nothing. recall(anchor=…) reads it back, and the read tools attach matching notes to their top hits. Writes to .fastgraph/memory.sqlite only, never to source."""
            return tools.remember(anchor, body, kind=kind, source=source, root=root)

        @tool
        def recall(
            anchor: Annotated[str, Field(description="Canonical anchor (see remember) or a bare name/path to resolve. Omit it (or pass \"\") for every note in this project -- that is a whole-store read, not 'whatever you are looking at', because the server keeps no current-symbol state.")] = "",
            kind: Annotated[str | None, Field(description="Optional kind filter: decision | warning | todo | context | adr; None = all kinds.")] = None,
            include_orphans: Annotated[bool, Field(description="true = also return notes whose anchor no longer matches the index (renamed or deleted code), each marked anchor_resolved=false. Return them to decide what to do: re-anchor with remember(anchor=<new>, body=…), then forget(id=<that note's id>) the stale one.")] = False,
            limit: Annotated[int, Field(description=_LIMIT_DESC)] = 50,
            root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
        ) -> dict:
            """Read the notes anchored on a symbol / file / module (or all notes). Call it BEFORE editing, and again when a note is expected but nothing comes back. To store a new note use remember."""
            return tools.recall(anchor, kind=kind, include_orphans=include_orphans, limit=limit, root=root)

        @writable_tool
        def forget(
            id: Annotated[int, Field(description="The numeric id of the note to remove: it comes from a recall() result, and remember() returns it too.")],
            root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
        ) -> dict:
            """Delete one stored note by id. Use it when a note turned out wrong, describes a decision that no longer holds, or is an orphan you have already re-anchored -- a wrong note is worse than no note, because recall is what runs before an edit. The removed row comes back whole in `removed`, so a mistaken id is one remember() away from being undone. Notes only: baselines from checkpoint stay."""
            return tools.forget(id, root=root)

        @writable_tool
        def checkpoint(
            label: Annotated[str, Field(description="Name for this baseline, e.g. 'before-auth-refactor'. changes(since=<label>) looks it up; re-using a name overwrites the baseline (the newest wins).")],
            ref: Annotated[str | None, Field(description="Optional git rev to record with the baseline; default is HEAD.")] = None,
            root: Annotated[str | None, Field(description=_ROOT_DESC)] = None,
        ) -> dict:
            """Record the call graph as a baseline to diff later. Refuses while the index is still building (such a snapshot would record build progress, not code) -- call reindex() and retry. Call it at a decision point — before a refactor, or at the end of a session — then changes(since=<label>) answers 'what moved since then'."""
            return tools.checkpoint(label, ref=ref, root=root)

        # `what_changed` is registered as the read-only `changes` tool above rather
        # than here: the git view and the baseline view answer one question, and a
        # client that picked wrong was the failure mode. Its internal method stays
        # callable as tools.what_changed(since=...) for the `since=` branch.

    # ---- UNEXPOSED: implemented and tested, but not advertised ----
    # Each of these is one call away from being re-exposed; they are held back
    # because every advertised tool costs context on every request and these add
    # nothing that the tools above (or an LSP-backed one) do not already answer:
    #   trace_path     -- same data as call_graph(direction="in", depth>=2)
    #   rename_impact  -- symbol_info + call_graph carry the data; executing a
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
        # The same decision list the server advertises, composed for the tools this
        # process actually registered: a client that relies on this prompt instead
        # of instructions would otherwise be told about tools that are not there.
        return surface_instructions(nav_on, memory_on)

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
