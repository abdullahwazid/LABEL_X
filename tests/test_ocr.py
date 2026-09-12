"""Unit tests for optical character recognition (OCR) engine and bounding box extraction."""

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from src.ocr.models import BoundingBox, OCRLine, OCRResult
from src.ocr.engine import OCRService


def test_bounding_box_calculations_and_immutability():
    """Verify BoundingBox area, aspect ratio calculations, and frozen immutability."""
    bbox = BoundingBox(x1=20, y1=40, x2=120, y2=90)

    # Width: 100, Height: 50
    assert bbox.area() == 5000
    assert bbox.aspect_ratio() == pytest.approx(2.0, 0.001)

    # Test edge cases (zero dimensions)
    zero_box = BoundingBox(x1=50, y1=50, x2=50, y2=50)
    assert zero_box.area() == 0
    assert zero_box.aspect_ratio() == 0.0

    # Immutability validation
    with pytest.raises(ValidationError):
        bbox.x1 = 0  # type: ignore


def test_ocr_line_and_result_immutability():
    """Verify OCRLine and OCRResult models are immutable."""
    bbox = BoundingBox(x1=0, y1=0, x2=100, y2=25)
    line = OCRLine(text="TEST DECLARATION", confidence=0.92, bbox=bbox)
    result = OCRResult(lines=[line], raw_text="TEST DECLARATION", mean_confidence=0.92, engine_used="MOCK_FALLBACK")

    with pytest.raises(ValidationError):
        line.text = "MUTATED"  # type: ignore

    with pytest.raises(ValidationError):
        result.mean_confidence = 0.5  # type: ignore


def test_ocr_service_initialization():
    """Verify OCRService initializes safely without throwing unhandled exceptions."""
    service = OCRService()
    assert isinstance(service.is_tesseract_available, bool)
    assert service.is_tesseract_available in (True, False)


def test_extract_text_blank_image():
    """Verify extract_text gracefully returns an empty result on a blank white image."""
    service = OCRService()
    blank_img = np.full((300, 400, 3), 255, dtype=np.uint8)

    result = service.extract_text(blank_img)

    assert isinstance(result, OCRResult)
    assert len(result.lines) == 0
    assert result.raw_text == ""
    assert result.mean_confidence == 0.0
    assert result.engine_used in ("PYTESSERACT", "MOCK_FALLBACK")


