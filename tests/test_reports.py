"""Unit tests for statutory compliance notice and inspection report generator."""

import pytest
from pydantic import ValidationError

from src.mock_generator import SyntheticPackageGenerator
from src.pipeline import CompliancePipeline, PipelineResult
from src.reports.generator import ReportGenerator
from src.reports.models import InspectionReport
from src.report.pdf_generator import build_pdf_report, sanitize_text


@pytest.fixture
def generator() -> ReportGenerator:
    """Fixture providing ReportGenerator instance."""
    return ReportGenerator()


@pytest.fixture
def compliant_pipeline_result() -> PipelineResult:
    """Fixture providing an end-to-end compliant PipelineResult."""
    mock_gen = SyntheticPackageGenerator()
    pipeline = CompliancePipeline()
    img_bytes = mock_gen.generate_compliant_label()

    if not pipeline.ocr_service.is_tesseract_available:
        pipeline.set_injected_text(mock_gen.COMPLIANT_TEXT)

    return pipeline.process_package(img_bytes)


@pytest.fixture
def violation_pipeline_result() -> PipelineResult:
    """Fixture providing an end-to-end unit violation PipelineResult."""
    mock_gen = SyntheticPackageGenerator()
    pipeline = CompliancePipeline()
    img_bytes = mock_gen.generate_unit_violation_label()

    if not pipeline.ocr_service.is_tesseract_available:
        pipeline.set_injected_text(mock_gen.UNIT_VIOLATION_TEXT)

    return pipeline.process_package(img_bytes)


def test_report_generator_produces_valid_header_disclaimer_and_uuid(
    generator: ReportGenerator, compliant_pipeline_result: PipelineResult
):
    """Test report generator produces correct official header, statutory disclaimer, and inspection UUID."""
    test_uuid = "123e4567-e89b-12d3-a456-426614174000"
    image_name = "sample_biscuit_pack.png"

    report = generator.generate_text_report(test_uuid, compliant_pipeline_result, image_name)

    assert isinstance(report, InspectionReport)
    assert report.inspection_id == test_uuid
    assert report.verdict == "NO_OBVIOUS_ISSUE"
    assert report.total_violations == 0

    # Validate official header
    assert "LEGAL METROLOGY (PACKAGED COMMODITIES) SCREENING NOTICE" in report.report_text
    assert "Department of Consumer Affairs • Statutory Compliance Triage Report" in report.report_text

    # Validate evidentiary disclaimer
    assert "PRELIMINARY ADMINISTRATIVE AUDIT ONLY" in report.report_text
    assert "Section 36 of the Legal Metrology Act, 2009" in report.report_text

    # Validate metadata
    assert test_uuid in report.report_text
    assert image_name in report.report_text
    assert "Sharpness (Laplacian):" in report.report_text
    assert "Quality Gate Status: PASSED" in report.report_text

    # Validate declarations
    assert "500.0 g" in report.report_text
    assert "Rs. 150.00" in report.report_text


def test_report_generator_renders_infractions_and_evidence_hashes(
    generator: ReportGenerator, violation_pipeline_result: PipelineResult
):
    """Test that statutory infractions and visual evidence SHA-256 hashes are rendered in the report."""
    test_uuid = "987e6543-e21b-12d3-a456-426614174999"
    image_name = "sample_violation_units.png"

    report = generator.generate_text_report(test_uuid, violation_pipeline_result, image_name)

    assert report.total_violations >= 1
    assert report.verdict == "POTENTIAL_NON_COMPLIANCE"

    # Verify infraction schedule
    assert "SCHEDULE OF STATUTORY INFRACTIONS:" in report.report_text
    assert "LMPC_R13" in report.report_text
    assert "Rule 13 read with Second Schedule" in report.report_text
    assert "CRITICAL" in report.report_text
    assert "gms" in report.report_text

    # Verify cryptographic chain of custody
    assert "CRYPTOGRAPHIC CHAIN OF CUSTODY (VISUAL EVIDENCE):" in report.report_text
    assert len(violation_pipeline_result.evidence_dossier.crops) >= 1

    crop_hash = violation_pipeline_result.evidence_dossier.crops[0].sha256_hash
    assert crop_hash in report.report_text
    assert len(crop_hash) == 64


def test_inspection_report_immutability():
    """Verify that InspectionReport is frozen and rejects runtime modification."""
    report = InspectionReport(
        inspection_id="11111111-2222-3333-4444-555555555555",
        generated_at="2026-09-11T12:00:00Z",
        report_text="SAMPLE NOTICE",
        verdict="NO_OBVIOUS_ISSUE",
        total_violations=0,
    )

    with pytest.raises(ValidationError):
        report.verdict = "POTENTIAL_NON_COMPLIANCE"  # type: ignore

    with pytest.raises(ValidationError):
        report.total_violations = 5  # type: ignore


def test_sanitize_text():
    """Verify Unicode symbols like Rupee and bullet are sanitized for FPDF Latin-1."""
    raw = "MRP: ₹ 150.00 • Mfg: 08/2026 “Special”"
    cleaned = sanitize_text(raw)
    assert "Rs." in cleaned
    assert "•" not in cleaned
    assert '"Special"' in cleaned
    # Ensure it encodes cleanly in latin-1
    cleaned.encode("latin-1")


def test_build_pdf_report_compliant(compliant_pipeline_result: PipelineResult):
    """Verify PDF report generation for compliant pipeline result."""
    pdf_bytes = build_pdf_report(compliant_pipeline_result, audit_id="compliant-audit-001")
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert bytes(pdf_bytes).startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_build_pdf_report_violations(violation_pipeline_result: PipelineResult):
    """Verify PDF report generation for violation pipeline result."""
    pdf_bytes = build_pdf_report(violation_pipeline_result, audit_id="violation-audit-002")
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert bytes(pdf_bytes).startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
