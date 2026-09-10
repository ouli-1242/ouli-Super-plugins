"""Regression: class-level find_callers/impact_analysis must include member
callers (Java Spring-style field calls like ``jwtUtil.parseClaims(...)``).

Was: only edges targeting the class symbol id (``new JwtUtil()``) counted,
so constructor-injected usage was invisible at class level.
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

WORK = Path(__file__).resolve().parent / "work_java"


def _rmtree(path: Path):
    if not path.exists():
        return
    for p in path.rglob("*"):
        p.chmod(p.stat().st_mode | 0o200)
    shutil.rmtree(path, ignore_errors=True)


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_sample(root: Path):
    write(root / "util/BaseUtil.java", '''\
package util;

public class BaseUtil {
    public String secret() { return "s"; }
}
''')
    write(root / "util/JwtUtil.java", '''\
package util;

public class JwtUtil extends BaseUtil {
    public String parseClaims(String token) { return token; }
    public String generateToken(long uid, String name, int role) { return ""; }
}
''')
    write(root / "config/JwtInterceptor.java", '''\
package config;

import util.JwtUtil;

public class JwtInterceptor {
    private final JwtUtil jwtUtil;

    public JwtInterceptor(JwtUtil jwtUtil) { this.jwtUtil = jwtUtil; }

    public void softParseToken(HttpServletRequest request) {
        String token = "t";
        try {
            this.jwtUtil.parseClaims(token);
        } catch (Exception e) {
        }
    }
}
''')
    write(root / "service/UserService.java", '''\
package service;

import util.JwtUtil;

public class UserService {
    private final JwtUtil jwtUtil;

    public UserService(JwtUtil jwtUtil) { this.jwtUtil = jwtUtil; }

    public String register() {
        return jwtUtil.generateToken(1L, "alice", 1);
    }
}
''')
    write(root / "test/JwtUtilTest.java", '''\
package test;

import util.JwtUtil;

public class JwtUtilTest {
    public void setup() {
        JwtUtil jwtUtil = new JwtUtil();
        jwtUtil.parseClaims("x");
    }
}
''')


@pytest.fixture(scope="module")
def toolbox():
    _rmtree(WORK)
    WORK.mkdir(parents=True)
    build_sample(WORK)
    db = DB(WORK)
    indexer = Indexer(WORK, db)
    tools = Toolbox(WORK, db, indexer)
    indexer.refresh()
    yield tools
    db.close()
    _rmtree(WORK)


def test_class_callers_include_member_callers(toolbox):
    callers = toolbox.find_callers("JwtUtil")["callers"]
    qnames = {c["qualified_name"] for c in callers}
    assert "JwtInterceptor.softParseToken" in qnames
    assert "UserService.register" in qnames
    # direct construction (`new JwtUtil()`) must stay visible
    assert "JwtUtilTest.setup" in qnames


def test_class_impact_includes_member_callers(toolbox):
    imp = toolbox.impact_analysis("JwtUtil")
    high = {s["qualified_name"] for s in imp["impact"]["HIGH"]}
    assert "JwtInterceptor.softParseToken" in high
    assert "UserService.register" in high
    assert "JwtUtilTest.setup" in high


def test_method_level_callers_still_work(toolbox):
    callers = toolbox.find_callers("JwtUtil.parseClaims")["callers"]
    qnames = {c["qualified_name"] for c in callers}
    assert "JwtInterceptor.softParseToken" in qnames


def test_method_callers_exclude_sibling_members(toolbox):
    """Method-level folding must be exact: sibling-member callers (incl.
    auto-generated getter/setter style edges) are not callers of this method.
    Was: `target LIKE 'JwtUtil.%'` folded every member caller into each member."""
    callers = toolbox.find_callers("JwtUtil.generateToken")["callers"]
    qnames = {c["qualified_name"] for c in callers}
    assert "UserService.register" in qnames  # real caller of generateToken
    assert "JwtInterceptor.softParseToken" not in qnames, \
        f"sibling-member caller leaked into generateToken callers: {qnames}"
    callers2 = toolbox.find_callers("JwtUtil.parseClaims")["callers"]
    qnames2 = {c["qualified_name"] for c in callers2}
    assert "UserService.register" not in qnames2, \
        f"sibling-member caller leaked into parseClaims callers: {qnames2}"


def test_rename_impact_no_duplicate_sites(toolbox):
    """One reference site must appear once, even when the parser emitted both
    a bare and a dotted edge for the same `obj.method()` call."""
    imp = toolbox.rename_impact("JwtUtil.generateToken")
    sites = [(r["file"], r["line"]) for r in imp["references"]]
    assert len(sites) == len(set(sites)), f"duplicate reference sites: {sites}"


def test_code_search_extends_text(toolbox):
    """Java class declarations embed their bases in the signature, so plain
    keywords like `extends` are searchable via FTS."""
    hits = toolbox.code_search("extends")["results"]
    assert any(h["symbol"] == "JwtUtil" for h in hits), \
        f"'extends' text search missed JwtUtil: {[h['symbol'] for h in hits]}"


def test_unique_short_name_caller_not_polluted(tmp_path):
    """Collection calls like `rows.add(...)` must NOT resolve to the project's
    only `add` symbol via unique-name resolution (was: every `xxx.add()` bare
    edge landed on FootprintController.add, polluting find_callers)."""
    root = tmp_path / "repo"
    write(root / "ctrl/FootprintController.java", '''\
package ctrl;

public class FootprintController {
    public void add(String x) {}
}
''')
    write(root / "svc/ExportService.java", '''\
package svc;

public class ExportService {
    public void go() {
        java.util.List<String> rows = new java.util.ArrayList<>();
        rows.add("a");
    }
}
''')
    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    ix.refresh()
    try:
        callers = tb.find_callers("FootprintController.add")["callers"]
        qnames = {c["qualified_name"] for c in callers}
        assert "ExportService.go" not in qnames, \
            f"collection call resolved as caller of add: {qnames}"
    finally:
        db.close()


def test_unresolved_edge_rescued_by_text(toolbox):
    """Edges the parser could not resolve (target_id NULL, e.g. some
    ``userService.register`` calls) must still surface at class level."""
    row = toolbox.db.conn.execute(
        "SELECT id FROM symbols WHERE qualified_name = 'UserService.register'"
    ).fetchone()
    assert row is not None
    toolbox.db.conn.execute(
        "INSERT INTO relations (source_id, target, rtype, target_id, line) VALUES (?, ?, 'calls', NULL, 1)",
        (row[0], "jwtUtil.register"),
    )
    toolbox.db.conn.commit()
    try:
        callers = toolbox.find_callers("JwtUtil")["callers"]
        assert any(c["qualified_name"] == "UserService.register" for c in callers)
    finally:
        toolbox.db.conn.execute("DELETE FROM relations WHERE target = 'jwtUtil.register'")
        toolbox.db.conn.commit()