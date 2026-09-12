"""Unit tests for deterministic Legal Metrology compliance rule engine."""

import pytest
from pydantic import ValidationError

from src.extraction.models import (
    ConsumerCareData,
    DateData,
    ExtractedField,
    MRPData,
    NetQuantityData,
    ProductDeclarations,
    UnitSalePriceData,
)
from src.ocr.models import BoundingBox
from src.regulatory.models import ViolationSeverity
from src.rules.engine import LegalMetrologyRuleEngine
from src.rules.models import RuleEvaluationResult, RuleStatus, RuleViolation


@pytest.fixture
def engine() -> LegalMetrologyRuleEngine:
    """Fixture providing an instance of LegalMetrologyRuleEngine."""
    return LegalMetrologyRuleEngine()


def build_declarations(
    mrp_amount: float = 150.0,
    mrp_includes_taxes: bool = True,
    has_mrp: bool = True,
    magnitude: float = 500.0,
    unit: str = "g",
    raw_unit: str = "g",
    has_net_qty: bool = True,
    usp_amount: float = 0.30,
    has_usp: bool = True,
    has_mfg_date: bool = True,
    has_consumer_care: bool = True,
) -> ProductDeclarations:
    """Helper factory to construct parameterized ProductDeclarations."""
    bbox = BoundingBox(x1=10, y1=10, x2=200, y2=40)

    mrp_field = None
    if has_mrp:
        mrp_field = ExtractedField(
            value=MRPData(amount=mrp_amount, currency="INR", includes_taxes=mrp_includes_taxes),
            raw_text=f"MRP Rs. {mrp_amount:.2f} {'incl. of all taxes' if mrp_includes_taxes else ''}",
            confidence=0.95,
            bbox=bbox,
        )

    net_qty_field = None
    if has_net_qty:
        net_qty_field = ExtractedField(
            value=NetQuantityData(magnitude=magnitude, unit=unit, raw_unit=raw_unit),
            raw_text=f"Net Qty: {magnitude} {raw_unit}",
            confidence=0.96,
            bbox=bbox,
        )

    usp_field = None
    if has_usp:
        usp_field = ExtractedField(
            value=UnitSalePriceData(amount=usp_amount, unit=unit),
            raw_text=f"USP Rs. {usp_amount:.2f} / {unit}",
            confidence=0.92,
            bbox=bbox,
        )

    date_field = None
    if has_mfg_date:
        date_field = ExtractedField(
            value=DateData(month=9, year=2026, raw_date_str="09/2026"),
            raw_text="Mfg Date: 09/2026",
            confidence=0.94,
            bbox=bbox,
        )

    care_field = None
    if has_consumer_care:
        care_field = ExtractedField(
            value=ConsumerCareData(email="care@brand.in", phone="1800-111-2222"),
            raw_text="Consumer Care: care@brand.in, 1800-111-2222",
            confidence=0.93,
            bbox=bbox,
        )

    return ProductDeclarations(
        mrp=mrp_field,
        net_quantity=net_qty_field,
        unit_sale_price=usp_field,
        mfg_date=date_field,
        consumer_care=care_field,
        raw_full_text="SAMPLE LABEL",
        overall_extraction_confidence=0.94,
    )


def test_fully_compliant_declarations_produce_all_pass(engine: LegalMetrologyRuleEngine):
    """Test that fully compliant packaging declarations satisfy all statutory rules."""
    decls = build_declarations()
    results = engine.evaluate(decls, is_quality_acceptable=True)

    assert len(results) == 6
    for result in results:
        assert isinstance(result, RuleEvaluationResult)
        assert result.status == RuleStatus.PASS, f"Rule {result.rule_id} failed: {result.reason}"
        assert result.violation is None


def test_missing_mrp_produces_fail(engine: LegalMetrologyRuleEngine):
    """Test that missing MRP produces a CRITICAL failure on LMPC_R06_1_E."""
    decls = build_declarations(has_mrp=False)
    results = engine.evaluate(decls)

    mrp_res = next(r for r in results if r.rule_id == "LMPC_R06_1_E")
    assert mrp_res.status == RuleStatus.FAIL
    assert mrp_res.violation is not None
    assert mrp_res.violation.severity == ViolationSeverity.CRITICAL
    assert mrp_res.violation.field == "mrp"


def test_mrp_missing_tax_clause_produces_fail(engine: LegalMetrologyRuleEngine):
    """Test that MRP missing 'inclusive of all taxes' produces a CRITICAL failure."""
    decls = build_declarations(mrp_includes_taxes=False)
    results = engine.evaluate(decls)

    mrp_res = next(r for r in results if r.rule_id == "LMPC_R06_1_E")
    assert mrp_res.status == RuleStatus.FAIL
    assert mrp_res.violation is not None
    assert mrp_res.violation.severity == ViolationSeverity.CRITICAL
    assert "inclusive of all taxes" in mrp_res.violation.message.lower()


