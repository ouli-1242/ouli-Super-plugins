"""Project configuration and defaults."""

from __future__ import annotations

import fnmatch
import os
import re
from os import getenv
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    "vendor",
    "third_party",
    ".fastgraph",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "Pods",
    ".gradle",
    ".cargo",
    ".tox",
}

MAX_FILE_SIZE = 2 * 1024 * 1024  # skip files larger than 2MB

RESERVED_ENTRIES = {
    ".fastgraph",
}


def user_home() -> Path:
    """Resolve the user's home dir (Windows-safe USERPROFILE check)."""
    return Path(getenv("USERPROFILE") or Path.home()).resolve()


# Local-only ignore file inside the index dir; auto-created with a template on
# first index. (The project-root variant was dropped: local-only keeps the
# project tree clean and the rules per-developer.)
IGNORE_FILENAME = ".fastgraphignore"

IGNORE_TEMPLATE = """# FastGraph 忽略规则（gitignore 风格，仅本机生效）
# 一行一个模式：匹配目录/文件名（任意深度）或相对路径通配
# 下面默认项已生效；删掉某行即恢复索引该目录，按需增删。
#
# ---- 通用 ----
node_modules/
dist/
build/
out/
target/
vendor/
third_party/
*.min.js
*.min.css
*.map
# ---- Python ----
__pycache__/
*.pyc
*.egg-info/
.venv/
venv/
env/
.pytest_cache/
.mypy_cache/
.ruff_cache/
# ---- Node / 前端 ----
.next/
.nuxt/
.svelte-kit/
.turbo/
coverage/
.cache/
# ---- Java ----
.gradle/
# ---- 敏感文件（密钥/证书/凭据，避免内容搜索泄漏）----
*.pem
*.key
*.p12
*.pfx
*.jks
*secret*.json
*credential*.json
service-account*.json
id_rsa*
id_ed25519*
# ---- 示例：你自己项目里的第三方大库 ----
# towxml
"""


def ensure_ignore_template(index_dir: Path) -> None:
    """Write the commented template once; never overwrite user rules."""
    f = index_dir / IGNORE_FILENAME
    if not f.is_file():
        try:
            f.write_text(IGNORE_TEMPLATE, encoding="utf-8")
        except OSError:
            pass


def parse_ignore(text: str) -> list[str]:
    """One pattern per line; '#' comments. A pattern matches a directory/file
    name at any depth, or a relative path, via fnmatch globbing (`towxml`,
    `miniprogram/vendor/*`, `*.min.js`)."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


_MAGIC_RE = re.compile(r"[*?\[\]]")


class IgnoreMatcher:
    """Precompiled `.fastgraphignore` rules.

    ``fnmatch`` normalizes case on every call -- on Windows through the kernel's
    ``LCMapStringEx`` -- so testing ~36 patterns against every scanned entry cost
    hundreds of thousands of normalizations per refresh. Profiling a no-op
    refresh of a 264-file repo put ``matches_ignore`` at ~90% of the total
    (124k ``fnmatch`` + 256k ``normcase`` calls). Rules are therefore compiled
    once: exact names become a set, and the glob rules of each category are fused
    into a single alternation regex, so an entry costs a handful of C-level
    regex matches instead of one ``fnmatch`` per rule. Semantics are unchanged
    (same ``normcase`` case-folding, same parent-directory rule).
    """

    def __init__(self, patterns: list[str]):
        names: list[str] = []
        name_globs: list[str] = []
        path_globs: list[str] = []
        for pat in patterns:
            p = os.path.normcase(pat.rstrip("/"))
            if not p:
                continue
            if "/" in p or "\\" in p:
                path_globs.append(p)
            elif _MAGIC_RE.search(p):
                name_globs.append(p)
            else:
                names.append(p)
        self.names: set[str] = set(names)
        # one alternation instead of N fnmatch calls (each translate() is
        # already anchored, so joining with | preserves match semantics)
        self.name_re = _compile_globs(name_globs)
        self.path_re = _compile_globs(path_globs)

    def __bool__(self) -> bool:
        return bool(self.names or self.name_re or self.path_re)

    def matches(self, rel: str, name: str) -> bool:
        """True when this entry (project-relative path + bare name) is ignored."""
        n = os.path.normcase(name)
        if n in self.names:
            return True
        name_re = self.name_re
        path_re = self.path_re
        if name_re is None and path_re is None:
            return False
        nrel = os.path.normcase(rel)
        if name_re is not None and (name_re.match(n) or name_re.match(nrel)):
            return True
        if self.names or name_re is not None:
            # a pattern without a separator also matches any parent directory
            for seg in rel.split("/")[:-1]:
                nseg = os.path.normcase(seg)
                if nseg in self.names or (name_re is not None and name_re.match(nseg)):
                    return True
        return path_re is not None and bool(path_re.match(nrel))


def _compile_globs(patterns: list[str]) -> re.Pattern | None:
    """Fuse glob patterns into one regex, or None when there are none."""
    if not patterns:
        return None
    return re.compile("|".join(fnmatch.translate(p) for p in patterns))


def matches_ignore(patterns: list[str], rel: str, name: str) -> bool:
    """True when an entry (project-relative path + bare name) is ignored.

    Convenience wrapper for one-off checks; callers in a loop should build an
    :class:`IgnoreMatcher` once and reuse it.
    """
    return IgnoreMatcher(patterns).matches(rel, name)