"""argus_search_web — DuckDuckGo HTML scrape (no API key)."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote_plus, unquote
from urllib.request import Request, urlopen


def search(query: str, *, max_results: int = 10) -> dict:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36",
            "Accept": "text/html",
        })
        with urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Parse DDG HTML — results have class result__a (link) + result__snippet
    results = []
    for m in re.finditer(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        html, re.DOTALL,
    ):
        href = unquote(m.group(1)).split("uddg=")[-1].split("&")[0] if "uddg=" in m.group(1) else m.group(1)
        href = unquote(href)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        results.append({"url": href, "title": title, "snippet": snippet})
        if len(results) >= max_results:
            break

    return {"ok": True, "query": query, "count": len(results), "results": results}
