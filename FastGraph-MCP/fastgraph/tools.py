"""MCP tool implementations (the locate/analyse surface)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fastgraph.config import MAX_FILE_SIZE
from fastgraph.db import DB
from fastgraph import graph, gitutil
from fastgraph.graph import name_path
from fastgraph.index import Indexer
from fastgraph.search import code_search


def _debug_enabled() -> bool:
    """FASTGRAPH_DEBUG=1 restores per-call index refresh stats in responses."""
    return os.environ.get("FASTGRAPH_DEBUG", "").lower() not in ("", "0", "false", "no")


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
        if refresh and (self._debug or refresh["parsed"] or refresh["deleted"] or refresh["errors"] or refresh.get("skipped")):
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
        return self._finish({"found": True, "symbol": symbol, "matches": out}, tb, refresh)

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
        if pending:
            out["unresolved_incoming"] = pending
            out["hint"] = (
                f"{pending} call edge(s) name this symbol but could not be "
                "resolved (the receiver's type is not statically known); an "
                "empty caller list is not proof that nothing calls it"
            )
        return self._finish(out, tb, refresh)

    def find_callees(self, symbol: str, limit: int = 50, depth: int = 1, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        roots = graph.find_symbols(tb.db, symbol)
        callees = graph.find_callees(tb.db, symbol, limit=limit, depth=depth)
        pending = sum(graph.unresolved_outgoing(tb.db, r["id"]) for r in roots[:3])
        out = {
            "symbol": symbol,
            "found": bool(roots),
            "callees": [tb._brief(s) for s in callees],
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
        return self._finish(result, tb, refresh)

    def changed_context(self, limit: int = 50, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        base = gitutil.git_root(tb.root)
        if base is not None:
            changes = gitutil.changed_files(tb.root, base=base)
            source = "git"
        else:
            # Non-git project: git status is unavailable, so fall back to the
            # files this very refresh re-parsed, i.e. what changed on disk
            # since the previous tool call. Coarser, but keeps the tool useful.
            changes = {rel: "modified" for rel in tb._last_changed}
            source = "mtime" if changes else "none"
        by_status = gitutil.changed_symbols(tb.db, changes)

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
        return self._finish({
            "changed_files": capped_files,
            "changed_symbols": capped_symbols,
            "affected_callers": affected[:limit],
            "truncated": truncated_files or truncated_symbols,
            "source": source,
        }, tb, refresh)

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
        return self._finish({"unused": hits, "count": len(hits), "hint": "candidate list; confirm with find_callers before deleting"}, tb, refresh)

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
        lines = text.split("\n")
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
        text = data.decode("utf-8", errors="replace")
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

    # ---------------- status ----------------

    def close(self) -> None:
        """Close and drop the per-root databases created for cross-project queries.

        The default root's DB is owned by the server and stays open. Closing the
        cached ones releases their SQLite file handles (call this at teardown,
        or before deleting a project directory on Windows, where an open handle
        blocks rmtree).
        """
        with self._roots_lock:
            for tb in self._roots.values():
                try:
                    tb.db.close()
                except Exception:
                    pass
            self._roots.clear()
            self._active_root = None

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