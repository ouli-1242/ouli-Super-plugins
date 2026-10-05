"""SQLite storage: files / symbols / relations / file_imports + FTS5."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from pathlib import Path

from fastgraph.config import ensure_ignore_template

# DDL (SCHEMA + migrations) needs the write lock. A second project window opening
# the same index, or WAL recovery after a killed process, can be holding it -- and
# an OperationalError raised here escapes before the MCP handshake, so the client
# can only report "Process Exited" with no reason. Waiting beats dying: the
# steady-state query timeout stays short (a hung query should surface fast), only
# the startup DDL waits.
DDL_BUSY_TIMEOUT_MS = 20_000
QUERY_BUSY_TIMEOUT_MS = 5_000
DDL_RETRIES = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id         INTEGER PRIMARY KEY,
    path       TEXT NOT NULL UNIQUE,
    language   TEXT NOT NULL,
    hash       TEXT NOT NULL DEFAULT '',
    mtime      REAL NOT NULL DEFAULT 0,
    size       INTEGER NOT NULL DEFAULT 0,
    content_capped INTEGER NOT NULL DEFAULT 0  -- literal corpus truncated
);

CREATE TABLE IF NOT EXISTS symbols (
    id             INTEGER PRIMARY KEY,
    file_id        INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL,
    qualified_name TEXT NOT NULL DEFAULT '',
    signature      TEXT NOT NULL DEFAULT '',
    doc            TEXT NOT NULL DEFAULT '',
    start_line     INTEGER NOT NULL,
    end_line       INTEGER NOT NULL,
    start_col      INTEGER NOT NULL DEFAULT 0,
    end_col        INTEGER NOT NULL DEFAULT 0,
    decorated      INTEGER NOT NULL DEFAULT 0,
    param_types    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sym_name    ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_sym_qname   ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_sym_file    ON symbols(file_id);

CREATE TABLE IF NOT EXISTS relations (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    target      TEXT NOT NULL,
    rtype       TEXT NOT NULL,          -- calls | inherits
    target_id   INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
    line        INTEGER NOT NULL DEFAULT 0,
    tried       INTEGER NOT NULL DEFAULT 0  -- the resolver already gave up on it
);
CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_id);
-- exact-text lookups (`_callers_with_class` folding `target = ?`) used to
-- scan the whole relations table; the prefix-wildcard LIKEs stay scans, but
-- the equality branch is the common one on constructor/qualified folds.
CREATE INDEX IF NOT EXISTS idx_rel_target_text ON relations(target);

CREATE TABLE IF NOT EXISTS file_imports (
    id       INTEGER PRIMARY KEY,
    file_id  INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    text     TEXT NOT NULL,
    kind     TEXT NOT NULL DEFAULT '',
    line     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fimp_file ON file_imports(file_id);

-- Materialized import->file resolution, computed by the indexer at refresh
-- time. file_deps / module_cycles / layering used to re-run the resolver over
-- every import of every file on every call (O(files x imports) per query);
-- with this table they become indexed reads. Rebuilt wholesale whenever the
-- *file set* changes (a new file can resolve a previously-unresolvable
-- import); content-only edits only recompute the changed file's own rows.
CREATE TABLE IF NOT EXISTS import_edges (
    file_id  INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    target   TEXT NOT NULL,
    line     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_impedges_file   ON import_edges(file_id);
CREATE INDEX IF NOT EXISTS idx_impedges_target ON import_edges(target);

CREATE TABLE IF NOT EXISTS parse_errors (
    path   TEXT PRIMARY KEY,
    error  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS template_refs (
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name    TEXT NOT NULL,
    PRIMARY KEY (file_id, name)
);

CREATE TABLE IF NOT EXISTS line_content (
    id      INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    line    INTEGER NOT NULL,
    kind    TEXT NOT NULL,
    text    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lc_file ON line_content(file_id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_symbols USING fts5(
    name, qualified_name, doc, kind, signature,
    file_path
);
"""

