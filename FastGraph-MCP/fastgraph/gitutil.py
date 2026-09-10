"""Git-aware change detection (used by changed_context)."""

from __future__ import annotations

import subprocess
from pathlib import Path


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


def changed_symbols(db, changes: dict[str, str]) -> dict[str, list[dict]]:
    """Map status->symbols that live in changed files."""
    out: dict[str, list[dict]] = {}
    for rel, status in changes.items():
        row = db.conn.execute("SELECT id FROM files WHERE path=?", (rel,)).fetchone()
        if row is None:
            continue
        fid = row[0]
        syms = db.conn.execute(
            """SELECT s.id, s.name, s.kind, s.qualified_name, s.start_line,
                      (SELECT path FROM files WHERE id=?) AS path
               FROM symbols s WHERE s.file_id=?""",
            (fid, fid),
        ).fetchall()
        out.setdefault(status, []).extend(
            {"id": r[0], "name": r[1], "kind": r[2], "qualified_name": r[3], "start_line": r[4], "path": r[5]}
            for r in syms
        )
    return out