"""Framework-registered code is not dead: decorated/annotated symbols,
Depends-referenced dependencies, and constructors."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph import graph
from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_registration"


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _unused(db: DB) -> dict[str, str]:
    return {u["symbol"]: u["file"] for u in graph.unused_symbols(db, limit=100)}


def test_fastapi_route_and_depends_not_unused():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "api.py").write_text(
        "from fastapi import Depends\n"
        "\n"
        "def get_db():\n"
        "    return None\n"
        "\n"
        "def get_current_user():\n"
        "    return 'u'\n"
        "\n"
        "@app.get('/x')\n"
        "def list_x(db=Depends(get_db), user=Depends(get_current_user)):\n"
        "    return 'ok'\n"
        "\n"
        "def really_dead():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    names = _unused(db)
    assert "list_x" not in names        # @app.get decorator registration
    assert "get_db" not in names        # Depends(get_db) reference
    assert "get_current_user" not in names
    assert "really_dead" in names
    db.close()
    _rmtree(WORK)


def test_java_annotated_method_not_unused():
    _rmtree(WORK)
    (WORK / "app").mkdir(parents=True, exist_ok=True)
    (WORK / "app/UserController.java").write_text(
        "package app;\n"
        "public class UserController {\n"
        "    @GetMapping(\"/x\")\n"
        "    public String list() { return \"x\"; }\n"
        "    public String deadHelper() { return \"d\"; }\n"
        "}\n",
        encoding="utf-8",
    )
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    names = _unused(db)
    assert "list" not in names      # @GetMapping annotation registration
    assert "deadHelper" in names
    db.close()
    _rmtree(WORK)


def test_python_constructors_not_unused():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "svc.py").write_text(
        "class Worker:\n"
        "    def __init__(self):\n"
        "        pass\n"
        "    def run(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    names = _unused(db)
    assert "__init__" not in names   # constructor called via Worker()
    assert "run" in names
    db.close()
    _rmtree(WORK)