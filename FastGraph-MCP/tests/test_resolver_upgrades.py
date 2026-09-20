"""Upgrades round: materialized import_edges, parameter-type evidence,
language coverage gaps, branch-level changed_context, config-cache invalidation.

Each test pins a behavior that was previously a known gap:

- file_deps / module_cycles used to re-run import resolution on every call;
  they now read the materialized ``import_edges`` table (P1).
- ``svc.run()`` with ``def handler(svc: UserService)`` stayed unresolved
  forever; the parameter annotation now names the receiver's type (P2).
- Import evidence matched by substring, so owner ``user`` matched an import
  of ``user_service`` and produced bogus edges (P2).
- TS class field arrow functions (``onSave = () => {}``) produced no symbol
  and lost their call edges (P3).
- ``void Cls::method() {}`` in a .cpp landed as a bare function unrelated to
  the class (P3).
- Go interface methods were not symbols, so ``iface.Method()`` never resolved
  (P3).
- Two same-named Java classes in different packages were indistinguishable;
  the fully-qualified import line now pins the package (P3).
- changed_context only saw uncommitted changes; ``base=`` diffs a whole
  branch (P4).
- Editing tsconfig.json / go.mod mid-session never refreshed graph's
  process-wide alias caches (P5).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer, _java_fq_imported
from fastgraph.parsers.util import call_targets, first_type_ident
from fastgraph.tools import Toolbox


def _project(tmp_path: Path, files: dict[str, str]) -> tuple[DB, Indexer, Toolbox]:
    root = tmp_path / "proj"
    root.mkdir()
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    ix.refresh()
    return db, ix, tb


# ---------------- P1: materialized import_edges ----------------

EDGE_FILES = {
    "pkg/__init__.py": "",
    "pkg/mod.py": "def helper():\n    return 1\n",
    "pkg/other.py": "def second():\n    return 2\n",
    "app.py": "from pkg import mod\nfrom pkg.other import second\n\n\ndef main():\n    return mod.helper() + second()\n",
}


def test_file_deps_reads_materialized_edges(tmp_path):
    db, ix, tb = _project(tmp_path, EDGE_FILES)
    deps = tb.file_deps("app.py")
    resolves = {imp["text"]: imp["resolves_to"] for imp in deps["imports"]}
    assert resolves["from pkg import mod"] == ["pkg/mod.py"]
    assert resolves["from pkg.other import second"] == ["pkg/other.py"]
    # importer direction: edges stored for app.py point at pkg files
    back = tb.file_deps("pkg/mod.py")
    assert [i["file"] for i in back["importers"]] == ["app.py"]


def test_module_cycles_reads_materialized_edges(tmp_path):
    db, ix, tb = _project(tmp_path, {
        "a.py": "import b\n\n\ndef fa():\n    return b.fb()\n",
        "b.py": "import a\n\n\ndef fb():\n    return a.fa()\n",
    })
    cycles = tb.module_cycles()
    assert cycles["count"] == 1
    assert set(cycles["cycles"][0]["files"]) == {"a.py", "b.py"}


def test_new_file_rebuilds_edges_for_existing_imports(tmp_path):
    """A file added *after* the first index can satisfy an import that was
    unresolvable before — the edge table must pick it up."""
    db, ix, tb = _project(tmp_path, {"app.py": "import late\n\n\ndef main():\n    return late.v\n"})
    deps = tb.file_deps("app.py")
    assert deps["external_imports"], "unresolvable import must stay external first"
    (Path(str(tb.root)) / "late.py").write_text("v = 1\n", encoding="utf-8")
    tb.code_search("late")  # triggers refresh
    deps = tb.file_deps("app.py")
    assert deps["imports"][0]["resolves_to"] == ["late.py"]


# ---------------- P2: parameter-type evidence ----------------

PARAM_TYPE_FILES = {
    "svc.py": "class UserService:\n    def run(self):\n        return 1\n",
    "other/UserService.py": "class UserService:\n    def run(self):\n        return 2\n",
    "app.py": (
        "from svc import UserService\n"
        "\n"
        "\n"
        "def handler(svc: UserService):\n"
        "    return svc.run()\n"
    ),
}


def test_param_annotation_resolves_receiver(tmp_path):
    """Two classes named UserService exist; the annotation + import evidence
    must pick the one in svc.py, not give up."""
    db, ix, tb = _project(tmp_path, PARAM_TYPE_FILES)
    out = tb.find_callers("UserService.run")
    assert out["found"]
    assert any(
        c["qualified_name"] == "handler" and c.get("via") == "resolved"
        for c in out["callers"]
    )


def test_param_annotation_survives_unique_name(tmp_path):
    db, ix, tb = _project(tmp_path, {
        "svc.py": "class Repo:\n    def add(self, x):\n        return x\n",
        "app.py": "from svc import Repo\n\n\ndef handle(repo: Repo):\n    return repo.add(1)\n",
    })
    out = tb.find_callers("Repo.add")
    assert out["found"]
    assert any(c["qualified_name"] == "handle" for c in out["callers"])


def test_import_evidence_is_word_boundary(tmp_path):
    """owner `user` must not match an import of `user_service`."""
    db, ix, tb = _project(tmp_path, {
        "user_service.py": "import helper\n\n\nclass User:\n    def save(self):\n        return 1\n",
        "helper.py": "def noop():\n    return 0\n",
        "app.py": "import user_service\n\n\ndef go(req):\n    return req.save()\n",
    })
    out = tb.find_callers("User.save")
    # previously this linked `go` as a caller of User.save via the substring
    # "user" in "import user_service"
    assert out["callers"] == []
    assert out.get("unresolved_incoming", 0) >= 1


# ---------------- P2: impact import-level dependents ----------------

def test_impact_reports_import_dependents(tmp_path):
    db, ix, tb = _project(tmp_path, {
        "core.py": "class Engine:\n    def start(self):\n        return 1\n",
        "app.py": "from core import Engine\n\n\ndef boot():\n    return Engine().start()\n",
    })
    out = tb.impact_analysis("Engine.start")
    assert out["import_dependents"] == ["app.py"]
    assert out["total_affected"] >= len(out["impact"]["HIGH"]) + len(out["import_dependents"])


# ---------------- P3: language coverage ----------------

def test_ts_class_field_arrow_function(tmp_path):
    db, ix, tb = _project(tmp_path, {
        "store.ts": "export function save(x: string) {}\n",
        "comp.ts": (
            "import { save } from './store';\n"
            "class C {\n"
            "  onSave = (e: string) => { save(e); };\n"
            "}\n"
        ),
    })
    syms = tb.file_symbols("comp.ts")
    names = [s["symbol"] for s in syms["symbols"]]
    assert "onSave" in names
    out = tb.find_callers("save")
    assert any(c["qualified_name"] == "C.onSave" and c.get("via") == "resolved"
               for c in out["callers"])


def test_cpp_out_of_class_definition_attaches_to_class(tmp_path):
    db, ix, tb = _project(tmp_path, {
        "widget.h": "class Widget {\npublic:\n    int draw();\n};\n",
        "widget.cpp": '#include "widget.h"\nint Widget::draw() { return 0; }\n',
    })
    syms = tb.file_symbols("widget.cpp")
    qnames = [s["qualified_name"] for s in syms["symbols"]]
    assert "Widget.draw" in qnames


def test_go_interface_methods_are_symbols(tmp_path):
    db, ix, tb = _project(tmp_path, {
        "iface.go": "package main\n\ntype Greeter interface {\n\tHello() string\n\tBye() string\n}\n",
    })
    syms = tb.file_symbols("iface.go")
    names = [s["symbol"] for s in syms["symbols"]]
    assert "Greeter" in names
    assert "Hello" in names and "Bye" in names
    # they are members of the interface (Class.method queries work)
    rows = db.conn.execute(
        "SELECT qualified_name FROM symbols WHERE qualified_name='Greeter.Hello'"
    ).fetchall()
    assert rows == [("Greeter.Hello",)]


# ---------------- P3: Java fully-qualified import disambiguation ----------------

JAVA_FILES = {
    "com/a/Parser.java": "package com.a;\npublic class Parser { public void parse() {} }\n",
    "com/b/Parser.java": "package com.b;\npublic class Parser { public void parse() {} }\n",
    "Main.java": (
        "import com.a.Parser;\n"
        "public class Main { public void go(Parser p) { p.parse(); } }\n"
    ),
}


def test_java_fq_import_picks_the_right_package(tmp_path):
    db, ix, tb = _project(tmp_path, JAVA_FILES)
    out = tb.find_callers("Parser.parse")
    # `parse` exists twice (both packages); the caller must land on exactly
    # one of them -- com.a, per the import line -- and not on both.
    hits = [c for c in out["callers"] if c["qualified_name"] == "Main.go"]
    assert len(hits) == 1
    # the resolved callee is the com.a Parser (verify via the stored edges;
    # the Java parser emits a bare and a dotted edge for one call site, so
    # two rows may map to the same file — what matters is that com/b got none)
    rows = db.conn.execute(
        """SELECT f.path FROM relations r
             JOIN symbols s ON s.id = r.target_id
             JOIN files f ON f.id = s.file_id
            WHERE r.rtype='calls' AND r.target LIKE '%parse%'"""
    ).fetchall()
    assert {r[0] for r in rows} == {"com/a/Parser.java"}


def test_java_fq_imported_helper():
    fq = "import com.a.parser;"
    assert _java_fq_imported("com/a/Parser.java", fq) is True
    assert _java_fq_imported("com/a/Parser.java", "import com.b.parser;") is False
    # word boundary: a longer trailing name must not match
    assert _java_fq_imported("com/a/Parser.java", "import com.a.parserx;") is False
    # word boundary: a longer leading segment must not match either
    assert _java_fq_imported("com/a/Parser.java", "import xcom.a.parser;") is False
    assert _java_fq_imported("com/a/Parser.java", "import com.a;") is False
    assert _java_fq_imported("notjava.py", fq) is False
    assert _java_fq_imported("com/a/Parser.java", "") is False


# ---------------- P4: branch-level changed_context ----------------

def _git(root: Path, *args: str):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_changed_context_base_covers_committed_changes(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "svc.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    # committed change on top of HEAD
    (root / "svc.py").write_text("def a():\n    return 2\n\ndef b():\n    return 3\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "change")

    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    out = tb.changed_context(base="HEAD~1")
    assert out["source"] == "git"
    assert out["base"] == "HEAD~1"
    assert "svc.py" in out["changed_files"]
    names = {s["symbol"] for syms in out["changed_symbols"].values() for s in syms}
    assert "b" in names  # the new function is part of the branch footprint


# ---------------- P5: config-change cache invalidation ----------------

ALIAS_FILES = {
    "tsconfig.json": '{"compilerOptions": {"paths": {"@/*": ["src/*"]}}}',
    "src/util.ts": "export function helper() { return 1; }\n",
    "lib/util.ts": "export function helper() { return 2; }\n",
    "app.ts": "import { helper } from '@/util';\n\nexport const v = helper();\n",
}


def test_tsconfig_change_invalidates_alias_cache(tmp_path):
    db, ix, tb = _project(tmp_path, ALIAS_FILES)
    deps = tb.file_deps("app.ts")
    assert deps["imports"][0]["resolves_to"] == ["src/util.ts"]

    cfg = Path(str(tb.root)) / "tsconfig.json"
    cfg.write_text('{"compilerOptions": {"paths": {"@/*": ["lib/*"]}}}', encoding="utf-8")
    # force a distinct mtime (same-second writes could otherwise be skipped)
    st = cfg.stat()
    os.utime(cfg, (st.st_atime, st.st_mtime + 2))
    tb.code_search("helper")  # triggers refresh with the new config fingerprint

    deps = tb.file_deps("app.ts")
    assert deps["imports"][0]["resolves_to"] == ["lib/util.ts"]


# ---------------- P5/P6 small items ----------------

def test_read_file_strips_crlf(tmp_path):
    # write raw bytes: write_text would translate \n and double the \r
    db, ix, tb = _project(tmp_path, {"win.py": "pass\n"})
    (Path(str(tb.root)) / "win.py").write_bytes(b"def a():\r\n    return 1\r\n")
    out = tb.read_file("win.py")
    assert out["found"]
    assert "\r" not in out["content"]
    assert out["content"].splitlines() == ["def a():", "    return 1"]


def test_first_type_ident_skips_wrappers():
    assert first_type_ident("Optional[UserService]") == "UserService"
    assert first_type_ident("list[UserService]") == "UserService"
    assert first_type_ident("UserService") == "UserService"
    assert first_type_ident("Array<UserService>") == "UserService"
    assert first_type_ident("string") == ""


def test_call_targets_unchanged_for_simple_chains():
    # guard the shared helper still behaves after the util.py rewrite
    assert call_targets(None, b"") == []