# A second FTS table over the same rows, tokenized by *trigram* instead of by word.
# It exists for one reason: `unicode61` does not split a CJK run, so a whole Chinese
# docstring is one token and `"限流"*` never matches it. Today that case is served by
# `LOWER(s.doc) LIKE '%…%'` -- a full scan of the symbols table, and it cannot reach
# `name`/`qualified_name` at all. Trigrams index those too and turn the scan into a
# MATCH.
#
# Only rows carrying non-ASCII text go in. An English-only repository would otherwise
# duplicate every docstring in the file for zero benefit, and trigram indexes are
# bigger than word indexes; with the filter, the cost on such a repo is one empty
# table. ASCII queries stay on fts_symbols, where word-token prefix matching is the
# better behaviour, so switching the existing table was never on the table.
FTS_CJK_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS fts_cjk USING fts5(
    name, qualified_name, doc, signature,
    file_path,
    tokenize = 'trigram'
);
"""

# Bump when the row filter or the column list changes: it is what tells an existing
# index that its fts_cjk content is stale and has to be rebuilt from `symbols`.
FTS_CJK_REV = "1"

_TRIGRAM: bool | None = None


def trigram_supported() -> bool:
    """Does this interpreter's SQLite have a working FTS5 trigram tokenizer?

    Probed by *behaviour*, not by version number: the bundled SQLite follows the
    interpreter build, so 3.34+ is necessary but not sufficient (FTS5 can also be
    compiled out), and a table created against a tokenizer that silently does nothing
    would answer every CJK query with an empty result forever.
    """
    global _TRIGRAM
    if _TRIGRAM is None:
        try:
            probe = sqlite3.connect(":memory:")
            probe.execute("CREATE VIRTUAL TABLE p USING fts5(x, tokenize='trigram')")
            probe.execute("INSERT INTO p VALUES ('登录限流策略')")
            # the needle is three characters because a trigram cannot express fewer:
            # probing with a 2-char term reports "unsupported" on a build where the
            # tokenizer works perfectly (and a table that matches nothing would look
            # like a data problem, not a startup probe problem)
            _TRIGRAM = bool(
                probe.execute("SELECT 1 FROM p WHERE p MATCH ?", ('"限流策"',)).fetchone()
            )
            probe.close()
        except Exception:
            _TRIGRAM = False
    return _TRIGRAM


def _has_cjk(*texts: object) -> bool:
    """True when any of these strings contains a non-ASCII character."""
    return any(t and not str(t).isascii() for t in texts)

# Project-memory layer (on by default; FASTGRAPH_MEMORY=0 parks it). Separate
# file, separate schema:
# index.sqlite's contract is "delete it and the index rebuilds" (reindex
# full=true, INDEX_VERSION upgrades -- index.py), and notes must not be
# collateral damage of that. No FK to the code tables on purpose: a note
# outlives the symbol it was pinned to, which is exactly what makes an
# orphaned note reportable rather than silently gone.
#
# AUTOINCREMENT is load-bearing, not style: `forget(id=…)` addresses a note by this
# column, and a plain INTEGER PRIMARY KEY hands out max(rowid)+1 -- delete the newest
# note and the next insert reuses its id, so a stale id copied from an old `recall`
# would delete a different note than the one it named.
MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    anchor_type TEXT NOT NULL,          -- symbol | file | module | project
    anchor_key  TEXT NOT NULL,          -- canonical form, see memory.symbol_anchor
    kind        TEXT NOT NULL,          -- decision | warning | todo | context | adr
    body        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_anchor ON notes(anchor_type, anchor_key);
CREATE INDEX IF NOT EXISTS idx_notes_kind   ON notes(kind);

-- Graph snapshots are what `what_changed` diffs. A hash cannot answer "which
-- symbols appeared / which call edges broke", so the normalized sets themselves
-- are stored (zlib; a few tens of thousands of edges compress to ~100KB).
CREATE TABLE IF NOT EXISTS graph_snapshot (
    id          INTEGER PRIMARY KEY,
    label       TEXT NOT NULL,          -- caller-chosen baseline name
    ref         TEXT NOT NULL DEFAULT '',  -- git rev recorded alongside
    complete    INTEGER NOT NULL,       -- 1 = built from a finished index
    symbol_blob BLOB NOT NULL,
    edge_blob   BLOB NOT NULL,
    cycle_blob  BLOB NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_label ON graph_snapshot(label, id);
"""


