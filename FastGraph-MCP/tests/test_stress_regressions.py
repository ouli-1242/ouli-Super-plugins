"""Regression tests for defects found in the stress-test audit (STRESS_TEST_REPORT.md).

Each test reproduces one confirmed bug; the fix must make it pass.
"""

import shutil
import threading
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox


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


# ---------------- P1-0: shared-connection cursor corruption under threads ----------------


def test_db_conn_per_thread_safe(tmp_root):
    """A second execute on the *same* sqlite3 connection from another thread
    corrupts an in-flight cursor iteration (wrong row counts, empty rows).
    DB.conn must hand out a per-thread connection instead (was: one shared
    check_same_thread=False connection -> module_cycles crashed with
    'not enough values to unpack (expected 1, got 0)' under concurrent
    MCP tool calls)."""
    import sys as _sys

    db = DB(tmp_root)
    conn = db.conn
    conn.execute("CREATE TABLE t (a TEXT, b TEXT)")
    conn.executemany("INSERT INTO t VALUES (?, ?)", [(f"x{i}", f"y{i}") for i in range(2000)])
    conn.commit()
    _sys.setswitchinterval(0.0001)

    errors: list[str] = []

    def reader():
        for _ in range(60):
            try:
                rows = list(db.conn.execute("SELECT a, b FROM t"))
                if len(rows) != 2000:
                    errors.append(f"row count {len(rows)} != 2000")
            except Exception as e:  # noqa: BLE001
                errors.append(f"{type(e).__name__}: {e}")

    def writer():
        for _ in range(60):
            db.conn.execute("SELECT 1")

    threads = [threading.Thread(target=reader) for _ in range(4)] + \
              [threading.Thread(target=writer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    db.close()
    assert errors == [], f"shared-connection corruption: {errors[:3]}"


def test_concurrent_tools_no_crash(tmp_root):
    """The full tool surface must survive concurrent calls from a thread pool
    (how MCP servers dispatch parallel requests). Was: module_cycles crashed
    with a ValueError whenever it overlapped other tools."""
    import sys as _sys

    files = {
        "a.py": "from b import run\ndef entry():\n    return run()\n",
        "b.py": "from a import entry\ndef run():\n    return entry()\n",
        **{f"m{i}.py": f"def f{i}():\n    return {i}\n" for i in range(20)},
    }
    db, ix, tb = _build(tmp_root, files)
    _sys.setswitchinterval(0.0001)

    errors: list[str] = []

    def worker():
        for _ in range(8):
            try:
                tb.module_cycles()
                tb.code_search("entry")
                tb.find_callers("entry")
                tb.project_overview()
            except Exception as e:  # noqa: BLE001
                errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    db.close()
    assert errors == [], f"concurrent tool calls crashed: {errors[:3]}"


# ---------------- P1-1: concurrent refresh must not crash ----------------

def test_concurrent_refresh_no_crash(tmp_root):
    files = {f"m{i}.py": f"def f{i}():\n    return {i}\n" for i in range(30)}
    files["caller.py"] = "from m0 import f0\ndef go():\n    return f0()\n"
    db, ix, tb = _build(tmp_root, files)

    errors: list[tuple] = []
    def worker(i):
        try:
            for _ in range(15):
                tb.code_search("f0")
                tb.find_callers("go")
        except Exception as e:  # noqa: BLE001 - collect any crash
            errors.append((i, type(e).__name__, str(e)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    db.close()
    assert errors == [], f"concurrent refresh crashed: {errors[:3]}"


# ---------------- P1-2: trace_path past 8 hops must resolve ----------------

def test_trace_path_deep_chain(tmp_root):
    chain = "".join(f"def f{i}():\n    return f{i + 1}()\n" for i in range(12))
    chain += "def f12():\n    return 0\n"
    db, ix, tb = _build(tmp_root, {"deep.py": chain})
    res = tb.trace_path("f0", "f12")
    db.close()
    assert res["path"] is not None, "trace_path failed on a 12-hop chain"
    qnames = [p["qualified_name"] for p in res["path"]]
    assert "f12" in qnames and "f0" in qnames


def test_trace_path_user_depth_respected(tmp_root):
    """depth param must reach path_between (was: hardcoded 8)."""
    chain = "".join(f"def f{i}():\n    return f{i + 1}()\n" for i in range(12))
    chain += "def f12():\n    return 0\n"
    db, ix, tb = _build(tmp_root, {"deep.py": chain})
    # depth=3 is too shallow -> None; depth=20 covers the chain
    shallow = tb.trace_path("f0", "f12", depth=3)
    deep = tb.trace_path("f0", "f12", depth=20)
    db.close()
    assert shallow["path"] is None
    assert deep["path"] is not None


# ---------------- P2-3: code_search must find non-ASCII symbols ----------------

def test_code_search_chinese_symbol(tmp_root):
    db, ix, tb = _build(tmp_root, {"mod.py": "def 中文函数():\n    return 'ok'\n"})
    hits = tb.code_search("中文函数")["results"]
    db.close()
    assert any(h["symbol"] == "中文函数" for h in hits)


# ---------------- P2-4: find_callees must not report inheritance as a call ----------------

def test_find_callees_excludes_inheritance(tmp_root):
    db, ix, tb = _build(tmp_root, {
        "base.py": "class Base:\n    def m(self):\n        pass\n",
        "derived.py": "from base import Base\nclass Derived(Base):\n    def m2(self):\n        pass\n",
    })
    callees = tb.find_callees("Derived")["callees"]
    db.close()
    assert all(c["qualified_name"] != "Base" for c in callees), \
        f"inheritance leaked into callees: {[c['qualified_name'] for c in callees]}"


# ---------------- P2-6: parser coverage for common declarations ----------------

def test_ts_interface_type_enum_namespace_indexed(tmp_root):
    db, ix, tb = _build(tmp_root, {
        "types.ts": "export interface User { id: number }\n"
                    "export type ID = string;\n"
                    "export enum Role { Admin }\n"
                    "export namespace NS { export const v = 1; }\n",
    })
    for sym in ("User", "ID", "Role", "NS"):
        assert tb.symbol_info(sym)["found"], f"{sym} not indexed (TS)"
    ns_v = tb.symbol_info("NS.v")
    assert ns_v["found"], "namespace member NS.v not indexed"
    db.close()


def test_cpp_struct_union_indexed(tmp_root):
    db, ix, tb = _build(tmp_root, {
        "tpl.cpp": "struct Point { int x; };\nunion U { int i; float f; };\n",
    })
    assert tb.symbol_info("Point")["found"], "C++ struct not indexed"
    assert tb.symbol_info("U")["found"], "C++ union not indexed"
    kinds = {s["kind"] for s in tb.file_symbols("tpl.cpp")["symbols"]}
    assert kinds == {"struct", "union"}
    db.close()


def test_vue_script_setup_variables_indexed(tmp_root):
    db, ix, tb = _build(tmp_root, {
        "comp.vue": "<script setup lang=\"ts\">\nimport { ref } from \"vue\";\n"
                    "const count = ref(0);\nfunction inc() { count.value++; }\n"
                    "</script>\n<template><button @click=\"inc\">{{count}}</button></template>\n",
    })
    assert tb.symbol_info("count")["found"], "Vue script-setup const not indexed"
    assert tb.symbol_info("inc")["found"]
    db.close()


def test_go_method_qualified_name(tmp_root):
    """Go method qualified_name must be `Struct.Method` (was: the whole
    receiver `s *Service` leaked in, so `Service.Run` was unsearchable)."""
    db, ix, tb = _build(tmp_root, {
        "svc.go": "package svc\n"
                  "type Service struct {}\n"
                  "func (s *Service) Run() int { return 1 }\n"
                  "func (s Service) Query() int { return 2 }\n"
                  "type Other struct {}\n"
                  "func (o *Other) Run() int { return 3 }\n",
    })
    r = tb.symbol_info("Service.Run")
    assert r["found"], f"Service.Run not found: {r}"
    assert r["matches"][0]["qualified_name"] == "Service.Run"
    assert tb.symbol_info("Service.Query")["found"]
    # two structs share method name `Run`; qualified lookup disambiguates
    assert tb.symbol_info("Other.Run")["found"]
    db.close()


def test_code_search_kind_is_filter(tmp_root):
    """kind= must AND with the name match (was: OR'd into the name clause, so
    `code_search("run", kind="function")` returned every function in the repo)."""
    db, ix, tb = _build(tmp_root, {
        "a.py": "def run():\n    return 1\n\ndef other():\n    return 2\n",
        "b.py": "class Run:\n    pass\n",
    })
    functions = tb.code_search("run", kind="function")["results"]
    names = {h["symbol"] for h in functions}
    assert "run" in names
    assert "other" not in names, f"kind filter leaked non-matching function: {names}"
    assert all(h["kind"] == "function" for h in functions)
    db.close()


def test_cpp_class_method_indexed(tmp_root):
    """C++ class methods must be indexed (were dropped: the method name node
    inside a class is a `field_identifier`, but extraction looked only for
    `identifier`)."""
    db, ix, tb = _build(tmp_root, {
        "k.cpp": "class K {\npublic:\n    int g() { return 1; }\n    void h() {}\n};\n",
    })
    assert tb.symbol_info("g")["found"], "C++ class method g not indexed"
    assert tb.symbol_info("h")["found"], "C++ class method h not indexed"
    db.close()


def test_code_search_chinese_in_docstring(tmp_root):
    """Chinese doc/prose must be searchable (was: FTS5 unicode61 tokenizes a
    whole CJK run as one token, so "知识图谱" never matched a docstring that
    merely *contains* it). The docstring here is module-level, so it lands on
    the module symbol `mod`."""
    db, ix, tb = _build(tmp_root, {
        "mod.py": '"""定制化学习策略与知识图谱。"""\n'
                  "def analyze():\n"
                  "    return 1\n",
    })
    hits = tb.code_search("知识图谱")
    db.close()
    assert any(h["symbol"] == "mod" for h in hits["results"]), \
        f"docstring CJK not searchable: {hits['results']}"


def test_module_docstring_searchable(tmp_root):
    """Module-level docstring must be searchable (was: kept in
    ParseResult.module_doc but never written to any symbol, so top-of-file
    Chinese/purpose docs were invisible to code_search)."""
    db, ix, tb = _build(tmp_root, {
        "docmod.py": '"""EduSpark 平台与知识图谱功能。"""\n'
                     "def f():\n"
                     "    return 1\n",
    })
    hits = tb.code_search("知识图谱")
    db.close()
    assert any(h["symbol"] == "docmod" for h in hits["results"]), \
        f"module docstring not searchable: {hits['results']}"


def test_code_search_fts_doc_hit(tmp_root):
    """FTS doc search must work (was: `SELECT id FROM fts_symbols` referenced a
    non-existent column on the regular FTS5 table -> every FTS query raised
    and was swallowed, so doc-only hits never surfaced; name/LIKE hits masked
    the breakage)."""
    db, ix, tb = _build(tmp_root, {
        "mod.py": '"""UniquePhraseXyz only appears in this doc."""\n'
                  "def f():\n"
                  "    return 1\n",
    })
    hits = tb.code_search("UniquePhraseXyz")
    db.close()
    assert any(h["symbol"] == "mod" for h in hits["results"]), \
        f"FTS doc-only hit missing: {hits['results']}"


def test_code_search_fts_qualified_suffix(tmp_root):
    """FTS must also match a phrase inside a longer doc, not just a prefix."""
    db, ix, tb = _build(tmp_root, {
        "mod.py": '"""Custom learning path builder for GenZ v2."""\n'
                  "def plan():\n"
                  "    return 1\n",
    })
    hits = tb.code_search("GenZ v2")
    db.close()
    assert any(h["symbol"] == "mod" for h in hits["results"]), \
        f"FTS mid-phrase hit missing: {hits['results']}"


# ---------------- P3-7: empty root must error, not silently index cwd ----------------

def test_empty_root_param_errors(tmp_root):
    db, ix, tb = _build(tmp_root, {"main.py": "def x():\n    pass\n"})
    try:
        tb.code_search("x", root="")
    except ValueError:
        db.close()
        return
    db.close()
    raise AssertionError("root='' should raise ValueError instead of indexing cwd")


# ---------------- P3-8: cyclic inheritance must not include self as descendant ----------------

def test_type_hierarchy_cyclic_no_self(tmp_root):
    db, ix, tb = _build(tmp_root, {
        "x.py": "class A(B):\n    pass\n\nclass B(A):\n    pass\n\nclass C(A):\n    pass\n",
    })
    hier = tb.type_hierarchy("A")
    db.close()
    assert hier["found"]
    desc = {d["symbol"] for d in hier["descendants"]}
    assert "A" not in desc, f"root symbol leaked into its own descendants: {desc}"


# ---------------- P3-9: resolve_file must not LIKE-wildcard-assign a nonexistent path ----------------

def test_file_symbols_no_wildcard_miss(tmp_root):
    """File names contain `_`; a nonexistent request must not resolve to a
    LIKE-wildcard match (was: `my_file_v2.py` could resolve to the existing
    `myXfile_v2.py` because `_` is a single-char LIKE wildcard)."""
    db, ix, tb = _build(tmp_root, {
        "src/myXfile_v2.py": "def xed():\n    pass\n",
    })
    res = tb.file_symbols("src/my_file_v2.py")  # does not exist; `_` acts as a wildcard
    db.close()
    assert res["count"] == 0, f"wildcard miss resolved to {res.get('file')}"