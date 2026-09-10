"""Framework lifecycle callbacks (uni-app/Vue) are excluded from unused_symbols;
plain JS files keep full coverage."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph import graph
from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_lifecycle"
VUE = """\
<template><view>hi</view></template>
<script>
export default {
  onLoad() {},
  mounted() {},
  reallyDead() {},
};
</script>
"""


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def test_lifecycle_callbacks_excluded_in_vue_only():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "page.vue").write_text(VUE, encoding="utf-8")
    (WORK / "helper.js").write_text(
        "export function onLoad() { return 1; }\n", encoding="utf-8"
    )
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    names = {u["symbol"]: u["file"] for u in graph.unused_symbols(db, limit=50)}
    assert "reallyDead" in names  # real dead code still reported
    flagged_onload = {f for n, f in names.items() if n == "onLoad"}
    # page.vue's lifecycle callback excluded; helper.js's plain function kept
    assert "helper.js" in flagged_onload
    assert not any(f.endswith("page.vue") for f in flagged_onload)
    assert "mounted" not in names
    db.close()
    _rmtree(WORK)


def test_miniapp_page_lifecycle_excluded():
    """WeChat miniapp page .js (sibling .wxml) and app.js keep lifecycle
    callbacks out of unused_symbols."""
    _rmtree(WORK)
    (WORK / "pages/mem").mkdir(parents=True, exist_ok=True)
    (WORK / "pages/mem/mem.js").write_text(
        "Page({ onShow() {}, onLoad() {} });\n", encoding="utf-8"
    )
    (WORK / "pages/mem/mem.wxml").write_text("<view>x</view>\n", encoding="utf-8")
    (WORK / "app.js").write_text("App({ onLaunch() {} });\n", encoding="utf-8")
    (WORK / "app.json").write_text("{}", encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    names = {u["symbol"] for u in graph.unused_symbols(db, limit=50)}
    assert "onShow" not in names
    assert "onLoad" not in names
    assert "onLaunch" not in names
    db.close()
    _rmtree(WORK)