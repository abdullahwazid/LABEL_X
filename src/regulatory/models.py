"""Data models for statutory provisions and regulatory severity."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ViolationSeverity(str, Enum):
    """Enforcement severity levels for statutory packaging violations."""

    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    ADVISORY = "ADVISORY"


class RegulatoryProvision(BaseModel):
    """Statutory provision defining a codified packaging requirement."""

    model_config = ConfigDict(frozen=True)

    provision_id: str = Field(..., description="Unique statutory provision identifier")
    rule_reference: str = Field(..., description="Legal citation reference (e.g., Rule 6(1)(e))")
    title: str = Field(..., description="Human-readable title of the statutory requirement")
    requirement_text: str = Field(..., description="Detailed text of the legal requirement")
    statutory_act: str = Field(
        default="Legal Metrology Act, 2009", description="Governing legislative Act"
    )
    rules_name: str = Field(
        default="Legal Metrology (Packaged Commodities) Rules, 2011",
        description="Governing rules statutory instrument",
    )
    amendment_reference: Optional[str] = Field(
        default=None, description="Specific amendment gazette notification reference"
    )
    effective_date: str = Field(..., description="Effective date (YYYY-MM-DD)")
    severity: ViolationSeverity = Field(
        ..., description="Enforcement severity classification of non-compliance"
    )
    applicable_categories: list[str] = Field(
        default_factory=lambda: ["GENERAL_COMMODITY"],
        description="Product categories subject to this provision",
    )
