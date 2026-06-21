# -*- coding: utf-8 -*-
"""Market-relevance filtering + evidence-quality assessment.

GENERAL by construction: relevance is judged against the market vocabulary
DERIVED FROM THE PLAN (subject + industry + market), so there is nothing
hardcoded to any single market. Off-market sources (e.g. a cloud-warehouse
report retrieved for a bootcamp query) are dropped because they share no
vocabulary with the subject's market.
"""
import re
from typing import List, Dict, Any, Tuple

_STOP = {
    "the", "and", "for", "with", "your", "you", "our", "are", "from", "this",
    "that", "market", "markets", "industry", "global", "services", "service",
    "solutions", "solution", "platform", "platforms", "company", "companies",
    "product", "products", "best", "top", "leading", "comparison", "vendors",
    "vendor", "overview", "report", "analysis", "size", "share", "growth",
}

COMPETITOR_SECTIONS = ("company_competitors", "product_competitors",
                       "alternative_solutions")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _tokens(s: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (s or "").lower())
            if len(t) >= 3 and t not in _STOP]


def market_keywords(plan: Dict[str, Any]) -> set:
    kws = set()
    for f in ("subject_entity", "industry", "market"):
        kws.update(_tokens(plan.get(f, "")))
    return kws


def source_relevance(source: Dict[str, Any], keywords: set, subject_norm: str) -> str:
    text = " ".join([source.get("title", ""), source.get("snippet", ""),
                     (source.get("raw", "") or "")[:1200]]).lower()
    if subject_norm and subject_norm in _norm(text):
        return "DIRECT"
    hits = sum(1 for k in keywords if k in text)
    if hits >= 2:
        return "DIRECT"
    if hits == 1:
        return "ADJACENT"
    return "IRRELEVANT"


def filter_relevant_sources(sources: List[Dict[str, Any]], plan: Dict[str, Any],
                            floor: int = 12) -> Tuple[List[Dict[str, Any]], int]:
    """Drop IRRELEVANT (zero market-vocabulary overlap) sources, but ALWAYS keep
    verified official/subject/competitor sources, and never fall below `floor`.
    Re-assigns contiguous ids so citations stay valid."""
    kws = market_keywords(plan)
    subj = _norm(plan.get("subject_entity", ""))
    if not kws and not subj:
        for i, s in enumerate(sources, 1):
            s["id"] = str(i)
        return sources, 0

    strong, adjacent = [], []   # strong = protected or DIRECT ; adjacent = filler
    for s in sources:
        rel = source_relevance(s, kws, subj)
        s["relevance"] = rel
        protected = (s.get("official")
                     or s.get("role") in ("subject_official", "competitor_official", "internal"))
        if protected:
            s["relevance"] = "DIRECT" if rel == "IRRELEVANT" else rel
            strong.append(s)
        elif rel == "DIRECT":
            strong.append(s)
        elif rel == "ADJACENT":
            adjacent.append(s)
        # IRRELEVANT (zero market-vocabulary overlap) is always dropped

    # Keep all strong (verified/on-market); use weak ADJACENT only to reach the
    # floor, so off-market filler is pruned whenever real evidence is plentiful.
    keep = list(strong)
    if len(keep) < floor and adjacent:
        keep += adjacent[:floor - len(keep)]
    dropped = len(sources) - len(keep)
    for i, s in enumerate(keep, 1):
        s["id"] = str(i)
    return keep, dropped


def score_evidence_quality(sources: List[Dict[str, Any]]) -> Dict[str, int]:
    def role(r):
        return sum(1 for s in sources if s.get("role") == r)
    return {
        "official": sum(1 for s in sources if s.get("official")),
        "subject_official": role("subject_official"),
        "competitor_official": role("competitor_official"),
        "discovery": role("competitor_discovery"),
        "customer": sum(1 for s in sources if s.get("role") in
                        ("customer", "customer_feedback", "review_site", "social_discussion")),
    }


def evidence_assessment(report: Dict[str, Any],
                        sources: List[Dict[str, Any]]) -> Tuple[Dict[str, int], List[str], str]:
    """Return (quality_counts, limitation_notes, confidence_cap). General: any
    report that makes competitor claims without verified competitor-official
    sources is flagged and capped, regardless of subject/market."""
    q = score_evidence_quality(sources)
    has_comp = any(report.get(k) for k in COMPETITOR_SECTIONS)
    notes: List[str] = []

    if has_comp and q["competitor_official"] == 0:
        notes.append("no verified competitor-official sources were retrieved, so "
                     "competitor, pricing and product details are directional and "
                     "should be independently verified")
    if q["official"] == 0:
        notes.append("no official sources were verified; figures are indicative only")
    elif q["official"] <= 1:
        notes.append("only one official source was verified; treat specifics with caution")

    cap = "high"
    if has_comp and q["competitor_official"] == 0:
        cap = "low"
    elif q["official"] <= 1:
        cap = "medium"
    return q, notes, cap
