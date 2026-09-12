"""Pydantic data models for optical character recognition and spatial bounding boxes."""

from pydantic import BaseModel, ConfigDict, Field


class BoundingBox(BaseModel):
    """Spatial bounding box coordinates for a recognized text region.
    
    Coordinates represent pixel positions (x1, y1) as top-left
    and (x2, y2) as bottom-right.
    """

    model_config = ConfigDict(frozen=True)

    x1: int = Field(..., description="Top-left x pixel coordinate", ge=0)
    y1: int = Field(..., description="Top-left y pixel coordinate", ge=0)
    x2: int = Field(..., description="Bottom-right x pixel coordinate", ge=0)
    y2: int = Field(..., description="Bottom-right y pixel coordinate", ge=0)

    def area(self) -> int:
        """Returns the bounding box surface area in pixels."""
        return max(0, self.x2 - self.x1) * max(0, self.y2 - self.y1)

    def aspect_ratio(self) -> float:
        """Returns the width-to-height aspect ratio (width / height)."""
        width = max(0, self.x2 - self.x1)
        height = max(1, self.y2 - self.y1)
        return float(width / height)


class OCRLine(BaseModel):
    """A single recognized line of text with spatial location and confidence."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(..., description="Recognized line text content")
    confidence: float = Field(
        ..., description="Normalized recognition confidence score from 0.0 to 1.0", ge=0.0, le=1.0
    )
    bbox: BoundingBox = Field(..., description="Spatial bounding box enclosing the line")


class OCRResult(BaseModel):
    """Aggregated OCR output containing all recognized lines, full raw text, and metrics."""

    model_config = ConfigDict(frozen=True)

    lines: list[OCRLine] = Field(
        default_factory=list, description="Ordered list of recognized text lines"
    )
    raw_text: str = Field(
        default="", description="Full concatenated text with newline separators"
    )
    mean_confidence: float = Field(
        default=0.0,
        description="Mean confidence across all recognized tokens/lines (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    engine_used: str = Field(
        ..., description="Identifier of the OCR engine used ('PYTESSERACT' or 'MOCK_FALLBACK')"
    )
