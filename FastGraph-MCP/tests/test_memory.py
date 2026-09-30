"""Project-memory layer (on by default, FASTGRAPH_MEMORY=0 to park it): anchored
notes, graph snapshots.

Two things every test here guards, because they are the layer's contract with
existing users:

* with the flag off the server is *indistinguishable* from a build without this
  code -- same advertised tools, same responses, and no `memory.sqlite` created;
* a note never becomes unreachable because the code it was pinned to moved --
  that would reproduce inside the memory layer the loss it exists to prevent.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph import index as index_mod
from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.server import build_server
from fastgraph.tools import Toolbox

WORK = Path(__file__).resolve().parent / "work_memory"
BASE_TOOLS = {
    "activate_project", "reindex", "project_overview", "code_search", "symbol_info",
    "read_code", "call_graph", "impact_analysis", "file_deps", "module_cycles",
    "changes",
}
# Three, not four: `what_changed` answers the same question as `changed_context`
# on a different time base, so both are one advertised tool (`changes`) whose
# `since=` branch still runs `Toolbox.what_changed`.
MEMORY_TOOLS = {"remember", "recall", "forget", "checkpoint"}


def _rmtree(path: Path):
    if not path.exists():
        return
    for p in path.rglob("*"):
        p.chmod(p.stat().st_mode | 0o200)
    shutil.rmtree(path, ignore_errors=True)


def write(path: Path, content: str):
    """Write + push mtime forward: the incremental scan keys on (mtime, size),
    so a same-second rewrite of the same length would not count as a change."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    st = path.stat()
    os.utime(path, (st.st_atime + 5, st.st_mtime + 5))


AUTH_V1 = '''\
class AuthService:
    def login(self, user, pw):
        return hash_pw(pw)

    def logout(self):
        return None


def hash_pw(pw):
    return pbkdf2(pw)


def pbkdf2(pw):
    return pw
'''
# rename hash_pw -> derive, drop logout, add new_helper + a second pbkdf2 caller
AUTH_V2 = '''\
class AuthService:
    def login(self, user, pw):
        return derive(pw)


def derive(pw):
    return pbkdf2(pw)


def pbkdf2(pw):
    return pw


def new_helper(x):
    return derive(x)
'''
API = '''\
from auth import AuthService


def handle(req):
    svc = AuthService()
    return svc.login(req.user, req.pw)
'''


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTGRAPH_MEMORY", "1")
    _rmtree(WORK)
    root = WORK
    root.mkdir(parents=True, exist_ok=True)
    write(root / "auth.py", AUTH_V1)
    write(root / "api.py", API)
    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    tb.reindex()
    yield tb
    tb.close()
    db.close()
    _rmtree(WORK)


# ---------------------------------------------------------------- flag off


def test_parked_layer_advertises_exactly_the_read_only_tools(tmp_path):
    os.environ["FASTGRAPH_MEMORY"] = "0"
    try:
        names = {t.name for t in build_server(tmp_path)._tool_manager.list_tools()}
        assert names == BASE_TOOLS, f"unexpected advertised tools: {names ^ BASE_TOOLS}"
    finally:
        os.environ.pop("FASTGRAPH_MEMORY", None)
        gc_and_clean()


def test_the_layer_is_registered_without_any_env_var(tmp_path):
    """On by default: `FASTGRAPH_MEMORY=1` must not be required to see the tools.

    The layer's whole point is cross-session memory, and a feature nobody configures
    on never gets to prove it -- so the default carries the cost (four schemas) and
    the file-creation guarantee below instead.
    """
    os.environ.pop("FASTGRAPH_MEMORY", None)
    try:
        srv = build_server(tmp_path)
        names = {t.name for t in srv._tool_manager.list_tools()}
        assert names == BASE_TOOLS | MEMORY_TOOLS, sorted(names ^ (BASE_TOOLS | MEMORY_TOOLS))
        assert "FASTGRAPH_MEMORY" in (srv.instructions or "")
    finally:
        gc_and_clean()


def test_default_on_still_creates_no_memory_sqlite(tmp_path):
    """Being on must not mean being written: reads may not create the store.

    Otherwise the default would drop a persistent file into every project someone
    opens, which is the one thing the read-only positioning promised not to do.
    """
    os.environ.pop("FASTGRAPH_MEMORY", None)
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    db = DB(root)
    tb = Toolbox(root, db, Indexer(root, db))
    try:
        tb.reindex()
        assert tb.symbol_info("f")["found"]
        assert tb.recall("module:src")["notes"] == []
        assert tb.what_changed("no-such-baseline")["ok"] is False
        assert not (root / ".fastgraph" / "memory.sqlite").exists(), "a read created the memory store"
        assert tb.remember("project:", "第一条笔记", kind="decision")["ok"]
        assert (root / ".fastgraph" / "memory.sqlite").exists()
    finally:
        tb.close()
        db.close()


def test_memory_on_adds_the_four_memory_tools(tmp_path):
    os.environ["FASTGRAPH_MEMORY"] = "1"
    try:
        tools = build_server(tmp_path)._tool_manager.list_tools()
        names = {t.name for t in tools}
        assert names == BASE_TOOLS | MEMORY_TOOLS
        by = {t.name: t for t in tools}
        # a write must not claim read_only_hint: that is what tells a client it
        # may auto-approve the call and run it in parallel with the others
        assert by["remember"].annotations.read_only_hint is False
        assert by["checkpoint"].annotations.read_only_hint is False
        # forget deletes a row: same reasoning as the inserts, and the client should
        # not treat it as a parallel-safe read
        assert by["forget"].annotations.read_only_hint is False
        assert by["recall"].annotations.read_only_hint is True
        assert by["changes"].annotations.read_only_hint is True
    finally:
        os.environ.pop("FASTGRAPH_MEMORY", None)
        gc_and_clean()


