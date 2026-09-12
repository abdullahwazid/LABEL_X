"""PDF generator module for Legal Metrology compliance screening dossiers."""

from datetime import datetime, timezone
from typing import Optional
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from src.decisions.models import ScreeningVerdict
from src.pipeline import PipelineResult
from src.rules.models import RuleStatus


def sanitize_text(text: Optional[str]) -> str:
    """Sanitizes text to ASCII/Latin-1 compatible strings for FPDF."""
    if text is None:
        return ""
    replacements = {
        "\u20b9": "Rs. ",
        "₹": "Rs. ",
        "•": "-",
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
        "✅": "[PASS]",
        "❌": "[FAIL]",
        "⚠️": "[WARN]",
        "🚨": "[ALERT]",
        "🛡️": "",
        "🔍": "",
        "📋": "",
        "⚖️": "",
        "📷": "",
        "📜": "",
        "📥": "",
        "📄": "",
        "🟢": "",
        "🔴": "",
        "🟠": "",
    }
    s = str(text)
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


class LegalMetrologyPDFReport(FPDF):
    """Custom FPDF document class with institutional legal metrology branding."""

    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_margins(left=15, top=15, right=15)
        self.set_auto_page_break(auto=True, margin=15)

    def header(self) -> None:
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(120, 120, 120)
        self.cell(
            0,
            5,
            "CONFIDENTIAL - STATUTORY SCREENING AUDIT DOSSIER",
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(
            0,
            6,
            f"LABEL-X AI Compliance Screener | Legal Metrology Rules, 2011 | Page {self.page_no()}",
            align="C",
        )


def build_pdf_report(result: PipelineResult, audit_id: str = "") -> bytes:
    """Generates a formal, multi-section Legal Metrology screening PDF report.

    Args:
        result: Evaluated PipelineResult with quality metrics, declarations, and rule outcomes.
        audit_id: Optional UUID inspection identifier.

    Returns:
        Raw bytes representing the PDF file.
    """
    pdf = LegalMetrologyPDFReport()
    pdf.add_page()

    audit_id_str = audit_id if audit_id else "UNASSIGNED"
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 1. Header Section
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(26, 36, 56)  # Dark navy
    pdf.cell(0, 8, "LEGAL METROLOGY SCREENING REPORT", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(80, 90, 105)
    pdf.cell(
        0,
        5,
        "Legal Metrology (Packaged Commodities) Rules, 2011 | Department of Consumer Affairs",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(2)

    # Decorative rule divider
    pdf.set_draw_color(200, 205, 215)
    pdf.set_line_width(0.4)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(3)

    # Metadata Block
    col_w = 45
    val_w = 45
    # Row 1
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(col_w, 4.5, "Audit Identifier:", new_x=XPos.RIGHT)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(
        val_w,
        4.5,
        sanitize_text(audit_id_str[:16] + "..." if len(audit_id_str) > 16 else audit_id_str),
        new_x=XPos.RIGHT,
    )
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(col_w, 4.5, "Inspection Timestamp:", new_x=XPos.RIGHT)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(val_w, 4.5, timestamp_str, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Row 2
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(col_w, 4.5, "Perception Engine:", new_x=XPos.RIGHT)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(val_w, 4.5, sanitize_text(result.ocr_result.engine_used), new_x=XPos.RIGHT)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(col_w, 4.5, "Mean OCR Confidence:", new_x=XPos.RIGHT)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(
        val_w,
        4.5,
        f"{result.ocr_result.mean_confidence * 100:.1f}%",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    pdf.ln(3)

    # 2. Evidentiary Disclaimer Box
    pdf.set_fill_color(245, 247, 250)
    pdf.set_draw_color(220, 225, 235)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(100, 105, 115)
    disclaimer_text = (
        "PRELIMINARY ADMINISTRATIVE TRIAGE ONLY: This automated screening dossier evaluates visible packaging declarations "
        "against the Legal Metrology (Packaged Commodities) Rules, 2011. It facilitates institutional triage and does not "
        "constitute a judicial order or conclusive determination under Section 36 of the Legal Metrology Act, 2009."
    )
    pdf.multi_cell(0, 3.8, disclaimer_text, border=1, fill=True)
    pdf.ln(3)

    # 3. Overall Screening Verdict Box
    dec = result.decision
    if dec.verdict == ScreeningVerdict.NO_OBVIOUS_ISSUE:
        bg_color = (235, 247, 238)
        border_color = (46, 125, 50)
        title_color = (27, 94, 32)
        verdict_title = "[COMPLIANT] VERDICT: NO OBVIOUS ISSUE"
        verdict_desc = (
            "All machine-checkable mandatory statutory packaging declarations satisfy the Legal Metrology "
            "(Packaged Commodities) Rules, 2011. No statutory infractions were flagged during automated audit."
        )
    elif dec.verdict == ScreeningVerdict.NEEDS_REVIEW:
        bg_color = (255, 248, 225)
        border_color = (245, 127, 23)
        title_color = (183, 75, 0)
        verdict_title = "[ATTENTION] VERDICT: NEEDS REVIEW"
        verdict_desc = (
            "Ambiguous declarations, low optical clarity, or advisory conditions were identified. "
            "Manual review by an authorized Legal Metrology Officer is recommended before disposition."
        )
    else:
        bg_color = (255, 235, 238)
        border_color = (198, 40, 40)
        title_color = (183, 28, 28)
        verdict_title = "[INFRACTION DETECTED] VERDICT: POTENTIAL NON-COMPLIANCE"
        verdict_desc = (
            f"Statutory infractions flagged: {dec.critical_violations_count} Critical, "
            f"{dec.major_violations_count} Major violation(s) under the Legal Metrology Rules, 2011."
        )

    pdf.set_fill_color(*bg_color)
    pdf.set_draw_color(*border_color)
    pdf.set_line_width(0.5)

    y_before = pdf.get_y()
    pdf.rect(15, y_before, 180, 16, style="DF")
    pdf.set_xy(18, y_before + 2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*title_color)
    pdf.cell(0, 5, verdict_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_xy(18, y_before + 7.5)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(174, 3.8, sanitize_text(verdict_desc))
    pdf.set_y(y_before + 19)

    # 4. Optical Quality Gate Summary Table
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(26, 36, 56)
    pdf.cell(0, 6, "1. Optical Quality Gate Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    q = result.quality_metrics
    sharp_text = f"{q.laplacian_variance:.1f}"
    sharp_status = "PASS" if q.is_sharp else "FAIL (Blurry)"
    glare_text = f"{q.glare_ratio * 100:.2f}%"
    glare_status = "PASS" if q.has_acceptable_glare else "FAIL (Glare)"
    res_text = f"{q.width} x {q.height} px"
    res_status = "PASS" if q.is_acceptable_for_screening else "DEGRADED"

    with pdf.table(col_widths=(60, 45, 45, 30)) as table:
        hdr = table.row()
        for h_title in ("Assessment Parameter", "Measured Value", "Statutory Threshold", "Gate Status"):
            hdr.cell(h_title)

        r1 = table.row()
        r1.cell("Image Sharpness (Laplacian)")
        r1.cell(sharp_text)
        r1.cell(">= 80.0 Variance")
        r1.cell(sharp_status)

        r2 = table.row()
        r2.cell("Specular Glare Ratio")
        r2.cell(glare_text)
        r2.cell("<= 5.0% Highlight Area")
        r2.cell(glare_status)

        r3 = table.row()
        r3.cell("Spatial Dimensions")
        r3.cell(res_text)
        r3.cell(">= 600 x 400 pixels")
        r3.cell(res_status)

    pdf.ln(3)

    # 5. Extracted Statutory Declarations Table (Rule 6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(26, 36, 56)
    pdf.cell(0, 6, "2. Extracted Mandatory Declarations (Rule 6)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    d = result.declarations
    mrp_val_str = (
        f"Rs. {d.mrp.value.amount:.2f} ({'Incl. of all taxes' if d.mrp.value.includes_taxes else 'MISSING TAX CLAUSE'})"
        if d.mrp
        else "NOT DETECTED"
    )
    qty_val_str = (
        f"{d.net_quantity.value.magnitude} {d.net_quantity.value.raw_unit} (SI: {d.net_quantity.value.unit})"
        if d.net_quantity
        else "NOT DETECTED"
    )
    usp_val_str = (
        f"Rs. {d.unit_sale_price.value.amount:.2f} / {d.unit_sale_price.value.unit}"
        if d.unit_sale_price
        else "NOT DECLARED / N/A"
    )
    mfg_val_str = d.mfg_date.value.raw_date_str if d.mfg_date else "NOT DETECTED"
    care_parts = []
    if d.consumer_care:
        if d.consumer_care.value.email:
            care_parts.append(d.consumer_care.value.email)
        if d.consumer_care.value.phone:
            care_parts.append(d.consumer_care.value.phone)
        if not care_parts and d.consumer_care.value.address:
            care_parts.append(d.consumer_care.value.address[:40])
    care_val_str = "; ".join(care_parts) if care_parts else "NOT DETECTED"

    with pdf.table(col_widths=(55, 95, 30)) as table:
        hdr = table.row()
        for h_title in ("Statutory Field", "Observed Packaging Declaration", "Field Status"):
            hdr.cell(h_title)

        r_mrp = table.row()
        r_mrp.cell("Maximum Retail Price (MRP)")
        r_mrp.cell(sanitize_text(mrp_val_str))
        r_mrp.cell("COMPLIANT" if d.mrp and d.mrp.value.includes_taxes else "FLAGGED")

        r_qty = table.row()
        r_qty.cell("Net Quantity Statement")
        r_qty.cell(sanitize_text(qty_val_str))
        r_qty.cell("DECLARED" if d.net_quantity else "MISSING")

        r_usp = table.row()
        r_usp.cell("Unit Sale Price (USP)")
        r_usp.cell(sanitize_text(usp_val_str))
        r_usp.cell("DECLARED" if d.unit_sale_price else "EXEMPT/N/A")

        r_mfg = table.row()
        r_mfg.cell("Mfg / Packing Month & Year")
        r_mfg.cell(sanitize_text(mfg_val_str))
        r_mfg.cell("DECLARED" if d.mfg_date else "MISSING")

        r_care = table.row()
        r_care.cell("Consumer Care / Grievance")
        r_care.cell(sanitize_text(care_val_str))
        r_care.cell("DECLARED" if care_parts else "MISSING")

    pdf.ln(3)

    # 6. Itemized Statutory Infractions under LMPC Rules, 2011
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(26, 36, 56)
    pdf.cell(
        0,
        6,
        "3. Schedule of Statutory Infractions (LMPC Rules, 2011)",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    failed_rules = [r for r in result.rule_results if r.status == RuleStatus.FAIL]
    if failed_rules:
        for idx, r in enumerate(failed_rules, 1):
            v = r.violation
            sev_str = v.severity.value if v else "FAIL"
            border_color = (198, 40, 40) if sev_str == "CRITICAL" else (245, 127, 23)

            pdf.set_draw_color(*border_color)
            pdf.set_line_width(0.3)
            pdf.set_fill_color(252, 252, 253)

            title_txt = f"{idx}. {r.rule_reference} - {r.rule_id} [{sev_str}]"
            msg_txt = f"Infraction: {v.message}" if v else f"Reason: {r.reason}"
            std_txt = f"Standard: {v.expected_condition}" if v and v.expected_condition else ""
            obs_txt = f"Detected: {v.detected_value}" if v and v.detected_value else ""

            content_lines = [sanitize_text(title_txt), sanitize_text(msg_txt)]
            if std_txt:
                content_lines.append(sanitize_text(std_txt))
            if obs_txt:
                content_lines.append(sanitize_text(obs_txt))

            full_box_text = "\n".join(content_lines)
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(40, 45, 55)
            pdf.multi_cell(0, 4.2, full_box_text, border=1, fill=True)
            pdf.ln(2)
    else:
        pdf.set_fill_color(240, 249, 242)
        pdf.set_draw_color(46, 125, 50)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(27, 94, 32)
        pdf.cell(
            0,
            8,
            "All 6 statutory rule checkpoints satisfied. Zero infractions detected under Legal Metrology Rules, 2011.",
            border=1,
            fill=True,
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    return bytes(pdf.output())
