"""Regression tests for the code-review fixes.

Covers: import resolution performance/caching (P0-1), skipping the resolver on
no-op refreshes (P0-2), FTS orphan rows, size-aware incremental detection,
actionable parse errors, the non-git changed_context fallback, the sticky
walk-guard reset, and the directory-keyed alias cache.
"""

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fastgraph.graph as graph_mod
import fastgraph.index as index_mod
from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox


@pytest.fixture()
def tmp_root(tmp_path):
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def _write(root: Path, files: dict[str, str]):
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def _build(root: Path, files: dict[str, str]):
    _write(root, files)
    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    ix.refresh()
    return db, ix, tb


# ---------------- P0-1: import resolution ----------------

def test_import_resolution_sees_files_added_later(tmp_root):
    """The stem-suffix cache must be invalidated when a file is added."""
    _write(tmp_root, {
        "pkg/__init__.py": "",
        "main.py": "from pkg.helper import f\n",
    })
    db = DB(tmp_root)
    ix = Indexer(tmp_root, db)
    tb = Toolbox(tmp_root, db, ix)
    ix.refresh()
    # file_deps splits resolved (internal) from unresolved imports; before the
    # helper exists the import can only be in external_imports
    before = tb.file_deps("main.py")
    assert before["imports"] == [], before
    assert before["external_imports"], before

    _write(tmp_root, {"pkg/helper.py": "def f():\n    return 1\n"})
    after = tb.file_deps("main.py")
    db.close()
    assert any(
        x.endswith("pkg/helper.py")
        for imp in after["imports"]
        for x in imp["resolves_to"]
    ), after


def test_import_suffix_matching_variants(tmp_root):
    """Dotted-suffix matching must keep working for deep module paths."""
    _write(tmp_root, {
        "app/services/auth.py": "def login():\n    return 1\n",
        "app/api.py": "from app.services.auth import login\n",
        "app/pkgmod.py": "def g():\n    return 1\n",
        "app/multi.py": "from app import pkgmod\n",
    })
    db, _ix, tb = _build(tmp_root, {})
    from_app = tb.file_deps("app/api.py")["imports"][0]["resolves_to"]
    multi = tb.file_deps("app/multi.py")["imports"][0]["resolves_to"]
    db.close()
    assert any(x.endswith("app/services/auth.py") for x in from_app), from_app
    assert any(x.endswith("app/pkgmod.py") for x in multi), multi


# ---------------- P0-2: resolver only runs when the symbol set changed -------

def test_steady_refresh_does_not_rerun_resolution(tmp_root, monkeypatch):
    """Unresolvable external calls keep target_id NULL forever; the resolver
    must not re-run for a refresh that re-parsed nothing."""
    _write(tmp_root, {"a.py": "def f():\n    print(1)\n"})
    db = DB(tmp_root)
    ix = Indexer(tmp_root, db)
    ix.refresh()
    assert db.conn.execute(
        "SELECT COUNT(*) FROM relations WHERE target_id IS NULL"
    ).fetchone()[0] > 0, "fixture must leave an unresolved relation"

    calls = {"n": 0}
    real = index_mod._resolve_all

    def counting(d):
        calls["n"] += 1
        return real(d)

    monkeypatch.setattr(index_mod, "_resolve_all", counting)

    ix.refresh()  # nothing changed
    assert calls["n"] == 0

    _write(tmp_root, {"a.py": "def f():\n    print(2)\n"})
    ix.refresh()  # a file changed -> resolution is retried
    db.close()
    assert calls["n"] == 1


# ---------------- FTS orphan rows ----------------

def test_fts_has_no_orphan_rows_after_repeated_edits(tmp_root):
    f = tmp_root / "m.py"
    f.write_text("def a():\n    return 1\n", encoding="utf-8")
    db = DB(tmp_root)
    ix = Indexer(tmp_root, db)
    ix.refresh()
    for k in range(6):
        f.write_text(f"def g{k}():\n    return {k}\n", encoding="utf-8")
        ix.refresh()
    symbols = db.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    fts = db.conn.execute("SELECT COUNT(*) FROM fts_symbols").fetchone()[0]
    orphans = db.conn.execute(
        "SELECT COUNT(*) FROM fts_symbols f LEFT JOIN symbols s ON f.rowid = s.id "
        "WHERE s.id IS NULL"
    ).fetchone()[0]
    db.close()
    assert fts == symbols, f"FTS rows {fts} != symbols {symbols}"
    assert orphans == 0


def test_removed_file_leaves_no_fts_rows(tmp_root):
    """delete_file must clear fts_symbols too.

    FTS rows are not covered by the files -> symbols ON DELETE CASCADE. If they
    survive, the rowids they keep (= old symbol ids) collide with the ids
    SQLite re-assigns after a rebuild, raising
    sqlite3.IntegrityError: "constraint failed" and aborting the index.
    """
    (tmp_root / "a.py").write_text("def x():\n    return 1\n", encoding="utf-8")
    b = tmp_root / "b.py"
    b.write_text("def y():\n    return 2\n", encoding="utf-8")
    db = DB(tmp_root)
    ix = Indexer(tmp_root, db)
    ix.refresh()
    before = db.conn.execute("SELECT COUNT(*) FROM fts_symbols").fetchone()[0]

    b.unlink()
    ix.refresh()
    after = db.conn.execute("SELECT COUNT(*) FROM fts_symbols").fetchone()[0]
    orphans = db.conn.execute(
        "SELECT COUNT(*) FROM fts_symbols f LEFT JOIN symbols s ON f.rowid = s.id "
        "WHERE s.id IS NULL"
    ).fetchone()[0]

    # simulate an INDEX_VERSION bump -> the whole index is rebuilt
    db.set_meta("index_version", "0")
    db.commit()
    stats = ix.refresh()  # must not raise IntegrityError
    db.close()

    assert after < before, (after, before)
    assert orphans == 0
    assert stats.errors == 0


