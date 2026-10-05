"""MCP tool implementations (the locate/analyse surface)."""

from __future__ import annotations

import threading
from pathlib import Path

from fastgraph.config import MAX_FILE_SIZE, env_flag, memory_enabled
from fastgraph.db import DB
from fastgraph import graph, gitutil, memory as mem
from fastgraph.graph import name_path
from fastgraph.index import Indexer
from fastgraph.memory import Memory
from fastgraph.search import code_search


def _debug_enabled() -> bool:
    """FASTGRAPH_DEBUG=1 restores per-call index refresh stats in responses."""
    return env_flag("FASTGRAPH_DEBUG", default=False)


# Hard cap on source text returned by read_file / symbol_body. FastGraph is a
# low-context MCP; an unbounded read would defeat that, so oversized content is
# truncated and the response carries an explicit `truncated` flag.
MAX_READ_CHARS = 40_000

# Default window when the caller passes no end_line. Without it a single
# read_file() of a large file (a 2871-line README was measured) returns up to
# MAX_READ_CHARS, ~10k tokens, in one call; callers that really want more can
# pass an explicit range.
MAX_READ_LINES = 400

# Cross-project queries (root=) cache a (DB, indexer) pair per root and each
# holds an open SQLite connection. The cache is bounded with LRU eviction so a
# session touching many projects neither accumulates file handles/memory nor
# keeps other projects' .fastgraph/ locked on Windows. Evicted roots are
# reopened transparently on the next query (cost: one incremental refresh).
MAX_CACHED_ROOTS = 8

# Context budget for the memory layer. FastGraph's pitch is low-context answers,
# so a note attached to an unrelated read is capped hard: short body, few rows,
# and `recall` is the tool for asking for the rest.
NOTE_BODY_BRIEF = 400
NOTES_PER_QUERY_MAX = 8

# A note is a record, not a document: past this it belongs in a file the anchor
# points at. Refusing (instead of truncating on write) keeps `recall` honest --
# what you read back is what was stored.
MAX_NOTE_BODY = 20_000


def _cap(rows: list, limit: int) -> tuple[list, bool]:
    return rows[:limit], len(rows) > limit


def _diff_lines(old: list[str], new: list[str], limit: int):
    """(added, removed) as (rows, truncated) pairs, ordered for stable output."""
    a, b = set(old), set(new)
    return _cap(sorted(b - a), limit), _cap(sorted(a - b), limit)


def _tag_callee_evidence(db: DB, rows: list[dict], roots: list[dict]) -> None:
    """Stamp each callee with how much the name-based resolver actually proved.

    ``children.push(...)`` is stored twice -- bare ``push`` and qualified
    ``excessDomChildren.push`` -- and the bare copy skips the member-evidence
    gate, so preact's ``excessDomChildren.push()`` linked to a ``const push``
    declared inside an unrelated browser test. Dropping the bare copy is not
    safe either (``self.x()`` resolves through it), so the edge stays and the
    caller is told what it is worth: ``same_file`` / ``imported`` (the callee
    lives in a file the caller imports) or ``name_only``.

    With ``depth >= 2`` a level-2 callee's caller is an intermediate symbol, not
    one of ``roots``, so it can be labelled ``name_only`` while genuinely
    imported -- the label understates evidence, never overstates it.
    """
    caller_files = {r.get("path") for r in roots if r.get("path")}
    imported: set[str] = set()
    for path in caller_files:
        for imp in graph.module_dependencies(db, path).get("imports", ()):
            imported.update(imp.get("resolves_to") or ())
    for row in rows:
        f = row.get("file") or ""
        row["evidence"] = (
            "same_file" if f in caller_files
            else "imported" if f in imported
            else "name_only"
        )


