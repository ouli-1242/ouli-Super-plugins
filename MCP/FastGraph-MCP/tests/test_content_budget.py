"""The string-literal content corpus is budgeted per file, and says so.

Found on sentry (21k files): one 822KB generated `android_models.py` produced
49,121 `line_content` rows -- 58% of what the entire 1,979-file element-plus
repo produces, from 2 symbols. That write volume, not parsing, is what made the
cold index crawl and the index file grow ~1MB per 1MB of source. Comments and
docstrings stay uncapped because prose is what content search exists for.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph import index as index_mod
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

WORK = Path(__file__).resolve().parent / "work_contentbudget"

LITERALS = "data = [\n" + "".join(f'    "value-{i}",\n' for i in range(400)) + "]\n"
PROSE = '# 限流：每秒最多 5 次\ndef f():\n    """缓存键前缀约定"""\n    return 1\n'


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _index(monkeypatch, budget: int = 50):
    monkeypatch.setattr(index_mod, "MAX_STRING_CONTENT_LINES", budget)
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "gen.py").write_text(LITERALS, encoding="utf-8")
    (WORK / "svc.py").write_text(PROSE, encoding="utf-8")
    db = DB(WORK)
    stats = Indexer(WORK, db).force_index()
    return db, stats


def test_literal_rows_are_capped_and_reported(monkeypatch):
    db, _stats = _index(monkeypatch, budget=50)
    rows = db.conn.execute(
        "SELECT count(*) FROM line_content lc JOIN files f ON f.id=lc.file_id WHERE f.path='gen.py'"
    ).fetchone()[0]
    assert rows <= 60, rows          # 400 literals -> the budget, not 400 rows
    flag = dict(db.conn.execute(
        "SELECT path, content_capped FROM files WHERE path IN ('gen.py','svc.py')"
    ).fetchall())
    assert flag["gen.py"] == 1, flag     # reported in the index, survives the process
    assert flag["svc.py"] == 0, flag     # a file near no budget is not reported
    db.close()
    _rmtree(WORK)


def test_prose_stays_searchable_in_a_capped_file(monkeypatch):
    """The budget throttles literal noise only; comments/docstrings survive."""
    db, _stats = _index(monkeypatch, budget=50)
    tb = Toolbox(WORK, db, Indexer(WORK, db))
    hits = tb.code_search("限流")["results"]
    assert any(h["file"] == "svc.py" for h in hits), hits
    hits = tb.code_search("缓存键前缀约定")["results"]
    assert any(h["file"] == "svc.py" for h in hits), hits
    # and the cap is visible to the caller, so a miss is not read as "absent"
    overview = tb.project_overview()
    assert overview["content_capped"] == ["gen.py"], overview
    tb.close()
    db.close()
    _rmtree(WORK)
