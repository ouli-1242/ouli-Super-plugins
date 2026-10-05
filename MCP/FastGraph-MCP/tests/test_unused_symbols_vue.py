"""Vue methods referenced only from the template are not flagged unused."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph import graph
from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_vueunused"
VUE = """\
<template><view @click="handleX">x</view></template>
<script>
export default {
  methods: {
    handleX() {},
    reallyDead() {},
  },
};
</script>
"""


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def test_template_bound_method_not_unused():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "comp.vue").write_text(VUE, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    names = {u["symbol"] for u in graph.unused_symbols(db, limit=50)}
    assert "handleX" not in names
    assert "reallyDead" in names
    db.close()
    _rmtree(WORK)