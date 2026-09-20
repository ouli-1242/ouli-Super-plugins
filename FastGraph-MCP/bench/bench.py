"""Reproducible benchmark for FastGraph's headline numbers.

Measures on a target repo (any project directory):
  1. cold first index      (delete .fastgraph, run one tool call)
  2. no-op refresh         (query again, nothing changed)
  3. incremental refresh   (touch one file's content, query again)
  4. typical query latency (code_search / symbol_info / find_callers / file_deps)

Usage:
    python bench/bench.py /path/to/project [--keep]

`--keep` preserves the built index (default: the pre-existing .fastgraph state
is restored — the bench never leaves its own index behind unless asked).
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import sys
import time
from pathlib import Path

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph import graph
from fastgraph.search import code_search


def _timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000.0, out


def _query_suite(db: DB, probe_symbol: str | None) -> dict[str, float]:
    """Latency of one representative call of each query family."""
    res: dict[str, float] = {}
    res["code_search"] = _timed(code_search, db, "config", limit=10)[0]
    res["project_overview"] = _timed(graph.project_overview, db)[0]
    target = probe_symbol or _first_function(db)
    if target:
        res["symbol_info"] = _timed(graph.find_symbols, db, target)[0]
        res["find_callers"] = _timed(graph.find_callers, db, target, limit=30)[0]
        res["impact_analysis"] = _timed(graph.impact_analysis, db, target)[0]
    paths = [r[0] for r in db.conn.execute("SELECT path FROM files LIMIT 1")]
    if paths:
        res["file_deps"] = _timed(graph.module_dependencies, db, paths[0])[0]
    res["module_cycles"] = _timed(graph.module_cycles, db)[0]
    return res


def _first_function(db: DB) -> str | None:
    row = db.conn.execute(
        "SELECT name FROM symbols WHERE kind='function' ORDER BY id LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FastGraph benchmark")
    ap.add_argument("root", type=Path, help="project directory to benchmark")
    ap.add_argument("--keep", action="store_true", help="leave the built index in place")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1

    index_dir = root / ".fastgraph"
    backup: Path | None = None
    if index_dir.exists():
        backup = root / ".fastgraph.bench-backup"
        shutil.move(str(index_dir), str(backup))

    try:
        db = DB(root)
        indexer = Indexer(root, db)

        cold_ms, stats = _timed(indexer.refresh)
        print(f"files={stats.total_files}  symbols={stats.total_symbols}")
        print(f"cold first index : {cold_ms:8.1f} ms")

        noop_ms, _ = _timed(indexer.refresh)
        print(f"no-op refresh    : {noop_ms:8.1f} ms")

        # touch one content change: append a harmless line to a random indexed file
        touched = None
        for (p,) in db.conn.execute("SELECT path FROM files LIMIT 50"):
            f = root / p
            if f.is_file():
                touched = f
                break
        if touched is not None:
            orig = touched.read_bytes()
            touched.write_bytes(orig + b"\n# bench touch\n")
            try:
                inc_ms, _ = _timed(indexer.refresh)
                print(f"incremental (1f) : {inc_ms:8.1f} ms")
            finally:
                touched.write_bytes(orig)

        # run the query suite several times, report median
        runs: list[dict[str, float]] = []
        for _ in range(5):
            runs.append(_query_suite(db, None))
        print("\nquery latency (median of 5):")
        keys = sorted({k for r in runs for k in r})
        for k in keys:
            vals = [r[k] for r in runs if k in r]
            print(f"  {k:<18} {statistics.median(vals):8.1f} ms")

        db.close()
        if not args.keep:
            shutil.rmtree(index_dir, ignore_errors=True)
        return 0
    finally:
        if backup is not None and not args.keep:
            shutil.rmtree(index_dir, ignore_errors=True)
            shutil.move(str(backup), str(index_dir))


if __name__ == "__main__":
    raise SystemExit(main())
