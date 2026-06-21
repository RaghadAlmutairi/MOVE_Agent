"""Markdown renderer for the assembled report (console / file output)."""
from typing import List, Dict, Any
from urllib.parse import urlparse


def _cell(items) -> str:
    return "; ".join(items) if items else "—"


def _rev_cell(models) -> str:
    return ", ".join(models) if models else "—"


def _swot_cell(items) -> str:
    if not items:
        return "—"
    lines = []
    for it in items:
        cites = "".join(f"[{s}]" for s in (it.get("source_ids") or []))
        point = (it.get("point") or "").strip()
        lines.append(f"• {point} {cites}".strip())
    return "<br>".join(lines)


def _site_cell(site: str, status: Dict[str, bool] = None) -> str:
    site = (site or "").strip()
    if not site:
        return "—"
    return f"[{urlparse(site).netloc.replace('www.','')}]({site})"


def _gtm_md(g):
    """Render the full GTM strategy (Foundation / Activation / Execution)."""
    f = g.get("foundation", {}) or {}
    a = g.get("activation", {}) or {}
    x = g.get("execution", {}) or {}
    o = ["## Go-To-Market Strategy", ""]
    if g.get("north_star") or f.get("north_star"):
        o.append(f"**North Star:** {g.get('north_star') or f.get('north_star')}")
        o.append("")

    # STRATEGY
    o.append("### Strategy")
    if f.get("positioning_statement"):
        o.append(f"**Positioning.** {f['positioning_statement']}")
        o.append("")
    sl = f.get("slot_statement") or {}
    if any(sl.values()):
        o.append("**Slot statement**")
        for k in ("for_who", "who_need", "category", "promise", "unlike", "proof"):
            if sl.get(k):
                o.append(f"- *{k.replace('_', ' ').title()}:* {sl[k]}")
        o.append("")

    # CUSTOMER
    icp = f.get("icp") or {}
    if any(icp.values()):
        o.append("### Customer - Ideal Customer Profile")
        for k in ("primary_segment", "firmographics", "technographics", "why_now"):
            if icp.get(k):
                o.append(f"- **{k.replace('_', ' ').title()}:** {icp[k]}")
        if icp.get("buying_committee"):
            o.append(f"- **Buying committee:** {', '.join(icp['buying_committee'])}")
        o.append("")
    for label, key in [("Top pains", "top_pains"), ("Trigger events", "trigger_events"),
                       ("Disqualifiers", "disqualifiers"), ("Secondary segments", "secondary_segments")]:
        if f.get(key):
            o.append(f"**{label}:** " + "; ".join(f[key]))
    o.append("")

    # PLAN - Beachhead
    bh = f.get("beachhead") or {}
    if any(bh.values()):
        o.append("### Plan - Beachhead Strategy")
        if bh.get("segment"):
            o.append(f"- **Segment:** {bh['segment']}")
        if bh.get("rationale"):
            o.append(f"- **Rationale:** {bh['rationale']}")
        if bh.get("entry_wedge"):
            o.append(f"- **Entry wedge:** {bh['entry_wedge']}")
        if bh.get("expansion_path"):
            o.append(f"- **Expansion path:** {' -> '.join(bh['expansion_path'])}")
        if bh.get("market_sizing_logic"):
            o.append(f"- **Market sizing:** {bh['market_sizing_logic']}")
        o.append("")

    # EDGE
    diffs = f.get("competitive_differentiation") or []
    if diffs:
        o.append("### Edge - Competitive Differentiation")
        o.append("| Competitor | Where we win | Where they win | Sharpest message |")
        o.append("|---|---|---|---|")
        for d in diffs:
            o.append(f"| {d.get('competitor','')} | {'; '.join(d.get('where_we_win',[]))} | "
                     f"{'; '.join(d.get('where_they_win',[]))} | {d.get('sharpest_message','')} |")
        o.append("")

    # COMMERCIAL
    pr = a.get("pricing") or {}
    if any(v for v in pr.values()):
        o.append("### Commercial - Offer & Pricing")
        if pr.get("packaging_logic"):
            o.append(f"- **Packaging:** {pr['packaging_logic']}")
        if pr.get("tiers"):
            o.append(f"- **Tiers:** {'; '.join(pr['tiers'])}")
        if pr.get("anchor_strategy"):
            o.append(f"- **Anchor:** {pr['anchor_strategy']}")
        if pr.get("commercial_motion"):
            o.append(f"- **Commercial motion:** {pr['commercial_motion']}")
        if pr.get("pricing_levers"):
            o.append(f"- **Pricing levers:** {'; '.join(pr['pricing_levers'])}")
        if pr.get("pricing_risks"):
            o.append(f"- **Pricing risks:** {'; '.join(pr['pricing_risks'])}")
        o.append("")

    # MOTION
    mo = a.get("motion") or {}
    if any(v for v in mo.values()):
        o.append("### Motion - GTM Motion")
        if mo.get("primary"):
            o.append(f"- **Primary:** {mo['primary']}")
        if mo.get("secondary"):
            o.append(f"- **Secondary:** {mo['secondary']}")
        if mo.get("rationale"):
            o.append(f"- **Rationale:** {mo['rationale']}")
        if mo.get("motion_risks"):
            o.append(f"- **Risks:** {'; '.join(mo['motion_risks'])}")
        o.append("")

    # CHANNELS
    ch = a.get("channel_plays") or []
    if ch:
        o.append("### Channels - Channel Plays")
        o.append("| Channel | Funnel role | Leading indicator | Invest |")
        o.append("|---|---|---|---|")
        for c in ch:
            o.append(f"| {c.get('channel','')} | {c.get('funnel_role','')} | "
                     f"{c.get('leading_indicator','')} | {c.get('invest','')} |")
        o.append("")

    # MESSAGING
    msg = a.get("messaging_by_persona") or []
    if msg:
        o.append("### Messaging by Persona")
        for m in msg:
            o.append(f"**{m.get('persona','')}** - {m.get('core_promise','')}")
            if m.get("primary_channel") or m.get("cta"):
                o.append(f"*Channel:* {m.get('primary_channel','')} · *CTA:* {m.get('cta','')}")
            if m.get("pillars"):
                o.append(f"*Pillars:* {'; '.join(m['pillars'])}")
            if m.get("objection_handling"):
                o.append(f"*Objections:* {'; '.join(m['objection_handling'])}")
            o.append("")

    # CONTENT
    ce = a.get("content_engine") or {}
    if any(v for v in ce.values()):
        o.append("### Content Engine")
        if ce.get("cadence"):
            o.append(f"- **Cadence:** {ce['cadence']}")
        if ce.get("distribution_strategy"):
            o.append(f"- **Distribution:** {ce['distribution_strategy']}")
        for lbl, k in [("TOFU", "tofu"), ("MOFU", "mofu"), ("BOFU", "bofu")]:
            if ce.get(k):
                o.append(f"- **{lbl}:** {'; '.join(ce[k])}")
        o.append("")

    # SALES
    sp = x.get("sales_playbook") or {}
    if sp.get("stages") or sp.get("qualification_framework"):
        o.append("### Sales Playbook")
        if sp.get("qualification_framework"):
            o.append(f"*Qualification:* {sp['qualification_framework']}")
        if sp.get("stages"):
            o.append("| Stage | Objective | Exit criteria |")
            o.append("|---|---|---|")
            for st in sp["stages"]:
                o.append(f"| {st.get('stage','')} | {st.get('objective','')} | {st.get('exit_criteria','')} |")
        if sp.get("must_have_collateral"):
            o.append(f"*Must-have collateral:* {'; '.join(sp['must_have_collateral'])}")
        o.append("")

    # DEMAND
    dg = x.get("demand_gen") or {}
    if dg.get("levers") or dg.get("campaign_concepts"):
        o.append("### Demand-Gen Mix")
        for lv in dg.get("levers", []):
            o.append(f"- **{lv.get('lever','')}:** {lv.get('logic','')}")
        if dg.get("campaign_concepts"):
            o.append(f"*Campaigns:* {'; '.join(dg['campaign_concepts'])}")
        o.append("")

    # MEASURE
    me = x.get("metrics") or {}
    if me.get("north_star_metric") or me.get("input_metrics"):
        o.append("### Metrics & North Star")
        if me.get("north_star_metric"):
            o.append(f"**North-star metric:** {me['north_star_metric']}")
            if me.get("north_star_why"):
                o.append(f"_{me['north_star_why']}_")
        for label, key in [("Input metrics", "input_metrics"), ("Funnel KPIs", "funnel_kpis"),
                           ("Health metrics", "health_metrics")]:
            rows = me.get(key) or []
            if rows:
                o.append(f"\n*{label}*")
                o.append("| Metric | Target band | Cadence |")
                o.append("|---|---|---|")
                for mt in rows:
                    o.append(f"| {mt.get('metric','')} | {mt.get('target_band','')} | {mt.get('cadence','')} |")
        o.append("")

    # EXECUTE
    rm = x.get("roadmap_90day") or []
    if rm:
        o.append("### 90-Day Execution Roadmap")
        for ph in rm:
            o.append(f"#### {ph.get('phase','')}")
            if ph.get("objective"):
                o.append(f"*Objective:* {ph['objective']}")
            if ph.get("workstreams"):
                o.append("| Workstream | Deliverable | Owner | Success signal |")
                o.append("|---|---|---|---|")
                for w in ph["workstreams"]:
                    o.append(f"| {w.get('workstream','')} | {w.get('deliverable','')} | "
                             f"{w.get('owner','')} | {w.get('success_signal','')} |")
            o.append("")

    # RISK
    rk = x.get("risks") or []
    if rk:
        o.append("### Strategic Risks & Mitigations")
        o.append("| Risk | Likelihood | Impact | Mitigation | Owner |")
        o.append("|---|---|---|---|---|")
        for r in rk:
            o.append(f"| {r.get('risk','')} | {r.get('likelihood','')} | {r.get('impact','')} | "
                     f"{r.get('mitigation','')} | {r.get('owner','')} |")
        o.append("")
    return o


