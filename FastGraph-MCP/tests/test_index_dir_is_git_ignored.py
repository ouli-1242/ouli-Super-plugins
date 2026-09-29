"""The index dir is created in somebody else's repository; keep it out of their
`git status` without editing their .gitignore (`.fastgraph/.gitignore` = `*`).
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer

WORK = Path(__file__).resolve().parent / "work_gitignore"


def _rmtree(path: Path):
    if not path.exists():
        return
    for p in path.rglob("*"):
        try:
            p.chmod(p.stat().st_mode | 0o200)
        except OSError:
            pass
    shutil.rmtree(path, ignore_errors=True)


def test_index_dir_does_not_appear_in_git_status():
    if shutil.which("git") is None:
        return  # no git on this box: nothing to check, nothing broken
    _rmtree(WORK)
    WORK.mkdir(parents=True)
    (WORK / "src").mkdir()
    (WORK / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=WORK, check=True)
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    assert (WORK / ".fastgraph" / ".gitignore").read_text(encoding="utf-8") == "*\n"
    out = subprocess.run(["git", "status", "--porcelain"], cwd=WORK,
                         capture_output=True, text=True).stdout
    db.close()
    assert ".fastgraph" not in out, out
    assert "src" in out, out  # git saw the untracked source; the probe is not vacuous
    _rmtree(WORK)
