"""A cold index that dies mid-run keeps its progress and resumes.

Found on sentry (21k files): the whole write phase was one transaction, so
killing the process at ~40% discarded all of it -- the WAL came back empty and
the next run started from zero, paying the full cold index again. Batching the
parse+store loop commits durable progress per chunk.
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph import index as index_mod
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_interrupted"
FILES = [f"m{i}.py" for i in range(6)]


def _rows(db):
    return {
        r[0]: r[1]
        for r in db.conn.execute(
            "SELECT f.path, (SELECT count(*) FROM symbols s WHERE s.file_id = f.id) FROM files f"
        )
    }


def _repo() -> Path:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    for i, name in enumerate(FILES):
        body = f"def fn_{i}():\n    return {i}\n\ndef other_{i}():\n    return {i}\n"
        if i == 0:
            body = "from m1 import fn_1\n\n" + body  # a real import for import_edges
        (WORK / name).write_text(body, encoding="utf-8")
    return WORK


def _edge_count(db) -> int:
    return db.conn.execute("SELECT count(*) FROM import_edges").fetchone()[0]


def test_partial_index_survives_and_resumes(monkeypatch):
    repo = _repo()
    monkeypatch.setattr(index_mod, "PARSE_CHUNK", 2)
    db = DB(repo)
    ix = Indexer(repo, db)
    real = ix._store_file
    seen = {"n": 0}

    def flaky(*args, **kwargs):
        seen["n"] += 1
        if seen["n"] == 3:  # second chunk: first chunk is already committed
            raise RuntimeError("process killed here")
        return real(*args, **kwargs)

    ix._store_file = flaky
    with pytest.raises(RuntimeError):
        ix.refresh()

    kept = _rows(db)
    assert len(kept) == 2, kept  # the committed chunk survived
    assert all(count >= 2 for count in kept.values()), kept

    # resume: only the files that never landed are parsed again
    ix._store_file = real
    stats = ix.refresh()
    assert stats.parsed == 4, stats.parsed
    after = _rows(db)
    assert len(after) == 6
    assert {k: after[k] for k in kept} == kept  # survivors were not rebuilt

    # and a second process can read what a crashed one left behind
    db.close()
    reopened = DB(repo)
    try:
        assert len(_rows(reopened)) == 6
    finally:
        reopened.close()


def test_rebuild_is_not_lost_when_the_rebuild_itself_dies():
    """`_store_file` skips its own import-edge pass when a wholesale rebuild is
    coming, so a refresh killed inside that rebuild must not leave the committed
    files without edges -- the next refresh has to finish the owed pass even
    though nothing on disk changed any more."""
    repo = _repo()
    db = DB(repo)
    ix = Indexer(repo, db)
    real = ix._rebuild_all_import_edges

    def boom():
        raise RuntimeError("killed inside the rebuild")

    ix._rebuild_all_import_edges = boom
    with pytest.raises(RuntimeError):
        ix.refresh()

    # The same process keeps serving: `_refresh` resets its per-call flags, so the
    # only record that the rebuild is still owed is the durable meta row. (A new
    # process would self-heal -- its first refresh always rebuilds.)
    ix._rebuild_all_import_edges = real
    stats = ix.refresh()
    assert stats.parsed == 0, stats.parsed  # nothing on disk changed
    assert _edge_count(db) > 0, "the owed rebuild never ran"
    assert db.get_meta("edges_rebuild_pending") != "1"
    db.close()
