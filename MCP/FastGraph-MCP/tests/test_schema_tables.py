"""New tables (template_refs, line_content) exist after DB init."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB

WORK = Path(__file__).resolve().parent / "work_schema"


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _tables(db: DB) -> set[str]:
    return {
        r[0]
        for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def test_new_tables_exist():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    db = DB(WORK)
    names = _tables(db)
    assert "template_refs" in names
    assert "line_content" in names
    db.close()
    _rmtree(WORK)


def test_busy_timeout_set():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    db = DB(WORK)
    val = db.conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert val == 5000, f"busy_timeout should be 5000, got {val}"
    db.close()
    _rmtree(WORK)


def test_cross_connection_writer_waits():
    """A second connection (another process) blocked by a write lock waits on
    busy_timeout instead of failing instantly with 'database is locked'."""
    import threading
    import time

    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    db1 = DB(WORK)
    db2 = DB(WORK)
    result: list[str] = []
    db1.conn.execute("BEGIN IMMEDIATE")  # hold the write lock

    def writer():
        try:
            db2.conn.execute("INSERT INTO meta (key, value) VALUES ('k', 'v')")
            db2.conn.commit()
            result.append("ok")
        except Exception as e:  # noqa: BLE001
            result.append(str(e))

    t = threading.Thread(target=writer)
    t.start()
    time.sleep(0.3)
    assert result == [], f"writer must wait on busy_timeout, got: {result}"
    db1.conn.rollback()  # release the lock
    t.join(timeout=5)
    assert result == ["ok"], f"writer should succeed after lock release: {result}"
    db1.close()
    db2.close()
    _rmtree(WORK)