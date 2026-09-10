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