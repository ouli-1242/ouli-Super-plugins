"""FTS5-backed symbol search with name-first boost."""

from __future__ import annotations

import re

from fastgraph.db import DB

_STOPWORDS: set[str] = set()


_TOKEN_MAX = 128  # a token longer than this is a pasted blob, not a search term


def _tokens(q: str) -> list[str]:
    # \w covers CJK and other unicode letters, so 中文符号 is searchable
    # (was: [A-Za-z0-9_] dropped all non-ASCII tokens).
    # Cap total query (1000) and per-token (128) length: SQLite raises
    # "LIKE or GLOB pattern too complex" on multi-thousand-char patterns.
    return [t[:_TOKEN_MAX] for t in re.findall(r"\w+", q[:1000].lower()) if len(t) >= 2]


def code_search(db: DB, query: str, limit: int = 10, kind: str | None = None) -> list[dict]:
    """Search across symbol names, qualified names, docstrings.

    Strategy: exact-name matches first, then FTS prefix matches, then doc prose.
    """
    results: list[dict] = []
    tokens = _tokens(query)
    if not tokens:
        return results

    # 1) exact & prefix name matches (case-insensitive: `=` in SQLite is
    #    case-sensitive; user queries like "DeepSeekLLM" use case but the
    #    stored symbol name must match regardless of case)
    name_clauses, params = (
        ["LOWER(s.name) = ?", "LOWER(s.qualified_name) = ?"],
        [tokens[0], tokens[0]],
    )
    # first token also as prefix/substring (covers partial names e.g. "orchestrator")
    name_clauses.append("LOWER(s.name) LIKE ?")
    params.append(f"%{tokens[0]}%")
    # remaining tokens only if they add real signal: 2-char tokens like "it"
    # in "markdown-it" match almost everything (initRadar, write, visit...) and
    # crowd out the real hit; require >=3 chars for name-level scoring
    for t in tokens[1:4]:
        if len(t) < 3:
            continue
        name_clauses.append("LOWER(s.name) LIKE ?")
        params.append(f"%{t}%")
    # CJK queries: FTS5's default unicode61 tokenizer treats a whole CJK run
    # as a single token, so `"学习"*` never matches a doc that merely contains
    # the phrase. Fall back to substring LIKE on doc/signature for non-ASCII.
    if re.search("[一-鿿]", query):
        cjk = next((t for t in tokens if re.search("[一-鿿]", t)), None)
        if cjk:
            name_clauses.append("LOWER(s.doc) LIKE ?")
            params.append(f"%{cjk}%")
            name_clauses.append("LOWER(s.signature) LIKE ?")
            params.append(f"%{cjk}%")
    # kind is a *filter* on the name matches, not another OR'd clause
    # (was: OR'd into the name chain, so kind="function" returned every
    # function in the repo regardless of the query).
    sql = (
        """SELECT s.id, s.name, s.kind, s.qualified_name, s.signature, s.start_line, f.path
           FROM symbols s JOIN files f ON f.id = s.file_id
           WHERE (""" + " OR ".join(name_clauses) + ")"
    )
    if kind:
        sql += " AND s.kind = ?"
        params.append(kind)
    sql += " LIMIT ?"
    rows = db.conn.execute(sql, params + [limit]).fetchall()

    # 2) FTS doc/signature search. fts_symbols is a contentless FTS5 table
    #    (content=''): rows carry only rowid (= symbols.id), so resolve hits
    #    through symbols by id. MATCH must reference the table, not a column.
    fts_tokens = [t for t in tokens[:3] if len(t) >= 3]
    fts_query = " AND ".join(f'"{t}"*' for t in fts_tokens)
    fts_ids: list[int] = []
    try:
        # fts_symbols is a regular FTS5 table: its implicit key column is
        # `rowid`, not `id` (searching `id` raised and was swallowed, so doc/
        # signature search silently never matched — A15).
        fts_ids = [
            r[0]
            for r in db.conn.execute(
                "SELECT rowid FROM fts_symbols WHERE fts_symbols MATCH ?", (fts_query,)
            )
        ]
    except Exception:
        fts_ids = []
    if fts_ids:
        placeholders = ",".join("?" * len(fts_ids))
        fts_sql = (
            f"""SELECT s.id, s.name, s.kind, s.qualified_name, s.signature,
                       s.start_line, f.path
                FROM symbols s JOIN files f ON f.id = s.file_id
                WHERE s.id IN ({placeholders})"""
        )
        fts_params: list = fts_ids
        if kind:
            fts_sql += " AND s.kind = ?"
            fts_params = fts_ids + [kind]
        fts_rows = db.conn.execute(fts_sql, fts_params).fetchall()
    else:
        fts_rows = []

    seen: set[int] = set()
    for r in list(rows) + list(fts_rows):
        if r[0] in seen:
            continue
        seen.add(r[0])
        results.append(_make_hit(r, query))
        if len(results) >= limit:
            break
    if len(results) < limit and kind is None:
        results.extend(_content_hits(db, query, limit - len(results)))
    if len(results) < limit and kind is None:
        # import hits are kind="import" and would violate any kind filter
        results.extend(_import_hits(db, query, limit - len(results)))
    return results


