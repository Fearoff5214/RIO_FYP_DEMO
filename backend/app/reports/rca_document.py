"""Root cause analysis document: problem, cause, reason, evidence, solution, traceability.

Input is the report dict built by workflow stage 7 (`compose_report`) or by the standalone
`POST /api/v1/rca/analyze` endpoint:

    report = {job_id, generated_at, part{}, defects[], measurements[],
              root_cause{cause, effect, rationale, corrective_actions, preventive_actions,
                         precautions, verification, confidence, citations, model_version,
                         edited, reviewer_id, finalized_at, status},
              rca{ranked[], evidence[]}}

Writes DOCX, PDF and Markdown next to the other reports and returns their paths.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path("tmp/reports")
DISCLAIMER = ("This analysis was drafted with AI assistance from the retrieved knowledge-base evidence. "
              "It must be reviewed and confirmed by a qualified quality expert before corrective action is taken.")


# ---- normalisation ------------------------------------------------------------------------
def _pct(value) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "n/a"


def build_view(report: dict) -> dict:
    """Flatten the report into the fields the document needs (tolerates missing data)."""
    rc = report.get("root_cause") or {}
    rca = report.get("rca") or {}
    ranked = rca.get("ranked") or []
    evidence = rca.get("evidence") or []
    by_id = {e.get("chunk_id"): e for e in evidence}
    cited = [by_id[c] for c in (rc.get("citations") or []) if c in by_id]
    primary = next((r for r in ranked if r.get("cause") == rc.get("cause")), ranked[0] if ranked else {})
    model = rc.get("model_version") or primary.get("model_version") or "not recorded"
    fallback = str(model).startswith(("fallback-fake", "fake"))
    if rc.get("reviewer_id") or rc.get("finalized_at"):
        status = "Reviewed by expert" + (f" ({rc.get('reviewer_id')})" if rc.get("reviewer_id") else "")
    else:
        status = "AI proposal, pending expert review"
    return {
        "job_id": report.get("job_id", ""),
        "generated_at": (report.get("generated_at") or datetime.now(timezone.utc).isoformat())[:19].replace("T", " "),
        "part": report.get("part") or {},
        "defects": report.get("defects") or [],
        "deviations": [m for m in (report.get("measurements") or []) if not m.get("within_tolerance", True)],
        "cause": rc.get("cause", ""),
        "reason": rc.get("rationale") or primary.get("rationale") or "No reason was recorded.",
        "effect": rc.get("effect") or primary.get("effect", ""),
        "confidence": rc.get("confidence", primary.get("confidence_cal")),
        "corrective": rc.get("corrective_actions") or primary.get("corrective_actions") or [],
        "preventive": rc.get("preventive_actions") or primary.get("preventive_actions") or [],
        "precautions": rc.get("precautions") or primary.get("precautions") or [],
        "verification": rc.get("verification") or primary.get("verification") or "",
        "evidence": cited or evidence[:3],
        "alternatives": [r for r in ranked if r.get("cause") != rc.get("cause")][:2],
        "model": model,
        "fallback": fallback,
        "edited": bool(rc.get("edited")),
        "status": status,
    }


def _safe(text) -> str:
    return "" if text is None else str(text)


# ---- Markdown -----------------------------------------------------------------------------
def to_markdown(v: dict) -> str:
    part = v["part"]
    out = [f"# Root Cause Analysis Report", "",
           f"**Part:** {part.get('part_number', '')} {part.get('part_name', '')}  ",
           f"**Material / process:** {part.get('material', '')} / {part.get('process', '')}  ",
           f"**Case:** {v['job_id']}  **Date:** {v['generated_at']}  ",
           f"**Status:** {v['status']}", ""]
    if v["fallback"]:
        out += [f"> **Warning:** the AI model was not used for this analysis ({v['model']}). The text below is a generic offline template, not a result.", ""]
    out += ["## 1. Problem", ""]
    if v["defects"]:
        out += ["| Defect | Severity | Confidence | Detail |", "|---|---|---|---|"]
        out += [f"| {d.get('defect_type', '')} | {d.get('severity', '') or '-'} | {_pct(d.get('confidence'))} | {_safe(d.get('note'))} |" for d in v["defects"]]
    else:
        out += ["No defects were listed."]
    if v["deviations"]:
        out += ["", "Out-of-tolerance measurements:", ""]
        out += [f"- {m.get('feature_id')}: {m.get('deviation', 0):+.2f} mm" for m in v["deviations"]]
    out += ["", "## 2. Root cause", "", f"**Cause:** {v['cause']}", "", f"**Reason:** {v['reason']}", "",
            f"**Effect:** {v['effect']}", "", f"**Confidence:** {_pct(v['confidence'])}", ""]
    if v["evidence"]:
        out += ["**Supporting evidence:**", ""]
        out += [f"- `{e.get('chunk_id', '')}`: {_safe(e.get('text_excerpt') or e.get('text'))[:400]}" for e in v["evidence"]]
    out += ["", "## 3. Solution", "", "### Corrective actions (fix this occurrence)", ""]
    out += [f"{i}. {a}" for i, a in enumerate(v["corrective"], 1)] or ["None recorded."]
    out += ["", "### Preventive actions (stop it recurring)", ""]
    out += [f"{i}. {a}" for i, a in enumerate(v["preventive"], 1)] or ["None recorded."]
    if v["precautions"]:
        out += ["", "### Precautions", ""] + [f"- {p}" for p in v["precautions"]]
    if v["verification"]:
        out += ["", "### How to verify the fix", "", v["verification"]]
    if v["alternatives"]:
        out += ["", "## 4. Other causes considered", "", "| Rank | Cause | Confidence | Reason |", "|---|---|---|---|"]
        out += [f"| {a.get('rank', '')} | {a.get('cause', '')} | {_pct(a.get('confidence_cal'))} | {_safe(a.get('rationale'))[:200]} |" for a in v["alternatives"]]
    out += ["", "## 5. Traceability", "", f"- AI model: {v['model']}",
            f"- Expert edited the cause: {'yes' if v['edited'] else 'no'}", f"- {DISCLAIMER}", ""]
    return "\n".join(out)


# ---- DOCX ---------------------------------------------------------------------------------
def to_docx(v: dict, path: Path) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(10.5)

    def shade(cell, color):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), color)
        tcPr.append(shd)

    def table(rows, widths, head="DCE6F2"):
        t = doc.add_table(rows=len(rows), cols=len(rows[0]))
        t.style = "Table Grid"
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                c = t.cell(ri, ci)
                c.width = Cm(widths[ci])
                c.text = ""
                r = c.paragraphs[0].add_run(_safe(val))
                r.font.size = Pt(9)
                r.bold = ri == 0
                if ri == 0:
                    shade(c, head)
        doc.add_paragraph()

    def labelled(label, text):
        p = doc.add_paragraph()
        r = p.add_run(f"{label}  ")
        r.bold = True
        p.add_run(_safe(text))

    title = doc.add_heading("Root Cause Analysis Report", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    part = v["part"]
    table([["Part", f"{part.get('part_number', '')} {part.get('part_name', '')}".strip()],
           ["Material / process", f"{part.get('material', '')} / {part.get('process', '')}"],
           ["Case", v["job_id"]], ["Date", v["generated_at"]], ["Status", v["status"]]], [4.0, 13.0], head="FFFFFF")
    if v["fallback"]:
        p = doc.add_paragraph()
        r = p.add_run(f"WARNING: the AI model was not used for this analysis ({v['model']}). "
                      "The text below is a generic offline template, not a result.")
        r.bold = True
        r.font.color.rgb = RGBColor(0xB0, 0x1E, 0x2E)

    doc.add_heading("1. Problem", 1)
    if v["defects"]:
        table([["Defect", "Severity", "Confidence", "Detail"]] +
              [[d.get("defect_type", ""), d.get("severity") or "-", _pct(d.get("confidence")), _safe(d.get("note"))] for d in v["defects"]],
              [3.5, 2.5, 2.5, 8.5])
    else:
        doc.add_paragraph("No defects were listed.")
    if v["deviations"]:
        doc.add_paragraph("Out-of-tolerance measurements:")
        for m in v["deviations"]:
            doc.add_paragraph(f"{m.get('feature_id')}: {m.get('deviation', 0):+.2f} mm", style="List Bullet")

    doc.add_heading("2. Root cause", 1)
    labelled("Cause:", v["cause"])
    labelled("Reason:", v["reason"])
    labelled("Effect:", v["effect"])
    labelled("Confidence:", _pct(v["confidence"]))
    if v["evidence"]:
        doc.add_paragraph().add_run("Supporting evidence").bold = True
        for e in v["evidence"]:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"{e.get('chunk_id', '')}: ").bold = True
            p.add_run(_safe(e.get("text_excerpt") or e.get("text"))[:400])

    doc.add_heading("3. Solution", 1)
    doc.add_heading("Corrective actions (fix this occurrence)", 2)
    for a in v["corrective"] or ["None recorded."]:
        doc.add_paragraph(_safe(a), style="List Number")
    doc.add_heading("Preventive actions (stop it recurring)", 2)
    for a in v["preventive"] or ["None recorded."]:
        doc.add_paragraph(_safe(a), style="List Number")
    if v["precautions"]:
        doc.add_heading("Precautions", 2)
        for a in v["precautions"]:
            doc.add_paragraph(_safe(a), style="List Bullet")
    if v["verification"]:
        doc.add_heading("How to verify the fix", 2)
        doc.add_paragraph(v["verification"])

    if v["alternatives"]:
        doc.add_heading("4. Other causes considered", 1)
        table([["Rank", "Cause", "Confidence", "Reason"]] +
              [[a.get("rank", ""), a.get("cause", ""), _pct(a.get("confidence_cal")), _safe(a.get("rationale"))[:300]] for a in v["alternatives"]],
              [1.5, 4.5, 2.5, 8.5])

    doc.add_heading("5. Traceability", 1)
    doc.add_paragraph(f"AI model: {v['model']}", style="List Bullet")
    doc.add_paragraph(f"Expert edited the cause: {'yes' if v['edited'] else 'no'}", style="List Bullet")
    note = doc.add_paragraph()
    r = note.add_run(DISCLAIMER)
    r.italic = True
    r.font.size = Pt(9)
    doc.save(str(path))


# ---- PDF ----------------------------------------------------------------------------------
def _pdf_text(text) -> str:
    """Escape for ReportLab markup and replace characters Helvetica cannot draw."""
    s = html.escape(_safe(text))
    for a, b in (("≈", "~"), ("≤", "<="), ("≥", ">="), ("→", "->"), ("°", " deg"), ("–", "-"), ("—", "-"), ("’", "'")):
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


def to_pdf(v: dict, path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    cell = styles["Normal"].clone("cell", fontSize=8.5, leading=10.5)
    story = [Paragraph("Root Cause Analysis Report", styles["Title"])]
    part = v["part"]

    def tbl(rows, widths, head=colors.HexColor("#DCE6F2")):
        data = [[Paragraph(_pdf_text(c), cell) for c in row] for row in rows]
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), head),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    story += [tbl([["Part", f"{part.get('part_number', '')} {part.get('part_name', '')}"],
                   ["Material / process", f"{part.get('material', '')} / {part.get('process', '')}"],
                   ["Case", v["job_id"]], ["Date", v["generated_at"]], ["Status", v["status"]]], [110, 360], colors.white), Spacer(1, 8)]
    if v["fallback"]:
        story += [Paragraph(f"<b>WARNING:</b> {_pdf_text('the AI model was not used for this analysis (' + v['model'] + '). The text below is a generic offline template, not a result.')}", styles["Normal"]), Spacer(1, 6)]
    story.append(Paragraph("1. Problem", styles["Heading2"]))
    if v["defects"]:
        story.append(tbl([["Defect", "Severity", "Confidence", "Detail"]] +
                         [[d.get("defect_type", ""), d.get("severity") or "-", _pct(d.get("confidence")), _safe(d.get("note"))] for d in v["defects"]],
                         [90, 70, 70, 240]))
    else:
        story.append(Paragraph("No defects were listed.", styles["Normal"]))
    for m in v["deviations"]:
        story.append(Paragraph(f"- {_pdf_text(m.get('feature_id'))}: {m.get('deviation', 0):+.2f} mm", styles["Normal"]))
    story.append(Paragraph("2. Root cause", styles["Heading2"]))
    for label, text in (("Cause", v["cause"]), ("Reason", v["reason"]), ("Effect", v["effect"]), ("Confidence", _pct(v["confidence"]))):
        story.append(Paragraph(f"<b>{label}:</b> {_pdf_text(text)}", styles["Normal"]))
        story.append(Spacer(1, 3))
    if v["evidence"]:
        story.append(Paragraph("<b>Supporting evidence</b>", styles["Normal"]))
        for e in v["evidence"]:
            story.append(Paragraph(f"- <b>{_pdf_text(e.get('chunk_id'))}</b>: {_pdf_text((e.get('text_excerpt') or e.get('text') or '')[:400])}", styles["Normal"]))
    story.append(Paragraph("3. Solution", styles["Heading2"]))
    story.append(Paragraph("Corrective actions (fix this occurrence)", styles["Heading3"]))
    for i, a in enumerate(v["corrective"] or ["None recorded."], 1):
        story.append(Paragraph(f"{i}. {_pdf_text(a)}", styles["Normal"]))
    story.append(Paragraph("Preventive actions (stop it recurring)", styles["Heading3"]))
    for i, a in enumerate(v["preventive"] or ["None recorded."], 1):
        story.append(Paragraph(f"{i}. {_pdf_text(a)}", styles["Normal"]))
    if v["precautions"]:
        story.append(Paragraph("Precautions", styles["Heading3"]))
        for a in v["precautions"]:
            story.append(Paragraph(f"- {_pdf_text(a)}", styles["Normal"]))
    if v["verification"]:
        story.append(Paragraph("How to verify the fix", styles["Heading3"]))
        story.append(Paragraph(_pdf_text(v["verification"]), styles["Normal"]))
    if v["alternatives"]:
        story.append(Paragraph("4. Other causes considered", styles["Heading2"]))
        story.append(tbl([["Rank", "Cause", "Confidence", "Reason"]] +
                         [[a.get("rank", ""), a.get("cause", ""), _pct(a.get("confidence_cal")), _safe(a.get("rationale"))[:300]] for a in v["alternatives"]],
                         [35, 120, 60, 255]))
    story.append(Paragraph("5. Traceability", styles["Heading2"]))
    story.append(Paragraph(f"AI model: {_pdf_text(v['model'])}. Expert edited the cause: {'yes' if v['edited'] else 'no'}.", styles["Normal"]))
    story.append(Paragraph(f"<i>{_pdf_text(DISCLAIMER)}</i>", styles["Normal"]))
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50).build(story)


# ---- entry point --------------------------------------------------------------------------
async def render_rca_documents(report: dict, out_dir: Path | None = None, stem: str | None = None) -> dict[str, str]:
    """Write DOCX, PDF and Markdown RCA documents; returns {docx, pdf, md} paths."""
    out_dir = Path(out_dir or REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or f"{report.get('job_id', 'unknown')}_rca"
    view = build_view(report)
    paths = {"docx": out_dir / f"{stem}.docx", "pdf": out_dir / f"{stem}.pdf", "md": out_dir / f"{stem}.md"}
    paths["md"].write_text(to_markdown(view), encoding="utf-8")
    to_docx(view, paths["docx"])
    to_pdf(view, paths["pdf"])
    return {k: str(p) for k, p in paths.items()}
