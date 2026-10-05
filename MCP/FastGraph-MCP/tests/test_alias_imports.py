"""import { b as a } from './mod' → call a() resolves to mod.b."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph import graph
from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_alias"
MOD = "export function b() { return 1; }\n"
MAIN = """\
import { b as a } from './mod.js';
export function main() { return a(); }
"""


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def test_alias_call_resolves_to_export():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "mod.js").write_text(MOD, encoding="utf-8")
    (WORK / "main.js").write_text(MAIN, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    callers = graph.find_callers(db, "b", limit=10)
    files = {c["path"] for c in callers}
    assert "main.js" in files
    db.close()
    _rmtree(WORK)