class Toolbox:
    """Stateful tool handler bound to one project root.

    An optional per-call ``root`` argument switches to another project:
    a dedicated (DB, indexer) pair is lazily created and cached per root.
    This makes the server usable from desktop clients, which launch MCP
    processes with a fixed cwd and cannot pass the working folder.
    """

    def __init__(self, root, db: DB, indexer: Indexer):
        self.root = root
        self.db = db
        self.indexer = indexer
        self._active_root: Path | None = None
        self._roots: dict[Path, "Toolbox"] = {}
        # MCP servers dispatch tool calls on a thread pool; activate_project and
        # the per-call root= switch both mutate _roots, so guard it.
        self._roots_lock = threading.RLock()
        self._last_changed: list[str] = []
        self._last_large_files: list[str] = []
        self._debug = _debug_enabled()
        # Opened on first use: with the layer off no Memory is ever constructed,
        # and with it on reading notes must not create the file (see
        # _memory_if_present), so an untouched project gains nothing.
        self._memory: Memory | None = None

    # ------------------------------------------------------------- memory

    def _memory_on(self) -> bool:
        return memory_enabled()

    @property
    def memory(self) -> Memory:
        if self._memory is None:
            self._memory = Memory(self.root)
        return self._memory

    def _memory_if_present(self) -> Memory | None:
        """The store when notes exist or will, None when nothing was ever written.

        Reading (note attachment, `recall`, "which baselines do I have") has to be
        side-effect-free: the layer is on by default, and a project would otherwise
        get a persistent `memory.sqlite` the moment someone called `symbol_info`.
        "nothing is written until you call remember" has to hold for the file too.
        """
        if self._memory is None and not (self.db.index_dir / "memory.sqlite").exists():
            return None
        return self.memory

    def _memory_off(self) -> dict:
        return {
            "ok": False,
            "error": "memory layer is off",
            "hint": "it is disabled by FASTGRAPH_MEMORY=0; unset it to get remember / recall / checkpoint / forget back",
        }

    def _index_incomplete(self, refresh: dict) -> bool:
        """True when the graph is not fully built, so a snapshot is meaningless.

        `_resolve_all` only runs once every file is indexed (index.py), and it
        deliberately refuses to link edges against a half-indexed symbol set. A
        snapshot of a still-building index therefore differs from a snapshot of
        the *same code* fully indexed -- and `what_changed` would report that
        build progress as a topology change.
        """
        return bool(
            refresh.get("skipped") or refresh.get("pending_files") or refresh.get("pending_edges")
        )

    def _resolve_anchor(self, anchor: str) -> tuple[tuple[str, str] | None, dict | None]:
        """anchor text -> ((anchor_type, anchor_key), None) or (None, error payload).

        Canonical text (`symbol:rel#qname`, `file:rel`, `module:dir`, `project:`)
        is validated against the index; anything else is *looked up*, which is
        where ambiguity lives: `find_symbols` on a plain name returns every file
        declaring it, ranked. Guessing which one the caller meant would write a
        decision under the wrong primary key and make it unrecallable, so more
        than one hit is refused with the candidates listed.
        """
        raw = (anchor or "").strip()
        parsed = mem.parse_anchor(raw)
        if parsed is not None:
            atype, key = parsed
            if atype == "project":
                return (atype, key), None
            problem = self._anchor_gap(atype, key)
            if problem is None:
                return (atype, key), None
            return None, {"anchor": raw, **problem}
        if not raw:
            return None, {"anchor": raw, "error": "anchor is empty", "hint": "use symbol:<rel>#<qualified_name>, file:<rel>, module:<dir> or project:"}

        # path-shaped text first: a bare `src/auth.py` must not be read as a symbol
        rel = graph.resolve_file(self.db, raw)
        if rel is not None:
            return ("file", mem.normalize_rel(rel)), None
        plain = mem.normalize_rel(raw)
        if "/" in plain or "." in plain.rsplit("/", 1)[-1]:
            # not in the index, but maybe a config/doc the read path would open
            if self._file_known(plain):
                return ("file", plain), None
        d = mem.normalize_rel(raw).rstrip("/")
        if d and self.db.conn.execute(
            "SELECT 1 FROM files WHERE path LIKE ? ESCAPE '\\' LIMIT 1", (mem.like_prefix(d),)
        ).fetchone():
            return ("module", d), None
        hits = graph.find_symbols(self.db, raw, limit=10)
        if len(hits) == 1:
            h = hits[0]
            return ("symbol", mem.symbol_key(h.get("path") or "", h.get("qualified_name") or "")), None
        if len(hits) > 1:
            return None, {
                "anchor": raw,
                "error": f"{len(hits)} symbols match, the anchor is ambiguous",
                "candidates": [
                    mem.symbol_anchor(h.get("path") or "", h.get("qualified_name") or "") for h in hits[:10]
                ],
                "hint": "re-call with the exact 'symbol:<file>#<qualified_name>' anchor from candidates",
            }
        if "#" not in raw:
            return None, {
                "anchor": raw,
                "error": f"nothing in the index matches {raw!r} as a symbol, file or module",
            }
        return None, self._anchor_gap("symbol", raw) or {
            "anchor": raw,
            "error": "nothing in the index matches this anchor",
        }

    def _file_known(self, rel: str) -> bool:
        """Is `rel` a file a note may be pinned to?

        Anything the read path would open, not only indexed sources: a decision
        about why a dependency is pinned, or why a doc says what it says, is
        project memory too -- `package.json` and `README.md` are never in the
        symbols table, so validating anchors against the index alone rejected
        them (found on preact, where the test rename was `oxlint.json` ->
        `.oxlintrc.json`). Dot/excluded and `.fastgraphignore` paths stay out,
        which is the same boundary reading already enforces.
        """
        if self.db.conn.execute("SELECT 1 FROM files WHERE path = ? LIMIT 1", (rel,)).fetchone():
            return True
        resolved, _indexed, _reason = self._resolve_read_target(self, rel)
        return resolved is not None

    def _indexed_symbol(self, rel: str, qname: str) -> bool:
        return bool(self.db.conn.execute(
            "SELECT 1 FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE f.path = ? AND s.qualified_name = ? LIMIT 1",
            (rel, qname),
        ).fetchone())

    def _anchor_gap(self, atype: str, key: str) -> dict | None:
        """Why a canonical anchor does not match the index, or None if it does."""
        rel, qname = mem.anchor_parts(atype, key)
        if atype == "symbol":
            if self._indexed_symbol(rel, qname):
                return None
            in_file = [
                mem.symbol_anchor(rel, r[0])
                for r in self.db.conn.execute(
                    "SELECT s.qualified_name FROM symbols s JOIN files f ON f.id = s.file_id "
                    "WHERE f.path = ? ORDER BY s.start_line LIMIT 20",
                    (rel,),
                )
            ]
            payload = {
                "anchor": f"{atype}:{key}",
                "error": f"no symbol {qname!r} indexed in {rel!r}",
            }
            if in_file:
                payload["candidates"] = in_file
            else:
                payload["error"] = f"{rel!r} has no indexed symbols"
            return payload
        if atype == "file":
            if self._file_known(rel):
                return None
            return {"anchor": f"{atype}:{key}", "error": f"{rel!r} is not a readable project file"}
        if atype == "module":
            if self.db.conn.execute(
                "SELECT 1 FROM files WHERE path LIKE ? ESCAPE '\\' LIMIT 1", (mem.like_prefix(rel),)
            ).fetchone():
                return None
            return {"anchor": f"{atype}:{key}", "error": f"no indexed file under {rel!r}/"}
        return None

    def _pending_hint(self, refresh: dict) -> dict:
        """A zero hit on a still-building index means 'unknown', not 'absent'."""
        if refresh.get("pending_files"):
            return {
                "hint": (
                    f"index incomplete ({refresh['pending_files']} files not parsed yet): "
                    "a symbol missing here is not a symbol absent -- finish the build with "
                    "reindex() before anchoring a note"
                )
            }
        if refresh.get("pending_edges"):
            return {"hint": "call graph still being assembled (pending_edges > 0)"}
        return {}

    def _note_pairs(self, rows: list[dict]) -> list[tuple[str, str]]:
        """Anchors for the *top-level* hits of a query, symbol + its own file.

        Deliberately not per-result: find_callers can return 30 symbols, and 30
        note lookups with 30 note blocks in the answer would trade FastGraph's
        whole low-context premise for a maybe-useful hint.
        """
        pairs: list[tuple[str, str]] = []
        for r in rows[:3]:
            path = mem.normalize_rel(r.get("path") or "")
            qname = r.get("qualified_name") or ""
            if path and qname:
                pairs.append(("symbol", mem.symbol_key(path, qname)))
            if path:
                pairs.append(("file", path))
        return pairs

    def _attach_notes(self, out: dict, rows: list[dict]) -> None:
        if not self._memory_on():
            return
        store = self._memory_if_present()
        if store is None:
            return
        notes = store.notes_for(self._note_pairs(rows), limit=NOTES_PER_QUERY_MAX)
        if notes:
            out["notes"] = [
                {**n, "body": (n["body"] or "")[:NOTE_BODY_BRIEF]} for n in notes
            ]

    # ------------------------------------------------------------- helpers

    def _touch_root(self, path: Path):
        """Mark a cached root as most-recently-used (dict order == LRU order)."""
        tb = self._roots.pop(path)
        self._roots[path] = tb
        return tb

    def _evict_roots(self):
        """Close and drop the least-recently-used cross-project indexes.

        Caller must hold ``_roots_lock``. The activated root is never evicted
        (the session is pinned to it), and a bounded cache is what keeps foreign
        SQLite handles — and therefore foreign .fastgraph/ directories — from
        being held open for the lifetime of the server.
        """
        while len(self._roots) > MAX_CACHED_ROOTS:
            victim = next((p for p in self._roots if p != self._active_root), None)
            if victim is None:
                return
            evicted = self._roots.pop(victim)
            try:
                evicted._close_memory()
                evicted.db.close()
            except Exception:
                pass

    def activate_project(self, root: str | None) -> dict:
        """Set the session-wide default project root.

        Works without any prior state, so desktop agents can point the server
        at the folder they are working on. Returns a description of what the
        new active root indexes.
        """
        if root is None:
            path = self.root.resolve()
        else:
            if not str(root).strip():
                # keep the empty-root rejection in sync with _for_root
                return {"ok": False, "error": "root must be a non-empty directory path", "active_root": str(self._active_root or self.root)}
            path = Path(root).resolve()
        if not path.is_dir():
            return {"ok": False, "error": f"root {path} is not an existing directory", "active_root": str(self._active_root) if self._active_root else str(self.root)}
        if path == self.root.resolve():
            self._active_root = None
        else:
            with self._roots_lock:
                if path in self._roots:
                    self._touch_root(path)
                else:
                    db = DB(path)
                    self._roots[path] = Toolbox(path, db, Indexer(path, db))
                self._evict_roots()
            self._active_root = path
        return {"ok": True, "active_root": str(self._active_root or self.root)}

    def _for_root(self, root: str | None):
        """Return the toolbox for ``root`` (default: active root, else this one)."""
        if root is None:
            if self._active_root is not None and self._active_root != self.root.resolve():
                with self._roots_lock:
                    if self._active_root in self._roots:
                        return self._touch_root(self._active_root)
            return self
        if not str(root).strip():
            # Path("") resolves to the process cwd, silently indexing a folder
            # the caller never meant (e.g. a desktop app's System32 cwd).
            raise ValueError("root must be a non-empty directory path")
        path = Path(root).resolve()
        if path == self.root.resolve():
            return self
        with self._roots_lock:
            if path in self._roots:
                return self._touch_root(path)
            if not path.is_dir():
                raise ValueError(f"root {path} is not an existing directory")
            db = DB(path)
            sub = Toolbox(path, db, Indexer(path, db))
            self._roots[path] = sub
            self._evict_roots()
            return sub

    def reindex(self, full: bool = False, root: str | None = None) -> dict:
        """Build the index all the way to the end in one call.

        Every other tool stops its refresh at `INDEX_TIME_BUDGET_S` (so a call
        cannot hang for minutes on a big repo) and answers from the partial index
        while reporting `pending_files`. This is the escape hatch for "I want the
        complete graph now": it loops over budget-sized passes until nothing is
        left. `full=True` drops the existing index first -- after editing
        `.fastgraphignore`, or when an answer looks inexplicably stale.
        """
        tb = self._for_root(root)
        stats = tb.indexer.force_index() if full else tb.indexer.build_to_completion()
        out = {
            "ok": True,
            "rebuilt": bool(full),
            "files": stats.total_files,
            "symbols": stats.total_symbols,
            "parsed": stats.parsed,
            "errors": stats.errors,
            "duration_ms": round(stats.duration_ms, 1),
            # 0 by construction: this call is the one that finishes the build
            "pending_files": stats.pending_files,
            "pending_edges": stats.pending_edges,
        }
        if stats.skipped:
            out["skipped"] = True
            out["hint"] = (
                "auto-detected root is the user home dir (or too large to "
                "scan); call activate_project(root=...) with the actual "
                "project folder"
            )
        if stats.large_files:
            out["large_files"] = stats.large_files
        return out

    def _ensure_fresh(self) -> dict:
        """Lazy incremental refresh: only changed files re-parsed."""
        stats = self.indexer.refresh()
        # remember which files this refresh re-parsed so changed_context can
        # report changes on non-git projects (see changed_context)
        self._last_changed = stats.changed
        self._last_large_files = list(stats.large_files)
        out = {
            "scanned": stats.scanned,
            "parsed": stats.parsed,
            "deleted": stats.deleted,
            "errors": stats.errors,
            "refresh_ms": round(stats.duration_ms, 1),
        }
        if stats.skipped:
            out["skipped"] = True
            out["hint"] = (
                "auto-detected root is the user home dir (or too large to "
                "scan); call activate_project(root=...) with the actual "
                "project folder"
            )
        if stats.pending_files and not stats.skipped:
            # a partial index makes "not found" meaningless: say so on every
            # answer rather than let a missing symbol read as absent code
            out["pending_files"] = stats.pending_files
            out["hint"] = (
                f"index incomplete: {stats.pending_files} files are not indexed "
                "yet (this call stopped at its time budget), and the call graph "
                "is only built once the index completes -- a missing symbol or "
                "caller here means 'not indexed yet', not 'absent'. Call again "
                "to continue the build, or reindex(full=true) to finish it now"
            )
        elif stats.pending_edges and not stats.skipped:
            out["pending_edges"] = stats.pending_edges
            out["hint"] = (
                f"every file is indexed, but the call graph is still being "
                f"assembled ({stats.pending_edges} call edges not looked at yet; "
                "this call stopped at its time budget) -- call_graph "
                "and impact_analysis are incomplete until it "
                "reaches 0. Call again, or reindex() to finish in one call"
            )
        return out

    def _brief(self, sym: dict) -> dict:
        """Compact symbol view: no source body, just location + signature."""
        out = {
            "symbol": sym.get("name"),
            "qualified_name": sym.get("qualified_name"),
            "kind": sym.get("kind"),
            "file": sym.get("path"),
            "lines": f"{sym.get('start_line')}-{sym.get('end_line')}",
            "signature": (sym.get("signature") or "")[:120],
        }
        np = name_path(sym.get("qualified_name"))
        if np and np != sym.get("name"):
            # slash name path for nested symbols (A.B.m -> A/B/m) so the
            # identifier can be reused verbatim in the next tool call
            out["name_path"] = np
        return out

    def _locate(self, symbol: str) -> list[dict]:
        rows = graph.find_symbols(self.db, symbol)
        return [self._brief(s) for s in rows]

    def _finish(self, out: dict, tb, refresh: dict | None) -> dict:
        """Attach the root, plus refresh stats when the refresh actually worked
        (re-parsed/deleted/errored/skipped) or whenever FASTGRAPH_DEBUG is set
        — keeps steady-state output compact (no per-call `ms`/no-op noise)."""
        out["root"] = str(tb.root)
        if refresh and (
            self._debug or refresh["parsed"] or refresh["deleted"] or refresh["errors"]
            or refresh.get("skipped") or refresh.get("pending_files")
            or refresh.get("pending_edges")
        ):
            out["refresh"] = refresh
        return out

    # --------------------------------------------------------------- tools

    def code_search(self, query: str, limit: int = 10, kind: str | None = None, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        hits = code_search(tb.db, query, limit=limit, kind=kind)
        return self._finish({"results": hits, "count": len(hits)}, tb, refresh)

    def symbol_info(self, symbol: str, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        syms = graph.find_symbols(tb.db, symbol)
        if not syms:
            return self._finish({"found": False, "symbol": symbol}, tb, refresh)
        out = []
        for s in syms[:3]:
            info = graph.symbol_by_id(tb.db, s["id"])
            if not info:
                continue
            out.append({
                "symbol": info["name"],
                "qualified_name": info["qualified_name"],
                "kind": info["kind"],
                "file": info["path"],
                "lines": f"{info['start_line']}-{info['end_line']}",
                "signature": (info["signature"] or "")[:120],
                "doc": (info["doc"] or "")[:200],
                "callees": [c for c in graph.callee_names_with_lines(tb.db, info["id"]) if c["rtype"] == "calls"][:20],
            })
        out_result = {"found": True, "symbol": symbol, "matches": out}
        tb._attach_notes(out_result, syms)
        return self._finish(out_result, tb, refresh)

    def find_callers(self, symbol: str, limit: int = 30, depth: int = 1, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        roots = graph.find_symbols(tb.db, symbol)
        callers = graph.find_callers(tb.db, symbol, limit=limit, depth=depth)
        # An empty list is NOT proof that nothing calls this symbol: resolution
        # is name-based and gives up when a name has several possible owners
        # (`svc.run()` where two modules define `Svc`). Report the unresolved
        # edges that still name it so the answer can be weighed.
        pending = sum(
            graph.unresolved_incoming(
                tb.db, r.get("name") or "", r.get("qualified_name") or ""
            )
            for r in roots[:3]
        )
        out = {
            "symbol": symbol,
            "found": bool(roots),
            "callers": [
                {**tb._brief(s), "via": s.get("via", "resolved")} for s in callers
            ],
            "count": len(callers),
        }
        tb._attach_notes(out, roots)
        if pending:
            out["unresolved_incoming"] = pending
            out["hint"] = (
                f"{pending} call edge(s) name this symbol but could not be "
                "resolved (the receiver's type is not statically known); an "
                "empty caller list is not proof that nothing calls it"
            )
        elif not callers and roots:
            # No call edge *and* nothing unresolved: still not evidence of dead
            # code. An enum / const / type is read, not called, so it never
            # enters the call graph -- report its importers instead of leaving
            # `callers: []` to be misread as "nobody uses this".
            users = graph.imported_by(
                tb.db, [r.get("path") or "" for r in roots], limit=20
            )
            if users:
                out["imported_by"] = users[:8]
                out["hint"] = (
                    f"{len(users)}{'+' if len(users) == 20 else ''} file(s) import the "
                    "module defining this symbol. It has no call edges because it is "
                    "read rather than called (enum/const/type), so the empty caller "
                    "list is not evidence that it is unused"
                )
        return self._finish(out, tb, refresh)

    def find_callees(self, symbol: str, limit: int = 50, depth: int = 1, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        roots = graph.find_symbols(tb.db, symbol)
        callees = graph.find_callees(tb.db, symbol, limit=limit, depth=depth)
        pending = sum(graph.unresolved_outgoing(tb.db, r["id"]) for r in roots[:3])
        rows = [tb._brief(s) for s in callees]
        _tag_callee_evidence(tb.db, rows, roots)
        out = {
            "symbol": symbol,
            "found": bool(roots),
            "callees": rows,
            "count": len(callees),
        }
        if pending:
            out["unresolved_outgoing"] = pending
            out["hint"] = (
                f"{pending} call edge(s) out of this symbol could not be "
                "resolved; the callee list is incomplete"
            )
        return self._finish(out, tb, refresh)

    def trace_path(self, from_symbol: str, to_symbol: str | None = None, depth: int = 20, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        if to_symbol:
            path = graph.path_between(tb.db, from_symbol, to_symbol, max_depth=depth)
            return self._finish({
                "from": from_symbol,
                "to": to_symbol,
                "path": [tb._brief(s) for s in path[0]] if path else None,
            }, tb, refresh)
        # no target: trace the symbol's transitive callers, levelled
        chain = graph.caller_trace(tb.db, from_symbol, max_depth=depth, limit=15)
        return self._finish({
            "from": from_symbol,
            "chain": chain,
        }, tb, refresh)

    def impact_analysis(self, symbol: str, max_depth: int = 2, limit: int = 40, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        result = graph.impact_analysis(tb.db, symbol, max_depth=max_depth, limit=limit)
        if tb._memory_on():
            tb._attach_notes(result, graph.find_symbols(tb.db, symbol))
        return self._finish(result, tb, refresh)

    def changed_context(self, limit: int = 50, base: str | None = None, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        base_dir = gitutil.git_root(tb.root)
        if base_dir is not None:
            # base given: diff that rev against the working tree (branch-level
            # footprint); otherwise the uncommitted `git status` view.
            changes = (
                gitutil.changed_files_vs(tb.root, base)
                if base
                else gitutil.changed_files(tb.root, base=base_dir)
            )
            source = "git"
        else:
            # Non-git project: git status is unavailable, so fall back to the
            # files this very refresh re-parsed, i.e. what changed on disk
            # since the previous tool call. Coarser, but keeps the tool useful.
            changes = {rel: "modified" for rel in tb._last_changed}
            source = "mtime" if changes else "none"
        by_status = gitutil.changed_symbols(
            tb.db, changes,
            gitutil.changed_ranges(base_dir, base) if base_dir is not None else None,
        )

        affected: list[dict] = []
        seen: set[int] = set()
        for status, syms in by_status.items():
            for s in syms:
                for c in graph.callers(tb.db, s["id"]):
                    if c in seen:
                        continue
                    seen.add(c)
                    info = graph.symbol_by_id(tb.db, c)
                    if info:
                        affected.append(tb._brief(info))

        # Cap every part of the output at `limit` — a repo with many untracked
        # files can otherwise dump thousands of symbols and blow the context.
        truncated_files = len(changes) > limit
        truncated_symbols = False
        capped_files = dict(list(changes.items())[:limit])
        capped_symbols: dict[str, list] = {}
        for k, v in by_status.items():
            if len(v) > limit:
                truncated_symbols = True
            capped_symbols[k] = [
                {"symbol": s["name"], "qualified_name": s["qualified_name"], "file": s["path"], "line": s["start_line"]}
                for s in v[:limit]
            ]
        out = {
            "changed_files": capped_files,
            "changed_symbols": capped_symbols,
            "affected_callers": affected[:limit],
            "truncated": truncated_files or truncated_symbols,
            "source": source,
        }
        if base and source == "git":
            out["base"] = base
        return self._finish(out, tb, refresh)

    # ---------------- 项目记忆层（默认开，FASTGRAPH_MEMORY=0 关） ----------------
    #
    # remember / recall pin notes to a code anchor and forget removes one;
    # checkpoint stores a graph snapshot and what_changed diffs two of them (as
    # `changes`, since the surface merge). Only remember and checkpoint ever create
    # `.fastgraph/memory.sqlite` -- forget goes through _memory_if_present(), so a
    # delete attempt on a project with no notes leaves no file behind.
    # Nothing here runs on its own: an implicit checkpoint would record a baseline
    # nobody chose and a completeness the caller never checked.

    def remember(
        self,
        anchor: str,
        body: str,
        kind: str = "context",
        source: str = "",
        root: str | None = None,
    ) -> dict:
        tb = self._for_root(root)
        if not tb._memory_on():
            return tb._finish(tb._memory_off(), tb, None)
        refresh = tb._ensure_fresh()
        text = (body or "").strip()
        if not text:
            return tb._finish({"ok": False, "error": "body is empty"}, tb, refresh)
        if len(text) > MAX_NOTE_BODY:
            return tb._finish(
                {"ok": False, "error": f"body is {len(text)} chars, over the {MAX_NOTE_BODY} cap",
                 "hint": "split it into per-symbol notes, or anchor a doc file and reference it in source="},
                tb, refresh,
            )
        k = (kind or "context").strip().lower()
        if k not in mem.NOTE_KINDS:
            return tb._finish(
                {"ok": False, "error": f"unknown kind {kind!r}", "kinds": list(mem.NOTE_KINDS)}, tb, refresh
            )
        resolved, problem = tb._resolve_anchor(anchor)
        if resolved is None:
            return tb._finish({"ok": False, **problem, **tb._pending_hint(refresh)}, tb, refresh)
        atype, akey = resolved
        dup = tb.memory.find_notes(atype, akey, k, limit=20)
        same = next((n for n in dup if (n["body"] or "").strip() == text), None)
        if same is not None:
            # re-anchoring the same decision is idempotent by intent; letting it
            # pile up rows would make recall return the same text four times
            return tb._finish(
                {"ok": True, "deduped": True, "id": same["id"], "anchor": f"{atype}:{akey}", "kind": k},
                tb, refresh,
            )
        nid = tb.memory.add_note(atype, akey, k, text, (source or "").strip())
        out = {"ok": True, "id": nid, "anchor": f"{atype}:{akey}", "kind": k,
               "stored_in": str(tb.memory.db.db_path)}
        if atype == "symbol":
            # The key names a (file, qualified_name) pair, not one declaration:
            # line numbers would move on every edit, so they cannot be part of it.
            # On real JS/TS one key can therefore cover many declarations (measured
            # on preact: `test/browser/fragments.test.jsx#Foo` matches 31 inline
            # components, and 659 such keys cover 2,425 rows). Legitimate, but it
            # has to be said at write time -- otherwise the caller believes the
            # note is pinned to one function.
            rel, qname = mem.anchor_parts(atype, akey)
            n = tb.db.conn.execute(
                "SELECT COUNT(*) FROM symbols s JOIN files f ON f.id = s.file_id "
                "WHERE f.path = ? AND s.qualified_name = ?",
                (rel, qname),
            ).fetchone()[0]
            if n > 1:
                out["anchor_matches"] = n
                out["hint"] = (
                    f"{n} declarations in {rel!r} share the name {qname!r}: this note is "
                    "attached to that name in that file, not to one of them"
                )
        return tb._finish(out, tb, refresh)

    def recall(
        self,
        anchor: str = "",
        kind: str | None = None,
        include_orphans: bool = False,
        limit: int = 50,
        root: str | None = None,
    ) -> dict:
        tb = self._for_root(root)
        if not tb._memory_on():
            return tb._finish(tb._memory_off(), tb, None)
        refresh = tb._ensure_fresh()
        store = tb._memory_if_present()
        if store is None:
            return tb._finish(
                {
                    "ok": True,
                    "notes": [],
                    "count": 0,
                    "scope": anchor or "all notes",
                    "hint": "no notes stored in this project yet -- remember(anchor=…, body=…) adds one",
                },
                tb,
                refresh,
            )
        # anchor is required in spirit: there is no "current symbol" server-side
        # state to fall back on, so an empty anchor means the whole store and is
        # reported as such rather than pretending to be context-sensitive.
        scope_all = not (anchor or "").strip()
        scope: tuple[str, str] | None = None
        pairs: list[tuple[str, str]] | None = None
        note: dict = {}
        orphan_path = False
        if not scope_all:
            resolved, problem = tb._resolve_anchor(anchor)
            if resolved is None:
                cands = problem.get("candidates") or []
                if cands:
                    # reading is safe to fan out over: query every candidate and
                    # say which ones matched, instead of refusing to answer
                    pairs = []
                    for c in cands:
                        p = mem.parse_anchor(c)
                        if p:
                            pairs.append(p)
                    note = {"ambiguous_anchor": True, "matched_anchors": cands}
                else:
                    # The anchor matches no code at all. Before saying "nothing
                    # found", look for notes whose anchor *text* ends with what
                    # was asked for: a note on a symbol that has since been
                    # renamed or deleted is unreachable by resolution, and
                    # reporting "no notes" there is exactly the loss this layer
                    # exists to prevent.
                    tail = (anchor or "").partition(":")[2] if (anchor or "").startswith("symbol:") else anchor
                    found: dict[int, dict] = {}
                    for row in store.notes_like(tail) + store.notes_like(anchor):
                        found.setdefault(row["id"], row)
                    if not found:
                        return tb._finish({"ok": False, "found": False, **problem}, tb, refresh)
                    rows = sorted(found.values(), key=lambda n: -n["id"])
                    orphan_path = True
                    note = {
                        "anchor_unresolved": True,
                        "hint": "no code matches this anchor any more; these notes were matched on their anchor text",
                    }
            else:
                scope = resolved
        if kind is not None and kind.strip().lower() not in mem.NOTE_KINDS:
            return tb._finish(
                {"ok": False, "error": f"unknown kind {kind!r}", "kinds": list(mem.NOTE_KINDS)}, tb, refresh
            )
        k = kind.strip().lower() if kind else None
        if orphan_path:
            rows = [n for n in rows if k is None or n["kind"] == k]
        elif scope is not None:
            rows = store.notes_under(scope[0], scope[1], kind=k, limit=max(limit, 1))
        elif pairs is not None:
            rows = store.notes_for(pairs, kind=k, limit=max(limit, 1) * max(len(pairs), 1))
        elif k is not None:
            rows = store.find_notes(kind=k, limit=limit)
        else:
            rows = store.find_notes(limit=limit)
        rows = rows[:limit]
        for n in rows:
            p = mem.parse_anchor(n["anchor"])
            n["anchor_resolved"] = p is None or tb._anchor_gap(p[0], p[1]) is None
        if not include_orphans and not orphan_path:
            rows = [n for n in rows if n["anchor_resolved"]]
        return tb._finish(
            {
                "ok": True,
                "notes": rows,
                "count": len(rows),
                "scope": "all notes" if scope_all else anchor,
                "truncated": len(rows) == limit,
                **note,
            },
            tb,
            refresh,
        )

    def forget(self, id: int, root: str | None = None) -> dict:
        tb = self._for_root(root)
        if not tb._memory_on():
            return tb._finish(tb._memory_off(), tb, None)
        refresh = tb._ensure_fresh()
        store = tb._memory_if_present()
        if store is None:
            return tb._finish(
                {
                    "ok": False,
                    "error": "no notes stored in this project",
                    "hint": "forget(id=…) removes a note; recall() lists them with their ids",
                },
                tb,
                refresh,
            )
        try:
            note_id = int(id)
        except (TypeError, ValueError):
            return tb._finish(
                {"ok": False, "error": f"id must be the number a recall() result carried, got {id!r}"},
                tb,
                refresh,
            )
        gone = store.delete_note(note_id)
        if gone is None:
            return tb._finish(
                {
                    "ok": False,
                    "error": f"no note with id {note_id}",
                    "hint": "ids come from recall(); already-removed notes have no id to forget",
                    "remaining": store.note_count(),
                },
                tb,
                refresh,
            )
        # the removed row is echoed rather than summarised: it is the only undo path,
        # and a caller who sees the body can tell immediately that the id pointed at
        # the wrong note
        out = {"ok": True, "removed": gone, "remaining": store.note_count()}
        if not out["remaining"]:
            out["hint"] = "that was the last note in this project; .fastgraph/memory.sqlite is now empty"
        else:
            out["hint"] = (
                "to move a note instead of losing it: remember(anchor=<new anchor>, "
                "body=<the body above>)"
            )
        return tb._finish(out, tb, refresh)

    def checkpoint(self, label: str, ref: str | None = None, root: str | None = None) -> dict:
        tb = self._for_root(root)
        if not tb._memory_on():
            return tb._finish(tb._memory_off(), tb, None)
        refresh = tb._ensure_fresh()
        name = (label or "").strip()
        if not name:
            return tb._finish({"ok": False, "error": "label is required (it is what changes(since=…) looks up)"}, tb, refresh)
        if tb._index_incomplete(refresh):
            return tb._finish(
                {
                    "ok": False,
                    "error": "index is still building, so a snapshot now would record build progress rather than code",
                    "pending_files": refresh.get("pending_files", 0),
                    "pending_edges": refresh.get("pending_edges", 0),
                    "hint": "call reindex() to finish the build in one call, then checkpoint again",
                },
                tb,
                refresh,
            )
        if not tb.db.count_files():
            # An empty index passes the completeness gate (nothing is pending
            # because nothing was scanned), and a baseline of "no symbols, no
            # edges" then reports the whole graph as newly added. Found by
            # probing a repo whose clone had not finished: 0 files, checkpoint ok.
            return tb._finish(
                {
                    "ok": False,
                    "error": "the index is empty, so this baseline would hold nothing at all",
                    "hint": (
                        "wrong root? activate_project(root=…) with the project folder, "
                        "or check .fastgraphignore -- a baseline is only useful once "
                        "files are indexed"
                    ),
                },
                tb,
                refresh,
            )
        try:
            symbols, edges, cycles = mem.collect_sets(tb.db)
        except mem.SnapshotTooLarge as e:
            return tb._finish({"ok": False, "error": str(e)}, tb, refresh)
        sha = (ref or "").strip() or gitutil.head_ref(tb.root)
        sid = tb.memory.put_snapshot(name, sha, True, symbols, edges, cycles)
        return tb._finish(
            {
                "ok": True,
                "id": sid,
                "label": name,
                "ref": sha,
                "symbols": len(set(symbols)),
                "edges": len(set(edges)),
                "cycles": len(cycles),
                "hint": f'changes(since="{name}") diffs the graph against this baseline',
            },
            tb,
            refresh,
        )

    def what_changed(self, since: str, to: str | None = None, limit: int = 50, root: str | None = None) -> dict:
        tb = self._for_root(root)
        if not tb._memory_on():
            return tb._finish(tb._memory_off(), tb, None)
        refresh = tb._ensure_fresh()
        store = tb._memory_if_present()
        if store is None:
            return tb._finish(
                {
                    "ok": False,
                    "error": f"no snapshot labelled {since!r}",
                    "snapshots": [],
                    "hint": "this project has no memory store yet -- checkpoint(label=…) records the first baseline",
                },
                tb,
                refresh,
            )
        base = store.snapshot_by_label((since or "").strip())
        if base is None:
            return tb._finish(
                {
                    "ok": False,
                    "error": f"no snapshot labelled {since!r}",
                    "snapshots": store.snapshot_list(limit=20),
                    "hint": "checkpoint(label=…) writes the baseline this tool reads",
                },
                tb,
                refresh,
            )
        if not base["complete"]:
            return tb._finish(
                {"ok": False, "error": f"snapshot {since!r} was taken from an incomplete index and cannot be a baseline"},
                tb,
                refresh,
            )
        if base["format"] != mem.SNAPSHOT_FORMAT:
            # diffing two line formats would report every row as changed, which
            # reads exactly like "the whole graph moved" -- refuse instead
            return tb._finish(
                {
                    "ok": False,
                    "error": (
                        f"snapshot {since!r} uses baseline format {base['format'] or 'pre-versioned'!r}, "
                        f"this build writes {mem.SNAPSHOT_FORMAT!r}; the diff would report every row changed"
                    ),
                    "hint": "checkpoint(label=…) a fresh baseline",
                },
                tb,
                refresh,
            )
        if to:
            other = store.snapshot_by_label(to.strip())
            if other is None:
                return tb._finish({"ok": False, "error": f"no snapshot labelled {to!r}"}, tb, refresh)
            if not other["complete"]:
                return tb._finish({"ok": False, "error": f"snapshot {to!r} is incomplete"}, tb, refresh)
            if other["format"] != mem.SNAPSHOT_FORMAT:
                return tb._finish(
                    {"ok": False, "error": f"snapshot {to!r} uses format {other['format'] or 'pre-versioned'!r}, "
                                            f"not {mem.SNAPSHOT_FORMAT!r}"},
                    tb,
                    refresh,
                )
            head_desc = {"label": other["label"], "id": other["id"]}
            cur_symbols, cur_edges, cur_cycles = other["symbols"], other["edges"], other["cycles"]
        else:
            if tb._index_incomplete(refresh):
                return tb._finish(
                    {
                        "ok": False,
                        "error": "cannot compare: the current index is still building, so any difference would be build progress",
                        "pending_files": refresh.get("pending_files", 0),
                        "pending_edges": refresh.get("pending_edges", 0),
                        "hint": "reindex() first",
                    },
                    tb,
                    refresh,
                )
            if not tb.db.count_files():
                # same trap as checkpoint: an empty current index would report
                # every symbol and edge in the baseline as removed
                return tb._finish(
                    {"ok": False, "error": "the current index is empty; a diff against it "
                                           "would read as 'everything was deleted'",
                     "hint": "activate_project(root=…) / reindex() first"},
                    tb,
                    refresh,
                )
            try:
                live_s, live_e, live_c = mem.collect_sets(tb.db)
            except mem.SnapshotTooLarge as e:
                return tb._finish({"ok": False, "error": str(e)}, tb, refresh)
            head_desc = {"label": "live"}
            cur_symbols, cur_edges, cur_cycles = live_s, live_e, live_c

        sym_added, sym_removed = _diff_lines(base["symbols"], cur_symbols, limit)
        edge_added, edge_removed = _diff_lines(base["edges"], cur_edges, limit)
        cyc_added, cyc_removed = _diff_lines(base["cycles"], cur_cycles, limit)

        def _edge_rows(rows: list[str]) -> list[dict]:
            # A resolved edge and a text edge are different strengths of proof, so
            # they stay in separate tiers: merging them made "this call
            # disappeared" out of what is really the resolver changing its mind
            # about a bare vs qualified copy of the same call site.
            out = []
            for ln in rows:
                parts = ln.split("\t")
                if len(parts) == 4:
                    rtype, src, dst, tier = parts
                    # escaped in the blob so the line stays one row; the caller
                    # should see the text as it appears in the source
                    out.append({"rtype": mem.unesc(rtype), "from": mem.unesc(src),
                                "to": mem.unesc(dst), "tier": tier})
            return out

        # Lines are stored escaped (call text really does contain tabs and
        # newlines), compared escaped, and unescaped only on the way out.
        out = {
            "ok": True,
            "since": {"label": base["label"], "id": base["id"], "ref": base["ref"], "created_at": base["created_at"]},
            "to": head_desc,
            "symbols": {"added": [mem.unesc(x) for x in sym_added[0]],
                        "removed": [mem.unesc(x) for x in sym_removed[0]],
                        "truncated": sym_added[1] or sym_removed[1]},
            "call_edges": {
                "added": _edge_rows(edge_added[0]),
                "removed": _edge_rows(edge_removed[0]),
                "truncated": edge_added[1] or edge_removed[1],
            },
            "module_cycles": {
                "appeared": [[mem.unesc(p) for p in c.split("\x1f")] for c in cyc_added[0]],
                "disappeared": [[mem.unesc(p) for p in c.split("\x1f")] for c in cyc_removed[0]],
            },
            "caveat": (
                "edges are (caller qualified_name, target text, rtype) triples from the "
                "name-based resolver: a difference here is the resolver's view changing, "
                "not proof that a call appeared or broke -- confirm with call_graph(direction=\"in\")"
            ),
        }
        if to:
            # The current worktree says nothing useful about a v1->v2 comparison:
            # which notes are orphaned, and what git changed, are properties of
            # *now*. Reporting them anyway would mix two different time bases
            # into one answer, so they are left out and the reason is stated.
            out["note"] = (
                "snapshot-to-snapshot comparison: stale_notes and the git view describe "
                "the working tree, not the 'to' snapshot, so they are omitted here"
            )
        else:
            stale = tb._stale_notes(limit, ref=base["ref"])
            if stale:
                out["stale_notes"] = stale
            if base["ref"]:
                changed = gitutil.changed_files_vs(tb.root, base["ref"])
                if changed:
                    out["git"] = {"ref": base["ref"], "changed_files": dict(list(changed.items())[:limit]),
                                  "truncated": len(changed) > limit}
        return self._finish(out, tb, refresh)

    def _stale_notes(self, limit: int = 20, ref: str | None = None) -> list[dict]:
        """Notes whose anchor no longer matches the index, with the rename if one explains it.

        Without this, a decision attached to `AuthService.login` silently stops
        coming back once the method is renamed -- which reproduces inside the
        memory layer the very loss (design knowledge evaporating) the layer was
        built to prevent.

        `ref` is the baseline snapshot's commit: rename detection has to compare
        *against it*, not against HEAD. Cross-session renames are usually already
        committed, and `git diff HEAD` of a clean worktree is empty -- which lost
        the `moved_to` hint on the first real-repo run (preact, `oxlint.json` ->
        `.oxlintrc.json`).

        Existence is checked in three batched queries (symbols, files, dirs)
        rather than one per note: a project with a few hundred notes used to cost
        a few hundred round trips on every `what_changed`.
        """
        rows = self.memory.find_notes(limit=500)
        if not rows:
            return []
        parsed = [(n, mem.parse_anchor(n["anchor"])) for n in rows]

        want_paths: set[str] = set()
        want_pairs: set[tuple[str, str]] = set()
        want_dirs: set[str] = set()
        for _n, p in parsed:
            if p is None or p[0] == "project":
                continue
            rel, qname = mem.anchor_parts(p[0], p[1])
            if p[0] == "symbol":
                want_pairs.add((rel, qname))
                want_paths.add(rel)
            elif p[0] == "file":
                want_paths.add(rel)
            else:
                want_dirs.add(rel)

        live_files: set[str] = set()
        live_pairs: set[tuple[str, str]] = set()
        if want_paths:
            marks = ",".join("?" * len(want_paths))
            args = tuple(want_paths)
            live_files = {r[0] for r in self.db.conn.execute(
                f"SELECT path FROM files WHERE path IN ({marks})", args)}
            live_pairs = {
                (r[0], r[1]) for r in self.db.conn.execute(
                    "SELECT f.path, s.qualified_name FROM symbols s "
                    f"JOIN files f ON f.id = s.file_id WHERE f.path IN ({marks})", args)
                if (r[0], r[1]) in want_pairs
            }
            # a path the index does not carry is not necessarily gone: configs and
            # docs take notes the same way read_file reads them, so the leftovers
            # get the disk check rather than an orphan verdict
            for rel in want_paths - live_files:
                if self._file_known(rel):
                    live_files.add(rel)
        # module anchors are prefixes, so they cannot share one IN list; the count
        # is the number of distinct directories a note is pinned to, not the notes
        live_dirs = {
            d for d in want_dirs
            if self.db.conn.execute(
                "SELECT 1 FROM files WHERE path LIKE ? ESCAPE '\\' LIMIT 1", (mem.like_prefix(d),)
            ).fetchone()
        }

        moved = gitutil.renames(self.root, base=ref or None)
        stale = []
        for n, p in parsed:
            if p is None or p[0] == "project":
                continue
            rel, qname = mem.anchor_parts(p[0], p[1])
            alive = (
                (rel, qname) in live_pairs if p[0] == "symbol"
                else rel in live_files if p[0] == "file"
                else rel in live_dirs
            )
            if alive:
                continue
            item = {"id": n["id"], "anchor": n["anchor"], "kind": n["kind"], "body": (n["body"] or "")[:NOTE_BODY_BRIEF]}
            if p[0] in ("file", "symbol") and rel in moved:
                item["moved_to"] = moved[rel]
            stale.append(item)
            if len(stale) >= limit:
                break
        return stale

    def project_overview(self, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        overview = graph.project_overview(tb.db)
        # Make the index's blind spots visible: a file over MAX_FILE_SIZE is
        # skipped without a parse error, and a walk that hit its entry cap
        # leaves a partial index. Both otherwise read as "nothing here".
        large = list(getattr(tb, "_last_large_files", ()))
        if large:
            overview["skipped_large_files"] = {"count": len(large), "sample": large[:5]}
        if refresh.get("skipped"):
            overview["scan_truncated"] = True
        return self._finish(overview, tb, refresh)

    def unused_symbols(self, limit: int = 50, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        hits = graph.unused_symbols(tb.db, limit=limit)
        return self._finish({"unused": hits, "count": len(hits), "hint": "candidate list; confirm with call_graph(direction=\"in\") before deleting"}, tb, refresh)

    def hot_symbols(self, limit: int = 20, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        hits = graph.hot_symbols(tb.db, limit=limit)
        return self._finish({"hot": hits, "count": len(hits)}, tb, refresh)

    def file_metrics(self, limit: int = 20, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        hits = graph.file_metrics(tb.db, limit=limit)
        return self._finish({"files": hits, "count": len(hits)}, tb, refresh)

    def module_cycles(self, max_cycles: int = 10, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        hits = graph.module_cycles(tb.db, max_cycles=max_cycles)
        return self._finish({"cycles": hits, "count": len(hits)}, tb, refresh)

    # ---------------- 文件级工具 ----------------

    def file_symbols(self, path: str, limit: int = 200, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        syms, truncated = graph.file_symbols(tb.db, path, limit=limit)
        return self._finish(
            {"file": path, "symbols": syms, "count": len(syms), "truncated": truncated},
            tb,
            refresh,
        )

    def file_deps(self, path: str, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        deps = graph.module_dependencies(tb.db, path)
        # split resolved (internal) from unresolved (stdlib/3rd-party) imports;
        # ambiguous/not-found results have no `imports` key
        if "imports" in deps:
            deps["external_imports"] = [imp for imp in deps["imports"] if not imp["resolves_to"]]
            deps["imports"] = [imp for imp in deps["imports"] if imp["resolves_to"]]
        deps["file"] = path
        return self._finish(deps, tb, refresh)

    def rename_impact(self, symbol: str, limit: int = 100, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        impact = graph.rename_impact(tb.db, symbol, limit=limit)
        return self._finish(impact, tb, refresh)

    def type_hierarchy(self, symbol: str, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        hier = graph.type_hierarchy(tb.db, symbol)
        return self._finish(hier, tb, refresh)

    # ---------------- source reading ----------------
    #
    # The only surface that returns file bodies; everything else returns
    # locations/relationships, not text. Reads are restricted to *indexed*
    # source files, which keeps the path inside the project root and keeps
    # ignored/secret files unreadable; MAX_READ_CHARS caps the response and the
    # `truncated` flag reports when the cap was hit.

    def _read_lines(self, tb, rel_path: str, start_line: int, end_line: int) -> str:
        try:
            text = (tb.root / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        lines = text.replace("\r\n", "\n").split("\n")
        return "\n".join(lines[max(0, start_line - 1):end_line])

    def _resolve_read_target(self, tb, path: str) -> tuple[str | None, bool, str]:
        """Resolve a ``read_file`` path to ``(rel_path, indexed, reason)``.

        Two layers, in order:

        1. the index lookup (exact / path-suffix / basename), which is what makes
           a bare ``server.py`` work when the index holds exactly one match;
        2. a direct filesystem resolution for files the index does not carry
           (docs, configs, lockfiles), because those are still part of the
           project a reader needs to see.

        Layer 2 deliberately mirrors the index's visibility rules -- inside the
        project root, no dot/excluded segments, nothing matched by
        ``.fastgraphignore`` -- so reading can never reach further than indexing
        did: paths outside the project and ignored secrets stay unreadable.
        """
        indexed = graph.resolve_file(tb.db, path)
        if indexed is not None:
            return indexed, True, ""
        raw = Path(path)
        root = tb.root.resolve()
        candidate = raw if raw.is_absolute() else root / path
        try:
            resolved = candidate.resolve()
        except OSError:
            return None, False, f"cannot resolve path: {path}"
        if not resolved.is_relative_to(root):
            return None, False, "path is outside the project root"
        parts = resolved.relative_to(root).parts
        for seg in parts:
            if seg in tb.indexer.excludes or seg.startswith("."):
                return None, False, f"'{seg}' is a dot/excluded path segment; those stay unreadable"
        rel = "/".join(parts)
        if tb.indexer.ignore_matcher().matches(rel, resolved.name):
            return None, False, "excluded by .fastgraphignore"
        if not resolved.is_file():
            return None, False, "not a file"
        try:
            size = resolved.stat().st_size
        except OSError as e:
            return None, False, f"cannot stat file: {e}"
        if size > MAX_FILE_SIZE:
            return None, False, f"file is {size} bytes (limit {MAX_FILE_SIZE}); open it in your editor"
        return rel, False, ""

    def read_file(
        self,
        path: str,
        start_line: int = 1,
        end_line: int | None = None,
        root: str | None = None,
    ) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        rel, indexed, reason = self._resolve_read_target(tb, path)
        if rel is None:
            return self._finish({"found": False, "file": path, "hint": reason}, tb, refresh)
        try:
            data = (tb.root / rel).read_bytes()
        except OSError as e:
            return self._finish({"found": False, "file": rel, "error": str(e)}, tb, refresh)
        if b"\0" in data[:4096]:
            return self._finish(
                {"found": False, "file": rel, "hint": "binary file: only text files can be read"},
                tb,
                refresh,
            )
        text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
        lines = text.split("\n")
        total = len(lines)
        start = max(1, start_line)
        if end_line is None:
            end = min(total, start + MAX_READ_LINES - 1)
        else:
            end = max(start - 1, min(total, end_line))
        content = "\n".join(lines[start - 1:end])
        # `truncated` means "there is more file than this response": either the
        # default window stopped short, or the character cap was hit
        truncated = len(content) > MAX_READ_CHARS or (end_line is None and end < total)
        if len(content) > MAX_READ_CHARS:
            content = content[:MAX_READ_CHARS]
        return self._finish(
            {
                "found": True,
                "file": rel,
                "indexed": indexed,
                "start_line": start,
                "end_line": end,
                "total_lines": total,
                "content": content,
                "truncated": truncated,
            },
            tb,
            refresh,
        )

    def symbol_body(self, symbol: str, max_lines: int = 200, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        syms = graph.find_symbols(tb.db, symbol)
        if not syms:
            return self._finish({"found": False, "symbol": symbol}, tb, refresh)
        s = syms[0]
        info = graph.symbol_by_id(tb.db, s["id"])
        if not info:
            return self._finish({"found": False, "symbol": symbol}, tb, refresh)
        start = info["start_line"]
        end = min(info["end_line"], start + max_lines - 1)
        content = self._read_lines(tb, info["path"], start, end)
        out = {
            "found": True,
            "symbol": info["name"],
            "qualified_name": info["qualified_name"],
            "kind": info["kind"],
            "file": info["path"],
            "lines": f"{start}-{end}",
            "truncated": end < info["end_line"],
            "content": content[:MAX_READ_CHARS],
        }
        if len(syms) > 1:
            out["other_matches"] = [tb._brief(x) for x in syms[1:6]]
        return self._finish(out, tb, refresh)

    # ---------------- merged surface ----------------
    #
    # One tool per question, not one per phrasing of it. These three stand in for
    # seven that differed only by a direction, a target kind, or a time base --
    # distinctions the caller has to settle *before* it knows what it is looking
    # for, and which cost advertised schema on every request. The underlying
    # methods stay exactly as they are (internal API, and what the tests call);
    # these wrappers only route.

    def call_graph(
        self,
        symbol: str,
        direction: str = "both",
        depth: int = 1,
        limit: int | None = None,
        root: str | None = None,
    ) -> dict:
        tb = self._for_root(root)
        way = (direction or "both").strip().lower()
        if way not in ("in", "out", "both"):
            return tb._finish(
                {
                    "found": False,
                    "error": f"unknown direction {direction!r}",
                    "hint": "use in (who calls it), out (what it calls) or both",
                },
                tb,
                None,
            )
        kwargs: dict = {"depth": depth, "root": root}
        if limit:
            kwargs["limit"] = limit
        if way == "in":
            return self.find_callers(symbol, **kwargs)
        if way == "out":
            return self.find_callees(symbol, **kwargs)
        # nested on purpose: each side carries its own honesty metadata
        # (`via`/`evidence`, unresolved counts, the enum-read-installed hint), and
        # flattening them would put two different `hint` values in one dict
        return tb._finish(
            {"symbol": symbol, "in": self.find_callers(symbol, **kwargs),
             "out": self.find_callees(symbol, **kwargs)},
            tb,
            None,
        )

    def read_code(
        self,
        target: str,
        start_line: int | None = None,
        end_line: int | None = None,
        structure: bool = False,
        max_lines: int = 200,
        limit: int = 200,
        root: str | None = None,
    ) -> dict:
        tb = self._for_root(root)
        t = (target or "").strip()
        rel, _indexed, reason = tb._resolve_read_target(tb, t)
        if rel is not None:
            if structure:
                out = tb.file_symbols(rel, limit=limit, root=root)
                out["mode"] = "structure"
                return out
            out = tb.read_file(rel, start_line or 1, end_line, root=root)
            out["mode"] = "lines"
            return out
        out = tb.symbol_body(t, max_lines=max_lines, root=root)
        out["mode"] = "symbol_body"
        if not out.get("found") and reason:
            out["hint"] = reason
        return out

    def changes(
        self,
        since: str | None = None,
        to: str | None = None,
        base: str | None = None,
        limit: int = 50,
        root: str | None = None,
    ) -> dict:
        """Two time bases, one question. `since=<checkpoint label>` diffs the call
        graph against a saved baseline; anything else is the git view (`base="main"`,
        or nothing for the working tree)."""
        if (since or "").strip():
            return self.what_changed(since, to=to, limit=limit, root=root)
        return self.changed_context(limit=limit, base=base, root=root)

    # ---------------- status ----------------

    def close(self) -> None:
        """Close and drop the per-root databases created for cross-project queries.

        The default root's DB is owned by the server and stays open. Closing the
        cached ones releases their SQLite file handles (call this at teardown,
        or before deleting a project directory on Windows, where an open handle
        blocks rmtree).
        """
        self._close_memory()
        with self._roots_lock:
            for tb in self._roots.values():
                tb._close_memory()
                try:
                    tb.db.close()
                except Exception:
                    pass
            self._roots.clear()
            self._active_root = None

    def _close_memory(self) -> None:
        if self._memory is not None:
            try:
                self._memory.close()
            except Exception:
                pass
            self._memory = None

    def index_summary(self, root: str | None = None) -> dict:
        """Cheap index-level status snapshot.

        Kept as an internal helper (the shared ``get_status`` tool it used to
        back is no longer advertised, since ``project_overview`` reports the same
        counts).
        """
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        languages = {
            r[0]: r[1]
            for r in tb.db.conn.execute(
                "SELECT language, COUNT(*) FROM files GROUP BY language ORDER BY 2 DESC"
            )
        }
        return self._finish(
            {
                "files": tb.db.count_files(),
                "symbols": tb.db.count_symbols(),
                "languages": languages,
                "index_version": tb.db.get_meta("index_version"),
                "parse_errors": len(tb.db.parse_errors(limit=200)),
            },
            tb,
            refresh,
        )