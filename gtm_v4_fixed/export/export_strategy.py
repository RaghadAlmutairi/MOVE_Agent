# -*- coding: utf-8 -*-
"""Dedicated GTM-Strategy PDF: research-style navy cover (NO confidence field),
then the full Foundation / Activation / Execution strategy."""
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak)

from utils.textutil import _san

NAVY = colors.HexColor("#1E2761")
ICE = colors.HexColor("#CADCFC")
INK = colors.HexColor("#212934")
LINE = colors.HexColor("#D6DCE8")
HEAD = colors.HexColor("#EEF2FB")


def _esc(x: Any) -> str:
    return (_san(str(x if x is not None else ""))
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _styles():
    ss = getSampleStyleSheet()
    S = {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontSize=15, textColor=NAVY,
                             spaceBefore=12, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.5, textColor=NAVY,
                             spaceBefore=8, spaceAfter=2),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.5, textColor=INK,
                               leading=13, spaceAfter=4),
        "th": ParagraphStyle("th", parent=ss["BodyText"], fontSize=8.5, textColor=NAVY,
                             leading=11),
        "td": ParagraphStyle("td", parent=ss["BodyText"], fontSize=8.5, textColor=INK,
                             leading=11),
        "kicker": ParagraphStyle("kicker", parent=ss["BodyText"], fontSize=8.5,
                                 textColor=colors.HexColor("#5A6472")),
    }
    return S


