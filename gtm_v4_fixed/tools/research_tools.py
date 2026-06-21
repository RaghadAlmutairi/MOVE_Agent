# -*- coding: utf-8 -*-
"""Research tools registry.

All four research tools are defined here and exported via TOOLS dict.
The research agent imports TOOLS from this module; nothing else should
define or duplicate tool logic.

Tools
-----
competitive_landscape_tool  - DISCOVER → VERIFY competitor pipeline
market_analysis_tool        - market size, trends, analyst-firm sources
customer_intelligence_tool  - persona context + real voice-of-customer
internal_knowledge_tool     - private RAG over org documents
"""
from typing import Any, Dict, List

from core.config import tool
from utils.search import search_parallel
from utils.rag import rag_sources
from utils.verify import build_discovery_queries, retag_official, dedupe_candidates
from utils.discovery import extract_competitor_candidates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_market(market: str) -> str:
    """Strip slash-separated qualifiers that pollute search queries.

    LLM-generated market labels like 'AI foundation models / LLM platforms'
    produce off-topic CAGR junk when passed verbatim to a search engine.
    Keep only the first clause.
    """
    m = (market or "").split("/")[0].split("(")[0].strip()
    return m or market


def _stamp(sources: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
    """Tag every source dict with the given role string (mutates in-place)."""
    for s in sources:
        s["role"] = role
    return sources


# Trusted social/community/review/blog domains where real customer voice lives.
REVIEW_DOMAINS = [
    "reddit.com", "linkedin.com", "x.com", "twitter.com",
    "medium.com", "substack.com", "news.ycombinator.com", "quora.com",
    "g2.com", "trustpilot.com", "capterra.com", "trustradius.com",
    "producthunt.com", "play.google.com", "apps.apple.com",
]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def competitive_landscape_tool(
    subject_entity: str = "",
    market: str = "",
    geography: str = "global",
    subject_type: str = "",
    industry: str = "",
) -> Dict[str, Any]:
    """Competitive landscape via DISCOVER → VERIFY.

    Input
    -----
    subject_entity : company / product being researched
    market         : broad market label (e.g. "CRM software")
    geography      : target geography (default "global")
    subject_type   : "COMPANY" | "PRODUCT" | etc.
    industry       : industry label (falls back to market)

    Output
    ------
    {
        "tool": "competitive_landscape_tool",
        "sources": [...],                 # all web sources gathered
        "competitor_candidates": [...]    # extracted + deduplicated candidates
    }
    """
    print("\n      [tool] competitive_landscape_tool (discover -> verify)")
    subj = subject_entity.strip()
    mk   = _clean_market(market)
    ind  = _clean_market(industry) or mk
    all_sources: List[Dict[str, Any]] = []

    # 1) Subject official evidence – verified by domain match, not query tag.
    if subj:
        print("        - subject official discovery")
        subj_queries = [
            f"{subj} official website",
            f"{subj} official pricing plans",
            f"{subj} products official site",
            f"{subj} official enterprise business",
        ]
        subj_srcs = search_parallel(subj_queries, official=False, depth="advanced", raw=True)
        retag_official(
            subj_srcs, subj,
            official_role="subject_official",
            other_role="subject_discovery",
        )
        all_sources += subj_srcs

    # 2) Competitor discovery (third-party allowed; explicitly NOT official).
    print("        - competitor candidate discovery")
    disc_queries = build_discovery_queries(subj, mk, ind, geography, subject_type)
    disc_srcs = search_parallel(disc_queries, official=False, depth="advanced", raw=True)
    for s in disc_srcs:
        s["official"] = False
        s["role"] = "competitor_discovery"
    all_sources += disc_srcs

    # 3) Extract + dedupe candidate competitors from discovery evidence.
    candidates = dedupe_candidates(
        extract_competitor_candidates(subj, subject_type, ind, mk, geography, disc_srcs)
    )
    print(
        f"        - candidates: "
        f"{', '.join(c.get('name', '') for c in candidates[:8]) or '(none)'}"
    )

    # 4) Verify each candidate against its own official site / pricing / products.
    print("        - official verification per candidate")
    for c in candidates[:8]:
        name = c.get("name", "")
        if not name:
            continue
        dom = c.get("likely_domain", "")
        ver_srcs = search_parallel(
            [f"{name} official website", f"{name} pricing", f"{name} products"],
            official=False,
            depth="advanced",
            raw=True,
            include_domains=[dom] if dom else None,
        )
        retag_official(
            ver_srcs, name,
            expected_domain=dom,
            official_role="competitor_official",
            other_role="competitor_third_party",
        )
        all_sources += ver_srcs

    return {
        "tool": "competitive_landscape_tool",
        "sources": all_sources,
        "competitor_candidates": candidates,
    }


@tool
def market_analysis_tool(
    subject_entity: str = "",
    market: str = "",
    geography: str = "global",
) -> Dict[str, Any]:
    """Market size, trends, and analyst-firm intelligence.

    Input
    -----
    subject_entity : company / product being researched (optional)
    market         : market segment label
    geography      : target geography

    Output
    ------
    {"tool": "market_analysis_tool", "sources": [...]}
    """
    print("\n      [tool] market_analysis_tool")
    subj = subject_entity.strip()
    mk   = _clean_market(market)

    standard_queries = [
        f"{subj or mk} market size CAGR forecast {geography}",
        f"{mk} industry trends {geography}",
        f"{mk} demand drivers and risks",
    ]
    analyst_queries = [
        f"{subj or mk} Gartner Magic Quadrant {geography}",
        f"{subj or mk} Forrester Wave report",
        f"{mk} IDC MarketScape analysis",
        f"{mk} Statista market size forecast",
        f"{mk} McKinsey Deloitte industry report",
    ]
    srcs = search_parallel(standard_queries + analyst_queries)
    return {"tool": "market_analysis_tool", "sources": _stamp(srcs, "market")}


@tool
def customer_intelligence_tool(
    subject_entity: str = "",
    market: str = "",
    geography: str = "global",
) -> Dict[str, Any]:
    """Customer segments, personas, pain points, and real voice-of-customer.

    Gathers persona context alongside actual customer feedback from Reddit,
    LinkedIn, Medium, review platforms, and the subject's own case studies.

    Input
    -----
    subject_entity : company / product being researched (optional)
    market         : market segment label
    geography      : target geography

    Output
    ------
    {"tool": "customer_intelligence_tool", "sources": [...]}
    """
    print("\n      [tool] customer_intelligence_tool")
    subj = subject_entity.strip()
    mk   = _clean_market(market)

    # (a) Generic persona / pain-point / channel context.
    base_queries = [
        f"{subj or mk} customer pain points",
        f"{mk} buyer segments personas",
        f"{mk} which social channels do buyers use to research and buy",
        f"{mk} adoption barriers objections",
    ]
    srcs = search_parallel(base_queries)

    # (b) Real feedback from social / community / review / blog sources.
    if subj:
        feedback_queries = [
            f"{subj} reviews complaints feedback reddit",
            f"{subj} user experience problems frustrations",
            f"{subj} pros and cons opinions discussion",
        ]
    else:
        feedback_queries = [
            f"{mk} product reviews complaints feedback",
            f"{mk} user frustrations problems discussion",
        ]
    fb_srcs = search_parallel(
        feedback_queries,
        depth="advanced",
        raw=True,
        include_domains=REVIEW_DOMAINS,
    )

    # (c) Official testimonials / case studies (named subject only).
    official_voc: List[Dict[str, Any]] = []
    if subj:
        official_voc = search_parallel(
            [f"{subj} customer testimonials case studies reviews"],
            depth="advanced",
            raw=True,
        )

    all_srcs = srcs + fb_srcs + official_voc
    print(
        f"        ↳ feedback: {len(fb_srcs)} social/review + "
        f"{len(official_voc)} official-site sources"
    )
    return {"tool": "customer_intelligence_tool", "sources": _stamp(all_srcs, "customer")}


@tool
def internal_knowledge_tool(
    subject_entity: str = "",
    market: str = "",
    geography: str = "global",
) -> Dict[str, Any]:
    """Internal RAG over the organisation's private document collection.

    Retrieves from case studies, decks, and reports for known internal
    entities (e.g. WeCloudData, BeamData). Falls back to an empty source
    list when no documents or RAG dependencies are available.

    Input
    -----
    subject_entity : internal entity name (e.g. "WeCloudData")
    market         : market context for relevance filtering
    geography      : not used by RAG; accepted for interface consistency

    Output
    ------
    {"tool": "internal_knowledge_tool", "sources": [...]}
    """
    print("\n      [tool] internal_knowledge_tool (RAG over internal docs)")
    srcs = rag_sources(subject_entity, market)
    print(f"        internal sources: {len(srcs)}")
    return {"tool": "internal_knowledge_tool", "sources": _stamp(srcs, "internal")}


# ---------------------------------------------------------------------------
# Registry – single authoritative mapping used by the research agent.
# ---------------------------------------------------------------------------

TOOLS: Dict[str, Any] = {
    "competitive_landscape_tool": competitive_landscape_tool,
    "market_analysis_tool":       market_analysis_tool,
    "customer_intelligence_tool": customer_intelligence_tool,
    "internal_knowledge_tool":    internal_knowledge_tool,
}
