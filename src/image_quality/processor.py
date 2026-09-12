"""Image quality assessment and validation processor using OpenCV."""

import cv2
import numpy as np

from src.image_quality.models import ImageQualityMetrics


class ImageQualityChecker:
    """Evaluates raw image bytes against optical criteria for compliance screening."""

    BLUR_THRESHOLD: float = 80.0
    GLARE_THRESHOLD: float = 0.05
    GLARE_LUMINANCE_CUTOFF: int = 250

    def load_image(self, image_bytes: bytes) -> np.ndarray:
        """Safely decodes image bytes into a BGR numpy array using OpenCV.

        Args:
            image_bytes: Raw binary payload of the image.

        Returns:
            Decoded BGR image as a numpy array.

        Raises:
            ValueError: If bytes are empty, invalid, corrupted, or cannot be decoded.
        """
        if not image_bytes:
            raise ValueError("Provided image bytes payload is empty.")

        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            if nparr.size == 0:
                raise ValueError("Provided buffer contains zero elements.")

            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                raise ValueError("Failed to decode image from provided bytes. Unsupported or corrupted format.")

            return img
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Unexpected error while decoding image bytes: {exc}") from exc

    def calculate_blur(self, gray_img: np.ndarray) -> float:
        """Calculates image sharpness using the variance of the Laplacian operator.

        Args:
            gray_img: Single-channel 2D grayscale numpy array.

        Returns:
            Laplacian variance as a floating-point score.
        """
        if gray_img.size == 0:
            return 0.0
        laplacian = cv2.Laplacian(gray_img, cv2.CV_64F)
        return float(laplacian.var())

    def calculate_glare(self, gray_img: np.ndarray) -> float:
        """Calculates specular glare ratio as pixels with luminance >= 250 over total pixels.

        Args:
            gray_img: Single-channel 2D grayscale numpy array.

        Returns:
            Glare ratio between 0.0 and 1.0.
        """
        total_pixels = gray_img.size
        if total_pixels == 0:
            return 0.0

        glare_pixels = int(np.count_nonzero(gray_img >= self.GLARE_LUMINANCE_CUTOFF))
        return float(glare_pixels / total_pixels)

    def assess_quality(self, image_bytes: bytes) -> tuple[np.ndarray, ImageQualityMetrics]:
        """Runs validation and optical quality assessment on raw image bytes.

        Args:
            image_bytes: Raw binary payload of the label image.

        Returns:
            A tuple of (bgr_image_array, ImageQualityMetrics).

        Raises:
            ValueError: If image bytes cannot be decoded.
        """
        img = self.load_image(image_bytes)
        height, width = img.shape[:2]

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        laplacian_var = self.calculate_blur(gray)
        glare_ratio = self.calculate_glare(gray)

        is_sharp = laplacian_var >= self.BLUR_THRESHOLD
        has_acceptable_glare = glare_ratio <= self.GLARE_THRESHOLD
        is_acceptable = is_sharp and has_acceptable_glare

        warnings: list[str] = []
        if not is_sharp:
            warnings.append(
                f"Image focus is degraded: Laplacian variance of {laplacian_var:.1f} is below the "
                f"minimum screening threshold of {self.BLUR_THRESHOLD:.1f}. OCR text recognition may fail or hallucinate."
            )

        if not has_acceptable_glare:
            warnings.append(
                f"Excessive specular glare detected: {glare_ratio * 100:.2f}% of pixels exceed the "
                f"luminance threshold of {self.GLARE_LUMINANCE_CUTOFF} (limit: {self.GLARE_THRESHOLD * 100:.1f}%). "
                f"Critical declarations (e.g., MRP or Date) in overexposed areas may be unreadable."
            )

        metrics = ImageQualityMetrics(
            width=width,
            height=height,
            laplacian_variance=round(laplacian_var, 2),
            glare_ratio=round(glare_ratio, 4),
            is_sharp=is_sharp,
            has_acceptable_glare=has_acceptable_glare,
            is_acceptable_for_screening=is_acceptable,
            quality_warnings=warnings,
        )

        return img, metrics
