"""Incremental indexer: walk -> mtime/size diff -> re-parse changed only."""

from __future__ import annotations

import hashlib
import json
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
from fastgraph.parsers.base import SymbolInfo, normalize_signature
from fastgraph.parsers.registry import get_adapter, language_for_path

MAX_PARSE_WORKERS = min(8, (os.cpu_count() or 2))

# Files parsed and committed per batch on a cold index. Two reasons it is a
# batch rather than one transaction: an interrupted index used to commit nothing
# (sentry: 15 minutes into a 17,703-file cold build the `files` table still had 0
# rows, and the killed process left a 138MB WAL that recovered to nothing), and
# `Executor.map` submits its whole iterable up front, so an unchunked first run
# buffers every parse result in memory at once.
#
# 128 also bounds how far a call can overshoot `INDEX_TIME_BUDGET_S`: the budget
# is only checked at batch boundaries, so one batch is the granularity. Measured
# with a 20s budget on the 4,788-file package: batches of 512 gave passes of
# 21.4-29.4s, batches of 128 gave 20.2-21.7s. Cold throughput is unaffected by the
# choice (alternating runs on a 364-file subtree: 6.36s / 6.50s / 6.38s for
# 128 / 256 / 512).
PARSE_CHUNK = 128

# A single tool call indexes at most this many seconds' worth of files, then
# answers from what it has and reports `pending_files` so the caller knows the
# index is still being built. Measured reason: a 4,791-file Python package takes
# 131s to build and a 17,703-file repo about 40 minutes -- a call that blocks
# that long is killed by the client's timeout and the agent sees an error, not a
# slow answer. Any repo that fits under the budget (most single services: 242
# files = 2.6s, 1,979 = 20.5s) is unaffected, and the batches are already
# durable, so each later call simply continues where the last one stopped.
#
# The window is a floor, not a hard cap: work is only interruptible at batch
# boundaries, and the pass that finishes the files also gets this much time for
# call-edge resolution. Worst case measured on the 4,788-file package: file passes
# 20.2-21.7s, the completing pass 41.2s, then 7.7s -- and the split index is
# byte-identical to the same tree built in one 157s call.
# Call-edge resolution is deferred while files are still queued; see _resolve_all's
# note on why a half-indexed symbol set must not guess.
# `FASTGRAPH_INDEX_BUDGET_S` overrides it (a large value restores the old
# one-call-builds-everything behaviour; `reindex()` keeps looping over
# budget-sized passes until nothing is left).
INDEX_TIME_BUDGET_S = float(os.environ.get("FASTGRAPH_INDEX_BUDGET_S", "20"))

# Call edges resolved between time-budget checks. ~4k edges is well under a
# second even on generated-code-heavy projects, so the budget is honoured to
# within a hair without ever letting a pass make zero progress.
RESOLVE_BLOCK = 4096

