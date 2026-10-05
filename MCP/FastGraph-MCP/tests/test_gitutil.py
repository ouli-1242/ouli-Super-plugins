"""gitutil: changed_files must ignore the tool's own .fastgraph index dir."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.gitutil import changed_files  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(root: Path, *args: str):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_changed_files_ignores_fastgraph(repo):
    (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    sub = repo / "travel-backend" / ".fastgraph"
    sub.mkdir(parents=True)
    (sub / "index.sqlite").write_bytes(b"\x00" * 8)
    (repo / "travel-backend" / "b.py").write_text("def g():\n    return 2\n", encoding="utf-8")

    changes = changed_files(repo)
    assert "a.py" in changes
    assert "travel-backend/b.py" in changes
    assert not any(".fastgraph" in p for p in changes), f".fastgraph leaked: {changes}"


def test_changed_files_keeps_root_dotfiles_out(repo):
    (repo / ".env.example").write_text("KEY=value\n", encoding="utf-8")
    assert changed_files(repo) == {}