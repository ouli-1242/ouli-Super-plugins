"""Graph queries: symbol lookup, callers/callees, BFS trace, impact scoring."""

from __future__ import annotations

import json
import posixpath
import re
from collections import deque
from pathlib import Path

from fastgraph.db import DB
from fastgraph.parsers.registry import language_for_path


def symbol_row(r: tuple) -> dict:
    return {
        "id": r[0],
        "name": r[1],
        "kind": r[2],
        "qualified_name": r[3],
        "signature": r[4],
        "start_line": r[5],
        "path": r[6],
    }


_OVERLOAD_SUFFIX_RE = re.compile(r"\[\d+\]$")


def normalize_symbol_query(name: str) -> str:
    """Accept slash name paths in addition to FastGraph's dotted names.

    A name path is ``/``-separated, may carry a leading ``/`` (absolute form)
    and a trailing overload index (``MyClass/my_method[1]``); FastGraph stores
    dotted qualified names. Callers paste identifiers from one tool into the
    next, so both spellings are accepted here rather than forcing a translation
    step. ``Class.method`` / ``top`` are returned unchanged.
    """
    if not name:
        return name
    s = name.strip()
    s = _OVERLOAD_SUFFIX_RE.sub("", s)
    if "/" in s:
        s = s.strip("/").replace("/", ".")
    return s


def name_path(qname: str) -> str:
    """FastGraph dotted qualified name -> slash name path (``A.B.m`` -> ``A/B/m``)."""
    return (qname or "").replace(".", "/")


def find_symbols(db: DB, name: str, limit: int = 20) -> list[dict]:
    """Locate symbols by plain name or dotted qualified name.

    Supports ``Class.method`` (exact qualified_name match) and, for 3+ segments,
    ``module.Class.method`` — the leading segment is resolved to its
    module/class symbol's file, then the rest is matched against qualified
    names inside that file (A7).

    Also accepts slash name paths (``Class/method``, ``/Class/method``,
    ``Class/method[1]``) via :func:`normalize_symbol_query`.
    """
    name = normalize_symbol_query(name)
    q = (
        "SELECT s.id, s.name, s.kind, s.qualified_name, s.signature, s.start_line, "
        "f.path"
        " FROM symbols s JOIN files f ON f.id = s.file_id"
        " WHERE s.name = ? OR s.qualified_name = ?"
        " ORDER BY s.file_id LIMIT ?"
    )
    rows = db.conn.execute(q, (name, name, limit)).fetchall()
    parts = name.split(".")
    if len(parts) >= 3:
        qual = ".".join(parts[1:])
        # Leading segment is a module (file stem) or a class symbol. Resolve it
        # to a set of candidate file ids, then match the remaining segments as
        # a qualified_name inside those files. Does not depend on a module
        # symbol existing (the parser only emits one when the file has imports
        # or a docstring).
        file_ids: set[int] = {
            m[1]
            for m in db.conn.execute(
                "SELECT id, file_id FROM symbols WHERE name = ? AND kind IN ('module', 'class')",
                (parts[0],),
            ).fetchall()
        }
        for (fp,) in db.conn.execute("SELECT path FROM files"):
            if fp.rsplit("/", 1)[-1].rsplit(".", 1)[0] == parts[0]:
                r = db.conn.execute("SELECT id FROM files WHERE path=?", (fp,)).fetchone()
                if r:
                    file_ids.add(r[0])
        seen = {r[0] for r in rows}
        for fid in file_ids:
            extra = db.conn.execute(
                "SELECT s.id, s.name, s.kind, s.qualified_name, s.signature, s.start_line, "
                "f.path FROM symbols s JOIN files f ON f.id = s.file_id"
                " WHERE s.qualified_name = ? AND s.file_id = ? ORDER BY s.start_line LIMIT ?",
                (qual, fid, limit),
            ).fetchall()
            rows.extend(r for r in extra if r[0] not in seen)
            seen.update(r[0] for r in extra)
    return [symbol_row(r) for r in rows[:limit]]


def symbol_by_id(db: DB, sid: int) -> dict | None:
    r = db.conn.execute(
        """SELECT s.id, s.name, s.kind, s.qualified_name, s.signature, s.start_line,
                  s.end_line, s.doc, f.path, f.language
           FROM symbols s JOIN files f ON f.id = s.file_id WHERE s.id = ?""",
        (sid,),
    ).fetchone()
    if not r:
        return None
    return {
        "id": r[0],
        "name": r[1],
        "kind": r[2],
        "qualified_name": r[3],
        "signature": r[4],
        "start_line": r[5],
        "end_line": r[6],
        "doc": r[7],
        "path": r[8],
        "language": r[9],
    }


def callers(db: DB, sid: int) -> list[int]:
    """Direct in-edges (calls only): relations targeting sid."""
    rows = db.conn.execute(
        "SELECT source_id FROM relations WHERE target_id = ? AND rtype = 'calls' "
        "ORDER BY source_id",
        (sid,),
    ).fetchall()
    return [r[0] for r in rows]


def callee_ids(db: DB, sid: int) -> list[int]:
    # calls only: inheritance is a hierarchy edge, not something the symbol
    # "calls" (was: pulls in `inherits` targets, so find_callees(Derived)
    # reported the base class — inconsistent with symbol_info.callees).
    rows = db.conn.execute(
        "SELECT target_id FROM relations WHERE source_id = ? "
        "AND target_id IS NOT NULL AND rtype = 'calls'",
        (sid,),
    ).fetchall()
    return [r[0] for r in rows]


def callee_names_with_lines(db: DB, sid: int) -> list[dict]:
    rows = db.conn.execute(
        """SELECT r.target, r.rtype, r.line FROM relations r
           WHERE r.source_id = ? ORDER BY r.line""",
        (sid,),
    ).fetchall()
    return [{"target": r[0], "rtype": r[1], "line": r[2]} for r in rows]


def find_callers(db: DB, name: str, limit: int = 30, depth: int = 1) -> list[dict]:
    """Who calls `name` (optionally transitively, BFS up to depth).

    Each result carries ``via``: ``"resolved"`` for a stored call edge,
    ``"text"`` for a raw-text fold -- an *unresolved* edge whose text happens
    to name the symbol (`thing.do_something()` folds onto a class called
    ``thing`` even when the receiver is an unrelated object). Text folds are
    guesses; filter on ``via`` when precision matters.
    """
    roots = find_symbols(db, name)
    if not roots:
        return []
    root_ids, member_ids = _expand_container_roots(db, roots)
    # keep discovery order (breadth-first, then by source id): a bare set made
    # the result order arbitrary, so the most relevant caller was not reliably
    # first
    ordered: list[int] = []
    via_of: dict[int, str] = {}
    seen: set[int] = set()
    frontier = list(root_ids)
    level = 0
    while frontier and level < depth:
        nxt: list[int] = []
        for sid in frontier:
            for c, via in _callers_with_class(db, sid):
                if c not in seen:
                    seen.add(c)
                    via_of[c] = via
                    ordered.append(c)
                    nxt.append(c)
        frontier = nxt
        level += 1
    out: list[dict] = []
    for s in ordered:
        if s in root_ids or s in member_ids:
            continue
        info = symbol_by_id(db, s)
        if not info:
            continue
        info["via"] = via_of.get(s, "resolved")
        out.append(info)
        if len(out) >= limit:
            break
    return out


def caller_trace(db: DB, name: str, max_depth: int = 20, limit: int = 50) -> list[dict]:
    """Transitive callers of ``name`` as a *leveled trace*.

    Unlike :func:`find_callers` (a flat set), each entry records the ``depth``
    at which it was reached and the immediate caller that leads to it (``via``),
    so the result reads as a chain instead of an unordered set.
    """
    roots = find_symbols(db, name)
    if not roots:
        return []
    root_ids, member_ids = _expand_container_roots(db, roots)
    display: dict[int, str] = {
        r["id"]: (r.get("qualified_name") or r.get("name") or "") for r in roots
    }
    seen: set[int] = set(root_ids)
    out: list[dict] = []
    frontier = list(root_ids)
    depth = 0
    while frontier and depth < max_depth and len(out) < limit:
        depth += 1
        nxt: list[int] = []
        for sid in frontier:
            for c, _via in _callers_with_class(db, sid):
                if c in seen:
                    continue
                seen.add(c)
                nxt.append(c)
                info = symbol_by_id(db, c)
                if not info:
                    continue
                display[c] = info["qualified_name"] or info["name"]
                if c in member_ids:
                    continue
                entry = _brief(info)
                entry["depth"] = depth
                entry["via"] = display.get(sid, "")
                out.append(entry)
                if len(out) >= limit:
                    break
            if len(out) >= limit:
                break
        frontier = nxt
    return out


def _symbol_ids(rows: list[dict]) -> set[int]:
    return {r["id"] for r in rows}


_CONTAINER_KINDS = {"class", "interface", "struct", "enum", "impl"}


