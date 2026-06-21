# -*- coding: utf-8 -*-
"""Research pipeline – LangGraph graph for the research agent.

Nodes
-----
input_guard   → validate query + URL
analyze       → route tools based on query
tools         → run research tools in parallel
generate      → research agent: 3-parallel LLM calls → Report
output_guard  → quality gate with bounded revision loop
finalize      → assemble the result dict

This graph is compiled once and called via run_research().
The orchestrator agent imports run_research() and manages subsequent phases.
"""
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from langgraph.graph import StateGraph, END
from typing import TypedDict

from core.config import (
    ENABLE_INPUT_GUARD, ENABLE_OUTPUT_GUARD, TOOL_WORKERS,
    INTERNAL_ENTITIES, traceable, map_in_context, ENABLE_EVALUATORS,
)
from pipeline.guards import input_guard, output_guard, validate_url, REFUSAL_MESSAGE
from pipeline.router import route, enforce_tool_floor
from tools.research_tools import TOOLS
from agents.research_agent import (
    synthesize, apply_derivations, backfill_homepages, merge_sources,
)
from utils.validators import validate_granularity
from utils.verify import print_source_diagnostics
from utils.relevance import filter_relevant_sources, evidence_assessment
import pipeline.memory as memory
import pipeline.evaluation as evaluation


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

class ResearchState(TypedDict, total=False):
    """State dict passed between LangGraph nodes.  Nodes return partial updates."""
    query:           str
    url:             str
    t0:              float
    seed_url:        str
    plan_obj:        Any           # ToolPlan
    sources:         List[Dict[str, Any]]
    report:          Dict[str, Any]
    output_guard:    Dict[str, Any]
    synth_attempts:  int
    revision_notes:  List[str]
    blocked:         bool
    stage:           str
    message:         List[str]
    input_guard:     Dict[str, Any]
    result:          Dict[str, Any]   # final assembled result


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def node_input_guard(state: ResearchState) -> ResearchState:
    """Validate the query (content policy) and the optional company URL."""
    t0    = state.get("t0") or time.time()
    query = state["query"]
    url   = state.get("url", "")

    if ENABLE_INPUT_GUARD:
        print("\n[guard] input")
        ig = input_guard(query)
        print(f"      query: {ig['verdict']} ({ig.get('by')}) - {ig['reason']}")

        if ig["verdict"] == "BLOCK":
            res = {
                "query": query, "blocked": True, "stage": "input",
                "message": REFUSAL_MESSAGE, "input_guard": ig,
                "seconds": round(time.time() - t0, 1),
            }
            return {"blocked": True, "stage": "input", "input_guard": ig,
                    "message": REFUSAL_MESSAGE, "result": res}

        uv = validate_url(url)
        print(f"      url:   {'OK' if uv['ok'] else 'BLOCK'} - {uv['reason']}")
        if not uv["ok"]:
            ig2 = {"verdict": "BLOCK", "category": "BAD_URL",
                   "reason": uv["reason"], "by": "deterministic"}
            msg = [f"The provided URL was rejected: {uv['reason']}"]
            res = {
                "query": query, "blocked": True, "stage": "input",
                "message": msg, "input_guard": ig2,
                "seconds": round(time.time() - t0, 1),
            }
            return {"blocked": True, "stage": "input", "input_guard": ig2,
                    "message": msg, "result": res}
        return {"seed_url": uv["url"]}

    uv = validate_url(url)
    return {"seed_url": uv["url"] if uv["ok"] else ""}


def node_analyze(state: ResearchState) -> ResearchState:
    """Route the query to the correct research tools."""
    print("\n[1/3] analyze (routing tools)")
    plan = route(state["query"])
    plan = enforce_tool_floor(plan)

    print(
        f"      subject: {plan.subject_entity or '(none)'} | "
        f"type: {plan.subject_type} | "
        f"industry: {plan.industry or plan.market}"
    )
    print(f"      market:  {plan.market}")

    # Internal-entity detection → attach the RAG tool deterministically.
    _subj = (plan.subject_entity or "").lower().replace(" ", "")
    if _subj and any(e in _subj or _subj in e for e in INTERNAL_ENTITIES):
        if "internal_knowledge_tool" not in plan.required_tools:
            plan.required_tools.append("internal_knowledge_tool")
        print(
            f"      internal: '{plan.subject_entity}' is a known internal entity "
            "→ internal_knowledge_tool attached"
        )

    print(f"      tools:   {plan.required_tools}")
    if plan.scope_is_user_restricted:
        print("      scope:   RESTRICTED (user narrowed the query)")
    elif plan.prohibited_narrowing:
        print(f"      scope:   broad (guard against: {', '.join(plan.prohibited_narrowing)})")

    return {"plan_obj": plan}