def test_prohibited_unit_gms_produces_fail(engine: LegalMetrologyRuleEngine):
    """Test that non-standard unit 'gms' produces a CRITICAL failure on LMPC_R13."""
    decls = build_declarations(unit="g", raw_unit="gms")
    results = engine.evaluate(decls)

    unit_res = next(r for r in results if r.rule_id == "LMPC_R13")
    assert unit_res.status == RuleStatus.FAIL
    assert unit_res.violation is not None
    assert unit_res.violation.severity == ViolationSeverity.CRITICAL
    assert "prohibited" in unit_res.violation.message.lower()
    assert unit_res.violation.detected_value == "gms"


def test_missing_usp_on_large_package_produces_fail(engine: LegalMetrologyRuleEngine):
    """Test that missing USP on package > 1 unit produces a MAJOR failure on LMPC_R06_11."""
    decls = build_declarations(magnitude=500.0, has_usp=False)
    results = engine.evaluate(decls)

    usp_res = next(r for r in results if r.rule_id == "LMPC_R06_11")
    assert usp_res.status == RuleStatus.FAIL
    assert usp_res.violation is not None
    assert usp_res.violation.severity == ViolationSeverity.MAJOR
    assert "missing" in usp_res.violation.message.lower()


def test_arithmetic_mismatch_in_usp_produces_fail(engine: LegalMetrologyRuleEngine):
    """Test that declared USP deviating from calculated rate produces a MAJOR failure."""
    # Net quantity = 500g, MRP = Rs. 150.00 -> Expected USP = 0.30/g
    # Declaring Rs. 0.45/g is a 50% discrepancy
    decls = build_declarations(mrp_amount=150.0, magnitude=500.0, usp_amount=0.45)
    results = engine.evaluate(decls)

    usp_res = next(r for r in results if r.rule_id == "LMPC_R06_11")
    assert usp_res.status == RuleStatus.FAIL
    assert usp_res.violation is not None
    assert usp_res.violation.severity == ViolationSeverity.MAJOR
    assert "arithmetic discrepancy" in usp_res.violation.message.lower()


def test_usp_arithmetic_tolerance_2_decimal_commercial_rounding(engine: LegalMetrologyRuleEngine):
    """Test that MRP = 10.00, Net Qty = 60.0g with declared USP 0.17/g passes 2-decimal commercial rounding."""
    # Expected USP: 10.00 / 60.0 = 0.166667. Declared USP: 0.17.
    # Deviation is 2.0%, but round(0.17, 2) == round(0.166667, 2) passes Rule 6(11).
    decls = build_declarations(mrp_amount=10.0, magnitude=60.0, unit="g", raw_unit="g", usp_amount=0.17)
    results = engine.evaluate(decls)

    usp_res = next(r for r in results if r.rule_id == "LMPC_R06_11")
    assert usp_res.status == RuleStatus.PASS
    assert usp_res.violation is None


def test_rule_26_small_package_exemption_returns_not_applicable(engine: LegalMetrologyRuleEngine):
    """Test that small packages (<= 10g) receive NOT_APPLICABLE status for standard rules."""
    decls = build_declarations(magnitude=5.0, unit="g", raw_unit="g")
    results = engine.evaluate(decls)

    standard_rule_ids = {
        "LMPC_R06_1_E",
        "LMPC_R13",
        "LMPC_R06_11",
        "LMPC_R06_1_D",
        "LMPC_R06_2",
        "LMPC_R07",
    }
    for res in results:
        if res.rule_id in standard_rule_ids:
            assert res.status == RuleStatus.NOT_APPLICABLE
            assert "Rule 26" in res.reason

    rule_26_res = next(r for r in results if r.rule_id == "LMPC_R26")
    assert rule_26_res.status == RuleStatus.PASS


def test_missing_consumer_care_produces_fail(engine: LegalMetrologyRuleEngine):
    """Test that missing consumer care contact channels produce a MAJOR failure on LMPC_R06_2."""
    decls = build_declarations(has_consumer_care=False)
    results = engine.evaluate(decls)

    care_res = next(r for r in results if r.rule_id == "LMPC_R06_2")
    assert care_res.status == RuleStatus.FAIL
    assert care_res.violation is not None
    assert care_res.violation.severity == ViolationSeverity.MAJOR


def test_rule_models_immutability():
    """Verify that RuleViolation and RuleEvaluationResult models are immutable."""
    violation = RuleViolation(
        rule_id="LMPC_R13",
        rule_reference="Rule 13",
        field="net_quantity",
        message="Prohibited unit",
        severity=ViolationSeverity.CRITICAL,
        expected_condition="Standard SI symbol",
    )
    result = RuleEvaluationResult(
        rule_id="LMPC_R13",
        rule_reference="Rule 13",
        status=RuleStatus.FAIL,
        violation=violation,
        reason="Detected prohibited unit",
    )

    with pytest.raises(ValidationError):
        result.status = RuleStatus.PASS  # type: ignore

    with pytest.raises(ValidationError):
        violation.severity = ViolationSeverity.MINOR  # type: ignore