def _content_hits(db: DB, query: str, limit: int) -> list[dict]:
    """LIKE scan over stored comment/string/template lines (CJK-safe).

    Runs after symbol-level tiers: identifiers live in the symbol index, this
    covers prose — Chinese keywords, error messages, doc comments. Each hit
    carries a ≤80-char snippet of the matching line.
    """
    tokens = [t for t in _tokens(query) if len(t) >= 2][:3]
    if not tokens:
        return []
    like = " AND ".join("lc.text LIKE ?" for _ in tokens)
    rows = db.conn.execute(
        f"""SELECT lc.line, lc.kind, lc.text, f.path
            FROM line_content lc JOIN files f ON f.id = lc.file_id
            WHERE {like} ORDER BY f.path, lc.line LIMIT ?""",
        [f"%{t}%" for t in tokens] + [limit],
    ).fetchall()
    return [
        {
            "symbol": "", "kind": r[1], "qualified_name": "", "signature": "",
            "line": r[0], "file": r[3], "match": "content", "snippet": r[2][:80],
        }
        for r in rows
    ]


def _import_hits(db: DB, query: str, limit: int) -> list[dict]:
    """Import lines mentioning any query token (package names like ``axios``,
    ``pydantic`` never appear as symbols — they are third-party deps)."""
    import re as _re
    words = [t for t in _re.findall(r"\w+", query.lower()) if len(t) >= 2]
    if not words:
        return []
    like = " OR ".join("LOWER(fi.text) LIKE ?" for _ in words[:4])
    rows = db.conn.execute(
        f"""SELECT fi.text, fi.line, f.path
            FROM file_imports fi JOIN files f ON f.id = fi.file_id
            WHERE {like} ORDER BY f.path, fi.line LIMIT ?""",
        [f"%{w}%" for w in words[:4]] + [limit * 3],
    ).fetchall()
    # whole-query matches ("markdown-it") rank above mere word overlaps
    full = query.lower().strip()
    rows.sort(key=lambda r: (0 if full in r[0].lower() else 1, r[2], r[1]))
    out: list[dict] = []
    for text, line, path in rows[:limit]:
        out.append(
            {
                "symbol": (text.strip().splitlines()[0] if text else "")[:100],
                "kind": "import",
                "qualified_name": "",
                "signature": "",
                "line": line,
                "file": path,
                "match": "import",
            }
        )
    return out


def _make_hit(r: tuple, query: str) -> dict:
    return {
        "symbol": r[1],
        "kind": r[2],
        "qualified_name": r[3],
        "signature": r[4],
        "line": r[5],
        "file": r[6],
        "match": "name",
    }