def _stem_of(path: str) -> str:
    """``src/pkg/mod.py`` -> ``src.pkg.mod`` (lowercased, extension dropped)."""
    return path.rsplit(".", 1)[0].replace("/", ".").lower()


class DB:
    def __init__(
        self,
        root: Path | str,
        filename: str = "index.sqlite",
        schema: str = SCHEMA,
        code_index: bool = True,
    ):
        """Open one SQLite file under `<root>/.fastgraph/`.

        `code_index=False` (the memory store) skips the index-only startup work:
        `_migrate_schema` reads symbols/relations PRAGMA tables, `_heal_fts`
        rebuilds FTS -- neither exists in MEMORY_SCHEMA, and running them there
        would either error or create the code tables inside memory.sqlite.
        """
        self.root = Path(root).resolve()
        self.index_dir = self.root / ".fastgraph"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        ensure_ignore_template(self.index_dir)
        self.db_path = self.index_dir / filename
        self._schema = schema
        self._code_index = code_index
        # the memory store has no symbols table to index, so it never grows FTS.
        # The table is appended to the schema text rather than being part of SCHEMA:
        # on an SQLite build without trigram support, executing that DDL would fail
        # the entire startup instead of one optional index.
        self._cjk_index = bool(code_index and trigram_supported())
        if self._cjk_index:
            self._schema = schema + FTS_CJK_SCHEMA
        self._local = threading.local()
        self._all_conns: list[sqlite3.Connection] = []
        self._stem_suffix_map: dict[str, list[str]] | None = None
        self._dir_stem_map: dict[str, dict[str, list[str]]] | None = None
        conn = self._new_conn()
        self._local.conn = conn
        self._all_conns.append(conn)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._init_storage(conn)

    def _init_storage(self, conn: sqlite3.Connection) -> None:
        """Create/upgrade the schema and heal FTS, waiting out a transient writer.

        Every write the startup performs lives in here on purpose: migration,
        SCHEMA and the FTS rebuild all need the write lock, and an
        OperationalError from any of them escapes before the MCP handshake --
        which a client reports only as "Process Exited", with nothing to act on.
        So all three retry together, then the connection drops back to the short
        query timeout (a hung *query* should still surface fast).
        """
        conn.execute(f"PRAGMA busy_timeout={DDL_BUSY_TIMEOUT_MS}")
        try:
            for attempt in range(DDL_RETRIES):
                try:
                    if self._code_index:
                        self._migrate_schema()
                    conn.executescript(self._schema)
                    conn.commit()
                    if self._code_index:
                        self._heal_fts()
                        self._ensure_fts_cjk()
                        conn.commit()
                    return
                except sqlite3.OperationalError as e:
                    if "locked" not in str(e).lower() or attempt == DDL_RETRIES - 1:
                        raise
                    conn.rollback()
                    time.sleep(0.5)
        finally:
            conn.execute(f"PRAGMA busy_timeout={QUERY_BUSY_TIMEOUT_MS}")

    def _new_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # cross-process writers (a second MCP instance, or a script + the
        # server) wait up to 5s instead of failing instantly with
        # "database is locked" (default busy_timeout is 0)
        conn.execute(f"PRAGMA busy_timeout={DDL_BUSY_TIMEOUT_MS}")
        try:
            conn.executescript(self._schema)
            conn.commit()
        finally:
            conn.execute(f"PRAGMA busy_timeout={QUERY_BUSY_TIMEOUT_MS}")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Per-thread connection (MCP servers dispatch tool calls on a thread
        pool; a single shared sqlite3 connection is not safe there — a second
        execute can corrupt an in-flight cursor iteration, yielding wrong row
        counts or empty rows). All connections share the same WAL database."""
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._new_conn()
            self._local.conn = c
            self._all_conns.append(c)
        return c

    def close(self):
        for c in self._all_conns:
            try:
                c.close()
            except Exception:
                pass
        self._all_conns.clear()

    @contextlib.contextmanager
    def patient_writes(self, ms: int = DDL_BUSY_TIMEOUT_MS):
        """Wait for the write lock instead of dying during a write burst.

        The steady-state 5s timeout is right for a hung query and wrong for a build:
        a second window rebuilding the same import_edges can hold the lock longer
        than that, and the loser raised "database is locked" out of the tool call
        (reproduced with four processes on one index). Same reasoning as the startup
        DDL -- a writer that waits is a writer that finishes. Thread-local like every
        other connection here, so the burst that sets it is the burst that uses it.
        """
        conn = self.conn
        previous = int(conn.execute("PRAGMA busy_timeout").fetchone()[0] or 0)
        conn.execute(f"PRAGMA busy_timeout={int(ms)}")
        try:
            yield
        finally:
            conn.execute(f"PRAGMA busy_timeout={previous or QUERY_BUSY_TIMEOUT_MS}")

    # ---------------- meta ----------------

    def get_meta(self, key: str) -> str | None:
        r = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return r[0] if r else None

    def set_meta(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # ---------------- schema migration ----------------

    def _migrate_schema(self) -> None:
        """Rebuild fts_symbols if it was created contentless (content='').

        Contentless FTS5 tables cannot be DELETE-filtered by column and their
        row column reads back as NULL, which broke search. The new schema is a
        regular FTS5 table; the FTS payload is re-populated lazily by
        register_fts on the next refresh.
        """
        try:
            row = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='fts_symbols'"
            ).fetchone()
        except Exception:
            return
        if row and "content=''" in (row[0] or ""):
            self.conn.execute("DROP TABLE fts_symbols")
        # symbols.decorated: added for decorator/annotation-aware dead-code
        # detection; old indexes lack the column and the INSERT would fail
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(symbols)")}
        if "decorated" not in cols:
            self.conn.execute(
                "ALTER TABLE symbols ADD COLUMN decorated INTEGER NOT NULL DEFAULT 0"
            )
        if "param_types" not in cols:
            self.conn.execute(
                "ALTER TABLE symbols ADD COLUMN param_types TEXT NOT NULL DEFAULT ''"
            )
        # relations.tried: the resolver's "already gave up" marker. Rows created
        # by an older build default to 0, so the first refresh after an upgrade
        # re-runs the full pass once and then settles into the cheap path.
        # files.content_capped: set when a file's string-literal corpus hit the
        # per-file budget. It has to live in the index, not in the parsing
        # process's state: a steady-state query reports the blind spot just as
        # much as the refresh that produced it.
        fcols = {r[1] for r in self.conn.execute("PRAGMA table_info(files)")}
        if "content_capped" not in fcols:
            self.conn.execute(
                "ALTER TABLE files ADD COLUMN content_capped INTEGER NOT NULL DEFAULT 0"
            )
        rcols = {r[1] for r in self.conn.execute("PRAGMA table_info(relations)")}
        if "tried" not in rcols:
            self.conn.execute(
                "ALTER TABLE relations ADD COLUMN tried INTEGER NOT NULL DEFAULT 0"
            )
        # created here, not in SCHEMA: SCHEMA runs first (via _new_conn) and this
        # index references a column older indexes only gain just above
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rel_pending ON relations(tried, rtype) "
            "WHERE target_id IS NULL"
        )

    # ---------------- files ----------------

    def file_map(self) -> dict[str, tuple[float, int]]:
        """path -> (mtime, size), the incremental-change comparison key."""
        return {
            p: (m, s)
            for p, m, s in self.conn.execute("SELECT path, mtime, size FROM files")
        }

    def stem_suffix_map(self) -> dict[str, list[str]]:
        """Dotted-stem suffix -> file paths, for O(1) import resolution.

        ``src/pkg/mod.py`` contributes ``src.pkg.mod``, ``pkg.mod`` and ``mod``,
        so an import of ``pkg.mod`` resolves via a dict lookup instead of a
        scan of the files table. Cached; invalidated whenever the file set
        changes (``upsert_file`` / ``delete_file``). This turns the import
        resolution used by file_deps / module_cycles / project_overview from
        O(files^2) into O(files).
        """
        cached = self._stem_suffix_map
        if cached is not None:
            return cached
        m: dict[str, list[str]] = {}
        for (p,) in self.conn.execute("SELECT path FROM files ORDER BY path"):
            parts = _stem_of(p).split(".")
            for i in range(len(parts)):
                m.setdefault(".".join(parts[i:]), []).append(p)
        self._stem_suffix_map = m
        return m

    def dir_stem_map(self) -> dict[str, dict[str, list[str]]]:
        """Directory -> {extension-less file name -> paths}, for local imports.

        Import resolution prefers the importing file's own directory (then its
        ancestors) before falling back to a repo-wide basename match: a quoted
        ``#include "core.h"`` means the sibling header, and a crate-relative
        ``use crate::util::…`` means the same-directory ``util.rs`` rather than
        a same-named file in another crate. Keys are lowercased, like
        ``stem_suffix_map()``, and cached with the same invalidation.
        """
        cached = self._dir_stem_map
        if cached is not None:
            return cached
        m: dict[str, dict[str, list[str]]] = {}
        for (p,) in self.conn.execute("SELECT path FROM files ORDER BY path"):
            d, _, name = p.rpartition("/")
            m.setdefault(d, {}).setdefault(name.rsplit(".", 1)[0].lower(), []).append(p)
        self._dir_stem_map = m
        return m

    def get_file_id(self, path: str) -> int | None:
        r = self.conn.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
        return r[0] if r else None

    def upsert_file(self, path: str, language: str, hash_: str, mtime: float, size: int) -> int:
        self._stem_suffix_map = None
        self._dir_stem_map = None
        fid = self.get_file_id(path)
        if fid is None:
            cur = self.conn.execute(
                "INSERT INTO files (path, language, hash, mtime, size) VALUES (?,?,?,?,?)",
                (path, language, hash_, mtime, size),
            )
            return int(cur.lastrowid)
        self.conn.execute(
            "UPDATE files SET language=?, hash=?, mtime=?, size=? WHERE id=?",
            (language, hash_, mtime, size, fid),
        )
        return fid

    def delete_file(self, path: str):
        self._stem_suffix_map = None
        self._dir_stem_map = None
        # fts_symbols has no foreign key, so it is NOT covered by the
        # files -> symbols ON DELETE CASCADE and must be cleared explicitly.
        # Otherwise its rows survive as orphans (observed: a rebuild that
        # removed every indexed file left 1676 orphan FTS rows behind), and a
        # later rebuild can collide with the rowids SQLite re-assigns after all
        # symbols are gone.
        self.conn.execute("DELETE FROM fts_symbols WHERE file_path=?", (path,))
        self.conn.execute("DELETE FROM files WHERE path=?", (path,))
        self.conn.execute("DELETE FROM parse_errors WHERE path=?", (path,))

    def file_path(self, file_id: int) -> str | None:
        r = self.conn.execute("SELECT path FROM files WHERE id=?", (file_id,)).fetchone()
        return r[0] if r else None

    # ---------------- symbols ----------------

    def replace_file_symbols(self, file_id: int, symbols: list[dict]) -> None:
        # any relation pointing at this file's old symbols: drop the id link,
        # the text resolver will re-attach after re-index
        old_ids = [
            r[0]
            for r in self.conn.execute(
                "SELECT id FROM symbols WHERE file_id=?", (file_id,)
            )
        ]
        if old_ids:
            self.conn.execute(
                "UPDATE relations SET target_id=NULL WHERE target_id IN (%s)"
                % ",".join("?" * len(old_ids)),
                old_ids,
            )
        self.conn.execute("DELETE FROM symbols WHERE file_id=?", (file_id,))
        if not symbols:
            return
        self.conn.executemany(
            "INSERT INTO symbols (file_id, name, kind, qualified_name, signature, doc, "
            "start_line, end_line, start_col, end_col, decorated, param_types) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    file_id, s["name"], s["kind"], s["qualified_name"], s["signature"],
                    s["doc"], s["start_line"], s["end_line"], s["start_col"], s["end_col"],
                    s.get("decorated", False), s.get("param_types", "") or "",
                )
                for s in symbols
            ],
        )

    def replace_file_import_edges(self, file_id: int, rows: list[tuple[str, int]]) -> None:
        """rows: (resolved target path, import line)."""
        self.conn.execute("DELETE FROM import_edges WHERE file_id=?", (file_id,))
        if rows:
            self.conn.executemany(
                "INSERT INTO import_edges (file_id, target, line) VALUES (?,?,?)",
                [(file_id, t, ln) for t, ln in rows],
            )

    def replace_file_imports(self, file_id: int, imports: list[dict]) -> None:
        self.conn.execute("DELETE FROM file_imports WHERE file_id=?", (file_id,))
        if not imports:
            return
        self.conn.executemany(
            "INSERT INTO file_imports (file_id, text, kind, line) VALUES (?,?,?,?)",
            [(file_id, i["text"], i.get("kind", ""), i.get("line", 0)) for i in imports],
        )

    def replace_file_relations(self, file_id: int, rows: list[tuple[int, int]]) -> None:
        """rows: (source_symbol_id, target_text, rtype, line)"""
        # delete old relations of this file (all symbols cascaded already but
        # relations may reference symbols in other files: they carry no file_id,
        # so delete via source ids).
        self.conn.execute(
            "DELETE FROM relations WHERE source_id IN "
            "(SELECT id FROM symbols WHERE file_id=?)",
            (file_id,),
        )
        if rows:
            self.conn.executemany(
                "INSERT INTO relations (source_id, target, rtype, line) VALUES (?,?,?,?)",
                rows,
            )

    def replace_file_template_refs(self, file_id: int, names: list[str]):
        self.conn.execute("DELETE FROM template_refs WHERE file_id=?", (file_id,))
        if names:
            self.conn.executemany(
                "INSERT OR IGNORE INTO template_refs (file_id, name) VALUES (?, ?)",
                [(file_id, n) for n in names],
            )

    def replace_file_line_content(self, file_id: int, rows: list[tuple[int, str, str]]):
        """rows: (line, kind, text)"""
        self.conn.execute("DELETE FROM line_content WHERE file_id=?", (file_id,))
        if rows:
            self.conn.executemany(
                "INSERT INTO line_content (file_id, line, kind, text) VALUES (?,?,?,?)",
                [(file_id, ln, kind, txt) for ln, kind, txt in rows],
            )

    def symbol_name_to_id(self, file_id: int) -> dict:
        return {
            r[0]: r[1]
            for r in self.conn.execute(
                "SELECT name, id FROM symbols WHERE file_id=?", (file_id,)
            )
        }

    # ---------------- FTS ----------------

    def register_fts(self, file_id: int, path: str, symbols: list[dict]) -> None:
        """Rebuild the FTS index rows for one file.

        fts_symbols is a regular FTS5 table storing payload columns; we keep
        rowid == symbols.id so search can resolve MATCH hits straight to
        symbols by id. Delete this file's rows by rowid, then re-insert.
        """
        if self._heal_fts():
            return  # full rebuild already covers this file's rows
        # A re-indexed file's symbols get fresh rowids (replace_file_symbols
        # deletes and re-inserts them), so deleting only the *new* ids would
        # leave the previous rows behind as orphans that accumulate on every
        # edit. file_path is already stored in the FTS row: delete the file's
        # whole slice, including the empty-symbols case below.
        self.conn.execute("DELETE FROM fts_symbols WHERE file_path = ?", (path,))
        if self._cjk_index:
            self.conn.execute("DELETE FROM fts_cjk WHERE file_path = ?", (path,))
        if not symbols:
            return
        # map symbols to their rowids by (name, kind, start_line): `name` alone
        # is ambiguous when a file has same-named symbols (methods on
        # different classes, overloads).
        sym_rows = self.conn.execute(
            "SELECT id, name, kind, qualified_name, start_line FROM symbols WHERE file_id=?",
            (file_id,),
        ).fetchall()
        key_to_id = {(r[1], r[2], r[3], r[4]): r[0] for r in sym_rows}
        by_name: dict[str, list[int]] = {}
        for sid, name, *_ in sym_rows:
            by_name.setdefault(name, []).append(sid)
        rows = []
        seen_sids: set[int] = set()
        for s in symbols:
            k = (s["name"], s.get("kind", ""), s["qualified_name"], s["start_line"])
            sid = key_to_id.get(k)
            if sid is None:
                # the start_line moved between parse and insert: fall back to
                # an *unambiguous* name match. Rowids are never paired by
                # position -- a shifted list would attach a doc/signature to
                # the wrong symbol and search would then report it at a line
                # that does not contain it.
                named = by_name.get(s["name"], [])
                if len(named) == 1:
                    sid = named[0]
            if sid is None:
                continue
            # key_to_id collapses duplicate (name, kind, qualified_name,
            # start_line) symbols (minified JS) onto one rowid; FTS5 forbids
            # duplicate rowids, so keep the first row per id.
            if sid in seen_sids:
                continue
            seen_sids.add(sid)
            rows.append(
                (
                    sid,
                    s["name"],
                    s["qualified_name"],
                    (s.get("doc") or "")[:400],
                    s.get("kind", ""),
                    (s.get("signature") or "")[:200],
                    path,
                )
            )
        if not rows:
            return
        self.conn.executemany(
            "INSERT INTO fts_symbols "
            "(rowid, name, qualified_name, doc, kind, signature, file_path) "
            "VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        self._write_fts_cjk(rows)

    def _write_fts_cjk(self, rows: list[tuple]) -> None:
        """Mirror the non-ASCII rows into the trigram table (same rowids).

        `rows` is register_fts' 7-tuple shape: (id, name, qualified_name, doc, kind,
        signature, path). The kind column is left out of fts_cjk on purpose -- it is
        ASCII by construction, so a trigram index over it would only ever be noise.
        """
        if not self._cjk_index:
            return
        cjk = [
            (sid, name, qname, doc, sig, path)
            for sid, name, qname, doc, _kind, sig, path in rows
            if _has_cjk(name, qname, doc, sig, path)
        ]
        if cjk:
            self.conn.executemany(
                "INSERT INTO fts_cjk "
                "(rowid, name, qualified_name, doc, signature, file_path) "
                "VALUES (?,?,?,?,?,?)",
                cjk,
            )

    def clear_fts(self) -> None:
        """Drop the whole FTS index.

        Used when the index is rebuilt from scratch: per-file deletes cannot
        remove rows leaked by an older build, and such a stale rowid would
        collide with the ids the rebuild is about to assign (FTS5 rejects a
        duplicate rowid with "constraint failed").
        """
        self.conn.execute("DELETE FROM fts_symbols")
        if self._cjk_index:
            self.conn.execute("DELETE FROM fts_cjk")

    def _fts_aligned(self) -> bool:
        """True when fts rowids match symbols ids (at least one hit)."""
        try:
            r = self.conn.execute(
                "SELECT 1 FROM fts_symbols f JOIN symbols s ON f.rowid = s.id LIMIT 1"
            ).fetchone()
        except Exception:
            return True
        return r is not None

    def _rebuild_fts_cjk(self) -> None:
        """Refill fts_cjk from `symbols`: a SQL pass, no parsing.

        The doc/signature text already lives in the symbols table, so the trigram
        index can be rebuilt without touching source files -- which is what makes an
        upgrade that adds this table cheap.
        """
        if not self._cjk_index:
            return
        self.conn.execute("DELETE FROM fts_cjk")
        self._write_fts_cjk(
            list(
                self.conn.execute(
                    """SELECT s.id, s.name, s.qualified_name, s.doc, s.kind, s.signature, f.path
                       FROM symbols s JOIN files f ON f.id = s.file_id"""
                )
            )
        )

    def _ensure_fts_cjk(self) -> None:
        """Build the trigram index once per revision.

        An index written before fts_cjk existed is otherwise healthy and aligned, so
        `_heal_fts` never fires for it and the CJK tier would silently return nothing
        until every file happened to change. Tied to FTS_CJK_REV rather than to
        INDEX_VERSION on purpose: the version bump means "re-parse everything", and
        this needs only the rows already on disk.
        """
        if not self._cjk_index or self.get_meta("fts_cjk_rev") == FTS_CJK_REV:
            return
        self._rebuild_fts_cjk()
        self.set_meta("fts_cjk_rev", FTS_CJK_REV)

    def has_cjk_index(self) -> bool:
        """Whether `search` may query fts_cjk at all (False on old SQLite builds)."""
        return self._cjk_index

    def cjk_match(self, match: str, limit: int) -> list[tuple[int, float]]:
        """(symbol id, bm25 score) for a trigram MATCH expression, best first.

        [] when the table is unavailable, which reads the same as "no hits" -- so the
        caller decides whether to fall back with `has_cjk_index()`, not by guessing
        from an empty list.
        """
        if not self._cjk_index:
            return []
        try:
            return [
                (r[0], r[1])
                for r in self.conn.execute(
                    "SELECT rowid, bm25(fts_cjk, 4.0, 3.0, 1.0, 1.5) FROM fts_cjk "
                    "WHERE fts_cjk MATCH ? ORDER BY 2 LIMIT ?",
                    (match, limit),
                )
            ]
        except Exception:
            return []

    def _heal_fts(self) -> bool:
        """Rebuild FTS from symbols when rowid alignment is broken
        (index created before rowid-synced inserts). Returns True when a
        full rebuild happened (caller can skip its own incremental write)."""
        if self._fts_aligned():
            return False
        self.conn.execute("DELETE FROM fts_symbols")
        rows = self.conn.execute(
            """SELECT s.id, s.name, s.qualified_name, s.doc, s.kind, s.signature, f.path
               FROM symbols s JOIN files f ON f.id = s.file_id"""
        ).fetchall()
        if rows:
            self.conn.executemany(
                "INSERT INTO fts_symbols "
                "(rowid, name, qualified_name, doc, kind, signature, file_path) "
                "VALUES (?,?,?,?,?,?,?)",
                rows,
            )
        # the trigram table is rebuilt in the same pass and the revision marked, so
        # the _ensure_fts_cjk() that follows in startup does not scan symbols twice
        self._rebuild_fts_cjk()
        self.set_meta("fts_cjk_rev", FTS_CJK_REV)
        return True

    # ---------------- resolution ----------------

    def resolve_single_name(self, name: str) -> list[int]:
        """Symbols matching a call/inherit target name.

        ``module`` symbols are excluded: every file has one (named after its
        stem) to carry import-time calls, but a module is imported, never
        called, so a bare ``parse(...)`` must not resolve to ``parse.js``.

        The limit is a safety valve for pathological names (``get``/``set`` in
        a large repo); it is high enough that the candidate set is not silently
        truncated in normal projects, which would make a multi-candidate
        lookup look like a unique one.
        """
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT id FROM symbols WHERE name=? AND kind <> 'module' "
                "ORDER BY file_id LIMIT 100",
                (name,),
            )
        ]

    def apply_resolution(self, rel_id: int, target_id: int | None):
        self.conn.execute(
            "UPDATE relations SET target_id=? WHERE id=?", (target_id, rel_id)
        )

    # ---------------- stats ----------------

    def count_symbols(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]

    def has_unresolved_edges(self) -> bool:
        """Any call edge no resolution pass has looked at yet.

        Answered by the partial index `idx_rel_pending`, so a refresh can ask it
        on every call: it is how a pass knows the graph is still owed work after
        an earlier pass stopped at its time budget.
        """
        return bool(self.conn.execute(
            "SELECT EXISTS(SELECT 1 FROM relations "
            "WHERE target_id IS NULL AND tried = 0 "
            "AND rtype IN ('calls', 'references', 'inherits'))"
        ).fetchone()[0])

    def count_files(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def commit(self):
        self.conn.commit()

    # ---------------- parse errors ----------------

    def set_parse_error(self, path: str, error: str):
        self.conn.execute(
            "INSERT INTO parse_errors (path, error) VALUES (?, ?) "
            "ON CONFLICT(path) DO UPDATE SET error = excluded.error",
            (path, error),
        )

    def clear_parse_error(self, path: str):
        self.conn.execute("DELETE FROM parse_errors WHERE path=?", (path,))

    def parse_errors(self, limit: int = 50) -> list[dict]:
        return [
            {"file": r[0], "error": r[1]}
            for r in self.conn.execute(
                "SELECT path, error FROM parse_errors ORDER BY path LIMIT ?", (limit,)
            )
        ]