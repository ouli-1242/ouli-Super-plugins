"""CLI entrypoint: fastgraph [--root <path>] (stdio MCP server).

Without --root, the project root is auto-detected: walk up from the current
directory to the nearest git root (repo boundary); non-git locations fall
back to the current directory. MCP clients that launch the server with their
working directory set to the opened folder therefore index that folder -
open any project, no config per project.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def detect_root(start: Path) -> Path:
    """Nearest git root above ``start``, or ``start`` itself if none found.

    ``.git`` may be a directory (normal repo) or a file (gitfile in
    submodules / worktrees), so ``.exists()`` covers both.
    """
    cur = start
    while True:
        if (cur / ".git").exists():
            return cur
        parent = cur.parent
        if parent == cur:  # filesystem root: nothing found above
            return start
        cur = parent


def _writable(path: Path) -> bool:
    """True if a `.fastgraph` index dir can be created under ``path``."""
    try:
        probe = path / ".fastgraph_probe"
        probe.mkdir(parents=True, exist_ok=True)
        probe.rmdir()
        return True
    except OSError:
        return False


def resolve_root(start: Path) -> Path:
    """Root to index: nearest git root above ``start`` if writable.

    Falls back through ancestors to the first writable dir (desktop apps
    launch stdio servers with cwd=C:\\Windows\\System32 etc., which is not
    writable); final fallback is the user home dir. Prints a hint to stderr
    whenever the detected root is not `start` itself.
    """
    from os import getenv

    home = Path(getenv("USERPROFILE") or Path.home())
    root = detect_root(start)
    if not _writable(root):
        # Desktop apps launch stdio servers with cwd=C:\Windows\System32 etc.
        # - not writable. Prefer the user home over climbing to a system root.
        print(
            f"notice: {root} is not writable, falling back to {home}",
            file=sys.stderr,
        )
        root = home
    elif root != start:
        print(f"notice: indexing git root {root} (cwd: {start})", file=sys.stderr)
    return root


def main(argv: list[str] | None = None) -> int:
    from os import getenv

    parser = argparse.ArgumentParser(
        prog="fastgraph",
        description="FastGraph-MCP stdio server (default root: auto-detected from cwd)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="project root to index (default: $FASTGRAPH_ROOT, else nearest git root above cwd, else cwd)",
    )
    args = parser.parse_args(argv)

    explicit = args.root or (
        Path(getenv("FASTGRAPH_ROOT")) if getenv("FASTGRAPH_ROOT") else None
    )
    root = (
        explicit.resolve()
        if explicit is not None
        else resolve_root(Path.cwd())
    )
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1

    try:
        from fastgraph.server import run_stdio

        run_stdio(root)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())