def _expand_container_roots(db: DB, rows: list[dict]) -> tuple[set[int], set[int]]:
    """Return (root_ids, member_ids).

    For container roots (class/interface/struct/enum/impl), member symbols are
    added to the root set so class-level queries aggregate member edges
    (``find_callers("Greeter")`` == callers of Greeter's methods). member_ids
    is returned so callers can exclude the class's own members from results.
    """
    root_ids: set[int] = set()
    member_ids: set[int] = set()
    for r in rows:
        root_ids.add(r["id"])
        if r.get("kind") not in _CONTAINER_KINDS:
            continue
        qname = r.get("qualified_name") or ""
        if not qname:
            continue
        for (mid,) in db.conn.execute(
            "SELECT id FROM symbols WHERE qualified_name LIKE ?", (qname + ".%",)
        ):
            if mid != r["id"]:
                member_ids.add(mid)
    return root_ids | member_ids, member_ids


def find_callees(db: DB, name: str, limit: int = 50, depth: int = 1) -> list[dict]:
    roots = find_symbols(db, name)
    if not roots:
        return []
    root_ids, member_ids = _expand_container_roots(db, roots)
    ordered: list[int] = []
    seen: set[int] = set()
    frontier = list(root_ids)
    level = 0
    while frontier and level < depth:
        nxt: list[int] = []
        for sid in frontier:
            for c in callee_ids(db, sid):
                if c not in seen and c not in root_ids:
                    seen.add(c)
                    ordered.append(c)
                    nxt.append(c)
        frontier = nxt
        level += 1
    out = [symbol_by_id(db, s) for s in ordered if s not in member_ids]
    return [o for o in out if o][:limit]


def unresolved_incoming(db: DB, name: str, qname: str = "") -> int:
    """Call-like edges whose text names this symbol but never resolved.

    Resolution is name-based, so a call that cannot be pinned to one symbol
    keeps ``target_id`` NULL, and ``find_callers`` then returns an empty list
    -- which reads as "nobody calls this". This count is the correction: it
    says how many unresolved edges name the symbol, so "no callers" can be
    told apart from "callers we could not resolve".
    """
    total = 0
    seen: set[str] = set()
    for cand in (name, qname):
        if not cand or cand in seen:
            continue
        seen.add(cand)
        esc = _like_escape(cand)
        total += db.conn.execute(
            "SELECT COUNT(*) FROM relations WHERE target_id IS NULL "
            "AND rtype IN ('calls', 'references') "
            "AND (LOWER(target) = LOWER(?) OR target LIKE ? ESCAPE '\\' "
            "     OR target LIKE ? ESCAPE '\\')",
            (cand, f"%.{esc}", f"%::{esc}"),
        ).fetchone()[0]
    return total


def unresolved_outgoing(db: DB, sid: int) -> int:
    """Calls a symbol makes that were never resolved to a target.

    ``find_callees`` drops them; reporting the count keeps a short callee list
    from reading as "this symbol depends on nothing".
    """
    return db.conn.execute(
        "SELECT COUNT(*) FROM relations WHERE source_id = ? AND target_id IS NULL "
        "AND rtype IN ('calls', 'references')",
        (sid,),
    ).fetchone()[0]


def _callers_with_class(db: DB, sid: int, fold_owner: bool = False) -> list[tuple[int, str]]:
    """Callers of a symbol, plus callers of its enclosing class's members.

    Resolves chains like ``chat() -> orchestrator.handle_chat -> ... -> TutorAgent``
    where the class-level init/instantiation is not recorded as a direct edge:
    anything calling ``Orchestrator.handle_chat`` is also an upstream of
    ``Orchestrator`` and of ``Orchestrator.__init__``.

    Two text-folding rules, both in addition to exact resolved-id edges:
    - container symbols (class/interface/struct/impl/enum) fold by qualified
      *and* bare name, so members of the same class share one upstream set
      (``Cls.method`` edges fold back to ``Cls``; constructors via
      ``new Cls()`` / ``Cls()`` edges count for the class);
    - member symbols fold *exactly*: only their own unresolved text edge
      (``Cls.method``); constructors additionally fold their container's
      constructor edge (``Cls``). Never a ``Cls.%`` prefix match: that would
      report every caller of sibling members (other methods, auto-generated
      getters/setters) as a caller of this member.

    ``fold_owner`` controls the owner (``Cls``) fold for ordinary members:

    - False (precision; "who calls / is affected" queries — find_callers,
      impact_analysis, caller_trace): only constructors fold their container.
      Applying it to every member made each ``Cls(...)`` instantiation site a
      caller of *all* of Cls's methods, which buried the real callers and
      contradicted rename_impact (which never folds).
    - True (recall; "is A connected to B" queries — path_between): folding the
      owner reconnects classes that merely instantiate the target's class, so
      ``trace_path("Proxy", "LLMClient.chat")`` still finds the path through
      ``Proxy.__init__ -> LLMClient()`` when the actual call edge is
      unresolvable.

    Bare module-level functions never text-fold: mere references such as
    FastAPI ``Depends(fn)`` must not masquerade as callers.
    """
    out: list[tuple[int, str]] = [(s, "resolved") for s in callers(db, sid)]
    seen = {s for s, _ in out}
    info = symbol_by_id(db, sid)
    if not info:
        return out
    qname = info.get("qualified_name") or ""
    kind = info.get("kind") or ""

    def add_text(rows) -> None:
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                out.append((r[0], "text"))

    if kind in ("class", "interface", "struct", "impl", "enum"):
        candidates = {qname, info.get("name") or ""}
        # longest first: dotted qualified names outmatch bare names
        for cand in sorted((c for c in candidates if c), key=len, reverse=True):
            esc = _like_escape(cand)
            add_text(db.conn.execute(
                "SELECT DISTINCT source_id FROM relations WHERE target = ? "
                "OR target LIKE ? ESCAPE '\\' OR target LIKE ? ESCAPE '\\' "
                "ORDER BY source_id",
                (cand, f"%.{esc}", f"%::{esc}"),
            ))
    elif "." in qname or "::" in qname:
        cands = [qname]
        if fold_owner or info.get("name") in ("__init__", "__new__", "__post_init__", "constructor"):
            cands.append(qname.rsplit("::" if "::" in qname else ".", 1)[0])
        for cand in cands:
            add_text(db.conn.execute(
                "SELECT DISTINCT source_id FROM relations "
                "WHERE target = ? OR target LIKE ? ESCAPE '\\' ORDER BY source_id",
                (cand, f"%.{_like_escape(cand)}"),
            ))
    return out


def path_between(db: DB, from_name: str, to_name: str, max_depth: int = 8) -> list[list[dict]] | None:
    """BFS upward from `to_name` until we reach `from_name`. Returns path symbols."""
    src = find_symbols(db, from_name)
    tgt = find_symbols(db, to_name)
    if not src or not tgt:
        return None
    # if `from_name` is a class, its members are valid starting points too
    src_ids, _member_ids = _expand_container_roots(db, src)
    tgt_ids = _symbol_ids(tgt)
    # multi-source BFS from targets upward, tracking parents
    parent: dict[int, int] = {}
    frontier = list(tgt_ids)
    visited = set(tgt_ids)
    found: int | None = None
    for depth in range(max_depth):
        nxt: list[int] = []
        for sid in frontier:
            # fold_owner=True: connectivity between two given symbols is a
            # recall problem (a class that merely instantiates the target's
            # class still counts as a path), unlike "who calls X"
            for c, _via in _callers_with_class(db, sid, fold_owner=True):
                if c in visited:
                    continue
                visited.add(c)
                parent[c] = sid
                if c in src_ids:
                    found = c
                    break
                nxt.append(c)
        if found is not None:
            break
        frontier = nxt
    if found is None:
        return None
    path: list[dict] = []
    cur = found
    while cur is not None:
        path.append(symbol_by_id(db, cur))
        cur = parent.get(cur)
    return [path]


def impact_analysis(db: DB, name: str, max_depth: int = 3, limit: int = 50) -> dict:
    """Reverse BFS from a symbol; bucket results HIGH (direct) / MEDIUM (indirect),
    and flag test-related files."""
    roots = find_symbols(db, name)
    if not roots:
        return {"symbol": name, "error": "not_found", "impact": {"HIGH": [], "MEDIUM": []}, "tests": []}
    root_ids, member_ids = _expand_container_roots(db, roots)

    buckets: dict[str, list[dict]] = {"HIGH": [], "MEDIUM": []}
    seen: set[int] = set()
    frontier = list(root_ids)
    for depth in range(max_depth):
        nxt: list[int] = []
        for sid in frontier:
            for c, via in _callers_with_class(db, sid):
                if c in seen or c in root_ids or c in member_ids:
                    continue
                seen.add(c)
                info = symbol_by_id(db, c)
                if info:
                    key = "HIGH" if depth == 0 else "MEDIUM"
                    brief = _impact_brief(info)
                    # "text" entries are unresolved edges whose text names the
                    # symbol -- a guess, not a stored call. Surfaced so a HIGH
                    # impact is not read as a certainty.
                    if via != "resolved":
                        brief["via"] = via
                    buckets[key].append(brief)
                nxt.append(c)
        frontier = nxt
        if not frontier:
            break

    def is_test(info: dict) -> bool:
        p = info.get("path", "").lower()
        return "test" in p or "spec" in p or "tests" in p

    tests = [i for b in buckets.values() for i in b if is_test(i)]
    for k in buckets:
        buckets[k] = [i for i in buckets[k] if not is_test(i)][:limit]

    total = len(buckets["HIGH"]) + len(buckets["MEDIUM"]) + len(tests)
    return {
        "symbol": name,
        "found": True,
        "impact": buckets,
        "tests": tests[:limit],
        "total_affected": total,
    }


