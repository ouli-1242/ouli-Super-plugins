"""Concurrent writers against one memory.sqlite (subprocess: SQLite locks are
per-process, so threads in a single Toolbox would not exercise the same thing).

Real scenario: two Qoder windows on the same project, both with the memory layer
on (its default; pinned explicitly in the subprocess env so an ambient `=0`
cannot silently turn this test into a no-op). WAL allows one writer at a time,
and `busy_timeout` decides whether the second waits or dies. A crash here is
loud ("database is locked") and
would land on the user's note write, so it is checked explicitly.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORK = Path(__file__).resolve().parent / "work_memory_concurrent"
sys.path.insert(0, str(REPO))

from fastgraph.db import DB  # noqa: E402
from fastgraph.index import Indexer  # noqa: E402
from fastgraph.tools import Toolbox  # noqa: E402

CHILD = r'''
import os, sys, json
sys.path.insert(0, r"@@REPO@@")
from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox
from pathlib import Path
root = Path(sys.argv[1]); tag = sys.argv[2]
db = DB(root)
tb = Toolbox(root, db, Indexer(root, db))
results = []
for i in range(15):
    out = tb.remember("symbol:src/mod0.py#worker", "note %s-%s" % (tag, i), kind="context")
    if not out.get("ok"):
        results.append("remember:" + out.get("error", "?"))
    cp = tb.checkpoint("snap-%s" % tag)
    if not cp.get("ok"):
        results.append("checkpoint:" + cp.get("error", "?"))
print(json.dumps(results) if results else "clean %s" % tag)
'''


@pytest.fixture()
def project():
    shutil.rmtree(WORK, ignore_errors=True)
    root = WORK
    (root / "src").mkdir(parents=True)
    for i in range(4):
        (root / "src" / f"mod{i}.py").write_text(
            f"def worker(x):\n    return x + {i}\n", encoding="utf-8"
        )
    db = DB(root)
    Toolbox(root, db, Indexer(root, db)).reindex()
    db.close()
    yield root
    shutil.rmtree(WORK, ignore_errors=True)


def test_parallel_processes_writing_the_same_memory(project):
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", CHILD.replace("@@REPO@@", str(REPO)), str(project), f"p{n}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "FASTGRAPH_MEMORY": "1"},
        )
        for n in range(4)
    ]
    outs = [(p.wait(timeout=240), p.stdout.read(), p.stderr.read()) for p in procs]

    failed = [(c, err.strip()[-200:]) for c, out, err in outs if c != 0]
    assert failed == [], f"child processes died: {failed}"
    reported = [o.strip() for _c, o, _e in outs]
    trouble = [r for r in reported if not r.startswith("clean")]
    assert trouble == [], f"a writer refused or died: {trouble[:2]}"

    db = DB(project, filename="memory.sqlite", code_index=False)
    try:
        notes = db.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        snaps = db.conn.execute("SELECT COUNT(*) FROM graph_snapshot").fetchone()[0]
        kinds = db.conn.execute("SELECT COUNT(DISTINCT label) FROM graph_snapshot").fetchone()[0]
    finally:
        db.close()
    assert notes == 60, notes          # 4 processes x 15 notes, none lost
    assert snaps == 60 and kinds == 4  # 15 per process x 4 labels, none lost
