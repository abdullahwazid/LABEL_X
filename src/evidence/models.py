"""Data models for visual evidence crops and compliance dossiers."""

from pydantic import BaseModel, ConfigDict, Field

from src.ocr.models import BoundingBox


class VisualEvidenceCrop(BaseModel):
    """Cryptographically hashed visual evidence snippet for an individual rule finding."""

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(..., description="Associated statutory rule/provision identifier")
    rule_reference: str = Field(..., description="Legal citation reference (e.g. Rule 6(1)(e))")
    field_name: str = Field(..., description="Target declaration field name (e.g. 'mrp')")
    raw_text: str = Field(..., description="Verbatim text extracted from the cropped region")
    bbox: BoundingBox = Field(..., description="Spatial bounding box coordinates of the declaration")
    crop_bytes: bytes = Field(..., description="Binary PNG-encoded image crop of the declaration")
    sha256_hash: str = Field(
        ..., description="SHA-256 cryptographic digest of the image crop for audit integrity"
    )


class EvidenceDossier(BaseModel):
    """Immutable dossier collecting all visual evidence crops for an inspection session."""

    model_config = ConfigDict(frozen=True)

    crops: list[VisualEvidenceCrop] = Field(
        default_factory=list, description="List of cropped visual evidence items"
    )
    total_evidences: int = Field(
        default=0, description="Total count of visual evidence snippets compiled", ge=0
    )
