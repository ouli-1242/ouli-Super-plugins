"""FTS5-backed symbol search with name-first boost."""

from __future__ import annotations

import re

from fastgraph.config import path_rank
from fastgraph.db import DB

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
    #    stored symbol name must match regardless of case).
    #    The first token must appear (exact / qualified / substring); every
    #    additional token must ALSO match the name. OR-ing the extra tokens made
    #    a phrase query behave like "match any word": searching "CAPABILITY
    #    MODE" returned every symbol containing "mode" and filled the limit, so
    #    the content tier below (comments/strings — where the phrase actually
    #    lives) was never reached.
    base = "LOWER(s.name) = ? OR LOWER(s.qualified_name) = ? OR LOWER(s.name) LIKE ?"
    params = [tokens[0], tokens[0], f"%{tokens[0]}%"]
    # extra tokens only if they add real signal: 2-char tokens like "it" in
    # "markdown-it" match almost everything and crowd out the real hit.
    # NOTE: the first-token group must be parenthesised, otherwise SQL's
    # precedence (AND binds tighter than OR) makes the extra tokens apply to
    # the last OR operand only.
    extra = []
    for t in tokens[1:4]:
        if len(t) < 3:
            continue
        extra.append("LOWER(s.name) LIKE ?")
        params.append(f"%{t}%")
    name_expr = f"({base})"
    if extra:
        name_expr += " AND " + " AND ".join(extra)
    conditions = [name_expr]
    # CJK queries: FTS5's default unicode61 tokenizer treats a whole CJK run
    # as a single token, so `"学习"*` never matches a doc that merely contains
    # the phrase. Substring LIKE on doc/signature is the fallback for what the
    # trigram index cannot express: terms shorter than one trigram, and every
    # query on an SQLite build without trigram support. Longer CJK goes through
    # fts_cjk (tier 2b), where the terms AND instead of one of them deciding.
    # Names are not affected either way: the name tier above is plain LIKE.
    if re.search("[一-鿿]", query):
        short_cjk = [
            t for t in tokens if not t.isascii() and (len(t) < 3 or not db.has_cjk_index())
        ][:3]
        for term in short_cjk:
            conditions.append("LOWER(s.doc) LIKE ?")
            params.append(f"%{term}%")
            conditions.append("LOWER(s.signature) LIKE ?")
            params.append(f"%{term}%")
    # kind is a *filter* on the name matches, not another OR'd clause
    # (was: OR'd into the name chain, so kind="function" returned every
    # function in the repo regardless of the query).
    sql = (
        """SELECT s.id, s.name, s.kind, s.qualified_name, s.signature, s.start_line, f.path
           FROM symbols s JOIN files f ON f.id = s.file_id
           WHERE (""" + " OR ".join(conditions) + ")"
    )
    if kind:
        sql += " AND s.kind = ?"
        params.append(kind)
    # fetch a window wider than `limit` and rank it below: cutting straight to
    # `limit` in SQL kept the first N index-order rows, so in a repo whose test
    # files index first the real definition never entered the result set.
    sql += " LIMIT ?"
    win = max(limit * 6, 60)
    rows = db.conn.execute(sql, params + [win]).fetchall()
    rows.sort(key=lambda r: (path_rank(r[6]), r[6], r[5]))

    # 2) FTS doc/signature search, ranked. fts_symbols is a regular (not contentless)
    #    FTS5 table whose key column is `rowid` — kept equal to symbols.id so a
    #    MATCH hit resolves straight to its symbol. MATCH must reference the
    #    table, not a column (searching `id` raised and was swallowed, so doc/
    #    signature search silently never matched — A15).
    #
    #    Ordered by bm25() with per-column weights, best first (SQLite's bm25 is
    #    negated). Before this the hits were sorted by path and line only, so "a doc
    #    in the file that happened to index first" outranked "the doc that actually
    #    repeats the term". `kind` gets a near-zero weight on purpose: it stores
    #    "function"/"class", ordinary English words a query can contain by accident.
    fts_tokens = [t for t in tokens[:3] if len(t) >= 3]
    fts_query = " AND ".join(f'"{t}"*' for t in fts_tokens)
    fts_scored: list[tuple[int, float]] = []
    if fts_query:
        try:
            # the LIMIT also caps the IN (...) list below: an unbounded MATCH result on
            # a common prefix used to build a many-thousand-parameter query
            fts_scored = [
                (r[0], r[1])
                for r in db.conn.execute(
                    "SELECT rowid, bm25(fts_symbols, 4.0, 3.0, 1.0, 0.1, 1.5, 1.0) "
                    "FROM fts_symbols WHERE fts_symbols MATCH ? ORDER BY 2 LIMIT ?",
                    (fts_query, win),
                )
            ]
        except Exception:
            fts_scored = []

    # 2b) CJK prose. unicode61 never splits a CJK run, so tier 2 above structurally
    #     cannot match one; fts_cjk indexes the same rows by trigram and additionally
    #     covers name/qualified_name, which the LIKE fallback in tier 1 cannot reach.
    #     A trigram needs >=3 characters, so shorter CJK queries ("限流" is 2) still
    #     take LIKE -- as does every query on an SQLite build without trigram support.
    cjk_tokens = [t for t in tokens[:3] if len(t) >= 3 and not t.isascii()]
    cjk_scored = db.cjk_match(" AND ".join(f'"{t}"' for t in cjk_tokens), win) if cjk_tokens else []

    taken: set[int] = set()
    # concatenated, not merged by score: bm25 is relative to the corpus each table
    # holds, and a CJK-index score is not comparable to an ASCII-index one. A query
    # with terms in both languages is rare enough that "ASCII prose hits first" beats
    # inventing a cross-table scale that means nothing.
    fts_rows = _rows_for_ids(db, fts_scored, kind, taken) + _rows_for_ids(db, cjk_scored, kind, taken)

    seen: set[int] = set()
    # label the tier each hit came from: FTS hits are doc/signature matches, and
    # calling them "name" made the two tiers indistinguishable in the output
    for tier, tier_rows in (("name", rows), ("doc", fts_rows)):
        for r in tier_rows:
            if r[0] in seen:
                continue
            seen.add(r[0])
            results.append(_make_hit(r, tier))
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    if len(results) < limit and kind is None:
        results.extend(_content_hits(db, query, limit - len(results)))
    if len(results) < limit and kind is None:
        # import hits are kind="import" and would violate any kind filter
        results.extend(_import_hits(db, query, limit - len(results)))
    return results


