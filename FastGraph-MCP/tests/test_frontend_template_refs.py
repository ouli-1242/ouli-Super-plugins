"""Vue template identifier references are captured into template_refs."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_tplrefs"
VUE = """\
<template>
  <view>
    <text @click="handleX">Hi {{ label }}</text>
    <view v-if="visible" :class="cls">A</view>
  </view>
</template>
<script>
export default {
  data() { return { label: 'a', visible: true, cls: 'b' }; },
  methods: {
    handleX() { console.log('x'); },
    unusedY() { console.log('y'); },
  },
};
</script>
"""


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _refs(db: DB) -> set[str]:
    return {r[0] for r in db.conn.execute("SELECT name FROM template_refs")}


def test_vue_template_refs_captured():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "comp.vue").write_text(VUE, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    refs = _refs(db)
    assert "handleX" in refs   # @click binding
    assert "visible" in refs   # v-if binding
    db.close()
    _rmtree(WORK)