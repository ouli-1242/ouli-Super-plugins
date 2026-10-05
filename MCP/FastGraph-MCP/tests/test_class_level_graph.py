"""Class-level queries aggregate member call edges."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph import graph
from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_classlevel"
SVC = """\
package app;
public class Greeter {
    public String greet() { return "hi"; }
}
"""
CTRL = """\
package app;
public class HomeController {
    private final Greeter greeter;
    public HomeController(Greeter g) { this.greeter = g; }
    public String home() { return greeter.greet(); }
}
"""


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def test_class_level_callers_and_callees():
    _rmtree(WORK)
    (WORK / "app").mkdir(parents=True, exist_ok=True)
    (WORK / "app/Greeter.java").write_text(SVC, encoding="utf-8")
    (WORK / "app/HomeController.java").write_text(CTRL, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    # 类名查询聚合成员边：Greeter 的调用方包含 HomeController
    callers = graph.find_callers(db, "Greeter", limit=10)
    files = {c["path"] for c in callers}
    assert any("HomeController.java" in f for f in files)
    # HomeController 调用了 Greeter.greet
    callees = graph.find_callees(db, "HomeController", limit=10)
    callee_names = {c["name"] for c in callees}
    assert "greet" in callee_names
    db.close()
    _rmtree(WORK)