"""End-to-end tests: index a sample project, exercise the 8 tools."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

SAMPLE = Path(__file__).resolve().parent / "sample_project"
WORK = Path(__file__).resolve().parent / "work"


def _rmtree(path: Path):
    """shutil.rmtree that also clears read-only flags (git object files on win32)."""
    if not path.exists():
        return
    for p in path.rglob("*"):
        p.chmod(p.stat().st_mode | 0o200)
    shutil.rmtree(path, ignore_errors=True)


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_sample(root: Path):
    toplevel = root / "src"
    write(toplevel / "auth/service.py", '''"""Auth service."""
from user.repo import UserRepository

class BaseService:
    pass

class AuthService(BaseService):
    """Handles login."""

    def login(self, username, password):
        repo = UserRepository()
        user = repo.find_by_username(username)
        return user is not None and user.verify_password(password)

    def _create_session(self, username):
        return Session().start(username)

class OAuthService(AuthService):
    def login(self, username, password):
        return super().login(username, password)
''')
    write(toplevel / "auth/controller.py", '''\
from auth.service import AuthService

class LoginController:
    def login(self, req):
        auth = AuthService()
        return auth.login(req["username"], req["password"])
''')
    write(toplevel / "models/user.py", '''\
class User:
    def verify_password(self, pw):
        return pw == "secret"
''')
    write(toplevel / "db/repo.py", '''\
from user.model import User

class UserRepository:
    def find_by_username(self, name):
        return User(name)

    def find_by_id(self, uid):
        return User(uid)
''')
    write(toplevel / "user/model.py", '''\
class User:
    def __init__(self, name=""):
        self.name = name

    def verify_password(self, pw):
        return pw == "secret"
''')
    write(root / "tests/test_auth.py", '''\
from auth.controller import LoginController

def test_login_ok():
    assert LoginController().login({"username": "u", "password": "secret"}) is True
''')
    write(root / "main.py", '''\
from auth.controller import LoginController

def run():
    return LoginController().login({"username": "u", "password": "secret"})
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


def test_code_search(toolbox):
    hits = toolbox.code_search("login")["results"]
    names = {h["symbol"] for h in hits}
    assert "login" in names


def test_symbol_info(toolbox):
    info = toolbox.symbol_info("AuthService.login")
    assert info["found"]
    assert info["matches"][0]["qualified_name"] == "AuthService.login"


def test_find_callers(toolbox):
    callers = toolbox.find_callers("AuthService.login")["callers"]
    assert any(c["qualified_name"] == "LoginController.login" for c in callers)


def test_find_callees(toolbox):
    callees = toolbox.find_callees("AuthService.login")["callees"]
    assert any(c["qualified_name"] == "UserRepository.find_by_username" for c in callees)
    # per-call targets include the local-variable call, even if not class-resolved
    info = toolbox.symbol_info("AuthService.login")
    targets = {c["target"] for c in info["matches"][0]["callees"]}
    assert "verify_password" in targets


def test_trace_path(toolbox):
    path = toolbox.trace_path("LoginController", "find_by_username")["path"]
    assert path is not None
    qnames = [p["qualified_name"] for p in path]
    assert "LoginController.login" in qnames
    assert "AuthService.login" in qnames


def test_impact_high(toolbox):
    imp = toolbox.impact_analysis("AuthService.login")
    high = {s["name"] for s in imp["impact"]["HIGH"]}
    assert "login" in high  # LoginController.login


def test_project_overview(toolbox):
    ov = toolbox.project_overview()
    assert ov["files"] == 7
    assert "python" in ov["languages"]
    assert "parse_errors" in ov
    assert "main.py" in ov["entry_points"]
    assert ov["layering"]


def test_file_symbols(toolbox):
    syms = toolbox.file_symbols("src/auth/service.py")["symbols"]
    names = {s["symbol"] for s in syms}
    assert "AuthService" in names
    assert "login" in names
    assert all("lines" in s for s in syms)


def test_file_deps(toolbox):
    deps = toolbox.file_deps("src/auth/service.py")
    assert deps["found"]
    # unresolved import (no such module in project) -> external_imports
    assert any("user.repo" in i["text"] for i in deps["external_imports"])
    assert any(i["file"] == "src/auth/controller.py" for i in deps["importers"])
    # internal import resolves to a file
    deps_ctl = toolbox.file_deps("src/auth/controller.py")
    assert any(i["resolves_to"] for i in deps_ctl["imports"])


def test_rename_impact(toolbox):
    imp = toolbox.rename_impact("AuthService.login")
    assert imp["definition_count"] == 1
    assert imp["reference_count"] >= 1
    files = {r["file"] for r in imp["references"]}
    assert "src/auth/controller.py" in files  # call site
    assert "src/auth/service.py" in files     # OAuthService super() usage
    assert "risk" in imp
    assert imp["risk"]["grade"] in ("HIGH", "MEDIUM", "LOW")


def test_rename_impact_risk(toolbox):
    imp = toolbox.rename_impact("LoginController")
    assert imp["risk"]["public_definitions"] >= 1
    files = {r["file"] for r in imp["references"]}
    assert "main.py" in files
    assert "tests/test_auth.py" in files


def test_type_hierarchy(toolbox):
    hier = toolbox.type_hierarchy("AuthService")
    assert hier["found"]
    anc = {a["qualified_name"] for a in hier["ancestors"]}
    desc = {d["qualified_name"] for d in hier["descendants"]}
    assert "BaseService" in anc
    assert "OAuthService" in desc


def test_incremental_update(toolbox):
    before = toolbox.db.count_symbols()
    # edit one file -> only that file re-parsed
    write(WORK / "src/auth/service.py", "class AuthService:\n    def login(self):\n        return True\n")
    stats = toolbox._ensure_fresh()
    assert stats["parsed"] == 1
    assert stats["scanned"] == 7
    # symbol still found, new shape
    info = toolbox.symbol_info("AuthService.login")
    assert info["found"]


def test_parse_errors_reported(toolbox):
    write(WORK / "src/broken.py", "def (\n")
    stats = toolbox._ensure_fresh()
    assert stats["errors"] == 1
    ov = toolbox.project_overview()
    assert "src/broken.py" in ov["parse_errors"]


def test_changed_context_git(toolbox):
    """changed_files requires a git repo; skip if git unavailable."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    git_init = subprocess.run(["git", "init"], cwd=str(WORK), capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(WORK), capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=str(WORK), capture_output=True,
    )
    write(WORK / "src/auth/service.py", "class \n    pass\n")
    res = toolbox.changed_context()
    assert "src/auth/service.py" in res["changed_files"]
    assert res["changed_symbols"]


