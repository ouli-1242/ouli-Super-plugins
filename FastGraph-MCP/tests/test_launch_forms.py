"""How the server is launched decides whether a project can shadow the stdlib.

`python -m fastgraph` puts the current directory first on `sys.path`, and a
desktop client starts the MCP process with the project (or a subfolder of it) as
cwd -- so any project containing a top-level `types/`, `json/`, `logging/`, ...
breaks the interpreter before our code runs. sentry does exactly this
(`src/sentry/types/__init__.py`). The forms that survive it are `python -P -m`
(recommended: only the cwd is kept off `sys.path`), `python -I -m` (isolated, so
`PYTHONPATH` and user site-packages go missing too) and the installed console
script -- all three are exercised here from a directory that shadows `types`.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT = 60
INIT = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
               "clientInfo": {"name": "probe", "version": "0"}},
})


def _handshake(cmd, cwd: Path):
    p = subprocess.Popen(cmd, cwd=str(cwd), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
    out, err = p.communicate(INIT + "\n", timeout=TIMEOUT)
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("result", {}).get("serverInfo"):
            return msg["result"]["serverInfo"]
    return None, err[-400:]


def _hostile_cwd(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "types").mkdir(parents=True)
    (root / "types" / "__init__.py").write_text("SHADOW = 1\n", encoding="utf-8")
    (root / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return root


def test_console_script_survives_a_stdlib_shadowing_project(tmp_path):
    exe = shutil.which("fastgraph")
    if exe is None:  # source checkout without `pip install -e .`
        return
    info = _handshake([exe], _hostile_cwd(tmp_path))
    assert isinstance(info, dict) and info["name"] == "fastgraph", info


def test_dash_P_dash_m_survives_a_stdlib_shadowing_project(tmp_path):
    """The recommended form: `-P` only drops the cwd/script dir from sys.path."""
    info = _handshake([sys.executable, "-P", "-m", "fastgraph"], _hostile_cwd(tmp_path))
    assert isinstance(info, dict) and info["name"] == "fastgraph", info


def test_isolated_dash_m_also_survives(tmp_path):
    """`-I` fixes the shadowing too, at the price of ignoring `PYTHONPATH` and the
    user site-packages -- so a `pip install --user` fastgraph would not be
    importable. A documented alternative, never the default advice."""
    info = _handshake([sys.executable, "-I", "-m", "fastgraph"], _hostile_cwd(tmp_path))
    assert isinstance(info, dict) and info["name"] == "fastgraph", info


def test_plain_dash_m_is_the_form_that_breaks(tmp_path):
    """Pinning the failure: if this ever stops failing, the note in README about
    `-I` / the console script is stale and should be removed."""
    info = _handshake([sys.executable, "-m", "fastgraph"], _hostile_cwd(tmp_path))
    assert not isinstance(info, dict), (
        "plain `-m` unexpectedly survived a project that shadows `types`; "
        "the README's launch advice needs updating")
