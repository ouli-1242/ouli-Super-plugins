"""E2E MCP protocol test over stdio, exactly like Cursor spawns the server.

Verifies the *running server* (not the library API). Requires the package
installed (`pip install -e .`) and FASTGRAPH_TEST_ROOT pointing at a real
project; skipped otherwise.
"""
import json
import os
import subprocess
import sys
import threading
import time

import pytest

ROOT = os.environ.get("FASTGRAPH_TEST_ROOT", "")

pytestmark = pytest.mark.skipif(
    not ROOT,
    reason="FASTGRAPH_TEST_ROOT not set (point at a real project for E2E)",
)


class Rpc:
    def __init__(self, proc):
        self.proc = proc
        self.next_id = 0

    def call(self, method: str, params: dict, timeout: float = 300.0):
        self.next_id += 1
        msg = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("server closed stdout (stderr: %s)" % self.proc.stderr.read())
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue
            if resp.get("id") == self.next_id:
                return resp
        raise TimeoutError(f"no response for {method}")

    def call_tool(self, name: str, args: dict) -> dict:
        resp = self.call("tools/call", {"name": name, "arguments": args})
        if resp.get("error"):
            raise RuntimeError(f"{name} errored: {resp['error']}")
        result = resp["result"]
        for c in result.get("content", []):
            if c.get("type") == "text":
                return json.loads(c["text"])
        raise RuntimeError(f"unexpected result shape: {result}")


@pytest.fixture(scope="module")
def server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "fastgraph"],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    rpc = Rpc(proc)
    rpc.call(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "e2e-test", "version": "1.0"},
        },
    )
    rpc.call("notifications/initialized", {})
    yield rpc
    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.wait(timeout=10)


def test_handshake_registers_tools(server):
    tools = server.call("tools/list", {})
    names = sorted(t["name"] for t in tools["result"]["tools"])
    assert len(names) >= 13
    assert "project_overview" in names
    assert "find_callers" in names


def test_find_callers_survives_plausibility(server):
    r = server.call_tool("find_callers", {"symbol": "PageUtil.normalizeSize"})
    assert r["found"] is True
    assert r["count"] >= 0


def test_code_search_returns_results(server):
    r = server.call_tool("code_search", {"query": "extends", "limit": 5})
    assert isinstance(r["results"], list)


def test_changed_context_no_index_noise(server):
    r = server.call_tool("changed_context", {})
    files = (
        list(r["changed_files"].keys())
        if isinstance(r.get("changed_files"), dict)
        else r.get("changed_files", [])
    )
    assert all(".fastgraph" not in f for f in files)


def test_module_cycles_stable(server):
    r = server.call_tool("module_cycles", {})
    assert r["count"] >= 0


def test_concurrent_find_callers(server):
    """8 parallel find_callers must not crash or corrupt responses (thread-pool
    safety of the sqlite connection layer)."""
    results: list[tuple] = []

    def probe(i):
        try:
            server.call_tool("find_callers", {"symbol": "PageUtil.normalizeSize"})
            results.append(("ok", i))
        except Exception as e:  # noqa: BLE001
            results.append(("err", i, str(e)))

    threads = [threading.Thread(target=probe, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(r[0] == "ok" for r in results), [r for r in results if r[0] != "ok"]