def test_optional_root_param(toolbox):
    """root= switches the query to another project; default keeps this one."""
    default = toolbox.code_search("login")
    assert default["root"] == str(WORK)

    other = WORK.parent / "other_work"
    write(other / "main.py", "def hello():\n    return 1\n")
    try:
        res = toolbox.code_search("hello", root=str(other))
        assert res["root"] == str(other.resolve())
        assert res["count"] == 1
        assert res["results"][0]["symbol"] == "hello"
    finally:
        toolbox.close()  # release the sub-root's sqlite handles before deleting
        _rmtree(other)

    back = toolbox.code_search("login")
    assert back["root"] == str(WORK)

    ov = toolbox.project_overview(root=str(WORK))
    assert ov["root"] == str(WORK)


def test_optional_root_all_tools(toolbox):
    """Every tool honors root= and falls back to the default root."""
    other = WORK.parent / "other_work2"
    write(other / "auth/service.py", '''\
"""Auth service."""
class BaseService:
    pass


def login():
    return "ok"
''')
    try:
        results = {}
        results["symbol_info"] = toolbox.symbol_info("BaseService", root=str(other))
        results["find_callees"] = toolbox.find_callees("login", root=str(other))
        results["impact_analysis"] = toolbox.impact_analysis("login", root=str(other))
        results["file_symbols"] = toolbox.file_symbols("auth/service.py", root=str(other))
        results["file_deps"] = toolbox.file_deps("auth/service.py", root=str(other))
        results["rename_impact"] = toolbox.rename_impact("login", root=str(other))
        results["type_hierarchy"] = toolbox.type_hierarchy("BaseService", root=str(other))
        for name, res in results.items():
            assert res["root"] == str(other.resolve()), name

        assert results["impact_analysis"]["root"] == str(other.resolve())
        # default root unchanged
        assert toolbox.find_callers("login")["root"] == str(WORK)
    finally:
        toolbox.close()  # release the sub-root's sqlite handles before deleting
        _rmtree(other)


def test_optional_root_invalid(toolbox):
    try:
        toolbox.code_search("x", root=str(WORK.parent / "does_not_exist"))
        raise AssertionError("expected ValueError for missing root dir")
    except ValueError:
        pass


def test_activate_project(toolbox):
    """Session activation: switch the default root, then tools run against it."""
    other = WORK.parent / "activated_work"
    write(other / "main.py", "def activated_fn():\n    pass\n")
    try:
        res = toolbox.activate_project(str(other))
        assert res["ok"] and res["active_root"] == str(other.resolve())

        hits = toolbox.code_search("activated_fn")
        assert hits["root"] == str(other.resolve())
        assert hits["count"] == 1

        ov = toolbox.project_overview()
        assert ov["root"] == str(other.resolve())

        # explicit root still overrides the active one
        assert toolbox.code_search("login", root=str(WORK))["root"] == str(WORK)

        # invalid activation is rejected without breaking the active root
        bad = toolbox.activate_project(str(WORK.parent / "nope"))
        assert not bad["ok"]
        assert toolbox.code_search("activated_fn")["count"] == 1

        # deactivate back to the default
        back = toolbox.activate_project(None)
        assert back["ok"] and back["active_root"] == str(WORK)
        assert toolbox.code_search("login")["root"] == str(WORK)
    finally:
        toolbox.close()  # release the sub-root's sqlite handles before deleting
        _rmtree(other)