# Per-file budget for the string-literal content corpus. Generated data files
# are literal-dense: sentry's 822KB `android_models.py` produced 49,121 rows --
# 58% of everything the whole 1,979-file element-plus repo produces, from 2
# symbols -- and that write volume, not parsing, is what put a 17k-file repo
# past 15 minutes of cold index at ~2MB of index per 2MB of source. Comments and
# docstrings stay uncapped on purpose: prose is what content search exists for.
MAX_STRING_CONTENT_LINES = 2000

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

    Returns ``(rows, capped)``: ``capped`` says the single-line string-literal
    pass hit :data:`MAX_STRING_CONTENT_LINES`, so the caller can report the file
    as only partially searchable instead of implying full coverage.
    """
    out: list[tuple[int, str, str]] = []
    lines = text.split("\n")

    # Line numbers come from a moving newline cursor. ``text.count("\n", 0,
    # m.start())`` per match re-scans the whole prefix, which is quadratic in
    # (file size x match count): a 1.2MB generated data file with 83k string
    # literals cost 40s of black's 55s cold index. Each pass gets its own
    # cursor, since ``finditer`` yields ascending positions within a pass.
    def newline_counter():
        """Return ``newlines_before(offset)``: newlines above a rising offset."""
        pos = 0
        seen = 0

        def newlines_before(at: int) -> int:
            nonlocal pos, seen
            if at > pos:
                seen += text.count("\n", pos, at)
                pos = at
            return seen

        return newlines_before

    def add(ln: int, kind: str, content: str):
        c = content.strip().strip("\"'")
        if c and len(c) <= 200:
            out.append((ln, kind, c))

    # block comments: emit every span line
    newlines_before = newline_counter()
    for m in re.finditer(r"/\*[\s\S]*?\*/", text):
        start = newlines_before(m.start())
        for i, sub in enumerate(m.group(0).split("\n")):
            add(start + i + 1, "comment", sub)
    # triple-quoted python strings
    newlines_before = newline_counter()
    for m in re.finditer(r'"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\'', text):
        start = newlines_before(m.start())
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
    newlines_before = newline_counter()
    kept_strings = 0
    capped = False
    for m in re.finditer(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', text):
        if kept_strings >= MAX_STRING_CONTENT_LINES:
            capped = True
            break
        ln = newlines_before(m.start()) + 1
        before = len(out)
        add(ln, "string", m.group(0))
        kept_strings += len(out) - before
    # vue/svelte/wxml: template lines (script blocks blanked for vue/svelte;
    # wxml has no script block, so the whole file is template)
    if lang in ("vue", "svelte", "wxml"):
        t = _SCRIPT_BLANK.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        for i, line in enumerate(t.split("\n"), 1):
            s = line.strip()
            if s and not s.startswith("<") and not s.startswith("</"):
                add(i, "template", s)
    return out, capped

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
# "11": import_edges table (materialized import->file resolution for
# file_deps / module_cycles / layering) and symbols.param_types (parameter
# annotation evidence for call-target resolution). Both only affect freshly
# computed data, but a rebuild is the cheap way to guarantee a consistent
# snapshot across the schema change.
# "12": TS/JS ``export ... from '...'`` re-export rows. A barrel file is made of
# nothing but these, so until now it had no inbound or outbound dependency at
# all: file_deps reported empty for it, import_dependents / layering /
# module_cycles lost every edge routed through it, and "who uses X" answered
# "nobody". Existing rows would keep the gap, so rebuild.
# "13": symbols.signature is stored one-line (see parsers.base.normalize_signature).
# Signatures ride along in every list payload, so stored CRLF + continuation
# lines were costing ~120 bytes per row: file_symbols on a 1,100-line module
# cost 11k characters for 40 symbols. Old rows keep the whitespace.
INDEX_VERSION = "13"

# Guard against accidentally walking a huge, unindexed directory (e.g. an
# unactivated default root like a user's home folder): stop once this many
# entries were checked. refresh() reports `skipped` so tools can hint at
# activate_project().
MAX_SCAN_ENTRIES = 200_000

# Build-config files that decide how imports resolve (tsconfig paths / vite
# aliases / Go module lines / uni-app sub-project roots). Their mtimes form a
# fingerprint checked each refresh; a change invalidates graph's process-wide
# resolution caches and forces an import_edges rebuild. Not indexed themselves.
_BUILD_CONFIG_FILES = {
    "tsconfig.json", "jsconfig.json", "go.mod", "pages.json",
}


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
    pending_files: int = 0
    """Files the walk found but this refresh left unindexed (time budget spent).

    The index is partial in two ways, and both must be reported: a symbol may be
    missing simply because its file was not read yet, and the call graph is not
    built until a pass finishes without truncating (resolving against a
    half-indexed symbol set would link edges a complete build refuses to guess).
    The batches are committed, so the next call continues from here.
    """
    pending_edges: int = 0
    """Call edges this pass did not reach (its time budget ran out).

    The files are all indexed -- only the graph is still being assembled, so
    `find_callers`/`impact_analysis` answers are incomplete while this is nonzero.
    """
    changed: list[str] = field(default_factory=list)
    large_files: list[str] = field(default_factory=list)
    """Indexable files skipped for exceeding MAX_FILE_SIZE.

    Reported by project_overview so the index's blind spots are visible: a file
    that is too large is not in `parse_errors` either, so without this the
    caller cannot tell "no symbols here" from "never looked"."""


class Indexer:
    def __init__(self, root: Path | str, db: DB, excludes: set[str] | None = None):
        self.root = Path(root).resolve()
        self.db = db
        self.excludes = excludes or DEFAULT_EXCLUDES
        self._walk_skipped = False
        self._large_files: list[str] = []
        self._ignore_patterns: list[str] = []
        # precompiled form of _ignore_patterns: _walk() tests every scanned
        # entry against it, so rebuilding per entry (fnmatch normalizes case on
        # each call) made the ignore rules ~90% of a no-op refresh
        self._ignore = IgnoreMatcher([])
        # path -> (mtime, size) for files whose parse failed this process. A
        # failed file has no `files` row, so without this stamp the walk offers
        # it again on every refresh and every tool call re-pays its parse cost
        # (a single unparseable 1MB fixture made every query on `bat` cost
        # ~150ms). Cleared when the file parses, so a real edit is retried.
        self._failed: dict[str, tuple[float, int]] = {}
        # symbol names declared by the files this refresh (re)parsed: the only
        # names that can turn a previously-unresolvable edge into a resolvable
        # one without the candidate set itself changing (see _resolve_all)
        self._fresh_names: set[str] = set()
        # Serialize refresh() across threads: every tool call runs _ensure_fresh,
        # and concurrent writes to the same sqlite connection crash with
        # InterfaceError / UNIQUE constraint races (see STRESS_TEST_REPORT P1-1).
        self._refresh_lock = threading.RLock()
        # True when this refresh created or removed a file (as opposed to
        # content-only edits): the *file set* drives import resolution, so any
        # addition/deletion requires a full import_edges rebuild.
        self._file_set_changed = False
        # mtime fingerprint of build-config files (tsconfig.json, go.mod, ...)
        # seen during the last walk; a change invalidates graph's resolution
        # caches (aliases/module roots are cached process-wide) and forces an
        # import_edges rebuild, since those configs decide how imports resolve.
        self._cfg_sig: tuple | None = None
        # Set once this refresh is known to end with a wholesale import_edges
        # rebuild: `_store_file` then skips its own per-file edge pass, which
        # would resolve every import a second time.
        self._edges_rebuilt_after = False

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
        self._file_set_changed = False
        # a rebuild still owed from a refresh that died between its batched
        # commits and the wholesale pass (see `edges_rebuild_pending`)
        self._edges_rebuilt_after = self.db.get_meta("edges_rebuild_pending") == "1"
        self._large_files = []
        self._fresh_names = set()

        # Desktop/Cursor may launch the stdio server from a fixed cwd (e.g.
        # System32); auto-detection then falls back to the user home. The home
        # dir — and anything covering it (C:\, C:\Users) — is never the intended
        # project: bail fast and let tools hint at activate_project() instead of
        # scanning it for minutes.
        home = user_home()
        if self.root == home or home.is_relative_to(self.root):
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
            # A parser upgrade can make a previously-failing file parse, so the
            # failure stamps must not survive the rebuild.
            self._failed.clear()
            # wipe FTS wholesale as well: rows leaked by an older build survive
            # per-file deletes, and a stale rowid would collide with the ids
            # this rebuild assigns (FTS5 rejects duplicate rowids)
            self.db.clear_fts()
            self.db.commit()
            cached = {}
            self.db.set_meta("index_version", INDEX_VERSION)
            self.db.commit()

        to_parse: list[tuple[str, str]] = []
        seen: set[str] = set()
        cfg_sig_parts: list[float] = []

        for p, st, rel in self._walk(cfg_sig_parts):
            seen.add(rel)
            if st.st_size > MAX_FILE_SIZE:
                self._large_files.append(rel)
                continue
            stats.scanned += 1
            # compare size as well as mtime: a same-second rewrite or an
            # mtime-preserving replacement (some VCS/editor operations) still
            # changes the size and must be re-parsed
            stamp = (st.st_mtime, st.st_size)
            if cached.get(rel) == stamp or self._failed.get(rel) == stamp:
                continue  # untouched: zero IO
            to_parse.append((rel, p))

        stats.skipped = self._walk_skipped
        # failed files have no `files` row, so they are not covered by the
        # deletion sweep below; drop their stamps once the file is gone
        if self._failed:
            self._failed = {r: s for r, s in self._failed.items() if r in seen}
        if not stats.skipped:
            for rel in cached:
                if rel not in seen:
                    self.db.delete_file(rel)
                    stats.deleted += 1

        # Build-config files (tsconfig.json, go.mod, ...) changed since the last
        # refresh: their content decides how imports resolve, so graph's
        # process-wide caches (aliases, Go module roots, Rust crate roots) must
        # be dropped and every import edge re-derived.
        cfg_sig = tuple(cfg_sig_parts)
        cfg_changed = cfg_sig != self._cfg_sig
        self._cfg_sig = cfg_sig
        if cfg_changed:
            graph.clear_resolution_caches()
        # A wholesale import_edges rebuild runs at the end of this refresh (deleted
        # file, new file, or a build-config change), so the per-file edge pass in
        # _store_file would resolve every import a second time.
        self._edges_rebuilt_after = (
            self._edges_rebuilt_after or bool(stats.deleted) or cfg_changed
        )
        if self._edges_rebuilt_after:
            # durable, not per-process: a build killed between the batched commits
            # and the rebuild must not leave already-committed files without their
            # import edges (file_deps would quietly under-report them). Committed
            # on its own so a crash before the rebuild leaves it visible.
            self.db.set_meta("edges_rebuild_pending", "1")
            self.db.commit()

        if to_parse:
            stats.changed = [rel for rel, _ in to_parse]
            try:
                with ThreadPoolExecutor(max_workers=MAX_PARSE_WORKERS) as ex:
                    for head in range(0, len(to_parse), PARSE_CHUNK):
                        batch = to_parse[head:head + PARSE_CHUNK]
                        for rel, st, hash_, result, source, error in ex.map(
                            self._parse_only, batch
                        ):
                            if result is None:
                                stats.errors += 1
                                self.db.set_parse_error(rel, error or "parse failed")
                                if st is not None:
                                    self._failed[rel] = (st.st_mtime, st.st_size)
                                continue
                            self.db.clear_parse_error(rel)
                            self._failed.pop(rel, None)
                            self._store_file(rel, st, hash_, result, source)
                            stats.parsed += 1
                        self.db.commit()
                        done = head + len(batch)
                        if done < len(to_parse) and (
                            time.perf_counter() - start > INDEX_TIME_BUDGET_S
                        ):
                            # At least one batch is durable; leave the rest for
                            # the next call instead of blocking this one (see
                            # INDEX_TIME_BUDGET_S).
                            stats.pending_files = len(to_parse) - done
                            break
            except Exception:
                # An exception here would leave the write transaction open on
                # this connection, which keeps the SQLite write lock and makes
                # every later call on this index fail with "database is
                # locked" until the process exits. Roll back so the index stays
                # at its last consistent state, then report the failure.
                self.db.conn.rollback()
                raise

        if stats.pending_files:
            # `changed` was the whole queue this pass was offered; only the files
            # it actually finished (stored or failed) are changes to report
            stats.changed = stats.changed[: stats.parsed + stats.errors]

        if stats.parsed or stats.deleted:
            self.db.commit()

        # import_edges: written per file during _store_file when only file
        # contents changed. Otherwise resolution outcomes shift for *other* files
        # too (a new file can satisfy a previously-unresolvable import), so every
        # row is re-derived in this one pass -- and _store_file skips its own pass
        # for the same reason (see _edges_rebuilt_after).
        #
        # Skipped while a budget-truncated build is still running: the rebuild is
        # O(all imports) and would be repeated by every budget-sized pass. The
        # durable meta row keeps it owed, so the pass that finishes the build pays
        # it once.
        if self._edges_rebuilt_after and not stats.pending_files:
            self._rebuild_all_import_edges()
            self.db.set_meta("edges_rebuild_pending", "0")
            self.db.commit()

        # Re-run resolution only when the symbol set can actually have changed
        # (a file was added/changed/removed). Unresolvable edges — external
        # calls like `print()` — keep target_id NULL forever, so gating on
        # "any unresolved edge exists" re-ran the whole resolver on every call,
        # which was the dominant cost of a no-op refresh on large repos. Those
        # edges are now stamped `tried`, so `_resolve_all` short-circuits on an
        # indexed query instead of rebuilding the symbol maps per edit.
        #
        # Deferred entirely on a budget-truncated pass, and that is not a cost
        # saving but a correctness rule: resolving against a half-indexed symbol
        # set links edges a complete build would refuse to guess (measured on a
        # 4,788-file package -- the split build linked 2,148 more call edges than
        # the one-pass build, every one of them an ambiguity the full set rejects).
        # A partial index therefore answers names, structure, search and files,
        # and says "graph not built yet" instead of showing speculative edges.
        if (stats.parsed or stats.deleted) and not stats.pending_files:
            stats.pending_edges = _resolve_all(
                self.db, self._fresh_names,
                full=bool(stats.deleted or self._file_set_changed or cfg_changed),
                deadline=start + 2 * INDEX_TIME_BUDGET_S,
            )
        elif not stats.pending_files and self.db.has_unresolved_edges():
            # the files are all indexed but an earlier pass ran out of budget
            # mid-graph: continue from the edges nobody has looked at yet
            stats.pending_edges = _resolve_all(
                self.db, set(), full=False, deadline=start + 2 * INDEX_TIME_BUDGET_S
            )
        self.db.commit()

        stats.duration_ms = (time.perf_counter() - start) * 1000
        stats.total_files = len(seen)
        stats.total_symbols = self.db.count_symbols()
        stats.skipped = self._walk_skipped
        stats.large_files = self._large_files[:20]
        return stats

    def build_to_completion(self) -> IndexStats:
        """Refresh until nothing is pending, merging the per-pass stats.

        One refresh stops at `INDEX_TIME_BUDGET_S` so a tool call cannot block for
        minutes; this is for callers that do want the whole index built. The
        batches are durable, so an interrupt here loses nothing either.
        """
        stats = self.refresh()
        while stats.pending_files or stats.pending_edges:
            more = self.refresh()
            stats.pending_files = more.pending_files
            stats.pending_edges = more.pending_edges
            stats.parsed += more.parsed
            stats.errors += more.errors
            stats.deleted += more.deleted
            stats.duration_ms += more.duration_ms
            stats.changed += more.changed
            stats.total_files = more.total_files
            stats.total_symbols = more.total_symbols
            stats.large_files = more.large_files
            stats.skipped = more.skipped
        return stats

    def force_index(self) -> IndexStats:
        """Rebuild from scratch (used once on first run)."""
        for row in self.db.conn.execute("SELECT path FROM files"):
            self.db.delete_file(row[0])
        self.db.commit()
        return self.build_to_completion()

    # ---------------- internals ----------------

    def _walk(
        self, cfg_sig_parts: list[float] | None = None
    ) -> list[tuple[str, os.stat_result, str]]:
        """Walk the tree and return (os path, stat, project-relative posix path).

        The path stays a plain string: nothing reads the file until it is
        parsed, so wrapping all 17k candidates in `Path` objects was pure
        startup cost for the incremental scan.

        The stat comes from the ``DirEntry`` (already fetched by ``is_dir``/
        ``is_file``), so the caller does not stat each file a second time —
        halving the syscalls of the per-call incremental scan. When
        ``cfg_sig_parts`` is given, the mtime of every build-config file
        encountered is appended, giving the caller a cheap change fingerprint
        for files that decide import resolution but are not themselves indexed.

        The relative path is carried down the stack rather than recomputed with
        ``os.path.relpath`` per entry: relpath runs ``abspath`` + two
        ``normcase`` calls (on Windows each is an ``LCMapStringEx`` round trip),
        which alone cost ~45% of a no-op refresh on a 2k-file repo. Directories
        stay plain strings for the same reason -- ``Path`` normalizes too.
        """
        out: list[tuple[str, os.stat_result, str]] = []
        root = str(self.root)
        stack: list[tuple[str, str]] = [(root, "")]
        checked = 0
        while stack:
            d, rel_prefix = stack.pop()
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
                    rel = f"{rel_prefix}/{name}" if rel_prefix else name
                    # check_parents=False: an ignored directory is never pushed,
                    # so no ancestor of this entry can match a bare-name rule
                    if self._ignore.matches(rel, name, check_parents=False):
                        continue
                    try:
                        is_dir = e.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir:
                        if name != ".git":
                            stack.append((e.path, rel))
                        continue
                    try:
                        if not e.is_file(follow_symlinks=False):
                            continue
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if cfg_sig_parts is not None and name in _BUILD_CONFIG_FILES:
                        cfg_sig_parts.append(st.st_mtime)
                    if language_for_path(name) is not None:
                        out.append((e.path, st, rel))
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
            st = os.stat(path)
            with open(path, "rb") as fh:
                source = fh.read()
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
                "signature": normalize_signature(s.signature),
                "doc": s.doc,
                "start_line": s.start_line,
                "end_line": s.end_line,
                "start_col": s.start_col,
                "end_col": s.end_col,
                "decorated": s.decorated,
                "param_types": json.dumps(s.param_types or {}),
            }
            for s in result.symbols
        ]
        self._fresh_names.update(s["name"] for s in symbols)
        if self.db.get_file_id(rel) is None:
            self._file_set_changed = True
            if not self._edges_rebuilt_after:
                # the flip happens per file, but the owed rebuild has to survive
                # a crash before it runs: recorded here, committed with this chunk
                self.db.set_meta("edges_rebuild_pending", "1")
                self._edges_rebuilt_after = True
        fid = self.db.upsert_file(rel, lang, hash_, st.st_mtime, st.st_size)
        self.db.replace_file_symbols(fid, symbols)
        self.db.replace_file_imports(
            fid,
            [{"text": i.text, "kind": i.kind, "line": i.line} for i in result.imports],
        )
        # Materialize this file's import->file edges now. Exact for content-only
        # edits (the file set, hence resolution, is unchanged); when the file set
        # changed, `_refresh` re-derives every row in one wholesale pass at the
        # end, and doing both passes resolves every import twice -- 47% of the
        # store phase on a 191-file sentry subtree.
        if not self._edges_rebuilt_after:
            edges: list[tuple[str, int]] = []
            for imp in result.imports:
                for target in graph.import_targets(self.db, imp.text, rel):
                    edges.append((target, imp.line))
            self.db.replace_file_import_edges(fid, edges)
        self.db.replace_file_template_refs(
            fid, getattr(result, "template_refs", None) or []
        )
        content_rows, capped = _extract_content_lines(
            lang, source.decode("utf-8", "replace")
        )
        # durable, not per-process: a steady-state query must still be able to
        # say that content search over this file is partial
        self.db.conn.execute(
            "UPDATE files SET content_capped = ? WHERE id = ?", (int(capped), fid)
        )
        self.db.replace_file_line_content(fid, content_rows)
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

    def _rebuild_all_import_edges(self) -> None:
        """Re-derive every file's import->file edges from scratch.

        Runs when the file set changed (a new file can satisfy a previously
        unresolvable import) or a build config (tsconfig/go.mod/...) changed.
        Cost is O(total imports) resolution per rebuild — paid only when the
        inputs to resolution changed, never on content-only edits.
        """
        for (rel,) in self.db.conn.execute("SELECT path FROM files ORDER BY path"):
            fid = self.db.get_file_id(rel)
            if fid is None:
                continue
            edges: list[tuple[str, int]] = []
            for (text, line) in self.db.conn.execute(
                "SELECT text, line FROM file_imports WHERE file_id=? ORDER BY line", (fid,)
            ):
                for target in graph.import_targets(self.db, text, rel):
                    edges.append((target, line))
            self.db.replace_file_import_edges(fid, edges)

class _LazyRow:
    """``dict.get`` over a per-key query.

    Only ``.get`` is used by the resolver, so this stands in for the bulk dicts
    it replaces; misses are cached too.
    """

    def __init__(self, fetch):
        self._fetch = fetch
        self._cache: dict = {}

    def get(self, key, default=None):
        if key not in self._cache:
            self._cache[key] = self._fetch(key)
        got = self._cache[key]
        return default if got is None else got


class _NameLookup:
    """Memoized ``db.resolve_single_name`` for the duration of one pass.

    The same leaf names recur thousands of times in a pass (`add`, `String`,
    `DeepCopyObject`), and every uncached call is its own SQL query: indexing a
    496-file subtree of kubernetes spent 72s of its 88s inside ``_resolve_all``,
    216k ``execute`` calls of it. Symbols do not change during a pass, so one
    instance per ``_resolve_all`` call is both safe and enough.
    """

    def __init__(self, db: DB):
        self._db = db
        self._cache: dict[str, list[int]] = {}

    def get(self, name: str) -> list[int]:
        got = self._cache.get(name)
        if got is None:
            got = self._db.resolve_single_name(name)
            self._cache[name] = got
        return got


def _file_import_text(db: DB, fid: int) -> str:
    """Lowercased import text of one file, in the shape the resolver expects."""
    return "".join(
        " " + (text or "").lower()
        for (text,) in db.conn.execute(
            "SELECT text FROM file_imports WHERE file_id = ?", (fid,)
        )
    )


def _symbol_names(db: DB, sid: int):
    r = db.conn.execute(
        "SELECT name, qualified_name FROM symbols WHERE id = ?", (sid,)
    ).fetchone()
    return (r[0], r[1]) if r else None


def _symbol_file(db: DB, sid: int):
    r = db.conn.execute("SELECT file_id FROM symbols WHERE id = ?", (sid,)).fetchone()
    return r[0] if r else None


def _symbol_param_types(db: DB, sid: int) -> dict:
    r = db.conn.execute(
        "SELECT param_types FROM symbols WHERE id = ?", (sid,)
    ).fetchone()
    if not r or not r[0]:
        return {}
    try:
        return json.loads(r[0])
    except Exception:
        return {}


def _resolve_all(
    db: DB, fresh_names: set[str] | None = None, full: bool = False,
    deadline: float | None = None,
) -> int:
    """Resolve relations whose target_id is NULL against known symbols.

    Returns the number of edges left unvisited (0 when this pass finished the
    graph). ``deadline`` is a ``time.perf_counter()`` value: the loop stops at the
    next :data:`RESOLVE_BLOCK` boundary and leaves everything past it `tried = 0`,
    so a later pass continues where this one stopped. Splitting is safe because
    each edge's decision depends only on the symbol set, which does not change
    during a pass -- the same edges come out resolved either way (verified on a
    4,788-file package: identical relation fingerprints).

    Strategy:
      - exact unique name -> link
      - multiple candidates -> pick the one whose class is imported in the
        caller's file (e.g. `from auth.service import AuthService`)
      - dotted target (auth.login) -> match qualified_name suffix

    An edge that this pass cannot resolve is stamped ``tried`` and skipped by
    later passes. Without that stamp every content edit re-attempted every
    never-resolvable edge (`print()`, `foo.bar()` on a third-party object) *and*
    rebuilt the symbol/import maps, which cost 962ms of a one-file refresh on
    vue/core and grows with total edges rather than with the edit -- unacceptable
    on a 100k-edge repo. The stamp is cleared wholesale when the candidate set
    itself changes (a file added/removed, build config edited), and per-name for
    bare targets matching a symbol a freshly parsed file declares -- the one case
    where "it did not exist when we tried" explains the miss. A member target
    that failed on ambiguity/evidence would fail again the same way, so leaving
    it stamped costs nothing it could have resolved.
    """
    if full:
        db.conn.execute("UPDATE relations SET tried = 0 WHERE target_id IS NULL")
    elif fresh_names:
        marks = ",".join("?" * len(fresh_names))
        db.conn.execute(
            f"UPDATE relations SET tried = 0 "
            f"WHERE target_id IS NULL AND tried = 1 AND target IN ({marks})",
            sorted(fresh_names),
        )
    pending = db.conn.execute(
        "SELECT id, source_id, target, rtype FROM relations "
        "WHERE target_id IS NULL AND tried = 0 "
        "AND rtype IN ('calls', 'references', 'inherits') ORDER BY id"
    ).fetchall()
    if not pending:
        return 0
    # A full pass touches most of the project, so read the lookup tables in one
    # scan each. A scoped one (the common case: an agent edited a file) touches a
    # handful, so read per key on demand -- the bulk builds alone cost ~400ms of
    # a 425ms single-file refresh on vue/core, i.e. the project paid for the edit.
    bulk = full or len(pending) > 200
    if bulk:
        # one scan of `symbols` fills all three per-symbol maps: three separate
        # full scans (and a filtered one for param_types, which has no index)
        # made this the cost of the edit rather than of the pass
        import_text_by_file: dict = {}
        for fid, text in db.conn.execute("SELECT file_id, text FROM file_imports"):
            import_text_by_file[fid] = import_text_by_file.get(fid, "") + " " + text.lower()
        sym_files: dict = {}
        caller_file: dict = {}
        param_types: dict = {}
        for sid, name, qname, fid, pt in db.conn.execute(
            "SELECT id, name, qualified_name, file_id, param_types FROM symbols"
        ):
            sym_files[sid] = (name, qname)
            caller_file[sid] = fid
            if pt:
                try:
                    param_types[sid] = json.loads(pt)
                except Exception:
                    pass
    else:
        import_text_by_file = _LazyRow(lambda fid: _file_import_text(db, fid))
        sym_files = _LazyRow(lambda cid: _symbol_names(db, cid))
        caller_file = _LazyRow(lambda sid: _symbol_file(db, sid))
    file_paths: dict[int, str] = {}
    single = _NameLookup(db)

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

    # Parameter annotations recorded at parse time (`def f(svc: UserService)`):
    # the call text names its receiver and the annotation names the receiver's
    # type, which together resolve `svc.run(...)` without full type inference.
    # The bulk branch filled these in its single scan.
    if not bulk:
        param_types = _LazyRow(lambda sid: _symbol_param_types(db, sid))

    # Import aliases, extracted once per file instead of once per unresolved
    # edge (see _build_alias_map).
    alias_maps: dict[int, tuple[dict, dict]] = {}

    def file_alias_map(fid: int) -> tuple[dict, dict]:
        got = alias_maps.get(fid)
        if got is None:
            got = _build_alias_map(import_text_by_file.get(fid, ""))
            alias_maps[fid] = got
        return got

    # Candidate sets depend only on the target text and the symbol table, which
    # is fixed for the duration of a pass, so the same call text never has to be
    # re-looked-up: `add`, `get` and friends recur thousands of times per repo.
    candidates_by_target: dict[str, list[int]] = {}

    visited = 0
    last_id = -1
    for rel_id, source_id, target, rtype in pending:
        if (deadline is not None and visited and not visited % RESOLVE_BLOCK
                and time.perf_counter() > deadline):
            # whole blocks only, and the first block always runs: a pass that is
            # asked to stop still makes progress it can resume from
            break
        visited += 1
        last_id = rel_id
        if rtype in ("calls", "references"):
            candidates = candidates_by_target.get(target)
            if candidates is None:
                candidates = _candidates_for_target(db, sym_files, target, single)
                candidates_by_target[target] = candidates
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
                    import_text_by_file, caller_file, sym_files, param_types,
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
                    # parameter-annotation evidence: `svc.run(...)` where the
                    # caller declares `svc: UserService` -- the owner must be
                    # that type. Cheap, explicit, and covers receivers the
                    # import evidence misses (caller and service in the same
                    # file, DI-provided instances).
                    head = _target_head(target)
                    ptype = param_types.get(source_id, {}).get(head, "")
                    if ptype:
                        by_type = [
                            cid for cid in candidates
                            if _owner_of(sym_files.get(cid, ("", ""))[1]) == ptype
                        ]
                        if len(by_type) == 1:
                            picked = by_type
                if len(picked) != 1 and src_fid is not None:
                    # Java fully-qualified import: `import com.a.UserService;`
                    # pins the candidate to package com.a
                    # (com/a/UserService.java), which bare class-name evidence
                    # cannot tell apart.
                    imp = import_text_by_file.get(src_fid, "")
                    fq = [
                        cid for cid in candidates
                        if _java_fq_imported(path_of_file(caller_file.get(cid)), imp)
                    ]
                    if len(fq) == 1:
                        picked = fq
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
                        solo = single.get(parts[1])
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
                caller_fid = caller_file.get(source_id)
                if caller_fid is not None:
                    alias = _resolve_via_alias(
                        db, target, file_alias_map(caller_fid), path_of_file(caller_fid)
                    )
                    if alias is not None:
                        db.apply_resolution(rel_id, alias)
        elif rtype == "inherits":
            # bases are class names: unique-name match, else skip (heuristic noise)
            last = _target_last(target)
            candidates = [
                cid for cid in single.get(last)
                if _target_last(sym_files.get(cid, ("", ""))[1]) == last
            ]
            if len(candidates) == 1:
                db.apply_resolution(rel_id, candidates[0])

    # whatever this pass looked at and left dangling is not resolvable without
    # new candidates: stamp it so the next edit does not walk it again. Bounded by
    # the highest id actually visited: a pass that stopped at its deadline must
    # leave the rest `tried = 0`, or the next pass would skip it forever.
    db.conn.execute(
        "UPDATE relations SET tried = 1 WHERE tried = 0 AND target_id IS NULL "
        "AND rtype IN ('calls', 'references', 'inherits') AND id <= ?", (last_id,)
    )
    return len(pending) - visited


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
    param_types: dict[int, dict[str, str]] | None = None,
) -> bool:
    """Should a *member* candidate be linked for this call?

    A member is any symbol whose qualified name has an owner (`Svc.run`);
    module-level functions (bare qname) are always plausible. A member needs
    local evidence, in this order:

    - the caller lives in the same file as the candidate;
    - the call text itself names the owner (`user.save()` -> owner `User`);
    - the receiver's declared parameter type matches the owner
      (`svc.run()` with `svc: UserService` -> owner `UserService`);
    - caller and candidate are members of the same class (`self.helper()`);
    - the owner name appears in the caller's imports (word-boundary match,
      so owner `user` does not match an import of `user_service`).

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
    if head and param_types:
        # the receiver is an annotated parameter: `svc: UserService` + `svc.run()`
        ptype = param_types.get(source_id, {}).get(head, "")
        if ptype and ptype == owner:
            return True
    src_owner = _owner_of(sym_files.get(source_id, ("", ""))[1])
    if src_owner and src_owner == owner:
        return True  # `self.helper()` -- the caller's own class owns the method
    if src_fid is not None:
        imp = import_text_by_file.get(src_fid, "")
        if not imp:
            return False
        return _bounded_hit(imp, owner.lower(), "$")
    return True


