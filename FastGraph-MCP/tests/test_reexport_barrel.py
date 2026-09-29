"""Barrel files (`export * from './x'`) are dependency edges.

Re-exports were not indexed as imports at all, so a pure barrel had zero
dependencies in both directions: file_deps answered "found, nothing", and every
lookup routed through it (import_dependents, layering, module_cycles) treated
the re-exported module as unused. Measured on zustand's src/index.ts and vue
core's packages/shared/src/index.ts.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

WORK = Path(__file__).resolve().parent / "work_reexport"

VANILLA = 'export const VERSION = "1.0"\nexport function createStore(init) { return init; }\n'
REACT = "export function create(init) { return createStore(init); }\n"
INDEX = "export * from './vanilla.ts'\nexport { create } from './react.ts'\n"
CONSUMER = "import { createStore } from './index.ts'\nexport const s = createStore(() => 1)\n"


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _tool() -> Toolbox:
    _rmtree(WORK)
    (WORK / "src").mkdir(parents=True, exist_ok=True)
    for rel, text in {
        "src/vanilla.ts": VANILLA,
        "src/react.ts": REACT,
        "src/index.ts": INDEX,
        "src/consumer.ts": CONSUMER,
    }.items():
        (WORK / rel).write_text(text, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    return Toolbox(WORK, db, Indexer(WORK, db))


def _targets(deps: dict, key: str) -> set[str]:
    out: set[str] = set()
    for row in deps.get(key, []):
        if isinstance(row, dict):
            out.update(row.get("resolves_to") or [])
            if row.get("file"):
                out.add(row["file"])
    return out


def test_barrel_outbound_edges():
    tb = _tool()
    deps = tb.file_deps("src/index.ts")
    assert deps["found"] is True
    assert _targets(deps, "imports") >= {"src/vanilla.ts", "src/react.ts"}
    tb.close()


def test_barrel_inbound_edges():
    tb = _tool()
    assert "src/index.ts" in _targets(tb.file_deps("src/vanilla.ts"), "importers")
    tb.close()


def test_read_only_symbol_reports_importers_not_silence():
    """A const is read, never called: `callers: []` must not read as "unused"."""
    tb = _tool()
    res = tb.find_callers("VERSION", limit=5)
    assert res["count"] == 0
    assert "src/index.ts" in res["imported_by"]
    assert "unused" in res["hint"]
    tb.close()
