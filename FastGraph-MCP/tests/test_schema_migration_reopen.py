"""A database written by an older build must reopen without error.

Bite taken live: `idx_rel_pending ON relations(tried, ...)` was added to SCHEMA,
but `DB.__init__` runs SCHEMA (via `_new_conn`) *before* `_migrate_schema()` adds
the column, so every existing index crashed the server at startup with
`OperationalError: no such column: tried` -- exit code 1 before the MCP handshake,
which a client reports only as "Process Exited". Migration-owned objects are
created in the migration, after the columns they reference exist.
"""
import shutil
import sqlite3
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_migration"


def _build_indexed_db() -> None:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    (WORK / "a.py").write_text("def f():\n    return print(1)\n", encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    db.close()


def _downgrade_to_previous_schema() -> None:
    """Strip what the current build adds, as if the file came from an older one."""
    conn = sqlite3.connect(str(WORK / ".fastgraph" / "index.sqlite"))
    conn.execute("DROP INDEX IF EXISTS idx_rel_pending")
    conn.execute("ALTER TABLE relations DROP COLUMN tried")
    conn.execute("ALTER TABLE files DROP COLUMN content_capped")
    conn.commit()
    conn.close()


def test_old_database_reopens_and_gains_the_new_objects():
    _build_indexed_db()
    _downgrade_to_previous_schema()

    db = DB(WORK)  # the crash site: SCHEMA first, then _migrate_schema

    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(relations)")}
    assert "tried" in cols, cols
    assert "content_capped" in {r[1] for r in db.conn.execute("PRAGMA table_info(files)")}
    assert db.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_rel_pending'"
    ).fetchone(), "the partial index must exist after the migration"
    # and the index is usable, not just present
    assert db.conn.execute(
        "SELECT count(*) FROM relations WHERE target_id IS NULL AND tried = 0"
    ).fetchone()[0] >= 0
    db.close()
    shutil.rmtree(WORK, ignore_errors=True)


def test_startup_waits_out_a_transient_write_lock(tmp_path):
    """A locked index must not turn into "MCP process exited".

    Reproduced live: a second process was still indexing the same project, and
    the DDL at startup raised `OperationalError: database is locked` before the
    MCP handshake could answer -- the client showed only exit code 1. The
    startup writes now run with a long busy timeout and retry.
    """
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    DB(project).close()  # index dir exists

    db_file = project / ".fastgraph" / "index.sqlite"
    holder = sqlite3.connect(str(db_file))
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("UPDATE files SET size = size + 0")

    result: dict = {}

    def open_while_locked():
        start = time.perf_counter()
        try:
            db = DB(project)
            result["ok"] = time.perf_counter() - start
            db.close()
        except Exception as e:  # noqa: BLE001 - the assertion below is the point
            result["error"] = f"{type(e).__name__}: {e}"

    worker = threading.Thread(target=open_while_locked)
    worker.start()
    time.sleep(1.0)
    holder.commit()
    holder.close()
    worker.join(60)

    assert "error" not in result, result["error"]
    assert result["ok"] >= 0.9, "should have waited, not failed instantly"


def test_old_database_data_survives():
    """The migration adds columns; it must not lose the indexed content."""
    _build_indexed_db()
    before = DB(WORK).conn.execute(
        "SELECT count(*) FROM symbols"
    ).fetchone()[0]
    _downgrade_to_previous_schema()
    db = DB(WORK)
    assert before > 0
    assert db.conn.execute("SELECT count(*) FROM symbols").fetchone()[0] == before
    db.close()
    shutil.rmtree(WORK, ignore_errors=True)
