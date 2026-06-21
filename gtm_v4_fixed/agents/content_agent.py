# -*- coding: utf-8 -*-
"""CONTENT AGENT.

Responsibility
--------------
Produce ContentBundle objects for Phase A and Phase B.  This module owns
ONLY the pure generation logic and brief-compression helpers.

  Phase A  – Social-media content (LinkedIn posts) drafted directly from
             the research report.  Designed to run IN PARALLEL with the
             strategy agent; it must NOT depend on GTM strategy output.

  Phase B  – Full content suite (blogs, SEO articles, email sequences)
             refined against the finalised GTM strategy.

What does NOT belong here
-------------------------
* Tool definitions (generate_email / blog / seo / pdf / ppt) → tools/content_tools.py
* Phase A / Phase B orchestration (when to run each phase, approval gates,
  parallel execution) → agents/orchestrator.py

Input (Phase A)
---------------
query   : str             – user's original goal
plan    : ToolPlan
report  : Dict[str, Any]  – approved research Report

Input (Phase B)
---------------
All Phase A inputs PLUS:
gtm     : Dict[str, Any]  – approved GTM strategy
draft   : Dict[str, Any]  – Phase A ContentBundle (to refine, not replace)

Output
------
ContentBundle (Pydantic model) per phase.
"""
from typing import Any, Dict, List, Optional

from core.config import CONTENT_MODEL, CONTENT_EFFORT, traceable
from core.llm import parse_llm
from core.prompts import CONTENT_PHASE_A_PROMPT, CONTENT_PHASE_B_PROMPT
from core.schemas import ContentBundle, ToolPlan
from agents.strategy_agent import _report_brief


# ---------------------------------------------------------------------------
# Brief helpers
# ---------------------------------------------------------------------------

def _strategy_brief(gtm: Dict[str, Any], max_chars: int = 3800) -> str:
    """Compress the GTM strategy into a short context block."""
    g = gtm or {}
    f = g.get("foundation", {}) or {}
    a = g.get("activation", {}) or {}

    wedge = (
        "; ".join(
            d.get("sharpest_message", "")
            for d in (f.get("competitive_differentiation") or [])
        )[:500]
        or "-"
    )
    pillars = (
        "; ".join(
            p
            for m in (a.get("messaging_by_persona") or [])
            for p in (m.get("pillars") or [])
        )[:500]
        or "-"
    )
    chans = (
        "; ".join(c.get("channel", "") for c in (a.get("channel_plays") or []))
        or "-"
    )
    return (
        f"NORTH STAR: {g.get('north_star') or f.get('north_star', '')}\n"
        f"POSITIONING: {f.get('positioning_statement', '')}\n"
        f"BEACHHEAD: {(f.get('beachhead') or {}).get('segment', '')}\n"
        f"COMPETITIVE WEDGE: {wedge}\n"
        f"MESSAGING PILLARS: {pillars}\n"
        f"GTM MOTION: {(a.get('motion') or {}).get('primary', '')}\n"
        f"CHANNELS: {chans}"
    )[:max_chars]


def _content_brief(c: Dict[str, Any], max_chars: int = 3500) -> str:
    """Summarise an existing ContentBundle for Phase B prompt."""
    def block(items: Optional[List[Dict]], fields: List[str]) -> str:
        out = [
            " | ".join(f"{k}={str(it.get(k, ''))[:80]}" for k in fields)
            for it in (items or [])
        ]
        return "\n".join(out) or "—"

    return (
        f"POSITIONING: {c.get('positioning_line', '')}\n"
        f"LINKEDIN:\n{block(c.get('linkedin_posts'), ['kind', 'hook'])}\n"
        f"BLOGS:\n{block(c.get('blog_drafts'), ['kind', 'title'])}\n"
        f"EMAILS:\n{block(c.get('email_drafts'), ['kind', 'subject'])}"
    )[:max_chars]


# ---------------------------------------------------------------------------
# Placeholder enforcement (deterministic safety net)
# ---------------------------------------------------------------------------

_RECIPIENT_PH = "[Recipient Name]"
_SENDER_PH    = "[Sender Name]"


def _force_email_placeholders(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure every email has sender/recipient placeholders.

    The LLM must never invent a real person's name; this deterministic
    post-process is the safety net when the model forgets a placeholder.
    """
    for e in bundle.get("email_drafts", []) or []:
        body = (e.get("body") or "").strip()
        if _RECIPIENT_PH not in body:
            body = f"Hi {_RECIPIENT_PH},\n\n{body}"
        if _SENDER_PH not in body:
            body = f"{body}\n\nBest,\n{_SENDER_PH}"
        e["body"] = body
    return bundle


# ---------------------------------------------------------------------------
# Phase A – social-media content (parallel with strategy agent)
# ---------------------------------------------------------------------------

@traceable(name="content_phase_a")
def generate_content_phase_a(
    query: str,
    plan: ToolPlan,
    report: Dict[str, Any],
) -> ContentBundle:
    """Phase A: draft LinkedIn / social content from research only.

    This phase is designed to run concurrently with the strategy agent.
    It must NOT depend on any strategy output; only the research report
    is used as input.

    Parameters
    ----------
    query  : user's original goal
    plan   : routing metadata
    report : approved research Report dict

    Returns
    -------
    ContentBundle (Phase A – social content only)
    """
    user = (
        f"USER GOAL: {query}\n"
        f"SUBJECT: {plan.subject_entity or '(market)'}\n\n"
        f"=== MARKET RESEARCH BRIEF ===\n{_report_brief(report)}\n\n"
        "Produce the Phase A content set now."
    )
    out = parse_llm(
        model=CONTENT_MODEL,
        system=CONTENT_PHASE_A_PROMPT,
        user=user,
        schema=ContentBundle,
        reasoning_effort=CONTENT_EFFORT,
        label="content-phase-a",
    )
    return ContentBundle(**_force_email_placeholders(out.model_dump()))


# ---------------------------------------------------------------------------
# Phase B – full content suite (requires approved strategy)
# ---------------------------------------------------------------------------

@traceable(name="content_phase_b")
def generate_content_phase_b(
    query: str,
    plan: ToolPlan,
    report: Dict[str, Any],
    gtm: Dict[str, Any],
    draft: Dict[str, Any],
) -> ContentBundle:
    """Phase B: refine and expand the full content suite against the GTM strategy.

    This phase runs ONLY AFTER the strategy agent has completed and been
    approved.  It refines the Phase A draft and adds blogs, SEO articles,
    and email sequences grounded in the GTM strategy.

    Parameters
    ----------
    query  : user's original goal
    plan   : routing metadata
    report : approved research Report dict
    gtm    : approved GTM strategy dict
    draft  : Phase A ContentBundle dict (to refine, not discard)

    Returns
    -------
    ContentBundle (Phase B – full suite)
    """
    user = (
        f"USER GOAL: {query}\n"
        f"SUBJECT: {plan.subject_entity or '(market)'}\n\n"
        f"=== RESEARCH BRIEF ===\n{_report_brief(report)}\n\n"
        f"=== GTM STRATEGY ===\n{_strategy_brief(gtm)}\n\n"
        f"=== EXISTING PHASE-A CONTENT (refine all of it) ===\n{_content_brief(draft)}\n\n"
        "Rewrite and align every asset to the strategy. Produce Phase B now."
    )
    out = parse_llm(
        model=CONTENT_MODEL,
        system=CONTENT_PHASE_B_PROMPT,
        user=user,
        schema=ContentBundle,
        reasoning_effort=CONTENT_EFFORT,
        label="content-phase-b",
    )
    return ContentBundle(**_force_email_placeholders(out.model_dump()))
