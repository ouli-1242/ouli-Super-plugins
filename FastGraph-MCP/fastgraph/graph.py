"""Graph queries: symbol lookup, callers/callees, BFS trace, impact scoring."""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path

from fastgraph.db import DB


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


def find_symbols(db: DB, name: str, limit: int = 20) -> list[dict]:
    """Locate symbols by plain name or dotted qualified name.

    Supports ``Class.method`` (exact qualified_name match) and, for 3+ segments,
    ``module.Class.method`` — the leading segment is resolved to its
    module/class symbol's file, then the rest is matched against qualified
    names inside that file (A7).
    """
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


def lookup_exact(db: DB, name: str) -> list[int]:
    ids: list[int] = []
    for r in db.conn.execute(
        "SELECT id FROM symbols WHERE name = ? OR qualified_name = ?", (name, name)
    ).fetchall():
        ids.append(r[0])
    return ids


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
        "SELECT source_id FROM relations WHERE target_id = ? AND rtype = 'calls'", (sid,)
    ).fetchall()
    return [r[0] for r in rows]


def caller_ids(db: DB, sid: int) -> list[int]:
    """Keep the old helper name for compatibility."""
    return callers(db, sid)


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
    """Who calls `name` (optionally transitively, BFS up to depth)."""
    roots = find_symbols(db, name)
    if not roots:
        return []
    root_ids, member_ids = _expand_container_roots(db, roots)
    seen: set[int] = set()
    frontier = list(root_ids)
    level = 0
    while frontier and level < depth:
        nxt: list[int] = []
        for sid in frontier:
            for c in _callers_with_class(db, sid):
                if c not in seen:
                    seen.add(c)
                    nxt.append(c)
        frontier = nxt
        level += 1
    out = [symbol_by_id(db, s) for s in seen if s not in root_ids and s not in member_ids]
    return [o for o in out if o][:limit]


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
    seen: set[int] = set()
    frontier = list(root_ids)
    level = 0
    while frontier and level < depth:
        nxt: list[int] = []
        for sid in frontier:
            for c in callee_ids(db, sid):
                if c not in seen and c not in root_ids:
                    seen.add(c)
                    nxt.append(c)
        frontier = nxt
        level += 1
    out = [symbol_by_id(db, s) for s in seen if s not in member_ids]
    return [o for o in out if o][:limit]


