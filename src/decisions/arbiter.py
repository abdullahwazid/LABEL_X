"""Three-state decision arbiter synthesizing visual quality, OCR confidence, and statutory verdicts."""

from typing import Optional

from src.decisions.models import ScreeningDecision, ScreeningVerdict
from src.image_quality.models import ImageQualityMetrics
from src.regulatory.models import ViolationSeverity
from src.rules.models import RuleEvaluationResult, RuleStatus


class DecisionArbiter:
    """Synthesizes perception quality, text extraction confidence, and deterministic rule outcomes."""

    OCR_CONFIDENCE_THRESHOLD: float = 0.70

    def adjudicate(
        self,
        rule_results: list[RuleEvaluationResult],
        quality_metrics: Optional[ImageQualityMetrics] = None,
        ocr_confidence: float = 1.0,
    ) -> ScreeningDecision:
        """Adjudicates a final Three-State screening verdict based on statutory and optical evidence.

        Args:
            rule_results: List of evaluated statutory rule outcomes.
            quality_metrics: Optical image quality metrics (if available).
            ocr_confidence: Aggregated OCR recognition confidence (0.0 to 1.0).

        Returns:
            An immutable ScreeningDecision instance.
        """
        critical_count = 0
        major_count = 0
        minor_count = 0
        advisory_count = 0

        advisory_notes: list[str] = []
        quality_warnings: list[str] = []

        if quality_metrics is not None:
            quality_warnings.extend(quality_metrics.quality_warnings)

        for res in rule_results:
            if res.violation:
                if res.violation.severity == ViolationSeverity.CRITICAL:
                    critical_count += 1
                elif res.violation.severity == ViolationSeverity.MAJOR:
                    major_count += 1
                elif res.violation.severity == ViolationSeverity.MINOR:
                    minor_count += 1
                elif res.violation.severity == ViolationSeverity.ADVISORY:
                    advisory_count += 1
                    advisory_notes.append(f"[{res.rule_id}] {res.violation.message}")
            elif "advisory" in res.reason.lower() or res.rule_id == "LMPC_R07":
                advisory_notes.append(f"[{res.rule_id}] {res.reason}")

        norm_confidence = round(min(1.0, max(0.0, ocr_confidence)), 2)

        # Rule A: Image Quality Gate Check
        if quality_metrics is not None and not quality_metrics.is_acceptable_for_screening:
            summary = (
                "Image quality is degraded; optical focus or specular glare violates screening "
                "thresholds. Automated screening is inconclusive and requires manual officer verification."
            )
            return ScreeningDecision(
                verdict=ScreeningVerdict.NEEDS_REVIEW,
                summary=summary,
                critical_violations_count=critical_count,
                major_violations_count=major_count,
                advisory_notes=advisory_notes,
                quality_warnings=quality_warnings,
                confidence_score=norm_confidence,
            )

        # Rule B: OCR Recognition Confidence Check
        if ocr_confidence < self.OCR_CONFIDENCE_THRESHOLD:
            summary = (
                f"OCR text recognition clarity is low ({norm_confidence * 100:.1f}% < "
                f"{self.OCR_CONFIDENCE_THRESHOLD * 100:.0f}%). Perceptual ambiguity requires human review."
            )
            return ScreeningDecision(
                verdict=ScreeningVerdict.NEEDS_REVIEW,
                summary=summary,
                critical_violations_count=critical_count,
                major_violations_count=major_count,
                advisory_notes=advisory_notes,
                quality_warnings=quality_warnings,
                confidence_score=norm_confidence,
            )

        # Rule C: Statutory Non-Compliance Check
        if critical_count > 0 or major_count > 0:
            violation_details = []
            for r in rule_results:
                if r.violation and r.violation.severity in (ViolationSeverity.CRITICAL, ViolationSeverity.MAJOR):
                    violation_details.append(f"{r.rule_reference}: {r.violation.message}")

            summary = (
                f"Potential non-compliance detected ({critical_count} critical, {major_count} major infractions): "
                + "; ".join(violation_details)
            )
            return ScreeningDecision(
                verdict=ScreeningVerdict.POTENTIAL_NON_COMPLIANCE,
                summary=summary,
                critical_violations_count=critical_count,
                major_violations_count=major_count,
                advisory_notes=advisory_notes,
                quality_warnings=quality_warnings,
                confidence_score=norm_confidence,
            )

        # Rule D: Advisory Check
        has_needs_review_rule = any(r.status == RuleStatus.NEEDS_REVIEW for r in rule_results)
        if advisory_count > 0 or has_needs_review_rule:
            summary = "Declarations meet basic requirements, but advisory or optical considerations require manual review."
            return ScreeningDecision(
                verdict=ScreeningVerdict.NEEDS_REVIEW,
                summary=summary,
                critical_violations_count=critical_count,
                major_violations_count=major_count,
                advisory_notes=advisory_notes,
                quality_warnings=quality_warnings,
                confidence_score=norm_confidence,
            )

        # Rule E: Full Compliance Pass
        return ScreeningDecision(
            verdict=ScreeningVerdict.NO_OBVIOUS_ISSUE,
            summary="All machine-checkable statutory rules verified successfully.",
            critical_violations_count=0,
            major_violations_count=0,
            advisory_notes=advisory_notes,
            quality_warnings=quality_warnings,
            confidence_score=norm_confidence,
        )
