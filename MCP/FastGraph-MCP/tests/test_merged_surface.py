"""The three merged tools: one call, and the response says which branch it took.

`read_code`, `call_graph` and `changes` each stand in for two or three advertised
tools that differed only by a target kind, a direction or a time base. The
underlying methods are untouched (they are still the internal API the rest of the
suite calls), so what is pinned here is the *routing*: the right branch for the
right argument, the branch named in the payload so a wrong guess is cheap to
correct, and no parameter that silently does nothing.

This matters most when FastGraph runs next to another code server: the merged tools
are what makes the two surfaces easy to tell apart without losing anything FastGraph
can do on its own.
"""
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

WORK = Path(__file__).resolve().parent / "work_merged"

MOD = (
    "class A:\n"
    "    def m1(self):\n"
    "        return 1\n"
    "\n"
    "def top():\n"
    "    return A().m1()\n"
)


@pytest.fixture
def box(monkeypatch):
    monkeypatch.setenv("FASTGRAPH_MEMORY", "1")
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    (WORK / "mod.py").write_text(MOD, encoding="utf-8")
    (WORK / "api.py").write_text("def handler():\n    return top()\n", encoding="utf-8")
    (WORK / "NOTES.md").write_text("# notes\nsecond line\n", encoding="utf-8")
    db = DB(WORK)
    tb = Toolbox(WORK, db, Indexer(WORK, db))
    tb.reindex()
    yield tb
    tb.close()
    db.close()
    shutil.rmtree(WORK, ignore_errors=True)


# ---------------------------------------------------------------- read_code


def test_read_code_reads_a_file_as_text(box):
    out = box.read_code("mod.py")
    assert out["mode"] == "lines" and out["found"] is True
    assert "def top():" in out["content"]


def test_read_code_window_and_structure_are_different_branches(box):
    window = box.read_code("mod.py", start_line=1, end_line=2)
    assert window["mode"] == "lines" and window["end_line"] == 2
    assert "def top()" not in window["content"]

    structure = box.read_code("mod.py", structure=True)
    assert structure["mode"] == "structure"
    assert {"A", "m1", "top"} <= {row["symbol"] for row in structure["symbols"]}


def test_read_code_of_a_symbol_returns_only_that_symbol(box):
    out = box.read_code("A.m1")
    assert out["mode"] == "symbol_body" and "def m1" in out["content"]
    assert "def top" not in out["content"]


def test_read_code_still_reaches_non_indexed_text(box):
    """Merging must not narrow what is readable: docs and configs came through
    `read_file` before, and `read_code` has to keep them."""
    out = box.read_code("NOTES.md")
    assert out["mode"] == "lines" and out["content"].startswith("# notes")


def test_read_code_of_nothing_says_why(box):
    out = box.read_code("no_such_file.py")
    assert out["found"] is False and out["mode"] == "symbol_body"


# ---------------------------------------------------------------- call_graph


def test_call_graph_directions(box):
    callers = box.call_graph("A.m1", direction="in")
    assert "callers" in callers and "callees" not in callers
    callees = box.call_graph("top", direction="out")
    assert "callees" in callees and "callers" not in callees


def test_call_graph_both_keeps_the_two_sides_apart(box):
    """Each side carries its own honesty metadata (`via` vs `evidence`, its own
    unresolved count and hint), so flattening them into one dict would put two
    different `hint` values in collision."""
    out = box.call_graph("A.m1")
    assert out["symbol"] == "A.m1"
    assert [c["qualified_name"] for c in out["in"]["callers"]] == ["top"]
    assert "callees" in out["out"]
    assert "hint" not in out or isinstance(out["hint"], str)


def test_call_graph_refuses_an_unknown_direction(box):
    out = box.call_graph("A.m1", direction="sideways")
    assert out["found"] is False and "in" in out["hint"] and "out" in out["hint"]


def test_call_graph_limit_applies_to_both_sides(box):
    assert box.call_graph("A.m1", direction="both", limit=1)["in"]["count"] <= 1


# ---------------------------------------------------------------- changes


def test_changes_picks_its_time_base_from_the_argument(box):
    git_view = box.changes()
    assert "since" not in git_view and "affected_callers" in git_view

    assert box.checkpoint("baseline")["ok"]
    topology = box.changes(since="baseline")
    assert topology["ok"] and topology["since"]["label"] == "baseline"
    assert "affected_callers" not in topology


def test_changes_baseline_view_is_refused_when_the_layer_is_off(box, monkeypatch):
    """`changes` is registered even with the memory layer parked, so its `since`
    branch has to say why it cannot answer rather than fall through to the git
    view (which would silently answer a different question)."""
    box.checkpoint("baseline")
    monkeypatch.setenv("FASTGRAPH_MEMORY", "0")
    out = box.changes(since="baseline")
    assert out["ok"] is False and "FASTGRAPH_MEMORY" in out["hint"]
    assert "affected_callers" in box.changes(base=None)  # the git branch still works