def _bounded_hit(hay: str, needle: str, extra: str) -> bool:
    """Does ``needle`` occur in ``hay`` delimited by non-word characters?

    Word characters are alphanumerics plus ``_``, plus whatever ``extra`` adds
    (``$`` for JS identifiers, ``.`` for Java fully-qualified names) -- the same
    sets the ``(?<![\\w$])name(?![\\w$])`` patterns this replaced used.

    The per-edge regex was the most expensive call in a full resolution pass:
    the pattern string differs per owner, so thousands of distinct owners thrashed
    the 512-entry ``re`` compile cache. On sentry's ``src/sentry/api`` (364
    files) the 2,005 calls of one pass cost 846us each, against 224us for this
    version -- same rule, same result, no compile.
    """
    if not needle:
        return False
    banned = "_" + extra
    at, width = 0, len(needle)
    while (i := hay.find(needle, at)) >= 0:
        before = hay[i - 1] if i else ""
        after = hay[i + width] if i + width < len(hay) else ""
        # `"" in banned` is True in Python (empty substring), so an edge of the
        # haystack has to be excluded by length, not by membership
        if not (before and (before.isalnum() or before in banned)) and not (
            after and (after.isalnum() or after in banned)
        ):
            return True
        at = i + 1
    return False


def _java_fq_imported(candidate_path: str, imp_text: str) -> bool:
    """Does the caller's import text pin ``candidate_path`` by fully-qualified
    Java name?

    ``import com.a.UserService;`` names the package of
    ``com/a/UserService.java`` — evidence a bare class-name match cannot
    provide, since two packages may both define ``UserService``. The import
    text is the caller's lowercased import concatenation.
    """
    if not imp_text or not candidate_path.endswith(".java"):
        return False
    pkg, _, stem = candidate_path.rpartition("/")
    if not pkg:
        return False
    fq = (pkg.replace("/", ".") + "." + stem.rsplit(".", 1)[0]).lower()
    return _bounded_hit(imp_text, fq, ".")


