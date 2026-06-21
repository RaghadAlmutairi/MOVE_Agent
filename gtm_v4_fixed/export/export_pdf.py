"""Pure-reportlab PDF export (MOVE-branded cover). No LLM."""
import re
from datetime import datetime
from typing import Any, Dict, Optional, List

from utils.textutil import _san, _esc


try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, PageBreak, HRFlowable)
    _RL = True
except ImportError:
    _RL = False
    print("   ⚠ reportlab not installed - PDF export disabled (pip install reportlab)")

if _RL:
    _INK = colors.HexColor("#111111")
    _BLUE = colors.HexColor("#2563eb")
    _NAVY = colors.HexColor("#002b5c")
    _LINE = colors.HexColor("#2563eb")
    _HEAD = colors.HexColor("#eaf2ff")
    _GREY = colors.HexColor("#5b6573")
    _MUTE = colors.HexColor("#9fb6da")

    def _ps():
        return {
            "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15,
                leading=19, textColor=_NAVY, spaceAfter=8),
            "kicker": ParagraphStyle("k", fontName="Helvetica-Bold", fontSize=8,
                leading=11, textColor=_BLUE, spaceBefore=14, spaceAfter=2),
            "body": ParagraphStyle("b", fontName="Helvetica", fontSize=9.5,
                leading=14, textColor=_INK, spaceAfter=5),
            "small": ParagraphStyle("sm", fontName="Helvetica", fontSize=8,
                leading=11, textColor=_INK),
            "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8,
                leading=11, textColor=_NAVY),
            "td": ParagraphStyle("td", fontName="Helvetica", fontSize=8,
                leading=11, textColor=_INK),
        }

    def _rule(color=_LINE, w=0.6, sa=10, sb=0):
        return HRFlowable(width="100%", thickness=w, color=color, spaceAfter=sa, spaceBefore=sb)

    def _section(kicker, title, S):
        return [Paragraph(_esc(kicker).upper(), S["kicker"]),
                Paragraph(_esc(title), S["h1"]), _rule(_NAVY, 1.2, sa=8)]

    def _swot_para(items) -> str:
        if not items:
            return "-"
        out = []
        for it in items:
            cites = "".join(f"[{c}]" for c in (it.get("source_ids") or []))
            out.append(f"- {_esc(it.get('point'))} {_esc(cites)}".strip())
        return "<br/>".join(out)

    def _join(xs) -> str:
        return _esc("; ".join(xs)) if xs else "-"

    def _tbl(hdrs, rows, ws, S):
        data = [[Paragraph(_esc(h), S["th"]) for h in hdrs]]
        for r in rows:
            data.append([Paragraph(c if isinstance(c, str) and "<br/>" in c else _esc(c),
                                   S["td"]) for c in r])
        t = Table(data, colWidths=ws, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _HEAD),
            ("LINEBELOW", (0, 0), (-1, 0), 1.0, _NAVY),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, _LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(_BLUE); canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 12 * mm, 192 * mm, 12 * mm)
        canvas.setFont("Helvetica-Bold", 8); canvas.setFillColor(_NAVY)
        canvas.drawString(18 * mm, 8 * mm, "MOVE")
        canvas.setFont("Helvetica", 7.5); canvas.setFillColor(_INK)
        canvas.drawRightString(192 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def _wrap_lines(canvas, text, font, size, max_w):
        out, cur = [], ""
        for word in (text or "").split():
            trial = (cur + " " + word).strip()
            if canvas.stringWidth(trial, font, size) <= max_w or not cur:
                cur = trial
            else:
                out.append(cur); cur = word
        if cur:
            out.append(cur)
        return out

    def _fit_size(canvas, text, font, max_w, start, floor=20):
        size = start
        while size > floor and canvas.stringWidth(text, font, size) > max_w:
            size -= 1
        return size

    def _clean_descriptor(title, entity):
        t = re.sub(r"\(.*?\)", "", title or "")
        if entity and t.lower().startswith(entity.lower()):
            t = t[len(entity):]
        t = re.sub(r"^[\s:\|\u00b7\u2010-\u2015\-]+", "", t)
        t = re.sub(r"\s{2,}", " ", t).strip(" \u2013\u2014-")
        return t or "Competitive Landscape & Strategy"

    def _label(canvas, x, y, label, value, val_w):
        canvas.setFillColor(_GREY)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(x, y, label.upper())
        canvas.setFillColor(_NAVY)
        canvas.setFont("Helvetica", 11.5)
        yy = y - 6 * mm
        for ln in _wrap_lines(canvas, value or "-", "Helvetica", 11.5, val_w)[:2]:
            canvas.drawString(x, yy, ln)
            yy -= 5.4 * mm
        return yy

    def _make_cover(hero, descriptor, sector, datestr):
        def _cover(canvas, doc):
            w, h = A4
            mL = 20 * mm
            inner = w - 40 * mm
            canvas.saveState()

            band_h = 150 * mm
            canvas.setFillColor(_NAVY)
            canvas.rect(0, h - band_h, w, band_h, fill=1, stroke=0)
            canvas.setFillColor(_BLUE)
            canvas.rect(0, h - band_h - 2.5 * mm, w, 2.5 * mm, fill=1, stroke=0)

            canvas.setFillColor(_MUTE)
            canvas.setFont("Helvetica-Bold", 10.5)
            canvas.drawString(mL, h - 32 * mm, "MARKET INTELLIGENCE REPORT")
            canvas.setStrokeColor(_BLUE); canvas.setLineWidth(2.5)
            canvas.line(mL, h - 37 * mm, mL + 22 * mm, h - 37 * mm)

            hsize = _fit_size(canvas, hero, "Helvetica-Bold", inner, 44, floor=24)
            canvas.setFillColor(colors.white)
            canvas.setFont("Helvetica-Bold", hsize)
            y = h - 64 * mm
            for ln in _wrap_lines(canvas, hero, "Helvetica-Bold", hsize, inner)[:2]:
                canvas.drawString(mL, y, ln)
                y -= (hsize + 6)

            canvas.setFillColor(_MUTE)
            canvas.setFont("Helvetica", 16)
            y -= 4 * mm
            for ln in _wrap_lines(canvas, descriptor, "Helvetica", 16, inner)[:2]:
                canvas.drawString(mL, y, ln)
                y -= 22

            mb = h - band_h - 26 * mm
            canvas.setStrokeColor(colors.HexColor("#d4dbe6")); canvas.setLineWidth(0.8)
            canvas.line(mL, mb + 9 * mm, w - mL, mb + 9 * mm)
            _label(canvas, mL, mb, "Date", datestr, inner)
            _label(canvas, mL, mb - 22 * mm, "Sector", sector, inner)

            canvas.setStrokeColor(_BLUE); canvas.setLineWidth(1.2)
            canvas.line(mL, 34 * mm, w - mL, 34 * mm)
            canvas.setFillColor(_NAVY)
            canvas.setFont("Helvetica-Bold", 30)
            canvas.drawString(mL, 20 * mm, "MOVE")
            canvas.setFillColor(_GREY)
            canvas.setFont("Helvetica", 8.5)
            canvas.drawString(mL, 14 * mm, "Strategic Market Intelligence")
            canvas.restoreState()
        return _cover


def Market_report_analysis(result: Dict[str, Any], path: Optional[str] = None) -> Optional[str]:
    """Render the approved result dict to a styled, MOVE-branded PDF. NO LLM."""
    if not _RL:
        print("reportlab not available - cannot export PDF."); return None
    r = result["report"]
    plan = result.get("plan", {})
    entity = plan.get("subject_entity") or r.get("title") or "Market Analysis"
    category = plan.get("industry") or plan.get("market", "")
    sources = result.get("sources", [])
    path = path or f"market_analysis_{re.sub(r'[^a-z0-9]+','_',entity.lower())[:30]}.pdf"

    S = _ps()
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            title=f"Market Analysis - {entity}", author="MOVE")
    fl = []

    # Hero = the lead part of the title (a "Name - tagline" split happens ONLY on a
    # SPACED dash, never an in-word hyphen like "AI-Powered"), falling back to entity.
    _title = (r.get("title") or entity or "").strip()
    cover_hero = _san(re.sub(r"\s+[-\u2013\u2014]\s+.*$", "", _title).strip() or entity)
    cover_desc = _san(_clean_descriptor(_title, cover_hero))
    cover_sector = _san(category)
    cover_date = f"{datetime.now():%B %Y}"
    fl.append(Spacer(1, 1))
    fl.append(PageBreak())

    fl += _section("Overview", "Executive Summary", S)
    fl.append(Paragraph(_esc(r.get("executive_summary", "")), S["body"]))

    sw = r.get("subject_swot", {})
    fl += _section("Position", "SWOT Analysis", S)
    fl.append(_tbl(["Strengths", "Weaknesses"],
                   [[_swot_para(sw.get("strengths")), _swot_para(sw.get("weaknesses"))]],
                   [87 * mm, 87 * mm], S))
    fl.append(Spacer(1, 4))
    fl.append(_tbl(["Opportunities", "Threats"],
                   [[_swot_para(sw.get("opportunities")), _swot_para(sw.get("threats"))]],
                   [87 * mm, 87 * mm], S))


    if r.get("product_competitors"):
        fl += _section("Landscape", "Competitors Products Catalog", S)
        rows = [[e.get("name"), _join(e.get("top_products")),
                 _join(e.get("key_features")), _join(e.get("differentiators_usp")),
                 e.get("target_audience") or "-", e.get("pricing_signal") or "-"]
                for e in r["product_competitors"]]
        fl.append(_tbl(["Name", "Top Products", "Key Features",
                        "Differentiators (USP)", "Audience", "Pricing"],
                       rows, [22 * mm, 30 * mm, 38 * mm, 40 * mm, 24 * mm, 20 * mm], S))

    if r.get("company_competitors"):
        fl += _section("Landscape", "Company Competitors", S)
        rows = [[e.get("name"), e.get("business_model") or "-",
                 _join(e.get("revenue_models")), e.get("target_audience") or "-",
                 e.get("value_proposition") or "-"] for e in r["company_competitors"]]
        fl.append(_tbl(["Name", "Model", "Revenue", "Audience", "Value Proposition"],
                       rows, [28 * mm, 18 * mm, 38 * mm, 38 * mm, 52 * mm], S))

    if r.get("alternative_solutions"):
        fl += _section("Substitutes", "Alternative Solutions", S)
        rows = [[e.get("name"), e.get("value_proposition") or e.get("positioning") or "-"]
                for e in r["alternative_solutions"][:2]]
        fl.append(_tbl(["Name", "Role / Approach"], rows, [50 * mm, 124 * mm], S))

    # Buyer personas - two stacked tables (psychographics + buying process folded
    # in) so every column still fits A4 portrait without a separate table.
    if r.get("buyer_personas"):
        fl += _section("Demand", "Buyer Personas", S)

        def _psy(p):
            ps = p.get("psychographics") or {}
            return _join((ps.get("values") or []) + (ps.get("attitudes") or [])
                         + (ps.get("interests") or []) + (ps.get("personality_traits") or []))

        # Table 1: identity + Psychographics (before Segment) + power, goals, messaging
        rows1 = [[p.get("persona_name"), p.get("role_title") or "-", _psy(p),
                  p.get("segment") or "-", p.get("decision_power") or "-",
                  _join(p.get("goals")), p.get("messaging_angle") or "-"]
                 for p in r["buyer_personas"]]
        fl.append(_tbl(["Persona", "Role", "Psychographics", "Segment", "Power",
                        "Goals", "Messaging Angle"],
                       rows1, [24 * mm, 24 * mm, 34 * mm, 22 * mm, 14 * mm,
                               28 * mm, 28 * mm], S))
        fl.append(Spacer(1, 6))
        # Table 2: pains, triggers, objections, channels + Buying Process (after channels)
        rows2 = [[p.get("persona_name"), _join(p.get("pain_points")),
                  _join(p.get("buying_triggers")), _join(p.get("objections")),
                  _join(p.get("channels")), p.get("buying_process") or "-"]
                 for p in r["buyer_personas"]]
        fl.append(_tbl(["Persona", "Pain Points", "Buying Triggers", "Objections",
                        "Social Channels", "Buying Process"],
                       rows2, [24 * mm, 34 * mm, 30 * mm, 30 * mm, 28 * mm, 28 * mm], S))

    def _list_section(kicker, title, items):
        if not items:
            return
        fl.extend(_section(kicker, title, S))
        for x in items:
            fl.append(Paragraph("- " + _esc(x), S["body"]))

    _list_section("Signals", "Market Trends", r.get("market_trends"))
    _list_section("Upside", "Opportunities", r.get("opportunities"))
    _list_section("Watch", "Risks", r.get("risks"))
    _list_section("Action", "Recommendations", r.get("recommendations"))

    gtm = result.get("gtm_strategy") or {}
    if gtm:
        fl.append(PageBreak())
        fl += _section("Go-To-Market", "Strategy", S)
        _f = gtm.get("foundation", {}) or {}
        _a = gtm.get("activation", {}) or {}
        _x = gtm.get("execution", {}) or {}
        fl.append(Paragraph("<b>North Star:</b> " + _esc(gtm.get("north_star") or _f.get("north_star", "")), S["body"]))
        fl.append(Paragraph("<b>Positioning:</b> " + _esc(_f.get("positioning_statement", "")), S["body"]))
        _bh = _f.get("beachhead", {}) or {}
        if _bh.get("segment"):
            fl.append(Paragraph("<b>Beachhead:</b> " + _esc(_bh.get("segment", "")), S["body"]))
        if (_a.get("motion") or {}).get("primary"):
            fl.append(Paragraph("<b>GTM motion:</b> " + _esc(_a["motion"]["primary"]), S["body"]))
        if _f.get("competitive_differentiation"):
            rows = [[d.get("competitor", ""), "; ".join(d.get("where_we_win", [])),
                     d.get("sharpest_message", "")] for d in _f["competitive_differentiation"]]
            fl.append(Spacer(1, 4))
            fl.append(_tbl(["Competitor", "Where we win", "Sharpest message"], rows,
                           [38 * mm, 70 * mm, 66 * mm], S))
        if _x.get("roadmap_90day"):
            rows = [[p.get("phase", ""), p.get("objective", "")] for p in _x["roadmap_90day"]]
            fl.append(Spacer(1, 4))
            fl.append(_tbl(["Phase", "Objective"], rows, [54 * mm, 120 * mm], S))

    content = result.get("content") or {}
    if content:
        fl.append(PageBreak())
        fl += _section("Marketing", f"Content (Phase {content.get('phase', 'A')})", S)
        for p in content.get("linkedin_posts", []):
            fl.append(Paragraph("<b>LinkedIn \u2014 " + _esc(p.get("kind", "")) + ":</b> "
                                + _esc(p.get("hook", "")), S["body"]))
            fl.append(Paragraph(_esc(p.get("body", "")), S["body"]))
        for b in content.get("blog_drafts", []):
            fl.append(Paragraph("<b>Blog \u2014 " + _esc(b.get("kind", "")) + ": "
                                + _esc(b.get("title", "")) + "</b>", S["body"]))
            fl.append(Paragraph(_esc(b.get("body", "")), S["body"]))
        for e in content.get("email_drafts", []):
            fl.append(Paragraph("<b>Email \u2014 " + _esc(e.get("kind", "")) + ": "
                                + _esc(e.get("subject", "")) + "</b>", S["body"]))
            fl.append(Paragraph(_esc(e.get("body", "")), S["body"]))

    fl += _section("Evidence", "Sources", S)
    for s in sources:
        line = f"[{s['id']}] {s.get('title') or s.get('domain')} - {s.get('url')}"
        fl.append(Paragraph(_esc(line), S["small"]))

    doc.build(fl, onFirstPage=_make_cover(cover_hero, cover_desc, cover_sector, cover_date),
              onLaterPages=_footer)
    print(f"   ✓ PDF written: {path}")
    return path


export_pdf = Market_report_analysis  # backward-compatible alias
