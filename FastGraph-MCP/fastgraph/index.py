"""Incremental indexer: walk -> mtime/size diff -> re-parse changed only."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from fastgraph.config import (
    DEFAULT_EXCLUDES,
    IGNORE_FILENAME,
    MAX_FILE_SIZE,
    IgnoreMatcher,
    parse_ignore,
    user_home,
)
from fastgraph.db import DB
from fastgraph import graph
from fastgraph.parsers.base import SymbolInfo
from fastgraph.parsers.registry import get_adapter, language_for_path

MAX_PARSE_WORKERS = min(8, (os.cpu_count() or 2))

_SCRIPT_BLANK = re.compile(r"<script\b[^>]*>[\s\S]*?</script\s*>", re.IGNORECASE)

_LINE_COMMENT_MARK = {
    "python": "#",
    "typescript": "//", "tsx": "//", "javascript": "//",
    "java": "//", "cpp": "//",
    "go": "//", "rust": "//",
}


def _extract_content_lines(lang: str, text: str) -> list[tuple[int, str, str]]:
    """Collect (1-based line, kind, text) for content search.

    kinds: comment (line + block), string (incl. triple-quoted spans),
    template (vue/svelte non-script lines). Text capped at 200 chars. This is
    deliberately lossy — identifiers are already covered by the symbol index.
    """
    out: list[tuple[int, str, str]] = []
    lines = text.split("\n")

    def add(ln: int, kind: str, content: str):
        c = content.strip().strip("\"'")
        if c and len(c) <= 200:
            out.append((ln, kind, c))

    # block comments: emit every span line
    for m in re.finditer(r"/\*[\s\S]*?\*/", text):
        start = text.count("\n", 0, m.start())
        for i, sub in enumerate(m.group(0).split("\n")):
            add(start + i + 1, "comment", sub)
    # triple-quoted python strings
    for m in re.finditer(r'"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\'', text):
        start = text.count("\n", 0, m.start())
        s = next((g for g in m.groups() if g is not None), "")
        for i, sub in enumerate(s.split("\n")):
            add(start + i + 1, "string", sub)
    # line comments + single-line string literals
    mark = _LINE_COMMENT_MARK.get(lang)
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if mark and stripped.startswith(mark):
            add(i, "comment", line[line.find(mark):])
        if lang in ("vue", "svelte") and stripped.startswith("<!--"):
            add(i, "comment", line)
    for m in re.finditer(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', text):
        ln = text.count("\n", 0, m.start()) + 1
        add(ln, "string", m.group(0))
    # vue/svelte/wxml: template lines (script blocks blanked for vue/svelte;
    # wxml has no script block, so the whole file is template)
    if lang in ("vue", "svelte", "wxml"):
        t = _SCRIPT_BLANK.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        for i, line in enumerate(t.split("\n"), 1):
            s = line.strip()
            if s and not s.startswith("<") and not s.startswith("</"):
                add(i, "template", s)
    return out

# Bump when the index format or parser output changes meaningfully (e.g.
# signatures now embed base-class info): refresh() detects a mismatch and
# rebuilds the index once, so upgraded servers don't serve stale shapes.
# "3": member-candidate plausibility check (same-file/imported owner) now
# rejects misresolved collection calls like `rows.add()`; v2 indexes have
# those edges already resolved, and _resolve_all only re-evaluates
# unresolved edges, so a rebuild is required to invalidate them.
# "4": new tables template_refs / line_content (schema change) + vue template
# refs and content lines are only collected at parse time.
# "5": wxml page templates feed template_refs via sibling .js; TS parser folds
# inner local variables' calls into the enclosing symbol (no more `fn.res`
# noise in callers), and drops non-identifier destructuring names.
# "6": symbols.decorated column + decorated/annotation-aware dead-code
# detection (FastAPI @app.get, Spring @GetMapping, ...); 'references' rtype
# resolved so Depends(get_db) counts as usage.
# "7": every file carries a `module` symbol (import-time calls attributed to
# it), so module-level registration/wiring appears in the call graph;
# callback arguments (`ex.map(self.fn, ...)`) count as usage.
# "8": `module` symbols are excluded from call/inherit target resolution (a
# module is imported, not called), so `parse(...)` no longer resolves to
# `parse.js`. Previously resolved wrong edges are not re-evaluated by the
# resolver, hence the bump.
# "9": Go import rows are per imported path instead of per `import (...)` block,
# so each path is classified internal/external on its own.
# "10": call-target resolution learned `::` separators, import-file evidence and
# class-internal ownership, and the too-permissive same-directory rule was
# dropped. Previously resolved WRONG edges (a `req.save()` linked to a local
# `User.save` in the same directory) are not re-evaluated by the resolver -- it
# only touches target_id IS NULL -- so a rebuild is required to clear them.
INDEX_VERSION = "10"

# Guard against accidentally walking a huge, unindexed directory (e.g. an
# unactivated default root like a user's home folder): stop once this many
# entries were checked. refresh() reports `skipped` so tools can hint at
# activate_project().
MAX_SCAN_ENTRIES = 200_000


@dataclass
class IndexStats:
    scanned: int = 0
    parsed: int = 0
    deleted: int = 0
    errors: int = 0
    duration_ms: float = 0.0
    total_files: int = 0
    total_symbols: int = 0
    skipped: bool = False
    changed: list[str] = field(default_factory=list)
    large_files: list[str] = field(default_factory=list)
    """Indexable files skipped for exceeding MAX_FILE_SIZE.

    Reported by project_overview so the index's blind spots are visible: a file
    that is too large is not in `parse_errors` either, so without this the
    caller cannot tell "no symbols here" from "never looked"."""


    """project-relative paths re-parsed by this refresh (the files that changed
    since the previous one); used by changed_context on non-git projects."""


class Indexer:
    def __init__(self, root: Path, db: DB, excludes: set[str] | None = None):
        self.root = root.resolve()
        self.db = db
        self.excludes = excludes or DEFAULT_EXCLUDES
        self._walk_skipped = False
        self._large_files: list[str] = []
        self._ignore_patterns: list[str] = []
        # precompiled form of _ignore_patterns: _walk() tests every scanned
        # entry against it, so rebuilding per entry (fnmatch normalizes case on
        # each call) made the ignore rules ~90% of a no-op refresh
        self._ignore = IgnoreMatcher([])
        # Serialize refresh() across threads: every tool call runs _ensure_fresh,
        # and concurrent writes to the same sqlite connection crash with
        # InterfaceError / UNIQUE constraint races (see STRESS_TEST_REPORT P1-1).
        self._refresh_lock = threading.RLock()

    def ignore_patterns(self) -> list[str]:
        """The `.fastgraphignore` rules loaded by the last ``refresh()``.

        Exposed so the reading tools honor exactly the same visibility rules as
        the index: they may read files the index does not carry (docs, configs),
        but never one the project marked as ignored (secrets, vendored trees).
        """
        return self._ignore_patterns

    def ignore_matcher(self) -> IgnoreMatcher:
        """The precompiled form of :meth:`ignore_patterns`."""
        return self._ignore

    def refresh(self) -> IndexStats:
        with self._refresh_lock:
            return self._refresh()

    def _refresh(self) -> IndexStats:
        start = time.perf_counter()
        stats = IndexStats()
        # reset per call: a trip in an earlier refresh (huge/unactivated root)
        # must not permanently suppress stale-file deletion afterwards
        self._walk_skipped = False
        self._large_files = []

        # Desktop/Cursor may launch the stdio server from a fixed cwd (e.g.
        # System32); auto-detection then falls back to the user home. The home
        # dir is never the intended project — bail fast and let tools hint at
        # activate_project() instead of scanning it for minutes.
        if self.root == user_home():
            stats.skipped = True
            self._walk_skipped = True
            return stats

        # local-only ignore config: .fastgraph/.fastgraphignore (template
        # auto-created on first index). Matched entries are skipped by the
        # walk (and, being absent from `seen`, removed on the next refresh if
        # they were indexed before the rule was added).
        ignore_file = self.root / ".fastgraph" / IGNORE_FILENAME
        self._ignore_patterns = (
            parse_ignore(ignore_file.read_text(encoding="utf-8", errors="replace"))
            if ignore_file.is_file()
            else []
        )
        self._ignore = IgnoreMatcher(self._ignore_patterns)

        cached = self.db.file_map()

        # Index-format/parser-output upgrade: rebuild once, then carry on with
        # the normal incremental scan (cached is now empty, so every file gets
        # re-parsed in the same pass).
        if self.db.get_meta("index_version") != INDEX_VERSION:
            for rel in cached:
                self.db.delete_file(rel)
            # wipe FTS wholesale as well: rows leaked by an older build survive
            # per-file deletes, and a stale rowid would collide with the ids
            # this rebuild assigns (FTS5 rejects duplicate rowids)
            self.db.clear_fts()
            self.db.commit()
            cached = {}
            self.db.set_meta("index_version", INDEX_VERSION)
            self.db.commit()

        to_parse: list[tuple[str, Path]] = []
        seen: set[str] = set()

        for p, st in self._walk():
            rel = p.relative_to(self.root).as_posix()
            seen.add(rel)
            if st.st_size > MAX_FILE_SIZE:
                self._large_files.append(rel)
                continue
            stats.scanned += 1
            # compare size as well as mtime: a same-second rewrite or an
            # mtime-preserving replacement (some VCS/editor operations) still
            # changes the size and must be re-parsed
            if cached.get(rel) == (st.st_mtime, st.st_size):
                continue  # untouched: zero IO
            to_parse.append((rel, p))

        stats.skipped = self._walk_skipped
        if not stats.skipped:
            for rel in cached:
                if rel not in seen:
                    self.db.delete_file(rel)
                    stats.deleted += 1

        if to_parse:
            stats.changed = [rel for rel, _ in to_parse]
            with ThreadPoolExecutor(max_workers=MAX_PARSE_WORKERS) as ex:
                parsed = ex.map(self._parse_only, to_parse)
            try:
                for rel, st, hash_, result, source, error in parsed:
                    if result is None:
                        stats.errors += 1
                        self.db.set_parse_error(rel, error or "parse failed")
                        continue
                    self.db.clear_parse_error(rel)
                    self._store_file(rel, st, hash_, result, source)
                    stats.parsed += 1
            except Exception:
                # An exception here would leave the write transaction open on
                # this connection, which keeps the SQLite write lock and makes
                # every later call on this index fail with "database is
                # locked" until the process exits. Roll back so the index stays
                # at its last consistent state, then report the failure.
                self.db.conn.rollback()
                raise

        if stats.parsed or stats.deleted:
            self.db.commit()

        # Re-run resolution only when the symbol set can actually have changed
        # (a file was added/changed/removed). Unresolvable edges — external
        # calls like `print()` — keep target_id NULL forever, so gating on
        # "any unresolved edge exists" re-ran the whole resolver on every call,
        # which was the dominant cost of a no-op refresh on large repos.
        if (stats.parsed or stats.deleted) and self.db.conn.execute(
            "SELECT 1 FROM relations WHERE target_id IS NULL "
            "AND rtype IN ('calls', 'references', 'inherits') LIMIT 1"
        ).fetchone():
            _resolve_all(self.db)
        self.db.commit()

        stats.duration_ms = (time.perf_counter() - start) * 1000
        stats.total_files = len(seen)
        stats.total_symbols = self.db.count_symbols()
        stats.skipped = self._walk_skipped
        stats.large_files = self._large_files[:20]
        return stats

    def force_index(self) -> IndexStats:
        """Rebuild from scratch (used once on first run)."""
        for row in self.db.conn.execute("SELECT path FROM files"):
            self.db.delete_file(row[0])
        self.db.commit()
        return self.refresh()

    # ---------------- internals ----------------

    def _walk(self) -> list[tuple[Path, os.stat_result]]:
        """Walk the tree and return (path, stat) for every indexable file.

        The stat comes from the ``DirEntry`` (already fetched by ``is_dir``/
        ``is_file``), so the caller does not stat each file a second time —
        halving the syscalls of the per-call incremental scan.
        """
        out: list[tuple[Path, os.stat_result]] = []
        stack = [self.root]
        checked = 0
        while stack:
            d = stack.pop()
            try:
                entries = os.scandir(d)
            except OSError:
                continue
            with entries as it:
                for e in it:
                    checked += 1
                    if checked > MAX_SCAN_ENTRIES:
                        self._walk_skipped = True
                        return out
                    name = e.name
                    if name in self.excludes or name.startswith("."):
                        continue
                    rel = os.path.relpath(e.path, self.root).replace("\\", "/")
                    if self._ignore.matches(rel, name):
                        continue
                    try:
                        is_dir = e.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir:
                        if name != ".git":
                            stack.append(Path(e.path))
                        continue
                    try:
                        if not e.is_file(follow_symlinks=False):
                            continue
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if language_for_path(name) is not None:
                        out.append((Path(e.path), st))
        return out

    def _parse_only(self, item: tuple) -> tuple:
        """Thread-safe: read + parse, no DB access.

        Returns (rel, stat, hash, ParseResult|None, source, error). ``error``
        carries the failure detail so parse_errors is actionable instead of a
        generic "parse failed".
        """
        rel, path = item
        adapter = get_adapter(language_for_path(rel))
        if adapter is None:
            return rel, None, "", None, "", "no adapter registered for this file type"
        try:
            st = path.stat()
            source = path.read_bytes()
        except OSError as e:
            return rel, None, "", None, "", f"read failed: {e}"
        hash_ = hashlib.sha256(source).hexdigest()[:24]
        try:
            result = adapter.parse(source)
        except Exception as e:
            return rel, st, hash_, None, source, f"{type(e).__name__}: {e}"[:300]
        return rel, st, hash_, result, source, None

    def _store_file(self, rel: str, st, hash_: str, result, source: bytes) -> None:
        """Single-threaded DB write for one parsed file."""
        lang = result.language
        module_doc = getattr(result, "module_doc", "") or ""
        # Every file gets a `module` symbol. It makes top-of-file docs
        # searchable (was silently dropped, so Chinese module docs were
        # invisible) and, crucially, gives the file's import-time calls a
        # source node so registration/wiring code is not absent from the
        # call graph (see ParseResult.module_calls).
        stem = Path(rel).stem
        result.symbols.insert(0, SymbolInfo(
            name=stem, kind="module", qualified_name=stem,
            signature="", doc=module_doc,
            start_line=1, end_line=1, start_col=0, end_col=0,
            calls=list(getattr(result, "module_calls", None) or []),
        ))
        symbols = [
            {
                "name": s.name,
                "kind": s.kind,
                "qualified_name": s.qualified_name,
                "signature": s.signature,
                "doc": s.doc,
                "start_line": s.start_line,
                "end_line": s.end_line,
                "start_col": s.start_col,
                "end_col": s.end_col,
                "decorated": s.decorated,
            }
            for s in result.symbols
        ]
        fid = self.db.upsert_file(rel, lang, hash_, st.st_mtime, st.st_size)
        self.db.replace_file_symbols(fid, symbols)
        self.db.replace_file_imports(
            fid,
            [{"text": i.text, "kind": i.kind, "line": i.line} for i in result.imports],
        )
        self.db.replace_file_template_refs(
            fid, getattr(result, "template_refs", None) or []
        )
        self.db.replace_file_line_content(
            fid, _extract_content_lines(lang, source.decode("utf-8", "replace"))
        )
        self.db.register_fts(fid, rel, symbols)

        rows: list[tuple] = []
        sym_ids = [
            r[0]
            for r in self.db.conn.execute(
                "SELECT id FROM symbols WHERE file_id=? ORDER BY id", (fid,)
            )
        ]
        if len(sym_ids) != len(result.symbols):
            name_ids = self.db.symbol_name_to_id(fid)
            sym_ids = [name_ids.get(s.name) for s in result.symbols]
        for s, src in zip(result.symbols, sym_ids):
            if src is None:
                continue
            for c in s.calls:
                rows.append((src, c.target, c.rtype, c.line))
            for b in s.bases:
                rows.append((src, b.target, b.rtype, b.line))
        self.db.replace_file_relations(fid, rows)

def _resolve_all(db: DB) -> None:
    """Resolve relations whose target_id is NULL against known symbols.

    Strategy:
      - exact unique name -> link
      - multiple candidates -> pick the one whose class is imported in the
        caller's file (e.g. `from auth.service import AuthService`)
      - dotted target (auth.login) -> match qualified_name suffix
    """
    pending = db.conn.execute(
        "SELECT id, source_id, target, rtype FROM relations "
        "WHERE target_id IS NULL AND rtype IN ('calls', 'references', 'inherits')"
    ).fetchall()
    if not pending:
        return
    # caller-file imports, grouped
    import_text_by_file: dict[int, str] = {}
    for fid, text in db.conn.execute("SELECT file_id, text FROM file_imports"):
        import_text_by_file[fid] = import_text_by_file.get(fid, "") + " " + text.lower()

    sym_files = {
        r[0]: (r[1], r[2])
        for r in db.conn.execute("SELECT id, name, qualified_name FROM symbols")
    }
    caller_file = {
        sid: fid
        for fid, sid in db.conn.execute("SELECT file_id, id FROM symbols")
    }
    file_paths: dict[int, str] = {}

    def path_of_file(fid: int | None) -> str:
        if fid is None:
            return ""
        p = file_paths.get(fid)
        if p is None:
            p = db.file_path(fid) or ""
            file_paths[fid] = p
        return p

    imported_by: dict[int, set[str]] = {}

    def files_imported_by(fid: int | None) -> set[str]:
        """The indexed files a caller's imports actually resolve to.

        Stronger evidence than "the owner's class name appears somewhere in the
        caller's import text": two classes may share a name (every module has a
        `Svc`), but only one of them lives in the file the caller imports.
        """
        if fid is None:
            return set()
        got = imported_by.get(fid)
        if got is None:
            got = set()
            src = path_of_file(fid)
            if src:
                for (text,) in db.conn.execute(
                    "SELECT text FROM file_imports WHERE file_id = ?", (fid,)
                ):
                    got.update(graph.import_targets(db, text, src))
            imported_by[fid] = got
        return got

    for rel_id, source_id, target, rtype in pending:
        if rtype in ("calls", "references"):
            candidates = _candidates_for_target(db, sym_files, target)
            picked: list[int] = []
            if len(candidates) == 1:
                # `rows.add(...)`/`noteList.add(...)` produce bare `add` (and
                # dotted `rows.add`) edges; when a project has exactly one
                # symbol named `add`, the unique-name resolution links every
                # collection call to it, polluting find_callers with dozens
                # of unrelated callers. Member targets must carry local
                # evidence -- same file, the owner named at the call site, an
                # import, or an intra-class call -- to be linked.
                if _member_target_plausible(
                    candidates[0], source_id, target,
                    import_text_by_file, caller_file, sym_files,
                ):
                    db.apply_resolution(rel_id, candidates[0])
            elif len(candidates) > 1:
                src_fid = caller_file.get(source_id)
                imports = import_text_by_file.get(src_fid or -1, "")
                picked: list[int] = []
                if imports:
                    picked = [
                        cid for cid in candidates
                        if _class_hint(sym_files.get(cid, ("", ""))[1]) in imports
                    ]
                if len(picked) != 1 and src_fid is not None:
                    # the caller's resolved imports decide: keep only candidates
                    # that live in a file it imports. `Svc().run()` where two
                    # modules both define a `Svc` class used to pick nothing at
                    # all -- both class names occur in the import text.
                    files = files_imported_by(src_fid)
                    if files:
                        by_import = [
                            cid for cid in candidates
                            if path_of_file(caller_file.get(cid)) in files
                        ]
                        if len(by_import) == 1:
                            picked = by_import
                if len(picked) != 1:
                    # `self.helper()` / class-internal call: the caller's own
                    # class is the natural owner of a bare member name.
                    src_owner = _owner_of(sym_files.get(source_id, ("", ""))[1])
                    if src_owner:
                        # never the caller itself: `super().login()` inside
                        # `OAuthService.login` targets the *base* method, and a
                        # self-link here would also show up as a 1-file cycle.
                        own = [
                            cid for cid in candidates
                            if cid != source_id
                            and _owner_of(sym_files.get(cid, ("", ""))[1]) == src_owner
                        ]
                        if len(own) == 1:
                            picked = own
                if len(picked) != 1 and target.startswith(("self.", "this.")):
                    # `self.tutor_agent.run`: the attribute name maps 1:1 onto
                    # the snake_cased owner class (TutorAgent -> tutor_agent),
                    # which resolves the per-instance dispatch without needing
                    # source assignment tracking. Java emits `this.x.y` edges.
                    parts = target.split(".")
                    # `self._method(...)`: bare member name, unique -> link it
                    if len(parts) == 2:
                        solo = db.resolve_single_name(parts[1])
                        if len(solo) == 1:
                            picked = solo
                    elif len(parts) >= 3:
                        attr = _snake(parts[1])
                        attr_picked = [
                            cid for cid in candidates
                            if _matches_attr(sym_files.get(cid, ("", ""))[1], attr)
                        ]
                        if len(attr_picked) == 1:
                            picked = attr_picked
                if len(picked) != 1 and not _has_sep(target):
                    # bare-name target: prefer the exact qualified_name match —
                    # `new BizException()` should resolve to the class, not the
                    # same-named constructors (A9 impact_analysis blind spot).
                    exact = [
                        cid for cid in candidates
                        if sym_files.get(cid, ("", ""))[1] == target
                    ]
                    if len(exact) == 1:
                        picked = exact
                if len(picked) == 1:
                    db.apply_resolution(rel_id, picked[0])
            if not picked and not _has_sep(target):
                # `import { logout as apiLogout } from '../api/admin'` +
                # `apiLogout()`: the bare edge names the *local* binding, so it
                # resolves to the exported symbol `logout` via the import map.
                alias = _resolve_via_alias(
                    db, source_id, target, import_text_by_file, sym_files, caller_file
                )
                if alias is not None:
                    db.apply_resolution(rel_id, alias)
        elif rtype == "inherits":
            # bases are class names: unique-name match, else skip (heuristic noise)
            last = _target_last(target)
            candidates = [
                cid for cid in db.resolve_single_name(last)
                if _target_last(sym_files.get(cid, ("", ""))[1]) == last
            ]
            if len(candidates) == 1:
                db.apply_resolution(rel_id, candidates[0])


def _has_sep(target: str) -> bool:
    """True when the call text is qualified (`a.b`, `x::y`)."""
    return "." in target or "::" in target


_TARGET_SEP_RE = re.compile(r"[.:]+")


def _target_parts(target: str) -> list[str]:
    parts = [p for p in _TARGET_SEP_RE.split(target) if p]
    return parts or [target]


def _target_last(target: str) -> str:
    """Trailing name of a call text: `clap::Command::new` -> `new`."""
    return _target_parts(target)[-1]


def _target_head(target: str) -> str:
    """Leading name of a call text: `req.save` -> `req`; `save` -> ``."""
    parts = _target_parts(target)
    return parts[0] if len(parts) > 1 else ""


def _owner_of(qname: str) -> str:
    """`Svc.run` -> `Svc`; `a::b::f` -> `a::b`; `run` -> ``."""
    for sep in ("::", "."):
        if sep in qname:
            return qname.rsplit(sep, 1)[0]
    return ""


_NORM_IDENT_RE = re.compile(r"[^0-9a-z]")


def _norm_ident(s: str) -> str:
    """Case/underscore/camel-insensitive key: `UserService` == `user_service`."""
    return _NORM_IDENT_RE.sub("", s.lower())


def _member_target_plausible(
    cid: int,
    source_id: int,
    target: str,
    import_text_by_file: dict[int, str],
    caller_file: dict[int, int],
    sym_files: dict[int, tuple],
) -> bool:
    """Should a *member* candidate be linked for this call?

    A member is any symbol whose qualified name has an owner (`Svc.run`);
    module-level functions (bare qname) are always plausible. A member needs
    local evidence, in this order:

    - the caller lives in the same file as the candidate;
    - the call text itself names the owner (`user.save()` -> owner `User`);
    - caller and candidate are members of the same class (`self.helper()`);
    - the owner name appears in the caller's imports.

    The previous "same directory is enough" rule was dropped: `req.save()`
    sitting next to an unrelated `User.save` linked the two and fed a bogus
    caller into find_callers / impact_analysis.
    """
    qname = sym_files.get(cid, ("", ""))[1]
    if not qname or not _owner_of(qname):
        return True  # module-level function/class: the name match is the evidence
    owner = _owner_of(qname)
    src_fid = caller_file.get(source_id)
    own_fid = caller_file.get(cid)
    if src_fid is not None and own_fid is not None and src_fid == own_fid:
        return True  # same-file member call (e.g. `this.add(...)` / `add(...)`)
    head = _target_head(target)
    if head and _norm_ident(head) == _norm_ident(owner):
        return True  # `user.save()` names an owner `User`
    src_owner = _owner_of(sym_files.get(source_id, ("", ""))[1])
    if src_owner and src_owner == owner:
        return True  # `self.helper()` -- the caller's own class owns the method
    if src_fid is not None:
        return owner.lower() in import_text_by_file.get(src_fid, "")
    return True


_ALIAS_NAMED_RE = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]")
_ALIAS_BARE_RE = re.compile(r"import\s+(\w+)\s+as\s+(\w+)\s+from\s*['\"]([^'\"]+)['\"]")
_ALIAS_NS_RE = re.compile(r"import\s+\*\s+as\s+(\w+)\s+from\s*['\"]([^'\"]+)['\"]")


def _resolve_via_alias(
    db: DB,
    source_id: int,
    target: str,
    import_text_by_file: dict[int, str],
    sym_files: dict[int, tuple],
    caller_file: dict[int, int],
) -> int | None:
    """Resolve a bare call target through import aliasing in the caller file.

    `import { logout as apiLogout } from '../api/admin'` + `apiLogout()` →
    the symbol `logout` in the resolved module. Also covers `import x as y`
    (Python) and `import * as ns` (dotted targets). Case-insensitive: the
    import text is lowercased when grouped.
    """
    src_fid = caller_file.get(source_id)
    if src_fid is None:
        return None
    src_path = db.file_path(src_fid)
    if not src_path:
        return None
    imp_text = import_text_by_file.get(src_fid, "")
    if not imp_text:
        return None

    def resolve_export(mod_spec: str, export: str) -> int | None:
        for cand in graph.import_targets(
            db, f"import {{ {export} }} from '{mod_spec}'", src_path
        ):
            rows = db.conn.execute(
                "SELECT id FROM symbols "
                "WHERE file_id = (SELECT id FROM files WHERE path = ?) "
                "AND LOWER(name) = LOWER(?) AND kind <> 'module'",
                (cand, export),
            ).fetchall()
            if len(rows) == 1:
                return rows[0][0]
        return None

    tgt = target.lower()
    for m in _ALIAS_NAMED_RE.finditer(imp_text):
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                orig, local = (p.strip() for p in part.split(" as ", 1))
            else:
                orig = local = part
            if local.lower() == tgt:
                hit = resolve_export(m.group(2), orig)
                if hit is not None:
                    return hit
    for m in _ALIAS_BARE_RE.finditer(imp_text):
        if m.group(2).lower() == tgt:
            hit = resolve_export(m.group(3), m.group(1))
            if hit is not None:
                return hit
    for m in _ALIAS_NS_RE.finditer(imp_text):
        ns, mod_spec = m.group(1), m.group(2)
        if tgt.startswith(ns.lower() + "."):
            export = target[len(ns) + 1:]
            hit = resolve_export(mod_spec, export)
            if hit is not None:
                return hit
    return None


def _candidates_for_target(db: DB, sym_files: dict[int, tuple], target: str) -> list[int]:
    """Symbols that could satisfy this call text.

    A qualified text (`Svc.run`, `clap::Command::new`) resolves through its last
    name segment and then prefers candidates whose qualified name matches the
    text with `.`/`::` normalized to a single separator. `::` used to fall
    through to a literal name lookup (`resolve_single_name("Command::new")`),
    which nothing can match, so Rust associated-function calls were never
    resolved.
    """
    cands_by_name = db.resolve_single_name(_target_last(target))
    if not _has_sep(target):
        return cands_by_name
    norm = target.replace("::", ".")
    exact: list[int] = []
    for cid in cands_by_name:
        q = sym_files.get(cid, ("", ""))[1].replace("::", ".")
        if q == norm or q.endswith("." + norm):
            exact.append(cid)
        elif "." in q and norm.endswith("." + q):
            # `clap::Command::new` vs a symbol qualified `Command.new`: the
            # candidate's qualified name is the shorter, more specific form.
            exact.append(cid)
    return exact or cands_by_name


def _class_hint(qname: str) -> str:
    parts = qname.split(".")
    return parts[0].lower() if parts else ""


_SNAKE_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

def _snake(name: str) -> str:
    return _SNAKE_RE.sub("_", name).lower()


def _matches_attr(qname: str, attr: str) -> bool:
    """Does the symbol's owner class plausibly back ``self.<attr>``?

    Matches when the snake_cased class name equals the attr, or when the
    attr is the trailing snake token of the class name (self.llm -> DeepSeekLLM,
    self.agent -> BaseAgent) or a known prefix alias (self.llm -> LLMCLIENT).
    """
    if not qname:
        return False
    cls = qname.split(".")[0]
    if not cls:
        return False
    snake = _snake(cls)
    if snake == attr:
        return True
    tokens = snake.split("_")
    if len(tokens) > 1 and tokens[-1] == attr:
        return True
    return False


