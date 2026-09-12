"""Statutory compliance notice and audit report generator."""

from datetime import datetime, timezone

from src.pipeline import PipelineResult
from src.reports.models import InspectionReport
from src.rules.models import RuleStatus


class ReportGenerator:
    """Generates formatted statutory notices and compliance dossiers."""

    def generate_text_report(
        self, inspection_id: str, result: PipelineResult, image_name: str
    ) -> InspectionReport:
        """Formulates an immutable statutory screening report from pipeline results.

        Args:
            inspection_id: Unique inspection UUID identifier.
            result: Complete PipelineResult from compliance screening.
            image_name: Source file name or descriptor of the package.

        Returns:
            An immutable InspectionReport instance.
        """
        generated_at = datetime.now(timezone.utc).isoformat()
        q = result.quality_metrics
        d = result.declarations
        dec = result.decision

        failed_rules = [r for r in result.rule_results if r.status == RuleStatus.FAIL]
        total_violations = len(failed_rules)

        lines: list[str] = [
            "=" * 80,
            "LEGAL METROLOGY (PACKAGED COMMODITIES) SCREENING NOTICE",
            "Department of Consumer Affairs • Statutory Compliance Triage Report",
            "=" * 80,
            "",
            "EVIDENTIARY DISCLAIMER:",
            "PRELIMINARY ADMINISTRATIVE AUDIT ONLY. This report summarizes automated perceptual",
            "screening findings and does not constitute a judicial compounding order or conclusive",
            "ruling under Section 36 of the Legal Metrology Act, 2009.",
            "-" * 80,
            "",
            "1. INSPECTION METADATA & OPTICAL INTEGRITY:",
            f"   • Inspection UUID:     {inspection_id}",
            f"   • Audit Timestamp:     {generated_at}",
            f"   • Package Source Name: {image_name}",
            f"   • Sharpness (Laplacian): {q.laplacian_variance:.1f} (Threshold >= 80.0)",
            f"   • Specular Glare:      {q.glare_ratio * 100:.2f}% (Threshold <= 5.0%)",
            f"   • Resolution:          {q.width} x {q.height} px",
            f"   • Quality Gate Status: {'PASSED' if q.is_acceptable_for_screening else 'DEGRADED'}",
            "",
            "2. ADJUDICATION STATUS:",
            f"   • Screening Verdict:   {dec.verdict.value}",
            f"   • Critical Violations: {dec.critical_violations_count}",
            f"   • Major Infractions:   {dec.major_violations_count}",
            f"   • Executive Summary:   {dec.summary}",
            "",
            "3. EXTRACTED MANDATORY STATUTORY DECLARATIONS:",
        ]

        mrp_text = (
            f"Rs. {d.mrp.value.amount:.2f} ({'inclusive of all taxes' if d.mrp.value.includes_taxes else 'MISSING TAX CLAUSE'})"
            if d.mrp
            else "[NOT DETECTED]"
        )
        qty_text = (
            f"{d.net_quantity.value.magnitude} {d.net_quantity.value.raw_unit} "
            f"(Normalized SI: {d.net_quantity.value.unit})"
            if d.net_quantity
            else "[NOT DETECTED]"
        )
        usp_text = (
            f"Rs. {d.unit_sale_price.value.amount:.2f} / {d.unit_sale_price.value.unit}"
            if d.unit_sale_price
            else "[NOT DETECTED / EXEMPT]"
        )
        mfg_text = d.mfg_date.value.raw_date_str if d.mfg_date else "[NOT DETECTED]"
        care_text = (
            f"{d.consumer_care.value.email or ''} {d.consumer_care.value.phone or ''}".strip()
            if d.consumer_care and (d.consumer_care.value.email or d.consumer_care.value.phone)
            else "[NOT DETECTED]"
        )

        lines.extend(
            [
                f"   • Maximum Retail Price (MRP): {mrp_text}",
                f"   • Net Quantity:               {qty_text}",
                f"   • Unit Sale Price (USP):      {usp_text}",
                f"   • Month & Year of Mfg/Pkd:    {mfg_text}",
                f"   • Consumer Grievance Care:    {care_text}",
                "",
                "4. SCHEDULE OF STATUTORY INFRACTIONS:",
            ]
        )

        if failed_rules:
            for idx, r in enumerate(failed_rules, 1):
                v = r.violation
                severity_str = v.severity.value if v else "UNKNOWN"
                lines.extend(
                    [
                        f"   [{idx}] RULE REFERENCE: {r.rule_reference} ({r.rule_id})",
                        f"       Severity:          {severity_str}",
                        f"       Target Field:      {v.field if v else 'N/A'}",
                        f"       Detected Text:     {v.detected_value if v and v.detected_value else '[MISSING]'}",
                        f"       Statutory Mandate: {v.expected_condition if v else 'N/A'}",
                        f"       Specific Finding:  {v.message if v else r.reason}",
                        "",
                    ]
                )
        else:
            lines.extend(
                [
                    "   • Zero statutory infractions identified across all evaluated rules.",
                    "",
                ]
            )

        lines.extend(
            [
                "5. CRYPTOGRAPHIC CHAIN OF CUSTODY (VISUAL EVIDENCE):",
            ]
        )

        if result.evidence_dossier.crops:
            for idx, crop in enumerate(result.evidence_dossier.crops, 1):
                lines.extend(
                    [
                        f"   [{idx}] Evidence Field: {crop.field_name}",
                        f"       Rule Reference: {crop.rule_reference} ({crop.rule_id})",
                        f"       Extracted Text: \"{crop.raw_text}\"",
                        f"       Bounding Box:   ({crop.bbox.x1}, {crop.bbox.y1}) to ({crop.bbox.x2}, {crop.bbox.y2})",
                        f"       SHA-256 Digest: {crop.sha256_hash}",
                        "",
                    ]
                )
        else:
            lines.extend(
                [
                    "   • No visual evidence crops generated for this session.",
                    "",
                ]
            )

        lines.extend(
            [
                "=" * 80,
                "END OF STATUTORY SCREENING REPORT",
                "=" * 80,
            ]
        )

        report_content = "\n".join(lines)

        return InspectionReport(
            inspection_id=inspection_id,
            generated_at=generated_at,
            report_text=report_content,
            verdict=dec.verdict.value,
            total_violations=total_violations,
        )
