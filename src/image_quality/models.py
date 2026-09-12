"""Pydantic data models for image quality assessment and gating."""

from pydantic import BaseModel, ConfigDict, Field


class ImageQualityMetrics(BaseModel):
    """Evaluation metrics for uploaded package label image quality.
    
    This model is immutable (frozen) to serve as a reliable, tamper-evident
    quality gate contract between ingestion and downstream OCR perception.
    """

    model_config = ConfigDict(frozen=True)

    width: int = Field(..., description="Image width in pixels", ge=1)
    height: int = Field(..., description="Image height in pixels", ge=1)
    laplacian_variance: float = Field(
        ..., description="Variance of the Laplacian operator; metric for image sharpness"
    )
    glare_ratio: float = Field(
        ..., description="Proportion of pixels with luminance >= 250 (range 0.0 to 1.0)", ge=0.0, le=1.0
    )
    is_sharp: bool = Field(
        ..., description="True if laplacian_variance >= 80.0, indicating sufficient focus"
    )
    has_acceptable_glare: bool = Field(
        ..., description="True if glare_ratio <= 0.05, indicating specular glare is within bounds"
    )
    is_acceptable_for_screening: bool = Field(
        ..., description="True if both is_sharp and has_acceptable_glare are satisfied"
    )
    quality_warnings: list[str] = Field(
        default_factory=list, description="Actionable, human-readable quality degradation notices"
    )