def _content_md(c):
    """Render the content bundle as markdown."""
    o = [f"## Marketing Content (Phase {c.get('phase','A')})", ""]
    if c.get("positioning_line"):
        o.append(f"**Positioning:** {c['positioning_line']}")
    if c.get("messaging_pillars"):
        o.append(f"**Messaging pillars:** {', '.join(c['messaging_pillars'])}")
    o.append("")

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    if c.get("linkedin_posts"):
        o.append("### LinkedIn Posts")
        o.append("")
        for i, p in enumerate(c["linkedin_posts"], 1):
            kind_label = p.get('kind', 'POST').replace('_', ' ').title()
            o.append(f"#### {i}. {kind_label}")
            o.append("")
            o.append(f"**Hook:** {p.get('hook', '')}")
            o.append("")
            o.append(p.get("body", ""))
            o.append("")
            if p.get("engagement_question"):
                o.append(f"*{p['engagement_question']}*")
                o.append("")
            if p.get("cta"):
                o.append(f"**→ {p['cta']}**")
            tags = " ".join(p.get("hashtags", []))
            if tags:
                o.append(f"{tags}")
            o.append("")
            o.append("---")
            o.append("")

    # ── Blog ──────────────────────────────────────────────────────────────────
    if c.get("blog_drafts"):
        o.append("### Blog Articles")
        o.append("")
        for b in c["blog_drafts"]:
            kind_label = b.get('kind', 'BLOG').title()
            o.append(f"#### {kind_label}: {b.get('title', '')}")
            o.append("")
            if b.get("target_keyword"):
                o.append(f"**Primary keyword:** `{b['target_keyword']}`")
            if b.get("secondary_keywords"):
                o.append(f"**Secondary keywords:** {', '.join(b['secondary_keywords'])}")
            if b.get("meta_description"):
                o.append(f"**Meta description:** _{b['meta_description']}_")
            o.append("")
            if b.get("outline"):
                o.append("**Outline:**")
                for idx, heading in enumerate(b["outline"], 1):
                    o.append(f"{idx}. {heading}")
            o.append("")
            o.append(b.get("body", ""))
            o.append("")
            if b.get("cta"):
                o.append(f"**→ {b['cta']}**")
            o.append("")
            o.append("---")
            o.append("")

    # ── Email ─────────────────────────────────────────────────────────────────
    if c.get("email_drafts"):
        o.append("### Email Campaigns")
        o.append("")
        for e in c["email_drafts"]:
            kind_label = e.get('kind', 'EMAIL').title()
            o.append(f"#### {kind_label} Email")
            o.append("")
            o.append(f"**Subject:** {e.get('subject', '')}")
            if e.get("preview"):
                o.append(f"**Preview text:** _{e['preview']}_")
            o.append("")
            o.append(e.get("body", ""))
            o.append("")
            if e.get("cta"):
                o.append(f"**[{e['cta']}]**")
            o.append("")
            o.append("---")
            o.append("")

    return o


