"""Data models for persisted inspection audit records."""

from pydantic import BaseModel, ConfigDict, Field


class InspectionRecord(BaseModel):
    """Immutable audit record representing a historical packaging screening run."""

    model_config = ConfigDict(frozen=True)

    inspection_id: str = Field(..., description="Unique inspection UUID identifier")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp of inspection")
    image_name: str = Field(..., description="Filename or descriptor of scanned packaging")
    verdict: str = Field(..., description="Three-state verdict string")
    critical_count: int = Field(..., description="Count of critical statutory violations", ge=0)
    major_count: int = Field(..., description="Count of major statutory infractions", ge=0)
    summary: str = Field(..., description="Compliance adjudication summary")
    is_sharp: bool = Field(..., description="Optical sharpness gate status")
    glare_ratio: float = Field(..., description="Specular glare proportion")
