"""Relevance ranking and the CJK trigram index.

Both live inside SQLite, so neither can be checked by reading the response shape:
a wrong order and a right order both return the same fields, and an empty CJK result
looks exactly like "this repo has no Chinese docs". These tests therefore assert on
*order* and on *which index answered*.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB, FTS_CJK_REV
from fastgraph.index import Indexer
from fastgraph.search import code_search

# `src/wide.py` wins on path_rank (0 = shipped source) and on path order, so any hit
# that outranks it here did so on text relevance alone. Both docs mention `throttle`;
# the difference is that one of it is *about* it.
WEAK = '''\
def alpha(item):
    """Adapter that forwards to the registry, keeps a throttle for the caller,
    then to the stored configuration object, then to whichever callback the
    caller supplied, and finally back through the same path it came in on,
    which is how the value arrives here.
    """
    return item
'''

STRONG = '''\
def beta(item):
    """throttle. throttle. throttle."""
    return item
'''


def _index(root: Path, files: dict[str, str]) -> DB:
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = DB(root)
    Indexer(root, db).refresh()
    return db


@pytest.fixture
def build(tmp_path):
    """Index a dict of files and hand back the DB, closed at teardown: on Windows an
    open handle is what stops pytest from reclaiming tmp_path."""
    opened: list[DB] = []

    def _build(files: dict[str, str]) -> DB:
        db = _index(tmp_path, files)
        opened.append(db)
        return db

    yield _build
    for db in opened:
        try:
            db.close()
        except Exception:
            pass  # a test that closed it on purpose (the upgrade case) is not a failure


def _ids(hits: list[dict]) -> list[str]:
    return [h["symbol"] for h in hits]


# ---------------------------------------------------------------- step 0: ranking


def test_doc_hits_rank_by_relevance_not_by_path(build):
    db = build({"src/wide.py": WEAK, "tests/note.py": STRONG})
    names = _ids(code_search(db, "throttle", limit=5))
    assert "beta" in names and "alpha" in names, names
    assert names.index("beta") < names.index("alpha"), (
        "the symbol whose docstring is *about* throttle lost to the one that "
        "mentions it once in a long doc -- that is path order, not relevance"
    )


def test_equal_relevance_still_breaks_ties_by_path(build):
    """Same docstring, same name length, same path shape: bm25 cannot separate them,
    so the shipped-source copy has to win on the tiebreak, not on rowid luck."""
    same = 'def gamma(item):\n    """retry budget accounting"""\n    return item\n'
    other = 'def delta(item):\n    """retry budget accounting"""\n    return item\n'
    db = build({"tests/core/app.py": other, "src/core/app.py": same})
    names = _ids(code_search(db, "budget", limit=5))
    assert {"gamma", "delta"} <= set(names), names
    assert names.index("gamma") < names.index("delta")


def test_kind_column_does_not_outrank_prose(build):
    """`kind` is an indexed column holding "function"/"class", so a query for those
    English words matches every row of that kind in the repository.

    The fixture puts the noise file first in *path* order, so this asserts the ranking
    rather than the scan order: the one symbol whose docstring actually discusses
    "function" must lead. (Measured: the near-zero `kind` weight is not what wins here
    -- `explain` also carries kind="function", so it matches two columns and beats a
    kind-only row either way. The weight is there so a kind-only row can never beat a
    prose row on a row where the prose does not also match.)
    """
    noisy = "".join(f"def op{i}():\n    return {i}\n" for i in range(30))
    db = build(
        {
            "src/aaa_noise.py": noisy,
            "src/zz_docs.py": 'def explain(x):\n    """How the function registry is wired up."""\n    return x\n',
        }
    )
    names = _ids(code_search(db, "function", limit=5))
    assert names and names[0] == "explain", names


# ---------------------------------------------------------------- step 1: CJK index


CJK_DOC = '''\
class Auth:
    def login(self, user, pw):
        """登录限流策略：同一账号六次失败后锁十分钟。"""
        return pw


def unrelated(x):
    """普通的辅助函数，没有提到登录限流。"""
    return x
'''


def test_cjk_doc_query_hits_the_symbol(build):
    db = build({"src/auth.py": CJK_DOC})
    names = _ids(code_search(db, "登录限流策略", limit=5))
    assert "login" in names, names


def test_cjk_query_ands_its_terms(build):
    """The LIKE fallback matched a *single* CJK token, so '登录限流 缓存键' returned any
    doc that mentioned either one. The trigram index requires both in the same symbol."""
    both = (
        "class Auth:\n"
        "    def login(self, user, pw):\n"
        '        """登录限流策略：按缓存键计数，六次失败后锁十分钟。"""\n'
        "        return pw\n"
    )
    only_one = 'def cache_note(x):\n    """这里只讲缓存键的选型。"""\n    return x\n'
    db = build({"src/auth.py": both, "src/cache.py": only_one})
    names = _ids(code_search(db, "登录限流 缓存键", limit=10))
    assert "login" in names, names
    assert "cache_note" not in names, (
        "a doc that carries only one of the two terms matched: the query went "
        "through the single-token LIKE path instead of the trigram index"
    )
    # the second term on its own does reach it: the AND is the query, not the index
    assert "cache_note" in _ids(code_search(db, "缓存键", limit=10))


def test_trigram_index_holds_only_non_ascii_rows(build):
    """An English-only repository must not pay for the second index: duplicating every
    docstring into a trigram table would grow the file for provably zero benefit."""
    ascii_doc = 'def plain(x):\n    """An ordinary English docstring."""\n    return x\n'
    db = build({"src/plain.py": ascii_doc, "src/auth.py": CJK_DOC})
    total = db.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    cjk = db.conn.execute("SELECT COUNT(*) FROM fts_cjk").fetchone()[0]
    assert cjk > 0, "the Chinese rows are missing"
    assert cjk < total, f"every row was mirrored ({cjk}/{total}): the ASCII filter is off"


def test_short_cjk_query_still_works(build):
    """Two characters is below one trigram, so this query cannot be answered by the
    index; the LIKE fallback has to stay reachable rather than being deleted."""
    db = build({"src/auth.py": CJK_DOC})
    names = _ids(code_search(db, "锁十分钟", limit=5))
    assert "login" in names, names


def test_cjk_search_survives_a_build_without_trigram(tmp_path, monkeypatch):
    """The fallback is not decoration: SQLite's version follows the interpreter build,
    so some real machines will not have the trigram tokenizer at all."""
    import fastgraph.db as db_mod

    monkeypatch.setattr(db_mod, "_TRIGRAM", False)
    db = _index(tmp_path, {"src/auth.py": CJK_DOC})
    try:
        assert not db.has_cjk_index()
        assert db.cjk_match('"登录限流"', 10) == []
        names = _ids(code_search(db, "登录限流策略", limit=5))
        assert "login" in names, names
    finally:
        db.close()


def test_index_built_before_the_table_exists_gets_it(build, tmp_path):
    """Simulate the upgrade: an otherwise healthy index whose trigram table is empty
    and whose revision marker is missing. `_heal_fts` will not fire for it (rowids are
    aligned), so only the once-per-revision rebuild can fill it."""
    db = build({"src/auth.py": CJK_DOC})
    db.conn.execute("DELETE FROM fts_cjk")
    db.conn.execute("UPDATE meta SET value='' WHERE key='fts_cjk_rev'")
    db.conn.commit()
    assert db.cjk_match('"登录限流"', 10) == []
    db.close()

    reopened = DB(tmp_path)
    try:
        assert reopened.cjk_match('"登录限流"', 10), "the trigram index stayed empty"
        assert reopened.get_meta("fts_cjk_rev") == FTS_CJK_REV
        assert "login" in _ids(code_search(reopened, "登录限流策略", limit=5))
    finally:
        reopened.close()


def test_incremental_edit_keeps_both_indexes_in_sync(build, tmp_path):
    """A re-parsed file reuses fresh rowids; the old slice has to disappear from the
    trigram table too, or a deleted Chinese docstring keeps answering queries."""
    db = build({"src/auth.py": CJK_DOC})
    src = tmp_path / "src" / "auth.py"
    src.write_text(
        'class Auth:\n    def login(self, user, pw):\n        """现在只校验密码长度。"""\n        return pw\n',
        encoding="utf-8",
    )
    st = src.stat()
    os.utime(src, (st.st_atime + 5, st.st_mtime + 5))
    Indexer(tmp_path, db).refresh()
    assert "login" not in _ids(code_search(db, "登录限流策略", limit=10)), (
        "the removed docstring is still indexed"
    )
    assert "login" in _ids(code_search(db, "密码长度", limit=10))