def _tbl(hdrs: List[str], rows: List[List[str]], ws, S):
    data = [[Paragraph(_esc(h), S["th"]) for h in hdrs]]
    for r in rows:
        data.append([Paragraph(_esc(c), S["td"]) for c in r])
    t = Table(data, colWidths=ws, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def export_strategy_pdf(result: Dict[str, Any], path: Optional[str] = None) -> Optional[str]:
    gtm = result.get("gtm_strategy") or {}
    if not gtm:
        return None
    plan = result.get("plan", {}) or {}
    report = result.get("report", {}) or {}
    name = plan.get("subject_entity") or report.get("title") or "Market"
    sector = plan.get("industry") or plan.get("market") or ""
    f = gtm.get("foundation", {}) or {}
    a = gtm.get("activation", {}) or {}
    x = gtm.get("execution", {}) or {}
    subtitle = gtm.get("north_star") or f.get("north_star") or "Go-To-Market Strategy"

    out = path or os.path.join("exports", "pdf",
                               f"gtm_strategy_{name.lower().replace(' ', '_')[:40]}.pdf")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    S = _styles()

    def _cover(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.setFillColor(ICE)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(22 * mm, h - 70 * mm, "GO-TO-MARKET STRATEGY")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 34)
        canvas.drawString(22 * mm, h - 92 * mm, _san(name)[:42])
        canvas.setFillColor(ICE)
        canvas.setFont("Helvetica", 13)
        # wrap subtitle
        words, line, y = _san(subtitle).split(), "", h - 108 * mm
        for word in words:
            if canvas.stringWidth(line + " " + word, "Helvetica", 13) > (w - 44 * mm):
                canvas.drawString(22 * mm, y, line.strip()); y -= 7 * mm; line = word
            else:
                line += " " + word
        if line.strip():
            canvas.drawString(22 * mm, y, line.strip())
        canvas.setFont("Helvetica", 10)
        canvas.drawString(22 * mm, 22 * mm, f"{_san(sector)}   |   {datetime.now():%B %Y}")
        canvas.restoreState()

    fl: List[Any] = [Spacer(1, 1), PageBreak()]

    def H(t):
        fl.append(Paragraph(_esc(t), S["h1"]))

    def P(t):
        if t:
            fl.append(Paragraph(t, S["body"]))

    # STRATEGY
    H("Strategy")
    P(f"<b>Positioning.</b> {_esc(f.get('positioning_statement',''))}")
    sl = f.get("slot_statement") or {}
    for k in ("for_who", "who_need", "category", "promise", "unlike", "proof"):
        if sl.get(k):
            P(f"<b>{k.replace('_',' ').title()}:</b> {_esc(sl[k])}")

    # CUSTOMER
    icp = f.get("icp") or {}
    if any(icp.values()):
        H("Customer - Ideal Customer Profile")
        for k in ("primary_segment", "firmographics", "technographics", "why_now"):
            if icp.get(k):
                P(f"<b>{k.replace('_',' ').title()}:</b> {_esc(icp[k])}")
        if icp.get("buying_committee"):
            P(f"<b>Buying committee:</b> {_esc('; '.join(icp['buying_committee']))}")
    for lbl, key in [("Top pains", "top_pains"), ("Trigger events", "trigger_events"),
                     ("Disqualifiers", "disqualifiers"), ("Secondary segments", "secondary_segments")]:
        if f.get(key):
            P(f"<b>{lbl}:</b> {_esc('; '.join(f[key]))}")

    # PLAN - Beachhead
    bh = f.get("beachhead") or {}
    if any(bh.values()):
        H("Plan - Beachhead Strategy")
        P(f"<b>Segment:</b> {_esc(bh.get('segment',''))}")
        P(f"<b>Rationale:</b> {_esc(bh.get('rationale',''))}")
        P(f"<b>Entry wedge:</b> {_esc(bh.get('entry_wedge',''))}")
        if bh.get("expansion_path"):
            P(f"<b>Expansion path:</b> {_esc(' -> '.join(bh['expansion_path']))}")
        P(f"<b>Market sizing:</b> {_esc(bh.get('market_sizing_logic',''))}")

    # EDGE
    diffs = f.get("competitive_differentiation") or []
    if diffs:
        H("Edge - Competitive Differentiation")
        rows = [[d.get("competitor", ""), "; ".join(d.get("where_we_win", [])),
                 "; ".join(d.get("where_they_win", [])), d.get("sharpest_message", "")]
                for d in diffs]
        fl.append(_tbl(["Competitor", "Where we win", "Where they win", "Sharpest message"],
                       rows, [30 * mm, 50 * mm, 40 * mm, 54 * mm], S))

    # COMMERCIAL
    pr = a.get("pricing") or {}
    if any(v for v in pr.values()):
        H("Commercial - Offer & Pricing")
        P(f"<b>Packaging:</b> {_esc(pr.get('packaging_logic',''))}")
        if pr.get("tiers"):
            P(f"<b>Tiers:</b> {_esc('; '.join(pr['tiers']))}")
        P(f"<b>Anchor:</b> {_esc(pr.get('anchor_strategy',''))}  |  "
          f"<b>Motion:</b> {_esc(pr.get('commercial_motion',''))}")
        if pr.get("pricing_levers"):
            P(f"<b>Levers:</b> {_esc('; '.join(pr['pricing_levers']))}")
        if pr.get("pricing_risks"):
            P(f"<b>Risks:</b> {_esc('; '.join(pr['pricing_risks']))}")

    # MOTION
    mo = a.get("motion") or {}
    if any(v for v in mo.values()):
        H("Motion - GTM Motion")
        P(f"<b>Primary:</b> {_esc(mo.get('primary',''))}  |  <b>Secondary:</b> {_esc(mo.get('secondary',''))}")
        P(f"<b>Rationale:</b> {_esc(mo.get('rationale',''))}")
        if mo.get("motion_risks"):
            P(f"<b>Risks:</b> {_esc('; '.join(mo['motion_risks']))}")

    # CHANNELS
    ch = a.get("channel_plays") or []
    if ch:
        H("Channels - Channel Plays")
        rows = [[c.get("channel", ""), c.get("funnel_role", ""),
                 c.get("leading_indicator", ""), c.get("invest", "")] for c in ch]
        fl.append(_tbl(["Channel", "Funnel role", "Leading indicator", "Invest"],
                       rows, [54 * mm, 30 * mm, 60 * mm, 20 * mm], S))

    # MESSAGING
    msg = a.get("messaging_by_persona") or []
    if msg:
        H("Messaging by Persona")
        for m in msg:
            fl.append(Paragraph(f"<b>{_esc(m.get('persona',''))}</b> - {_esc(m.get('core_promise',''))}", S["h2"]))
            P(f"<i>Channel:</i> {_esc(m.get('primary_channel',''))} &nbsp; <i>CTA:</i> {_esc(m.get('cta',''))}")
            if m.get("pillars"):
                P(f"<i>Pillars:</i> {_esc('; '.join(m['pillars']))}")
            if m.get("objection_handling"):
                P(f"<i>Objections:</i> {_esc('; '.join(m['objection_handling']))}")

    # CONTENT
    ce = a.get("content_engine") or {}
    if any(v for v in ce.values()):
        H("Content Engine")
        P(f"<b>Cadence:</b> {_esc(ce.get('cadence',''))}")
        P(f"<b>Distribution:</b> {_esc(ce.get('distribution_strategy',''))}")
        for lbl, k in [("TOFU", "tofu"), ("MOFU", "mofu"), ("BOFU", "bofu")]:
            if ce.get(k):
                P(f"<b>{lbl}:</b> {_esc('; '.join(ce[k]))}")

    # SALES
    sp = x.get("sales_playbook") or {}
    if sp.get("stages") or sp.get("qualification_framework"):
        H("Sales Playbook")
        P(f"<b>Qualification:</b> {_esc(sp.get('qualification_framework',''))}")
        if sp.get("stages"):
            rows = [[st.get("stage", ""), st.get("objective", ""), st.get("exit_criteria", "")]
                    for st in sp["stages"]]
            fl.append(_tbl(["Stage", "Objective", "Exit criteria"],
                           rows, [30 * mm, 70 * mm, 74 * mm], S))
        if sp.get("must_have_collateral"):
            P(f"<b>Must-have collateral:</b> {_esc('; '.join(sp['must_have_collateral']))}")

    # DEMAND
    dg = x.get("demand_gen") or {}
    if dg.get("levers") or dg.get("campaign_concepts"):
        H("Demand-Gen Mix")
        for lv in dg.get("levers", []):
            P(f"<b>{_esc(lv.get('lever',''))}:</b> {_esc(lv.get('logic',''))}")
        if dg.get("campaign_concepts"):
            P(f"<b>Campaigns:</b> {_esc('; '.join(dg['campaign_concepts']))}")

    # MEASURE
    me = x.get("metrics") or {}
    if me.get("north_star_metric") or me.get("input_metrics"):
        H("Metrics & North Star")
        P(f"<b>North-star metric:</b> {_esc(me.get('north_star_metric',''))} - {_esc(me.get('north_star_why',''))}")
        for lbl, key in [("Input metrics", "input_metrics"), ("Funnel KPIs", "funnel_kpis"),
                         ("Health metrics", "health_metrics")]:
            rows = me.get(key) or []
            if rows:
                fl.append(Paragraph(_esc(lbl), S["h2"]))
                fl.append(_tbl(["Metric", "Target band", "Cadence"],
                               [[m.get("metric", ""), m.get("target_band", ""), m.get("cadence", "")]
                                for m in rows], [84 * mm, 50 * mm, 40 * mm], S))

    # EXECUTE
    rm = x.get("roadmap_90day") or []
    if rm:
        H("90-Day Execution Roadmap")
        for ph in rm:
            fl.append(Paragraph(f"{_esc(ph.get('phase',''))} - {_esc(ph.get('objective',''))}", S["h2"]))
            if ph.get("workstreams"):
                rows = [[w.get("workstream", ""), w.get("deliverable", ""),
                         w.get("owner", ""), w.get("success_signal", "")] for w in ph["workstreams"]]
                fl.append(_tbl(["Workstream", "Deliverable", "Owner", "Success signal"],
                               rows, [34 * mm, 60 * mm, 30 * mm, 50 * mm], S))

    # RISK
    rk = x.get("risks") or []
    if rk:
        H("Strategic Risks & Mitigations")
        rows = [[r.get("risk", ""), r.get("likelihood", ""), r.get("impact", ""),
                 r.get("mitigation", ""), r.get("owner", "")] for r in rk]
        fl.append(_tbl(["Risk", "Likelihood", "Impact", "Mitigation", "Owner"],
                       rows, [44 * mm, 20 * mm, 18 * mm, 60 * mm, 32 * mm], S))

    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=16 * mm)
    doc.build(fl, onFirstPage=_cover)
    print(f"   \u2713 Strategy PDF written: {out}")
    return out
