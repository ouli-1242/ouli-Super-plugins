"""Inner local variables fold their calls into the enclosing method."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph import graph
from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_inner"
SRC = """\
export function inner() { return 1; }
export function outer() {
  const res = inner();
  return res;
}
"""


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def test_inner_variable_calls_attribute_to_method():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "svc.js").write_text(SRC, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    callers = graph.find_callers(db, "inner", limit=10)
    quals = {c["qualified_name"] for c in callers}
    assert "outer" in quals
    assert not any(q.endswith(".res") for q in quals)
    # the noisy inner-variable symbol no longer exists
    syms = db.conn.execute(
        "SELECT qualified_name FROM symbols WHERE qualified_name LIKE '%outer%'"
    ).fetchall()
    assert all("res" not in r[0] for r in syms)
    db.close()
    _rmtree(WORK)