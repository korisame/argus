"""argus_quickstart — interactive try-it-now for new agents.

Returns a curated 'first 5 minutes' of argus: 5 example invocations with
expected output shape. Agents that don't yet have argus muscle memory can
read this once and learn the most common patterns.
"""
from __future__ import annotations


EXAMPLES = [
    {
        "step": 1,
        "title": "Health check first",
        "tool": "argus_doctor",
        "args": {},
        "expected_keys": ["status", "summary", "deps", "surface"],
        "explanation": "Always call argus_doctor first. status:READY means everything is wired."
    },
    {
        "step": 2,
        "title": "Where am I?",
        "tool": "argus_surface",
        "args": {},
        "expected_keys": ["surface", "app", "scope"],
        "explanation": "surface ∈ {browser, webview, native}. scope is your cache key."
    },
    {
        "step": 3,
        "title": "Find a target without clicking",
        "tool": "argus_find",
        "args": {"target": "Send"},
        "expected_keys": ["x", "y", "source", "confidence", "scope", "attempts"],
        "explanation": "source tells you which layer resolved (cache, ax, ocr, cdp, vision)."
    },
    {
        "step": 4,
        "title": "Click + verify in one shot",
        "tool": "argus_click",
        "args": {"target": "the gear icon top right"},
        "expected_keys": ["clicked", "x", "y", "verified", "source"],
        "explanation": "verified.ok tells you if the click had a visible effect. Updates the learned cache."
    },
    {
        "step": 5,
        "title": "Read structured data from the screen",
        "tool": "argus_extract",
        "args": {"schema": {"price": "the total amount", "date": "the order date"}},
        "expected_keys": ["price", "date", "_meta"],
        "explanation": "OCR-first then Moondream Q&A. Use this to scrape any UI without an API."
    },
]


WORKFLOWS = [
    {
        "name": "Record + replay a workflow",
        "steps": [
            'argus_pattern action=record_begin name="login" scope="web:foo.com" intent_label="sign in"',
            '... do the login by hand (each click/type/key auto-records) ...',
            'argus_pattern action=record_end name="login"',
            '# next time:',
            'argus_replay scope="web:foo.com" intent_label="sign in"',
        ],
    },
    {
        "name": "Multi-app workflow",
        "steps": [
            'argus_workspace tasks=[',
            '  {"app": "Safari", "tool": "argus_extract", "args": {"schema": {"title": "page title"}}},',
            '  {"app": "Notes",  "tool": "argus_notes", "args": {"title": "{{step_0.title}}", "body": "from web"}}',
            ']',
        ],
    },
    {
        "name": "Composable pipeline (one MCP call, multi-step)",
        "steps": [
            'argus_chain steps=[',
            '  {"tool": "argus_window", "args": {"app": "Safari"}, "as": "shot"},',
            '  {"tool": "argus_extract", "args": {"schema": {"price": "..."}}}',
            ']',
        ],
    },
]


def quickstart() -> dict:
    return {
        "version": "0.10+",
        "first_call_recommended": "argus_doctor",
        "examples": EXAMPLES,
        "common_workflows": WORKFLOWS,
        "tips": [
            "Use argus_paste (not argus_type) for text > 80 chars — clipboard is 100x faster.",
            "After a non-trivial click, check verified.ok. If false, the click landed but nothing visibly changed.",
            "argus_session save name=<jar> after a manual login → reuse forever via argus_session load.",
            "Dont have a Moondream key? Cascade still works for literal-text targets via OCR / AX. Vision-only targets ('the gear icon top right') need a key.",
            "On Mac with argus, you can disable Anthropic Computer Use entirely. argus_cu_route routes any incoming CU calls.",
        ],
    }
