"""Deterministic legal metrology rule evaluation engine."""

from typing import Optional

from src.extraction.models import ProductDeclarations
from src.regulatory.knowledge_base import RegulatoryKnowledgeBase
from src.regulatory.models import ViolationSeverity
from src.rules.models import RuleEvaluationResult, RuleStatus, RuleViolation

FORBIDDEN_UNITS: set[str] = {"gms", "gm", "kilos", "kgs", "mls", "nos", "pcs"}
APPROVED_UNITS: set[str] = {"g", "kg", "ml", "l", "N", "U"}


class LegalMetrologyRuleEngine:
    """Deterministic rule evaluator enforcing Legal Metrology (Packaged Commodities) Rules, 2011."""

    def __init__(self, kb: Optional[RegulatoryKnowledgeBase] = None) -> None:
        """Initializes the rule engine with a regulatory knowledge base."""
        self.kb = kb if kb is not None else RegulatoryKnowledgeBase()

    def evaluate(
        self, declarations: ProductDeclarations, is_quality_acceptable: bool = True
    ) -> list[RuleEvaluationResult]:
        """Evaluates extracted product declarations deterministically against statutory rules.

        Args:
            declarations: Extracted structured product declarations.
            is_quality_acceptable: Optical image quality gate status.

        Returns:
            List of RuleEvaluationResult records.
        """
        results: list[RuleEvaluationResult] = []

        # Step 0: Small package exemption check under Rule 26
        qty_magnitude = (
            declarations.net_quantity.value.magnitude if declarations.net_quantity else None
        )
        qty_unit = declarations.net_quantity.value.unit if declarations.net_quantity else None

        if self.kb.is_exempt_under_rule_26(qty_magnitude, qty_unit):
            # Packages <= 10g or <= 10ml are exempt from standard declarations under Rule 26
            exemption_reason = (
                f"Exempt under Rule 26: Net quantity ({qty_magnitude} {qty_unit}) qualifies "
                f"for small-package statutory exemption (<= 10g or <= 10ml)."
            )
            standard_rule_ids = [
                ("LMPC_R06_1_E", "Rule 6(1)(e)"),
                ("LMPC_R13", "Rule 13 read with Second Schedule"),
                ("LMPC_R06_11", "Rule 6(11)"),
                ("LMPC_R06_1_D", "Rule 6(1)(d)"),
                ("LMPC_R06_2", "Rule 6(2)"),
                ("LMPC_R07", "Rule 7"),
            ]
            for rule_id, rule_ref in standard_rule_ids:
                results.append(
                    RuleEvaluationResult(
                        rule_id=rule_id,
                        rule_reference=rule_ref,
                        status=RuleStatus.NOT_APPLICABLE,
                        violation=None,
                        reason=exemption_reason,
                    )
                )

            results.append(
                RuleEvaluationResult(
                    rule_id="LMPC_R26",
                    rule_reference="Rule 26",
                    status=RuleStatus.PASS,
                    violation=None,
                    reason=f"Small package exemption verified: {qty_magnitude} {qty_unit} <= 10g/ml threshold.",
                )
            )
            return results

        # Step 1: Rule 6(1)(e) - Maximum Retail Price (MRP)
        results.append(self._evaluate_mrp(declarations))

        # Step 2: Rule 13 - Standard Metric Units
        results.append(self._evaluate_net_quantity_units(declarations))

        # Step 3: Rule 6(11) - Unit Sale Price (USP)
        results.append(self._evaluate_unit_sale_price(declarations))

        # Step 4: Rule 6(1)(d) - Month and Year of Manufacture / Packing
        results.append(self._evaluate_mfg_date(declarations))

        # Step 5: Rule 6(2) - Consumer Care Contact Details
        results.append(self._evaluate_consumer_care(declarations))

        # Step 6: Rule 7 - Font Height & Area Proportionality (Advisory)
        results.append(self._evaluate_font_and_display(is_quality_acceptable))

        return results

    def _evaluate_mrp(self, declarations: ProductDeclarations) -> RuleEvaluationResult:
        """Evaluates compliance with MRP declaration and compulsory tax inclusion."""
        rule_id = "LMPC_R06_1_E"
        rule_ref = "Rule 6(1)(e)"

        if declarations.mrp is None:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.FAIL,
                violation=RuleViolation(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    field="mrp",
                    message="Maximum Retail Price (MRP) declaration is missing from scanned packaging.",
                    severity=ViolationSeverity.CRITICAL,
                    detected_value=None,
                    expected_condition="Conspicuous MRP declaration with 'inclusive of all taxes'",
                ),
                reason="Mandatory MRP declaration not detected on package label.",
            )

        if not declarations.mrp.value.includes_taxes:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.FAIL,
                violation=RuleViolation(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    field="mrp.includes_taxes",
                    message="Maximum Retail Price declaration lacks compulsory 'inclusive of all taxes' or statutory abbreviation.",
                    severity=ViolationSeverity.CRITICAL,
                    detected_value=declarations.mrp.raw_text,
                    expected_condition="Must explicitly state 'inclusive of all taxes' or 'incl. of all taxes'",
                ),
                reason="MRP is declared without the mandatory tax-inclusive statement.",
            )

        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_reference=rule_ref,
            status=RuleStatus.PASS,
            violation=None,
            reason=f"MRP declared compliant: Rs. {declarations.mrp.value.amount:.2f} inclusive of all taxes.",
        )

    def _evaluate_net_quantity_units(self, declarations: ProductDeclarations) -> RuleEvaluationResult:
        """Evaluates net quantity metric units under Rule 13 and Second Schedule."""
        rule_id = "LMPC_R13"
        rule_ref = "Rule 13 read with Second Schedule"

        if declarations.net_quantity is None:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.FAIL,
                violation=RuleViolation(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    field="net_quantity",
                    message="Net quantity declaration is missing from scanned packaging.",
                    severity=ViolationSeverity.CRITICAL,
                    detected_value=None,
                    expected_condition="Standard metric net quantity declaration (e.g., g, kg, ml, l, N, U)",
                ),
                reason="Mandatory net quantity declaration not detected on package label.",
            )

        raw_unit_lower = declarations.net_quantity.value.raw_unit.strip().lower()
        canonical_unit = declarations.net_quantity.value.unit.strip()

        if raw_unit_lower in FORBIDDEN_UNITS:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.FAIL,
                violation=RuleViolation(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    field="net_quantity.raw_unit",
                    message=(
                        f"Prohibited unit abbreviation '{declarations.net_quantity.value.raw_unit}' used. "
                        f"Second Schedule permits only standard SI symbols ('{canonical_unit}')."
                    ),
                    severity=ViolationSeverity.CRITICAL,
                    detected_value=declarations.net_quantity.value.raw_unit,
                    expected_condition=f"Standard SI symbol '{canonical_unit}' without prohibited suffix",
                ),
                reason=f"Prohibited unit symbol '{declarations.net_quantity.value.raw_unit}' detected in violation of Rule 13.",
            )

        if canonical_unit not in APPROVED_UNITS:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.FAIL,
                violation=RuleViolation(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    field="net_quantity.unit",
                    message=f"Non-standard unit '{canonical_unit}' not approved under Second Schedule.",
                    severity=ViolationSeverity.CRITICAL,
                    detected_value=canonical_unit,
                    expected_condition="Approved metric unit: g, kg, ml, l, N, U",
                ),
                reason=f"Unapproved unit symbol '{canonical_unit}' detected.",
            )

        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_reference=rule_ref,
            status=RuleStatus.PASS,
            violation=None,
            reason=f"Standard metric net quantity compliant: {declarations.net_quantity.value.magnitude} {canonical_unit}.",
        )

    def _evaluate_unit_sale_price(self, declarations: ProductDeclarations) -> RuleEvaluationResult:
        """Evaluates Unit Sale Price (USP) mandate and mathematical parity under Rule 6(11)."""
        rule_id = "LMPC_R06_11"
        rule_ref = "Rule 6(11)"

        if not declarations.net_quantity or not declarations.mrp:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.FAIL,
                violation=RuleViolation(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    field="unit_sale_price",
                    message="Unit Sale Price cannot be verified because prerequisite Net Quantity or MRP is missing.",
                    severity=ViolationSeverity.MAJOR,
                    detected_value=None,
                    expected_condition="Net Quantity and MRP must be present to evaluate Unit Sale Price",
                ),
                reason="Prerequisite declarations (MRP or Net Quantity) missing for USP evaluation.",
            )

        magnitude = declarations.net_quantity.value.magnitude
        mrp_amount = declarations.mrp.value.amount

        if magnitude <= 0:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.FAIL,
                violation=RuleViolation(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    field="net_quantity.magnitude",
                    message="Net quantity magnitude must be greater than zero.",
                    severity=ViolationSeverity.CRITICAL,
                    detected_value=str(magnitude),
                    expected_condition="Net quantity magnitude > 0",
                ),
                reason="Invalid net quantity magnitude (<= 0).",
            )

        if magnitude > 1.0:
            if declarations.unit_sale_price is None:
                expected_usp = mrp_amount / magnitude
                return RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    status=RuleStatus.FAIL,
                    violation=RuleViolation(
                        rule_id=rule_id,
                        rule_reference=rule_ref,
                        field="unit_sale_price",
                        message="Mandatory Unit Sale Price (USP) declaration is missing for package with net quantity > 1 unit.",
                        severity=ViolationSeverity.MAJOR,
                        detected_value=None,
                        expected_condition=f"Declared USP matching MRP / Net Quantity (~Rs. {expected_usp:.2f} per unit)",
                    ),
                    reason="Mandatory Unit Sale Price not declared on package with quantity > 1.",
                )

            declared_usp = declarations.unit_sale_price.value.amount
            expected_usp = mrp_amount / magnitude

            # First check: If they match at 2 decimal places (standard commercial rounding for INR), evaluate as PASS
            if round(declared_usp, 2) == round(expected_usp, 2):
                return RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    status=RuleStatus.PASS,
                    violation=None,
                    reason=f"Unit Sale Price compliant: Rs. {declared_usp:.2f}/{declarations.unit_sale_price.value.unit} matches calculated rate.",
                )

            deviation = abs(declared_usp - expected_usp) / expected_usp if expected_usp > 0 else 0.0

            if deviation > 0.025:
                return RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    status=RuleStatus.FAIL,
                    violation=RuleViolation(
                        rule_id=rule_id,
                        rule_reference=rule_ref,
                        field="unit_sale_price.amount",
                        message=(
                            f"Arithmetic discrepancy in declared USP: declared Rs. {declared_usp:.2f} differs from "
                            f"expected Rs. {expected_usp:.2f} (MRP Rs. {mrp_amount:.2f} / {magnitude} {declarations.net_quantity.value.unit}) "
                            f"by {deviation * 100:.1f}% (> 2.5% tolerance)."
                        ),
                        severity=ViolationSeverity.MAJOR,
                        detected_value=f"Rs. {declared_usp:.2f} / {declarations.unit_sale_price.value.unit}",
                        expected_condition=f"Rs. {expected_usp:.2f} / {declarations.unit_sale_price.value.unit} (within 2.5%)",
                    ),
                    reason=f"Arithmetic discrepancy of {deviation * 100:.1f}% detected between declared USP and calculated USP.",
                )

            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.PASS,
                violation=None,
                reason=f"Unit Sale Price compliant: Rs. {declared_usp:.2f}/{declarations.unit_sale_price.value.unit} matches calculated rate.",
            )

        # Net quantity <= 1.0
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_reference=rule_ref,
            status=RuleStatus.PASS,
            violation=None,
            reason=f"Package net quantity ({magnitude} {declarations.net_quantity.value.unit}) <= 1 unit; separate USP not mandated.",
        )

    def _evaluate_mfg_date(self, declarations: ProductDeclarations) -> RuleEvaluationResult:
        """Evaluates presence of manufacturing or packing date declaration under Rule 6(1)(d)."""
        rule_id = "LMPC_R06_1_D"
        rule_ref = "Rule 6(1)(d)"

        if declarations.mfg_date is None:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.FAIL,
                violation=RuleViolation(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    field="mfg_date",
                    message="Month and year of manufacture or pre-packing declaration is missing.",
                    severity=ViolationSeverity.CRITICAL,
                    detected_value=None,
                    expected_condition="Month and year in valid format (e.g. MM/YYYY or Month Year)",
                ),
                reason="Mandatory manufacturing/packing date declaration missing.",
            )

        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_reference=rule_ref,
            status=RuleStatus.PASS,
            violation=None,
            reason=f"Manufacturing/packing date declared: {declarations.mfg_date.value.raw_date_str}.",
        )

    def _evaluate_consumer_care(self, declarations: ProductDeclarations) -> RuleEvaluationResult:
        """Evaluates consumer care grievance redressal contact channels under Rule 6(2)."""
        rule_id = "LMPC_R06_2"
        rule_ref = "Rule 6(2)"

        has_contact_channel = False
        if declarations.consumer_care is not None and declarations.consumer_care.value is not None:
            c = declarations.consumer_care.value
            has_contact_channel = bool(
                (c.email and c.email.strip())
                or (c.phone and c.phone.strip())
                or (c.address and len(c.address.strip()) > 3)
            )

        if not has_contact_channel:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.FAIL,
                violation=RuleViolation(
                    rule_id=rule_id,
                    rule_reference=rule_ref,
                    field="consumer_care",
                    message="Consumer care contact details (telephone number, email address, or grievance address/website) are missing.",
                    severity=ViolationSeverity.MAJOR,
                    detected_value=None,
                    expected_condition="At least one consumer grievance contact channel (email, phone, or address/website)",
                ),
                reason="Mandatory consumer grievance redressal contact channels not detected.",
            )

        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_reference=rule_ref,
            status=RuleStatus.PASS,
            violation=None,
            reason="Consumer care contact details declared compliant.",
        )

    def _evaluate_font_and_display(self, is_quality_acceptable: bool) -> RuleEvaluationResult:
        """Advisory assessment for font height and display proportionality under Rule 7."""
        rule_id = "LMPC_R07"
        rule_ref = "Rule 7"

        if is_quality_acceptable:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_reference=rule_ref,
                status=RuleStatus.PASS,
                violation=None,
                reason=(
                    "Advisory: Optical resolution is acceptable. Note that physical font height in "
                    "millimeters cannot be certified from 2D photos without a calibrated reference scale."
                ),
            )

        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_reference=rule_ref,
            status=RuleStatus.NEEDS_REVIEW,
            violation=None,
            reason=(
                "Advisory / Quality Alert: Image quality is degraded, preventing reliable font "
                "legibility verification. Physical font height in millimeters cannot be certified."
            ),
        )
