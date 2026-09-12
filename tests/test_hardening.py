"""Production hardening and edge-case fault tolerance tests."""

import cv2
import numpy as np
import pytest

from src.decisions.models import ScreeningVerdict
from src.pipeline import CompliancePipeline, PipelineResult


@pytest.fixture
def pipeline() -> CompliancePipeline:
    """Fixture providing an instance of CompliancePipeline."""
    return CompliancePipeline()


def test_zero_byte_payload_raises_value_error(pipeline: CompliancePipeline):
    """Test that submitting zero bytes raises a clean ValueError."""
    with pytest.raises(ValueError, match="empty"):
        pipeline.process_package(b"")


def test_non_image_bytes_raises_value_error(pipeline: CompliancePipeline):
    """Test that submitting random non-image ASCII/binary data raises a clean ValueError."""
    with pytest.raises(ValueError, match="Unsupported or corrupted"):
        pipeline.process_package(b"NOT_AN_IMAGE_FILE_DATA_ASCII_12345")


def test_giant_image_executes_safely_without_crashing(pipeline: CompliancePipeline):
    """Test that a giant 4000x4000 image processes through all pipeline stages safely."""
    # Construct a 4000x4000 image with light background
    giant = np.full((4000, 4000, 3), 240, dtype=np.uint8)
    cv2.putText(
        giant,
        "GIANT PACKAGE TEST LABEL",
        (200, 500),
        cv2.FONT_HERSHEY_SIMPLEX,
        3.0,
        (20, 20, 20),
        6,
    )

    success, encoded = cv2.imencode(".png", giant)
    assert success
    giant_bytes = encoded.tobytes()

    result = pipeline.process_package(giant_bytes)

    assert isinstance(result, PipelineResult)
    assert result.quality_metrics.width == 4000
    assert result.quality_metrics.height == 4000
    assert result.decision.verdict in (
        ScreeningVerdict.NO_OBVIOUS_ISSUE,
        ScreeningVerdict.NEEDS_REVIEW,
        ScreeningVerdict.POTENTIAL_NON_COMPLIANCE,
    )


def test_tiny_image_flags_for_review_or_fails_screening(pipeline: CompliancePipeline):
    """Test that a tiny 20x20 image is flagged for review and does not falsely pass."""
    tiny = np.full((20, 20, 3), 220, dtype=np.uint8)
    success, encoded = cv2.imencode(".png", tiny)
    assert success
    tiny_bytes = encoded.tobytes()

    result = pipeline.process_package(tiny_bytes)

    assert isinstance(result, PipelineResult)
    assert result.quality_metrics.width == 20
    assert result.quality_metrics.height == 20

    # Tiny blank image must not emit a false NO_OBVIOUS_ISSUE
    assert result.decision.verdict in (
        ScreeningVerdict.NEEDS_REVIEW,
        ScreeningVerdict.POTENTIAL_NON_COMPLIANCE,
    )
