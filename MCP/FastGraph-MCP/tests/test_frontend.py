"""Test Vue / Svelte single-file-component extraction."""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer


@pytest.fixture(scope="module")
def db():
    import shutil as _sh

    work = Path(__file__).resolve().parent / "work_frontend"
    if work.exists():
        _sh.rmtree(work)
    work.mkdir(parents=True)
    (work / "components").mkdir()
    (work / "components" / "Login.vue").write_text(
        """<template>
  <button @click="doLogin">Login</button>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { authApi } from '../api/auth'

const loading = ref(false)

async function doLogin() {
  loading.value = true
  const ok = await authApi.login('u', 'p')
  loading.value = false
  return ok
}

export { doLogin }
</script>
""",
        encoding="utf-8",
    )
    (work / "components" / "Counter.svelte").write_text(
        """<script>
  let count = 0
  export function increment() {
    count += 1
    return count
  }
  function getTotal(a, b) {
    return a + b
  }
</script>

<button on:click={increment}>{count}</button>
""",
        encoding="utf-8",
    )

    fresh = DB(work)
    Indexer(work, fresh).refresh()
    yield fresh
    fresh.close()
    _sh.rmtree(work, ignore_errors=True)


def test_vue_script_symbols(db):
    rows = db.conn.execute(
        "SELECT s.name, s.kind, s.qualified_name, s.start_line, f.path "
        "FROM symbols s JOIN files f ON f.id = s.file_id"
    ).fetchall()
    names = {r[0] for r in rows}
    assert "doLogin" in names, rows
    assert "useAuth" not in names  # imported symbol is not a local def


def test_vue_symbol_line_map(db):
    """Symbol line must refer to the ORIGINAL .vue line, not the extracted script."""
    row = db.conn.execute(
        "SELECT s.start_line, f.path FROM symbols s JOIN files f ON f.id = s.file_id "
        "WHERE s.name = 'doLogin'"
    ).fetchone()
    assert row is not None
    assert row[1].endswith("Login.vue")
    assert row[0] == 11  # `async function doLogin()` sits on line 11 of the .vue source


def test_svelte_functions(db):
    names = {
        r[0]
        for r in db.conn.execute("SELECT name FROM symbols WHERE name IN ('increment', 'getTotal')")
    }
    assert names == {"increment", "getTotal"}


def test_language_counts(db):
    langs = {
        r[0]: r[1]
        for r in db.conn.execute("SELECT language, COUNT(*) FROM files GROUP BY language")
    }
    assert langs.get("vue") == 1
    assert langs.get("svelte") == 1