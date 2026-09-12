"""Unit tests for integrated compliance screening pipeline and synthetic generator."""

from pathlib import Path
import pytest

from src.decisions.models import ScreeningVerdict
from src.mock_generator import SyntheticPackageGenerator
from src.pipeline import CompliancePipeline, PipelineResult
from src.regulatory.models import ViolationSeverity
from src.rules.models import RuleStatus


@pytest.fixture
def mock_gen() -> SyntheticPackageGenerator:
    """Fixture providing SyntheticPackageGenerator."""
    return SyntheticPackageGenerator()


@pytest.fixture
def pipeline() -> CompliancePipeline:
    """Fixture providing CompliancePipeline instance."""
    return CompliancePipeline()


def test_synthetic_sample_generation(mock_gen: SyntheticPackageGenerator, tmp_path: Path):
    """Test generating synthetic sample labels and saving them to disk."""
    compliant_bytes = mock_gen.generate_compliant_label()
    unit_violation_bytes = mock_gen.generate_unit_violation_label()
    mrp_violation_bytes = mock_gen.generate_mrp_tax_violation_label()

    png_header = b"\x89PNG\r\n\x1a\n"
    assert compliant_bytes.startswith(png_header)
    assert unit_violation_bytes.startswith(png_header)
    assert mrp_violation_bytes.startswith(png_header)

    saved_paths = mock_gen.save_samples_to_disk(target_dir=str(tmp_path))
    assert len(saved_paths) == 3
    for filename, filepath in saved_paths.items():
        p = Path(filepath)
        assert p.exists()
        assert p.is_file()
        assert p.stat().st_size > 1000


def test_end_to_end_compliant_label(mock_gen: SyntheticPackageGenerator, pipeline: CompliancePipeline):
    """Test end-to-end processing of a compliant label yields a valid pipeline result."""
    img_bytes = mock_gen.generate_compliant_label()

    if not pipeline.ocr_service.is_tesseract_available:
        pipeline.set_injected_text(mock_gen.COMPLIANT_TEXT)

    result = pipeline.process_package(img_bytes)

    assert isinstance(result, PipelineResult)
    assert result.quality_metrics.is_acceptable_for_screening is True
    assert result.decision.verdict in (
        ScreeningVerdict.NO_OBVIOUS_ISSUE,
        ScreeningVerdict.NEEDS_REVIEW,
    )

    if not pipeline.ocr_service.is_tesseract_available:
        assert result.decision.verdict == ScreeningVerdict.NO_OBVIOUS_ISSUE
        assert result.decision.critical_violations_count == 0
        assert result.decision.major_violations_count == 0


def test_end_to_end_corrupted_bytes_raises_value_error(pipeline: CompliancePipeline):
    """Test that submitting invalid or corrupted bytes raises a clean ValueError."""
    with pytest.raises(ValueError, match="empty"):
        pipeline.process_package(b"")

    with pytest.raises(ValueError):
        pipeline.process_package(b"corrupted_non_image_payload_xyz_123")


def test_end_to_end_unit_violation_label_flags_rule_13(
    mock_gen: SyntheticPackageGenerator, pipeline: CompliancePipeline
):
    """Test end-to-end processing of a unit-violation label flags Rule 13 with evidence."""
    img_bytes = mock_gen.generate_unit_violation_label()

    if not pipeline.ocr_service.is_tesseract_available:
        pipeline.set_injected_text(mock_gen.UNIT_VIOLATION_TEXT)

    result = pipeline.process_package(img_bytes)

    assert isinstance(result, PipelineResult)
    assert result.decision.verdict == ScreeningVerdict.POTENTIAL_NON_COMPLIANCE

    r13 = next((r for r in result.rule_results if r.rule_id == "LMPC_R13"), None)
    assert r13 is not None
    assert r13.status == RuleStatus.FAIL
    assert r13.violation is not None
    assert r13.violation.severity == ViolationSeverity.CRITICAL
    assert "prohibited" in r13.violation.message.lower()

    # Verify visual evidence dossier captures the infraction
    assert result.evidence_dossier.total_evidences >= 1
    r13_crop = next((c for c in result.evidence_dossier.crops if c.rule_id == "LMPC_R13"), None)
    assert r13_crop is not None
    assert len(r13_crop.sha256_hash) == 64
    assert r13_crop.crop_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_end_to_end_mrp_violation_label_flags_rule_6_1_e(
    mock_gen: SyntheticPackageGenerator, pipeline: CompliancePipeline
):
    """Test end-to-end processing of an MRP missing taxes label flags Rule 6(1)(e)."""
    img_bytes = mock_gen.generate_mrp_tax_violation_label()

    if not pipeline.ocr_service.is_tesseract_available:
        pipeline.set_injected_text(mock_gen.MRP_VIOLATION_TEXT)

    result = pipeline.process_package(img_bytes)

    assert result.decision.verdict == ScreeningVerdict.POTENTIAL_NON_COMPLIANCE

    mrp_res = next((r for r in result.rule_results if r.rule_id == "LMPC_R06_1_E"), None)
    assert mrp_res is not None
    assert mrp_res.status == RuleStatus.FAIL
    assert mrp_res.violation is not None
    assert mrp_res.violation.severity == ViolationSeverity.CRITICAL
    assert "inclusive of all taxes" in mrp_res.violation.message.lower()