def node_tools(state: ResearchState) -> ResearchState:
    """Run all routed research tools in parallel and merge their sources."""
    plan = state["plan_obj"]
    print(
        f"\n[2/3] gathering evidence: {len(plan.required_tools)} tool(s) in parallel "
        "(official discovery runs inside competitive_landscape_tool)"
    )

    def _run(tool_name: str) -> Dict[str, Any]:
        fn   = TOOLS[tool_name]
        args = {
            "subject_entity": plan.subject_entity,
            "market":         plan.market,
            "geography":      plan.geography,
        }
        if tool_name == "competitive_landscape_tool":
            args["subject_type"] = plan.subject_type
            args["industry"]     = plan.industry
        return fn.invoke(args) if hasattr(fn, "invoke") else fn(**args)

    routed_outputs = map_in_context(_run, plan.required_tools, TOOL_WORKERS)

    # Fold in user-supplied seed URL as an official source.
    tool_outputs = list(routed_outputs)
    seed_url = state.get("seed_url", "")
    if seed_url:
        seed = {
            "id": "0", "title": "User-provided official site", "url": seed_url,
            "domain": urlparse(seed_url).netloc.replace("www.", ""),
            "snippet": "", "raw": "", "official": True, "role": "official",
        }
        tool_outputs = [{"tool": "seed", "sources": [seed]}] + tool_outputs
        print(f"      ↳ seeded official source: {seed_url}")

    sources, dropped = filter_relevant_sources(
        merge_sources(tool_outputs), state["plan_obj"].model_dump()
    )
    if dropped:
        print(f"      relevance filter: dropped {dropped} off-market source(s)")

    n_off = sum(1 for s in sources if s.get("official"))
    print(f"\n      ✓ {len(sources)} unique sources ({n_off} official)")
    print_source_diagnostics(sources)
    return {"sources": sources}


def node_generate(state: ResearchState) -> ResearchState:
    """Call the research agent to synthesise the Report from gathered evidence."""
    attempt = state.get("synth_attempts", 0) + 1
    notes   = state.get("revision_notes") or []

    print(
        "\n[3/3] generate (3 parallel LLM calls)"
        + (f" - REVISION {attempt - 1}" if notes else "")
    )

    report = synthesize(
        state["query"], state["plan_obj"], state["sources"], revision_notes=notes
    ).model_dump()

    apply_derivations(report)
    backfill_homepages(report, state["sources"])

    issues = validate_granularity(report, state["plan_obj"].model_dump())
    if issues:
        report["_granularity_issues"] = issues
        print(f"      ⚠ granularity advisory: {len(issues)} note(s)")
        for it in issues:
            print(f"        • {it}")

    # Evidence-quality gate: cap confidence if competitor-official sources are thin.
    q, ev_notes, cap = evidence_assessment(report, state["sources"])
    report["_evidence_quality"] = q
    if ev_notes:
        report["_evidence_limitation"] = (
            "Evidence limitation: " + "; ".join(ev_notes) + "."
        )
        _order = {"low": 0, "medium": 1, "high": 2}
        if _order.get(report.get("confidence_level", "medium"), 1) > _order[cap]:
            report["confidence_level"] = cap
        print(
            f"      ⚠ evidence limitation attached; confidence capped to "
            f"'{report.get('confidence_level')}' "
            f"(official={q['official']}, competitor_official={q['competitor_official']})"
        )

    if ENABLE_EVALUATORS:
        ev = evaluation.evaluate_research(report)
        report["_evaluation"] = ev
        print(
            f"      [eval] research overall={ev.get('overall')} "
            f"passed={ev.get('passed')} (threshold {ev.get('threshold')})"
        )

    return {"report": report, "synth_attempts": attempt}


