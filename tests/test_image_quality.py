"""Unit tests for image ingestion and quality assessment module."""

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from src.image_quality.models import ImageQualityMetrics
from src.image_quality.processor import ImageQualityChecker


@pytest.fixture
def checker() -> ImageQualityChecker:
    """Fixture providing an instance of ImageQualityChecker."""
    return ImageQualityChecker()


def encode_image(img: np.ndarray, ext: str = ".png") -> bytes:
    """Helper utility to encode an OpenCV image array to bytes."""
    success, encoded = cv2.imencode(ext, img)
    assert success, "Failed to encode test image"
    return encoded.tobytes()


def test_load_empty_or_corrupted_bytes_raises_value_error(checker: ImageQualityChecker):
    """Test that loading empty or corrupted bytes raises a clean ValueError."""
    with pytest.raises(ValueError, match="empty"):
        checker.load_image(b"")

    with pytest.raises(ValueError, match="Unsupported or corrupted"):
        checker.load_image(b"corrupted_non_image_binary_data_12345")

    with pytest.raises(ValueError):
        checker.assess_quality(b"invalid_bytes")


def test_synthetic_sharp_image_passes_sharpness(checker: ImageQualityChecker):
    """Test that a high-contrast pattern (checkerboard) passes the sharpness threshold."""
    # Generate a 200x200 high-contrast checkerboard
    size = 200
    tile_size = 10
    pattern = np.zeros((size, size), dtype=np.uint8)
    for y in range(0, size, tile_size):
        for x in range(0, size, tile_size):
            if ((x // tile_size) + (y // tile_size)) % 2 == 0:
                pattern[y : y + tile_size, x : x + tile_size] = 200  # under 250 to avoid glare

    bgr = cv2.cvtColor(pattern, cv2.COLOR_GRAY2BGR)
    img_bytes = encode_image(bgr)

    decoded_img, metrics = checker.assess_quality(img_bytes)

    assert isinstance(decoded_img, np.ndarray)
    assert decoded_img.shape == (200, 200, 3)
    assert metrics.width == 200
    assert metrics.height == 200
    assert metrics.laplacian_variance >= checker.BLUR_THRESHOLD
    assert metrics.is_sharp is True
    assert metrics.has_acceptable_glare is True
    assert metrics.is_acceptable_for_screening is True
    assert len(metrics.quality_warnings) == 0


def test_synthetic_blurry_image_fails_sharpness_and_records_warning(checker: ImageQualityChecker):
    """Test that an excessively blurred image fails is_sharp and records a warning."""
    # Start with a pattern, then heavily blur it with Gaussian blur
    base = np.zeros((200, 200, 3), dtype=np.uint8)
    base[50:150, 50:150] = 180
    blurry = cv2.GaussianBlur(base, (45, 45), sigmaX=30)
    img_bytes = encode_image(blurry)

    _, metrics = checker.assess_quality(img_bytes)

    assert metrics.laplacian_variance < checker.BLUR_THRESHOLD
    assert metrics.is_sharp is False
    assert metrics.is_acceptable_for_screening is False
    assert any("focus is degraded" in warning for warning in metrics.quality_warnings)


def test_synthetic_glare_image_fails_glare_threshold(checker: ImageQualityChecker):
    """Test that an image with > 5% specular glare (>250 intensity) fails acceptable glare."""
    # 200x200 image with a white glare patch covering 15% of the total area
    img = np.full((200, 200, 3), 100, dtype=np.uint8)
    # 200*200 = 40000 pixels. 15% is 6000 pixels. A 80x80 box is 6400 pixels (~16%)
    img[20:100, 20:100] = 255  # Exceeds cutoff of 250

    img_bytes = encode_image(img)
    _, metrics = checker.assess_quality(img_bytes)

    assert metrics.glare_ratio > checker.GLARE_THRESHOLD
    assert metrics.has_acceptable_glare is False
    assert metrics.is_acceptable_for_screening is False
    assert any("Excessive specular glare" in warning for warning in metrics.quality_warnings)


def test_image_quality_metrics_immutability(checker: ImageQualityChecker):
    """Test that ImageQualityMetrics is an immutable Pydantic model."""
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    img_bytes = encode_image(img)

    _, metrics = checker.assess_quality(img_bytes)
    assert isinstance(metrics, ImageQualityMetrics)

    with pytest.raises(ValidationError):
        # Attempting to modify frozen model attribute must raise ValidationError
        metrics.is_sharp = False  # type: ignore

    with pytest.raises(ValidationError):
        metrics.width = 999  # type: ignore
