import os, sys, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


def test_destructive_verb_detected():
    from core import policy
    assert policy.is_destructive("Confirm payment now")
    assert policy.is_destructive("Elimina account")
    assert not policy.is_destructive("Cancel")


def test_app_blocklist_glob():
    from core import policy
    ok, _ = policy.app_allowed("native:com.agilebits.onepassword7")
    assert ok is False
    ok, _ = policy.app_allowed("native:com.apple.finder")
    assert ok is True
