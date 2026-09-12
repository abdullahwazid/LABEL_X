"""Data models for statutory inspection reports and compliance notices."""

from pydantic import BaseModel, ConfigDict, Field


class InspectionReport(BaseModel):
    """Immutable statutory screening notice and compliance report."""

    model_config = ConfigDict(frozen=True)

    inspection_id: str = Field(..., description="Unique inspection identifier")
    generated_at: str = Field(..., description="ISO-8601 UTC timestamp of report creation")
    report_text: str = Field(..., description="Formatted statutory text notice content")
    verdict: str = Field(..., description="Tri-state screening verdict string")
    total_violations: int = Field(default=0, description="Total number of violations detected", ge=0)
