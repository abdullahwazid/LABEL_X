"""Optical character recognition service with robust fallback handling."""

from collections import defaultdict
import logging
import os
import cv2
import numpy as np
import pytesseract
from pytesseract import Output

from src.ocr.models import BoundingBox, OCRLine, OCRResult

logger = logging.getLogger(__name__)

windows_tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(windows_tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = windows_tesseract_path


DEFAULT_TESSERACT_CONFIG: str = "--oem 3 --psm 11"


class OCRService:
    """Provides optical character recognition with line-level bounding boxes.
    
    Operates using PyTesseract when a local Tesseract installation is present.
    If the Tesseract binary is absent or unreachable, seamlessly falls back to
    a deterministic CV contour-based mock extraction layer to prevent system failure.
    """

    def __init__(
        self,
        tesseract_cmd: str | None = None,
        tesseract_config: str = DEFAULT_TESSERACT_CONFIG,
    ) -> None:
        """Initializes the OCR service.

        Args:
            tesseract_cmd: Optional explicit path to the tesseract executable.
            tesseract_config: Optional Tesseract CLI configuration arguments (defaults to '--oem 3 --psm 11').
        """
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        elif os.path.exists(windows_tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = windows_tesseract_path

        self.tesseract_config: str = tesseract_config
        self._injected_text: list[str] | None = None
        self.is_tesseract_available: bool = self._probe_tesseract()

    def _probe_tesseract(self) -> bool:
        """Probes whether Tesseract binary is executable on the host system."""
        try:
            version = pytesseract.get_tesseract_version()
            logger.info("Tesseract binary detected successfully (version: %s)", version)
            return True
        except (pytesseract.TesseractNotFoundError, Exception) as exc:
            logger.warning(
                "Tesseract binary not found or unreachable on system PATH: %s. "
                "OCRService will operate in MOCK_FALLBACK mode.",
                exc,
            )
            return False

    @property
    def injected_text(self) -> list[str] | None:
        """Returns currently injected synthetic text lines, if any."""
        return self._injected_text

    def set_injected_text(self, lines: list[str] | None) -> None:
        """Injects synthetic text lines for testing or simulation purposes."""
        self._injected_text = lines

    @staticmethod
    def _compute_bbox_iou(box_a: BoundingBox, box_b: BoundingBox) -> float:
        """Calculates Intersection-over-Union (IoU) between two bounding boxes."""
        ix1 = max(box_a.x1, box_b.x1)
        iy1 = max(box_a.y1, box_b.y1)
        ix2 = min(box_a.x2, box_b.x2)
        iy2 = min(box_a.y2, box_b.y2)

        iw = max(0, ix2 - ix1)
        ih = max(0, iy2 - iy1)
        intersection = iw * ih

        if intersection == 0:
            return 0.0

        area_a = box_a.area()
        area_b = box_b.area()
        union = area_a + area_b - intersection

        if union <= 0:
            return 0.0
        return float(intersection / union)

    def _merge_and_deduplicate_lines(
        self,
        primary_lines: list[OCRLine],
        secondary_lines: list[OCRLine],
        iou_threshold: float = 0.5,
    ) -> list[OCRLine]:
        """Merges two sets of OCR lines, deduplicating lines with bounding box IoU > iou_threshold."""
        if not primary_lines:
            return list(secondary_lines)
        if not secondary_lines:
            return list(primary_lines)

        merged = list(primary_lines)

        for sec_line in secondary_lines:
            matched_idx = -1
            best_iou = 0.0

            for idx, pri_line in enumerate(merged):
                iou = self._compute_bbox_iou(sec_line.bbox, pri_line.bbox)
                if iou > iou_threshold and iou > best_iou:
                    best_iou = iou
                    matched_idx = idx

            if matched_idx >= 0:
                curr_line = merged[matched_idx]
                if (sec_line.confidence > curr_line.confidence) or (
                    sec_line.confidence >= curr_line.confidence - 0.05
                    and len(sec_line.text.strip()) > len(curr_line.text.strip())
                ):
                    merged[matched_idx] = sec_line
            else:
                merged.append(sec_line)

        merged.sort(key=lambda l: (l.bbox.y1, l.bbox.x1))
        return merged

    def extract_text(self, image: np.ndarray) -> OCRResult:
        """Extracts recognized text lines and spatial bounding boxes from an image.

        Args:
            image: BGR or Grayscale numpy array.

        Returns:
            OCRResult containing lines, full raw text, mean confidence, and engine used.

        Raises:
            ValueError: If the input image is None, empty, or has 0x0 dimensions.
        """
        if image is None or image.size == 0 or image.shape[0] == 0 or image.shape[1] == 0:
            raise ValueError("Invalid image dimensions. Expected non-empty image array with height > 0 and width > 0.")

        # Preprocess to grayscale
        if len(image.shape) == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif len(image.shape) == 2:
            gray = image
        else:
            gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)

        if self.is_tesseract_available:
            try:
                # 1. Dual-Polarity Pass:
                # Pass A: Standard polarity (dark-on-light) with adaptive CLAHE
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                gray_clahe = clahe.apply(gray)
                res_std = self._extract_with_tesseract(gray_clahe)

                # Pass B: Inverted polarity (light-on-dark, white text on dark wrappers)
                gray_inv = cv2.bitwise_not(gray_clahe)
                res_inv = self._extract_with_tesseract(gray_inv)

                # Merge and deduplicate by bounding box IoU > 0.5
                merged_lines = self._merge_and_deduplicate_lines(
                    res_std.lines, res_inv.lines, iou_threshold=0.5
                )

                # 2. Adaptive fallback: if recognition yielded zero lines or low confidence,
                # attempt dot-matrix morphological enhancement
                mean_conf = (
                    round(sum(l.confidence for l in merged_lines) / len(merged_lines), 3)
                    if merged_lines
                    else 0.0
                )
                if len(merged_lines) == 0 or mean_conf < 0.60:
                    enhanced_gray = self.preprocess_dot_matrix(gray)
                    res_dm = self._extract_with_tesseract(enhanced_gray)
                    if len(res_dm.lines) > len(merged_lines) or (
                        len(res_dm.lines) == len(merged_lines)
                        and res_dm.mean_confidence > mean_conf
                    ):
                        merged_lines = self._merge_and_deduplicate_lines(
                            merged_lines, res_dm.lines, iou_threshold=0.5
                        )
                        mean_conf = (
                            round(sum(l.confidence for l in merged_lines) / len(merged_lines), 3)
                            if merged_lines
                            else 0.0
                        )

                raw_text = "\n".join(l.text for l in merged_lines)
                return OCRResult(
                    lines=merged_lines,
                    raw_text=raw_text,
                    mean_confidence=mean_conf,
                    engine_used="PYTESSERACT",
                )
            except pytesseract.TesseractNotFoundError as err:
                logger.warning("Tesseract binary missing at runtime: %s. Switching to MOCK_FALLBACK.", err)
                self.is_tesseract_available = False

        return self._extract_with_mock_fallback(gray)

    def preprocess_dot_matrix(self, gray: np.ndarray) -> np.ndarray:
        """Applies adaptive enhancement for low-contrast or dot-matrix inkjet printing.

        Pipelines:
        1. Grayscale verification.
        2. CLAHE (Contrast Limited Adaptive Histogram Equalization) with clipLimit=2.0, tileGridSize=(8, 8).
        3. Light Gaussian blur (3x3) to bridge small dot-matrix micro-disconnects.
        4. Otsu's thresholding for binarization.
        5. Morphological close with 2x2 rectangular kernel on inverted text to connect dots.
        """
        if len(gray.shape) == 3:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Determine if text is dark on light background
        is_dark_text = np.mean(thresh) > 127
        binary_text = cv2.bitwise_not(thresh) if is_dark_text else thresh

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        closed = cv2.morphologyEx(binary_text, cv2.MORPH_CLOSE, kernel)

        if is_dark_text:
            return cv2.bitwise_not(closed)
        return closed

    def _extract_with_tesseract(self, gray: np.ndarray, config: str | None = None) -> OCRResult:
        """Extracts text tokens and groups them into lines using PyTesseract."""
        cfg = config or self.tesseract_config
        data = pytesseract.image_to_data(gray, config=cfg, output_type=Output.DICT)
        num_boxes = len(data["text"])

        # Group words by (block_num, par_num, line_num)
        lines_dict: dict[tuple[int, int, int], list[dict]] = defaultdict(list)

        for i in range(num_boxes):
            text = str(data["text"][i]).strip()
            conf_val = float(data["conf"][i])

            # Filter empty strings and invalid confidence scores
            if not text or conf_val < 0.0:
                continue

            lines_dict[(data["block_num"][i], data["par_num"][i], data["line_num"][i])].append(
                {
                    "text": text,
                    "conf": conf_val / 100.0,  # Scale to 0.0 - 1.0
                    "left": int(data["left"][i]),
                    "top": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                }
            )

        ocr_lines: list[OCRLine] = []
        for _, words in lines_dict.items():
            if not words:
                continue
            line_text = " ".join(w["text"] for w in words)
            mean_line_conf = sum(w["conf"] for w in words) / len(words)
            x1 = min(w["left"] for w in words)
            y1 = min(w["top"] for w in words)
            x2 = max(w["left"] + w["width"] for w in words)
            y2 = max(w["top"] + w["height"] for w in words)

            ocr_lines.append(
                OCRLine(
                    text=line_text,
                    confidence=round(mean_line_conf, 3),
                    bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                )
            )

        raw_text = "\n".join(l.text for l in ocr_lines)
        mean_conf = (
            round(sum(l.confidence for l in ocr_lines) / len(ocr_lines), 3) if ocr_lines else 0.0
        )

        return OCRResult(
            lines=ocr_lines,
            raw_text=raw_text,
            mean_confidence=mean_conf,
            engine_used="PYTESSERACT",
        )

    def _extract_with_mock_fallback(self, gray: np.ndarray) -> OCRResult:
        """Fallback processor: detects text-like high-contrast regions via edge/contour analysis."""
        # Detect edges
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        raw_boxes: list[tuple[int, int, int, int]] = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # Filter noise
            if w >= 4 and h >= 4 and (w * h) >= 16:
                raw_boxes.append((x, y, x + w, y + h))

        # Check for blank image
        if not raw_boxes and not self._injected_text:
            return OCRResult(
                lines=[],
                raw_text="",
                mean_confidence=0.0,
                engine_used="MOCK_FALLBACK",
            )

        # Merge spatially overlapping or horizontally adjacent bounding boxes
        merged_boxes = self._cluster_line_boxes(raw_boxes)

        ocr_lines: list[OCRLine] = []
        if self._injected_text is not None:
            # Map injected text lines to detected boxes or default synthetic positions
            for idx, text_line in enumerate(self._injected_text):
                if idx < len(merged_boxes):
                    x1, y1, x2, y2 = merged_boxes[idx]
                else:
                    x1, y1, x2, y2 = 10, 10 + (idx * 30), 200, 35 + (idx * 30)

                ocr_lines.append(
                    OCRLine(
                        text=text_line,
                        confidence=0.95,
                        bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    )
                )
        else:
            # Generate synthetic line detections for identified contours
            for idx, (x1, y1, x2, y2) in enumerate(merged_boxes):
                ocr_lines.append(
                    OCRLine(
                        text=f"DETECTED_TEXT_LINE_{idx + 1}",
                        confidence=0.90,
                        bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    )
                )

        raw_text = "\n".join(l.text for l in ocr_lines)
        mean_conf = (
            round(sum(l.confidence for l in ocr_lines) / len(ocr_lines), 3) if ocr_lines else 0.0
        )

        return OCRResult(
            lines=ocr_lines,
            raw_text=raw_text,
            mean_confidence=mean_conf,
            engine_used="MOCK_FALLBACK",
        )

    def _cluster_line_boxes(
        self, boxes: list[tuple[int, int, int, int]]
    ) -> list[tuple[int, int, int, int]]:
        """Groups nearby horizontal character bounding boxes into coherent text lines."""
        if not boxes:
            return []

        # Sort boxes primarily by vertical position y1, then x1
        sorted_boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
        lines: list[list[tuple[int, int, int, int]]] = []

        for box in sorted_boxes:
            bx1, by1, bx2, by2 = box
            matched_line = False
            for line in lines:
                # Check vertical alignment with line's median height
                ly1 = min(b[1] for b in line)
                ly2 = max(b[3] for b in line)
                line_height = max(1, ly2 - ly1)
                box_height = max(1, by2 - by1)

                # Overlap test: centers are close vertically
                box_cy = (by1 + by2) / 2
                line_cy = (ly1 + ly2) / 2

                if abs(box_cy - line_cy) <= max(line_height, box_height) * 0.7:
                    line.append(box)
                    matched_line = True
                    break

            if not matched_line:
                lines.append([box])

        # Merge each line's boxes into one bounding box
        merged: list[tuple[int, int, int, int]] = []
        for line in lines:
            lx1 = min(b[0] for b in line)
            ly1 = min(b[1] for b in line)
            lx2 = max(b[2] for b in line)
            ly2 = max(b[3] for b in line)
            merged.append((lx1, ly1, lx2, ly2))

        # Sort merged lines top-to-bottom
        return sorted(merged, key=lambda b: b[1])
