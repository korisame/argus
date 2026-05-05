"""Async runtime for the MCP server.

Conservative design: the server reads stdin and dispatches in an asyncio
event loop. Tool handlers stay synchronous (we don't rewrite the world)
but run in a thread-pool executor so that:
  - long-running tool calls (vision, screenshot, REPL drain) don't block
    other concurrent calls
  - new requests arriving on stdin are processed while a previous tool is
    still working

Caveats:
  - the legacy sync server.main() is still available for tests
  - asyncio runtime is enabled when ARGUS_ASYNC=1 (default true in v0.5)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import sys
import time
import traceback
from typing import Callable

DEFAULT_WORKERS = 8


async def _read_lines(stream) -> "asyncio.AsyncIterator[str]":
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    transport = await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), stream)
    try:
        while True:
            line = await reader.readline()
            if not line:
                return
            yield line.decode("utf-8", errors="replace").rstrip("\n")
    finally:
        try: transport.close()
        except Exception: pass


def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, default=str) + "\n")
    sys.stdout.flush()


async def serve(handlers: dict[str, Callable], tools: list, *,
                proto: str, name: str, version: str,
                metrics_record: Callable[[str, bool, float], None] | None = None,
                workers: int = DEFAULT_WORKERS) -> None:
    """Run the MCP server in async mode."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers,
                                                  thread_name_prefix="argus-tool")
    loop = asyncio.get_running_loop()

    async def handle_one(req: dict) -> None:
        method = req.get("method")
        rid = req.get("id")
        params = req.get("params") or {}
        try:
            if method == "initialize":
                _send({"jsonrpc": "2.0", "id": rid, "result": {
                    "protocolVersion": proto,
                    "serverInfo": {"name": name, "version": version},
                    "capabilities": {"tools": {}}}})
            elif method == "notifications/initialized":
                pass
            elif method == "tools/list":
                _send({"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}})
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments") or {}
                fn = handlers.get(tool_name)
                if not fn:
                    _send({"jsonrpc": "2.0", "id": rid,
                           "error": {"code": -32601,
                                     "message": f"unknown tool: {tool_name}"}})
                    return
                t0 = time.monotonic()
                try:
                    result = await loop.run_in_executor(pool, lambda: fn(arguments))
                    if metrics_record:
                        metrics_record(tool_name, True, (time.monotonic() - t0) * 1000)
                    _send({"jsonrpc": "2.0", "id": rid,
                           "result": {"content": result, "isError": False}})
                except Exception as e:
                    if metrics_record:
                        metrics_record(tool_name, False, (time.monotonic() - t0) * 1000)
                    _send({"jsonrpc": "2.0", "id": rid,
                           "result": {"content": [{"type": "text",
                                                    "text": f"error: {e}\n{traceback.format_exc()}"}],
                                       "isError": True}})
            elif method == "ping":
                _send({"jsonrpc": "2.0", "id": rid, "result": {}})
            elif method.startswith("notifications/"):
                pass
            else:
                _send({"jsonrpc": "2.0", "id": rid,
                       "error": {"code": -32601, "message": f"method not implemented: {method}"}})
        except Exception as e:
            _send({"jsonrpc": "2.0", "id": rid,
                   "error": {"code": -32603, "message": f"internal: {e}"}})

    async for line in _read_lines(sys.stdin):
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            _send({"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": f"parse: {e}"}})
            continue
        # fire and forget — concurrent dispatch
        asyncio.create_task(handle_one(req))


def run(handlers, tools, *, proto, name, version, metrics_record=None,
        workers: int = DEFAULT_WORKERS) -> None:
    asyncio.run(serve(handlers, tools, proto=proto, name=name, version=version,
                      metrics_record=metrics_record, workers=workers))
