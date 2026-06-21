"""Web search with a provider fallback chain:
primary Tavily -> Firecrawl -> Google (Custom Search) -> DuckDuckGo (no-key net)."""
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

import requests

from core.config import (TAVILY_API_KEY, FIRECRAWL_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID,
                    RESULTS_PER_QUERY, REQ_TIMEOUT, RAW_CONTENT_CHARS, SEARCH_WORKERS)


def tavily_search(query: str, max_results: int = RESULTS_PER_QUERY,
                  depth: str = "basic", raw: bool = False,
                  include_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        raise RuntimeError("Missing TAVILY_API_KEY")
    payload = {
        "api_key": TAVILY_API_KEY, "query": query, "search_depth": depth,
        "max_results": max_results, "include_answer": False,
        "include_raw_content": raw,
    }
    if include_domains:
        payload["include_domains"] = include_domains  # restrict to these sources
    r = requests.post("https://api.tavily.com/search", json=payload, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    out = []
    for it in r.json().get("results", []):
        raw_txt = (it.get("raw_content") or "")[:RAW_CONTENT_CHARS]
        out.append({"title": it.get("title", ""), "url": it.get("url", ""),
                    "snippet": it.get("content", ""), "raw": raw_txt})
    return out


def firecrawl_search(query: str, max_results: int = RESULTS_PER_QUERY,
                     raw: bool = False,
                     include_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Search fallback #1 via Firecrawl's /v1/search endpoint."""
    if not FIRECRAWL_API_KEY:
        raise RuntimeError("Missing FIRECRAWL_API_KEY")
    q = query
    if include_domains:
        q = f"{query} (" + " OR ".join(f"site:{d}" for d in include_domains) + ")"
    payload: Dict[str, Any] = {"query": q, "limit": max_results}
    if raw:
        payload["scrapeOptions"] = {"formats": ["markdown"]}
    r = requests.post("https://api.firecrawl.dev/v1/search", json=payload,
                      headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}"},
                      timeout=REQ_TIMEOUT)
    r.raise_for_status()
    out = []
    for it in (r.json().get("data") or []):
        raw_txt = (it.get("markdown") or "")[:RAW_CONTENT_CHARS] if raw else ""
        out.append({"title": it.get("title", ""), "url": it.get("url", ""),
                    "snippet": it.get("description", ""), "raw": raw_txt})
    return out


def google_search(query: str, max_results: int = RESULTS_PER_QUERY,
                  raw: bool = False,
                  include_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Search fallback #2 via Google Programmable Search (Custom Search JSON API).
    Requires GOOGLE_API_KEY + GOOGLE_CSE_ID. `raw` is ignored (snippets only)."""
    if not (GOOGLE_API_KEY and GOOGLE_CSE_ID):
        raise RuntimeError("Missing GOOGLE_API_KEY / GOOGLE_CSE_ID")
    q = query
    if include_domains:
        q = f"{query} (" + " OR ".join(f"site:{d}" for d in include_domains) + ")"
    params = {"key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": q,
              "num": max(1, min(int(max_results), 10))}
    r = requests.get("https://www.googleapis.com/customsearch/v1", params=params,
                     timeout=REQ_TIMEOUT)
    r.raise_for_status()
    out = []
    for it in (r.json().get("items") or []):
        out.append({"title": it.get("title", ""), "url": it.get("link", ""),
                    "snippet": it.get("snippet", ""), "raw": ""})
    return out


def duckduckgo_search(query: str, max_results: int = RESULTS_PER_QUERY,
                      raw: bool = False,
                      include_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Fallback web search via DuckDuckGo (no API key). Mirrors tavily_search's
    output shape. `raw` is ignored - DDG returns snippets only."""
    try:
        from ddgs import DDGS                       # current package name
    except ImportError:
        try:
            from duckduckgo_search import DDGS      # legacy package name
        except ImportError as e:
            raise RuntimeError("DuckDuckGo package missing (pip install ddgs)") from e
    q = query
    if include_domains:
        q = f"{query} (" + " OR ".join(f"site:{d}" for d in include_domains) + ")"
    out = []
    with DDGS() as ddgs:
        for it in (ddgs.text(q, max_results=max_results) or []):
            out.append({"title": it.get("title", ""), "url": it.get("href", ""),
                        "snippet": it.get("body", ""), "raw": ""})
    return out


def search_with_fallback(query: str, max_results: int = RESULTS_PER_QUERY,
                         depth: str = "basic", raw: bool = False,
                         include_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Try each provider in order, returning the first non-empty result set.
    Chain: Tavily (primary) -> Firecrawl -> Google -> DuckDuckGo (no-key net)."""
    providers = [
        ("Tavily", lambda: tavily_search(query, max_results=max_results, depth=depth,
                                         raw=raw, include_domains=include_domains)),
        ("Firecrawl", lambda: firecrawl_search(query, max_results=max_results, raw=raw,
                                               include_domains=include_domains)),
        ("Google", lambda: google_search(query, max_results=max_results, raw=raw,
                                         include_domains=include_domains)),
        ("DuckDuckGo", lambda: duckduckgo_search(query, max_results=max_results, raw=raw,
                                                 include_domains=include_domains)),
    ]
    for i, (name, fn) in enumerate(providers):
        try:
            res = fn()
            if res:
                if i:
                    print(f"        \u21b3 {name}: {len(res)} result(s)")
                return res
            print(f"        \u21b3 {name} returned 0 results - trying next provider")
        except Exception as e:
            print(f"        \u21b3 {name} unavailable ({str(e)[:55]}) - trying next provider")
    return []


class SourceLedger:
    def __init__(self, official: bool = False):
        self.sources: List[Dict[str, Any]] = []
        self.seen = set()
        self.official_default = official

    def add(self, title, url, snippet="", raw="", official=None):
        if not url:
            return
        u = url.strip()
        if u in self.seen:
            return
        self.seen.add(u)
        try:
            domain = urlparse(u).netloc.replace("www.", "")
        except Exception:
            domain = ""
        is_off = self.official_default if official is None else official
        sid = str(len(self.sources) + 1)
        self.sources.append({"id": sid, "title": title or "", "url": u,
                             "domain": domain, "snippet": snippet or "",
                             "raw": raw or "", "official": is_off})
        tag = "OFFICIAL " if is_off else ""
        print(f"        🔗 [{sid}] {tag}{domain}  {u}")
        return sid


def search_parallel(queries: List[str], official: bool = False,
                    depth: str = "basic", raw: bool = False,
                    include_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    ledger = SourceLedger(official=official)

    def _one(q):
        try:
            tag = f" [{include_domains[0]}…]" if include_domains else ""
            print(f"        search{tag}: {q}")
            return search_with_fallback(q, depth=depth, raw=raw, include_domains=include_domains)
        except Exception as e:
            print(f"        search error: {str(e)[:100]}")
            return []

    with ThreadPoolExecutor(max_workers=SEARCH_WORKERS) as ex:
        for rows in ex.map(_one, queries):
            for r in rows:
                ledger.add(r["title"], r["url"], r["snippet"], r.get("raw", ""))
    return ledger.sources
