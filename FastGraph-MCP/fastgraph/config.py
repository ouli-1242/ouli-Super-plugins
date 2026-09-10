"""Project configuration and defaults."""

from __future__ import annotations

import fnmatch
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


def matches_ignore(patterns: list[str], rel: str, name: str) -> bool:
    """True when an entry (project-relative path + bare name) is ignored."""
    for pat in patterns:
        p = pat.rstrip("/")
        if fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p):
            return True
        # pattern matches one of the entry's parent directories
        if "/" not in p and any(
            seg == p or fnmatch.fnmatch(seg, p) for seg in rel.split("/")[:-1]
        ):
            return True
    return False