def render_md(result: Dict[str, Any]) -> str:
    r = result["report"]
    out: List[str] = []

    plan = result.get("plan", {})
    out.append(f"# {r['title']}")
    out.append("")
    out.append(f"**Query:** {result['query']}  ")
    out.append(f"**Industry:** {plan.get('industry') or plan.get('market','')}  "
               f"|  **Subject Type:** {plan.get('subject_type','UNKNOWN')}  ")
    out.append(f"**Time:** {result['seconds']}s  ")
    _tools_used = result["plan"]["required_tools"]
    _note = ("competitive_landscape_tool includes official-site discovery"
             if "competitive_landscape_tool" in _tools_used
             else "competitive_landscape_tool was NOT run")
    out.append(f"**Tools used:** {', '.join(_tools_used)} ({_note})")
    out.append("")
    out.append("## Executive Summary")
    out.append(r["executive_summary"])
    out.append("")
    if r.get("_evidence_limitation"):
        out.append(f"> \u26a0 **{r['_evidence_limitation']}**")
        out.append("")

    sw = r["subject_swot"]
    out.append("## SWOT Analysis")
    out.append("| Strengths | Weaknesses |")
    out.append("|---|---|")
    out.append(f"| {_swot_cell(sw['strengths'])} | {_swot_cell(sw['weaknesses'])} |")
    out.append("")
    out.append("| Opportunities | Threats |")
    out.append("|---|---|")
    out.append(f"| {_swot_cell(sw['opportunities'])} | {_swot_cell(sw['threats'])} |")
    out.append("")


    out.append("## Company Competitors")
    companies = r["company_competitors"]
    if not companies:
        out.append("_None sufficiently sourced._")
        out.append("")
    else:
        out.append("| Name | Directness | Business Model | Revenue Model | "
                   "Target Audience | Value Proposition | Positioning | "
                   "Pricing | Official Website |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for e in companies:
            out.append(
                f"| {e['name']} | {e['directness']} | {e.get('business_model') or '—'} | "
                f"{_rev_cell(e.get('revenue_models'))} | {e.get('target_audience') or '—'} | "
                f"{e.get('value_proposition') or '—'} | "
                f"{e.get('positioning') or '—'} | {e.get('pricing_signal') or '—'} | "
                f"{_site_cell(e.get('official_website',''))} |"
            )
        out.append("")

    out.append("## Competitor SWOT (Companies)")
    with_swot = [e for e in companies if e.get("swot")][:4]
    if not with_swot:
        out.append("_None sufficiently sourced._")
        out.append("")
    else:
        for e in with_swot:
            s = e["swot"]
            out.append(f"### {e['name']}")
            out.append("| Strengths | Weaknesses |")
            out.append("|---|---|")
            out.append(f"| {_swot_cell(s['strengths'])} | {_swot_cell(s['weaknesses'])} |")
            out.append("| Opportunities | Threats |")
            out.append(f"| {_swot_cell(s['opportunities'])} | {_swot_cell(s['threats'])} |")
            out.append("")

    out.append("## Competitors Products Catalog")
    products = r["product_competitors"]
    if not products:
        out.append("_None sufficiently sourced._")
        out.append("")
    else:
        out.append("| Name | Top Products | Key Features | Differentiators (USP) | "
                   "Target Audience | Pricing | Official Website |")
        out.append("|---|---|---|---|---|---|---|")
        for e in products:
            out.append(
                f"| {e['name']} | {_cell(e.get('top_products'))} | "
                f"{_cell(e.get('key_features'))} | {_cell(e.get('differentiators_usp'))} | "
                f"{e.get('target_audience') or '—'} | {e.get('pricing_signal') or '—'} | "
                f"{_site_cell(e.get('official_website',''))} |"
            )
        out.append("")

    alts = r["alternative_solutions"]
    if alts:
        out.append("## Alternative Solutions")
        out.append("| Name | Role / Approach | Official Website |")
        out.append("|---|---|---|")
        for e in alts[:2]:
            role = e.get("value_proposition") or e.get("positioning") or "—"
            out.append(f"| {e['name']} | {role} | {_site_cell(e.get('official_website',''))} |")
        out.append("")

    out.append("## Buyer Personas")
    if not r["buyer_personas"]:
        out.append("_None sufficiently sourced._")
        out.append("")
    else:
        out.append("| Persona | Role | Psychographics | Segment | Power | Goals | "
                   "Pain Points | Triggers | Objections | Social Channels | "
                   "Buying Process | Messaging |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for p in r["buyer_personas"]:
            ps = p.get("psychographics") or {}
            psy = _cell((ps.get("values") or []) + (ps.get("attitudes") or [])
                        + (ps.get("interests") or []) + (ps.get("personality_traits") or []))
            out.append(
                f"| {p['persona_name']} | {p.get('role_title') or '—'} | {psy} | "
                f"{p.get('segment') or '—'} | {p['decision_power']} | "
                f"{_cell(p['goals'])} | {_cell(p['pain_points'])} | "
                f"{_cell(p['buying_triggers'])} | {_cell(p['objections'])} | "
                f"{_cell(p.get('channels'))} | {p.get('buying_process') or '—'} | "
                f"{p.get('messaging_angle') or '—'} |"
            )
        out.append("")

    def lst(title, items):
        out.append(f"## {title}")
        if items:
            for x in items:
                out.append(f"- {x}")
        else:
            out.append("_No sourced evidence._")
        out.append("")

    lst("Market Trends", r["market_trends"])
    lst("Opportunities", r["opportunities"])
    lst("Risks", r["risks"])
    lst("Recommendations", r["recommendations"])

    if result.get("gtm_strategy"):
        out += _gtm_md(result["gtm_strategy"])

    if result.get("content"):
        out += _content_md(result["content"])

    out.append("## Sources")
    for s in result["sources"]:
        tag = "OFFICIAL " if s.get("official") else ""
        out.append(f"- [{s['id']}] {tag}{s['title']} - {s['domain']} - {s['url']}")
    # Escape bare '$' so Jupyter/Colab MathJax doesn't mangle prices.
    return "\n".join(out).replace("$", "\\$")