def test_flag_off_never_creates_memory_sqlite(box):
    os.environ["FASTGRAPH_MEMORY"] = "0"
    try:
        box.symbol_info("AuthService.login")
        box.find_callers("pbkdf2")
        box.impact_analysis("pbkdf2")
        assert not (WORK / ".fastgraph" / "memory.sqlite").exists()
    finally:
        os.environ["FASTGRAPH_MEMORY"] = "1"


def test_flag_off_read_tools_carry_no_notes_field(box):
    box.remember("AuthService.login", "decision text", kind="decision")
    os.environ["FASTGRAPH_MEMORY"] = "0"
    try:
        for out in (box.symbol_info("AuthService.login"), box.find_callers("pbkdf2"),
                    box.impact_analysis("pbkdf2")):
            assert "notes" not in out
    finally:
        os.environ["FASTGRAPH_MEMORY"] = "1"
    assert box.symbol_info("AuthService.login")["notes"]


def gc_and_clean():
    import gc
    gc.collect()
    _rmtree(WORK)


# ---------------------------------------------------------------- notes


def test_remember_recall_roundtrip_keeps_unicode(box):
    r = box.remember("AuthService.login", "用 PBKDF2 不用 bcrypt：ARM 构建机上 bcrypt 慢", kind="decision")
    assert r["ok"] and r["anchor"] == "symbol:auth.py#AuthService.login"
    got = box.recall("AuthService.login")
    assert got["count"] == 1
    assert got["notes"][0]["body"] == "用 PBKDF2 不用 bcrypt：ARM 构建机上 bcrypt 慢"
    assert got["notes"][0]["kind"] == "decision"


def test_same_name_in_two_files_does_not_collide(box):
    write(box.root / "other.py", "def login(a):\n    return a\n")
    box.reindex()
    r = box.remember("login", "ambiguous on purpose")
    assert r["ok"] is False
    assert set(r["candidates"]) == {"symbol:auth.py#AuthService.login", "symbol:other.py#login"}
    exact = box.remember("symbol:other.py#login", "另一个 login 的说明")
    assert exact["ok"]
    only = box.recall("symbol:other.py#login")
    assert [n["body"] for n in only["notes"]] == ["另一个 login 的说明"]
    # the sibling that shares the name must not surface this note
    assert box.recall("symbol:auth.py#AuthService.login")["count"] == 0


def test_remember_refuses_unknown_anchor(box):
    r = box.remember("symbol:auth.py#Nope.gone", "typo")
    assert r["ok"] is False and "Nope.gone" in r["error"]
    assert box.remember("totally_absent_symbol", "x")["ok"] is False


def test_remember_dedups_identical_note(box):
    a = box.remember("auth.py", "同一个文件级说明", kind="context")
    b = box.remember("file:auth.py", "同一个文件级说明", kind="context")
    assert a["ok"] and b["deduped"] and a["id"] == b["id"]


def test_remember_rejects_unknown_kind_and_empty_body(box):
    assert box.remember("auth.py", "x", kind="rumour")["ok"] is False
    assert box.remember("auth.py", "   ")["ok"] is False


# ---------------------------------------------------------------- forget


def test_forget_removes_the_note_and_echoes_its_body(box):
    """The echoed row is the undo path, so it has to be the whole note: an agent that
    deleted the wrong one needs the anchor and the text to put it back."""
    added = box.remember("AuthService.login", "这条判断后来被推翻了", kind="decision")
    gone = box.forget(added["id"])
    assert gone["ok"]
    assert gone["removed"]["body"] == "这条判断后来被推翻了"
    assert gone["removed"]["anchor"] == "symbol:auth.py#AuthService.login"
    assert gone["removed"]["kind"] == "decision"
    assert gone["remaining"] == 0
    assert box.recall("AuthService.login")["count"] == 0
    assert box.recall("")["count"] == 0


def test_forget_can_undo_a_wrong_remember(box):
    box.remember("AuthService.login", "写错了的说明", kind="warning")
    wrong = box.recall("AuthService.login")["notes"][0]
    box.forget(wrong["id"])
    fixed = box.remember("AuthService.login", "正确的说明", kind="decision")
    got = box.recall("AuthService.login")
    assert got["count"] == 1 and got["notes"][0]["id"] == fixed["id"]
    assert got["notes"][0]["kind"] == "decision"


def test_forget_on_an_unknown_id_changes_nothing(box):
    box.remember("auth.py", "文件级")
    box.remember("project:", "仓库级")
    r = box.forget(9999)
    assert r["ok"] is False and "9999" in r["error"]
    assert r["remaining"] == 2
    assert {n["body"] for n in box.recall("")["notes"]} == {"文件级", "仓库级"}


def test_forget_never_creates_the_store(box):
    """Deleting must not leave a file in a project nobody wrote to.

    Same rule as the read tools' (test_default_on_still_creates_no_memory_sqlite),
    reached from the other side: `forget` is a write tool, so it is the one a caller
    would expect to be allowed to create the database -- and the one that must not.
    """
    assert not (box.root / ".fastgraph" / "memory.sqlite").exists()
    r = box.forget(1)
    assert r["ok"] is False and "no notes" in r["error"]
    assert not (box.root / ".fastgraph" / "memory.sqlite").exists()


def test_a_forgotten_id_is_never_reused(box):
    """notes.id is AUTOINCREMENT for one reason: `forget(id=…)` addresses that column.

    A plain INTEGER PRIMARYKEY key hands out max(rowid)+1, so deleting the newest note
    frees its id and the next remember() takes it -- an id copied from an older recall
    would then delete a note that has nothing to do with the one it named.
    """
    first = box.remember("auth.py", "第一条")
    second = box.remember("project:", "第二条")
    assert second["id"] > first["id"]
    box.forget(second["id"])
    third = box.remember("file:api.py", "第三条")
    assert third["id"] != second["id"]
    assert {n["body"] for n in box.recall("")["notes"]} == {"第一条", "第三条"}


