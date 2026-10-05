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
import re
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

# The read-only surface with the memory layer parked: 11 tools. Deliberately
# small -- every definition is re-sent with each request, so a tool only earns a
# slot by answering something an LSP-backed tool cannot answer cheaply. Seven
# earlier tools were folded into three (`read_code`, `call_graph`, `changes`)
# because they differed only by a direction, a target kind or a time base, which
# is a choice the caller has to make before it knows what it is looking for.
ADVERTISED = {
    "activate_project",
    "reindex",
    "project_overview",
    "code_search",
    "symbol_info",
    "read_code",
    "call_graph",
    "impact_analysis",
    "file_deps",
    "module_cycles",
    "changes",
}


def _surface(tmp_path):
    # tmp_path is owned (and reclaimed) by pytest: the server keeps its sqlite
    # connection open, so the test must not try to delete the directory itself
    work = tmp_path / "proj"
    work.mkdir(parents=True, exist_ok=True)
    return build_server(work)


def test_advertised_surface_is_exactly_the_intended_set(tmp_path, monkeypatch):
    """Pinning the set makes an accidental re-exposure fail loudly.

    The tools held back (trace_path, rename_impact, type_hierarchy,
    unused_symbols, hot_symbols, file_metrics, get_status) remain implemented and
    tested as an internal API -- see the UNEXPOSED note in fastgraph.server.

    The memory layer parks itself out here: these pins are about the read-only
    core, and the memory surface is pinned in test_memory.py.
    """
    monkeypatch.setenv("FASTGRAPH_MEMORY", "0")
    names = {t.name for t in _surface(tmp_path)._tool_manager.list_tools()}
    assert names == ADVERTISED, sorted(names ^ ADVERTISED)
    assert len(names) == 11


def test_all_tools_advertise_readonly_annotations(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTGRAPH_MEMORY", "0")
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


# The locate/read tools `FASTGRAPH_PROFILE=lean` withholds: reading a file, listing a
# file's symbols and finding a definition are covered by a client's own tools or an
# LSP-backed server, so a project running both does not pay their schema twice.
# Withholding them is opt-in precisely because FastGraph also runs alone.
LEAN_WITHHELD = {"code_search", "symbol_info", "read_code"}
MEMORY_TOOLS = {"remember", "recall", "forget", "checkpoint"}


def _names(server):
    return {t.name for t in server._tool_manager.list_tools()}


def test_lean_profile_advertises_only_the_differentiated_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTGRAPH_MEMORY", "0")
    monkeypatch.setenv("FASTGRAPH_PROFILE", "lean")
    assert _names(_surface(tmp_path)) == ADVERTISED - LEAN_WITHHELD

    monkeypatch.setenv("FASTGRAPH_MEMORY", "1")
    assert _names(_surface(tmp_path)) == (ADVERTISED - LEAN_WITHHELD) | MEMORY_TOOLS


@pytest.mark.parametrize("nav", ["full", "lean"])
@pytest.mark.parametrize("memory", ["1", "0"])
def test_instructions_stay_one_readable_list_whatever_is_registered(tmp_path, monkeypatch, nav, memory):
    """The guidance is assembled from per-profile blocks, so the seams are the part
    that rots: a block that forgot its trailing newline fuses two sentences into
    "...source files.Wrong folder...", and a duplicated footer reads as two
    contradictory conventions. Both are invisible to a diff and visible to the model.
    """
    from fastgraph.server import surface_instructions

    monkeypatch.setenv("FASTGRAPH_PROFILE", nav)
    monkeypatch.setenv("FASTGRAPH_MEMORY", memory)
    text = _surface(tmp_path).instructions
    assert text == surface_instructions(nav != "lean", memory != "0")
    assert re.search(r"[a-z]\.[A-Z]", text) is None, "sentences glued at a block seam"
    assert text.count("1-based") == 1
    assert text.rstrip().endswith("not file dumps."), text[-60:]
    assert ("source text comes only from read_code" in text) is (nav != "lean")


@pytest.mark.parametrize("nav", ["full", "lean"])
@pytest.mark.parametrize("memory", ["1", "0"])
def test_nothing_advertises_a_tool_this_process_did_not_register(tmp_path, monkeypatch, nav, memory):
    """Guidance naming an unregistered tool is a wrong-tool invitation.

    A tool reference in this server's prose is always written `name(...)` or
    `name=...`, so that is what is searched -- the call syntax is what separates
    "use changes(base=...)" from the English word in "changed files".
    """
    monkeypatch.setenv("FASTGRAPH_PROFILE", nav)
    monkeypatch.setenv("FASTGRAPH_MEMORY", memory)
    server = _surface(tmp_path)
    registered = _names(server)
    absent = (ADVERTISED | MEMORY_TOOLS) - registered
    texts = [server.instructions or ""]
    pm = server._prompt_manager
    texts.append(str(pm.get_prompt("fastgraph-workflow").fn()))
    for t in server._tool_manager.list_tools():
        texts.append(t.description or "")
        for prop in (t.parameters or {}).get("properties", {}).values():
            texts.append(str(prop.get("description") or ""))
    named = {n for n in absent for text in texts if re.search(rf"\b{n}[(_=]", text)}
    assert named == set(), f"{sorted(named)} named but not registered (nav={nav}, memory={memory})"
