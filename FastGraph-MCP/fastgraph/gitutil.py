"""Git-aware change detection (used by changed_context)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


# `+++ b/<path>` (post-image name) and `@@ -a,b +c,d @@` (hunk header)
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_ranges(root: Path, base: str | None = None) -> dict[str, list[tuple[int, int]]]:
    """path -> inclusive line ranges touched, in the post-image file.

    ``git status`` answers only *which* file changed, so a one-line edit inside
    one function reported every symbol of a 1,500-line file as touched. With
    ``--unified=0`` the hunk header is exactly the changed range. Files with no
    hunks (untracked, renamed, deleted) get no entry, so they keep whole-file
    handling at the call site.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotepath=false", "diff",
             "--unified=0", "--no-color", "--no-ext-diff", base or "HEAD", "--"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20,
        )
    except Exception:
        return {}
    ranges: dict[str, list[tuple[int, int]]] = {}
    cur: str | None = None
    for line in out.stdout.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            cur = path if path and path != "/dev/null" else None
            continue
        if cur is None or not line.startswith("@@"):
            continue
        m = _HUNK_RE.match(line)
        if not m:
            continue
        start = int(m.group(1))
        # a pure deletion has count 0 and no post-image lines: attribute it to
        # the line it happened at so an enclosing symbol still counts as touched
        count = int(m.group(2) or 1)
        ranges.setdefault(cur, []).append((start, max(start, start + count - 1)))
    return {k: v for k, v in ranges.items() if v}


def git_root(root: Path) -> Path | None:
    try:
        # text=True uses the locale encoding (GBK on Chinese Windows), which
        # cannot decode git's UTF-8 output for non-ASCII paths and silently
        # breaks every git-aware tool. Force UTF-8.
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        if out.returncode == 0:
            return Path(out.stdout.strip())
    except Exception:
        pass
    return None


