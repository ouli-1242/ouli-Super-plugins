"""Coverage for the analysis tools: unused_symbols, hot_symbols,
file_metrics, module_cycles."""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

WORK = Path(__file__).resolve().parent / "work_analysis"


def _rmtree(path: Path):
    if not path.exists():
        return
    for p in path.rglob("*"):
        p.chmod(p.stat().st_mode | 0o200)
    shutil.rmtree(path, ignore_errors=True)


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_sample(root: Path):
    write(root / "src/core.py", '''\
class Service:
    def handle(self):
        return "ok"

    def legacy(self):
        return "old"


def unused_fn():
    return 1
''')
    write(root / "src/a.py", '''\
from core import Service
from b import y

def entry():
    return Service().handle()


def y():
    return "y"
''')
    write(root / "src/b.py", '''\
from a import entry
from core import Service

def run():
    return entry() and Service().handle()
''')


@pytest.fixture(scope="module")
def toolbox():
    _rmtree(WORK)
    WORK.mkdir(parents=True)
    build_sample(WORK)
    db = DB(WORK)
    indexer = Indexer(WORK, db)
    tools = Toolbox(WORK, db, indexer)
    indexer.refresh()
    yield tools
    db.close()
    _rmtree(WORK)


def test_unused_symbols(toolbox):
    res = toolbox.unused_symbols()
    names = {u["qualified_name"] for u in res["unused"]}
    assert "Service.legacy" in names      # member never called
    assert "unused_fn" in names           # module function never referenced
    assert "Service.handle" not in names  # called by a.entry and b.run
    assert "entry" not in names           # called by b.run


def test_hot_symbols(toolbox):
    res = toolbox.hot_symbols()
    by_qname = {h["qualified_name"]: h for h in res["hot"]}
    handle = by_qname.get("Service.handle")
    assert handle is not None and handle["call_count"] >= 2
    # entry is called by run() once and constructs/calls handle too
    assert "entry" in by_qname


def test_file_metrics(toolbox):
    res = toolbox.file_metrics()
    by_file = {f["file"]: f for f in res["files"]}
    assert "src/core.py" in by_file
    core = by_file["src/core.py"]
    assert core["symbols"] >= 3        # Service + handle + legacy + unused_fn
    assert core["incoming_calls"] >= 2  # via a.py and b.py
    assert "src/a.py" in by_file


def test_module_cycles(toolbox):
    res = toolbox.module_cycles()
    assert res["count"] >= 1
    cycle_files = [set(c["files"]) for c in res["cycles"]]
    assert any({"src/a.py", "src/b.py"} <= files for files in cycle_files)


def test_analysis_tools_honor_root(toolbox):
    other = WORK.parent / "other_analysis"
    write(other / "solo.py", "def only_one():\n    return 1\n")
    try:
        for name, call in [
            ("unused_symbols", lambda: toolbox.unused_symbols(root=str(other))),
            ("hot_symbols", lambda: toolbox.hot_symbols(root=str(other))),
            ("file_metrics", lambda: toolbox.file_metrics(root=str(other))),
            ("module_cycles", lambda: toolbox.module_cycles(root=str(other))),
        ]:
            res = call()
            assert res["root"] == str(other.resolve()), name
    finally:
        _rmtree(other)