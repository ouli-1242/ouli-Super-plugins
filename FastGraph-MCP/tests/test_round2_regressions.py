"""Regression tests for Round-2 real-scenario findings (REAL_SCENARIO_TEST_REPORT.md).

Each test reproduces one confirmed defect; the fix must make it pass.
Round 2 defects: A1-A15 (see the report for details).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox
from fastgraph import gitutil


def _build(root: Path, files: dict[str, str]) -> tuple[DB, Indexer, Toolbox]:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    ix.refresh()
    return db, ix, tb


@pytest.fixture()
def tmp_root(tmp_path):
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


# ---------------- A1: JS `this.x` must not duplicate edges ----------------

def test_js_this_call_no_duplicate_reference(tmp_root):
    files = {
        "app.js": (
            "Page({\n"
            "  send() {\n"
            "    this.persist();\n"
            "  },\n"
            "  persist() {}\n"
            "})\n"
        ),
    }
    db, ix, tb = _build(tmp_root, files)
    imp = tb.rename_impact("persist")
    # one call site (`this.persist()`) must produce ONE reference, not two
    assert imp["reference_count"] == 1, imp
    r = imp["references"][0]
    assert r["via_text"] == "persist", r  # not "this.persist"
    db.close()


# ---------------- A2: changed_context must cap changed_symbols ----------------

def test_changed_context_caps_symbols(tmp_root):
    files = {f"m{i}.py": f"def f{i}():\n    return {i}\n" for i in range(30)}
    db, ix, tb = _build(tmp_root, files)
    # no git repo -> empty; the cap logic is exercised through the git path,
    # so simulate by checking the default limit is applied to the output shape.
    # Absolute check lives in test_changed_context_git_symbols_capped below.
    out = tb.changed_context(limit=5)
    assert "changed_symbols" in out and "changed_files" in out
    db.close()


def test_changed_context_git_symbols_capped(tmp_root):
    repo = tmp_root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    for i in range(30):
        (repo / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    # make all 30 files untracked (simulate fresh checkout w/ many added files)
    for i in range(30):
        p = repo / f"m{i}.py"
        (repo / f"m{i}.py").write_text(f"def f{i}():\n    return {i + 100}\n", encoding="utf-8")
        _git(repo, "rm", "-q", "--cached", str(p.relative_to(repo)))
    db = DB(repo)
    ix = Indexer(repo, db)
    tb = Toolbox(repo, db, ix)
    ix.refresh()
    out = tb.changed_context(limit=5)
    assert out["truncated"] is True, out
    total = sum(len(v) for v in out["changed_symbols"].values())
    assert total <= 10, out  # 5 per status, both statuses
    db.close()


# ---------------- A3: Python chained calls must not pollute callees ----------------

def test_python_chained_call_callees_clean(tmp_root):
    files = {
        "db.py": "class Session:\n    pass\nclass ChatHistory:\n    pass\n",
        "mod.py": (
            "from db import Session, ChatHistory\n"
            "def go(db):\n"
            "    return db.query(ChatHistory).filter(ChatHistory.id > 1).order_by(ChatHistory.id.desc()).all()\n"
        ),
    }
    db, ix, tb = _build(tmp_root, files)
    info = tb.symbol_info("go")
    callees = [(c["target"], c["line"]) for c in info["matches"][0]["callees"]]
    # no multi-line expression garbage, no parens, no full chain text
    for target, _ in callees:
        assert "\n" not in target, target
        assert "(" not in target, target
    names = set(t for t, _ in callees)
    assert {"query", "filter", "order_by", "all"} <= names, names
    db.close()


# ---------------- A4: multi-symbol `from x import a, b, c` resolves ----------------

def test_multi_symbol_import_resolves(tmp_root):
    files = {
        "pkg/__init__.py": "",
        "pkg/auth.py": "def login(): pass\n",
        "pkg/profile.py": "def get(): pass\n",
        "main.py": "from pkg import auth, profile\n",
    }
    db, ix, tb = _build(tmp_root, files)
    deps = tb.file_deps("main.py")
    resolved = {f for imp in deps["imports"] for f in imp["resolves_to"]}
    assert any(x.endswith("pkg/auth.py") for x in resolved), resolved
    assert any(x.endswith("pkg/profile.py") for x in resolved), resolved
    db.close()


# ---------------- A5+A11: gitutil utf-8 + quotepath on Chinese paths ----------------

def test_changed_context_chinese_path_and_filename(tmp_root):
    repo = tmp_root / "中文项目"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (repo / "中文文件.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    # modify both files (one has a Chinese filename)
    (repo / "a.py").write_text("def alpha():\n    return 10\n", encoding="utf-8")
    (repo / "中文文件.py").write_text("def beta():\n    return 20\n", encoding="utf-8")

    assert gitutil.git_root(repo) is not None, "git_root must survive Chinese path"
    changes = gitutil.changed_files(repo)
    assert "a.py" in changes, changes
    assert "中文文件.py" in changes, changes

    db = DB(repo)
    ix = Indexer(repo, db)
    tb = Toolbox(repo, db, ix)
    ix.refresh()
    out = tb.changed_context()
    assert "a.py" in out["changed_files"], out
    assert "中文文件.py" in out["changed_files"], out
    assert "alpha" in {s["symbol"] for s in out["changed_symbols"].get("modified", [])}, out
    db.close()


# ---------------- A6: FastAPI Depends(x) reference visible ----------------

def test_fastapi_depends_reference_visible(tmp_root):
    files = {
        "auth.py": (
            "def get_current_user():\n    return None\n"
            "def get_db():\n    return None\n"
        ),
        "api.py": (
            "from auth import get_current_user, get_db\n"
            "def endpoint():\n"
            "    user = Depends(get_current_user)\n"
            "    db = Depends(get_db)\n"
            "    return user\n"
        ),
    }
    db, ix, tb = _build(tmp_root, files)
    imp = tb.rename_impact("get_current_user")
    via = [r.get("via_text", r.get("via", "")) for r in imp["references"]]
    assert "get_current_user" in via, (imp["references"], via)
    ref_types = {r["rtype"] for r in imp["references"]}
    assert "references" in ref_types, ref_types
    # call graph stays clean: find_callers must NOT list Depends sites
    callers = tb.find_callers("get_current_user")
    assert callers["count"] == 0, callers
    db.close()


# ---------------- A7: three-part qualified name ----------------

def test_three_part_qualified_name(tmp_root):
    files = {
        "orchestrator.py": (
            "class Orchestrator:\n"
            "    def _extract_topic(self, m):\n"
            "        return m\n"
        ),
    }
    db, ix, tb = _build(tmp_root, files)
    info = tb.symbol_info("orchestrator.Orchestrator._extract_topic")
    assert info["found"] is True, info
    assert info["matches"][0]["qualified_name"] == "Orchestrator._extract_topic", info
    db.close()


# ---------------- A8: Java import case-insensitive resolution ----------------

def test_java_import_case_insensitive(tmp_root):
    files = {
        "com/travel/common/RateLimiter.java": "public class RateLimiter {}\n",
        "com/travel/controller/AiController.java": (
            "package com.travel.controller;\n"
            "import com.travel.common.RateLimiter;\n"
            "class AiController {}\n"
        ),
    }
    db, ix, tb = _build(tmp_root, files)
    deps = tb.file_deps("com/travel/controller/AiController.java")
    resolved = {f for imp in deps["imports"] for f in imp["resolves_to"]}
    assert any(x.endswith("RateLimiter.java") for x in resolved), resolved
    db.close()


# ---------------- A9: Java `new X()` constructor reference ----------------

def test_java_new_constructor_reference(tmp_root):
    files = {
        "BizException.java": "public class BizException extends RuntimeException {}\n",
        "Service.java": (
            "class Service {\n"
            "  void go() {\n"
            "    throw new BizException();\n"
            "  }\n"
            "}\n"
        ),
    }
    db, ix, tb = _build(tmp_root, files)
    imp = tb.rename_impact("BizException")
    via = [r.get("via_text", r.get("via", "")) for r in imp["references"]]
    assert "BizException" in via, (imp["references"], via)
    # the constructor reference must *resolve* to the class so impact_analysis
    # counts the throwing site as a HIGH caller (was: ambiguous constructor
    # names left it unresolved -> total_affected=0 despite 1 usage).
    impact = tb.impact_analysis("BizException")
    assert impact["total_affected"] >= 1, impact
    assert any(i["name"] == "go" for i in impact["impact"]["HIGH"]), impact
    db.close()


# ---------------- A10: activate_project empty root rejected ----------------

def test_activate_project_empty_root_rejected(tmp_root):
    files = {"a.py": "def f():\n    return 1\n"}
    db, ix, tb = _build(tmp_root, files)
    out = tb.activate_project("")
    assert out["ok"] is False, out
    assert "non-empty" in out.get("error", ""), out
    db.close()


# ---------------- A13: oversized query must not throw ----------------

def test_oversized_query_no_crash(tmp_root):
    files = {"a.py": "def alpha():\n    return 1\n"}
    db, ix, tb = _build(tmp_root, files)
    out = tb.code_search("x" * 5000)
    assert "results" in out, out  # success, not an error
    db.close()


# ---------------- A14: kind filter excludes imports ----------------

def test_kind_filter_excludes_imports(tmp_root):
    files = {
        "mod.py": "def alpha():\n    return 1\n",
        "main.py": "from mod import alpha\n",
    }
    db, ix, tb = _build(tmp_root, files)
    out = tb.code_search("alpha", kind="class")
    for r in out["results"]:
        assert r["kind"] != "import", r
    db.close()


# ---------------- A15: FTS doc search works ----------------

def test_fts_doc_search_works(tmp_root):
    files = {
        "mod.py": '"""UniquePhraseXyz only appears in this doc."""\n'
                  "def f():\n"
                  "    return 1\n",
    }
    db, ix, tb = _build(tmp_root, files)
    hits = tb.code_search("UniquePhraseXyz")
    assert any(
        h.get("symbol") == "mod" or h.get("match") == "doc"
        for h in hits["results"]
    ), hits
    db.close()


# ---------------- return-surface design (round 3) ----------------

def test_steady_state_output_omits_refresh_and_ms(tmp_root):
    """After the initial index, tool output must not carry per-call telemetry
    (refresh/ms) — it is pure noise for the agent."""
    files = {"a.py": "def alpha():\n    return 1\n"}
    db, ix, tb = _build(tmp_root, files)
    tb.code_search("alpha")  # first call does the full index
    out = tb.code_search("alpha")
    assert "ms" not in out, out
    assert "refresh" not in out, out
    assert "root" in out, out
    db.close()


def test_refresh_present_when_parse_happens(tmp_root):
    """The gated refresh block must appear when a call actually re-parses."""
    files = {"a.py": "def alpha():\n    return 1\n"}
    db, ix, tb = _build(tmp_root, files)
    tb.code_search("alpha")
    (tmp_root / "a.py").write_text("def alpha():\n    return 2\n", encoding="utf-8")
    out = tb.code_search("alpha")
    assert "refresh" in out, out
    assert out["refresh"]["parsed"] >= 1, out
    db.close()


def test_rename_impact_reference_keys_consistent(tmp_root):
    """Every reference row must use the same key (via_text), not a mix of
    via_text / via."""
    files = {
        "mod.py": "def alpha():\n    return 1\n",
        "main.py": "from mod import alpha\n\ndef go():\n    return alpha()\n",
    }
    db, ix, tb = _build(tmp_root, files)
    imp = tb.rename_impact("alpha")
    for r in imp["references"]:
        assert "via_text" in r, r
        assert "via" not in r, r
    db.close()


def test_file_deps_splits_internal_and_external(tmp_root):
    files = {
        "pkg/thing.py": "def f():\n    return 1\n",
        "main.py": "import os\nfrom pkg.thing import f\n",
    }
    db, ix, tb = _build(tmp_root, files)
    deps = tb.file_deps("main.py")
    assert all(i["resolves_to"] for i in deps["imports"]), deps["imports"]
    assert any("os" in i["text"] for i in deps["external_imports"]), deps["external_imports"]
    db.close()


def test_fastgraph_debug_env_restores_refresh(monkeypatch, tmp_root):
    """FASTGRAPH_DEBUG=1 must restore per-call refresh stats (perf diagnosis)."""
    files = {"a.py": "def alpha():\n    return 1\n"}
    # steady state: no refresh
    db, ix, tb = _build(tmp_root, files)
    tb.code_search("alpha")
    assert "refresh" not in tb.code_search("alpha")
    db.close()
    # debug mode: refresh always present
    monkeypatch.setenv("FASTGRAPH_DEBUG", "1")
    db2, ix2, tb2 = _build(tmp_root, files)
    tb2.code_search("alpha")
    out = tb2.code_search("alpha")
    assert "refresh" in out, out
    assert "refresh_ms" in out["refresh"], out
    db2.close()