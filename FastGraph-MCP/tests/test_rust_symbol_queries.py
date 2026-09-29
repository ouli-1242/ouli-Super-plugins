"""Rust/C++ symbol queries: separator, generic args, callee rows, signature shape.

Found on ripgrep and bat: `GlobSet.matches` returned not_found because Rust
stores `GlobSet::matches` (and `::` was not among the spellings the tool
description advertised); `Controller::print_file` returned not_found because the
impl block stores `Controller<'_>::print_file`; `symbol_info` listed one written
call twice; and signatures were stored with the source's CRLF and continuation
lines inside them.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.graph import find_symbols
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

WORK = Path(__file__).resolve().parent / "work_rust_queries"

CTRL = """\
pub struct GlobSet;

impl GlobSet {
    pub fn matches(&self, p: &str) -> u32 {
        self.matches_candidate(p)
    }

    fn matches_candidate(&self, p: &str) -> u32 {
        0
    }
}

pub struct Controller<R> {
    reader: R,
}

impl Controller<u8> {
    pub fn print_file(&self, name: &str, width: u8, paging: bool) -> u32 {
        0
    }
}
"""


def _tool() -> Toolbox:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "lib.rs").write_text(CTRL, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    return Toolbox(WORK, db, Indexer(WORK, db))


def test_dot_and_slash_forms_find_the_colon_qualified_name():
    tb = _tool()
    for query in ("GlobSet.matches", "GlobSet/matches", "GlobSet::matches"):
        hits = find_symbols(tb.db, query)
        assert hits, query
        assert hits[0]["qualified_name"] == "GlobSet::matches", query
    tb.close()


def test_generic_receiver_matches_when_pasted_without_it():
    tb = _tool()
    # code_search reports `Controller<u8>::print_file`; the caller pastes the
    # method path it is reading in the source
    for query in ("Controller::print_file", "Controller.print_file"):
        hits = find_symbols(tb.db, query)
        assert hits, query
        assert hits[0]["qualified_name"] == "Controller<u8>::print_file", query
    tb.close()


def test_one_written_call_is_one_callee_row():
    tb = _tool()
    info = tb.symbol_info("GlobSet::matches")
    callees = info["matches"][0]["callees"]
    assert [c["target"] for c in callees] == ["matches_candidate"], callees
    tb.close()


def test_signatures_are_stored_one_line():
    tb = _tool()
    for sym in tb.file_symbols("lib.rs")["symbols"]:
        sig = sym["signature"]
        assert "\n" not in sig and "\r" not in sig, sig
        assert "((" not in sig, sig
    sig = find_symbols(tb.db, "Controller<u8>::print_file")[0]
    assert sig["signature"] == "fn print_file(&self, name: &str, width: u8, paging: bool)"
    tb.close()