MAX_OUTPUT_REVISIONS = 1   # reflection passes before accepting as-is


def node_output_guard(state: ResearchState) -> ResearchState:
    """Quality-gate the report.  On failure, request targeted revisions (bounded)."""
    upd: Dict[str, Any] = {"revision_notes": []}
    if not ENABLE_OUTPUT_GUARD:
        return upd

    print("\n[guard] output")
    og = output_guard(
        state["query"], state["report"], state["sources"], state["plan_obj"].model_dump()
    )
    upd["output_guard"] = og
    print(f"      {og['verdict']} ({og.get('by')}) - {og['reason']}")
    for it in og.get("issues", []):
        print(f"        - {it}")

    if og["verdict"] == "BLOCK":
        attempts = state.get("synth_attempts", 1)
        if attempts <= MAX_OUTPUT_REVISIONS:
            notes = list(og.get("issues") or [])
            if og.get("reason"):
                notes.append(og["reason"])
            upd["revision_notes"] = notes
            print(
                f"      → asking research agent to revise {len(notes)} point(s) "
                f"(pass {attempts}/{MAX_OUTPUT_REVISIONS})"
            )
        else:
            print("      revision budget spent; accepting report with guard notes")
            rep = dict(state["report"])
            rep["_output_guard_issues"] = (
                og.get("issues") or ([og["reason"]] if og.get("reason") else [])
            )
            upd["report"] = rep

    return upd


def node_finalize(state: ResearchState) -> ResearchState:
    """Assemble the final result dict that the orchestrator will use."""
    if state.get("result"):
        return {}   # already built (e.g. blocked at input)

    t0 = state.get("t0") or time.time()
    result: Dict[str, Any] = {
        "query":   state["query"],
        "plan":    state["plan_obj"].model_dump(),
        "report":  state["report"],
        "sources": state["sources"],
        "seconds": round(time.time() - t0, 1),
    }
    if state.get("output_guard"):
        result["output_guard"] = state["output_guard"]
    if state.get("blocked"):
        result["blocked"] = True
        result["stage"]   = state.get("stage", "output")
        result["message"] = state.get("message", [])

    print(f"\n✓ Research complete in {result['seconds']}s")
    return {"result": result}


# ---------------------------------------------------------------------------
# Edge conditions
# ---------------------------------------------------------------------------

def _after_input(state: ResearchState) -> str:
    return "finalize" if state.get("blocked") else "analyze"


def _after_output_guard(state: ResearchState) -> str:
    return "generate" if state.get("revision_notes") else "finalize"


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------

def _build_research_graph() -> Any:
    g = StateGraph(ResearchState)
    g.add_node("input_guard",  node_input_guard)
    g.add_node("analyze",      node_analyze)
    g.add_node("tools",        node_tools)
    g.add_node("generate",     node_generate)
    g.add_node("output_guard", node_output_guard)
    g.add_node("finalize",     node_finalize)

    g.set_entry_point("input_guard")
    g.add_conditional_edges(
        "input_guard", _after_input,
        {"analyze": "analyze", "finalize": "finalize"},
    )
    g.add_edge("analyze",      "tools")
    g.add_edge("tools",        "generate")
    g.add_edge("generate",     "output_guard")
    g.add_conditional_edges(
        "output_guard", _after_output_guard,
        {"generate": "generate", "finalize": "finalize"},
    )
    g.add_edge("finalize", END)
    return g.compile()


_RESEARCH_GRAPH = _build_research_graph()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@traceable(name="run_research")
def run_research(query: str, url: str = "") -> Dict[str, Any]:
    """Run the research pipeline and return the result dict.

    This is the only function the orchestrator agent should call for the
    research phase.  All LangGraph details are internal to this module.

    Parameters
    ----------
    query : user's research question
    url   : optional company / product URL

    Returns
    -------
    result dict with keys: query, plan, report, sources, seconds,
    and optionally: blocked, stage, message, output_guard
    """
    final = _RESEARCH_GRAPH.invoke({"query": query, "url": url, "t0": time.time()})
    return final["result"]
