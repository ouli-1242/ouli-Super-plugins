"""Project memory: notes anchored to code, plus graph snapshots to diff.

Two ideas live here and they are deliberately not mixed:

* **notes** -- small structured records pinned to a canonical *anchor key*
  (a symbol, a file, a module, or the project). The anchor is the primary key
  of the memory layer, so its format is spelled out once, below, and every
  other module goes through these helpers to build or read one.
* **graph snapshots** -- the normalized symbol set and call-edge set of the
  index at one moment, compressed. `what_changed` diffs two of them. Stored as
  sets rather than a hash because the tool's promise is "which symbols
  appeared, which edges broke", and a hash cannot answer that.

The store is a separate `memory.sqlite`, not `index.sqlite`: the index file's
contract is "delete it and it rebuilds" (see `Indexer.force_index`), and losing
a project's decision history to a routine rebuild would be a bad trade.
"""

from __future__ import annotations

import time
import zlib

from fastgraph.db import DB, MEMORY_SCHEMA

# The separator inside an anchor key. A rel path never contains '#' (the index
# stores POSIX project-relative paths), so splitting on the *first* '#' is
# unambiguous even when a qualified_name carries one.
SEP = "#"

PROJECT_ANCHOR = "project:"

ANCHOR_TYPES = ("symbol", "file", "module", "project")
NOTE_KINDS = ("decision", "warning", "todo", "context", "adr")

# A snapshot is diffed in Python, so its cost is the size of the edge set, not
# the number of queries. 400k normalized lines is already a multi-MB blob; a
# repo beyond that needs a sharded diff, which is out of scope here -- refusing
# is honest, silently truncating is not.
MAX_SNAPSHOT_LINES = 400_000


