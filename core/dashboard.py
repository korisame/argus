"""Local web dashboard for argus state.

Stdlib only (http.server). Single-file SPA: cache view + intent log live tail
+ metrics + app-skills coverage. Bind localhost only.

Started by `argus_dashboard action=start [port=9999]`. Runs in a daemon
thread inside the MCP server process. Stop with `argus_dashboard action=stop`.
"""
from __future__ import annotations

import json
import threading
import socketserver
from http.server import BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import urlparse, parse_qs

from . import intent, patterns, autotune

_STATE: dict = {"server": None, "thread": None, "port": None}


_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>argus dashboard</title>
<style>
  * { box-sizing: border-box; }
  body { font: 13px/1.45 -apple-system, system-ui, sans-serif;
         margin: 0; background: #0d1117; color: #e6edf3; }
  header { padding: 14px 20px; background: #161b22;
           border-bottom: 1px solid #30363d; display: flex; gap: 24px; align-items: center; }
  h1 { font-size: 16px; margin: 0; font-weight: 600; }
  nav a { color: #58a6ff; margin-right: 16px; text-decoration: none; cursor: pointer; }
  nav a.active { color: #f0f6fc; border-bottom: 2px solid #58a6ff; padding-bottom: 8px; }
  main { padding: 20px; max-width: 1400px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 6px;
          padding: 16px; margin-bottom: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 14px; font-weight: 600;
             text-transform: uppercase; letter-spacing: 0.05em; color: #7d8590; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 6px 12px; border-bottom: 1px solid #21262d; }
  th { color: #7d8590; font-weight: 500; font-size: 11px; text-transform: uppercase; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr:hover td { background: #1f242c; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 12px;
          background: #21262d; color: #c9d1d9; font-size: 11px; }
  .pill.ok { background: #033a16; color: #3fb950; }
  .pill.fail { background: #3a0a0a; color: #f85149; }
  pre { background: #0d1117; padding: 12px; border-radius: 4px; overflow: auto;
        max-height: 400px; font-size: 12px; }
  .muted { color: #7d8590; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 12px; }
  .stat { padding: 12px; background: #0d1117; border-radius: 4px; }
  .stat .v { font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .stat .l { font-size: 11px; color: #7d8590; text-transform: uppercase; }
</style>
</head>
<body>
<header>
  <h1>argus</h1>
  <nav>
    <a class="active" data-tab="overview">Overview</a>
    <a data-tab="cache">Cache</a>
    <a data-tab="patterns">Patterns</a>
    <a data-tab="history">History</a>
    <a data-tab="autotune">Autotune</a>
  </nav>
  <span class="muted" id="ts" style="margin-left:auto"></span>
</header>
<main>
  <div id="tab-overview"></div>
  <div id="tab-cache" hidden></div>
  <div id="tab-patterns" hidden></div>
  <div id="tab-history" hidden></div>
  <div id="tab-autotune" hidden></div>
</main>

<script>
const $ = s => document.querySelector(s);
const fmt = v => v == null ? "—" : v;

async function api(p) { return await (await fetch("/api/" + p)).json(); }

async function refresh() {
  $("#ts").textContent = new Date().toLocaleTimeString();
  const [m, c, p, h] = await Promise.all([
    api("metrics"), api("cache"), api("patterns"), api("history?limit=20"),
  ]);

  // overview
  const ok_calls = Object.values(m).reduce((a, x) => a + (x.ok || 0), 0);
  const err_calls = Object.values(m).reduce((a, x) => a + (x.err || 0), 0);
  const total = ok_calls + err_calls;
  $("#tab-overview").innerHTML = `
    <div class="card"><h2>Health</h2>
    <div class="grid">
      <div class="stat"><div class="v">${total}</div><div class="l">total tool calls</div></div>
      <div class="stat"><div class="v">${total ? ((ok_calls/total)*100).toFixed(0) : 0}%</div><div class="l">success rate</div></div>
      <div class="stat"><div class="v">${c.length}</div><div class="l">learned selectors</div></div>
      <div class="stat"><div class="v">${p.length}</div><div class="l">task patterns</div></div>
    </div></div>
    <div class="card"><h2>Top tools by latency</h2>
    <table><tr><th>tool</th><th class="num">calls</th><th class="num">success</th><th class="num">p50ms</th><th class="num">p95ms</th></tr>
    ${Object.entries(m).sort((a,b)=>b[1].calls-a[1].calls).slice(0,12)
      .map(([k,v])=>`<tr><td>${k}</td><td class="num">${v.calls}</td><td class="num">${(v.success_rate*100).toFixed(0)}%</td><td class="num">${v.p50_ms}</td><td class="num">${v.p95_ms}</td></tr>`).join("")}
    </table></div>`;

  // cache
  $("#tab-cache").innerHTML = `<div class="card"><h2>Learned selectors</h2>
    <table><tr><th>scope</th><th>target</th><th>source</th><th>selector</th><th class="num">succ</th><th class="num">fail</th></tr>
    ${c.slice(0,200).map(r=>`<tr><td>${r.scope}</td><td>${r.target_norm}</td>
      <td><span class="pill">${r.source}</span></td>
      <td><code>${(r.selector||"").slice(0,80)}</code></td>
      <td class="num">${r.successes}</td><td class="num">${r.failures}</td></tr>`).join("")}
    </table></div>`;

  // patterns
  $("#tab-patterns").innerHTML = `<div class="card"><h2>Task patterns</h2>
    <table><tr><th>scope</th><th>intent</th><th class="num">v</th><th class="num">steps</th><th>ops</th><th class="num">succ</th></tr>
    ${p.map(r=>`<tr><td>${r.scope}</td><td>${r.intent}</td><td class="num">${r.version}</td>
      <td class="num">${r.step_count}</td><td class="muted">${(r.step_ops||[]).join(" → ")}</td>
      <td class="num">${r.successes}</td></tr>`).join("")}
    </table></div>`;

  // history
  $("#tab-history").innerHTML = `<div class="card"><h2>Recent intent log</h2>
    <table><tr><th>time</th><th>intent</th><th>scope</th><th>target</th><th>source</th><th>outcome</th><th class="num">ms</th></tr>
    ${h.map(r=>`<tr><td class="muted">${new Date((r.ts||0)*1000).toLocaleTimeString()}</td>
      <td>${r.intent}</td><td>${r.scope||""}</td><td>${(r.target||"").slice(0,40)}</td>
      <td><span class="pill">${r.source||""}</span></td>
      <td><span class="pill ${r.outcome==="ok"?"ok":"fail"}">${r.outcome}</span></td>
      <td class="num">${r.ms||0}</td></tr>`).join("")}
    </table></div>`;
}

async function loadAutotune() {
  const r = await api("autotune");
  $("#tab-autotune").innerHTML = `<div class="card"><h2>Autotune report</h2>
    <pre>${JSON.stringify(r, null, 2)}</pre></div>`;
}

document.querySelectorAll("nav a").forEach(a => a.onclick = () => {
  document.querySelectorAll("nav a").forEach(x => x.classList.remove("active"));
  a.classList.add("active");
  document.querySelectorAll("main > div").forEach(x => x.hidden = true);
  $("#tab-" + a.dataset.tab).hidden = false;
  if (a.dataset.tab === "autotune") loadAutotune();
});

refresh();
setInterval(refresh, 4000);
</script>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass  # silence

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._send(200, "text/html; charset=utf-8", _INDEX_HTML)
        if url.path == "/api/metrics":
            return self._send(200, "application/json", json.dumps(intent.metrics()))
        if url.path == "/api/cache":
            return self._send(200, "application/json",
                              json.dumps(intent.cache_view(limit=500)))
        if url.path == "/api/patterns":
            return self._send(200, "application/json",
                              json.dumps(patterns.list_patterns(limit=200)))
        if url.path == "/api/history":
            qs = parse_qs(url.query)
            return self._send(200, "application/json",
                              json.dumps(intent.history(
                                  limit=int(qs.get("limit", [50])[0]))))
        if url.path == "/api/autotune":
            return self._send(200, "application/json",
                              json.dumps(autotune.run_full(dry_run=True)))
        return self._send(404, "text/plain", "not found")


class _ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start(port: int = 9999) -> dict:
    if _STATE["server"]:
        return {"ok": True, "already_running": True, "port": _STATE["port"]}
    srv = _ThreadedServer(("127.0.0.1", port), _Handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True,
                          name="argus-dashboard")
    th.start()
    _STATE["server"] = srv
    _STATE["thread"] = th
    _STATE["port"] = port
    return {"ok": True, "url": f"http://127.0.0.1:{port}/", "port": port}


def stop() -> dict:
    s = _STATE["server"]
    if not s:
        return {"ok": True, "running": False}
    try: s.shutdown()
    except Exception: pass
    try: s.server_close()
    except Exception: pass
    _STATE["server"] = None
    _STATE["thread"] = None
    return {"ok": True, "stopped": True}


def status() -> dict:
    if _STATE["server"]:
        return {"running": True, "port": _STATE["port"],
                "url": f"http://127.0.0.1:{_STATE['port']}/"}
    return {"running": False}