def _impact_brief(info: dict) -> dict:
    out = {
        "name": info["name"],
        "qualified_name": info["qualified_name"],
        "kind": info["kind"],
        "file": info["path"],
        "lines": f"{info['start_line']}-{info['end_line']}",
        "signature": (info["signature"] or "")[:120],
    }
    np = name_path(info["qualified_name"])
    if np and np != info["name"]:
        # emit the slash name path only for nested symbols: a top-level name is
        # already identical in both spellings, so the key would be pure noise
        out["name_path"] = np
    return out


# Module specifier of one import statement. The ESM `import <bindings> from
# '<path>'` branch must come first: bare `import\s+` matched the *bindings*, so
# `import axios from './lib/axios.js'` resolved the name "axios" -- the local
# variable, not the path. Measured on axios: 395 of ~700 import rows use that
# form, i.e. more than half of its dependency graph resolved by variable name.
_IMP_RE = re.compile(
    r"(?:"
    r"import\s+[^'\"]*?\bfrom\s+"   # ESM: import X / {a, b} / * as ns from 'p'
    r"|from\s+"                      # python: from pkg.mod import name
    r"|import\s+"                    # bare side-effect import: import 'p'
    r"|require\(|using\s+"           # CommonJS / C#
    r")(['\"]?)([\w./@~-]+)",
    re.IGNORECASE,
)


def _imported_names(text: str) -> list[str]:
    """Symbols actually brought into scope by one import line.

    ``from pkg.mod import A, B as C`` -> [A, B, C]; ``import pkg.mod`` -> [mod].
    Used by rename_impact so ``from app.agents.resource_agents import
    DocumentAgent`` no longer counts as a reference to ``RESOURCE_AGENTS``
    (which only shares the module path).
    """
    m = re.match(r"^\s*from\s+([\w.]+)\s+import\s+(.*)$", text.strip(), re.I)
    if m:
        names: list[str] = []
        for part in m.group(2).split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                part = part.split(" as ", 1)[-1].strip()
            part = part.strip()
            if part and (part[0] in "\"'(" or part == "*"):
                continue  # 'import *', 'import ("a")', string wildcards
            names.append(part)
        return [n for n in names if n]
    m = re.match(r"^\s*import\s+(.+)$", text, re.I)
    if m:
        tail: list[str] = []
        for part in m.group(1).split(","):
            part = part.strip()
            if " as " in part:
                part = part.split(" as ", 1)[-1].strip()
            tail.append(part.rsplit(".", 1)[-1].strip())
        return [n for n in tail if n]
    return []