def _callers_with_class(db: DB, sid: int) -> list[int]:
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
      (``Cls.method``) and the container's constructor edge (``Cls``) count.
      Never a ``Cls.%`` prefix match: that would report every caller of
      sibling members (other methods, auto-generated getters/setters) as a
      caller of this member.

    Bare module-level functions never text-fold: mere references such as
    FastAPI ``Depends(fn)`` must not masquerade as callers.
    """
    out = list(callers(db, sid))
    info = symbol_by_id(db, sid)
    if not info:
        return out
    qname = info.get("qualified_name") or ""
    kind = info.get("kind") or ""
    if kind in ("class", "interface", "struct", "impl", "enum"):
        candidates = {qname, info.get("name") or ""}
        # longest first: dotted qualified names outmatch bare names
        for cand in sorted((c for c in candidates if c), key=len, reverse=True):
            for r in db.conn.execute(
                "SELECT DISTINCT source_id FROM relations WHERE target = ? OR target LIKE ?",
                (cand, cand + ".%"),
            ):
                if r[0] not in out:
                    out.append(r[0])
    elif "." in qname:
        for cand in (qname, qname.rsplit(".", 1)[0]):
            for r in db.conn.execute(
                "SELECT DISTINCT source_id FROM relations WHERE target = ?",
                (cand,),
            ):
                if r[0] not in out:
                    out.append(r[0])
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
            for c in _callers_with_class(db, sid):
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
            for c in _callers_with_class(db, sid):
                if c in seen or c in root_ids or c in member_ids:
                    continue
                seen.add(c)
                info = symbol_by_id(db, c)
                if info:
                    key = "HIGH" if depth == 0 else "MEDIUM"
                    buckets[key].append(_impact_brief(info))
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
    return {
        "name": info["name"],
        "qualified_name": info["qualified_name"],
        "kind": info["kind"],
        "file": info["path"],
        "lines": f"{info['start_line']}-{info['end_line']}",
        "signature": (info["signature"] or "")[:120],
    }


_IMP_RE = re.compile(r"(?:from\s+|import\s*\{[^}]+\}\s*from\s*|import\s+|require\(|using\s+)(['\"]?)([\w./@~-]+)", re.IGNORECASE)


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


def file_symbols(db: DB, path: str, limit: int = 200) -> list[dict]:
    """All indexed symbols declared in one file, in source order."""
    resolved = resolve_file(db, path)
    if resolved is None:
        return []
    rows = db.conn.execute(
        """SELECT s.id, s.name, s.kind, s.qualified_name, s.signature,
                  s.start_line, s.end_line, f.path
           FROM symbols s JOIN files f ON f.id = s.file_id
           WHERE f.path = ? ORDER BY s.start_line, s.start_col LIMIT ?""",
        (resolved, limit),
    ).fetchall()
    return [
        {"id": r[0], "symbol": r[1], "kind": r[2], "qualified_name": r[3],
         "signature": (r[4] or "")[:120], "lines": f"{r[5]}-{r[6]}", "file": r[7]}
        for r in rows
    ]


_alias_cache: dict[tuple[Path, str], dict[str, str]] = {}


def _alias_prefixes(db: DB, import_file: str | None = None) -> dict[str, str]:
    """Import alias prefix → directory (relative to the config's own dir).

    Config is looked up from the importing file's directory upward to the
    project root, so sub-projects (e.g. a uni-app miniapp folder) resolve
    their own aliases (`@` → miniapp root when pages.json lives there).
    Sources (deeper dirs override): tsconfig/jsconfig compilerOptions paths,
    vite resolve.alias, and the uni-app convention. Cached per (root, import
    file); never guesses when no config exists.
    """
    root = db.root
    key = (root, import_file or "")
    if key in _alias_cache:
        return _alias_cache[key]
    m: dict[str, str] = {}
    dirs: list[Path] = []
    if import_file:
        cur = (root / import_file).parent
        while True:
            dirs.append(cur)
            if cur == root:
                break
            parent = cur.parent
            if parent == cur:
                break
            cur = parent
        dirs.reverse()  # root first, deepest dir overrides on conflict
    else:
        dirs = [root]
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
    _alias_cache[key] = m
    return m


def import_targets(db: DB, import_text: str, import_file: str) -> list[str]:
    """Guess which indexed files an import statement refers to."""
    m = _IMP_RE.search(import_text)
    if not m:
        return []
    mod = m.group(2)
    # configured import aliases (`@/x`, tsconfig paths, vite alias): substitute
    # the prefix before the stem matching below
    for alias, tgt in sorted(_alias_prefixes(db, import_file).items(), key=lambda kv: -len(kv[0])):
        if mod == alias or mod.startswith(alias + "/"):
            rest = mod[len(alias):].lstrip("/")
            mod = f"{tgt}/{rest}" if tgt else rest
            break
    if mod.startswith((".", "/")):
        rel = mod[1:] if mod.startswith(".") else mod
        mod = rel.replace("/", ".")
    else:
        mod = mod.replace("/", ".")
    mod = mod.strip(".")
    # CommonJS require paths often carry a file extension ("./x/index.js")
    # while the index stores extension-less stems; normalize before matching.
    for _ext in (".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx"):
        if mod.endswith(_ext):
            mod = mod[: -len(_ext)]
            break
    dir_part = "/".join(import_file.split("/")[:-1])
    rel_root = f"{dir_part}/" if dir_part else ""
    candidates: list[str] = []
    # Match case-insensitively: Java/C# fully-qualified names are mixed-case
    # (com.travel...RateLimiter), and the file stems below are lowercased, so a
    # case-sensitive compare would never match them (A8).
    mod = mod.lower()
    for (p,) in db.conn.execute("SELECT path FROM files"):
        stem = p.rsplit(".", 1)[0].replace("/", ".").lower()
        if stem == mod or stem.endswith("." + mod):
            candidates.append(p)
        elif mod.startswith(".") and p.lower() == rel_root + mod[1:] + ".__init__":
            candidates.append(p)
    # `from pkg import a, b, c` (multi-symbol package import): the regex only
    # captured `pkg`, so also resolve each imported name against pkg's dir.
    _multi = re.match(r"\s*from\s+[\w./@~-]+\s+import\s+(.+)", import_text, re.IGNORECASE)
    if not candidates and _multi:
        names_part = _multi.group(1).split(" as ")[0]
        for name in (n.strip().rstrip(",") for n in names_part.split(",")):
            if not name or "." in name or name in ("*", "(", ")"):
                continue
            target = f"{mod}.{name.lower()}"
            for (p,) in db.conn.execute("SELECT path FROM files"):
                stem = p.rsplit(".", 1)[0].replace("/", ".").lower()
                if stem == target or stem.endswith("." + target):
                    if p not in candidates:
                        candidates.append(p)
    return candidates[:5]


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
    return {
        "symbol": sym.get("name"),
        "qualified_name": sym.get("qualified_name"),
        "kind": sym.get("kind"),
        "file": sym.get("path"),
        "lines": f"{sym.get('start_line')}-{sym.get('end_line')}" if sym.get("end_line") else f"{sym.get('start_line')}",
        "signature": (sym.get("signature") or "")[:120],
    }


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