def test_forget_refuses_while_the_layer_is_parked(box):
    added = box.remember("auth.py", "留着")
    os.environ["FASTGRAPH_MEMORY"] = "0"
    try:
        r = box.forget(added["id"])
        assert r["ok"] is False and "FASTGRAPH_MEMORY=0" in r["hint"]
    finally:
        os.environ["FASTGRAPH_MEMORY"] = "1"
    assert box.forget(added["id"])["ok"]


def test_forget_leaves_the_anchor_free_to_remember_again(box):
    """The dedup guard compares bodies of the notes *still present*, so removal has to
    clear that path or a corrected note would be refused as a duplicate forever."""
    text = "同一条决定，改错了"
    box.remember("auth.py", text, kind="decision")
    box.forget(box.recall("auth.py")["notes"][0]["id"])
    again = box.remember("auth.py", text, kind="decision")
    assert again["ok"] and not again.get("deduped")


def test_project_anchor(box):
    assert box.remember("project:", "整体重构走小步提交")["ok"]
    got = box.recall("project:")
    assert got["notes"][0]["anchor"] == "project:"


def test_recall_empty_anchor_means_whole_store(box):
    box.remember("auth.py", "one", kind="todo")
    box.remember("api.py", "two", kind="warning")
    got = box.recall("")
    assert got["scope"] == "all notes" and got["count"] == 2


def test_recall_finds_note_on_deleted_code(box):
    box.remember("AuthService.logout", "登出要清 session cookie，历史原因见 ADR-7", kind="warning")
    write(box.root / "auth.py", AUTH_V2)
    assert box.symbol_info("AuthService.logout")["found"] is False
    got = box.recall("AuthService.logout")
    assert got["anchor_unresolved"] is True
    assert got["notes"][0]["anchor_resolved"] is False
    assert "ADR-7" in got["notes"][0]["body"]


def test_recall_orphans_only_on_request(box):
    box.remember("AuthService.logout", "will be orphaned", kind="warning")
    write(box.root / "auth.py", AUTH_V2)
    all_notes = box.recall("")
    assert all_notes["count"] == 0
    assert box.recall("", include_orphans=True)["count"] == 1


# ---------------------------------------------------------------- snapshots


def test_checkpoint_then_what_changed_reports_topology(box):
    assert box.checkpoint("before-refactor")["ok"]
    write(box.root / "auth.py", AUTH_V2)
    out = box.what_changed("before-refactor")
    assert out["ok"]
    added_syms = out["symbols"]["added"]
    removed_syms = out["symbols"]["removed"]
    assert any("auth.py#derive" in s for s in added_syms)
    assert any("auth.py#new_helper" in s for s in added_syms)
    assert any("auth.py#hash_pw" in s for s in removed_syms)
    assert any("AuthService.logout" in s for s in removed_syms)
    broke = [e for e in out["call_edges"]["removed"] if e["to"].endswith("hash_pw")]
    assert broke and broke[0]["tier"] == "resolved"
    assert any(e["to"].endswith("derive") and e["tier"] == "resolved" for e in out["call_edges"]["added"])
    assert "caveat" in out


def test_what_changed_no_op_when_nothing_moved(box):
    box.checkpoint("calm")
    out = box.what_changed("calm")
    assert out["symbols"]["added"] == [] and out["symbols"]["removed"] == []
    assert out["call_edges"]["added"] == [] and out["call_edges"]["removed"] == []


def test_what_changed_lists_stale_notes(box):
    box.remember("AuthService.logout", "orphan me", kind="warning")
    box.checkpoint("before")
    write(box.root / "auth.py", AUTH_V2)
    out = box.what_changed("before")
    assert any(n["anchor"].endswith("AuthService.logout") for n in out["stale_notes"])


def test_stale_notes_cover_every_anchor_type(box):
    """The batched existence check has to agree with the per-anchor rules: an
    indexed symbol, an indexed file, a non-indexed doc, a module dir and the
    project are all alive; only what really went away is reported."""
    write(box.root / "src" / "util.py", "def helper():\n    return 1\n")
    write(box.root / "other" / "deep.py", "def far():\n    return 2\n")
    write(box.root / "docs" / "note.md", "# doc\n")
    box.reindex()

    box.remember("symbol:src/util.py#helper", "符号级", kind="decision")
    box.remember("file:auth.py", "文件级", kind="context")
    box.remember("file:docs/note.md", "非索引文档", kind="adr")
    box.remember("module:other", "模块级", kind="todo")
    box.remember("project:", "项目级", kind="warning")
    box.checkpoint("all-types")
    assert "stale_notes" not in box.what_changed("all-types")

    (box.root / "src" / "util.py").unlink()
    (box.root / "docs" / "note.md").unlink()
    shutil.rmtree(box.root / "other")
    out = box.what_changed("all-types")
    stale = {n["anchor"] for n in out.get("stale_notes", [])}
    assert stale == {"symbol:src/util.py#helper", "file:docs/note.md", "module:other"}, stale
    # project notes cannot be orphaned, and untouched files stay alive
    assert "project:" not in stale and "file:auth.py" not in stale
    assert box.recall("project:")["count"] == 1
    assert box.recall("module:other", include_orphans=True)["count"] == 1


def test_what_changed_unknown_label_lists_snapshots(box):
    box.checkpoint("real-label")
    out = box.what_changed("nope")
    assert out["ok"] is False
    assert [s["label"] for s in out["snapshots"]] == ["real-label"]


def test_two_checkpoints_compare_label_to_label(box):
    box.checkpoint("v1")
    write(box.root / "auth.py", AUTH_V2)
    box.checkpoint("v2")
    write(box.root / "auth.py", AUTH_V1)  # back again: live index no longer differs
    direct = box.what_changed("v1", to="v2")
    assert direct["symbols"]["added"] and direct["to"]["label"] == "v2"
    assert box.what_changed("v1")["symbols"]["added"] == []
    # a history-vs-history answer must not describe the current working tree
    assert "stale_notes" not in direct and "note" in direct
    assert "working tree" in direct["note"]


