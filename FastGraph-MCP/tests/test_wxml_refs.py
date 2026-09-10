"""Native miniapp .wxml event bindings exclude page .js handlers from unused."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph import graph
from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_wxml"
PAGE_JS = """\
Page({
  goMemory() {},
  toggle() {},
  reallyDead() {},
});
"""
PAGE_WXML = """\
<view bindtap="goMemory">记忆</view>
<switch bindchange="toggle" />
"""
OTHER_JS = "export function goMemory() { return 1; }\n"


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def test_wxml_bound_handlers_not_unused():
    _rmtree(WORK)
    (WORK / "pages/mem").mkdir(parents=True, exist_ok=True)
    (WORK / "pages/mem/mem.js").write_text(PAGE_JS, encoding="utf-8")
    (WORK / "pages/mem/mem.wxml").write_text(PAGE_WXML, encoding="utf-8")
    (WORK / "helper.js").write_text(OTHER_JS, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    names = {u["symbol"]: u["file"] for u in graph.unused_symbols(db, limit=50)}
    assert "reallyDead" in names
    flagged_go = {f for n, f in names.items() if n == "goMemory"}
    assert not any("pages/mem/mem.js" in f for f in flagged_go)
    assert "helper.js" in flagged_go  # standalone .js keeps full coverage
    assert "toggle" not in names
    db.close()
    _rmtree(WORK)