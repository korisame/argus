"""argus_help — searchable tool catalog for runtime discovery.

When an agent doesn't know which tool to use, this surfaces relevant
options grouped by category, with examples.
"""
from __future__ import annotations


CATEGORIES = {
    "click_and_type":   ["argus_click", "argus_smart_click", "argus_type", "argus_paste",
                          "argus_send_keys", "argus_key", "argus_drag"],
    "see_and_capture":  ["argus_see", "argus_window", "argus_window_list",
                          "argus_diff_screens", "argus_screenshot_history"],
    "find_target":      ["argus_find", "argus_find_all", "argus_text_search",
                          "argus_dom_query", "argus_wait_for"],
    "browser":          ["argus_browser", "argus_dom_query", "argus_session",
                          "argus_secure_session", "argus_cookies", "argus_localstorage",
                          "argus_emulate", "argus_pdf_export"],
    "extract_and_qa":   ["argus_extract", "argus_ask", "argus_pdf"],
    "automate":         ["argus_pattern", "argus_replay", "argus_workflow",
                          "argus_workflow_template", "argus_macros",
                          "argus_chain", "argus_workspace"],
    "apple_apps":       ["argus_notes", "argus_reminders", "argus_calendar",
                          "argus_calendar_create", "argus_mail", "argus_imessage",
                          "argus_contacts", "argus_clipboard"],
    "system":           ["argus_open_app", "argus_quit_app", "argus_focus",
                          "argus_notify", "argus_speak", "argus_listen",
                          "argus_system", "argus_app_explore"],
    "files_and_data":   ["argus_files", "argus_http", "argus_jq", "argus_sql",
                          "argus_image", "argus_qr", "argus_translate"],
    "devops":           ["argus_git", "argus_repl", "argus_schedule", "argus_archive"],
    "admin":            ["argus_doctor", "argus_setup", "argus_uninstall",
                          "argus_dashboard", "argus_chrome", "argus_skills",
                          "argus_health", "argus_benchmark", "argus_log_rotate",
                          "argus_install_log_rotation"],
    "observability":    ["argus_history", "argus_metrics", "argus_cache",
                          "argus_summary", "argus_observe", "argus_log_search",
                          "argus_export_skills"],
    "safety":           ["argus_policy", "argus_redact", "argus_exec_apple_script",
                          "argus_session_begin", "argus_session_end",
                          "argus_vision_unload"],
    "compatibility":    ["argus_cu_route", "argus_quickstart", "argus_help"],
}


EXAMPLES = {
    "click_and_type": [
        'argus_click target="Send button"',
        'argus_smart_click target="Submit" alternates=["Save","Confirm"]',
        'argus_paste text="long text here"',
    ],
    "find_target": [
        'argus_find target="the gear icon top right"',
        'argus_text_search query="error" max_windows=5',
    ],
    "browser": [
        'argus_browser action=navigate url="https://github.com"',
        'argus_session save name=github',
        'argus_pdf_export out_path=/tmp/page.pdf',
    ],
    "extract_and_qa": [
        'argus_extract schema={"price":"total","date":"order date"}',
        'argus_ask question="Is the build green?"',
    ],
    "automate": [
        'argus_pattern action=record_begin name=login scope=web:foo intent_label="sign in"',
        'argus_replay scope=web:foo intent_label="sign in"',
        'argus_workflow_template name=post_to_notion',
    ],
}


def help(topic: str | None = None) -> dict:
    if not topic:
        return {
            "categories": {k: len(v) for k, v in CATEGORIES.items()},
            "tip": "argus_help topic='browser' to see browser-related tools",
            "topics": list(CATEGORIES.keys()),
        }
    topic_l = topic.lower()
    if topic_l in CATEGORIES:
        return {
            "topic": topic_l,
            "tools": CATEGORIES[topic_l],
            "examples": EXAMPLES.get(topic_l, []),
        }
    # Fuzzy match against tool names
    hits = []
    for cat, tools in CATEGORIES.items():
        for t in tools:
            if topic_l in t.lower():
                hits.append({"tool": t, "category": cat})
    if hits:
        return {"query": topic, "matches": hits}
    return {"error": f"no match for {topic!r}",
            "topics": list(CATEGORIES.keys())}
