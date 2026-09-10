"""SQLite storage: files / symbols / relations / file_imports + FTS5."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from fastgraph.config import ensure_ignore_template

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id         INTEGER PRIMARY KEY,
    path       TEXT NOT NULL UNIQUE,
    language   TEXT NOT NULL,
    hash       TEXT NOT NULL DEFAULT '',
    mtime      REAL NOT NULL DEFAULT 0,
    size       INTEGER NOT NULL DEFAULT 0
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
    decorated      INTEGER NOT NULL DEFAULT 0
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
    line        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_id);

CREATE TABLE IF NOT EXISTS file_imports (
    id       INTEGER PRIMARY KEY,
    file_id  INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    text     TEXT NOT NULL,
    kind     TEXT NOT NULL DEFAULT '',
    line     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fimp_file ON file_imports(file_id);

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


def _stem_of(path: str) -> str:
    """``src/pkg/mod.py`` -> ``src.pkg.mod`` (lowercased, extension dropped)."""
    return path.rsplit(".", 1)[0].replace("/", ".").lower()


class DB:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.index_dir = self.root / ".fastgraph"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        ensure_ignore_template(self.index_dir)
        self.db_path = self.index_dir / "index.sqlite"
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
        self._migrate_schema()
        conn.executescript(SCHEMA)
        conn.commit()
        self._heal_fts()
        conn.commit()

    def _new_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # cross-process writers (a second MCP instance, or a script + the
        # server) wait up to 5s instead of failing instantly with
        # "database is locked" (default busy_timeout is 0)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(SCHEMA)
        conn.commit()
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
            "start_line, end_line, start_col, end_col, decorated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    file_id, s["name"], s["kind"], s["qualified_name"], s["signature"],
                    s["doc"], s["start_line"], s["end_line"], s["start_col"], s["end_col"],
                    s.get("decorated", False),
                )
                for s in symbols
            ],
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

    def clear_fts(self) -> None:
        """Drop the whole FTS index.

        Used when the index is rebuilt from scratch: per-file deletes cannot
        remove rows leaked by an older build, and such a stale rowid would
        collide with the ids the rebuild is about to assign (FTS5 rejects a
        duplicate rowid with "constraint failed").
        """
        self.conn.execute("DELETE FROM fts_symbols")

    def _fts_aligned(self) -> bool:
        """True when fts rowids match symbols ids (at least one hit)."""
        try:
            r = self.conn.execute(
                "SELECT 1 FROM fts_symbols f JOIN symbols s ON f.rowid = s.id LIMIT 1"
            ).fetchone()
        except Exception:
            return True
        return r is not None

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