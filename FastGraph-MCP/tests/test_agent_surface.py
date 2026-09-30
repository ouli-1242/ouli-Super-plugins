"""The agent-facing text is an interface, so it is tested like one.

Everything here is injected into the model's context on every request: the tool
descriptions, the parameter descriptions and the server instructions. Free prose
drifts -- a description that contradicts its own default, a value list that no
longer matches what the code accepts, an empty result that reads as "nothing
depends on this" -- and none of it fails a functional test. These checks are the
rules the last audit had to be applied by hand.
"""
import inspect
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph import memory as mem
from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.server import build_server
from fastgraph.tools import Toolbox

WORK = Path(__file__).resolve().parent / "work_agentsurface"
SRV = Path(__file__).resolve().parent / "work_agentsurface_srv"
NOBODY = "definitely_not_in_this_repo_xyzzy"

# Trigger phrases: text that tells the model *when* to make the call. A description
# that only says what something is (a definition) leaves the routing to chance.
TRIGGERS = ("before", "after", "call it", "call this", "use for", "run it", "instead",
            "first choice", "check ", "prefer", "reach", "refuses", "resumes", "retry",
            "use it")
# routing counts as a trigger too: "For the full callee list use call_graph(...)"
# tells the model what to do next, which is the same job a "when" clause does
ROUTING = r"\buse[sd]? [a-z_]+\("
# How to read a result that can come back empty.
EMPTINESS = ("error", "not_found", "found", "pending_files", "truncated", "unresolved",
             "NOT", "count: 0", "never")


def _rmtree(path: Path):
    if not path.exists():
        return
    for p in path.rglob("*"):
        p.chmod(p.stat().st_mode | 0o200)
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def project(monkeypatch):
    monkeypatch.setenv("FASTGRAPH_MEMORY", "1")
    monkeypatch.setenv("FASTGRAPH_PROFILE", "full")
    _rmtree(WORK)
    WORK.mkdir(parents=True)
    (WORK / "app.py").write_text(
        "class Svc:\n    def run(self):\n        return helper()\n\n\ndef helper():\n    return 1\n",
        encoding="utf-8",
    )
    db = DB(WORK)
    tb = Toolbox(WORK, db, Indexer(WORK, db))
    tb.reindex()
    yield tb
    tb.close()
    db.close()
    _rmtree(WORK)


def _tools(dest=SRV):
    """Build a server over a throwaway directory: the surface is decided at build
    time from the environment, so this reads what a client would actually be sent.
    The directory is left for the OS to reclaim under pytest's tmp handling."""
    _rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    srv = build_server(dest)
    tools = list(srv._tool_manager.list_tools())
    text = srv.instructions or ""
    srv._fastgraph_tools.close()
    return tools, text


def _cost(tools):
    return sum(
        len(json.dumps({"name": t.name, "description": t.description,
                        "inputSchema": t.parameters}, ensure_ascii=False))
        for t in tools
    )


# ---------------------------------------------------------------- 1. budget

def test_advertised_surface_stays_inside_its_budget():
    """A ratchet, not a review: every feature quietly adds a sentence, and the only
    reason this server is 15 tools rather than 40 is that someone had to pay for each
    slot. The numbers are the current measured cost plus a little slack -- lower them
    when the surface shrinks, raise them only on purpose.

    17,650 is the price of the `forget` slot (~700 for a tool plus its parameters),
    paid for by trimming two sentences out of the instructions that were reassuring
    humans rather than routing the model.
    """
    tools, instructions = _tools()
    assert len(tools) == 15
    assert _cost(tools) <= 17_650, f"tool schemas grew to {_cost(tools)} chars"
    assert len(instructions) <= 3_000, f"instructions grew to {len(instructions)} chars"


def test_lean_profile_is_materially_cheaper():
    os.environ["FASTGRAPH_PROFILE"] = "lean"
    try:
        lean, _ = _tools()
    finally:
        os.environ["FASTGRAPH_PROFILE"] = "full"
    full, _ = _tools()  # same dir, rebuilt after the env flip
    assert len(lean) == 12
    assert _cost(lean) < _cost(full) * 0.8


# ---------------------------------------------------------------- 2. documented values

def test_documented_kind_values_are_the_ones_the_code_accepts():
    """A value list in prose and an enum in code drift apart one new kind at a time,
    and the model learns the difference from a rejected call."""
    tools, _ = _tools()
    by = {t.name: t for t in tools}
    for name in ("remember", "recall"):
        described = by[name].parameters["properties"]["kind"]["description"]
        for k in mem.NOTE_KINDS:
            assert k in described, f"{name}: kind {k!r} accepted but not documented"
        assert described.count("|") == len(mem.NOTE_KINDS) - 1, described
    assert "kind" in by["remember"].description or any(
        k in by["remember"].description for k in mem.NOTE_KINDS)


