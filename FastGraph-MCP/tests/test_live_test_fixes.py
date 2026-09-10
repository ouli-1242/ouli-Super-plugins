"""Regression tests for the defects found in the live MCP session test.

Each test reproduces one confirmed defect:

1. module-level calls were not recorded at all
   (so `register_adapter(...)`-style wiring was invisible and reported as dead)
2. `find_callers`/`impact_analysis` folded the owning class for *every* member,
   making each `Cls(...)` site a caller of all of Cls's methods
3. `code_search` OR-ed the query tokens over names, so a phrase query filled the
   limit with name hits and the content (comment/string) tier was never reached
4. `trace_path(from)` returned a flat set without depth/via
5. `file_symbols` truncated silently
6. a callable passed as a value (`map(self.handle, xs)`) did not count as usage
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox


@pytest.fixture()
def tmp_root(tmp_path):
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def _write(root: Path, files: dict[str, str]):
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def _build(root: Path, files: dict[str, str]):
    _write(root, files)
    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    ix.refresh()
    return db, ix, tb


# ---------------- 1. module-level calls ----------------

def test_module_level_call_is_recorded(tmp_root):
    db, _ix, tb = _build(tmp_root, {
        "reg.py": "def register(x):\n    return x\n",
        # bare module-level call (not an assignment): the case that used to be
        # dropped entirely
        "a.py": "from reg import register\n\n\nclass A:\n    pass\n\n\nregister(A())\n",
    })
    callers = tb.find_callers("register", depth=1, limit=10)
    unused = {u["symbol"] for u in tb.unused_symbols(limit=50)["unused"]}
    symbols = {s["symbol"] for s in tb.file_symbols("a.py")["symbols"]}
    db.close()

    assert callers["count"] >= 1, callers
    # the caller is the *module* of a.py (module symbols carry import-time code)
    assert "a" in {c["symbol"] for c in callers["callers"]}, callers["callers"]
    assert "a" in symbols, "every file must expose a module symbol"
    assert "register" not in unused, "a module-level caller must prevent a dead-code report"


def test_module_level_call_not_double_counted(tmp_root):
    """`app = FastAPI()` is carried by the module-level variable symbol; the
    module symbol must not record the same call a second time."""
    db, _ix, tb = _build(tmp_root, {
        "factory.py": "class App:\n    pass\n",
        "b.py": "from factory import App\n\napp = App()\n",
    })
    callers = tb.find_callers("App", depth=1, limit=10)["callers"]
    db.close()
    assert len(callers) == 1, callers


def test_module_symbol_does_not_absorb_call_edges(tmp_root):
    """A file stem must not attract call edges.

    Every file has a `module` symbol named after its stem, so a bare call whose
    name matches a file (`parse(...)` next to `parse.js`) must not be resolved
    to that module — modules are imported, not called. Without this the module
    showed up as a hot symbol with phantom callers.
    """
    db, _ix, tb = _build(tmp_root, {
        "parse.js": "function tokenize(s) { return s; }\n",
        "caller.js": "parse(payload);\n",
    })
    callers = tb.find_callers("parse", depth=1, limit=10)
    hot = {h["symbol"] for h in tb.hot_symbols(limit=20)["hot"]}
    db.close()
    assert callers["count"] == 0, callers
    assert "parse" not in hot, hot


def test_ts_module_level_call_is_recorded(tmp_root):
    """The same gap exists in JS/TS (`registerAdapter(App)` at module scope)."""
    db, _ix, tb = _build(tmp_root, {
        "reg.ts": "export function registerAdapter(x: unknown) {\n  return x;\n}\n",
        "app.ts": "import { registerAdapter } from './reg';\n\nclass App {}\n\nregisterAdapter(App);\n",
    })
    callers = tb.find_callers("registerAdapter", depth=1, limit=10)
    unused = {u["symbol"] for u in tb.unused_symbols(limit=50)["unused"]}
    db.close()
    assert callers["count"] >= 1, callers
    assert "app" in {c["symbol"] for c in callers["callers"]}, callers["callers"]
    assert "registerAdapter" not in unused


# ---------------- 2. member folding precision ----------------

_FOLD_FILES = {
    "svc.py": "class Svc:\n    def target(self):\n        return 1\n",
    "user.py": (
        "from svc import Svc\n"
        "\n"
        "def only_constructs():\n"
        "    s = Svc()\n"
        "    return s\n"
        "\n"
        "def really_calls(s):\n"
        "    return s.target()\n"
    ),
}


def test_method_callers_exclude_constructor_sites(tmp_root):
    db, _ix, tb = _build(tmp_root, _FOLD_FILES)
    names = {c["symbol"] for c in tb.find_callers("Svc.target", depth=1, limit=20)["callers"]}
    db.close()
    assert "really_calls" in names, names
    assert "only_constructs" not in names, names


def test_impact_analysis_matches_rename_impact_for_methods(tmp_root):
    db, _ix, tb = _build(tmp_root, _FOLD_FILES)
    impact = tb.impact_analysis("Svc.target", max_depth=1, limit=20)
    impacted = {i["name"] for i in impact["impact"]["HIGH"]}
    db.close()
    assert "really_calls" in impacted
    assert "only_constructs" not in impacted, impacted


def test_find_callers_order_is_stable(tmp_root):
    db, _ix, tb = _build(tmp_root, _FOLD_FILES)
    first = [c["qualified_name"] for c in tb.find_callers("Svc.target", depth=2, limit=20)["callers"]]
    second = [c["qualified_name"] for c in tb.find_callers("Svc.target", depth=2, limit=20)["callers"]]
    db.close()
    assert first == second, (first, second)


# ---------------- 3. multi-token search reaches the content tier ----------------

def test_phrase_query_reaches_content_tier(tmp_root):
    db, _ix, tb = _build(tmp_root, {
        "mod.py": "def alpha():\n    return 'CAPABILITY MODE handled here'\n",
        # a symbol matching only ONE of the two tokens: it must not be returned
        # (guards the SQL precedence bug where AND applied to the last OR arm)
        "other.py": "def mode_helper():\n    return 1\n",
    })
    hits = tb.code_search("CAPABILITY MODE", limit=5)["results"]
    single = tb.code_search("mode_helper", limit=5)["results"]
    db.close()
    # the string literal must surface: with OR-ed tokens the name hit on "mode"
    # filled the limit and _content_hits never ran
    assert any(h.get("match") == "content" for h in hits), hits
    # partial-token matches must be excluded from the name tier
    assert not any(h.get("symbol") == "mode_helper" for h in hits), hits
    # single-token search is unchanged
    assert any(h["symbol"] == "mode_helper" for h in single), single


def test_search_labels_the_hit_tier(tmp_root):
    """Doc/signature (FTS) hits must not be labelled `name`."""
    db, _ix, tb = _build(tmp_root, {
        "mod.py": '"""Capability mode resolution for widgets."""\n'
                  "def alpha():\n    return 1\n",
    })
    hits = tb.code_search("capability mode", limit=5)["results"]
    db.close()
    assert any(h.get("match") == "doc" for h in hits), hits


# ---------------- 4. trace_path is a leveled trace ----------------

def test_trace_path_entries_carry_depth_and_via(tmp_root):
    db, _ix, tb = _build(tmp_root, {
        "chain.py": (
            "def leaf():\n    return 1\n"
            "def mid():\n    return leaf()\n"
            "def top():\n    return mid()\n"
        ),
    })
    chain = tb.trace_path("leaf")["chain"]
    db.close()
    by_name = {c["symbol"]: c for c in chain}
    assert by_name["mid"]["depth"] == 1 and by_name["mid"]["via"] == "leaf"
    assert by_name["top"]["depth"] == 2 and by_name["top"]["via"] == "mid"


# ---------------- 5. explicit truncation ----------------

def test_file_symbols_reports_truncation(tmp_root):
    body = "".join(f"def f{i}():\n    return {i}\n\n" for i in range(6))
    db, _ix, tb = _build(tmp_root, {"many.py": body})
    capped = tb.file_symbols("many.py", limit=3)
    full = tb.file_symbols("many.py", limit=200)
    db.close()
    assert capped["truncated"] is True and capped["count"] == 3, capped
    assert full["truncated"] is False
    assert full["count"] == 7, full  # 6 functions + the module symbol


# ---------------- 7. cross-project root cache is bounded ----------------

def test_root_cache_is_bounded_and_releases_handles(tmp_path, monkeypatch):
    """Every cached `root=` holds an open SQLite connection.

    Observed live: after querying a foreign project, its .fastgraph/index.sqlite
    stayed locked by the server process, so the folder could not be deleted. The
    cache must therefore be bounded and release evicted handles.
    """
    import fastgraph.tools as tools_mod

    monkeypatch.setattr(tools_mod, "MAX_CACHED_ROOTS", 2)
    base = tmp_path / "base"
    base.mkdir()
    db = DB(base)
    ix = Indexer(base, db)
    tb = Toolbox(base, db, ix)

    foreign = []
    for i in range(4):
        p = tmp_path / f"foreign{i}"
        p.mkdir()
        (p / "m.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
        foreign.append(p)
    for p in foreign:
        tb.code_search("f", root=str(p))

    cached = len(tb._roots)
    evicted = [p for p in foreign if p.resolve() not in tb._roots]
    for p in evicted:
        # raises on Windows while the DB handle is still open
        shutil.rmtree(p)
    tb.close()
    db.close()

    assert cached <= 2, cached
    assert evicted, "LRU must have evicted something"


# ---------------- 6. callables passed as values count as usage ----------------

def test_callback_reference_counts_as_usage(tmp_root):
    db, _ix, tb = _build(tmp_root, {
        "cb.py": (
            "class P:\n"
            "    def run_all(self, items):\n"
            "        return list(map(self.handle, items))\n"
            "    def handle(self, x):\n"
            "        return x\n"
        ),
    })
    unused = {u["symbol"] for u in tb.unused_symbols(limit=50)["unused"]}
    db.close()
    assert "handle" not in unused, unused
