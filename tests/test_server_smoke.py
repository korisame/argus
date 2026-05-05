"""Spawn the MCP server, send initialize + tools/list, expect 25+ tools."""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_initialize_and_tools_list():
    server = os.path.join(ROOT, "mcp_server", "server.py")
    inp = ('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
           '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n')
    env = {**os.environ, "ARGUS_ASYNC": "0"}  # sync path is deterministic for tests
    r = subprocess.run([sys.executable, server], input=inp, capture_output=True,
                       text=True, timeout=20, env=env)
    assert r.returncode == 0, f"server crashed: {r.stderr[:500]}"
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert len(lines) >= 2
    init = json.loads(lines[0])
    assert init["result"]["serverInfo"]["name"] == "argus"
    tl = json.loads(lines[1])
    tools = tl["result"]["tools"]
    assert len(tools) >= 25, f"expected ≥25 tools, got {len(tools)}"
    names = {t["name"] for t in tools}
    for required in ("argus_doctor", "argus_click", "argus_find", "argus_paste",
                     "argus_wait_for", "argus_repl", "argus_autotune"):
        assert required in names, f"missing tool: {required}"