def test_extract_text_synthetic_high_contrast_image():
    """Verify that an image with drawn text lines produces populated lines and bounding boxes."""
    service = OCRService()

    # Draw synthetic high-contrast text lines
    img = np.full((300, 600, 3), 255, dtype=np.uint8)
    cv2.putText(img, "NET QUANTITY: 500 g", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cv2.putText(img, "MRP Rs. 150.00", (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    result = service.extract_text(img)

    assert isinstance(result, OCRResult)
    assert len(result.lines) >= 1
    assert len(result.raw_text) > 0
    assert result.mean_confidence > 0.0

    for line in result.lines:
        assert isinstance(line.bbox, BoundingBox)
        assert line.bbox.area() > 0
        assert line.confidence > 0.0


def test_extract_text_invalid_dimensions_raises_value_error():
    """Verify that invalid image dimensions (0x0 or empty array) raise ValueError."""
    service = OCRService()

    empty_img = np.zeros((0, 0, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="Invalid image dimensions"):
        service.extract_text(empty_img)

    none_img = None  # type: ignore
    with pytest.raises(ValueError, match="Invalid image dimensions"):
        service.extract_text(none_img)


def test_ocr_service_injected_text():
    """Verify that injected text lines are extracted properly with spatial boxes."""
    service = OCRService()
    service.is_tesseract_available = False  # Force fallback behavior
    service.set_injected_text(["NET WT: 500 g", "MRP Rs. 199.00 INCL OF ALL TAXES"])

    img = np.full((200, 500, 3), 255, dtype=np.uint8)
    result = service.extract_text(img)

    assert result.engine_used == "MOCK_FALLBACK"
    assert len(result.lines) == 2
    assert "NET WT: 500 g" in result.lines[0].text
    assert "MRP Rs. 199.00 INCL OF ALL TAXES" in result.lines[1].text
    assert result.mean_confidence == 0.95


def test_preprocess_dot_matrix():
    """Verify dot-matrix adaptive enhancement produces valid binarized output."""
    service = OCRService()
    img = np.full((100, 200), 200, dtype=np.uint8)
    # Simulate dot-matrix pattern with isolated pixels
    img[40:60:4, 30:170:4] = 30

    enhanced = service.preprocess_dot_matrix(img)

    assert isinstance(enhanced, np.ndarray)
    assert enhanced.shape == img.shape
    assert enhanced.dtype == np.uint8
    # Should be binarized (values primarily 0 and 255)
    unique_vals = set(np.unique(enhanced))
    assert unique_vals.issubset({0, 255})


def test_windows_tesseract_detection_and_execution():
    """Verify standard Windows installation path is detected and uses real PyTesseract."""
    import os
    windows_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(windows_path):
        service = OCRService()
        assert service.is_tesseract_available is True

        img = np.full((120, 500, 3), 255, dtype=np.uint8)
        cv2.putText(img, "NET QTY: 500 g", (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        res = service.extract_text(img)

        assert res.engine_used == "PYTESSERACT"
        assert len(res.lines) >= 1
        assert any("500" in line.text for line in res.lines)


def test_bbox_iou_computation():
    """Verify BoundingBox IoU calculations for identical, disjoint, and partial boxes."""
    b1 = BoundingBox(x1=10, y1=10, x2=100, y2=50)
    b2 = BoundingBox(x1=10, y1=10, x2=100, y2=50)
    assert OCRService._compute_bbox_iou(b1, b2) == pytest.approx(1.0, 0.001)

    b3 = BoundingBox(x1=200, y1=200, x2=300, y2=250)
    assert OCRService._compute_bbox_iou(b1, b3) == 0.0

    b4 = BoundingBox(x1=55, y1=10, x2=145, y2=50)
    assert OCRService._compute_bbox_iou(b1, b4) == pytest.approx(1 / 3, 0.01)


def test_merge_and_deduplicate_lines():
    """Verify deduplication keeps higher confidence line when IoU > 0.5 and merges disjoint lines."""
    service = OCRService()
    line_std = OCRLine(
        text="MRP Rs. 10.00",
        confidence=0.80,
        bbox=BoundingBox(x1=10, y1=10, x2=100, y2=40),
    )
    line_inv_dup = OCRLine(
        text="MRP Rs. 10.00",
        confidence=0.95,
        bbox=BoundingBox(x1=12, y1=10, x2=98, y2=40),  # IoU > 0.8 with line_std
    )
    line_inv_separate = OCRLine(
        text="PKD. 21/08/26",
        confidence=0.90,
        bbox=BoundingBox(x1=10, y1=50, x2=100, y2=80),
    )

    merged = service._merge_and_deduplicate_lines([line_std], [line_inv_dup, line_inv_separate], iou_threshold=0.5)

    assert len(merged) == 2
    mrp_line = next(l for l in merged if "MRP" in l.text)
    assert mrp_line.confidence == 0.95
    pkd_line = next(l for l in merged if "PKD" in l.text)
    assert pkd_line.text == "PKD. 21/08/26"


def test_dual_polarity_extraction():
    """Verify extract_text detects both white-on-dark text and dark-on-white text in a single image."""
    service = OCRService()
    if not service.is_tesseract_available:
        pytest.skip("PyTesseract binary not available on host system.")

    canvas = np.full((200, 600), 30, dtype=np.uint8)
    # Light-on-dark text (white text on dark background)
    cv2.putText(canvas, "MRP Rs. 150.00", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 255, 2)
    # Dark-on-light text (black text inside a white box)
    cv2.rectangle(canvas, (320, 20), (580, 150), 250, -1)
    cv2.putText(canvas, "10.00 Rs. 0.17 per g", (330, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 10, 2)

    result = service.extract_text(canvas)

    assert result.engine_used == "PYTESSERACT"
    assert len(result.lines) >= 2
    raw_combined = " ".join(l.text for l in result.lines)
    assert "MRP" in raw_combined or "150" in raw_combined
    assert "10.00" in raw_combined or "0.17" in raw_combined



