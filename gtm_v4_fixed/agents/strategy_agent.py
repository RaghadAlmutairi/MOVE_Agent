# -*- coding: utf-8 -*-
"""STRATEGY AGENT.

Responsibility
--------------
Consume the approved research Report and produce a CMO-grade GTM strategy.
This agent owns nothing else – it does not touch sources, tools, or content.

Execution model: THREE parallel LLM calls (Foundation | Activation | Execution)
whose results are merged into a single GTMStrategy object.

Input
-----
query   : str          – the user's original goal / question
plan    : ToolPlan     – routing metadata (subject, industry, geography)
report  : Dict[str, Any]  – approved research Report (as dict)
sources : Optional[List[Dict]]  – raw sources (passed for future grounding; unused today)

Output
------
GTMStrategy (Pydantic model)
"""
from typing import Any, Dict, List, Optional

from core.config import SYNTH_MODEL, SYNTH_EFFORT, traceable, map_in_context
from core.llm import parse_llm
from core.prompts import GTM_FOUNDATION_PROMPT, GTM_ACTIVATION_PROMPT, GTM_EXECUTION_PROMPT
from core.schemas import GTMStrategy, GTMFoundation, GTMActivation, GTMExecution, ToolPlan


# ---------------------------------------------------------------------------
# Research brief compressor (used by this agent AND by the content agent)
# ---------------------------------------------------------------------------

def _report_brief(report: Dict[str, Any], max_chars: int = 6500) -> str:
    """Compress the research Report into a tight brief the strategist grounds on."""
    r = report or {}

    def _lst(x: Any, n: int = 6) -> str:
        return "; ".join(str(i) for i in (x or [])[:n]) or "(none)"

    sw = r.get("subject_swot") or {}

    def _swot(k: str) -> str:
        return (
            "; ".join(
                it.get("point", "") for it in (sw.get(k) or [])[:4]
            ) or "(none)"
        )

    comps = (
        ", ".join(c.get("name", "") for c in (r.get("company_competitors") or [])[:6])
        or "(none)"
    )
    usp = (
        "; ".join(
            u
            for c in (r.get("product_competitors") or [])
            for u in (c.get("differentiators_usp") or [])
        )[:900]
        or "(none)"
    )
    personas = (
        "; ".join(
            f"{p.get('persona_name', '')} ({p.get('role_title', '')}, {p.get('segment', '')})"
            for p in (r.get("buyer_personas") or [])[:5]
        )
        or "(none)"
    )

    brief = (
        f"TITLE: {r.get('title', '')}\n"
        f"EXECUTIVE SUMMARY: {r.get('executive_summary', '')}\n"
        f"SWOT Strengths: {_swot('strengths')}\n"
        f"SWOT Weaknesses: {_swot('weaknesses')}\n"
        f"SWOT Opportunities: {_swot('opportunities')}\n"
        f"SWOT Threats: {_swot('threats')}\n"
        f"COMPANY COMPETITORS: {comps}\n"
        f"COMPETITOR DIFFERENTIATORS / USP (relative to the subject): {usp}\n"
        f"BUYER PERSONAS / ICP: {personas}\n"
        f"MARKET TRENDS: {_lst(r.get('market_trends'))}\n"
        f"OPPORTUNITIES: {_lst(r.get('opportunities'))}\n"
        f"RISKS: {_lst(r.get('risks'))}\n"
        f"RESEARCH RECOMMENDATIONS: {_lst(r.get('recommendations'))}"
    )
    return brief[:max_chars]


# ---------------------------------------------------------------------------
# Parallel job definitions
# ---------------------------------------------------------------------------

_JOBS = [
    ("foundation", GTM_FOUNDATION_PROMPT, GTMFoundation),
    ("activation", GTM_ACTIVATION_PROMPT, GTMActivation),
    ("execution",  GTM_EXECUTION_PROMPT,  GTMExecution),
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@traceable(name="generate_gtm_strategy")
def generate_gtm_strategy(
    query: str,
    plan: ToolPlan,
    report: Dict[str, Any],
    sources: Optional[List[Dict[str, Any]]] = None,
) -> GTMStrategy:
    """Generate a GTM strategy from the approved research report.

    Runs the three strategy pillars as PARALLEL LLM calls and merges them
    into a single GTMStrategy object.

    Parameters
    ----------
    query   : user's research / GTM goal
    plan    : ToolPlan from the research phase
    report  : approved research Report as a plain dict
    sources : raw web sources (accepted for interface consistency; reserved
              for future grounding passes)

    Returns
    -------
    GTMStrategy (Pydantic model)
    """
    header = (
        f"USER GOAL: {query}\n"
        f"SUBJECT: {plan.subject_entity or '(market)'}\n"
        f"SUBJECT TYPE: {plan.subject_type}\n"
        f"INDUSTRY: {plan.industry or plan.market}\n"
        f"GEOGRAPHY: {plan.geography}\n\n"
        f"=== MARKET RESEARCH BRIEF (ground the strategy in this) ===\n"
        f"{_report_brief(report)}\n"
    )

    def _run(job: tuple) -> tuple:
        name, system, schema = job
        user = header + f"\nProduce the {name.upper()} pillar now."
        parsed = parse_llm(
            model=SYNTH_MODEL,
            system=system,
            user=user,
            schema=schema,
            reasoning_effort=SYNTH_EFFORT,
            label=f"gtm-{name}",
        )
        return name, parsed

    print("        → GTM strategy: 3 parallel calls (foundation | activation | execution)")
    results = dict(map_in_context(_run, _JOBS, max_workers=3))

    foundation = results["foundation"]
    activation = results["activation"]
    execution  = results["execution"]

    return GTMStrategy(
        north_star=getattr(foundation, "north_star", "") or "",
        foundation=foundation,
        activation=activation,
        execution=execution,
    )
