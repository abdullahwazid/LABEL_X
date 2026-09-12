"""Visual evidence generation and cryptographic audit hashing module."""

import hashlib
from typing import Optional
import cv2
import numpy as np

from src.evidence.models import EvidenceDossier, VisualEvidenceCrop
from src.extraction.models import ExtractedField, ProductDeclarations
from src.ocr.models import BoundingBox
from src.rules.models import RuleEvaluationResult, RuleStatus


class EvidenceGenerator:
    """Extracts cropped image evidence for compliance infractions and computes cryptographic hashes."""

    def crop_region(
        self, image: np.ndarray, bbox: BoundingBox, padding: int = 10
    ) -> tuple[bytes, str]:
        """Crops an image region with padding, clamped to image boundaries, and encodes to PNG bytes.

        Args:
            image: BGR source image numpy array.
            bbox: Spatial bounding box of the declaration.
            padding: Pixel padding around the bounding box.

        Returns:
            Tuple of (png_crop_bytes, sha256_hex_digest).
        """
        h, w = image.shape[:2]

        x1 = max(0, int(bbox.x1) - padding)
        y1 = max(0, int(bbox.y1) - padding)
        x2 = min(w, int(bbox.x2) + padding)
        y2 = min(h, int(bbox.y2) + padding)

        # Fallback to safe patch if crop area is invalid or empty
        if x2 <= x1 or y2 <= y1 or (x2 - x1) <= 0 or (y2 - y1) <= 0:
            crop = image[0 : min(10, h), 0 : min(10, w)]
        else:
            crop = image[y1:y2, x1:x2]

        if crop.size == 0 or crop.shape[0] == 0 or crop.shape[1] == 0:
            crop = np.zeros((10, 10, 3), dtype=np.uint8)

        success, encoded = cv2.imencode(".png", crop)
        if not success:
            # Fallback encode
            success, encoded = cv2.imencode(".png", np.zeros((10, 10, 3), dtype=np.uint8))

        crop_bytes = encoded.tobytes()
        sha256_hash = hashlib.sha256(crop_bytes).hexdigest()

        return crop_bytes, sha256_hash

    def generate_dossier(
        self,
        image: np.ndarray,
        declarations: ProductDeclarations,
        rule_results: list[RuleEvaluationResult],
    ) -> EvidenceDossier:
        """Compiles an immutable evidence dossier for rule evaluation findings.

        Args:
            image: Original package image array.
            declarations: Extracted structured product declarations.
            rule_results: Evaluated statutory rule outcomes.

        Returns:
            An immutable EvidenceDossier instance.
        """
        # Field lookup mapping
        field_map: dict[str, Optional[ExtractedField]] = {
            "mrp": declarations.mrp,
            "mrp.includes_taxes": declarations.mrp,
            "net_quantity": declarations.net_quantity,
            "net_quantity.raw_unit": declarations.net_quantity,
            "net_quantity.unit": declarations.net_quantity,
            "net_quantity.magnitude": declarations.net_quantity,
            "unit_sale_price": declarations.unit_sale_price,
            "unit_sale_price.amount": declarations.unit_sale_price,
            "mfg_date": declarations.mfg_date,
            "consumer_care": declarations.consumer_care,
            "generic_name": declarations.generic_name,
        }

        crops: list[VisualEvidenceCrop] = []

        for result in rule_results:
            # Process failed or review-flagged rules with violations
            if result.status == RuleStatus.FAIL and result.violation:
                target_field_name = result.violation.field
                extracted_field = field_map.get(target_field_name)

                if extracted_field is not None:
                    bbox = (
                        extracted_field.bbox
                        if extracted_field.bbox is not None
                        else BoundingBox(x1=0, y1=0, x2=image.shape[1], y2=image.shape[0])
                    )
                    crop_bytes, sha256_hash = self.crop_region(image, bbox)

                    crops.append(
                        VisualEvidenceCrop(
                            rule_id=result.rule_id,
                            rule_reference=result.rule_reference,
                            field_name=target_field_name,
                            raw_text=extracted_field.raw_text,
                            bbox=bbox,
                            crop_bytes=crop_bytes,
                            sha256_hash=sha256_hash,
                        )
                    )

        return EvidenceDossier(crops=crops, total_evidences=len(crops))
