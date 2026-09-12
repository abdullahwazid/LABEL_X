"""Data models for three-state screening decisions and compliance arbitration."""

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class ScreeningVerdict(str, Enum):
    """Three-State Verdict for packaging regulatory screening."""

    NO_OBVIOUS_ISSUE = "NO_OBVIOUS_ISSUE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    POTENTIAL_NON_COMPLIANCE = "POTENTIAL_NON_COMPLIANCE"


class ScreeningDecision(BaseModel):
    """Comprehensive compliance screening verdict and evidentiary summary."""

    model_config = ConfigDict(frozen=True)

    verdict: ScreeningVerdict = Field(..., description="Top-level tri-state screening verdict")
    summary: str = Field(..., description="Executive compliance explanation or violation summary")
    critical_violations_count: int = Field(
        default=0, description="Number of critical statutory violations detected", ge=0
    )
    major_violations_count: int = Field(
        default=0, description="Number of major statutory infractions detected", ge=0
    )
    advisory_notes: list[str] = Field(
        default_factory=list, description="Advisory remarks or uncalibrated optical notes"
    )
    quality_warnings: list[str] = Field(
        default_factory=list, description="Image quality alerts and perceptual degradation warnings"
    )
    confidence_score: float = Field(
        ..., description="Overall algorithmic assessment confidence score from 0.0 to 1.0", ge=0.0, le=1.0
    )
