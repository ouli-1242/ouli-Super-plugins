"""code_search finds keywords that appear only in comments/strings."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.search import code_search

WORK = Path(__file__).resolve().parent / "work_content"
PY = """\
# 限流：每秒最多 5 次
def fetch():
    return "https://example.com"
"""


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def test_chinese_comment_searchable():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "svc.py").write_text(PY, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    hits = code_search(db, "限流", limit=10)
    assert any(h["match"] == "content" and h["file"] == "svc.py" for h in hits)
    assert any("限流" in h.get("snippet", "") for h in hits)
    db.close()
    _rmtree(WORK)

# ---------------------------------------------------------------- duplicate lines
# A one-line `"""docstring"""` is matched by the triple-quoted pass AND by the
# single-line string-literal pass. Quote-stripped, the two rows are identical, so the
# same line used to be stored twice and then answered a query twice -- two of five
# result slots gone for a line the caller has already seen.


def _repo(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    db = DB(tmp_path)
    Indexer(tmp_path, db).refresh()
    return db


def test_one_line_docstring_is_stored_once(tmp_path):
    db = _repo(tmp_path, {"src/a.py": 'def f(x):\n    """限流阈值配置"""\n    return x\n'})
    try:
        rows = db.conn.execute("SELECT line, kind, text FROM line_content").fetchall()
        assert len(rows) == len(set(rows)), rows
        assert any("限流阈值配置" in r[2] for r in rows), rows
    finally:
        db.close()


def test_content_results_do_not_repeat_a_line(tmp_path):
    db = _repo(tmp_path, {"src/a.py": 'def f(x):\n    """限流阈值配置"""\n    return x\n'})
    try:
        hits = code_search(db, "限流阈值配置", limit=5)
        content = [h for h in hits if h["match"] == "content"]
        assert content, hits
        assert len({(h["file"], h["line"], h["snippet"]) for h in content}) == len(content), content
    finally:
        db.close()


def test_an_old_index_with_duplicates_still_answers_once(tmp_path):
    """Indexes written before the collector refused duplicates keep the pairs on disk,
    and re-parsing every repository to fix a result-slot bug is the wrong trade."""
    db = _repo(tmp_path, {"src/a.py": 'def f(x):\n    """限流阈值配置"""\n    return x\n'})
    try:
        original = db.conn.execute(
            "SELECT file_id, line, kind, text FROM line_content LIMIT 1").fetchone()
        db.conn.execute(
            "INSERT INTO line_content (file_id, line, kind, text) VALUES (?,?,?,?)", original)
        db.conn.commit()
        assert len(db.conn.execute("SELECT DISTINCT line, text FROM line_content").fetchall()) == 1
        hits = [h for h in code_search(db, "限流阈值配置", limit=5) if h["match"] == "content"]
        assert len(hits) == 1, hits
    finally:
        db.close()