# ---------------------------------------------------------------- retired names

RETIRED = ("read_file", "symbol_body", "file_symbols", "find_callers", "find_callees",
           "changed_context", "what_changed")
PROSE_KEYS = {"hint", "error", "caveat", "reason", "note", "warning"}


def _prose(node):
    """Strings the model is meant to read as instructions, not data."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in PROSE_KEYS and isinstance(v, str):
                yield v
            else:
                yield from _prose(v)
    elif isinstance(node, list):
        for v in node:
            yield from _prose(v)


def test_no_response_hint_names_a_retired_tool(box, monkeypatch):
    """A hint pointing at a tool that is no longer registered is the same wrong-tool
    invitation the advertised-text rule blocks -- and the advertised-text rule did not
    catch this one. It took reading a live `changes` payload to notice its caveat still
    said "confirm with find_callers" long after that tool folded into `call_graph`:
    merging renames the things a client can call, and the guidance inside the answers
    has to follow."""
    payloads = [
        box.read_code("mod.py"),
        box.read_code("mod.py", structure=True, limit=1),
        box.read_code("A.m1"),
        box.call_graph("A.m1"),
        box.call_graph("A.m1", direction="in"),
        box.call_graph("nope_at_all", direction="out"),
        box.impact_analysis("A.m1"),
        box.symbol_info("A.m1"),
        box.file_deps("mod.py"),
        box.module_cycles(),
        box.project_overview(),
        box.changes(),
        box.checkpoint("pin-baseline"),
        box.changes(since="pin-baseline"),
        box.recall("file:mod.py"),
        box.what_changed("pin-baseline", to="no-such-label"),
        box.checkpoint(""),
        box.recall("nothing_matches_this_anymore"),
        box.read_code("no_such_file.py"),
        box.call_graph("A.m1", direction="sideways"),
        box.remember("symbol:mod.py#nope", "x"),
    ]
    # and the two refusals that only exist with the layer parked
    monkeypatch.setenv("FASTGRAPH_MEMORY", "0")
    payloads.append(box.recall("file:mod.py"))
    payloads.append(box.changes(since="pin-baseline"))
    monkeypatch.setenv("FASTGRAPH_MEMORY", "1")

    prose = "\n".join(text for payload in payloads for text in _prose(payload))
    assert prose, "no prose fields to check -- the payloads changed shape"
    hits = {name for name in RETIRED if re.search(rf"\b{name}\b", prose)}
    assert hits == set(), f"hints name withdrawn tools: {hits}"


def test_read_code_structure_limit_is_not_silently_dropped(box):
    """`file_symbols` had a `limit`; the merged tool has to keep it, or the merge
    removes a capability instead of a phrasing."""
    capped = box.read_code("mod.py", structure=True, limit=2)
    assert capped["count"] == 2 and capped["truncated"] is True


# ------------------------------------------------- through the MCP arg model


def test_merged_tools_survive_the_mcp_argument_model(tmp_path, monkeypatch):
    """Registering a tool generates a pydantic argument model; a default that does
    not survive that step reads as a required parameter to the client. The merges
    added enum-ish string parameters (`direction`) and booleans (`structure`), which
    is exactly where that breaks."""
    import asyncio
    import json

    from fastgraph.server import build_server

    monkeypatch.setenv("FASTGRAPH_MEMORY", "1")
    (tmp_path / "a.py").write_text("def f(x):\n    return x\n\ndef g():\n    return f(1)\n", encoding="utf-8")
    tm = build_server(tmp_path)._tool_manager

    async def call(name, args):
        return await tm.call_tool(name, args, context=None, convert_result=True)

    async def run():
        return {
            "read_lines": await call("read_code", {"target": "a.py"}),
            "read_struct": await call("read_code", {"target": "a.py", "structure": True}),
            "graph": await call("call_graph", {"symbol": "f"}),
            "graph_in": await call("call_graph", {"symbol": "f", "direction": "in", "depth": 1}),
            "changes": await call("changes", {}),
        }

    res = {k: json.loads(v.content[0].text) for k, v in asyncio.run(run()).items()}
    assert res["read_lines"]["mode"] == "lines" and "def g" in res["read_lines"]["content"]
    assert res["read_struct"]["mode"] == "structure"
    assert {"in", "out"} <= set(res["graph"])
    assert "callers" in res["graph_in"] and "out" not in res["graph_in"]
    assert "affected_callers" in res["changes"]