def changed_files(root: Path, base: Path | None = None) -> dict:
    """Return {path: status} for unstaged+untracked changes, relative POSIX paths.

    ``base`` lets a caller that already resolved the git root (e.g. to fall
    back to mtime detection for non-git projects) pass it in, avoiding a second
    ``git rev-parse`` subprocess.
    """
    changes: dict[str, str] = {}
    base = base if base is not None else git_root(root)
    if base is None:
        return changes
    try:
        # core.quotepath=false: without it git quotes non-ASCII paths as octal
        # escapes ("docs/\346\212\200..."), which then never match the DB paths.
        # encoding=utf-8 mirrors git_root above (locale GBK would corrupt CJK).
        out = subprocess.run(
            ["git", "-C", str(base), "-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
    except Exception:
        return changes
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        status = line[:2].strip()
        path = line[3:].strip()
        # Skip the tool's own index dir even in subdirectories
        # (`.fastgraph/index.sqlite` under any project folder): `git status`
        # reports it as untracked noise on every call.
        if not path or path.startswith(".") or ".fastgraph" in path.split("/"):
            continue
        try:
            rel = (base / path).resolve().relative_to(base.resolve()).as_posix()
        except (ValueError, OSError):
            continue
        if status == "??":
            changes[rel] = "added"
        elif status.startswith("D"):
            changes[rel] = "deleted"
        elif status[0] == "R":
            changes[rel] = "renamed"
        else:
            changes[rel] = "modified"
    return changes


def changed_files_vs(root: Path, base: str) -> dict:
    """{path: status} for every tracked change between ``base`` and the
    working tree, plus untracked files as "added".

    ``base`` is any rev the repo resolves (branch, tag, ``HEAD~5``, a SHA), so
    a whole branch's footprint is visible, not just uncommitted edits. Uses
    ``git diff --name-status <base>`` (worktree vs base — includes uncommitted
    edits) and merges ``git status``'s untracked entries, which diff cannot
    see. Renames report the *new* path: that is the file the index holds.
    """
    changes: dict[str, str] = {}
    base_dir = git_root(root)
    if base_dir is None:
        return changes
    try:
        out = subprocess.run(
            ["git", "-C", str(base_dir), "-c", "core.quotepath=false",
             "diff", "--name-status", base],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
    except Exception:
        return changes
    if out.returncode != 0:
        return changes
    status_map = {"A": "added", "D": "deleted", "R": "renamed", "C": "renamed", "T": "modified"}
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0][0].upper()
        path = parts[-1]
        if not path or path.startswith(".") or ".fastgraph" in path.split("/"):
            continue
        try:
            rel = (base_dir / path).resolve().relative_to(base_dir.resolve()).as_posix()
        except (ValueError, OSError):
            continue
        changes[rel] = status_map.get(status, "modified")
    for rel, st in changed_files(root, base=base_dir).items():
        if st == "added":
            changes.setdefault(rel, "added")
    return changes


def head_ref(root: Path) -> str:
    """Full SHA of HEAD, '' outside a repo.

    Recorded on a snapshot so `what_changed` can later diff the *files* against
    the commit the snapshot was taken at, not just the graph.
    """
    base_dir = git_root(root)
    if base_dir is None:
        return ""
    try:
        out = subprocess.run(
            ["git", "-C", str(base_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def renames(root: Path, base: str | None = None) -> dict[str, str]:
    """old path -> new path for renames git detects between ``base`` and the tree.

    ``changed_files_vs`` deliberately reports only the *new* path, because that
    is the file the index holds. The memory layer needs the other side: without
    old -> new, a note anchored to the file that moved reads as "the code it was
    about is gone", which is the exact failure the layer exists to prevent.
    ``-M`` matters: without rename detection git reports delete + add, and there
    is nothing to link the old anchor to.
    """
    base_dir = git_root(root)
    if base_dir is None:
        return {}
    try:
        out = subprocess.run(
            ["git", "-C", str(base_dir), "-c", "core.quotepath=false",
             "diff", "-M", "--name-status", base or "HEAD", "--"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
    except Exception:
        return {}
    if out.returncode != 0:
        return {}
    found: dict[str, str] = {}
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or not parts[0].upper().startswith(("R", "C")):
            continue
        old, new = parts[-2], parts[-1]
        # No dot-path exclusion here, unlike changed_files: that one is about
        # keeping `git status` noise out of a change report, while this is about
        # explaining one move. `oxlint.json -> .oxlintrc.json` is precisely a move
        # a note anchored on the old path needs to be told about.
        if not old or not new:
            continue
        found[_rel_to_root(base_dir, old)] = _rel_to_root(base_dir, new)
    return {k: v for k, v in found.items() if k and v}


def _rel_to_root(base_dir: Path, path: str) -> str | None:
    try:
        return (base_dir / path).resolve().relative_to(base_dir.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def changed_symbols(
    db,
    changes: dict[str, str],
    ranges: dict[str, list[tuple[int, int]]] | None = None,
) -> dict[str, list[dict]]:
    """Map status->symbols that live in changed files.

    When ``ranges`` (see :func:`changed_ranges`) covers a modified file, only
    symbols whose line span intersects a hunk are reported: without it the
    answer to "what did I touch" is "everything in this file".
    """
    ranges = ranges or {}
    out: dict[str, list[dict]] = {}
    for rel, status in changes.items():
        row = db.conn.execute("SELECT id FROM files WHERE path=?", (rel,)).fetchone()
        if row is None:
            continue
        fid = row[0]
        syms = db.conn.execute(
            """SELECT s.id, s.name, s.kind, s.qualified_name, s.start_line,
                      s.end_line,
                      (SELECT path FROM files WHERE id=?) AS path
               FROM symbols s WHERE s.file_id=?""",
            (fid, fid),
        ).fetchall()
        hunks = ranges.get(rel) or []
        if hunks and status == "modified":
            syms = [r for r in syms if any(r[4] <= hi and r[5] >= lo for lo, hi in hunks)]
        out.setdefault(status, []).extend(
            {"id": r[0], "name": r[1], "kind": r[2], "qualified_name": r[3], "start_line": r[4], "path": r[6]}
            for r in syms
        )
    return out