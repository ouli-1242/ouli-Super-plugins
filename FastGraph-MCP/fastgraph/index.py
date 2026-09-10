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
    matches_ignore,
    parse_ignore,
    user_home,
)
from fastgraph.db import DB
from fastgraph import graph
from fastgraph.parsers.base import SymbolInfo
from fastgraph.parsers.registry import get_adapter

_EXT_LANG = {
    ".py": "python",
    ".ts": "typescript", ".tsx": "tsx", ".mts": "typescript", ".cts": "typescript",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".vue": "vue", ".svelte": "svelte", ".wxml": "wxml",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "cpp", ".h": "cpp", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp",
}

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
INDEX_VERSION = "6"

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


class Indexer:
    def __init__(self, root: Path, db: DB, excludes: set[str] | None = None):
        self.root = root.resolve()
        self.db = db
        self.excludes = excludes or DEFAULT_EXCLUDES
        self._walk_skipped = False
        self._ignore_patterns: list[str] = []
        # Serialize refresh() across threads: every tool call runs _ensure_fresh,
        # and concurrent writes to the same sqlite connection crash with
        # InterfaceError / UNIQUE constraint races (see STRESS_TEST_REPORT P1-1).
        self._refresh_lock = threading.RLock()

    def refresh(self) -> IndexStats:
        with self._refresh_lock:
            return self._refresh()

    def _refresh(self) -> IndexStats:
        start = time.perf_counter()
        stats = IndexStats()

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

        cached = self.db.file_map()

        # Index-format/parser-output upgrade: rebuild once, then carry on with
        # the normal incremental scan (cached is now empty, so every file gets
        # re-parsed in the same pass).
        if self.db.get_meta("index_version") != INDEX_VERSION:
            for rel in cached:
                self.db.delete_file(rel)
            self.db.commit()
            cached = {}
            self.db.set_meta("index_version", INDEX_VERSION)
            self.db.commit()

        to_parse: list[tuple[str, Path]] = []
        seen: set[str] = set()

        for p in self._walk():
            rel = p.relative_to(self.root).as_posix()
            seen.add(rel)
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_size > MAX_FILE_SIZE:
                continue
            stats.scanned += 1
            if cached.get(rel) == st.st_mtime:
                continue  # untouched: zero IO
            to_parse.append((rel, p))

        stats.skipped = getattr(self, "_walk_skipped", False)
        if not stats.skipped:
            for rel in cached:
                if rel not in seen:
                    self.db.delete_file(rel)
                    stats.deleted += 1

        if to_parse:
            with ThreadPoolExecutor(max_workers=MAX_PARSE_WORKERS) as ex:
                parsed = ex.map(self._parse_only, to_parse)
            for rel, st, hash_, result, source in parsed:
                if result is None:
                    stats.errors += 1
                    self.db.set_parse_error(rel, "parse failed")
                    continue
                self.db.clear_parse_error(rel)
                self._store_file(rel, st, hash_, result, source)
                stats.parsed += 1

        if stats.parsed or stats.deleted:
            self.db.commit()

        # Re-run resolution on leftover unresolved relations so improved
        # resolver logic (e.g. constructor disambiguation) heals existing
        # indexes without a full rebuild. Cheap when nothing is unresolved.
        if self.db.conn.execute("SELECT 1 FROM relations WHERE target_id IS NULL AND rtype IN ('calls','inherits') LIMIT 1").fetchone():
            _resolve_all(self.db)
        self.db.commit()

        stats.duration_ms = (time.perf_counter() - start) * 1000
        stats.total_files = len(seen)
        stats.total_symbols = self.db.count_symbols()
        stats.skipped = getattr(self, "_walk_skipped", False)
        return stats

    def force_index(self) -> IndexStats:
        """Rebuild from scratch (used once on first run)."""
        for row in self.db.conn.execute("SELECT path FROM files"):
            self.db.delete_file(row[0])
        self.db.commit()
        return self.refresh()

    # ---------------- internals ----------------

    def _walk(self) -> list[Path]:
        out: list[Path] = []
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
                    if self._ignore_patterns and matches_ignore(
                        self._ignore_patterns, rel, name
                    ):
                        continue
                    try:
                        is_dir = e.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir:
                        if name != ".git":
                            stack.append(Path(e.path))
                    elif e.is_file(follow_symlinks=False):
                        ext = Path(name).suffix.lower()
                        if ext in _EXT_LANG:
                            out.append(Path(e.path))
        return out

    def _parse_only(self, item: tuple) -> tuple:
        """Thread-safe: read + parse, no DB access. Returns (rel, stat, hash, ParseResult|None)."""
        rel, path = item
        lang = _EXT_LANG.get(Path(rel).suffix.lower())
        adapter = get_adapter(lang)
        if adapter is None:
            return rel, None, "", None, ""
        try:
            st = path.stat()
            source = path.read_bytes()
        except OSError:
            return rel, None, "", None, ""
        hash_ = hashlib.sha256(source).hexdigest()[:24]
        try:
            result = adapter.parse(source)
        except Exception:
            result = None
        return rel, st, hash_, result, source

    def _store_file(self, rel: str, st, hash_: str, result, source: bytes) -> None:
        """Single-threaded DB write for one parsed file."""
        lang = result.language
        module_doc = getattr(result, "module_doc", "") or ""
        if module_doc:
            # Adapters return a module-level docstring separately; surface it
            # as a `module` symbol so top-of-file docs are searchable (was
            # silently dropped, so Chinese module docs were invisible).
            stem = Path(rel).stem
            result.symbols.insert(0, SymbolInfo(
                name=stem, kind="module", qualified_name=stem,
                signature="", doc=module_doc,
                start_line=1, end_line=1, start_col=0, end_col=0,
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

    for rel_id, source_id, target, rtype in pending:
        if rtype in ("calls", "references"):
            candidates = _candidates_for_target(db, sym_files, target)
            picked: list[int] = []
            if len(candidates) == 1:
                # `rows.add(...)`/`noteList.add(...)` produce bare `add` (and
                # dotted `rows.add`) edges; when a project has exactly one
                # symbol named `add`, the unique-name resolution links every
                # collection call to it, polluting find_callers with dozens
                # of unrelated callers. Member targets must live in the same
                # file as the caller or be imported by it.
                if _member_target_plausible(
                    db, candidates[0], source_id, import_text_by_file, caller_file
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
                # `self.tutor_agent.run`: the attribute name maps 1:1 onto the
                # snake_cased owner class (TutorAgent -> tutor_agent), which
                # resolves the per-instance dispatch without needing source
                # assignment tracking.
                if len(picked) != 1 and target.startswith("self."):
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
                if len(picked) != 1 and "." not in target:
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
            if not picked and "." not in target:
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
            candidates = [
                cid for cid in db.resolve_single_name(target)
                if sym_files.get(cid, ("", ""))[1].rsplit(".", 1)[-1] == target.rsplit(".", 1)[-1]
            ]
            if len(candidates) == 1:
                db.apply_resolution(rel_id, candidates[0])


def _member_target_plausible(
    db: DB,
    cid: int,
    source_id: int,
    import_text_by_file: dict[int, str],
    caller_file: dict[int, int],
) -> bool:
    """Reject resolving a *member* candidate (qualified name contains ``.``)
    when the caller neither lives in the same file nor imports the owner
    class/module. Module-level and class-level (bare qname) targets are
    always plausible. See the `rows.add()` -> sole `add` symbol misresolution
    that polluted find_callers/impact_analysis."""
    row = db.conn.execute("SELECT qualified_name FROM symbols WHERE id = ?", (cid,)).fetchone()
    if not row:
        return True
    qname = row[0]
    if "." not in qname:
        return True
    owner = qname.rsplit(".", 1)[0]
    owner_fid: int | None = None
    r = db.conn.execute(
        "SELECT file_id FROM symbols WHERE qualified_name = ? LIMIT 1", (owner,)
    ).fetchone()
    if r:
        owner_fid = r[0]
    src_fid = caller_file.get(source_id)
    if src_fid is not None and owner_fid is not None and src_fid == owner_fid:
        return True  # same-file member call (e.g. `this.add(...)` / `add(...)`)
    if src_fid is not None and owner_fid is not None:
        # Java/C#: same-package classes are visible without an import
        # statement — the import-text check below would wrongly reject
        # legitimate cross-file member calls inside one package.
        src_dir = (db.file_path(src_fid) or "").rsplit("/", 1)[0]
        own_dir = (db.file_path(owner_fid) or "").rsplit("/", 1)[0]
        if src_dir and src_dir == own_dir:
            return True
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
                "AND LOWER(name) = LOWER(?)",
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
    candidates: list[int] = []
    if "." in target:
        last = target.rsplit(".", 1)[-1]
        cands_by_name = db.resolve_single_name(last)
        # prefer exact qualified suffix match
        for cid in cands_by_name:
            q = sym_files.get(cid, ("", ""))[1]
            if q == target or q.endswith("." + target):
                candidates.append(cid)
        if not candidates:
            candidates = cands_by_name
    else:
        candidates = db.resolve_single_name(target)
    return candidates


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


