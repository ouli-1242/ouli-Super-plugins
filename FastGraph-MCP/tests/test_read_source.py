"""Reading text from the project (read_file / symbol_body).

read_file serves two jobs: it is the reading layer over the index, and it is the
way to see any other text file in the project (docs, configs, lockfiles) that the
index never carried. Both go through the same visibility rules, so it must never
be possible to read outside the project root, nor to read a file the project
marked as ignored (`.fastgraphignore`, dot paths) -- i.e. reading can never reach
further than indexing did.
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.config import MAX_FILE_SIZE
from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import MAX_READ_CHARS, Toolbox

FILES = {
    "mod.py": (
        "class A:\n"
        "    def m1(self):\n"
        "        return 1\n"
        "\n"
        "def top():\n"
        "    return A().m1()\n"
    ),
    "NOTES.md": "# notes\nsecond line\nthird line\n",
    "pyproject.toml": "[project]\nname = \"x\"\n",
}


@pytest.fixture()
def project(tmp_path):
    """A project at <tmp_path>/proj, so tests can place files *outside* it."""
    root = tmp_path / "proj"
    root.mkdir()
    for rel, content in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    db = DB(root)  # creates .fastgraph/ plus the ignore template
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    ix.refresh()
    yield root, tb
    db.close()
    shutil.rmtree(root, ignore_errors=True)


def test_read_file_returns_source_and_range(project):
    _, tb = project
    full = tb.read_file("mod.py")
    ranged = tb.read_file("mod.py", start_line=1, end_line=3)
    assert full["found"] is True and "class A:" in full["content"]
    assert full["indexed"] is True
    assert full["start_line"] == 1 and full["end_line"] == full["total_lines"]
    assert ranged["content"].strip().endswith("return 1")
    assert ranged["end_line"] == 3


def test_read_file_reads_files_the_index_does_not_carry(project):
    """Docs and configs are not source files, but a reader still needs them."""
    _, tb = project
    md = tb.read_file("NOTES.md")
    toml = tb.read_file("pyproject.toml")
    assert md["found"] is True and "second line" in md["content"]
    assert md["indexed"] is False
    assert toml["found"] is True and "name" in toml["content"]


def test_read_file_accepts_absolute_paths_inside_the_project(project):
    root, tb = project
    out = tb.read_file(str(root / "NOTES.md"))
    assert out["found"] is True
    assert out["file"] == "NOTES.md"


def test_read_file_refuses_paths_outside_the_project(project, tmp_path):
    _, tb = project
    outside = tmp_path / "outside" / "secret.txt"
    outside.parent.mkdir()
    outside.write_text("top secret\n", encoding="utf-8")

    escaped = tb.read_file("../outside/secret.txt")
    absolute = tb.read_file(str(outside))
    assert escaped["found"] is False
    assert absolute["found"] is False
    assert "outside the project root" in escaped["hint"]


def test_read_file_refuses_dot_and_ignored_paths(project):
    """The safety property: reading reaches no further than indexing does."""
    root, tb = project
    (root / ".env").write_text("API_KEY=abc\n", encoding="utf-8")
    (root / "keys.pem").write_text("-----BEGIN KEY-----\n", encoding="utf-8")
    ci = root / ".github" / "workflows" / "ci.yml"
    ci.parent.mkdir(parents=True)
    ci.write_text("on: push\n", encoding="utf-8")

    dot = tb.read_file(".env")
    pem = tb.read_file("keys.pem")
    nested = tb.read_file(".github/workflows/ci.yml")
    assert dot["found"] is False and "dot" in dot["hint"]
    # *.pem is ignored by the template shipped in .fastgraphignore
    assert pem["found"] is False and "fastgraphignore" in pem["hint"]
    assert nested["found"] is False


def test_read_file_refuses_binary_files(project):
    root, tb = project
    (root / "blob.bin").write_bytes(b"\x00\x01\x02binary\x00\xff")
    out = tb.read_file("blob.bin")
    assert out["found"] is False and "binary" in out["hint"]


def test_read_file_truncates_oversized_content(project):
    root, tb = project
    (root / "big.txt").write_text("x" * (MAX_FILE_SIZE - 1), encoding="utf-8")
    out = tb.read_file("big.txt")
    assert out["found"] is True and out["truncated"] is True
    assert len(out["content"]) == MAX_READ_CHARS


def test_read_file_refuses_files_over_the_size_limit(project):
    root, tb = project
    (root / "huge.log").write_bytes(b"a" * (MAX_FILE_SIZE + 1))
    out = tb.read_file("huge.log")
    assert out["found"] is False and "limit" in out["hint"]


def test_read_file_reports_a_missing_path(project):
    _, tb = project
    out = tb.read_file("nope/missing.txt")
    assert out["found"] is False


def test_read_file_default_window_is_capped(project):
    """A whole-file read must not dump ~10k tokens of context in one call.

    Measured on axios: read_file('README.md') returned 2871 lines. The default
    window is 400 lines and says so via `truncated`; an explicit range still
    reads as far as the caller asks.
    """
    root, tb = project
    (root / "long.txt").write_text(
        "\n".join(f"line {i}" for i in range(600)), encoding="utf-8"
    )
    default = tb.read_file("long.txt")
    explicit = tb.read_file("long.txt", end_line=600)
    assert default["end_line"] == 400
    assert default["total_lines"] == 600
    assert default["truncated"] is True
    assert explicit["end_line"] == 600
    assert explicit["truncated"] is False
    assert "line 599" in explicit["content"]


def test_symbol_body_returns_only_the_symbol(project):
    _, tb = project
    body = tb.symbol_body("A.m1")
    absent = tb.symbol_body("does_not_exist")
    assert body["found"] is True
    assert "def m1" in body["content"]
    assert "def top" not in body["content"]
    assert body["file"] == "mod.py"
    assert absent["found"] is False
