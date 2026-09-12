"""Pydantic data models for structured declaration extraction."""

from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

from src.ocr.models import BoundingBox

T = TypeVar("T")


class ExtractedField(BaseModel, Generic[T]):
    """Generic wrapper for an extracted regulatory field with visual and confidence metadata."""

    model_config = ConfigDict(frozen=True)

    value: T = Field(..., description="Parsed strongly-typed field value")
    raw_text: str = Field(..., description="Verbatim text snippet from which the field was extracted")
    confidence: float = Field(
        ..., description="Extraction confidence score from 0.0 to 1.0", ge=0.0, le=1.0
    )
    bbox: Optional[BoundingBox] = Field(
        default=None, description="Spatial bounding box corresponding to the declaration on the label"
    )


class MRPData(BaseModel):
    """Structured Maximum Retail Price declaration data."""

    model_config = ConfigDict(frozen=True)

    amount: float = Field(..., description="Declared numerical price amount", ge=0.0)
    currency: str = Field(default="INR", description="Currency code or symbol (default: INR)")
    includes_taxes: bool = Field(
        ..., description="True if 'inclusive of all taxes' or statutory equivalent is explicitly present"
    )


class NetQuantityData(BaseModel):
    """Structured Net Quantity declaration data."""

    model_config = ConfigDict(frozen=True)

    magnitude: float = Field(..., description="Numerical measure or count", ge=0.0)
    unit: str = Field(..., description="Normalized metric unit symbol (e.g. 'g', 'kg', 'ml', 'l', 'N')")
    raw_unit: str = Field(..., description="Verbatim unit string as recognized by OCR (e.g. 'gms', 'gm')")


class UnitSalePriceData(BaseModel):
    """Structured Unit Sale Price (USP) declaration data."""

    model_config = ConfigDict(frozen=True)

    amount: float = Field(..., description="Numerical price per unit", ge=0.0)
    unit: str = Field(..., description="Reference unit denominator (e.g. 'g', 'kg', 'ml', 'l', 'N')")


class DateData(BaseModel):
    """Structured manufacturing / packing / import date declaration data."""

    model_config = ConfigDict(frozen=True)

    month: Optional[int] = Field(default=None, description="Month of manufacture/packing (1 to 12)", ge=1, le=12)
    year: Optional[int] = Field(default=None, description="Full 4-digit Gregorian calendar year")
    raw_date_str: str = Field(..., description="Verbatim raw date string captured from label")


class ConsumerCareData(BaseModel):
    """Structured Consumer Care / Grievance contact details."""

    model_config = ConfigDict(frozen=True)

    email: Optional[str] = Field(default=None, description="Customer care email address")
    phone: Optional[str] = Field(default=None, description="Customer care toll-free or helpline telephone number")
    address: Optional[str] = Field(default=None, description="Physical postal address for consumer grievances")


class ProductDeclarations(BaseModel):
    """Comprehensive aggregation of all extracted regulatory product declarations."""

    model_config = ConfigDict(frozen=True)

    mrp: Optional[ExtractedField[MRPData]] = Field(
        default=None, description="Extracted Maximum Retail Price declaration"
    )
    net_quantity: Optional[ExtractedField[NetQuantityData]] = Field(
        default=None, description="Extracted Net Quantity declaration"
    )
    unit_sale_price: Optional[ExtractedField[UnitSalePriceData]] = Field(
        default=None, description="Extracted Unit Sale Price (USP) declaration"
    )
    mfg_date: Optional[ExtractedField[DateData]] = Field(
        default=None, description="Extracted Month and Year of Manufacture/Packing"
    )
    expiry_date: Optional[ExtractedField[DateData]] = Field(
        default=None, description="Extracted Expiration / Use By date"
    )
    consumer_care: Optional[ExtractedField[ConsumerCareData]] = Field(
        default=None, description="Extracted Consumer Care contact channels"
    )
    generic_name: Optional[ExtractedField[str]] = Field(
        default=None, description="Extracted common/generic name of the commodity"
    )
    raw_full_text: str = Field(
        default="", description="Full concatenated OCR text from the packaging image"
    )
    overall_extraction_confidence: float = Field(
        default=0.0,
        description="Aggregate extraction confidence score from 0.0 to 1.0",
        ge=0.0,
        le=1.0,
    )