_ALIAS_NAMED_RE = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]")
_ALIAS_BARE_RE = re.compile(r"import\s+(\w+)\s+as\s+(\w+)\s+from\s*['\"]([^'\"]+)['\"]")
_ALIAS_NS_RE = re.compile(r"import\s+\*\s+as\s+(\w+)\s+from\s*['\"]([^'\"]+)['\"]")


def _build_alias_map(imp_text: str) -> tuple[dict[str, list], dict[str, str]]:
    """A file's local bindings, from its (lowercased) import text.

    Returns ``(alias_to_export, namespace_to_module)``: `import {a as b}` and
    `import x as y` both map local name -> [(exported name, module spec)]
    (named imports first, then bare ones, matching the previous scan order),
    and `import * as ns` maps `ns` -> module spec.

    Per file rather than per edge: the resolver used to run these three patterns
    over the caller's whole import block for every unresolved bare call, which on
    a 364-file subtree meant ~59k regex scans of text that never changes (and
    that block is several KB in Python modules).
    """
    alias_to_export: dict[str, list[tuple[str, str]]] = {}
    for m in _ALIAS_NAMED_RE.finditer(imp_text):
        mod_spec = m.group(2)
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                orig, local = (p.strip() for p in part.split(" as ", 1))
            else:
                orig = local = part
            alias_to_export.setdefault(local.lower(), []).append((orig, mod_spec))
    for m in _ALIAS_BARE_RE.finditer(imp_text):
        alias_to_export.setdefault(m.group(2).lower(), []).append(
            (m.group(1), m.group(3))
        )
    namespace_to_module: dict[str, str] = {}
    for m in _ALIAS_NS_RE.finditer(imp_text):
        namespace_to_module.setdefault(m.group(1).lower(), m.group(2))
    return alias_to_export, namespace_to_module


