"""Content-only edits must re-derive a file's import edges on the per-file path.

The wholesale import_edges rebuild is skipped when nothing but file *contents*
changed, so `_store_file` has to write that file's own edges. If it did not,
`file_deps` would keep reporting the imports that were just edited away -- and a
test that only ever does a first index would miss it, because a fresh Indexer
always rebuilds once (its build-config fingerprint starts empty).
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_incedges"
# module names are two characters or more on purpose: the resolver declines
# single-letter specs (`from src.c import f` resolves to nothing), which would
# make these fixtures fail for a reason unrelated to what they test


def _targets(db: DB, rel: str) -> list[str]:
    return sorted(
        t
        for (t,) in db.conn.execute(
            "SELECT ie.target FROM import_edges ie JOIN files f ON f.id = ie.file_id "
            "WHERE f.path = ?",
            (rel,),
        )
    )


def _build() -> Path:
    shutil.rmtree(WORK, ignore_errors=True)
    (WORK / "src").mkdir(parents=True)
    for name in ("bee.py", "cee.py"):
        (WORK / "src" / name).write_text("def f():\n    return 1\n", encoding="utf-8")
    (WORK / "src" / "alpha.py").write_text(
        "from src.bee import f\n\ndef g():\n    return f()\n", encoding="utf-8"
    )
    return WORK


def test_content_only_edit_updates_import_edges():
    repo = _build()
    db = DB(repo)
    ix = Indexer(repo, db)
    ix.refresh()
    assert _targets(db, "src/alpha.py") == ["src/bee.py"]

    # only the content changes: no file added, none removed
    (repo / "src" / "alpha.py").write_text(
        "from src.cee import f\n\ndef g():\n    return f()\n", encoding="utf-8"
    )
    stats = ix.refresh()
    assert stats.parsed == 1 and stats.deleted == 0, stats
    assert _targets(db, "src/alpha.py") == ["src/cee.py"]

    # and a removed import leaves nothing behind
    (repo / "src" / "alpha.py").write_text("def g():\n    return 1\n", encoding="utf-8")
    ix.refresh()
    assert _targets(db, "src/alpha.py") == []
    db.close()


def test_owed_rebuild_survives_a_crash_inside_it():
    """The flag that skips the per-file edge pass flips when the *first new file*
    is stored, mid-refresh, after the durable write at the top. The rebuild it
    promises can still be interrupted -- and a later refresh in the same process
    sees no changes at all (its build-config fingerprint is already current), so
    the owed pass has to be recorded when the flag flips."""
    repo = _build()
    db = DB(repo)
    ix = Indexer(repo, db)
    ix.refresh()  # steady state: config fingerprint recorded, meta cleared
    assert db.get_meta("edges_rebuild_pending") != "1"

    (repo / "src" / "dee.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / "src" / "alpha.py").write_text(
        "from src.dee import f\n\ndef g():\n    return f()\n", encoding="utf-8"
    )
    real = ix._rebuild_all_import_edges

    def boom():
        raise RuntimeError("killed inside the rebuild")

    ix._rebuild_all_import_edges = boom
    with pytest.raises(RuntimeError):
        ix.refresh()

    ix._rebuild_all_import_edges = real
    stats = ix.refresh()
    assert stats.parsed == 0, stats.parsed
    assert _targets(db, "src/alpha.py") == ["src/dee.py"]
    assert db.get_meta("edges_rebuild_pending") != "1"
    db.close()