def test_documented_directions_are_the_ones_the_code_accepts(project):
    tools, _ = _tools()
    described = tools[[t.name for t in tools].index("call_graph")].parameters["properties"]["direction"]["description"]
    for way in ("in", "out", "both"):
        assert way in described
    # and the implementation agrees: the three documented values work, a fourth is refused
    assert project.call_graph("Svc.run", direction="in")["found"] is True
    assert "callees" in project.call_graph("Svc.run", direction="out")
    assert "in" in project.call_graph("Svc.run", direction="both")
    assert project.call_graph("Svc.run", direction="inward")["found"] is False


# ---------------------------------------------------------------- 3. triggers

def test_every_tool_says_when_to_use_it():
    """Definitions do not route; conditions do. Each description has to contain the
    phrase that fires the call ("run it BEFORE editing", "refuses while …, retry").
    """
    tools, _ = _tools()
    weak = [
        t.name for t in tools
        if not any(word in (t.description or "").lower() for word in TRIGGERS)
        and not re.search(ROUTING, t.description or "")
    ]
    assert weak == [], f"descriptions with no trigger condition: {weak}"


# ---------------------------------------------------------------- 4. defaults vs advice

def test_no_param_advises_a_range_its_own_default_breaks():
    """"Max results (keep small: 10-20)" sat on parameters defaulting to 40 and 50,
    so the model was told twice contradictory things about the same number. If a
    description quotes a numeric range, the default has to live inside it.
    """
    tools, _ = _tools()
    bad = []
    for t in tools:
        for pname, prop in (t.parameters or {}).get("properties", {}).items():
            default = prop.get("default")
            text = str(prop.get("description") or "")
            for lo, hi in re.findall(r"\b(\d+)-(\d+)\b", text):
                if isinstance(default, int) and not (int(lo) <= default <= int(hi)):
                    bad.append(f"{t.name}.{pname}: default {default} outside advised {lo}-{hi}")
    assert bad == [], bad


# ---------------------------------------------------------------- 5. empty results

@pytest.mark.parametrize(
    "call",
    [
        ("code_search", {"query": NOBODY}),
        ("module_cycles", {}),
        ("impact_analysis", {"symbol": NOBODY}),
        ("call_graph", {"symbol": NOBODY, "direction": "in"}),
    ],
    ids=["code_search", "module_cycles", "impact_analysis", "call_graph"],
)
def test_a_result_that_can_look_empty_explains_what_empty_means(project, call):
    """Query for something absent and these tools hand back a *plausible* answer:
    empty tiers, an empty list, `count: 0` -- and in `impact_analysis`'s case an
    `error: "not_found"` sitting next to two empty lists, which is the one a model
    reads as "nobody depends on this" and then deletes live code.

    The class is decided by calling the tools rather than by trusting the prose: any
    payload that still returns an empty collection on a query that matches nothing
    must be paired with a description that tells the model how to read it. Tools that
    answer a bad query with nothing but `found: false` (symbol_info, file_deps) are
    deliberately left out -- there the marker is the whole payload and cannot be missed.
    """
    name, args = call
    payload = getattr(project, name)(**args)
    empties = [k for k, v in payload.items()
               if isinstance(v, (list, dict)) and len(v) == 0 and k != "root"]
    assert empties, f"{name} no longer returns an empty collection: {sorted(payload)}"
    tools, _ = _tools()
    description = next(t.description for t in tools if t.name == name)
    assert any(marker in description for marker in EMPTINESS), (
        f"{name} returns empty {empties} on a no-match query, but its description "
        f"never tells the model how to read that: {description!r}"
    )


# ---------------------------------------------------------------- 6. required vs reachable

def test_the_schema_never_requires_what_the_code_defaults():
    """`recall` promised "Empty = every note" and its Toolbox method defaults
    `anchor=""`, but the wrapper forgot the default, so the schema marked it required:
    the whole-store read the description advertised was rejected by the client before
    the tool ever ran. Prose cannot open a path the schema closes, and the mismatch is
    invisible from either side alone -- hence both signatures, compared.
    """
    tools, _ = _tools()
    over_required, under_required = [], []
    for t in tools:
        impl = getattr(Toolbox, t.name, None)
        assert impl is not None, f"{t.name} has no Toolbox method to check against"
        sig = inspect.signature(impl)
        needs = {
            name for name, p in sig.parameters.items()
            if name != "self" and p.default is inspect._empty
            and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        }
        advertised = set((t.parameters or {}).get("required", []))
        over_required += [f"{t.name}.{n}" for n in sorted(advertised - needs)]
        under_required += [f"{t.name}.{n}" for n in sorted(needs - advertised)]
    assert over_required == [], (
        f"required in the schema but optional in the code, so the documented "
        f"omit-it behaviour is unreachable: {over_required}"
    )
    assert under_required == [], (
        f"required in the code but optional in the schema: {under_required}"
    )
