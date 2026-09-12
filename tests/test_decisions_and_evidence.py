"""Unit tests for decision arbiter and visual evidence generation module."""

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from src.decisions.arbiter import DecisionArbiter
from src.decisions.models import ScreeningDecision, ScreeningVerdict
from src.evidence.generator import EvidenceGenerator
from src.evidence.models import EvidenceDossier, VisualEvidenceCrop
from src.extraction.models import (
    ConsumerCareData,
    DateData,
    ExtractedField,
    MRPData,
    NetQuantityData,
    ProductDeclarations,
    UnitSalePriceData,
)
from src.image_quality.models import ImageQualityMetrics
from src.ocr.models import BoundingBox
from src.rules.engine import LegalMetrologyRuleEngine
from src.rules.models import RuleEvaluationResult, RuleStatus, RuleViolation
from src.regulatory.models import ViolationSeverity


@pytest.fixture
def arbiter() -> DecisionArbiter:
    """Fixture providing DecisionArbiter instance."""
    return DecisionArbiter()


@pytest.fixture
def generator() -> EvidenceGenerator:
    """Fixture providing EvidenceGenerator instance."""
    return EvidenceGenerator()


@pytest.fixture
def valid_quality() -> ImageQualityMetrics:
    """Fixture providing passing image quality metrics."""
    return ImageQualityMetrics(
        width=800,
        height=600,
        laplacian_variance=145.2,
        glare_ratio=0.015,
        is_sharp=True,
        has_acceptable_glare=True,
        is_acceptable_for_screening=True,
        quality_warnings=[],
    )


@pytest.fixture
def degraded_quality() -> ImageQualityMetrics:
    """Fixture providing failing image quality metrics."""
    return ImageQualityMetrics(
        width=800,
        height=600,
        laplacian_variance=32.0,
        glare_ratio=0.12,
        is_sharp=False,
        has_acceptable_glare=False,
        is_acceptable_for_screening=False,
        quality_warnings=["Focus degraded (Laplacian: 32.0 < 80.0)", "Excessive specular glare (12%)"],
    )


@pytest.fixture
def compliant_rule_results() -> list[RuleEvaluationResult]:
    """Fixture providing all-PASS rule evaluation results."""
    return [
        RuleEvaluationResult(rule_id="LMPC_R06_1_E", rule_reference="Rule 6(1)(e)", status=RuleStatus.PASS, reason="MRP OK"),
        RuleEvaluationResult(rule_id="LMPC_R13", rule_reference="Rule 13", status=RuleStatus.PASS, reason="Units OK"),
        RuleEvaluationResult(rule_id="LMPC_R06_11", rule_reference="Rule 6(11)", status=RuleStatus.PASS, reason="USP OK"),
        RuleEvaluationResult(rule_id="LMPC_R06_1_D", rule_reference="Rule 6(1)(d)", status=RuleStatus.PASS, reason="Date OK"),
        RuleEvaluationResult(rule_id="LMPC_R06_2", rule_reference="Rule 6(2)", status=RuleStatus.PASS, reason="Consumer care OK"),
        RuleEvaluationResult(rule_id="LMPC_R07", rule_reference="Rule 7", status=RuleStatus.PASS, reason="Advisory font OK"),
    ]


def test_arbiter_emits_no_obvious_issue_when_compliant(
    arbiter: DecisionArbiter, valid_quality: ImageQualityMetrics, compliant_rule_results: list[RuleEvaluationResult]
):
    """Test arbiter produces NO_OBVIOUS_ISSUE when all rules pass and quality is good."""
    decision = arbiter.adjudicate(
        rule_results=compliant_rule_results,
        quality_metrics=valid_quality,
        ocr_confidence=0.94,
    )

    assert isinstance(decision, ScreeningDecision)
    assert decision.verdict == ScreeningVerdict.NO_OBVIOUS_ISSUE
    assert decision.critical_violations_count == 0
    assert decision.major_violations_count == 0
    assert decision.confidence_score == 0.94
    assert "successfully" in decision.summary.lower()


def test_arbiter_emits_potential_non_compliance_when_critical_rule_fails(
    arbiter: DecisionArbiter, valid_quality: ImageQualityMetrics
):
    """Test arbiter produces POTENTIAL_NON_COMPLIANCE when a critical violation occurs."""
    failing_results = [
        RuleEvaluationResult(
            rule_id="LMPC_R13",
            rule_reference="Rule 13 read with Second Schedule",
            status=RuleStatus.FAIL,
            violation=RuleViolation(
                rule_id="LMPC_R13",
                rule_reference="Rule 13 read with Second Schedule",
                field="net_quantity.raw_unit",
                message="Prohibited unit 'gms' used.",
                severity=ViolationSeverity.CRITICAL,
                detected_value="gms",
                expected_condition="Standard SI symbol 'g'",
            ),
            reason="Prohibited unit detected.",
        )
    ]

    decision = arbiter.adjudicate(
        rule_results=failing_results,
        quality_metrics=valid_quality,
        ocr_confidence=0.92,
    )

    assert decision.verdict == ScreeningVerdict.POTENTIAL_NON_COMPLIANCE
    assert decision.critical_violations_count == 1
    assert "potential non-compliance" in decision.summary.lower()


def test_arbiter_emits_needs_review_when_quality_degraded(
    arbiter: DecisionArbiter, degraded_quality: ImageQualityMetrics, compliant_rule_results: list[RuleEvaluationResult]
):
    """Test arbiter produces NEEDS_REVIEW when image quality is degraded."""
    decision = arbiter.adjudicate(
        rule_results=compliant_rule_results,
        quality_metrics=degraded_quality,
        ocr_confidence=0.92,
    )

    assert decision.verdict == ScreeningVerdict.NEEDS_REVIEW
    assert len(decision.quality_warnings) == 2
    assert "quality is degraded" in decision.summary.lower()


