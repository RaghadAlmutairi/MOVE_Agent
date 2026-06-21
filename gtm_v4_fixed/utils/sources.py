# -*- coding: utf-8 -*-
"""Source merging and compaction utilities.

These helpers are consumed by both the research agent (for synthesis) and
by utils/discovery.py (for candidate extraction).  Keeping them here — rather
than inside agents/research_agent.py — breaks the otherwise circular import:

    research_agent → discovery → research_agent   (circular)
    research_agent → utils/sources ← discovery    (clean)
"""
from typing import Any, Dict, List

from core.config import MAX_SOURCES_FOR_LLM, SOURCE_CHARS


# ---------------------------------------------------------------------------
# Role priority table (lower = more authoritative)
# ---------------------------------------------------------------------------

_ROLE_PRIORITY: Dict[str, int] = {
    "subject_official":       1,
    "competitor_official":    2,
    "internal":               2,
    "analyst_report":         3,
    "market":                 4,
    "market_research":        4,
    "competitor_discovery":   5,
    "customer":               6,
    "customer_feedback":      6,
    "competitor_third_party": 7,
    "subject_discovery":      7,
    "review_site":            7,
    "social_discussion":      8,
}

_WEAK_ROLES = {"", "competitor_third_party", "subject_discovery", "competitor_discovery"}


# ---------------------------------------------------------------------------
# merge_sources
# ---------------------------------------------------------------------------

def merge_sources(tool_outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate by URL while preserving the strongest metadata across duplicates.

    Rules
    -----
    * official flag : OR  (once official, always official)
    * role          : strongest (most specific) wins
    * candidate metadata : first non-empty value wins
    * raw content   : longest version wins (more context is better)
    """
    merged: List[Dict[str, Any]] = []
    by_url: Dict[str, Dict[str, Any]] = {}

    for out in tool_outputs:
        for s in out.get("sources", []):
            url = s.get("url", "")
            if not url:
                continue
            if url not in by_url:
                s2 = dict(s)
                s2["id"] = str(len(merged) + 1)
                by_url[url] = s2
                merged.append(s2)
            else:
                ex = by_url[url]
                ex["official"] = bool(ex.get("official") or s.get("official"))
                if (
                    ex.get("role", "") in _WEAK_ROLES
                    and s.get("role")
                    and s["role"] not in _WEAK_ROLES
                ):
                    ex["role"] = s["role"]
                for k in ("candidate_entity", "expected_domain"):
                    if s.get(k) and not ex.get(k):
                        ex[k] = s[k]
                if len(s.get("raw", "")) > len(ex.get("raw", "")):
                    ex["raw"] = s["raw"]

    return merged


# ---------------------------------------------------------------------------
# compact_sources
# ---------------------------------------------------------------------------

def compact_sources(
    sources: List[Dict[str, Any]],
    prefer_role: str = "",
    max_per_domain: int = 3,
) -> str:
    """Build a balanced evidence packet for LLM context.

    Prioritises official / role-relevant sources and caps any single domain
    so the subject (or a listicle) cannot dominate the evidence set.
    """
    def _rank(s: Dict[str, Any]) -> float:
        r = float(_ROLE_PRIORITY.get(s.get("role", ""), 9))
        if prefer_role and s.get("role") == prefer_role:
            r = -1.0
        if s.get("official"):
            r -= 0.5
        return r

    selected: List[Dict[str, Any]] = []
    seen_urls: set = set()
    dom_count: Dict[str, int] = {}

    for s in sorted(sources, key=_rank):
        if len(selected) >= MAX_SOURCES_FOR_LLM:
            break
        url = s.get("url", "")
        dom = s.get("domain", "")
        if not url or url in seen_urls or dom_count.get(dom, 0) >= max_per_domain:
            continue
        selected.append(s)
        seen_urls.add(url)
        dom_count[dom] = dom_count.get(dom, 0) + 1

    chunks: List[str] = []
    for s in selected:
        tag  = "OFFICIAL " if s.get("official") else ""
        role = s.get("role", "")
        ent  = s.get("candidate_entity", "")
        body = s.get("raw") or s.get("snippet") or ""
        head = (
            f"[{s['id']}] {tag}{role}{(' ' + ent) if ent else ''} "
            f"| {s['title']} ({s['domain']})"
        )
        chunks.append(f"{head}\n{body}")

    return "\n---\n".join(chunks)[:SOURCE_CHARS]
