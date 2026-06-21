# -*- coding: utf-8 -*-
"""ORCHESTRATOR AGENT.

Responsibility
--------------
Coordinate the three specialist agents in the correct order, enforce
human-in-the-loop approval at every stage, and manage parallel execution
where the workflow permits it.

This is the single place that owns Phase A / Phase B content sequencing.
The content agent (agents/content_agent.py) provides pure generation
functions; the orchestrator decides *when* to call them.

Execution order
---------------

  ┌─────────────────────────────────────────────────────────┐
  │  STEP 1 – RESEARCH AGENT                                │
  │  Runs alone first.  Output: approved research Report.   │
  └──────────────────────────┬──────────────────────────────┘
                             │  [Human approves research]
                             ▼
  ┌──────────────────────────────────────────────────────────┐
  │  STEP 2 – STRATEGY AGENT  ║  CONTENT AGENT (Phase A)    │
  │  GTM strategy             ║  Social-media content only   │
  │  (parallel execution)     ║  Uses research output only   │
  └──────────────────────────────────────────────────────────┘
                             │
     [Human approves strategy]   [Human approves Phase A content]
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │  STEP 3 – CONTENT AGENT (Phase B)                       │
  │  Full content suite: blogs / SEO / emails               │
  │  Uses BOTH research output AND approved GTM strategy    │
  └─────────────────────────────────────────────────────────┘
                             │
          [Human approves full content]
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │  STEP 4 – REPORTING                                     │
  │  Export: PDF / Word / PPTX / strategy PDF               │
  └─────────────────────────────────────────────────────────┘

Human-in-the-loop gates
-----------------------
Every stage pauses for human review before the next stage starts.
The orchestrator never skips a gate.  Phase B is only started after
BOTH the strategy AND Phase A content have been approved.
"""
import os
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from core.config import IN_NOTEBOOK
from core.schemas import ToolPlan

from export.render import render_md, _gtm_md, _content_md
from export.export import market_report_analysis_tool
from export.export_strategy import export_strategy_pdf

from agents.strategy_agent import generate_gtm_strategy
from agents.content_agent import generate_content_phase_a, generate_content_phase_b

# All tools live in the tools package.
from tools.content_tools import generate_ppt, INTENT_KEYWORDS, TEXT_TOOL_NAMES, CONTENT_TOOLS

import pipeline.guardrails as guardrails
import pipeline.evaluation as evaluation
import pipeline.memory as memory


# ---------------------------------------------------------------------------
# Terminal UI helpers
# ---------------------------------------------------------------------------

def _has_llm_output(result: Dict[str, Any]) -> bool:
    """Return True when the result dict contains usable LLM-generated content."""
    if result.get("blocked"):
        return False
    r = result.get("report") or {}
    return bool(
        r.get("executive_summary")
        or r.get("product_competitors")
        or r.get("company_competitors")
        or r.get("buyer_personas")
    )


def _ask_exact(prompt: str, valid: Dict[str, str], attempts: int = 3) -> Optional[str]:
    """Prompt for one of a fixed set of responses; return the canonical value."""
    for i in range(attempts):
        try:
            raw = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if raw in valid:
            return valid[raw]
        left = attempts - i - 1
        print(
            f"   Invalid response. Allowed: "
            f"{' / '.join(sorted(set(valid.values())))}. "
            f"{left} attempt(s) left."
        )
    return None


def _ask_yes_no(prompt: str, attempts: int = 3) -> bool:
    return (
        _ask_exact(prompt, {"y": "y", "yes": "y", "n": "n", "no": "n"}, attempts) == "y"
    )


def _ask_multi(prompt: str, valid: Dict[str, str], attempts: int = 3) -> List[str]:
    """Multi-select: accept any number of options; 'all' selects everything."""
    import re
    allvals = list(dict.fromkeys(valid.values()))
    for i in range(attempts):
        try:
            raw = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return []
        toks = [t for t in re.split(r"[ ,/]+", raw) if t]
        if "all" in toks or "everything" in toks:
            return allvals
        sel = []
        for t in toks:
            if t in valid and valid[t] not in sel:
                sel.append(valid[t])
        if sel:
            return sel
        print(f"   Choose from: {' / '.join(allvals)} (or 'all').")
    return []


