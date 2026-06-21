# -*- coding: utf-8 -*-
"""RESEARCH AGENT.

Responsibility
--------------
Given a user query + tool-call outputs (web sources), produce a structured
market-research Report.  This agent owns:

  * Deterministic post-processing: business_model derivation, homepage
    backfilling, granularity validation, evidence-quality gating
  * Three parallel LLM calls that synthesise the final Report:
      - analyze_overview    → ReportCore  (exec summary, SWOT, trends, …)
      - analyze_competitors → CompetitorBlock
      - analyze_personas    → PersonaBlock

Source merging / compaction live in utils/sources.py so that utils/discovery.py
can import them without a circular dependency.

Input
-----
query          : str   – the user's original research question
plan           : ToolPlan
sources        : List[Dict]  – raw sources from the research tools
revision_notes : Optional[List[str]]  – feedback from output-guard for re-runs

Output
------
Report (Pydantic model) – fully populated, ready for the orchestrator.
"""
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.config import (
    SYNTH_MODEL, SYNTH_EFFORT, SYNTH_WORKERS,
    map_in_context,
)
from core.llm import parse_llm
from core.prompts import SYNTH_CORE, SYNTH_COMP, SYNTH_PERS
from core.schemas import Report, ReportCore, CompetitorBlock, PersonaBlock, ToolPlan
from utils.sources import compact_sources, merge_sources
from utils.verify import is_non_official_domain, choose_official_homepage


# ---------------------------------------------------------------------------
# Re-export for backwards compatibility (research_graph.py imports these)
# ---------------------------------------------------------------------------

__all__ = [
    "synthesize",
    "apply_derivations",
    "backfill_homepages",
    "merge_sources",   # re-exported from utils.sources
    "compact_sources", # re-exported from utils.sources
]


# ---------------------------------------------------------------------------
# Deterministic post-processing
# ---------------------------------------------------------------------------

def _derive_business_model(c: Dict[str, Any]) -> str:
    if c.get("is_marketplace"):
        return "MARKETPLACE"
    b   = bool(c.get("serves_businesses"))
    con = bool(c.get("serves_consumers"))
    gov = bool(c.get("serves_government"))
    if b and con:
        return "B2B2C"
    if con and not b:
        return "B2C"
    if gov and not (b or con):
        return "B2G"
    if b:
        return "B2B"
    if "OPEN_SOURCE" in (c.get("revenue_models") or []):
        return "OPEN_SOURCE"
    return "UNKNOWN"


def apply_derivations(report: Dict[str, Any]) -> None:
    """Populate business_model on every competitor entry (deterministic)."""
    for key in ("company_competitors", "product_competitors", "alternative_solutions"):
        for c in report.get(key, []):
            c["business_model"] = _derive_business_model(c)


def _root(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.replace("www.", "")
        return f"https://{netloc}" if netloc else ""
    except Exception:
        return ""


def backfill_homepages(
    report: Dict[str, Any],
    sources: List[Dict[str, Any]],
) -> None:
    """Fill / repair official_website from verified sources.

    Replaces a blank URL or a non-official (directory / social / news) URL
    with the best homepage found in the evidence.
    """
    for key in ("company_competitors", "product_competitors", "alternative_solutions"):
        for e in report.get(key, []):
            site = (e.get("official_website") or "").strip()
            dom  = urlparse(site).netloc.replace("www.", "") if site else ""
            if site and dom and not is_non_official_domain(dom):
                continue
            best = choose_official_homepage(e.get("name", ""), sources)
            if best:
                e["official_website"] = best


# ---------------------------------------------------------------------------
# Core synthesis – three parallel LLM calls
# ---------------------------------------------------------------------------

def synthesize(
    query: str,
    plan: ToolPlan,
    sources: List[Dict[str, Any]],
    revision_notes: Optional[List[str]] = None,
) -> Report:
    """Run three parallel LLM calls and assemble a full Report.

    Parameters
    ----------
    query          : user's research question
    plan           : routing plan (subject, geography, industry, …)
    sources        : compacted + merged web sources
    revision_notes : if set, asks the LLM to fix specific issues from a
                     previous draft (output-guard reflection loop)

    Returns
    -------
    Report (Pydantic model)
    """
    rev = ""
    if revision_notes:
        joined = "\n".join(f"- {n}" for n in revision_notes)
        rev = (
            "\nREVISION REQUEST – a previous draft FAILED quality review. "
            "Fix these SPECIFIC points and regenerate, keeping everything "
            f"that was already correct:\n{joined}\n"
        )

    def _user_prompt(prefer_role: str) -> str:
        return f"""{rev}
USER QUERY: {query}
SUBJECT: {plan.subject_entity or '(whole market)'}
SUBJECT TYPE: {plan.subject_type}
INDUSTRY (true scope – do not narrow without explicit cause): {plan.industry or plan.market}
MARKET (search sub-segment): {plan.market}
GEOGRAPHY: {plan.geography}
SCOPE IS USER-RESTRICTED: {plan.scope_is_user_restricted}
PROHIBITED NARROWING (do not let these dominate unless scope is user-restricted): \
{', '.join(plan.prohibited_narrowing) or '(none)'}

SOURCES (OFFICIAL-tagged sources are authoritative; page text included):
{compact_sources(sources, prefer_role=prefer_role)}

Write now.
"""

    # Each job: (schema, system_prompt, prefer_role, effort)
    jobs = {
        "analyze_overview":    (ReportCore,      SYNTH_CORE, "market",     SYNTH_EFFORT),
        "analyze_competitors": (CompetitorBlock, SYNTH_COMP, "competitor", SYNTH_EFFORT),
        "analyze_personas":    (PersonaBlock,    SYNTH_PERS, "customer",   SYNTH_EFFORT),
    }

    def _run(item: tuple) -> tuple:
        name, (schema, system, role, effort) = item
        parsed = parse_llm(
            model=SYNTH_MODEL,
            system=system,
            user=_user_prompt(role),
            schema=schema,
            reasoning_effort=effort,
            label=name,
        )
        return name, parsed

    parts = dict(map_in_context(_run, jobs.items(), SYNTH_WORKERS))

    return Report(
        **parts["analyze_overview"].model_dump(),
        **parts["analyze_competitors"].model_dump(),
        **parts["analyze_personas"].model_dump(),
    )
