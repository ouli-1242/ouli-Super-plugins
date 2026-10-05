"""A time-budgeted, multi-pass build must end with exactly the index one pass makes.

The budget exists because a first call on a big repo otherwise blocks for minutes
(4,791 Python files = 131s) and the client kills it. Truncation is only safe if
splitting the build changes nothing about the result, so this compares a build
forced through many tiny passes against the same tree built in one go: same files,
same symbols, same resolved edges.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.config import IGNORE_FILENAME
from fastgraph.db import DB
from fastgraph import index as index_mod
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

HERE = Path(__file__).resolve().parent
A = HERE / "work_budget_partial"
B = HERE / "work_budget_whole"

MODULES = 10
# plus src/p1/lib.py, src/p2/lib.py, src/user.py
TOTAL_FILES = MODULES + 3


def _write(root: Path):
    shutil.rmtree(root, ignore_errors=True)
    (root / "src").mkdir(parents=True)
    for i in range(MODULES):
        dep = (i + 1) % MODULES
        (root / "src" / f"mod{i}.py").write_text(
            f'"""Module {i}."""\nfrom src.mod{dep} import helper_{dep}\n\n\n'
            f"class Thing{i}:\n    def run(self):\n        return helper_{dep}()\n\n\n"
            f"def helper_{i}():\n    return Thing{i}().run()\n"
            f"\n# note: helper_{i} is called from mod{dep}'s Thing.run\n",
            encoding="utf-8",
        )
    # A deliberately ambiguous name. A pass that resolves before both files are
    # indexed links `shared()` to whichever landed first; a build over the
    # complete symbol set refuses to guess. This is what splitting used to get
    # wrong (measured on a 4,788-file package: 2,148 extra speculative edges).
    for pkg in ("p1", "p2"):
        (root / "src" / pkg).mkdir()
        (root / "src" / pkg / "lib.py").write_text(
            "def shared():\n    return 1\n", encoding="utf-8"
        )
    (root / "src" / "user.py").write_text(
        "def use():\n    return shared()\n", encoding="utf-8"
    )


def _snapshot(db) -> tuple:
    """(files, symbols, resolved edges, unresolved edges) as sorted name tuples."""
    files = sorted(r[0] for r in db.conn.execute("SELECT path FROM files"))
    symbols = sorted(
        (r[0], r[1], r[2])
        for r in db.conn.execute(
            "SELECT f.path, s.name, s.kind FROM symbols s JOIN files f ON f.id=s.file_id"
        )
    )
    edges = sorted(
        (r[0], r[1], r[2], r[3] or "")
        for r in db.conn.execute(
            "SELECT s.qualified_name, r.target, r.rtype, t.qualified_name "
            "FROM relations r JOIN symbols s ON s.id=r.source_id "
            "LEFT JOIN symbols t ON t.id=r.target_id"
        )
    )
    return files, symbols, edges


def test_split_build_matches_one_pass_build(monkeypatch):
    # many tiny passes: one 2-file chunk per refresh, and the graph resolved two
    # edges at a time so the resolution loop is split across passes as well
    _write(A)
    monkeypatch.setattr(index_mod, "PARSE_CHUNK", 2)
    monkeypatch.setattr(index_mod, "RESOLVE_BLOCK", 2)
    monkeypatch.setattr(index_mod, "INDEX_TIME_BUDGET_S", -1.0)
    db_a = DB(A)
    ix_a = Indexer(A, db_a)
    passes = 0
    split_files = split_edges = False
    while True:
        stats = ix_a.refresh()
        passes += 1
        split_files = split_files or bool(stats.pending_files)
        split_edges = split_edges or bool(stats.pending_edges)
        assert passes < 200, "budget truncation is not making progress"
        if not stats.pending_files and not stats.pending_edges:
            break
    assert split_files, "the file phase never truncated"
    assert split_edges, "the resolution phase never truncated"
    assert passes > 4, passes

    # one pass, same content
    _write(B)
    monkeypatch.setattr(index_mod, "INDEX_TIME_BUDGET_S", float("inf"))
    db_b = DB(B)
    stats_b = Indexer(B, db_b).refresh()
    assert stats_b.pending_files == 0 and stats_b.pending_edges == 0
    assert stats_b.parsed == TOTAL_FILES

    assert _snapshot(db_a) == _snapshot(db_b), (
        "splitting a build across calls changed the index: the whole point of the "
        "budget is that it can only move work in time, not change results")
    db_a.close()
    db_b.close()


def test_partial_index_says_so(monkeypatch):
    _write(A)
    monkeypatch.setattr(index_mod, "PARSE_CHUNK", 2)
    monkeypatch.setattr(index_mod, "INDEX_TIME_BUDGET_S", -1.0)
    db = DB(A)
    ix = Indexer(A, db)
    tb = Toolbox(A, db, ix)
    out = tb.code_search("Thing0", limit=5)
    refresh = out["refresh"]
    assert refresh["pending_files"] > 0, refresh
    assert "hint" in refresh
    # reindex is the tool that finishes the build in one call
    done = tb.reindex()
    assert done["pending_files"] == 0
    assert done["files"] == TOTAL_FILES
    assert done["symbols"] > 0
    assert "refresh" not in tb.code_search("Thing0", limit=5)  # nothing left to build
    db.close()


def test_graph_still_building_is_reported_even_with_nothing_left_to_index(monkeypatch):
    """The second partial state -- files done, call graph mid-build -- arrives on
    a refresh that parsed nothing. `_finish` only attaches `refresh` when
    something happened, so without this the hint would be dropped exactly when
    it matters (an agent would read an empty find_callers as "unused")."""
    _write(A)
    monkeypatch.setattr(index_mod, "PARSE_CHUNK", 200)  # files fit in one chunk
    monkeypatch.setattr(index_mod, "RESOLVE_BLOCK", 2)  # graph needs many passes
    monkeypatch.setattr(index_mod, "INDEX_TIME_BUDGET_S", -1.0)
    db = DB(A)
    ix = Indexer(A, db)
    tb = Toolbox(A, db, ix)
    first = ix.refresh()
    assert first.pending_files == 0 and first.pending_edges > 0, first

    stats = ix.refresh()
    assert stats.parsed == 0, stats  # nothing left to index
    assert stats.pending_edges > 0, stats  # but the graph is mid-assembly
    out = tb.code_search("Thing0", limit=5)
    assert out["refresh"]["pending_edges"] > 0, out
    assert "call graph" in out["refresh"]["hint"]

    done = tb.reindex()
    assert done["pending_edges"] == 0 and done["pending_files"] == 0, done
    assert tb.find_callers("helper_1", limit=20)["callers"], "graph never got built"
    assert "refresh" not in tb.code_search("Thing0", limit=5)
    db.close()


def test_reindex_full_rebuilds_from_scratch(monkeypatch):
    _write(A)
    monkeypatch.setattr(index_mod, "INDEX_TIME_BUDGET_S", float("inf"))
    db = DB(A)
    ix = Indexer(A, db)
    tb = Toolbox(A, db, ix)
    tb.code_search("Thing0", limit=1)
    before = _snapshot(db)
    # an ignored rule only takes effect on a rebuild
    (A / ".fastgraph" / IGNORE_FILENAME).write_text(
        "mod3.py\n", encoding="utf-8"
    )
    out = tb.reindex(full=True)
    assert out["rebuilt"] is True
    assert out["files"] == TOTAL_FILES - 1, out
    files = _snapshot(db)[0]
    assert "src/mod3.py" not in files
    assert files == [f for f in before[0] if f != "src/mod3.py"]
    db.close()