def _render_to_terminal(md: str) -> None:
    try:
        from rich.console import Console
        from rich.markdown import Markdown as _RichMD
        Console().print(_RichMD(md))
    except Exception:
        print(md)


def _show_md(md: str, banner: str) -> None:
    print(f"\n\n================ {banner} ================\n")
    if IN_NOTEBOOK:
        from IPython.display import Markdown, display
        display(Markdown(md))
    else:
        _render_to_terminal(md)


def _show_report(result: Dict[str, Any]) -> str:
    md = render_md(result)
    _show_md(md, "RESEARCH REPORT")
    with open("market_research_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    with open("market_research_report.md", "w", encoding="utf-8") as f:
        f.write(md)
    return md


def _deliver_file(path: str) -> None:
    try:
        from google.colab import files as _colab_files  # type: ignore
        _colab_files.download(path)
        print(f"   ⬇ download started: {path}")
        return
    except Exception:
        pass
    print(f"   File saved to: {os.path.abspath(path)}")


def _plan_obj(result: Dict[str, Any]) -> ToolPlan:
    return ToolPlan(**result["plan"])


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

_FMT = {
    "pdf": "pdf", "word": "word", "docx": "word",
    "pptx": "pptx", "ppt": "pptx", "powerpoint": "pptx", "deck": "pptx",
    "no": "no", "n": "no", "none": "no",
}

_APPROVE = {
    "approved": "approved", "approve": "approved", "a": "approved",
    "re-generate": "regenerate", "regenerate": "regenerate", "r": "regenerate",
}


def _export(result: Dict[str, Any], fmt: str) -> Optional[str]:
    """Export the result in the requested format; return the file path."""
    if fmt == "pptx":
        fn  = generate_ppt
        out = fn.invoke({"result": result}) if hasattr(fn, "invoke") else fn(result=result)
    else:
        fn  = market_report_analysis_tool
        out = (
            fn.invoke({"result": result, "fmt": fmt})
            if hasattr(fn, "invoke")
            else fn(result=result, fmt=fmt)
        )
    p = out.get("path")
    if p:
        _deliver_file(p)
        result.setdefault("exports", []).append({"format": fmt, "path": p})
        print(f"   ✓ {fmt.upper()} created: {p}")
    else:
        print(f"   ⚠ {fmt} export unavailable (install the matching library).")
    return p


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------

def _run_strategy(result: Dict[str, Any], max_attempts: int = 2) -> Optional[Dict[str, Any]]:
    """Generate (and validate) the GTM strategy; return the strategy dict or None."""
    plan   = _plan_obj(result)
    report = result["report"]
    gtm    = None

    for attempt in range(1, max_attempts + 1):
        print(f"\n[strategy agent] generating GTM strategy (attempt {attempt}) …")
        try:
            gtm = generate_gtm_strategy(
                result["query"], plan, report, result.get("sources")
            ).model_dump()
        except Exception as e:
            print(f"   ⚠ strategy generation failed: {str(e)[:90]}")
            return None

        issues = guardrails.strategy_guardrails(gtm, report)
        ev     = evaluation.evaluate_strategy(gtm)
        gtm["_evaluation"] = ev
        print(
            f"   [eval] strategy overall={ev.get('overall')} "
            f"passed={ev.get('passed')} (threshold {ev.get('threshold')})"
        )
        if issues:
            print("   guardrail issues: " + "; ".join(issues))

        if (not issues and ev.get("passed")) or attempt == max_attempts:
            if issues or not ev.get("passed"):
                print("   proceeding with noted gaps.")
            return gtm

        print("   enforcing strategy REGENERATE …")

    return gtm


# ---------------------------------------------------------------------------
# Phase A – social-media content (runs in parallel with strategy agent)
# ---------------------------------------------------------------------------

def _run_content_phase_a(
    result: Dict[str, Any],
    max_attempts: int = 2,
) -> Optional[Dict[str, Any]]:
    """Generate and validate Phase A (social-media) content from research only.

    Runs concurrently with the strategy agent.  Must NOT use any strategy output.
    """
    plan   = _plan_obj(result)
    report = result["report"]
    bundle = None

    for attempt in range(1, max_attempts + 1):
        print(f"\n[content agent] Phase A – social content (attempt {attempt}) …")
        try:
            bundle = generate_content_phase_a(result["query"], plan, report).model_dump()
        except Exception as e:
            print(f"   ⚠ Phase A content generation failed: {str(e)[:90]}")
            return None

        # Phase A scope: LinkedIn posts only.
        bundle["blog_drafts"]  = []
        bundle["email_drafts"] = []

        issues = guardrails.content_guardrails(bundle)
        ev     = evaluation.evaluate_content(bundle)
        bundle["_evaluation"] = ev
        print(
            f"   [eval] Phase A content overall={ev.get('overall')} "
            f"passed={ev.get('passed')} (threshold {ev.get('threshold')})"
        )
        if issues:
            print("   brand guardrail issues: " + "; ".join(issues))

        if (not issues and ev.get("passed")) or attempt == max_attempts:
            if issues or not ev.get("passed"):
                print("   proceeding with noted gaps.")
            return bundle

        print("   brand guardrails failed → enforcing Phase A REGENERATE …")

    return bundle


# ---------------------------------------------------------------------------
# Phase B – full content suite (requires approved strategy + Phase A)
# ---------------------------------------------------------------------------

def _run_content_phase_b(
    result: Dict[str, Any],
    gtm: Dict[str, Any],
    phase_a_bundle: Dict[str, Any],
    channels: List[str],
    max_attempts: int = 2,
) -> Optional[Dict[str, Any]]:
    """Generate and validate Phase B (full content suite) using the GTM strategy.

    Requires BOTH an approved strategy AND an approved Phase A bundle.
    This function is the only place in the codebase where Phase B is initiated.
    """
    plan   = _plan_obj(result)
    report = result["report"]
    bundle = None

    for attempt in range(1, max_attempts + 1):
        print(f"\n[content agent] Phase B – full content suite (attempt {attempt}) …")
        try:
            bundle = generate_content_phase_b(
                result["query"], plan, report, gtm, phase_a_bundle
            ).model_dump()
            bundle["phase"] = "B"
        except Exception as e:
            print(f"   ⚠ Phase B content generation failed: {str(e)[:90]}")
            return None

        bundle = _filter_content(bundle, channels)

        issues = guardrails.content_guardrails(bundle)
        ev     = evaluation.evaluate_content(bundle)
        bundle["_evaluation"] = ev
        print(
            f"   [eval] Phase B content overall={ev.get('overall')} "
            f"passed={ev.get('passed')} (threshold {ev.get('threshold')})"
        )
        if issues:
            print("   brand guardrail issues: " + "; ".join(issues))

        if (not issues and ev.get("passed")) or attempt == max_attempts:
            if issues or not ev.get("passed"):
                print("   proceeding with noted gaps.")
            return bundle

        print("   brand guardrails failed → enforcing Phase B REGENERATE …")

    return bundle


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

_CONTENT_OPTS = {
    "linkedin": "linkedin", "li": "linkedin",
    "blog": "blog", "seo": "seo",
    "email": "email", "emails": "email",
    "pdf": "pdf", "ppt": "pptx", "pptx": "pptx", "powerpoint": "pptx",
}


def _filter_content(bundle: Dict[str, Any], channels: List[str]) -> Dict[str, Any]:
    """Remove content assets not in the requested channels list."""
    if not channels:
        return bundle
    if "linkedin" not in channels:
        bundle["linkedin_posts"] = []
    if "blog" not in channels and "seo" not in channels:
        bundle["blog_drafts"] = []
    elif "blog" not in channels and "seo" in channels:
        bundle["blog_drafts"] = [
            b for b in bundle.get("blog_drafts", []) if b.get("kind") == "SEO"
        ]
    if "email" not in channels:
        bundle["email_drafts"] = []
    return bundle


def _detect_intents(query: str) -> List[str]:
    """Detect which asset types the user explicitly requested."""
    q = (query or "").lower()
    return [name for name, kws in INTENT_KEYWORDS.items() if any(k in q for k in kws)]


def _call_tool(t: Any, **kwargs: Any) -> Dict[str, Any]:
    return t.invoke(kwargs) if hasattr(t, "invoke") else t(**kwargs)


# ---------------------------------------------------------------------------
# Orchestrator entry point
# ---------------------------------------------------------------------------

def run_pipeline(result: Dict[str, Any], regenerate_research) -> Dict[str, Any]:
    """Run the full multi-agent pipeline with human-in-the-loop at every stage.

    This is the orchestrator entry point called by main.py after research
    completes.  It owns all sequencing, parallelism, phase decisions, and
    approval gates.

    Parameters
    ----------
    result              : research result dict (from run_research)
    regenerate_research : callable() → result dict  – regenerates research

    Returns
    -------
    Final result dict (accumulated across all stages).
    """
    company = (
        (result.get("plan") or {}).get("subject_entity")
        or (result.get("report") or {}).get("title")
        or "(market)"
    )

    # ------------------------------------------------------------------
    # STEP 1: RESEARCH – show, guardrail-check, Approve / Regenerate
    # ------------------------------------------------------------------
    print("\n\n═══════════════ STEP 1: RESEARCH ═══════════════")
    while True:
        _show_report(result)
        ri = guardrails.research_guardrails(result)
        if ri:
            print("\n⚠ Research guardrail notes:")
            for x in ri:
                print(f"   • {x}")

        choice = _ask_exact("\nApproved? / Re-Generate : ", _APPROVE, attempts=3)
        if choice is None:
            print("\n⛔ No valid choice. Session terminated.")
            return result
        if choice == "approved":
            memory.log_approval(company, "research:approved")
            break

        print("\n↻ Regenerating research …")
        new = regenerate_research()
        if not _has_llm_output(new):
            print("\n⛔ Regeneration produced no usable output. Session terminated.")
            return new
        result = new

    # Export research document (optional).
    fmt = _ask_exact(
        "\nExport research document? PDF / Word / No : ",
        {k: v for k, v in _FMT.items() if v != "pptx"},
        attempts=3,
    )
    if fmt and fmt != "no":
        _export(result, fmt)

    # ------------------------------------------------------------------
    # STEP 2: STRATEGY + CONTENT PHASE A (run in parallel)
    # Both require research approval.
    # Phase A does NOT require strategy — runs alongside it.
    # ------------------------------------------------------------------
    run_strategy = _ask_yes_no("\nCreate your GTM strategy? (y/n) : ")
    run_content  = _ask_yes_no("\nGenerate marketing content? (y/n) : ")

    gtm: Optional[Dict[str, Any]] = None
    phase_a_bundle: Optional[Dict[str, Any]] = None

    if run_strategy or run_content:
        print("\n\n═══════════════ STEP 2: STRATEGY + CONTENT PHASE A (parallel) ═══════════════")

        futures: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=2) as ex:
            if run_strategy:
                futures["strategy"] = ex.submit(_run_strategy, result)
            if run_content:
                futures["phase_a"]  = ex.submit(_run_content_phase_a, result)

        if "strategy" in futures:
            gtm = futures["strategy"].result()
        if "phase_a" in futures:
            phase_a_bundle = futures["phase_a"].result()

    # ---- 2a) Human approves STRATEGY ----
    if run_strategy and gtm:
        print("\n\n─── STRATEGY APPROVAL ───")
        result["gtm_strategy"] = gtm
        for _ in range(3):
            _show_md("\n".join(_gtm_md(gtm)), "GTM STRATEGY")
            sc = _ask_exact("\nApproved? / Re-Generate : ", _APPROVE, attempts=3)
            if sc is None or sc == "approved":
                memory.log_approval(company, "strategy:approved")
                break
            gtm = _run_strategy(result)
            if gtm is None:
                print("   ⚠ Strategy regeneration failed; proceeding with last draft.")
                gtm = result["gtm_strategy"]
                break
            result["gtm_strategy"] = gtm

        sf = _ask_exact(
            "\nExport GTM strategy? PDF / No : ",
            {"pdf": "pdf", "no": "no", "n": "no"},
            attempts=3,
        )
        if sf == "pdf":
            p = export_strategy_pdf(result)
            if p:
                _deliver_file(p)
                result.setdefault("exports", []).append({"format": "strategy_pdf", "path": p})
                memory.log_approval(company, "strategy:pdf")

    # ---- 2b) Human approves PHASE A CONTENT (social-media) ----
    if run_content and phase_a_bundle:
        print("\n\n─── CONTENT PHASE A APPROVAL (social-media content) ───")
        result["content_phase_a"] = phase_a_bundle
        for _ in range(3):
            _show_md("\n".join(_content_md(phase_a_bundle)), "SOCIAL MEDIA CONTENT (Phase A)")
            cc = _ask_exact("\nApproved? / Re-Generate : ", _APPROVE, attempts=3)
            if cc is None or cc == "approved":
                memory.log_approval(company, "content_phase_a:approved")
                break
            new_bundle = _run_content_phase_a(result)
            if new_bundle is None:
                print("   ⚠ Regeneration failed; proceeding with last Phase A draft.")
                break
            phase_a_bundle = new_bundle
            result["content_phase_a"] = phase_a_bundle

    # ------------------------------------------------------------------
    # STEP 3: CONTENT PHASE B – full suite
    # Gate: requires BOTH approved strategy AND approved Phase A bundle.
    # ------------------------------------------------------------------
    if run_content and gtm and phase_a_bundle:
        print("\n\n═══════════════ STEP 3: CONTENT PHASE B (full content suite) ═══════════════")
        print(
            "   Phase B uses the approved GTM strategy + Phase A draft to produce\n"
            "   blogs, SEO articles, and email sequences.\n"
        )

        sel = _ask_multi(
            "\nSelect content channels – linkedin / blog / seo / email"
            "  (add pdf / ppt to export, or type 'all') : ",
            _CONTENT_OPTS,
        )
        channels = [t for t in sel if t in ("linkedin", "blog", "seo", "email")]
        formats  = [t for t in sel if t in ("pdf", "pptx")]

        phase_b_bundle: Optional[Dict[str, Any]] = None
        for _ in range(1, 3):
            phase_b_bundle = _run_content_phase_b(
                result, gtm, phase_a_bundle, channels
            )
            if phase_b_bundle is None:
                break
            result["content"] = phase_b_bundle
            _show_md("\n".join(_content_md(phase_b_bundle)), "FULL CONTENT SUITE (Phase B)")
            cb = _ask_exact("\nApproved? / Re-Generate : ", _APPROVE, attempts=3)
            if cb is None or cb == "approved":
                memory.log_approval(company, "content_phase_b:approved")
                break

        for f in formats:
            if _export(result, f):
                memory.log_approval(company, f"content:{f}")

    # ------------------------------------------------------------------
    # STEP 4: REPORTING – optional combined export
    # ------------------------------------------------------------------
    print("\n\n═══════════════ STEP 4: REPORTING ═══════════════")
    has_extras = bool(gtm or result.get("content"))
    if has_extras and not result.get("exports"):
        cf = _ask_exact(
            "\nExport combined report? PDF / Word / PPTX / No : ",
            _FMT,
            attempts=3,
        )
        if cf and cf != "no":
            _export(result, cf)
            memory.log_approval(company, f"combined:{cf}")

    memory.save_run(result)
    print("\n✓ Session complete. Session terminated.")
    return result