def normalize_rel(path: str) -> str:
    """POSIX, project-relative, no leading './' or '/'.

    Anchor keys are compared as strings across sessions, so `./a/b.py` and
    `a/b.py` must not become two different anchors.
    """
    p = (path or "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def symbol_key(rel: str, qualified_name: str) -> str:
    """The anchor *key* for a symbol: '<rel_path>#<qualified_name>'.

    Carrying rel_path is what makes the key usable as a primary key: a plain
    name matches every file that declares it (see graph.find_symbols), so
    'AuthService.login' alone can name several symbols in a real repo.
    """
    return f"{normalize_rel(rel)}{SEP}{qualified_name}"


def symbol_anchor(rel: str, qualified_name: str) -> str:
    return f"symbol:{symbol_key(rel, qualified_name)}"


def file_anchor(rel: str) -> str:
    return f"file:{normalize_rel(rel)}"


def module_anchor(rel_dir: str) -> str:
    d = normalize_rel(rel_dir).rstrip("/")
    return f"module:{d}"


def parse_anchor(anchor: str) -> tuple[str, str] | None:
    """`'symbol:src/a.py#Klass.method'` -> ('symbol', 'src/a.py#Klass.method').

    Returns None when the string is not in canonical form (no known prefix),
    which is when the caller has to *resolve* it against the index instead.
    """
    raw = (anchor or "").strip()
    if not raw:
        return ("project", "")
    if raw in ("project", "project:"):
        return ("project", "")
    for t in ANCHOR_TYPES:
        prefix = f"{t}:"
        if raw.startswith(prefix):
            key = raw[len(prefix):].strip()
            if t == "symbol":
                key = _normalize_symbol_key(key)
            elif t == "file":
                key = normalize_rel(key)
            elif t == "module":
                key = normalize_rel(key).rstrip("/")
            if not key:
                return None
            return (t, key)
    return None


def _normalize_symbol_key(key: str) -> str:
    rel, _, qname = key.partition(SEP)
    return f"{normalize_rel(rel)}{SEP}{qname.strip()}"


def anchor_parts(anchor_type: str, key: str) -> tuple[str, str]:
    """(rel_path, qualified_name) for a symbol anchor; (value, '') otherwise."""
    if anchor_type == "symbol":
        rel, _, qname = key.partition(SEP)
        return rel, qname
    return key, ""


def escape_like(value: str) -> str:
    """Neutralise the LIKE wildcards in user-supplied text.

    Without this, an anchor like `module:%` validates against every file in the
    index, and a directory named `a_b` silently matches `axb`.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_prefix(value: str) -> str:
    """An escaped `LIKE` pattern matching paths *under* `value`."""
    return f"{escape_like(value)}/%"


# Snapshot line format version, stored as the blob's first line. Changing how
# lines are built invalidates every existing baseline, and a diff across the two
# formats reads as "the whole graph changed", so the version is checked rather
# than trusted.
SNAPSHOT_FORMAT = "fg-snap/1"

_ESCAPES = {"\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\x1f": "\\_"}
_UNESCAPES = {v: k for k, v in _ESCAPES.items()}


def esc(value: str) -> str:
    """Make a field safe to put inside a tab-separated, newline-joined line.

    `relations.target` holds extracted call text, and on real repos it contains
    tabs and newlines (measured on uber-go/zap: 109 tab-bearing and 112
    newline-bearing targets). Without this those rows split into the wrong number
    of fields and `decode_lines` reads them back as extra symbols/edges -- which
    is invisible in a diff and wrong in every count.
    """
    out = []
    for ch in value or "":
        out.append(_ESCAPES.get(ch, ch))
    return "".join(out)


def unesc(value: str) -> str:
    i, out = 0, []
    while i < len(value):
        two = value[i:i + 2]
        if two in _UNESCAPES:
            out.append(_UNESCAPES[two])
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def encode_lines(lines: list[str]) -> bytes:
    """Sorted, deduped, newline-joined -- with the format version as line 1.

    The version is part of the blob rather than a column because a baseline whose
    lines are built differently cannot be diffed against the current format at
    all: every row would read as changed, and that looks exactly like a huge
    refactor.
    """
    body = "\n".join(sorted(set(lines)))
    return zlib.compress(f"{SNAPSHOT_FORMAT}\n{body}".encode("utf-8"), 6)


def decode_lines(blob: bytes) -> tuple[str, list[str]]:
    """(format, lines). A pre-versioning blob reports '' and is refused."""
    if not blob:
        return "", []
    text = zlib.decompress(bytes(blob)).decode("utf-8", errors="replace")
    head, _, rest = text.partition("\n")
    if not head.startswith("fg-snap/"):
        return "", [ln for ln in text.split("\n") if ln]  # v0: no header line
    return head, [ln for ln in rest.split("\n") if ln]


def collect_sets(index_db: DB, max_cycles: int = 500) -> tuple[list[str], list[str], list[str]]:
    """The three normalized sets a snapshot stores: symbols, edges, import cycles.

    Content rules that make two snapshots comparable:

    * **no ids** -- `replace_file_symbols` deletes and re-inserts a file's
      symbols on every re-parse (and NULLs the `target_id` of edges pointing at
      them), so `symbols.id`/`relations.id` change without the code changing.
      Only paths and qualified names survive a re-index unchanged.
    * **no line numbers** -- inserting one line at the top of a file would
      otherwise report every call edge in that file as removed and re-added.
    * **deduped, sorted** -- `children.push(x)` is stored twice (bare `push` and
      `excessDomChildren.push`), and unresolved edges keep their raw text, so
      the diff says which tier a line came from instead of guessing.
    """
    symbols = [
        f"{esc(kind)}\t{esc(rel)}{SEP}{esc(qname)}"
        for kind, rel, qname in index_db.conn.execute(
            "SELECT s.kind, f.path, s.qualified_name FROM symbols s "
            "JOIN files f ON f.id = s.file_id"
        )
    ]
    edges = []
    for rtype, src_path, src_qname, dst, tid in index_db.conn.execute(
        """SELECT r.rtype,
                  sf.path,
                  s.qualified_name,
                  CASE WHEN r.target_id IS NULL THEN r.target
                       ELSE tf.path || ? || t.qualified_name END,
                  r.target_id
           FROM relations r
           JOIN symbols s ON s.id = r.source_id
           JOIN files sf ON sf.id = s.file_id
           LEFT JOIN symbols t ON t.id = r.target_id
           LEFT JOIN files tf ON tf.id = t.file_id""",
        (SEP,),
    ):
        # a resolved edge's target is another anchored symbol, so it carries the
        # same path#qname shape as an anchor; an unresolved one carries raw call
        # text, which is the field that contains tabs and newlines on real repos.
        # The 4th field already says which of the two it is, so no prefix here.
        edges.append(
            f"{esc(rtype)}\t{esc(src_path)}{SEP}{esc(src_qname)}\t{esc(dst or '')}\t"
            f"{'resolved' if tid is not None else 'text'}"
        )
    # Cycles are stored as the *computed* SCC list: recomputing them for the
    # past side would need the past import graph, which is a fourth set nobody
    # asked for. `module_cycles` already answers "largest first"; cap it.
    from fastgraph import graph  # local import: graph pulls in the parsers

    cycles = [
        "\x1f".join(esc(p) for p in sorted(c.get("files") or ()))
        for c in graph.module_cycles(index_db, max_cycles=max_cycles)
    ]
    if len(symbols) > MAX_SNAPSHOT_LINES or len(edges) > MAX_SNAPSHOT_LINES:
        raise SnapshotTooLarge(len(symbols), len(edges))
    return symbols, edges, cycles


class SnapshotTooLarge(Exception):
    def __init__(self, symbols: int, edges: int):
        self.symbols, self.edges = symbols, edges
        super().__init__(
            f"graph has {symbols} symbols / {edges} edges, over the "
            f"{MAX_SNAPSHOT_LINES}-line snapshot cap"
        )


class Memory:
    """The notes + snapshot store for one project root."""

    def __init__(self, root):
        self.db = DB(root, filename="memory.sqlite", schema=MEMORY_SCHEMA, code_index=False)

    def close(self) -> None:
        # Windows: an open handle on memory.sqlite blocks rmtree of the project,
        # the same reason Toolbox.close() exists for the index connection.
        self.db.close()

    # ---------------- notes ----------------

    def add_note(self, anchor_type: str, anchor_key: str, kind: str, body: str, source: str = "") -> int:
        # patient_writes: a second window on the same project is the documented
        # situation here, and a note the user asked for must queue rather than
        # surface as "database is locked"
        with self.db.patient_writes():
            cur = self.db.conn.execute(
                "INSERT INTO notes (anchor_type, anchor_key, kind, body, source, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (anchor_type, anchor_key, kind, body, source or "", time.time()),
            )
            self.db.conn.commit()
        return int(cur.lastrowid)

    def delete_note(self, note_id: int) -> dict | None:
        """Remove one note by id, returning what was removed (None if there was no such id).

        The read and the delete share one lock window, and the row comes back so the
        caller can see what it just destroyed: `forget` is undoable by re-`remember`ing
        the echoed body, which is the only reason a delete here needs no backup copy.
        """
        with self.db.patient_writes():
            row = self.db.conn.execute(
                "SELECT id, anchor_type, anchor_key, kind, body, source, created_at "
                "FROM notes WHERE id = ?",
                (note_id,),
            ).fetchone()
            if row is None:
                return None
            self.db.conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            self.db.conn.commit()
        return self._note_row(*row)

    def note_count(self) -> int:
        """How many notes are stored. `forget` reports it so a caller cleaning up
        orphans can tell an empty project from one it has not finished with."""
        return int(self.db.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0])

    def notes_for(
        self, pairs: list[tuple[str, str]], kind: str | None = None, limit: int = 200
    ) -> list[dict]:
        """Batch fetch by (anchor_type, anchor_key); one query, not N."""
        if not pairs:
            return []
        clauses, args = [], []
        for t, k in pairs:
            clauses.append("(anchor_type = ? AND anchor_key = ?)")
            args.extend([t, k])
        where = " OR ".join(clauses)
        if kind is not None:
            where, args = f"({where}) AND kind = ?", args + [kind]
        args.append(limit)
        return [
            self._note_row(*r)
            for r in self.db.conn.execute(
                f"SELECT id, anchor_type, anchor_key, kind, body, source, created_at "
                f"FROM notes WHERE {where} ORDER BY id DESC LIMIT ?",
                args,
            )
        ]

    def notes_under(
        self, anchor_type: str, key: str, kind: str | None = None, limit: int = 200
    ) -> list[dict]:
        """Notes pinned at a location *or anywhere inside it*.

        `recall(anchor="file:src/error.rs")` is the question "what do we know about
        this file", and the decisions worth knowing are mostly pinned to the symbols
        inside it. Exact-key matching alone answers that with zero notes, which is
        the same silent loss as a deleted symbol -- just reached from the coarser
        anchor. A symbol anchor has nothing inside it, so it stays exact.
        `project:` stays exact too: it is the repo-wide bucket, and making it the
        superset would bury the few session-level notes under every code note.
        """
        if anchor_type == "symbol":
            return self.notes_for([("symbol", key)], kind=kind, limit=limit)
        args: list = []
        if anchor_type == "file":
            where = "((anchor_type = 'file' AND anchor_key = ?) OR (anchor_type = 'symbol' AND anchor_key LIKE ? ESCAPE '\\'))"
            args = [key, escape_like(key) + SEP + "%"]
        elif anchor_type == "module":
            where = "((anchor_type = 'module' AND anchor_key = ?) OR anchor_key LIKE ? ESCAPE '\\')"
            args = [key.rstrip("/") or key, like_prefix(key.rstrip("/"))]
        else:
            where = "(anchor_type = ? AND anchor_key = ?)"
            args = [anchor_type, key]
        if kind is not None:
            where, args = f"({where}) AND kind = ?", args + [kind]
        args.append(limit)
        return [
            self._note_row(*r)
            for r in self.db.conn.execute(
                f"SELECT id, anchor_type, anchor_key, kind, body, source, created_at "
                f"FROM notes WHERE {where} ORDER BY id DESC LIMIT ?",
                args,
            )
        ]

    def find_notes(
        self,
        anchor_type: str | None = None,
        anchor_key: str | None = None,
        kind: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        sql = "SELECT id, anchor_type, anchor_key, kind, body, source, created_at FROM notes WHERE 1=1"
        args: list = []
        if anchor_type is not None:
            sql += " AND anchor_type = ?"
            args.append(anchor_type)
        if anchor_key is not None:
            sql += " AND anchor_key = ?"
            args.append(anchor_key)
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [self._note_row(*r) for r in self.db.conn.execute(sql, args)]

    @staticmethod
    def _note_row(nid, anchor_type, anchor_key, kind, body, source, created_at) -> dict:
        return {
            "id": nid,
            "anchor": f"{anchor_type}:{anchor_key}",
            "anchor_type": anchor_type,
            "kind": kind,
            "body": body,
            "source": source,
            "created_at": created_at,
        }

    def notes_like(self, text: str, limit: int = 50) -> list[dict]:
        """Notes whose anchor ends with `text` -- the path that finds an orphan.

        A note anchored to `symbol:auth.py#AuthService.logout` cannot be reached
        by resolving anchors any more once the method is deleted: there is no
        symbol to resolve to. Matching the anchor *text* is what keeps a decision
        about removed code readable, which is the whole point of the layer, so
        `recall` uses this before reporting "nothing found".
        """
        needle = escape_like((text or "").strip())
        if not needle:
            return []
        return [
            self._note_row(*r)
            for r in self.db.conn.execute(
                "SELECT id, anchor_type, anchor_key, kind, body, source, created_at FROM notes "
                "WHERE (anchor_type || ':' || anchor_key) LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",
                (f"%{needle}", limit),
            )
        ]

    # ---------------- snapshots ----------------

    def put_snapshot(
        self, label: str, ref: str, complete: bool, symbols: list[str], edges: list[str], cycles: list[str]
    ) -> int:
        # compress outside the write window, hold the lock only for the insert: a
        # 250 KB blob is a long write to be holding up a second window's `remember`
        blobs = (encode_lines(symbols), encode_lines(edges), encode_lines(cycles))
        with self.db.patient_writes():
            cur = self.db.conn.execute(
                "INSERT INTO graph_snapshot (label, ref, complete, symbol_blob, edge_blob, cycle_blob, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (label, ref or "", int(bool(complete)), *blobs, time.time()),
            )
            self.db.conn.commit()
        return int(cur.lastrowid)

    def snapshot_by_label(self, label: str) -> dict | None:
        row = self.db.conn.execute(
            "SELECT id, label, ref, complete, symbol_blob, edge_blob, cycle_blob, created_at "
            "FROM graph_snapshot WHERE label = ? ORDER BY id DESC LIMIT 1",
            (label,),
        ).fetchone()
        return self._snapshot_row(*row) if row else None

    def snapshot_list(self, limit: int = 50) -> list[dict]:
        # blobs stay out: a caller picking a `since` label needs metadata only,
        # and returning tens of KB of compressed edges per row would be absurd
        return [
            {"id": r[0], "label": r[1], "ref": r[2], "complete": bool(r[3]), "created_at": r[4]}
            for r in self.db.conn.execute(
                "SELECT id, label, ref, complete, created_at FROM graph_snapshot ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        ]

    @staticmethod
    def _snapshot_row(sid, label, ref, complete, sb, eb, cb, created_at) -> dict:
        fmt_s, symbols = decode_lines(sb)
        fmt_e, edges = decode_lines(eb)
        fmt_c, cycles = decode_lines(cb)
        return {
            "id": sid, "label": label, "ref": ref, "complete": bool(complete),
            # one format field is enough: all three blobs are written together
            "format": fmt_s or fmt_e or fmt_c,
            "symbols": symbols, "edges": edges, "cycles": cycles,
            "created_at": created_at,
        }