def _like_escape(s: str) -> str:
    """Escape LIKE wildcards so a path containing `%`/`_` matches literally
    (was: `my_file_v2.py` wildcard-matched an existing `myXfile_v2.py`)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def resolve_file(db: DB, path: str) -> str | None:
    """Best-effort path lookup: exact match, then path-suffix, then basename.

    Clients (LLMs) often pass a bare filename like ``main.py`` while the
    index stores project-relative paths. If the hint is ambiguous, prefer
    an unambiguous suffix match and otherwise return None (caller reports).
    """
    if not path:
        return None
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if p.endswith("/"):
        p = p.rstrip("/")
    exact: list[str] = [r[0] for r in db.conn.execute("SELECT path FROM files WHERE path = ?", (p,))]
    if len(exact) == 1:
        return exact[0]
    suffix = [
        r[0]
        for r in db.conn.execute(
            "SELECT path FROM files WHERE path LIKE ? ESCAPE '\\'", (f"%/{_like_escape(p)}",)
        )
    ]
    if len(suffix) == 1:
        return suffix[0]
    base = p.rsplit("/", 1)[-1]
    basenames = [
        r[0]
        for r in db.conn.execute(
            "SELECT path FROM files WHERE path LIKE ? ESCAPE '\\'", (f"%/{_like_escape(base)}",)
        )
    ]
    if len(basenames) == 1:
        return basenames[0]
    if len(suffix) > 1 and all(x.endswith("/" + p) for x in suffix):
        return None  # ambiguous: caller decides via candidates
    return None


def file_symbols(db: DB, path: str, limit: int = 200) -> tuple[list[dict], bool]:
    """All indexed symbols declared in one file, in source order.

    Returns ``(symbols, truncated)``: ``limit + 1`` rows are fetched so the
    caller can tell a complete list from a capped one (a silent cap made a
    200-symbol file look like it had only 12).
    """
    resolved = resolve_file(db, path)
    if resolved is None:
        return [], False
    rows = db.conn.execute(
        """SELECT s.id, s.name, s.kind, s.qualified_name, s.signature,
                  s.start_line, s.end_line, f.path
           FROM symbols s JOIN files f ON f.id = s.file_id
           WHERE f.path = ? ORDER BY s.start_line, s.start_col LIMIT ?""",
        (resolved, limit + 1),
    ).fetchall()
    truncated = len(rows) > limit
    return [
        {"id": r[0], "symbol": r[1], "kind": r[2], "qualified_name": r[3],
         "signature": (r[4] or "")[:120], "lines": f"{r[5]}-{r[6]}", "file": r[7]}
        for r in rows[:limit]
    ], truncated


_alias_cache: dict[tuple[Path, str], dict[str, str]] = {}
# Keyed by (root, importing *directory*): every file in a directory resolves
# the same aliases, so the cache stays proportional to the number of
# directories rather than files. Bounded with LRU-style eviction — clearing the
# whole cache on overflow would thrash on repos with many directories.
_ALIAS_CACHE_MAX = 4096
_ALIAS_MAX_ASCENT = 64


def _alias_prefixes(db: DB, import_file: str | None = None) -> dict[str, str]:
    """Import alias prefix → directory (relative to the config's own dir).

    Config is looked up from the importing file's directory upward to the
    project root, so sub-projects (e.g. a uni-app miniapp folder) resolve
    their own aliases (`@` → miniapp root when pages.json lives there).
    Sources (deeper dirs override): tsconfig/jsconfig compilerOptions paths,
    the compilerOptions ``baseUrl`` (kept under the ``""`` key), vite
    resolve.alias, and the uni-app convention. Cached per (root, importing
    directory); never guesses when no config exists.
    """
    root = db.root
    base_dir = (root / import_file).parent if import_file else root
    key = (root, str(base_dir))
    cached = _alias_cache.get(key)
    if cached is not None:
        return cached
    m: dict[str, str] = {}
    dirs: list[Path] = []
    cur = base_dir
    for _ in range(_ALIAS_MAX_ASCENT):
        dirs.append(cur)
        if cur == root:
            break
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    dirs.reverse()  # root first, deepest dir overrides on conflict
    for d in dirs:
        for cfg_name in ("jsconfig.json", "tsconfig.json"):
            cfg = d / cfg_name
            if not cfg.is_file():
                continue
            try:
                data = json.loads(cfg.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            paths = (data.get("compilerOptions") or {}).get("paths") or {}
            for key_, targets in paths.items():
                if not targets or not isinstance(targets, list):
                    continue
                alias = key_.split("/*")[0].rstrip("*")
                tgt = str(targets[0]).split("/*")[0].rstrip("*")
                if alias and tgt:
                    m[alias] = tgt.strip("./")
            base_url = (data.get("compilerOptions") or {}).get("baseUrl")
            if isinstance(base_url, str):
                # "" is the sentinel entry: bare specifiers resolve from here,
                # and an empty value means the config's own directory. Without
                # it a baseUrl project's bare imports would look like packages.
                m[""] = base_url.strip().strip("./")
        for vname in ("vite.config.js", "vite.config.ts", "vite.config.mjs"):
            vcfg = d / vname
            if not vcfg.is_file():
                continue
            txt = vcfg.read_text(encoding="utf-8", errors="replace")
            for mm in re.finditer(r"alias\s*:\s*\{([\s\S]*?)\}", txt):
                for am in re.finditer(
                    r"['\"]([@\w/-]+)['\"]\s*:\s*['\"]?([^'\"\s,}]+)", mm.group(1)
                ):
                    m[am.group(1)] = am.group(2).strip("'\"")
        if not any(k == "@" for k in m) and (d / "pages.json").is_file():
            m["@"] = ""  # uni-app: @ → this directory (sub-project root)
    if len(_alias_cache) >= _ALIAS_CACHE_MAX:
        _alias_cache.pop(next(iter(_alias_cache)), None)  # evict oldest
    _alias_cache[key] = m
    return m


# Import forms the generic regex above cannot express. Go imports a
# parenthesised block of quoted paths, Rust imports ``use a::b::Item``, and
# C/C++ imports ``#include "x.h"`` / ``#include <x>``; none contains a keyword
# ``_IMP_RE`` knows, so those three languages produced *no* internal dependency
# edges at all (empty file_deps / module_cycles / layering) even though their
# imports were collected by the parsers.
_GO_PATH_RE = re.compile(r'"([^"\n]+)"')
_RUST_USE_RE = re.compile(r"\buse\s+([^;{]+)", re.IGNORECASE)
_RUST_PREFIX_RE = re.compile(r"^(?:crate|self|super)(?:::|$)")
_CPP_INCLUDE_RE = re.compile(r'#\s*include\s*[<"]([^>"]+)[>"]')


def _go_modules(text: str) -> list[str]:
    """``import (\n "bytes"\n "path/filepath"\n)`` -> its quoted paths."""
    return _GO_PATH_RE.findall(text)


def _rust_modules(text: str) -> list[str]:
    """``use crate::a::b::Item;`` -> ``["a.b"]`` (the module the item lives in).

    Rust paths are ``::``-separated and normally end in the imported item, so
    the last segment is dropped when more than one remains; ``crate``/``self``/
    ``super`` are stripped because resolution matches file stems, not crate
    roots. A braced group (``use a::b::{C, D}``) imports from the path before
    the brace.
    """
    out: list[str] = []
    for raw in _RUST_USE_RE.findall(text):
        path = _RUST_PREFIX_RE.sub("", raw.split("{", 1)[0].strip()).strip(":")
        segs = [s for s in path.split("::") if s and s != "*"]
        if not segs:
            continue
        if len(segs) > 1:
            segs = segs[:-1]
        out.append(".".join(segs))
    return out


def _cpp_modules(text: str) -> list[str]:
    """``#include "core.h"`` -> ``["core.h"]``; ``#include <vector>`` -> ``["vector"]``.

    The path and extension are kept (only leading separators are dropped): the
    extension is what keeps ``"jv.h"`` from resolving to a sibling ``jv.c``, and
    a relative include path resolves next to the including file.
    """
    out: list[str] = []
    for raw in _CPP_INCLUDE_RE.findall(text):
        path = raw.replace("\\", "/").lstrip("/")
        if path:
            out.append(path)
    return out


_MODULE_EXTRACTORS = {"go": _go_modules, "rust": _rust_modules, "cpp": _cpp_modules}

# ---- module-root aware resolution (Go modules, Rust crates) ----
#
# Both languages define what an import path means relative to a build-file root,
# so resolution can be exact instead of "a file somewhere with this name":
# go.mod's `module` line turns "github.com/spf13/cobra/internal/x" into the
# directory internal/x, and Rust's crate root turns `crate::a::b` into
# <crate>/src/a/b.rs (or a/b/mod.rs). Lookups are cached per (root, directory).
_GO_PREFIX_CACHE_MAX = 4096
_go_module_cache: dict[tuple, tuple[str, str] | None] = {}
_rust_root_cache: dict[tuple, str | None] = {}


def _cached_put(cache: dict, key: tuple, value) -> None:
    if len(cache) >= _GO_PREFIX_CACHE_MAX:
        cache.pop(next(iter(cache)), None)  # evict oldest
    cache[key] = value


def _go_module_for(db: DB, import_file: str) -> tuple[str, str] | None:
    """``(module path, directory holding its go.mod)`` for the importing file.

    The nearest go.mod upward defines the module a file belongs to, which is
    what makes an import path decidable: anything under ``<module>/`` is an
    in-repo package, anything else is stdlib or a third-party module.
    """
    directory = import_file.rpartition("/")[0]
    key = (db.root, directory)
    if key in _go_module_cache:
        return _go_module_cache[key]
    result: tuple[str, str] | None = None
    d = directory
    while True:
        cfg = (db.root / d / "go.mod") if d else (db.root / "go.mod")
        if cfg.is_file():
            try:
                text = cfg.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            m = re.search(r"(?m)^\s*module\s+(\S+)", text)
            if m:
                result = (m.group(1).strip('"'), d)
            break
        if not d:
            break
        d = d.rpartition("/")[0]
    _cached_put(_go_module_cache, key, result)
    return result


def _rust_crate_root(db: DB, import_file: str) -> str | None:
    """The crate root directory (``…/src``, ``…/tests``) of the importing file.

    ``crate::`` paths are relative to that root, and an integration test is its
    own crate rooted at ``tests/`` — which is why ``tests/binary.rs``'s
    ``use crate::util::…`` means ``tests/util.rs`` rather than a same-named file
    under some other crate's src/.
    """
    directory = import_file.rpartition("/")[0]
    key = (db.root, directory)
    if key in _rust_root_cache:
        return _rust_root_cache[key]
    marked = f"/{import_file}"
    root: str | None = None
    for marker in ("src", "tests", "benches", "examples"):
        idx = f"/{marker}/"
        if idx in marked:
            # split the *marked* form: at the project root there is no leading
            # slash in the stored path, so splitting it directly misses
            prefix = marked.split(idx, 1)[0].lstrip("/")
            root = f"{prefix}/{marker}" if prefix else marker
            break
    _cached_put(_rust_root_cache, key, root)
    return root


def _dir_files(db: DB, rel_dir: str, allowed: set[str] | None) -> list[str]:
    """Indexed files directly inside ``rel_dir`` (a package/module directory)."""
    entries = db.dir_stem_map().get(rel_dir)
    if not entries:
        return []
    out: list[str] = []
    for paths in entries.values():
        for p in paths:
            if _lang_ok(allowed, p) and p not in out:
                out.append(p)
    return out


def _go_targets(db: DB, import_text: str, import_file: str) -> list[str] | None:
    """Resolve Go imports through go.mod, or None when there is no module file."""
    info = _go_module_for(db, import_file)
    if info is None:
        return None
    module, mod_dir = info
    allowed = _LANG_TARGET_EXTS.get("go")
    out: list[str] = []
    for path in _go_modules(import_text):
        if path == module:
            rel = mod_dir
        elif path.startswith(module + "/"):
            tail = path[len(module) + 1:]
            rel = f"{mod_dir}/{tail}" if mod_dir else tail
        else:
            continue  # stdlib or another module: external by definition
        for f in _dir_files(db, rel, allowed):
            if f not in out:
                out.append(f)
    return out[:5]


def _rust_use_paths(text: str) -> list[tuple[str, int, list[str]]]:
    """``use`` paths as ``(kind, super_hops, segments)``.

    ``kind`` is ``crate`` / ``self`` / ``super`` for a crate-relative path and
    ``""`` for a bare path (an external crate, or Rust 2015 style).
    """
    out: list[tuple[str, int, list[str]]] = []
    for raw in _RUST_USE_RE.findall(text):
        segs = [s for s in raw.split("{", 1)[0].strip().split("::") if s and s != "*"]
        if not segs:
            continue
        kind = ""
        hops = 0
        while segs and segs[0] in ("crate", "self", "super"):
            head = segs.pop(0)
            if head == "crate":
                kind = "crate"
            elif head == "self":
                kind = kind or "self"
            else:
                kind = "super"
                hops += 1
        out.append((kind, hops, segs))
    return out


def _rust_targets(db: DB, import_text: str, import_file: str) -> list[str] | None:
    """Resolve crate-relative Rust `use` paths.

    Returns None when there is no structural opinion to offer (no crate root, or
    no ``crate::``-style path in the text), so the caller can fall back to name
    matching for bare paths.
    """
    paths = [p for p in _rust_use_paths(import_text) if p[0]]
    root = _rust_crate_root(db, import_file)
    if root is None or not paths:
        return None
    allowed = _LANG_TARGET_EXTS.get("rust")
    dirs = db.dir_stem_map()
    file_dir = import_file.rpartition("/")[0]
    out: list[str] = []

    def hits(base: str, segs: list[str]) -> list[str]:
        # the path names a module file, or an item inside that module, so try
        # the whole path first and then drop the last segment
        for n in (len(segs), len(segs) - 1):
            if n <= 0:
                continue
            sub = "/".join(segs[:n])
            parent, _, name = f"{base}/{sub}".rpartition("/")
            found = [
                p
                for p in dirs.get(parent, {}).get(name.lower(), ())
                if _ext_ok(".rs", p) and _lang_ok(allowed, p)
            ]
            if found:
                return found
            found = [
                p
                for p in dirs.get(f"{base}/{sub}", {}).get("mod", ())
                if _ext_ok(".rs", p) and _lang_ok(allowed, p)
            ]
            if found:
                return found
        return []

    for kind, hops, segs in paths:
        if kind == "crate":
            found = hits(root, segs)
        else:
            # self:: / super:: are module-relative, and a module file's parent
            # module is usually its own directory (a/b.rs -> module a::b; only
            # mod.rs sits one level below). Walk upward so both layouts resolve.
            base = file_dir
            for _ in range(max(0, hops - 1)):
                base = base.rpartition("/")[0]
            found = []
            while True:
                found = hits(base, segs)
                if found or not base:
                    break
                base = base.rpartition("/")[0]
        for f in found:
            if f not in out:
                out.append(f)
    return out[:5]


# Extensions an import may name explicitly. When it does, only files with a
# compatible extension may match: `#include "jv.h"` must not resolve to jv.c
# (that single conflation was 92 of jq's 363 import rows and most of fmt's).
_SOURCE_EXTS = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx",
    ".vue", ".svelte", ".java", ".go", ".rs",
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",
}
# TS projects import "./x.js" for a source file named x.ts (Node's TS
# resolution), so a .js specifier may land on a TS file as well. The families
# are kept narrow otherwise: `.js` must not match a sibling `.cjs`/`.mjs`/
# `.vue`, which is exactly what the last ambiguous rows on axios were.
_EXT_ALIASES = {
    ".js": {".js", ".jsx", ".ts", ".tsx"},
    ".jsx": {".jsx", ".tsx"},
    ".mjs": {".mjs", ".mts"},
    ".cjs": {".cjs", ".cts"},
    ".py": {".py", ".pyi"},
}
# Include families stay strict: a header specifier must match a header.
for _family in ((".h",), (".hh", ".hpp", ".hxx")):
    for _e in _family:
        _EXT_ALIASES[_e] = set(_family)


def _split_ext(mod: str) -> tuple[str, str]:
    """Peel a trailing source extension off a module candidate.

    ``"jv.h"`` -> ``("jv", ".h")``; ``"lib.axios"`` -> ``("lib.axios", "")``.
    """
    base, dot, tail = mod.rpartition(".")
    if dot:
        ext = f".{tail.lower()}"
        if ext in _SOURCE_EXTS:
            return base, ext
    return mod, ""


# Which file types an import from a given language may resolve to. Without this
# a Python `import os` resolved to the C++ files os.h / os.cc in the same repo
# (fmt's last two ambiguous rows), and any mixed-language repo could
# cross-connect by name alone.
_LANG_TARGET_EXTS: dict[str, set[str]] = {
    "python": {".py", ".pyi"},
    "java": {".java"},
    "go": {".go"},
    "rust": {".rs"},
    "cpp": {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"},
}
_JS_FAMILY_EXTS = {
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx", ".vue", ".svelte",
}
for _js_lang in ("javascript", "typescript", "tsx", "vue", "svelte"):
    _LANG_TARGET_EXTS[_js_lang] = set(_JS_FAMILY_EXTS)
# Languages whose bare specifiers are package names, not project paths: under
# Node resolution `vitest/config` is a node_modules package, and matching it to
# a project file named vitest.config.js was 60 of axios's remaining ambiguous
# rows. Python/Java/Go/Rust bare names *are* project paths, so this is JS-only.
_JS_FAMILY = {"javascript", "typescript", "tsx", "vue", "svelte"}


def _ext_ok(want: str, path: str) -> bool:
    """True when ``path`` may satisfy an import that named extension ``want``."""
    if not want:
        return True
    got = Path(path).suffix.lower()
    return got == want or got in _EXT_ALIASES.get(want, ())


def _lang_ok(allowed: set[str] | None, path: str) -> bool:
    """True when ``path`` is a plausible target for the importing language."""
    return allowed is None or Path(path).suffix.lower() in allowed


# A specifier may name a *directory* rather than a file: under Node/TS
# resolution `./server` is `server/index.ts`, and a Python package import
# (`from .pkg import x`) is `pkg/__init__.py`. Neither named an indexed file, so
# vite's `import './importing-updated'` rows resolved to nothing (35 unresolved
# rows on a repo where every other gap was closed).
_DIR_ENTRY_STEMS = ("index", "__init__")
# Only Python and JS-family files act as directory entries: `index.h` is just a
# file named index, so a C++ `#include "./x.h"` must not fall into a directory.
_DIR_ENTRY_EXTS = {".py", ".pyi"} | set(_JS_FAMILY_EXTS)


def _dir_entry_files(
    dirs: dict[str, dict[str, list[str]]], d: str, want_ext: str, allowed: set[str] | None
) -> list[str]:
    """Entry-point files (``index.*`` / ``__init__.*``) of directory ``d``.

    An explicit extension means the specifier names a file
    (``./server.js`` must not land in a ``server/`` directory), so the lookup
    only applies to extension-less specifiers.
    """
    if want_ext:
        return []
    sub = dirs.get(d)
    if not sub:
        return []
    out: list[str] = []
    for stem in _DIR_ENTRY_STEMS:
        for p in sub.get(stem, ()):
            if (
                p not in out
                and Path(p).suffix.lower() in _DIR_ENTRY_EXTS
                and _ext_ok(want_ext, p)
                and _lang_ok(allowed, p)
            ):
                out.append(p)
    return out


def _local_entry_lookup(
    db: DB, src_file: str, rel: str, allowed: set[str] | None
) -> list[str]:
    """Resolve ``rel`` as a *directory* holding the module entry file.

    ``rel`` is the specifier with ``/`` separators (``server``, ``pkg/sub``); it
    is tried as a subdirectory of the importing file's directory and of each
    ancestor, which covers ``./server`` (same directory) and a Python package
    path (``pkg.sub`` rooted at a directory on that chain).
    """
    dirs = db.dir_stem_map()
    d = src_file.rpartition("/")[0]
    while True:
        sub = f"{d}/{rel}" if d else rel
        hits = _dir_entry_files(dirs, sub, "", allowed)
        if hits:
            return hits
        if not d:
            return []
        d = d.rpartition("/")[0]


def _local_lookup(
    db: DB, src_file: str, stem: str, want_ext: str, allowed: set[str] | None
) -> list[str]:
    """Files named ``stem`` in the importing file's directory, then ancestors.

    A relative import, a quoted ``#include`` and a crate-relative ``use`` all
    resolve next to the importing file long before they resolve by basename
    anywhere in the repo. Trying this first is what stops
    ``tests/binary.rs``'s ``use crate::util::…`` from matching a same-named
    ``util.rs`` in another crate (14 of ripgrep's 17 ambiguous rows).
    """
    dirs = db.dir_stem_map()
    d = src_file.rpartition("/")[0]
    want = stem.lower()
    while True:
        hits = [
            p
            for p in dirs.get(d, {}).get(want, ())
            if _ext_ok(want_ext, p) and _lang_ok(allowed, p)
        ]
        if hits:
            return hits
        if not d:
            return []
        d = d.rpartition("/")[0]


def _resolve_module(
    db: DB,
    mod: str,
    import_file: str,
    import_text: str,
    allowed: set[str] | None = None,
    bare_is_external: bool = False,
) -> list[str]:
    """Resolve one module candidate to indexed files (shared normalization).

    Order: named aliases -> tsconfig ``baseUrl`` -> the importing file's own
    directory and its ancestors -> a repo-wide dotted-stem suffix match. Every
    step honors the extension the import named and the importing language's
    plausible target types.
    """
    mod, want_ext = _split_ext(mod)
    aliases = _alias_prefixes(db, import_file)
    bare = not mod.startswith((".", "/"))
    # configured import aliases (`@/x`, tsconfig paths, vite alias): substitute
    # the prefix before the stem matching below
    for alias, tgt in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
        if not alias:  # "" is the baseUrl sentinel, handled below
            continue
        if mod == alias or mod.startswith(alias + "/"):
            rest = mod[len(alias):].lstrip("/")
            mod = f"{tgt}/{rest}" if tgt else rest
            bare = False
            break
    if bare and "" in aliases:
        # tsconfig baseUrl: bare specifiers resolve from that directory (an
        # empty value means the config's own directory)
        base = aliases[""]
        mod = f"{base}/{mod}" if base else mod
        bare = False
    if bare and bare_is_external:
        return []  # a package, not a project path
    # A relative path naming a file ("./classes/x.js") resolves against the
    # importing file's directory as a *path*: the basename fallback below would
    # happily pick the same-named file of a sibling platform instead (browser/
    # vs node/ build variants -- the last ambiguous rows on axios).
    if import_file and mod.startswith(".") and "/" in mod:
        base_dir = import_file.rpartition("/")[0]
        head, _, tail = mod.rpartition("/")
        target_dir = posixpath.normpath(posixpath.join(base_dir, head))
        if target_dir == ".":
            target_dir = ""
        dirs = db.dir_stem_map()
        hits = [
            p
            for p in dirs.get(target_dir, {}).get(tail.lower(), ())
            if _ext_ok(want_ext, p) and _lang_ok(allowed, p)
        ]
        if hits:
            return hits
        # …or the specifier names a *directory* whose entry file is the module
        # (`import './importing-updated'` -> importing-updated/index.js).
        sub = f"{target_dir}/{tail}" if target_dir else tail
        entry = _dir_entry_files(dirs, sub, want_ext, allowed)
        if entry:
            return entry
    if mod.startswith((".", "/")):
        rel = mod[1:] if mod.startswith(".") else mod
        mod = rel.replace("/", ".")
    else:
        mod = mod.replace("/", ".")
    mod = mod.strip(".")
    # Match case-insensitively: Java/C# fully-qualified names are mixed-case
    # (com.travel...RateLimiter), and the file stems are lowercased, so a
    # case-sensitive compare would never match them (A8).
    mod = mod.lower()
    entries: list[str] = []
    if import_file and mod:
        local = _local_lookup(db, import_file, mod.rsplit(".", 1)[-1], want_ext, allowed)
        if local:
            return local
        # …or the specifier names a package directory rather than a module file
        # (`from .pkg import x` -> pkg/__init__.py; `import pkg.sub` ->
        # pkg/sub/__init__.py). Held back as a fallback: a real same-named
        # module anywhere (suffix lookup, `from pkg import sub`) is the better
        # answer, and returning both would turn a single match into noise.
        if not want_ext:
            entries = _local_entry_lookup(db, import_file, mod.replace(".", "/"), allowed)
    # Suffix lookup instead of a files-table scan: ``mod`` matches a file when
    # its dotted stem equals ``mod`` or ends with ``.{mod}`` — exactly the set
    # of files whose stem has ``mod`` as a suffix.
    by_suffix = db.stem_suffix_map()
    candidates: list[str] = [
        p for p in by_suffix.get(mod, ()) if _ext_ok(want_ext, p) and _lang_ok(allowed, p)
    ]
    # `from pkg import a, b, c` (multi-symbol package import): the regex only
    # captured `pkg`, so also resolve each imported name against pkg's dir.
    _multi = re.match(r"\s*from\s+([\w./@~-]+)\s+import\s+(.+)", import_text, re.IGNORECASE)
    if not candidates and _multi:
        pkg_part = _multi.group(1)
        names_part = _multi.group(2).split(" as ")[0]
        for name in (n.strip().rstrip(",") for n in names_part.split(",")):
            if not name or "." in name or name in ("*", "(", ")"):
                continue
            if not mod and pkg_part.startswith(".") and import_file:
                # `from . import x` / `from .. import x`: the module part is
                # empty, and x is a module or package inside the importing
                # file's own package directory -- one level up per extra dot.
                # The suffix lookup below cannot see this form (`.` never
                # matches a stem), so requests' 11 `from . import _types`
                # rows resolved to nothing.
                base = import_file.rpartition("/")[0]
                for _ in range(len(pkg_part) - 1):
                    base = base.rpartition("/")[0]
                dirs = db.dir_stem_map()
                before = len(candidates)
                for p in dirs.get(base, {}).get(name.lower(), ()):
                    if p not in candidates and _ext_ok(want_ext, p) and _lang_ok(allowed, p):
                        candidates.append(p)
                sub = f"{base}/{name}" if base else name
                for p in _dir_entry_files(dirs, sub, want_ext, allowed):
                    if p not in candidates:
                        candidates.append(p)
                if len(candidates) == before:
                    # neither a module nor a subpackage of `.`: the name comes
                    # from the package entry itself (requests' tests re-export
                    # SNIMissingWarning from tests/__init__.py)
                    for p in _dir_entry_files(dirs, base, want_ext, allowed):
                        if p not in candidates:
                            candidates.append(p)
                continue
            for p in by_suffix.get(f"{mod}.{name.lower()}", ()):
                if p not in candidates and _ext_ok(want_ext, p) and _lang_ok(allowed, p):
                    candidates.append(p)
    if not candidates:
        # nothing named `mod` exists: the specifier is a package directory
        return entries
    return candidates


def _without_self(targets: list[str], import_file: str) -> list[str]:
    """Drop the importing file from its own import targets.

    A package-level import resolves to every file of that package, which can
    include the importer itself (a Go ``_test`` package importing its own
    directory, a Rust ``mod.rs`` re-exporting a child). Nothing depends on
    itself, and such an edge surfaced as a bogus 1-file cycle.

    The cap is high enough for a package directory; a low one silently dropped
    real dependencies of packages with many files.
    """
    return [t for t in targets if t != import_file][:20]


def import_targets(db: DB, import_text: str, import_file: str) -> list[str]:
    """Guess which indexed files an import statement refers to."""
    lang = language_for_path(import_file) or ""
    allowed = _LANG_TARGET_EXTS.get(lang)
    bare_external = lang in _JS_FAMILY
    # Go and Rust know their own module roots, so resolve those structurally:
    # "<module>/internal/x" and crate::a::b name a *directory*, and matching
    # their last segment against file stems would happily pick a same-named file
    # from another module or crate.
    if lang == "go":
        structured = _go_targets(db, import_text, import_file)
        if structured is not None:
            return _without_self(structured, import_file)
    elif lang == "rust":
        structured = _rust_targets(db, import_text, import_file)
        if structured is not None:
            return _without_self(structured, import_file)
    extractor = _MODULE_EXTRACTORS.get(lang)
    if extractor is None:
        m = _IMP_RE.search(import_text)
        mods = [m.group(2)] if m else []
    else:
        mods = extractor(import_text)
        if lang == "go":
            # no go.mod to resolve against: fall back to the package name in the
            # last segment, and only for >=3 segments so that two-segment stdlib
            # paths ("net/http") cannot match an unrelated same-named file
            mods = mods + [m.rsplit("/", 1)[-1] for m in mods if m.count("/") >= 2]
    out: list[str] = []
    for mod in mods:
        for target in _resolve_module(
            db, mod, import_file, import_text, allowed, bare_external
        ):
            if target not in out:
                out.append(target)
    return _without_self(out, import_file)


def module_dependencies(db: DB, path: str) -> dict:
    """File-level import view: what a file imports, and who imports it."""
    resolved = resolve_file(db, path)
    if resolved is None:
        ambiguous = [
            r[0]
            for r in db.conn.execute(
                "SELECT path FROM files WHERE path LIKE ? ORDER BY path",
                (f"%/{path.rsplit('/', 1)[-1]}",),
            )
        ]
        if len(ambiguous) > 1:
            return {"found": False, "path": path, "ambiguous": True, "candidates": ambiguous[:10]}
        return {"found": False, "path": path}
    fid = db.get_file_id(resolved)
    if fid is None:
        return {"found": False, "path": resolved}
    imports: list[dict] = []
    for text, line in db.conn.execute(
        "SELECT text, line FROM file_imports WHERE file_id = ? ORDER BY line", (fid,)
    ):
        imports.append({"text": text[:120], "line": line, "resolves_to": import_targets(db, text, path)})

    stem = path.rsplit(".", 1)[0].replace("/", ".").lower()
    importers: list[dict] = []
    for (fid2, p) in db.conn.execute("SELECT id, path FROM files WHERE id != ?", (fid,)):
        for text, line in db.conn.execute(
            "SELECT text, line FROM file_imports WHERE file_id=?", (fid2,)
        ):
            for t in import_targets(db, text, p):
                tstem = t.rsplit(".", 1)[0].replace("/", ".").lower()
                if tstem == stem or tstem.endswith("." + stem):
                    importers.append({"file": p, "line": line, "import": text[:120]})
                    break
    return {"found": True, "imports": imports[:30], "importers": importers[:30]}


def project_overview(db: DB) -> dict:
    files = db.conn.execute(
        "SELECT path, language FROM files ORDER BY path"
    ).fetchall()
    by_lang: dict[str, int] = {}
    for _, lang in files:
        by_lang[lang] = by_lang.get(lang, 0) + 1
    return {
        "files": len(files),
        "symbols": db.count_symbols(),
        "languages": by_lang,
        "index_version": db.get_meta("index_version"),
        "top_level": {
            r[0]: r[1]
            for r in db.conn.execute(
                "SELECT substr(path, 1, instr(path, '/') - 1) || '', COUNT(*) FROM files "
                "WHERE instr(path, '/') > 0 GROUP BY 1 ORDER BY 2 DESC LIMIT 15"
            )
        },
        "entry_points": _entry_points(db),
        "layering": _layering(db),
        "parse_errors": [e["file"] for e in db.parse_errors(limit=50)],
    }


# Framework lifecycle callbacks are registered by the framework (uni-app page
# lifecycle, Vue options API hooks) and never called by name in source code, so
# a missing incoming call edge does NOT mean dead code. Scoped to .vue/.svelte
# files so plain JS/TS modules keep full coverage.
_FRAMEWORK_LIFECYCLE = {
    # uni-app / WeChat mini-program page + app lifecycle
    "onLoad", "onShow", "onHide", "onUnload", "onReady",
    "onPullDownRefresh", "onReachBottom", "onShareAppMessage",
    "onShareTimeline", "onPageScroll", "onTabItemTap", "onResize",
    "onBackPress", "onNavigationBarButtonTap",
    "onLaunch", "onError", "onThemeChange", "onPageNotFound",
    "onUnhandledRejection",
    # Vue options API lifecycle hooks
    "beforeCreate", "created", "beforeMount", "mounted",
    "beforeUpdate", "updated", "beforeUnmount", "unmounted",
    "activated", "deactivated", "errorCaptured",
    "beforeDestroy", "destroyed", "setup",
}


def unused_symbols(db: DB, limit: int = 50) -> list[dict]:
    """Potentially dead code: methods/functions with no incoming call edge.

    Incoming means either a resolved id edge (target_id) or a raw-text edge
    (`instance.method` / `new X()` / `X()` shapes). Constructors, interface
    members, test/spec paths and entry-point files are excluded by design.
    Output is a *candidate* list: confirm with find_callers before deleting.
    """
    by_id: set[int] = set()
    texts: set[str] = set()
    for r in db.conn.execute(
        "SELECT target_id, target FROM relations WHERE rtype IN ('calls', 'references')"
    ):
        if r[0] is not None:
            by_id.add(r[0])
        if r[1]:
            texts.add(r[1])
    # O(1) per-symbol text check: exact name OR dotted-target first segment
    # (SQLite LIKE is ASCII case-insensitive; `.lower()` mirrors that)
    exact = {t.lower() for t in texts}
    first_seg = {t.split(".", 1)[0].lower() for t in texts if "." in t}
    ifaces = db.conn.execute(
        "SELECT file_id, start_line, end_line FROM symbols WHERE kind = 'interface'"
    ).fetchall()
    # Vue/Svelte: methods referenced only from the template (event/prop
    # bindings) never produce call edges; exclude them per (file, name).
    # Native miniapp pages bind handlers in a sibling .wxml — its refs are
    # stored under the .wxml file id, so merge them onto the page .js id.
    wxml_to_js: dict[int, int] = {}
    for (wpath,) in db.conn.execute("SELECT path FROM files WHERE language = 'wxml'"):
        wfid = db.get_file_id(wpath)
        jfid = db.get_file_id(wpath[:-5] + ".js")
        if wfid is not None and jfid is not None:
            wxml_to_js[wfid] = jfid
    tpl_refs = {
        (wxml_to_js.get(fid, fid), name)
        for fid, name in db.conn.execute("SELECT file_id, name FROM template_refs")
    }
    # miniapp page .js (has a sibling .wxml) or app.js: apply the framework
    # lifecycle list there too; standalone .js files keep full coverage.
    miniapp_js: set[int] = set()
    for (wpath,) in db.conn.execute("SELECT path FROM files WHERE language = 'wxml'"):
        jfid = db.get_file_id(wpath[:-5] + ".js")
        if jfid is not None:
            miniapp_js.add(jfid)
    # app.js lives at the project root or under miniprogram/; only consider it
    # a miniapp root when the project actually contains .wxml templates
    if db.conn.execute("SELECT 1 FROM files WHERE language = 'wxml' LIMIT 1").fetchone():
        for (afid,) in db.conn.execute(
            "SELECT id FROM files WHERE path = 'app.js' OR path LIKE '%/app.js'"
        ):
            miniapp_js.add(afid)

    def text_referenced(name: str, qname: str) -> bool:
        for cand in {name, qname}:
            cl = cand.lower()
            if cl in exact or cl in first_seg:
                return True
        return False

    out: list[dict] = []
    for r in db.conn.execute(
        """SELECT s.id, s.name, s.kind, s.qualified_name, s.signature, s.start_line,
                  f.path, f.id, s.decorated
           FROM symbols s JOIN files f ON f.id = s.file_id
           WHERE s.kind IN ('method', 'function')
           ORDER BY f.path, s.start_line"""
    ):
        sid, name, kind, qname, sig, line, path, fid, decorated = r
        if sid in by_id:
            continue
        # constructors are called via `Class()` instantiation, never by name:
        # Java uses kind='constructor', Python/TS name them `__init__`/`constructor`
        if name in ("__init__", "__new__", "__post_init__", "constructor"):
            continue
        # decorated/annotated symbols are registered by the framework
        # (FastAPI @app.get, Spring @GetMapping, pytest @fixture, ...)
        if decorated:
            continue
        if (fid, name) in tpl_refs:
            continue
        lp = path.lower()
        if name in _FRAMEWORK_LIFECYCLE and (
            lp.endswith((".vue", ".svelte"))
            or (lp.endswith(".js") and fid in miniapp_js)
        ):
            continue
        if "test" in lp or "spec" in lp or Path(path).name in _ENTRY_NAMES:
            continue
        # interface members are dispatched polymorphically, not called by name
        if any(fid == ifid and istart <= line <= iend for ifid, istart, iend in ifaces):
            continue
        if text_referenced(name, qname):
            continue
        out.append({
            "symbol": name,
            "qualified_name": qname,
            "kind": kind,
            "file": path,
            "lines": str(line),
            "signature": (sig or "")[:120],
        })
        if len(out) >= limit:
            break
    return out


def hot_symbols(db: DB, limit: int = 20) -> list[dict]:
    """Most-referenced symbols by resolved incoming call edge count,
    with a test/main split for each hotspot."""
    rows = db.conn.execute(
        """SELECT s.id, s.name, s.kind, s.qualified_name, s.start_line, f.path,
                  COUNT(*) AS n,
                  SUM(CASE WHEN sf.path LIKE '%test%' OR sf.path LIKE '%spec%'
                           OR sf.path LIKE '%tests%' THEN 1 ELSE 0 END) AS test_n
           FROM relations r
           JOIN symbols s ON s.id = r.target_id
           JOIN files f ON f.id = s.file_id
           LEFT JOIN symbols ss ON ss.id = r.source_id
           LEFT JOIN files sf ON sf.id = ss.file_id
           WHERE r.rtype = 'calls' AND r.target_id IS NOT NULL
           GROUP BY s.id
           ORDER BY n DESC, s.start_line
           LIMIT ?""",
        (limit,),
    )
    return [
        {
            "symbol": r[1],
            "qualified_name": r[3],
            "kind": r[2],
            "file": r[5],
            "lines": str(r[4]),
            "call_count": r[6],
            "test_calls": r[7] or 0,
        }
        for r in rows
    ]


def file_metrics(db: DB, limit: int = 20) -> list[dict]:
    """Per-file aggregation: symbol count, outgoing call edges, incoming
    call edges — a quick "which files are big/complex" table."""
    rows = db.conn.execute(
        """SELECT f.path,
                  (SELECT COUNT(*) FROM symbols ss WHERE ss.file_id = f.id) AS symbols,
                  (SELECT COUNT(*) FROM relations rr JOIN symbols ss ON ss.id = rr.source_id
                   WHERE ss.file_id = f.id AND rr.rtype = 'calls') AS outgoing,
                  (SELECT COUNT(*) FROM relations rr JOIN symbols ss ON ss.id = rr.target_id
                   WHERE ss.file_id = f.id AND rr.rtype = 'calls') AS incoming
           FROM files f
           ORDER BY symbols DESC, outgoing DESC
           LIMIT ?""",
        (limit,),
    )
    return [
        {"file": r[0], "symbols": r[1], "outgoing_calls": r[2], "incoming_calls": r[3]}
        for r in rows
    ]


def module_cycles(db: DB, max_cycles: int = 10) -> list[dict]:
    """Directed import cycles between files (Strongly Connected Components
    of the resolved-import graph). Self-imports count as 1-node cycles."""
    adj: dict[str, set[str]] = {}
    for (fid, path) in db.conn.execute("SELECT id, path FROM files"):
        targets: set[str] = set()
        for (text,) in db.conn.execute(
            "SELECT text FROM file_imports WHERE file_id = ?", (fid,)
        ):
            targets.update(import_targets(db, text, path))
        adj[path] = targets

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    onstack: set[str] = set()
    stack: list[str] = []
    counter = [0]
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack.add(v)
        for w in adj.get(v, ()):
            if w not in index:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in onstack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                onstack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for node in adj:
        if node not in index:
            strongconnect(node)

    cycles = [
        {"files": comp, "size": len(comp)}
        for comp in sccs
        if len(comp) > 1 or (len(comp) == 1 and comp[0] in adj.get(comp[0], ()))
    ]
    return sorted(cycles, key=lambda c: -c["size"])[:max_cycles]


_ENTRY_NAMES = {
    "main.py", "__main__.py", "app.py", "cli.py", "manage.py", "serve.py",
    "app.ts", "index.ts", "index.js", "index.tsx", "index.jsx", "main.ts", "main.go", "main.rs",
    # C/C++ and Java were missing, so a repo whose only entry point is main.c
    # (jq) or Main.java reported no entry points at all
    "main.c", "main.cc", "main.cpp", "main.cxx", "Main.java",
}


def _entry_points(db: DB) -> list[str]:
    """Files conventionally treated as entry points (main/app/index/cli)."""
    out: list[str] = []
    for (p,) in db.conn.execute("SELECT path FROM files ORDER BY path"):
        if Path(p).name in _ENTRY_NAMES and not p.startswith("test") and "test" not in p.lower():
            out.append(p)
    return out[:10]


def _layering(db: DB) -> dict:
    """Top-level dependency direction summary: dir A -> dir B counts."""
    counts: dict[str, int] = {}
    row_map = {r[0]: r[1] for r in db.conn.execute("SELECT id, path FROM files")}
    # use file-level imports instead: module -> module edges
    pairs: dict[tuple[str, str], int] = {}
    for (fid, text) in db.conn.execute("SELECT file_id, text FROM file_imports"):
        src = row_map.get(fid)
        if not src:
            continue
        src_top = src.split("/")[0] if "/" in src else "(root)"
        for cand in import_targets(db, text, src):
            tgt_top = cand.split("/")[0] if "/" in cand else "(root)"
            if src_top != tgt_top and "/" in cand:
                k = (src_top, tgt_top)
                pairs[k] = pairs.get(k, 0) + 1
    for (a, b), n in sorted(pairs.items(), key=lambda kv: -kv[1])[:10]:
        counts[f"{a} -> {b}"] = n
    return counts


def rename_impact(db: DB, name: str, limit: int = 100) -> dict:
    """Rename/change risk: every definition + every reference of a symbol.

    Uses both resolved relations (calls/inherits) and raw import text.
    """
    name = normalize_symbol_query(name)
    defs = find_symbols(db, name)
    refs: list[dict] = []
    if defs:
        # 1) references resolved via relations (callers/inheritors)
        for r in db.conn.execute(
            """SELECT s.name, f.path, r.line, r.rtype, r.target
               FROM relations r JOIN symbols s ON s.id = r.source_id
               JOIN files f ON f.id = s.file_id
               WHERE r.target_id IN (%s) OR r.target = ?
               ORDER BY f.path, r.line LIMIT ?"""
            % ",".join("?" * len(defs)),
            tuple(d["id"] for d in defs) + (name, limit),
        ):
            refs.append({"symbol": r[0], "file": r[1], "line": r[2], "rtype": r[3], "via_text": r[4][:60]})

        # 1b) unresolved same-name call targets (e.g. super().login), only for
        #     qualified requests, so bare-name renames don't explode
        if "." in name:
            short = name.rsplit(".", 1)[-1]
            for r in db.conn.execute(
                """SELECT s.name, f.path, r.line, r.rtype, r.target
                   FROM relations r JOIN symbols s ON s.id = r.source_id
                   JOIN files f ON f.id = s.file_id
                   WHERE r.rtype = 'calls' AND r.target_id IS NULL AND r.target = ?
                   ORDER BY f.path, r.line LIMIT ?""",
                (short, limit),
            ):
                refs.append({"symbol": r[0], "file": r[1], "line": r[2], "rtype": r[3], "via_text": r[4][:60]})

        # 2) raw text occurrences in other files' symbols (docstrings, qualified uses)
        for r in db.conn.execute(
            """SELECT s.name, s.kind, s.qualified_name, s.start_line, f.path
               FROM symbols s JOIN files f ON f.id = s.file_id
               WHERE s.name != ? AND s.qualified_name LIKE ?
               ORDER BY f.path, s.start_line LIMIT ?""",
            (name, f"%.{name}", limit),
        ):
            refs.append({"symbol": r[0], "file": r[4], "line": r[3], "rtype": "uses", "via_text": r[2][:60]})

    # 3) import statements that actually bind the symbol's name (e.g.
    #    `from app.agents.orchestrator import orchestrator` when renaming
    #    Orchestrator, or `from app.services.llm import deepseek_llm` when
    #    renaming the deepseek_llm variable). Only the imported name counts:
    #    a shared *module path* (resource_agents) is not a symbol reference.
    #    Runs even when the symbol is unindexed (module-level instances),
    #    because imports still tell us who is affected.
    import_like = f"%{name.lower()}%"
    for r in db.conn.execute(
        """SELECT text, line, f.path
           FROM file_imports fi JOIN files f ON f.id = fi.file_id
           WHERE LOWER(text) LIKE ?
           ORDER BY f.path, fi.line LIMIT ?""",
        (import_like, limit),
    ):
        imported = _imported_names(r[0])
        if not any(name.lower() in n.lower() for n in imported):
            continue
        refs.append({"symbol": name, "file": r[2], "line": r[1], "rtype": "import", "via_text": r[0][:60]})
        if len(refs) >= limit:
            break

    # The Java/TS parsers emit both a bare and a dotted call edge for
    # `Cls.method()`; both may resolve to the same target, so one reference
    # site can appear twice (once per via_text). Dedupe by site.
    seen_refs: set[tuple] = set()
    deduped: list[dict] = []
    for r in refs:
        k = (r.get("file"), r.get("line"), r.get("symbol"))
        if k in seen_refs:
            continue
        seen_refs.add(k)
        deduped.append(r)
    refs = deduped

    risk = _risk_grade(defs, refs)
    return {
        "symbol": name,
        "definitions": [_brief(s) for s in defs],
        "references": refs[:limit],
        "definition_count": len(defs),
        "reference_count": len(refs),
        "risk": risk,
    }


def _risk_grade(defs: list[dict], refs: list[dict]) -> dict:
    """Risk hints for symbol-level change: HIGH/MEDIUM/LOW + breakdown.

    HIGH = public API (class/interface/struct) with many callers or tests.
    MEDIUM = internal with test coverage. LOW = leaf/internal usage only.
    """
    public_kinds = {"class", "interface", "struct", "enum", "impl", "type", "delegate"}
    has_public_def = any(d.get("kind") in public_kinds for d in defs)
    tests = sum(1 for r in refs if "test" in r.get("file", "").lower() or "spec" in r.get("file", "").lower())
    callers = sum(1 for r in refs if r.get("rtype") in ("calls", "uses"))
    n = len(refs)

    if has_public_def and (callers or tests):
        grade = "HIGH"
    elif has_public_def or (tests and n):
        grade = "MEDIUM"
    else:
        grade = "LOW"

    return {
        "grade": grade,
        "public_definitions": sum(1 for d in defs if d.get("kind") in public_kinds),
        "reference_sites": n,
        "test_sites": tests,
        "hint": (
            f"{grade} risk: {n} reference sites, {tests} in tests"
            + (", public API" if has_public_def else ", internal")
        ),
    }


def _brief(sym: dict) -> dict:
    out = {
        "symbol": sym.get("name"),
        "qualified_name": sym.get("qualified_name"),
        "kind": sym.get("kind"),
        "file": sym.get("path"),
        "lines": f"{sym.get('start_line')}-{sym.get('end_line')}" if sym.get("end_line") else f"{sym.get('start_line')}",
        "signature": (sym.get("signature") or "")[:120],
    }
    np = name_path(sym.get("qualified_name"))
    if np and np != sym.get("name"):
        out["name_path"] = np
    return out


def type_hierarchy(db: DB, name: str) -> dict:
    """Class hierarchy: ancestors (bases) and descendants (subclasses), BFS."""
    roots = find_symbols(db, name)
    if not roots:
        return {"symbol": name, "found": False}

    def ancestors_of(sid: int) -> list[dict]:
        out: list[dict] = []
        frontier = {sid}
        seen = set(frontier)
        for _ in range(6):
            nxt: set[int] = set()
            for cid in frontier:
                for r in db.conn.execute(
                    """SELECT s.id FROM relations r JOIN symbols s ON s.id = r.target_id
                       WHERE r.rtype = 'inherits' AND r.source_id = ? AND r.target_id IS NOT NULL""",
                    (cid,),
                ):
                    if r[0] not in seen:
                        seen.add(r[0])
                        nxt.add(r[0])
            if not nxt:
                break
            out.extend(symbol_by_id(db, i) for i in nxt)
            frontier = nxt
        return out

    def descendants_of(sid: int) -> list[dict]:
        out: list[dict] = []
        frontier = {sid}
        # seed seen with the root itself so a cyclic hierarchy (A extends B,
        # B extends A) cannot leak the root back into its own descendants.
        seen = {sid}
        for _ in range(6):
            nxt: set[int] = set()
            for cid in frontier:
                for r in db.conn.execute(
                    """SELECT DISTINCT r.source_id FROM relations r
                       WHERE r.rtype = 'inherits' AND r.target_id = ?""",
                    (cid,),
                ):
                    if r[0] not in seen:
                        seen.add(r[0])
                        nxt.add(r[0])
            if not nxt:
                break
            out.extend(symbol_by_id(db, i) for i in nxt)
            frontier = nxt
        return out

    return {
        "symbol": name,
        "found": True,
        "matches": len(roots),
        "ancestors": [_brief(s) for s in ancestors_of(roots[0]["id"])][:50],
        "descendants": [_brief(s) for s in descendants_of(roots[0]["id"])][:50],
    }