def test_arbiter_emits_needs_review_when_ocr_confidence_low(
    arbiter: DecisionArbiter, valid_quality: ImageQualityMetrics, compliant_rule_results: list[RuleEvaluationResult]
):
    """Test arbiter produces NEEDS_REVIEW when OCR confidence is below 70% threshold."""
    decision = arbiter.adjudicate(
        rule_results=compliant_rule_results,
        quality_metrics=valid_quality,
        ocr_confidence=0.62,
    )

    assert decision.verdict == ScreeningVerdict.NEEDS_REVIEW
    assert "clarity is low" in decision.summary.lower()
    assert decision.confidence_score == 0.62


def test_evidence_generator_produces_png_and_sha256(generator: EvidenceGenerator):
    """Test evidence crop generation returns valid PNG bytes and a 64-char hex SHA-256 hash."""
    image = np.full((300, 400, 3), 180, dtype=np.uint8)
    # Draw dark rectangle inside
    image[40:100, 50:150] = (20, 20, 20)

    bbox = BoundingBox(x1=50, y1=40, x2=150, y2=100)
    crop_bytes, sha256_hash = generator.crop_region(image, bbox, padding=5)

    assert isinstance(crop_bytes, bytes)
    assert len(crop_bytes) > 0
    # Check PNG magic bytes (\x89PNG\r\n\x1a\n)
    assert crop_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    assert isinstance(sha256_hash, str)
    assert len(sha256_hash) == 64
    assert all(c in "0123456789abcdef" for c in sha256_hash)

    # Verify OpenCV can decode the cropped bytes
    decoded = cv2.imdecode(np.frombuffer(crop_bytes, np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    # 100 width + 10 padding = 110; 60 height + 10 padding = 70
    assert decoded.shape == (70, 110, 3)


def test_evidence_generator_handles_boundary_and_out_of_bounds_safely(generator: EvidenceGenerator):
    """Test that coordinates near or beyond image boundaries are clamped without throwing exceptions."""
    image = np.full((100, 100, 3), 120, dtype=np.uint8)

    # Case 1: Coordinates at top-left boundary
    bbox_edge = BoundingBox(x1=0, y1=0, x2=10, y2=10)
    crop_bytes, sha = generator.crop_region(image, bbox_edge, padding=20)
    assert crop_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(sha) == 64

    # Case 2: Coordinates extending past bottom-right boundary
    bbox_oob = BoundingBox(x1=90, y1=90, x2=150, y2=150)
    crop_bytes_oob, sha_oob = generator.crop_region(image, bbox_oob, padding=10)
    assert crop_bytes_oob.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(sha_oob) == 64

    # Case 3: Zero-area box fallback
    bbox_zero = BoundingBox(x1=50, y1=50, x2=50, y2=50)
    crop_bytes_zero, sha_zero = generator.crop_region(image, bbox_zero, padding=0)
    assert crop_bytes_zero.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(sha_zero) == 64


def test_generate_dossier_compiles_evidence_for_violations(generator: EvidenceGenerator):
    """Test generating a complete EvidenceDossier for detected violations."""
    image = np.full((300, 500, 3), 200, dtype=np.uint8)

    # Construct declarations with prohibited unit 'gms'
    bbox = BoundingBox(x1=20, y1=50, x2=180, y2=90)
    declarations = ProductDeclarations(
        net_quantity=ExtractedField(
            value=NetQuantityData(magnitude=500.0, unit="g", raw_unit="gms"),
            raw_text="Net Wt: 500 gms",
            confidence=0.95,
            bbox=bbox,
        ),
        raw_full_text="Net Wt: 500 gms",
        overall_extraction_confidence=0.95,
    )

    engine = LegalMetrologyRuleEngine()
    rule_results = engine.evaluate(declarations)

    dossier = generator.generate_dossier(image, declarations, rule_results)

    assert isinstance(dossier, EvidenceDossier)
    assert dossier.total_evidences >= 1

    # Find the crop for net_quantity.raw_unit
    unit_crop = next((c for c in dossier.crops if c.field_name == "net_quantity.raw_unit"), None)
    assert unit_crop is not None
    assert unit_crop.rule_id == "LMPC_R13"
    assert unit_crop.raw_text == "Net Wt: 500 gms"
    assert len(unit_crop.sha256_hash) == 64
    assert unit_crop.crop_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_models_enforce_immutability():
    """Verify that ScreeningDecision, VisualEvidenceCrop, and EvidenceDossier models are immutable."""
    decision = ScreeningDecision(
        verdict=ScreeningVerdict.NO_OBVIOUS_ISSUE,
        summary="Verified",
        confidence_score=0.95,
    )
    with pytest.raises(ValidationError):
        decision.verdict = ScreeningVerdict.NEEDS_REVIEW  # type: ignore

    bbox = BoundingBox(x1=0, y1=0, x2=10, y2=10)
    crop = VisualEvidenceCrop(
        rule_id="LMPC_R13",
        rule_reference="Rule 13",
        field_name="net_quantity",
        raw_text="500 gms",
        bbox=bbox,
        crop_bytes=b"fake_bytes",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    with pytest.raises(ValidationError):
        crop.rule_id = "MUTATED"  # type: ignore

    dossier = EvidenceDossier(crops=[crop], total_evidences=1)
    with pytest.raises(ValidationError):
        dossier.total_evidences = 5  # type: ignore