# ---------------- regression: 5 bugs found in the EduSpark audit ----------------

def test_code_search_case_insensitive(toolbox):
    """Upper/lower case must not decide the result (was: `=` is case-sensitive)."""
    hits = toolbox.code_search("authservice")
    names = {h["symbol"].lower() for h in hits["results"]}
    assert "authservice" in names
    hits = toolbox.code_search("AUTHSERVICE")
    names = {h["symbol"].lower() for h in hits["results"]}
    assert "authservice" in names


def test_code_search_fts_works_for_docs(toolbox):
    """FTS query must not be swallowed by a bad column name (was: 'no such column: fts')."""
    hits = toolbox.code_search("auth service")
    assert hits["count"] >= 1


def test_file_symbols_basename(toolbox):
    """Bare filename must resolve to the indexed file (was: exact path only)."""
    syms = toolbox.file_symbols("service.py")
    names = {s["symbol"] for s in syms["symbols"]}
    assert "AuthService" in names


def test_file_deps_ambiguous(toolbox):
    """Multiple files sharing a basename report candidates instead of 'not found'."""
    write(WORK / "src/other/service.py", "class Other:\n    pass\n")
    toolbox._ensure_fresh()
    deps = toolbox.file_deps("service.py")
    assert deps["found"] is False
    assert deps["ambiguous"] is True
    assert len(deps["candidates"]) >= 2


def test_rename_impact_import_sites(toolbox):
    """rename_impact must surface import lines (was: only relations/qualified names)."""
    imp = toolbox.rename_impact("AuthService")
    files = {r["file"] for r in imp["references"]}
    assert "src/auth/controller.py" in files  # imports AuthService
    assert any(r["rtype"] == "import" for r in imp["references"])


def test_trace_path_through_class_members(toolbox):
    """trace_path must climb through a class's methods (was: died at __init__).

    Chain: entry() -> Helper(func) -> Target().run(). Self-contained files so
    earlier tests that rewrite shared sample files cannot poison the chain.
    """
    write(WORK / "src/chain/entry.py", '''\
from chain.helper import Helper
def entry():
    return Helper().go()
''')
    write(WORK / "src/chain/helper.py", '''\
from chain.target import Target
class Helper:
    def go(self):
        t = Target()
        return t.run()
''')
    write(WORK / "src/chain/target.py", '''\
class Target:
    def run(self):
        return 42
''')
    toolbox._ensure_fresh()
    path = toolbox.trace_path("entry", "Target.run")["path"]
    assert path is not None
    qnames = [p["qualified_name"] for p in path]
    assert "Helper.go" in qnames
    assert "Target.run" in qnames


def test_module_variables_indexed(toolbox):
    """Module-level `g = Thing()` must be a searchable symbol (was: dropped)."""
    write(WORK / "src/gv.py", "from gv import G\n\nclass G:\n    pass\n\ninst = G()\n")
    write(WORK / "src/consumer.py", "from gv import inst\n\ndef use():\n    return inst\n")
    toolbox._ensure_fresh()
    hits = toolbox.code_search("inst")
    names = {h["symbol"] for h in hits["results"]}
    assert "inst" in names


def test_self_attr_dispatch_resolved(toolbox):
    """`self.llm.chat()` must resolve to the owning class method even when
    several classes define `chat` (was: ambiguous -> target_id NULL)."""
    write(WORK / "src/llm/api.py", '''\
class LLMClient:
    def chat(self, msg):
        return "ok"

class Proxy:
    def __init__(self):
        self.llm = LLMClient()
    def ask(self, msg):
        return self.llm.chat(msg)
''')
    write(WORK / "src/llm/other.py", '''\
class OtherLLM:
    def chat(self, msg):
        return "no"
''')
    toolbox._ensure_fresh()
    path = toolbox.trace_path("Proxy", "LLMClient.chat")["path"]
    assert path is not None
    qnames = [p["qualified_name"] for p in path]
    assert "LLMClient.chat" in qnames


def test_code_search_import_hits(toolbox):
    """Package names used only in imports (axios/pydantic) must surface."""
    write(WORK / "src/uses_pkg.py", "import aiohttp_async\ndef f():\n    return aiohttp_async.get('x')\n")
    toolbox._ensure_fresh()
    hits = toolbox.code_search("aiohttp_async")
    kinds = {h["kind"] for h in hits["results"]}
    assert "import" in kinds