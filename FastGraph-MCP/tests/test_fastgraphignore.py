""".fastgraph/.fastgraphignore skips matching entries (local-only, template
auto-created on first index), with incremental removal on refresh."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.config import IGNORE_TEMPLATE
from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_ignore"


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _make_project(files: dict[str, str]):
    _rmtree(WORK)
    for rel, content in files.items():
        p = WORK / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def _paths(db: DB) -> list[str]:
    return [r[0] for r in db.conn.execute("SELECT path FROM files ORDER BY path")]


def test_ignore_template_auto_created():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    db = DB(WORK)
    ignore = WORK / ".fastgraph" / ".fastgraphignore"
    assert ignore.is_file()
    assert ignore.read_text(encoding="utf-8") == IGNORE_TEMPLATE
    # never overwritten once the user edits it
    ignore.write_text("vendor\n", encoding="utf-8")
    db2 = DB(WORK)
    assert ignore.read_text(encoding="utf-8") == "vendor\n"
    db.close()
    db2.close()
    _rmtree(WORK)


def test_ignore_vendor_dir():
    _make_project({
        "src/a.py": "x = 1\n",
        "vendor/lib.py": "y = 2\n",
        "src/vendor/helper.py": "z = 3\n",
    })
    (WORK / ".fastgraph").mkdir(parents=True, exist_ok=True)
    (WORK / ".fastgraph/.fastgraphignore").write_text("vendor\n", encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    paths = _paths(db)
    assert "src/a.py" in paths
    assert "vendor/lib.py" not in paths
    assert "src/vendor/helper.py" not in paths  # name match at any depth
    db.close()
    _rmtree(WORK)


def test_incremental_removal_when_ignored_later():
    _make_project({
        "src/a.py": "x = 1\n",
        "legacy/b.py": "y = 2\n",
    })
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    assert "legacy/b.py" in _paths(db)
    ignore = WORK / ".fastgraph" / ".fastgraphignore"
    ignore.write_text("legacy\n", encoding="utf-8")
    stats = Indexer(WORK, db).refresh()
    assert stats.deleted >= 1
    assert "legacy/b.py" not in _paths(db)
    assert "src/a.py" in _paths(db)
    db.close()
    _rmtree(WORK)


def test_path_glob_pattern():
    _make_project({
        "generated/bundle.min.js": "x\n",
        "generated/source.js": "y\n",
        "src/main.js": "z\n",
    })
    (WORK / ".fastgraph").mkdir(parents=True, exist_ok=True)
    (WORK / ".fastgraph/.fastgraphignore").write_text(
        "generated/*.min.js\n", encoding="utf-8"
    )
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    paths = _paths(db)
    assert "generated/bundle.min.js" not in paths
    assert "generated/source.js" in paths
    assert "src/main.js" in paths
    db.close()
    _rmtree(WORK)


def test_sensitive_files_ignored_by_default_template():
    """The auto-created template's sensitive-file defaults keep secret
    material out of the index (and out of content-search snippets)."""
    _make_project({
        "app.py": "x = 1\n",
        "secrets.json": '{"api_key": "sk-123"}\n',
        "config/service-account.json": '{"private_key": "p"}\n',
    })
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    paths = _paths(db)
    assert "app.py" in paths
    assert "secrets.json" not in paths
    assert "config/service-account.json" not in paths
    db.close()
    _rmtree(WORK)