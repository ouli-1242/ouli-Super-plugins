"""Same-named symbols: shipped source must rank above tests and fixtures.

Found on real repos: `diff` resolved to preact's bundled test fixture,
`AssertionResult` to an empty stub inside gtest_unittest.cc, `createStore` to a
closure inside a test file. All three returned *a* definition confidently, which
reads as an answer but points the caller at the wrong file.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.config import is_test_path, path_rank
from fastgraph.db import DB
from fastgraph.graph import find_symbols
from fastgraph.index import Indexer
from fastgraph.search import code_search

WORK = Path(__file__).resolve().parent / "work_ranking"

REAL = """\
def diff(a, b):
    return a - b
"""

# a vendored legacy build and a test-local stub, both declaring the same name
FIXTURE = "function diff(a, b) { return 0; }\n"
STUB = "def diff(x):\n    return None  # test stub\n"


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _index(files: dict[str, str]) -> DB:
    _rmtree(WORK)
    for rel, text in files.items():
        p = WORK / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    return db


def test_source_definition_wins_over_fixture_and_test():
    # index order is alphabetical, so `tests/` is written first: without a path
    # prior it is also the first match
    db = _index({
        "tests/fixtures/legacy.py": STUB,
        "src/core.py": REAL,
        "z_last.py": "diff = 1\n",
    })
    assert find_symbols(db, "diff")[0]["path"] == "src/core.py"
    assert code_search(db, "diff", limit=5)[0]["file"] == "src/core.py"
    db.close()


def test_js_test_file_by_name_shape():
    db = _index({
        "src/diff.js": "export function diff(a, b) {}\n",
        "src/diff.test.js": "function diff(a, b) {}\n",
        "vendor/legacy/diff.js": "function diff(a, b) {}\n",
    })
    top = find_symbols(db, "diff", limit=10)
    assert top[0]["path"] == "src/diff.js"
    # `_test`/`.spec` name shapes and fixture dirs are noise even under src/
    assert is_test_path("src/diff.test.js")
    assert is_test_path("packages/shared/__tests__/x.spec.ts")
    assert is_test_path("go/mux_test.go")
    assert is_test_path("tests/conftest.py")
    assert is_test_path("src/model/OwnerTests.java")
    # ...but a name that merely *contains* "test" is still source: the
    # substring rule this replaced got these wrong
    assert not is_test_path("src/latest.py")
    assert not is_test_path("src/contests.ts")
    assert not is_test_path("src/LatestNews.jsx")
    assert not is_test_path("src/attestation.rs")
    db.close()


def test_path_rank_tiers():
    assert path_rank("src/a.py") == 0
    assert path_rank("crates/core/src/main.rs") == 0
    assert path_rank("main.py") == 1
    assert path_rank("tests/a.py") == 3
    assert path_rank("src/__tests__/a.ts") == 3  # inside source, still a test
    # the substring check this replaced flagged any path *containing* "test"
    assert not is_test_path("src/latest_news.js")
    assert not is_test_path("src/requests.py")
    # package-name words are not demo dirs: `samples` in the spring namespace
    # ranked all of spring-petclinic's source as test code, and `example` is the
    # Android default package
    assert path_rank("src/main/java/org/springframework/samples/petclinic/Owner.java") == 0
    assert path_rank("com/example/app/MainActivity.java") == 0
    # ...while a repo-level examples/ or docs/ tree stays demoted
    assert path_rank("examples/demo/src/App.jsx") == 3
    assert path_rank("docs/guide.md") == 3