def test_index_failure_does_not_wedge_the_db(tmp_root, monkeypatch):
    """A mid-index exception must roll back.

    Otherwise the write transaction stays open on that connection, keeping the
    SQLite write lock: every later call on the index fails with
    "database is locked" until the process exits (observed on a real project
    that hit an IntegrityError while rebuilding).
    """
    import sqlite3

    (tmp_root / "a.py").write_text("def x():\n    return 1\n", encoding="utf-8")
    db = DB(tmp_root)
    ix = Indexer(tmp_root, db)
    real = ix._store_file

    def boom(rel, st, hash_, result, source):
        real(rel, st, hash_, result, source)  # write something first
        raise sqlite3.IntegrityError("constraint failed")

    monkeypatch.setattr(ix, "_store_file", boom)
    with pytest.raises(sqlite3.IntegrityError):
        ix.refresh()

    monkeypatch.setattr(ix, "_store_file", real)
    # a *second* connection must be able to write again (lock released)
    db2 = DB(tmp_root)
    try:
        db2.conn.execute("DELETE FROM fts_symbols")
        db2.commit()
    finally:
        db2.close()

    stats = ix.refresh()
    symbols = db.count_symbols()
    db.close()
    assert stats.errors == 0
    assert symbols > 0


# ---------------- size-aware incremental detection ----------------

def test_incremental_detects_size_change_with_preserved_mtime(tmp_root):
    f = tmp_root / "a.py"
    f.write_text("def f():\n    return 1\n", encoding="utf-8")
    db = DB(tmp_root)
    ix = Indexer(tmp_root, db)
    ix.refresh()

    st = f.stat()
    f.write_text("def f():\n    return 11111\n", encoding="utf-8")
    os.utime(f, (st.st_atime, st.st_mtime))  # same mtime, different size

    stats = ix.refresh()
    db.close()
    assert stats.parsed == 1, "a size-only change must be re-parsed"


# ---------------- actionable parse errors ----------------

def test_parse_error_reports_the_cause(tmp_root):
    _write(tmp_root, {"bad.py": "def f(:\n    pass\n"})
    db = DB(tmp_root)
    ix = Indexer(tmp_root, db)
    stats = ix.refresh()
    errors = db.parse_errors()
    db.close()
    assert stats.errors >= 1
    assert errors, "a syntax error must be recorded"
    assert any(
        "SyntaxError" in e["error"] or "parse error" in e["error"] for e in errors
    ), errors


# ---------------- non-git changed_context fallback ----------------

def test_changed_context_non_git_falls_back_to_mtime(tmp_root):
    _write(tmp_root, {"a.py": "def f():\n    return 1\n"})
    db = DB(tmp_root)
    ix = Indexer(tmp_root, db)
    tb = Toolbox(tmp_root, db, ix)
    ix.refresh()

    _write(tmp_root, {"a.py": "def f():\n    return 2\n"})
    out = tb.changed_context()
    db.close()
    assert out["source"] == "mtime", out
    assert "a.py" in out["changed_files"], out
    assert any(s["symbol"] == "f" for s in out["changed_symbols"].get("modified", [])), out


# ---------------- walk-guard reset ----------------

def test_walk_skip_guard_resets_between_refreshes(tmp_root, monkeypatch):
    _write(tmp_root, {f"m{i}.py": f"def f{i}():\n    return {i}\n" for i in range(6)})
    db = DB(tmp_root)
    ix = Indexer(tmp_root, db)
    ix.refresh()
    assert db.get_file_id("m5.py") is not None

    (tmp_root / "m5.py").unlink()

    # an artificially tiny scan budget trips the guard and suppresses deletion
    monkeypatch.setattr(index_mod, "MAX_SCAN_ENTRIES", 1)
    skipped_once = ix.refresh().skipped
    stale_while_skipped = db.get_file_id("m5.py")

    # restoring the budget must clear the guard so stale files are removed
    monkeypatch.setattr(index_mod, "MAX_SCAN_ENTRIES", 200_000)
    skipped_again = ix.refresh().skipped
    gone = db.get_file_id("m5.py")
    db.close()

    assert skipped_once is True
    assert stale_while_skipped is not None, "deletion must not run on a truncated walk"
    assert skipped_again is False
    assert gone is None, "the guard must reset so stale files are deleted again"


# ---------------- alias cache is directory-keyed and bounded ----------------

def test_alias_cache_is_dir_keyed(tmp_root):
    db, _ix, _tb = _build(tmp_root, {
        "src/a.py": "import os\n",
        "src/b.py": "import os\n",
        "src/deep/c.py": "import os\n",
    })
    graph_mod._alias_cache.clear()
    graph_mod._alias_prefixes(db, "src/a.py")
    graph_mod._alias_prefixes(db, "src/b.py")   # same dir -> same entry
    assert len(graph_mod._alias_cache) == 1
    graph_mod._alias_prefixes(db, "src/deep/c.py")  # different dir -> new entry
    db.close()
    assert len(graph_mod._alias_cache) == 2
