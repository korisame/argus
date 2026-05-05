"""Selector cache + TTL + autotune behaviour."""
import os
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


def setup_module(_):
    # isolate state
    os.environ["ARGUS_PRIME_HOME"] = tempfile.mkdtemp(prefix="argus-test-")


def test_record_and_lookup():
    from core import intent
    intent.cache_record_success("native:com.test", "Send",
                                 source="ax", selector="AX[role=Button;text='Send']",
                                 confidence=0.95)
    hit = intent.cache_lookup("native:com.test", "Send")
    assert hit is not None
    assert hit["source"] == "ax"
    assert hit["successes"] == 1
    assert hit["from_cache"] is True


def test_failure_poisoning():
    from core import intent
    intent.cache_record_success("native:com.test2", "Login",
                                 source="ocr", selector="OCR[text='Login']",
                                 confidence=0.5)
    for _ in range(5):
        intent.cache_record_failure("native:com.test2", "Login")
    hit = intent.cache_lookup("native:com.test2", "Login")
    assert hit is None  # poisoned


def test_autotune_promotes():
    from core import intent, autotune
    for _ in range(20):
        intent.cache_record_success("web:example.com", "Sign in",
                                     source="cdp_raw", selector="DOM[btn]",
                                     confidence=1.0)
    eligible = autotune._eligible_entries()
    assert any(e["scope"] == "web:example.com" and e["target_norm"] == "sign in"
               for e in eligible)
