"""All Python modules import without (non-platform) dependencies present."""
import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "mcp_server"))


def test_core_imports():
    for m in ("core.intent", "core.vision", "core.router", "core.cascade",
              "core.verify", "core.session", "core.repl", "core.autotune",
              "core.screen", "core.patterns", "core.policy", "core.prewarm",
              "core.dashboard", "core.wizard", "core.uninstall",
              "core.chrome_admin", "core.registry", "core.asyncio_runtime"):
        importlib.import_module(m)


def test_adapters_imports():
    for m in ("adapters.ax", "adapters.ocr", "adapters.cdp",
              "adapters.cdp_raw", "adapters.cgevent"):
        importlib.import_module(m)


def test_server_imports():
    importlib.import_module("server")