def test_snapshot_content_carries_no_rowids(box):
    box.checkpoint("no-ids")
    snap = box.memory.snapshot_by_label("no-ids")
    assert snap["symbols"] and snap["edges"]
    # symbols.id / relations.id change on every re-parse (replace_file_symbols
    # deletes and re-inserts a file's symbols and NULLs the edges pointing at
    # them), so a snapshot that stored ids would diff the index, not the code
    assert all(line.count("\t") == 1 and "#" in line.split("\t")[1] for line in snap["symbols"])
    assert all(len(line.split("\t")) == 4 for line in snap["edges"])
    assert all(line.split("\t")[3] in ("resolved", "text") for line in snap["edges"])
    assert all("#" in line.split("\t")[1] for line in snap["edges"])


def test_snapshot_survives_full_reindex(box):
    box.remember("auth.py", "survives a rebuild", kind="decision")
    box.checkpoint("before-rebuild")
    box.reindex(full=True)
    assert box.recall("auth.py")["notes"][0]["body"] == "survives a rebuild"
    assert box.memory.snapshot_by_label("before-rebuild")["complete"]


def test_memory_db_is_separate_from_index(box):
    # With the flag on, even a read tool opens the store (it has to look notes
    # up), so the separation that matters is the *schema*: memory.sqlite must not
    # carry the code tables, and index.sqlite must not carry the notes -- else a
    # "delete the index and rebuild" would take the memory with it.
    box.remember("auth.py", "opens the store")
    box.find_callers("pbkdf2")
    files = {p.name for p in (box.root / ".fastgraph").iterdir()}
    assert {"index.sqlite", "memory.sqlite"} <= files
    mem_tables = {r[0] for r in box.memory.db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"notes", "graph_snapshot"} <= mem_tables
    assert "symbols" not in mem_tables
    idx_tables = {r[0] for r in box.db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "notes" not in idx_tables


def test_only_dot_fastgraph_is_written(box):
    before = {p.relative_to(box.root).as_posix() for p in box.root.rglob("*") if p.is_file()}
    box.remember("auth.py", "note", kind="todo")
    box.checkpoint("c")
    box.what_changed("c")
    box.recall("auth.py")
    after = {p.relative_to(box.root).as_posix() for p in box.root.rglob("*") if p.is_file()}
    stray = {p for p in after - before if not p.startswith(".fastgraph/")}
    # the read-only-navigation contract: memory never leaks into the source tree
    assert stray == set(), f"memory layer wrote outside .fastgraph/: {stray}"


def test_memory_tools_follow_the_schema_rules(tmp_path):
    """The flag-on tools are held to the same bar as the 14: every parameter
    described, so the model can call them without guessing."""
    os.environ["FASTGRAPH_MEMORY"] = "1"
    try:
        tools = build_server(tmp_path)._tool_manager.list_tools()
        missing = [
            (t.name, pname)
            for t in tools
            for pname, prop in (t.parameters or {}).get("properties", {}).items()
            if not prop.get("description")
        ]
        assert missing == [], f"parameters without description: {missing}"
        docs = {t.name: t.description or "" for t in tools}
        # the pairs a model cannot tell apart from the name alone
        assert "checkpoint" in docs["changes"]
        assert "recall" in docs["remember"]
        assert "changes" in docs["checkpoint"]
    finally:
        os.environ.pop("FASTGRAPH_MEMORY", None)


def test_memory_is_per_project_root(box):
    other = box.root / "other-project"
    write(other / "x.py", "def thing():\n    return 1\n")
    made = box.remember("symbol:x.py#thing", "另一个项目的决定", kind="decision", root=str(other))
    assert made["ok"] and made["root"].replace("\\", "/").endswith("other-project")
    assert box.recall("symbol:x.py#thing", root=str(other))["count"] == 1
    # ...and it must not leak into the active project's store
    assert box.recall("")["count"] == 0
    box._for_root(str(other)).close()


def test_notes_field_is_the_only_difference(box):
    """§7's promise: with the flag on, a read tool adds `notes` and changes
    nothing else in the response."""
    box.remember("AuthService.login", "用 PBKDF2 不用 bcrypt", kind="decision")
    on = box.find_callers("AuthService.login")
    os.environ["FASTGRAPH_MEMORY"] = "0"
    try:
        off = box.find_callers("AuthService.login")
    finally:
        os.environ["FASTGRAPH_MEMORY"] = "1"
    assert on.get("notes") and "notes" not in off
    on.pop("refresh", None)
    off.pop("refresh", None)
    assert {k: v for k, v in on.items() if k != "notes"} == off


def test_memory_tools_run_through_the_mcp_layer(tmp_path):
    """The JSON-args -> pydantic -> Toolbox path, which unit tests on Toolbox miss.

    Registering a tool generates an argument model; a default that does not
    survive that step reads as a required parameter to the client, so the whole
    surface is exercised through the server here: omitted optional arguments, the
    explicit empty anchor, and the label handoff between checkpoint / changes.
    """
    import asyncio

    os.environ["FASTGRAPH_MEMORY"] = "1"
    (tmp_path / "a.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    try:
        server = build_server(tmp_path)
        tm = server._tool_manager

        async def call(name, args):
            return await tm.call_tool(name, args, context=None, convert_result=True)

        async def run():
            out = {}
            out["remember"] = await call("remember", {"anchor": "a.py", "body": "最小参数集"})
            out["recall"] = await call("recall", {"anchor": ""})
            out["checkpoint"] = await call("checkpoint", {"label": "L"})
            out["changes"] = await call("changes", {"since": "L"})
            out["changes_git"] = await call("changes", {})
            out["exact"] = await call("recall", {"anchor": "file:a.py"})
            return out

        res = {k: json.loads(v.content[0].text) for k, v in asyncio.run(run()).items()}
        assert res["remember"]["ok"] and res["remember"]["kind"] == "context"
        assert res["recall"]["count"] == 1 and res["exact"]["count"] == 1
        assert res["checkpoint"]["ok"] and res["checkpoint"]["label"] == "L"
        assert res["changes"]["ok"] and res["changes"]["since"]["label"] == "L"
        assert res["changes"]["symbols"]["added"] == []
        # the other time base, same tool: no `since` -> the git view of the worktree,
        # which is a different payload shape (no `symbols`/`call_edges` diff)
        assert "since" not in res["changes_git"] and "affected_callers" in res["changes_git"], res["changes_git"]
    finally:
        os.environ.pop("FASTGRAPH_MEMORY", None)


def test_workflow_prompt_matches_the_advertised_surface(tmp_path):
    """The prompt is the fallback for clients that ignore server instructions;
    it must not describe 14 tools while 18 are registered, nor the reverse.

    The off case is `FASTGRAPH_MEMORY=0`, not an unset variable -- the layer
    registers by default now.
    """

    def prompt_text():
        pm = build_server(tmp_path)._prompt_manager
        return str(pm.get_prompt("fastgraph-workflow").fn())

    os.environ.pop("FASTGRAPH_MEMORY", None)
    body = prompt_text()
    assert "FASTGRAPH_MEMORY=0" in body and "remember" in body

    os.environ["FASTGRAPH_MEMORY"] = "0"
    try:
        assert "FASTGRAPH_MEMORY" not in prompt_text()
    finally:
        os.environ.pop("FASTGRAPH_MEMORY", None)


def test_python_api_refuses_when_flag_off(box):
    box.remember("auth.py", "written while on")
    os.environ["FASTGRAPH_MEMORY"] = "0"
    try:
        for call in (
            lambda: box.remember("auth.py", "nope"),
            lambda: box.recall("auth.py"),
            lambda: box.checkpoint("nope"),
            lambda: box.what_changed("whatever"),
        ):
            assert call()["ok"] is False
        assert "FASTGRAPH_MEMORY" in box.remember("auth.py", "nope")["hint"]
    finally:
        os.environ["FASTGRAPH_MEMORY"] = "1"
    assert box.recall("auth.py")["count"] == 1


# ---------------------------------------------------------------- completeness


def test_checkpoint_refuses_a_still_building_index(tmp_path, monkeypatch):
    """The gate that keeps `what_changed` honest.

    `_resolve_all` only runs once every file is indexed, and it refuses to link
    edges against a half-known symbol set -- so a snapshot of a building index
    differs from a snapshot of the same code fully indexed. Diffing those would
    report build progress as topology change.
    """
    monkeypatch.setenv("FASTGRAPH_MEMORY", "1")
    monkeypatch.setattr(index_mod, "PARSE_CHUNK", 2)
    monkeypatch.setattr(index_mod, "INDEX_TIME_BUDGET_S", -1.0)
    root = tmp_path / "proj"
    root.mkdir()
    for i in range(6):
        (root / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    try:
        out = tb.checkpoint("too-early")
        assert out["ok"] is False and out["pending_files"] > 0
        assert "building" in out["error"]
        assert tb.memory.snapshot_list() == [], "a refused checkpoint must write nothing"
        monkeypatch.setattr(index_mod, "INDEX_TIME_BUDGET_S", float("inf"))
        assert tb.checkpoint("after-build")["ok"]
    finally:
        tb.close()
        db.close()


def test_what_changed_refuses_an_incomplete_baseline(box):
    box.memory.put_snapshot("partial", "", False, ["function\ta.py#a"], [], [])
    out = box.what_changed("partial")
    assert out["ok"] is False and "incomplete" in out["error"]
    assert box.what_changed("partial", to=None)["ok"] is False


def test_duplicate_names_in_one_file_are_disclosed(box):
    """The anchor key is (file, qualified_name), not a declaration id -- line
    numbers would move on every edit. So one key can cover several declarations
    (real case: preact's `fragments.test.jsx#Foo`, 31 inline components), and
    `remember` has to say so instead of implying it pinned one function."""
    write(box.root / "dupes.py", "class Repeat:\n    pass\n\n\nclass Repeat:\n    pass\n")
    box.reindex()
    made = box.remember("symbol:dupes.py#Repeat", "覆盖同名重复声明")
    assert made["ok"] and made["anchor_matches"] == 2
    assert "share the name" in made["hint"]
    # a unique name gets no such warning
    assert "anchor_matches" not in box.remember("auth.py", "唯一名字")
    assert box.recall("symbol:dupes.py#Repeat")["count"] == 1


def test_anchor_survives_a_qualified_name_with_a_newline(box):
    """C++ really does produce these (2 of 5,313 symbols in Catch2: the parser
    pulls the template argument list across lines). The anchor is `path#qname`, so
    such a name cannot be typed by hand -- it has to survive being copied verbatim
    out of code_search, round-trip through SQLite, and stay one snapshot row.

    The row is crafted on a file that exists on disk: a crafted row on a phantom
    path is wiped by the refresh every tool call runs first.
    """
    from fastgraph import memory as mem_mod

    write(box.root / "src/tmpl.hpp", "#include <string>\n\nstruct Maker {\n    int to_string();\n};\n")
    box.reindex()
    weird = "StringMaker<R, std::enable_if_t<\n  #has_hash::value>>"
    fid = box.db.get_file_id("src/tmpl.hpp")
    box.db.replace_file_symbols(fid, [
        {"name": "Maker", "kind": "struct", "qualified_name": "Maker", "signature": "", "doc": "",
         "start_line": 3, "end_line": 5, "start_col": 0, "end_col": 0},
        {"name": "StringMaker", "kind": "class", "qualified_name": weird, "signature": "", "doc": "",
         "start_line": 7, "end_line": 9, "start_col": 0, "end_col": 0},
    ])
    box.db.commit()

    anchor = f"symbol:src/tmpl.hpp#{weird}"
    made = box.remember(anchor, "模板特化的原因", kind="decision")
    assert made["ok"], made
    assert made["anchor"] == anchor  # stored verbatim: newline and '#' survive
    back = box.recall(anchor)
    assert back["count"] == 1 and back["notes"][0]["anchor_resolved"] is True
    # the split is on the FIRST '#', so everything after it is the name
    assert mem_mod.parse_anchor(anchor) == ("symbol", f"src/tmpl.hpp#{weird}")

    symbols, edges, cycles = mem_mod.collect_sets(box.db)
    box.memory.put_snapshot("with-newline-name", "", True, symbols, edges, cycles)
    snap = box.memory.snapshot_by_label("with-newline-name")
    rows = [l for l in snap["symbols"] if "class" in l]
    assert rows and [l for l in rows if len(l.split("\t")) != 2] == []
    assert any(mem_mod.unesc(l.split("\t")[1]) == f"src/tmpl.hpp#{weird}" for l in rows)


def test_empty_index_is_not_a_valid_baseline(tmp_path, monkeypatch):
    """An empty index passes the completeness gate (nothing is pending because
    nothing was scanned), so it needs its own refusal: a baseline of "no symbols,
    no edges" later reports the entire graph as added, and a diff *against* it
    reads as 'everything was deleted'. Found by probing a repo whose clone had not
    finished -- 0 files, checkpoint returned ok."""
    monkeypatch.setenv("FASTGRAPH_MEMORY", "1")
    root = tmp_path / "empty"
    root.mkdir()
    db = DB(root)
    tb = Toolbox(root, db, Indexer(root, db))
    try:
        out = tb.checkpoint("nothing-here")
        assert out["ok"] is False and "empty" in out["error"]
        assert "activate_project" in out["hint"]
        assert tb.memory.snapshot_list() == []
        tb.memory.put_snapshot("elsewhere", "", True, ["function\ta.py#a"],
                               ["calls\ta.py#a\ta.py#b\tresolved"], [])
        wc = tb.what_changed("elsewhere")
        assert wc["ok"] is False and "empty" in wc["error"]
    finally:
        tb.close()
        db.close()


def test_note_on_a_non_indexed_file_is_allowed(box):
    """Configs and docs are project memory too (found on preact: a rename of
    `oxlint.json` could not be anchored at all, because only indexed sources
    passed validation while `read_file` accepts these files)."""
    write(box.root / "docs" / "adr-001.md", "# why PBKDF2\n")
    made = box.remember("file:docs/adr-001.md", "bcrypt 在 ARM 构建机上太慢，固定用 PBKDF2", kind="adr")
    assert made["ok"] and made["anchor"] == "file:docs/adr-001.md"
    assert box.recall("docs/adr-001.md")["count"] == 1  # bare path, not in the index either
    box.checkpoint("docs-base")
    assert "stale_notes" not in box.what_changed("docs-base"), "a real file is not an orphan"
    # the read-path boundary still holds: dot/excluded paths stay unanchorable
    assert box.remember("file:.fastgraphignore", "x")["ok"] is False
    assert box.remember("file:../outside.py", "x")["ok"] is False


def test_snapshot_survives_control_characters_in_call_text(box):
    """Go / TS really do store target text containing tabs and newlines (measured
    on uber-go/zap: 109 tab-bearing, 112 newline-bearing targets). The snapshot
    format is tab-separated and newline-joined, so unescaped text there splits a
    row into the wrong number of fields and the diff silently lies."""
    from fastgraph import memory as mem_mod

    fid = box.db.upsert_file("weird.go", "go", "h", 1.0, 10)
    box.db.replace_file_symbols(fid, [{
        "name": "call", "kind": "function", "qualified_name": "call", "signature": "",
        "doc": "", "start_line": 1, "end_line": 5, "start_col": 0, "end_col": 0,
    }])
    box.db.replace_file_relations(fid, [
        (sid, "multi\nline\ttarget", "calls", 2)
        for sid in [r[0] for r in box.db.conn.execute("SELECT id FROM symbols WHERE file_id=?", (fid,))]
    ])
    box.db.commit()
    # build the snapshot straight from collect_sets: going through checkpoint()
    # would run a refresh first, and the refresh reconciles the index with disk
    # (this file does not exist on disk), wiping the crafted row
    symbols, edges, cycles = mem_mod.collect_sets(box.db)
    box.memory.put_snapshot("with-control-chars", "", True, symbols, edges, cycles)

    snap = box.memory.snapshot_by_label("with-control-chars")
    malformed = [ln for ln in snap["edges"] if len(ln.split("\t")) != 4]
    assert malformed == [], f"escaped rows must stay one row: {malformed[:2]}"
    text_rows = [ln for ln in snap["edges"] if ln.split("\t")[3] == "text"]
    assert any("\\n" in ln and "\\t" in ln for ln in text_rows), text_rows
    # unescaping is lossless, so the caller still sees the source text as written
    assert any(mem_mod.unesc(ln.split("\t")[2]) == "multi\nline\ttarget" for ln in text_rows)


def test_what_changed_refuses_an_other_format_baseline(box):
    import zlib

    legacy = zlib.compress(b"function\tauth.py#a\nmethod\tauth.py#B.c")
    box.memory.db.conn.execute(
        "INSERT INTO graph_snapshot (label, ref, complete, symbol_blob, edge_blob, cycle_blob, created_at) "
        "VALUES ('legacy', '', 1, ?, ?, ?, 0)",
        (legacy, legacy, legacy),
    )
    box.memory.db.conn.commit()
    out = box.what_changed("legacy")
    assert out["ok"] is False and "format" in out["error"]
    box.checkpoint("modern")
    assert box.what_changed("legacy", to="modern")["ok"] is False


LANG_SAMPLES = {
    "go": ("main.go", 'package main\n\nimport "fmt"\n\nfunc Run(s *Svc) {\n\tfmt.Println(s.Call())\n}\n\n'
                      'type Svc struct{}\n\nfunc (s *Svc) Call() int { return 1 }\n'),
    "rust": ("src/lib.rs", "pub struct Controller;\n\nimpl Controller {\n    pub fn print_file(&self) -> u8 { 0 }\n}\n\n"
                           "pub fn run(c: &Controller) -> u8 {\n    c.print_file()\n}\n"),
    "java": ("src/App.java", "public class App {\n    private Helper h = new Helper();\n\n"
                             "    public int run() { return h.call(); }\n\n"
                             "    class Inner {\n        void go() {}\n    }\n}\n\n"
                             "class Helper { int call() { return 2; } }\n"),
    "cpp": ("src/engine.cpp", "#include \"engine.h\"\n\nint Engine::run() {\n    return step(1);\n}\n\n"
                              "namespace ns {\nclass Thing { public: void go() { step(2); } };\n}\n"),
    "c": ("src/util.c", "#include <stdlib.h>\n\nint compute(int n) {\n    return abs(n);\n}\n\n"
                        "void loop(void) {\n    compute(1);\n}\n"),
    "ts": ("src/handler.ts", "export class Handler {\n    handle(req: Req): number { return this.inner(req); }\n"
                             "    private inner(r: Req) { return r.id; }\n}\n"),
    "vue": ("src/Widget.vue", "<template>\n  <div>{{ label }}</div>\n</template>\n\n"
                              "<script setup lang=\"ts\">\nimport { ref } from 'vue';\n"
                              "const label = ref('x');\nfunction onClick() { label.value = 'y'; }\n</script>\n"),
    "svelte": ("src/Page.svelte", "<script>\n  let count = 0;\n  function inc() { count += 1; }\n</script>\n"
                                  "<button on:click={inc}>{count}</button>\n"),
}


def test_language_matrix_anchors_and_snapshots(box):
    """Every supported language puts a different grammar into qualified_name
    (Go `(recv).Method`, Rust `Foo::bar`, C++ `ns::Thing::go`, Java inner classes,
    Vue/Svelte script blocks). Anchors and snapshot lines are pure string
    contracts, so the round trip is checked for *every* indexed symbol, not for
    one Python sample.
    """
    for rel, text in LANG_SAMPLES.values():
        write(box.root / rel, text)
    stats = box.reindex()
    assert stats["errors"] == 0, box.db.parse_errors(limit=20)

    rows = box.db.conn.execute(
        "SELECT f.path, s.qualified_name, s.kind FROM symbols s JOIN files f ON f.id = s.file_id "
        "WHERE f.path LIKE 'src/%' OR f.path = 'main.go' ORDER BY f.path, s.start_line"
    ).fetchall()
    assert len(rows) > 25, f"expected symbols from 8 languages, got {len(rows)}"
    seen_langs = {r[0].rsplit(".", 1)[-1] for r in rows}
    assert {"go", "rs", "java", "cpp", "c", "ts", "vue", "svelte"} <= seen_langs, seen_langs

    wrote = 0
    for path, qname, _kind in rows:
        anchor = f"symbol:{path}#{qname}"
        made = box.remember(anchor, f"note for {qname}", kind="context")
        assert made["ok"], made
        if qname:  # a note needs a name to hang on
            wrote += 1
        back = box.recall(anchor)
        assert back["count"] >= 1, anchor
        assert all(n["body"].startswith("note for ") for n in back["notes"])
        if made.get("anchor_matches", 1) > 1:
            # a name shared by several declarations in one file must be disclosed
            assert len(back["notes"]) == 1, "one key, one note, listed for every match"

    cp = box.checkpoint("polyglot")
    assert cp["ok"], cp
    snap = box.memory.snapshot_by_label("polyglot")
    assert snap["format"] == "fg-snap/1"
    assert [l for l in snap["symbols"] if len(l.split("\t")) != 2] == []
    assert [l for l in snap["edges"] if len(l.split("\t")) != 4] == []
    assert snap["edges"], "the sample repos do call each other's functions"
    tiers = {l.split("\t")[3] for l in snap["edges"]}
    assert tiers <= {"resolved", "text"}
    print_report = {  # keep the failure message useful without dumping the corpus
        "symbols": len(rows), "notes_written": wrote, "edges": len(snap["edges"])
    }
    assert print_report["symbols"] > 25


def test_language_matrix_reports_no_orphans_when_nothing_moved(box):
    for rel, text in LANG_SAMPLES.values():
        write(box.root / rel, text)
    box.reindex()
    box.remember("src/handler.ts#Handler.handle", "改签名前先看这里", kind="warning")
    box.checkpoint("polyglot-base")
    out = box.what_changed("polyglot-base")
    assert out["ok"] and out["symbols"]["added"] == [] and out["call_edges"]["added"] == []
    assert "stale_notes" not in out, out.get("stale_notes")


def test_module_anchor(box):
    write(box.root / "src/util.py", "def helper():\n    return 1\n")
    box.reindex()
    assert box.remember("module:src", "src 里所有公共函数都要写 docstring", kind="todo")["ok"]
    got = box.recall("src")
    assert got["notes"][0]["kind"] == "todo"
    assert box.remember("module:nope", "x")["ok"] is False


def test_recall_on_a_file_includes_the_notes_inside_it(box):
    """A coarse anchor answers "what do we know about this file", so it has to
    reach the decisions pinned to its symbols. Found on the live MCP run: exact
    key matching returned zero notes for a file that had two."""
    box.remember("file:auth.py", "auth.py 不直接读数据库", kind="warning")
    box.remember("symbol:auth.py#AuthService.login", "登录只接受 SSO", kind="decision")
    box.remember("symbol:api.py#handle", "无关文件，不该出现")

    got = box.recall("file:auth.py")
    assert {n["anchor"] for n in got["notes"]} == {
        "file:auth.py",
        "symbol:auth.py#AuthService.login",
    }, got["notes"]


def test_recall_on_a_module_reaches_through_its_files(box):
    write(box.root / "src/util.py", "def helper():\n    return 1\n")
    box.reindex()
    box.remember("module:src", "src 下的公共函数都要写 docstring", kind="todo")
    box.remember("file:src/util.py", "这个文件在启动早期被导入", kind="context")
    box.remember("symbol:src/util.py#helper", "不要在这里做 IO", kind="warning")
    box.remember("file:auth.py", "仓库根目录的笔记不该被 src 命中")

    got = box.recall("module:src")
    assert {n["anchor"] for n in got["notes"]} == {
        "module:src",
        "file:src/util.py",
        "symbol:src/util.py#helper",
    }, got["notes"]


def test_project_anchor_is_not_a_wildcard(box):
    """`project:` is the repo-wide *bucket*, not "everything": the documented
    "where did the last session leave off" read needs the few project notes
    without every code note in the store crowding them out."""
    box.remember("project:", "本仓库用 ruff，不要再加 flake8 配置", kind="decision")
    box.remember("symbol:auth.py#pbkdf2", "为什么不用 bcrypt")

    assert [n["anchor"] for n in box.recall("project:")["notes"]] == ["project:"]
    assert box.recall("")["count"] == 2


def test_recall_kind_filter_applies_to_an_anchor(box):
    """`kind=` has to narrow an anchored read too, not only the whole-store one."""
    box.remember("symbol:auth.py#pbkdf2", "选 pbkdf2 是因为没有外部依赖", kind="decision")
    box.remember("symbol:auth.py#pbkdf2", "TODO: 换成 argon2 评估", kind="todo")

    got = box.recall("symbol:auth.py#pbkdf2", kind="todo")
    assert got["count"] == 1 and got["notes"][0]["kind"] == "todo", got["notes"]
    assert box.recall("symbol:auth.py#pbkdf2")["count"] == 2


def test_recall_scope_patterns_are_escaped(box):
    """`a_b` must not match `axb`: the '_' in a path is data, not a wildcard."""
    write(box.root / "a_b/mod.py", "def helper():\n    return 1\n")
    write(box.root / "axb/mod.py", "def other():\n    return 1\n")
    box.reindex()
    box.remember("file:axb/mod.py", "不该被 a_b 命中")

    assert box.recall("module:a_b")["count"] == 0
    assert box.recall("module:axb")["count"] == 1


# ---------------------------------------------------------------- git


git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(root: Path, *args: str):
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    )


@git
def test_stale_notes_explain_a_git_rename(box):
    """A moved file must read as 'it moved to login.py', not as 'no notes here'."""
    _git(box.root, "init", "-q")
    _git(box.root, "add", "-A")
    _git(box.root, "commit", "-q", "-m", "base")
    assert box.remember("file:auth.py", "登出要清 session cookie", kind="adr")["ok"]
    box.checkpoint("before-move")
    _git(box.root, "mv", "auth.py", "login.py")

    out = box.what_changed("before-move")
    stale = [n for n in out.get("stale_notes", []) if n["anchor"] == "file:auth.py"]
    assert stale, f"note on the moved file not reported: {out.get('stale_notes')}"
    assert stale[0]["moved_to"] == "login.py"
    # the git side of the same answer
    assert out["git"]["changed_files"].get("login.py") == "renamed"


@git
def test_stale_notes_explain_a_committed_rename(box):
    """The realistic case: the rename is already committed and the tree is clean.

    `git diff HEAD` of a clean worktree is empty, so rename detection has to run
    against the baseline commit the snapshot recorded -- the first real-repo run
    (preact) lost `moved_to` exactly here.
    """
    _git(box.root, "init", "-q")
    _git(box.root, "add", "-A")
    _git(box.root, "commit", "-q", "-m", "base")
    box.remember("file:auth.py", "已提交的重命名也要能找到", kind="adr")
    made = box.checkpoint("before-move")
    assert made["ref"], "the baseline needs a commit to compare against"
    _git(box.root, "mv", "auth.py", "login.py")
    _git(box.root, "commit", "-q", "-m", "rename")

    assert not box.root.joinpath("auth.py").exists()
    out = box.what_changed("before-move")
    stale = [n for n in out.get("stale_notes", []) if n["anchor"] == "file:auth.py"]
    assert stale and stale[0]["moved_to"] == "login.py"


@git
@git
def test_moved_to_reports_a_rename_into_a_dotfile(box):
    """`git mv auth.py .auth.py`: explaining one move must not inherit the
    dot-path noise filter that `changed_files` uses."""
    _git(box.root, "init", "-q")
    _git(box.root, "add", "-A")
    _git(box.root, "commit", "-q", "-m", "base")
    box.remember("file:auth.py", "搬进点文件也要说清楚", kind="adr")
    box.checkpoint("before-dot-move")
    _git(box.root, "mv", "auth.py", ".auth.py")
    _git(box.root, "commit", "-q", "-m", "hide it")

    stale = [n for n in box.what_changed("before-dot-move").get("stale_notes", [])
             if n["anchor"] == "file:auth.py"]
    assert stale and stale[0]["moved_to"] == ".auth.py"


def test_checkpoint_records_head_ref(box):
    _git(box.root, "init", "-q")
    _git(box.root, "add", "-A")
    _git(box.root, "commit", "-q", "-m", "base")
    sha = subprocess.run(["git", "-C", str(box.root), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    made = box.checkpoint("with-ref")
    assert made["ok"] and made["ref"] == sha
    assert box.memory.snapshot_by_label("with-ref")["ref"] == sha
    assert box.checkpoint("explicit", ref="HEAD")["ref"] == "HEAD"
