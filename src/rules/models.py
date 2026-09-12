"""Data models for deterministic rule evaluation results and violations."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from src.regulatory.models import ViolationSeverity


class RuleStatus(str, Enum):
    """Execution status for deterministic statutory rule evaluations."""

    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RuleViolation(BaseModel):
    """Detailed record of a statutory rule violation."""

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(..., description="Statutory rule/provision identifier")
    rule_reference: str = Field(..., description="Legal citation reference")
    field: str = Field(..., description="Product declaration field associated with violation")
    message: str = Field(..., description="Human-readable explanation of the non-compliance")
    severity: ViolationSeverity = Field(..., description="Statutory violation severity")
    detected_value: Optional[str] = Field(default=None, description="Observed value extracted from package")
    expected_condition: str = Field(..., description="Statutory compliance condition required by law")


class RuleEvaluationResult(BaseModel):
    """Deterministic evaluation outcome for an individual statutory rule."""

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(..., description="Statutory rule/provision identifier")
    rule_reference: str = Field(..., description="Legal citation reference")
    status: RuleStatus = Field(..., description="Outcome of deterministic rule check")
    violation: Optional[RuleViolation] = Field(
        default=None, description="Violation details if status is FAIL"
    )
    reason: str = Field(..., description="Justification or evidence rationale for verdict")
