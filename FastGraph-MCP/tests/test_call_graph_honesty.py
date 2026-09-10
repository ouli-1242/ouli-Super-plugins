"""Call-graph honesty: precision, recall, and visibility of unresolved edges.

Regression guards for the adversarial review findings:

- an empty `callers` list used to be indistinguishable from "nothing calls
  this", because edges that could not be resolved were silently dropped;
- `Type::assoc` targets (Rust, and any `::` form) never entered the candidate
  set, so associated-function calls were never resolved;
- two same-named classes in different modules made the class-name import hint
  useless, so `Svc().run()` resolved to nothing;
- "same directory" was treated as evidence, which linked `req.save()` to an
  unrelated `User.save` in that directory;
- text-fold callers were reported as if they were stored call edges;
- files above MAX_FILE_SIZE were skipped with no trace anywhere.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB  # noqa: E402
from fastgraph.index import Indexer  # noqa: E402
from fastgraph.tools import Toolbox  # noqa: E402


def _project(tmp_path: Path, files: dict[str, str]):
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
    return root, db, tb


def _callers(tb, name):
    return [(r["file"], r["qualified_name"]) for r in tb.find_callers(name)["callers"]]


# ---------------- same-named classes: resolve via the imported file ---------

SAME_NAME = {
    "pkg/__init__.py": "",
    "pkg/a.py": "class Svc:\n    def run(self):\n        return 1\n",
    "pkg/b.py": "class Svc:\n    def run(self):\n        return 2\n",
    "pkg/typed.py": "from pkg.a import Svc\n\n\ndef go_typed():\n    return Svc().run()\n",
}


def test_same_named_class_resolves_through_the_imported_file(tmp_path):
    """Two classes called `Svc`: only the imported one is a candidate.

    The class-name hint (`"svc" in import text`) matched both and gave up, so
    `Svc().run()` was left unresolved even though the caller imports exactly
    one `Svc`.
    """
    root, db, tb = _project(tmp_path, SAME_NAME)
    callers = _callers(tb, "run")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert ("pkg/typed.py", "go_typed") in callers, callers


# ---------------- unrelated receiver: no same-directory link ----------------

UNRELATED = {
    "pkg/__init__.py": "",
    "pkg/models.py": "class User:\n    def save(self):\n        return 1\n",
    "pkg/api.py": "def handle(req):\n    return req.save()\n",
}


def test_unrelated_receiver_is_not_linked_to_a_same_directory_method(tmp_path):
    """`req.save()` must not become a caller of a local `User.save`.

    `req` is any object; "the owner lives in the same directory" was accepted
    as evidence and produced a caller that does not exist.
    """
    root, db, tb = _project(tmp_path, UNRELATED)
    callers = _callers(tb, "User.save")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert callers == [], callers


def test_unresolved_incoming_is_reported(tmp_path):
    """`find_callers` must say that edges name the symbol but did not resolve."""
    root, db, tb = _project(tmp_path, UNRELATED)
    out = tb.find_callers("User.save")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert out["count"] == 0
    assert out["unresolved_incoming"] >= 1, out
    assert "hint" in out


def test_unresolved_outgoing_is_reported(tmp_path):
    """`find_callees` must report callees it dropped as unresolvable."""
    root, db, tb = _project(
        tmp_path,
        {"m.py": "def caller():\n    return missing_thing()\n"},
    )
    out = tb.find_callees("caller")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert out["count"] == 0
    assert out["unresolved_outgoing"] >= 1, out


# ---------------- `Type::assoc` targets -------------------------------------

RUST_ASSOC = {
    "Cargo.toml": '[package]\nname = "demo"\n',
    "src/main.rs": (
        "use crate::cmd::Command;\n"
        "\n"
        "fn main() {\n"
        "\tlet _ = Command::new();\n"
        "}\n"
    ),
    "src/cmd.rs": (
        "pub struct Command;\n"
        "\n"
        "impl Command {\n"
        "\tpub fn new() -> Self {\n"
        "\t\tCommand\n"
        "\t}\n"
        "}\n"
    ),
}


def test_rust_associated_function_call_resolves(tmp_path):
    """`Command::new()` never resolved: `::` was not a candidate separator."""
    root, db, tb = _project(tmp_path, RUST_ASSOC)
    callers = _callers(tb, "new")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert ("src/main.rs", "main") in callers, callers


# ---------------- class-internal calls --------------------------------------

INTERNAL = {
    "pkg/__init__.py": "",
    "pkg/a.py": (
        "class A:\n"
        "    def helper(self):\n"
        "        return 1\n"
        "\n"
        "    def run(self):\n"
        "        return self.helper()\n"
    ),
    "pkg/b.py": "class B:\n    def helper(self):\n        return 2\n",
}


def test_class_internal_call_prefers_its_own_class(tmp_path):
    """`self.helper()` inside `A.run` is `A.helper`, not `B.helper`.

    The parser drops the `self.` receiver, so the bare name `helper` has two
    candidates with no import to tell them apart; the caller's own class picks
    the right one.
    """
    root, db, tb = _project(tmp_path, INTERNAL)
    callers = _callers(tb, "helper")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert ("pkg/a.py", "A.run") in callers, callers


def test_super_call_is_not_a_self_link(tmp_path):
    """`super().login()` inside `OAuthService.login` targets the base method."""
    root, db, tb = _project(
        tmp_path,
        {
            "svc.py": (
                "class AuthService:\n"
                "    def login(self):\n"
                "        return 1\n"
                "\n"
                "class OAuthService(AuthService):\n"
                "    def login(self):\n"
                "        return super().login()\n"
            ),
        },
    )
    cycles = tb.module_cycles(max_cycles=10)["count"]
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert cycles == 0, cycles


# ---------------- text folds are labelled -----------------------------------

TEXT_FOLD = {
    "pkg/a.py": "class Widget:\n    def render(self):\n        return 1\n",
    "pkg/b.py": "class Widget:\n    def render(self):\n        return 2\n",
    "pkg/c.py": "def make():\n    return Widget()\n",
}


def test_text_fold_callers_are_labelled(tmp_path):
    """A caller matched by raw text (not a stored edge) must say so.

    `Widget()` cannot be resolved -- two classes carry the name -- so the only
    thing linking `make` to them is the raw target text. Reporting it as a
    stored call edge would overstate the evidence.
    """
    root, db, tb = _project(tmp_path, TEXT_FOLD)
    out = tb.find_callers("Widget")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert out["count"] >= 1, out
    assert all(c["via"] == "text" for c in out["callers"]), out["callers"]


def test_a_receiver_named_like_the_class_is_accepted_as_evidence(tmp_path):
    """`thing.do_something()` is linked on the strength of the name alone.

    The receiver may be any object -- this is still a guess, just the best
    available one (`via` is "resolved", not "text", because the call text names
    the owner). Documented here so the behaviour is a decision, not an accident:
    without type inference the alternative is to resolve nothing at all.
    """
    root, db, tb = _project(
        tmp_path,
        {
            "pkg/thing.py": "class thing:\n    def do_something(self):\n        return 1\n",
            "pkg/other.py": "def f():\n    thing = object()\n    return thing.do_something()\n",
        },
    )
    callers = _callers(tb, "thing")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert ("pkg/other.py", "f") in callers, callers


# ---------------- skipped files are visible ---------------------------------


def test_oversized_files_are_reported(tmp_path):
    """A file above MAX_FILE_SIZE is not parsed and not a parse error either."""
    big = "# padding line\n" * 200_000  # ~3 MB
    root, db, tb = _project(
        tmp_path,
        {
            "big.py": big,
            "small.py": "def small():\n    return 1\n",
        },
    )
    overview = tb.project_overview()
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    skipped = overview.get("skipped_large_files")
    assert skipped and skipped["count"] == 1, overview
    assert skipped["sample"][0] == "big.py", skipped
    assert "big.py" not in [e["file"] for e in overview["parse_errors"]]


def test_unknown_symbol_says_found_false(tmp_path):
    """A symbol that is not in the index must not read as "found, no callers"."""
    root, db, tb = _project(tmp_path, UNRELATED)
    out = tb.find_callers("nope")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert out["found"] is False
    assert out["count"] == 0
