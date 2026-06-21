# -*- coding: utf-8 -*-
"""Guardrail service - deterministic validation gates for each stage.

Research : company exists, URL valid, competitors exist, sources exist.
Strategy : consistent with research, no fabricated/empty assumptions, no missing sections.
Content  : no fake data / testimonials / statistics / unsupported claims / harmful info.
Returns a list of issue strings ([] == pass).
"""
import re
from urllib.parse import urlparse
from typing import Any, Dict, List

# ----------------------------------------------------------------- research
def research_guardrails(result: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    plan = result.get("plan", {}) or {}
    report = result.get("report", {}) or {}
    sources = result.get("sources", []) or []

    if not (plan.get("subject_entity") or report.get("title")):
        issues.append("Company/subject not identified.")
    url = (result.get("url") or "").strip()
    if url:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            issues.append(f"Company URL is not valid: {url}")
    if not (report.get("company_competitors") or report.get("product_competitors")):
        issues.append("No competitors identified.")
    if not sources:
        issues.append("No sources were retrieved.")
    return issues


# ----------------------------------------------------------------- strategy
def strategy_guardrails(gtm: Dict[str, Any], report: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    f = gtm.get("foundation", {}) or {}
    a = gtm.get("activation", {}) or {}
    x = gtm.get("execution", {}) or {}
    if not (gtm.get("north_star") or f.get("north_star") or "").strip():
        issues.append("Strategy missing north star.")
    if not (f.get("positioning_statement") or "").strip():
        issues.append("Strategy missing positioning statement.")
    if not (f.get("beachhead") or {}).get("segment"):
        issues.append("Strategy missing beachhead segment.")
    if not f.get("competitive_differentiation"):
        issues.append("Strategy missing competitive differentiation.")
    if not (a.get("motion") or {}).get("primary"):
        issues.append("Strategy has no defined GTM motion.")
    if not a.get("channel_plays"):
        issues.append("Strategy missing channel plays.")
    if not x.get("roadmap_90day"):
        issues.append("Strategy missing 90-day roadmap.")
    if not (x.get("metrics") or {}).get("north_star_metric"):
        issues.append("Strategy missing north-star metric.")
    has_comp = bool(report.get("company_competitors") or report.get("product_competitors"))
    if has_comp and not f.get("competitive_differentiation"):
        issues.append("Strategy not consistent with research: no competitive "
                      "differentiation despite competitors in the research.")
    return issues


# ----------------------------------------------------------------- content (brand)
_TESTIMONIAL = re.compile(r"[\"\u201c][^\"\u201d]{8,}[\"\u201d]\s*[\u2014\-]\s*[A-Z][a-z]+"
                          r"|\b(said|according to|testimonial|raved|quoted)\b", re.I)
_STAT = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%|\b\d+x\b|\$\s?\d|\b\d{3,}\+?\s+(?:customers|users|clients|companies)\b", re.I)
_SUPERLATIVE = re.compile(r"\b(#1|number one|best[- ]in[- ]class|world[- ]class|"
                          r"award[- ]winning|guaranteed|the best|industry[- ]leading|"
                          r"unrivalled|unrivaled|the leading)\b", re.I)
_HARMFUL = re.compile(r"\b(guaranteed returns|miracle cure|risk[- ]free profit|"
                      r"cure cancer|get rich quick)\b", re.I)


def _content_text(content: Dict[str, Any]) -> str:
    parts: List[str] = [content.get("positioning_line", "")]
    for p in content.get("linkedin_posts", []):
        parts += [p.get("hook", ""), p.get("body", ""), p.get("cta", "")]
    for b in content.get("blog_drafts", []):
        parts += [b.get("title", ""), b.get("body", ""), b.get("meta_description", "")]
    for e in content.get("email_drafts", []):
        parts += [e.get("subject", ""), e.get("body", ""), e.get("cta", "")]
    return "\n".join(x for x in parts if x)


def content_guardrails(content: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    text = _content_text(content)
    if _TESTIMONIAL.search(text):
        issues.append("Possible fake testimonial / attributed quote detected.")
    stats = [m.group(0).strip() for m in _STAT.finditer(text)]
    if stats:
        issues.append(f"Unsupported statistic(s) detected (avoid hard numbers): "
                      f"{', '.join(stats[:4])}.")
    sup = _SUPERLATIVE.findall(text)
    if sup:
        issues.append(f"Unsupported superlative claim(s): {', '.join(set(sup))}.")
    if _HARMFUL.search(text):
        issues.append("Harmful / misleading claim detected.")
    return issues
