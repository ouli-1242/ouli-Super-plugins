"""Symbol name paths, and the advertised tool surface.

FastGraph accepts two spellings of a symbol: dotted (``Class.method``, the form
stored in the index) and slash-separated (``Class/method``, optional leading
``/`` and trailing ``[i]`` overload index). Results for nested symbols echo the
slash form back as ``name_path``, so an identifier taken from one tool can be
pasted straight into the next.

This module also pins the advertised surface, the read-only annotations every
tool carries, and the requirement that nothing FastGraph shows the model refers
to another server.
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.graph import name_path, normalize_symbol_query
from fastgraph.index import Indexer
from fastgraph.server import build_server
from fastgraph.tools import Toolbox

FILES = {
    "svc.py": (
        "class A:\n"
        "    def m2(self):\n"
        "        return 1\n"
        "    def m1(self):\n"
        "        return self.m2()\n"
    ),
}


def _build(root: Path, files: dict[str, str]):
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    ix.refresh()
    return db, tb


@pytest.fixture()
def tmp_root(tmp_path):
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


# ---------------- name-path normalization ----------------

def test_normalize_symbol_query_accepts_both_spellings():
    assert normalize_symbol_query("A/m1") == "A.m1"
    assert normalize_symbol_query("/A/m1") == "A.m1"
    assert normalize_symbol_query("A/m1[1]") == "A.m1"
    assert normalize_symbol_query("A.m1") == "A.m1"
    assert normalize_symbol_query("top") == "top"
    assert normalize_symbol_query("") == ""


def test_name_path_conversion():
    assert name_path("A.m1") == "A/m1"
    assert name_path("NS.Cls.m") == "NS/Cls/m"
    assert name_path("top") == "top"


# ---------------- symbol lookup accepts both forms ----------------

def test_symbol_lookup_accepts_name_path(tmp_root):
    db, tb = _build(tmp_root, FILES)
    dotted = tb.symbol_info("A.m1")
    slashed = tb.symbol_info("A/m1")
    absolute = tb.symbol_info("/A/m1")
    overload = tb.symbol_info("A/m1[0]")
    db.close()
    assert dotted["found"] and slashed["found"] and absolute["found"] and overload["found"]
    assert [m["qualified_name"] for m in slashed["matches"]] == [
        m["qualified_name"] for m in dotted["matches"]
    ]


def test_graph_tools_accept_name_path(tmp_root):
    db, tb = _build(tmp_root, FILES)
    assert tb.find_callers("A/m2")["found"] is True
    assert tb.impact_analysis("A/m2")["found"] is True
    assert tb.rename_impact("A/m2")["definition_count"] >= 1
    assert tb.trace_path("A/m1")["from"] == "A/m1"
    db.close()


# ---------------- results emit a reusable name_path ----------------

def test_nested_brief_exposes_name_path(tmp_root):
    db, tb = _build(tmp_root, FILES)
    out = tb.find_callees("A.m1")
    db.close()
    nested = [c for c in out["callees"] if c.get("qualified_name") == "A.m2"]
    assert nested, out["callees"]
    assert nested[0].get("name_path") == "A/m2"
    # top-level symbols must not carry a redundant name_path key
    assert "name_path" not in tb._brief({"name": "top", "qualified_name": "top"})


# ---------------- advertised surface ----------------

# The whole surface: 13 tools. Deliberately small -- every definition is re-sent
# with each request, so a tool only earns a slot by answering something an
# LSP-backed tool cannot answer cheaply.
ADVERTISED = {
    "activate_project",
    "project_overview",
    "code_search",
    "symbol_info",
    "file_symbols",
    "read_file",
    "symbol_body",
    "find_callers",
    "find_callees",
    "impact_analysis",
    "file_deps",
    "module_cycles",
    "changed_context",
}


def _surface(tmp_path):
    # tmp_path is owned (and reclaimed) by pytest: the server keeps its sqlite
    # connection open, so the test must not try to delete the directory itself
    work = tmp_path / "proj"
    work.mkdir(parents=True, exist_ok=True)
    return build_server(work)


def test_advertised_surface_is_exactly_the_intended_set(tmp_path):
    """Pinning the set makes an accidental re-exposure fail loudly.

    The tools held back (trace_path, rename_impact, type_hierarchy,
    unused_symbols, hot_symbols, file_metrics, get_status) remain implemented and
    tested as an internal API -- see the UNEXPOSED note in fastgraph.server.
    """
    names = {t.name for t in _surface(tmp_path)._tool_manager.list_tools()}
    assert names == ADVERTISED, sorted(names ^ ADVERTISED)
    assert len(names) == 13


def test_all_tools_advertise_readonly_annotations(tmp_path):
    tools = _surface(tmp_path)._tool_manager.list_tools()
    for t in tools:
        a = t.annotations
        assert a is not None, t.name
        assert a.read_only_hint is True, t.name
        assert a.destructive_hint is False, t.name
        assert a.idempotent_hint is True, t.name
        assert t.title, t.name


def test_advertised_content_does_not_name_another_server(tmp_path):
    """FastGraph must read as a standalone tool.

    Nothing it shows the model may refer to another code server, so the surface
    stays correct whether or not one runs next to it (and so the model never has
    to reason about a server it may not have).
    """
    server = _surface(tmp_path)
    texts = [server.instructions or ""]
    texts += [
        f"{t.name}: {t.description or ''}" for t in server._tool_manager.list_tools()
    ]
    offenders = [t for t in texts if "serena" in t.lower()]
    assert offenders == [], offenders
    assert "1-based" in (server.instructions or "")