def _rows_for_ids(
    db: DB, scored: list[tuple[int, float]], kind: str | None, taken: set[int]
) -> list[tuple]:
    """Resolve (id, bm25 score) pairs into symbol rows, ordered by score.

    `taken` is shared across the two FTS tables so a symbol that matches in both is
    reported once, at its better rank. The score is carried rather than the position:
    on a tie SQLite hands back rowid order, and two docs that say the same thing
    should be separated by where they live, not by which file was scanned first.
    """
    fresh = [sid for sid, _ in scored if sid not in taken]
    if not fresh:
        return []
    score = dict(scored)
    placeholders = ",".join("?" * len(fresh))
    sql = f"""SELECT s.id, s.name, s.kind, s.qualified_name, s.signature,
                     s.start_line, f.path
              FROM symbols s JOIN files f ON f.id = s.file_id
              WHERE s.id IN ({placeholders})"""
    params: list = list(fresh)
    if kind:
        sql += " AND s.kind = ?"
        params.append(kind)
    rows = list(db.conn.execute(sql, params))
    rows.sort(key=lambda r: (score.get(r[0], 0.0), path_rank(r[6]), r[6], r[5]))
    taken.update(r[0] for r in rows)
    return rows


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
    # over-fetch and re-rank: ORDER BY f.path puts `benchmarks/` and `tests/`
    # before `src/` alphabetically, so a prose hit in a test fixture used to
    # crowd the source hit out of the window
    rows = db.conn.execute(
        f"""SELECT lc.line, lc.kind, lc.text, f.path
            FROM line_content lc JOIN files f ON f.id = lc.file_id
            WHERE {like} ORDER BY f.path, lc.line LIMIT ?""",
        [f"%{t}%" for t in tokens] + [max(limit * 8, 80)],
    ).fetchall()
    rows.sort(key=lambda r: (path_rank(r[3]), r[3], r[0]))
    # dedup before truncating: an index written before the collector refused
    # duplicates still stores one-line docstrings twice, and both copies would take a
    # slot each out of a five-result answer. Re-indexing to fix that would mean a full
    # re-parse of every repository on the map, which is a heavier price than a pass
    # over the rows already in hand.
    hits: list[dict] = []
    seen: set[tuple] = set()
    for r in rows:
        key = (r[3], r[0], r[1], r[2])
        if key in seen:
            continue
        seen.add(key)
        hits.append(
            {
                "symbol": "", "kind": r[1], "qualified_name": "", "signature": "",
                "line": r[0], "file": r[3], "match": "content", "snippet": r[2][:80],
            }
        )
        if len(hits) >= limit:
            break
    return hits


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


def _make_hit(r: tuple, match: str = "name") -> dict:
    return {
        "symbol": r[1],
        "kind": r[2],
        "qualified_name": r[3],
        "signature": r[4],
        "line": r[5],
        "file": r[6],
        "match": match,
    }
    if r[3] and r[3] != r[1]:
        # only carried when it says more than `symbol` already did
        hit["qualified_name"] = r[3]
    return hit