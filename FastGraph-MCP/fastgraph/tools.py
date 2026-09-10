"""MCP tool implementations (the 13-tool surface)."""

from __future__ import annotations

import os
from pathlib import Path

from fastgraph.db import DB
from fastgraph import graph, gitutil
from fastgraph.index import Indexer
from fastgraph.search import code_search


def _debug_enabled() -> bool:
    """FASTGRAPH_DEBUG=1 restores per-call index refresh stats in responses."""
    return os.environ.get("FASTGRAPH_DEBUG", "").lower() not in ("", "0", "false", "no")


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
        self._debug = _debug_enabled()

    # ------------------------------------------------------------- helpers

    def activate_project(self, root: str | None) -> dict:
        """Set the session-wide default project root (Serena-style activation).

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
            if path not in self._roots:
                db = DB(path)
                self._roots[path] = Toolbox(path, db, Indexer(path, db))
            self._active_root = path
        return {"ok": True, "active_root": str(self._active_root or self.root)}

    def _for_root(self, root: str | None):
        """Return the toolbox for ``root`` (default: active root, else this one)."""
        if root is None:
            if self._active_root is not None and self._active_root != self.root.resolve():
                return self._roots[self._active_root]
            return self
        if not str(root).strip():
            # Path("") resolves to the process cwd, silently indexing a folder
            # the caller never meant (e.g. a desktop app's System32 cwd).
            raise ValueError("root must be a non-empty directory path")
        path = Path(root).resolve()
        if path == self.root.resolve():
            return self
        if path in self._roots:
            return self._roots[path]
        if not path.is_dir():
            raise ValueError(f"root {path} is not an existing directory")
        db = DB(path)
        sub = Toolbox(path, db, Indexer(path, db))
        self._roots[path] = sub
        return sub

    def _ensure_fresh(self) -> dict:
        """Lazy incremental refresh: only changed files re-parsed."""
        stats = self.indexer.refresh()
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
        return {
            "symbol": sym.get("name"),
            "qualified_name": sym.get("qualified_name"),
            "kind": sym.get("kind"),
            "file": sym.get("path"),
            "lines": f"{sym.get('start_line')}-{sym.get('end_line')}",
            "signature": (sym.get("signature") or "")[:120],
        }

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
        base = len(graph.find_symbols(tb.db, symbol))
        callers = graph.find_callers(tb.db, symbol, limit=limit, depth=depth)
        return self._finish({
            "symbol": symbol,
            "found": base > 0,
            "callers": [tb._brief(s) for s in callers],
            "count": len(callers),
        }, tb, refresh)

    def find_callees(self, symbol: str, limit: int = 50, depth: int = 1, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        base = len(graph.find_symbols(tb.db, symbol))
        callees = graph.find_callees(tb.db, symbol, limit=limit, depth=depth)
        return self._finish({
            "symbol": symbol,
            "found": base > 0,
            "callees": [tb._brief(s) for s in callees],
            "count": len(callees),
        }, tb, refresh)

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
        # no target: show the symbol's call chain upward
        callers = graph.find_callers(tb.db, from_symbol, limit=15, depth=depth)
        return self._finish({
            "from": from_symbol,
            "chain": [tb._brief(s) for s in callers],
        }, tb, refresh)

    def impact_analysis(self, symbol: str, max_depth: int = 2, limit: int = 40, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        result = graph.impact_analysis(tb.db, symbol, max_depth=max_depth, limit=limit)
        return self._finish(result, tb, refresh)

    def changed_context(self, limit: int = 50, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        changes = gitutil.changed_files(tb.root)
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
        }, tb, refresh)

    def project_overview(self, root: str | None = None) -> dict:
        tb = self._for_root(root)
        refresh = tb._ensure_fresh()
        overview = graph.project_overview(tb.db)
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
        syms = graph.file_symbols(tb.db, path, limit=limit)
        return self._finish({"file": path, "symbols": syms, "count": len(syms)}, tb, refresh)

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