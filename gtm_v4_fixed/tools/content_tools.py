# -*- coding: utf-8 -*-
"""Content generation tools.

All intent-routed content tools live here so the tools/ package is the
single authoritative location for every callable tool in the system.

Tools
-----
generate_email  – outbound / nurture / launch email drafts
generate_blog   – long-form educational blog article
generate_seo    – keyword-optimised SEO article
generate_pdf    – export the research report as PDF
generate_ppt    – render the executive PPTX deck (with Claude copy polish)

The content agent (agents/content_agent.py) provides the pure generation
functions (generate_content_phase_a / generate_content_phase_b).  These
tools wrap those functions to add intent-routing and output filtering.
Phase A / Phase B orchestration belongs exclusively to the orchestrator.
"""
from typing import Any, Dict, List, Optional

from core.config import tool
from export.export import market_report_analysis_tool
from export.export_pptx import export_pptx


# ---------------------------------------------------------------------------
# Internal helpers (imported lazily to avoid circular imports at module load)
# ---------------------------------------------------------------------------

def _get_content_agent():
    """Deferred import of the content agent to avoid circular dependencies."""
    import agents.content_agent as ca
    return ca


def _bundle_for(
    query: str,
    plan: Any,
    report: Dict[str, Any],
    gtm: Optional[Dict[str, Any]],
    draft: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return the correct phase ContentBundle dict.

    Generates Phase A first when no draft is supplied; upgrades to Phase B
    when a GTM strategy is available.  Phase sequencing decisions (when to
    run A vs B) belong to the orchestrator — this helper only resolves which
    generation function to call based on what inputs are present.
    """
    ca = _get_content_agent()
    if draft is None:
        draft = ca.generate_content_phase_a(query, plan, report).model_dump()
    if gtm:
        bundle = ca.generate_content_phase_b(query, plan, report, gtm, draft).model_dump()
        bundle["phase"] = "B"
    else:
        bundle = draft
    return bundle


def _call(t: Any, **kwargs: Any) -> Dict[str, Any]:
    return t.invoke(kwargs) if hasattr(t, "invoke") else t(**kwargs)


# ---------------------------------------------------------------------------
# Text content tools
# ---------------------------------------------------------------------------

@tool
def generate_email(
    query: str,
    plan: Any,
    report: Dict[str, Any],
    gtm: Optional[Dict[str, Any]] = None,
    draft: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """CONTENT TOOL – generate send-ready outbound / nurture / launch emails.

    Produces email drafts with [Sender Name] / [Recipient Name] placeholders.
    LinkedIn posts and blog drafts are excluded from the output.
    """
    bundle = _bundle_for(query, plan, report, gtm, draft)
    bundle["linkedin_posts"] = []
    bundle["blog_drafts"]    = []
    return bundle


@tool
def generate_blog(
    query: str,
    plan: Any,
    report: Dict[str, Any],
    gtm: Optional[Dict[str, Any]] = None,
    draft: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """CONTENT TOOL – generate a long-form educational blog article (publish-ready prose)."""
    bundle = _bundle_for(query, plan, report, gtm, draft)
    bundle["linkedin_posts"] = []
    bundle["email_drafts"]   = []
    bundle["blog_drafts"] = [
        b for b in bundle.get("blog_drafts", []) if b.get("kind") == "EDUCATIONAL"
    ]
    return bundle


@tool
def generate_seo(
    query: str,
    plan: Any,
    report: Dict[str, Any],
    gtm: Optional[Dict[str, Any]] = None,
    draft: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """CONTENT TOOL – generate a keyword-optimised SEO article.

    Includes target keyword, secondary keywords, meta description, and full body.
    """
    bundle = _bundle_for(query, plan, report, gtm, draft)
    bundle["linkedin_posts"] = []
    bundle["email_drafts"]   = []
    bundle["blog_drafts"] = [
        b for b in bundle.get("blog_drafts", []) if b.get("kind") == "SEO"
    ]
    return bundle


# ---------------------------------------------------------------------------
# Export tools
# ---------------------------------------------------------------------------

@tool
def generate_pdf(result: Dict[str, Any]) -> Dict[str, Any]:
    """CONTENT TOOL – export the approved research report as a PDF.

    Delegates to the shared export tool; no export logic is duplicated here.
    """
    fn = market_report_analysis_tool
    return fn.invoke({"result": result, "fmt": "pdf"}) if hasattr(fn, "invoke") \
        else fn(result=result, fmt="pdf")


def _enhance_pptx_copy(result: Dict[str, Any]) -> Dict[str, Any]:
    """Polish slide-bound narrative copy with Claude before rendering.

    Sharpens executive summary, recommendations, and SWOT bullet wording
    for board-ready language.  Degrades gracefully to a no-op if no
    ANTHROPIC_API_KEY is set.  Facts and structure are preserved; only
    wording is improved.
    """
    from core.llm import enhance_with_claude

    report = dict((result.get("report") or {}))
    if not report:
        return result

    sys_prompt = (
        "You are a senior brand strategist polishing slide copy for an executive "
        "GTM deck. Rewrite to tight, punchy, board-ready language. Do not invent "
        "facts, numbers, or claims. Return ONLY the rewritten lines, same count "
        "and order as given, one per line, no numbering, no commentary."
    )

    def _rewrite(lines: List[str]) -> List[str]:
        lines = [l for l in lines if l]
        if not lines:
            return lines
        out = enhance_with_claude(sys_prompt, "\n".join(lines))
        new_lines = [l.strip("-• ").strip() for l in out.splitlines() if l.strip()]
        return new_lines if len(new_lines) == len(lines) else lines

    if report.get("executive_summary"):
        rewritten = _rewrite([report["executive_summary"]])
        if rewritten:
            report["executive_summary"] = rewritten[0]

    if report.get("recommendations"):
        recs = report["recommendations"]
        report["recommendations"] = _rewrite(list(recs)) or recs

    swot = dict(report.get("subject_swot") or {})
    for key in ("strengths", "weaknesses", "opportunities", "threats"):
        items = swot.get(key) or []
        if not items:
            continue
        pts = [
            it.get("point", "") if isinstance(it, dict) else str(it)
            for it in items
        ]
        new_pts = _rewrite(pts)
        if new_pts:
            for i, it in enumerate(items):
                if isinstance(it, dict):
                    it["point"] = new_pts[i]
                else:
                    items[i] = new_pts[i]
    if swot:
        report["subject_swot"] = swot

    enhanced = dict(result)
    enhanced["report"] = report
    return enhanced


@tool
def generate_ppt(result: Dict[str, Any]) -> Dict[str, Any]:
    """CONTENT TOOL – render the executive PPTX deck.

    Enhances SWOT / executive-summary / recommendations copy with Claude
    for sharper narrative before rendering using the existing deck template.
    """
    enhanced = _enhance_pptx_copy(result)
    path = export_pptx(enhanced)
    return {"tool": "generate_ppt", "format": "pptx", "path": path}


# ---------------------------------------------------------------------------
# Registry – single authoritative mapping for all content tools
# ---------------------------------------------------------------------------

CONTENT_TOOLS: Dict[str, Any] = {
    "generate_email": generate_email,
    "generate_blog":  generate_blog,
    "generate_seo":   generate_seo,
    "generate_pdf":   generate_pdf,
    "generate_ppt":   generate_ppt,
}

# Keyword → tool-name intent mapping used by the orchestrator's router.
INTENT_KEYWORDS: Dict[str, tuple] = {
    "pdf":   ("pdf",),
    "ppt":   ("ppt", "pptx", "powerpoint", "deck", "slide"),
    "email": ("email", "e-mail", "outreach"),
    "seo":   ("seo", "search engine", "keyword"),
    "blog":  ("blog", "article"),
}

TEXT_TOOL_NAMES = {"email", "blog", "seo"}
