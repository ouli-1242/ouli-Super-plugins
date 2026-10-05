"""changed_context must scope to the changed lines, not the whole file.

`git status` reports which *file* changed, and changed_symbols turned that into
every symbol of the file: one comment line added inside `NewRouter` in chi
reported ~30 changed symbols (7.8k characters), so "what did I touch" answered
"all of it" and the blast radius was unreadable.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.gitutil import changed_ranges, changed_symbols
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

SRC = '''\
def alpha(x):
    return x + 1


def beta(x):
    return x + 2


def gamma(x):
    return x + 3
'''

MODIFIED = SRC.replace("    return x + 2", "    return x + 20  # touched")


def _git(root: Path, *args: str):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def test_ranges_parse_from_the_hunk_headers(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "m.py").write_text(SRC, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / "m.py").write_text(MODIFIED, encoding="utf-8")

    ranges = changed_ranges(tmp_path)
    assert list(ranges) == ["m.py"], ranges
    # `beta` spans lines 5-6; the edit is line 6 only
    assert ranges["m.py"] == [(6, 6)], ranges

    db = DB(tmp_path)
    Indexer(tmp_path, db).force_index()
    names = {s["name"] for s in changed_symbols(db, {"m.py": "modified"}, ranges)["modified"]}
    assert names == {"beta"}, names
    # no ranges (non-git / mtime fallback) keeps the whole-file behaviour
    assert len(changed_symbols(db, {"m.py": "modified"})["modified"]) == 4
    db.close()
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_changed_context_end_to_end(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "m.py").write_text(SRC, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    db = DB(tmp_path)
    ix = Indexer(tmp_path, db)
    tb = Toolbox(tmp_path, db, ix)
    ix.refresh()
    (tmp_path / "m.py").write_text(MODIFIED, encoding="utf-8")

    out = tb.changed_context()
    assert out["source"] == "git", out
    names = {s["symbol"] for s in out["changed_symbols"].get("modified", [])}
    assert names == {"beta"}, names
    db.close()
    shutil.rmtree(tmp_path, ignore_errors=True)