def _resolve_via_alias(
    db: DB, target: str, aliases: tuple[dict, dict], src_path: str
) -> int | None:
    """Resolve a bare call target through import aliasing in the caller file.

    `import { logout as apiLogout } from '../api/admin'` + `apiLogout()` →
    the symbol `logout` in the resolved module. Also covers `import x as y`
    (Python) and `import * as ns` (dotted targets). Case-insensitive: the
    import text is lowercased when grouped.
    """
    if not src_path:
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

    alias_to_export, namespace_to_module = aliases
    tgt = target.lower()
    for orig, mod_spec in alias_to_export.get(tgt, ()):
        hit = resolve_export(mod_spec, orig)
        if hit is not None:
            return hit
    if "." in tgt:
        head = tgt.split(".", 1)[0]
        mod_spec = namespace_to_module.get(head)
        if mod_spec:
            hit = resolve_export(mod_spec, target[len(head) + 1:])
            if hit is not None:
                return hit
    return None


def _candidates_for_target(
    db: DB, sym_files: dict[int, tuple], target: str, single: _NameLookup
) -> list[int]:
    """Symbols that could satisfy this call text.

    A qualified text (`Svc.run`, `clap::Command::new`) resolves through its last
    name segment and then prefers candidates whose qualified name matches the
    text with `.`/`::` normalized to a single separator. `::` used to fall
    through to a literal name lookup (`resolve_single_name("Command::new")`),
    which nothing can match, so Rust associated-function calls were never
    resolved.
    """
    cands_by_name = single.get(_target_last(target))
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


