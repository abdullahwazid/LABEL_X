"""Gemini Multimodal perception service for legal metrology packaging extraction."""

from datetime import datetime
import os
from pathlib import Path
import re
from typing import Any, List, Optional, Union
import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from src.extraction.models import (
    ConsumerCareData,
    DateData,
    ExtractedField,
    MRPData,
    NetQuantityData,
    ProductDeclarations,
    UnitSalePriceData,
)
from src.ocr.models import BoundingBox, OCRLine, OCRResult


class PackagingDeclarationsSchema(BaseModel):
    """Pydantic schema for structured Gemini multimodal packaging label extraction."""

    model_config = ConfigDict(extra="ignore")

    mrp_amount: Optional[float] = Field(
        default=None, description="Numerical Maximum Retail Price amount in INR"
    )
    includes_all_taxes: bool = Field(
        default=False,
        description="True if 'inclusive of all taxes' or statutory equivalent is explicitly declared",
    )
    net_quantity_value: Optional[float] = Field(
        default=None, description="Net quantity magnitude or numerical count"
    )
    net_quantity_unit: Optional[str] = Field(
        default=None,
        description="Declared net quantity unit symbol (e.g. 'g', 'kg', 'ml', 'l', 'N')",
    )
    unit_sale_price_amount: Optional[float] = Field(
        default=None, description="Declared Unit Sale Price (USP) amount per unit"
    )
    unit_sale_price_unit: Optional[str] = Field(
        default=None,
        description="Declared Unit Sale Price unit denominator (e.g. 'g', 'kg', 'ml', 'l')",
    )
    mfg_or_pkd_date: Optional[str] = Field(
        default=None,
        description="Manufacturing or Packing Date string (e.g. DD/MM/YYYY, MM/YYYY, or DD-MM-YY)",
    )
    use_by_or_expiry_date: Optional[str] = Field(
        default=None,
        description="Use By or Expiry Date string (e.g. DD/MM/YYYY, MM/YYYY, or DD-MM-YY)",
    )
    consumer_care_details: Optional[str] = Field(
        default=None,
        description="Customer grievance/feedback contact details (email, phone, address)",
    )
    raw_transcript: str = Field(
        default="",
        description="Verbatim transcript of all visible text printed or stamped on the packaging",
    )


GEMINI_SYSTEM_INSTRUCTION = (
    "You are an expert Legal Metrology compliance perception engine. "
    "Accurately transcribe packaging labels even with faint dot-matrix inkjet stamping, "
    "reflective backgrounds, or split-panel layouts. "
    "Distinguish carefully between Manufacturing/Packing Date (PKD) and Expiry Date (USE BY). "
    "Never confuse USP (Rs per g) with Net Quantity."
)

UNIT_NORMALIZATION_MAP: dict[str, str] = {
    "g": "g",
    "gm": "g",
    "gms": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "ml",
    "mls": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "l": "l",
    "ltr": "l",
    "litre": "l",
    "litres": "l",
    "n": "N",
    "u": "N",
    "unit": "N",
    "units": "N",
    "piece": "N",
    "pcs": "N",
}

MONTH_NAME_MAP: dict[str, int] = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def load_gemini_api_key(env_path: Optional[str | Path] = None) -> Optional[str]:
    """Retrieves GEMINI_API_KEY from environment variables or .env file."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key and api_key.strip():
        return api_key.strip()

    search_paths = (
        [Path(env_path)]
        if env_path
        else [
            Path(".env"),
            Path(__file__).resolve().parent.parent.parent / ".env",
        ]
    )

    for p in search_paths:
        if p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k == "GEMINI_API_KEY" and v:
                                os.environ["GEMINI_API_KEY"] = v
                                return v
            except Exception:
                pass

    return None


class GeminiPerceptionService:
    """Multimodal perception service utilizing Google Gemini for packaging extraction."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-3.5-flash-lite",
        client: Optional[Any] = None,
    ) -> None:
        if api_key is None:
            self.api_key = load_gemini_api_key()
        else:
            self.api_key = api_key.strip() if api_key and api_key.strip() else None
        self.model_name = model_name
        self.active_model = model_name
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is not configured or available.")
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        """Returns True if a valid API key or client instance is available."""
        return bool(self._client is not None or self.api_key)

    def extract(
        self,
        images: Union[bytes, List[bytes], np.ndarray, List[np.ndarray]],
        mime_types: Union[str, List[str]] = "image/jpeg",
    ) -> tuple[ProductDeclarations, OCRResult]:
        """Extracts structured statutory declarations from packaging image(s) using Gemini.

        Supports multi-angle uploads so declarations across different faces/panels
        are synthesized into a unified compliance dossier.

        Args:
            images: Single image or list of images as raw binary bytes or BGR numpy arrays.
            mime_types: Single MIME type string or list of MIME types corresponding to images.

        Returns:
            Tuple of (ProductDeclarations, OCRResult).
        """
        raw_images: list[bytes | np.ndarray] = (
            list(images) if isinstance(images, (list, tuple)) else [images]
        )

        image_bytes_list: list[bytes] = []
        for img in raw_images:
            if isinstance(img, np.ndarray):
                success, encoded = cv2.imencode(".jpg", img)
                if not success:
                    success, encoded = cv2.imencode(".png", img)
                if not success:
                    raise ValueError("Failed to encode image array to image bytes.")
                image_bytes_list.append(encoded.tobytes())
            elif isinstance(img, (bytes, bytearray)):
                image_bytes_list.append(bytes(img))
            else:
                raise TypeError(f"Expected bytes or np.ndarray, got {type(img)}")

        if not image_bytes_list:
            raise ValueError("No images provided for extraction.")

        from google.genai import types

        image_parts = []
        for idx, img_bytes in enumerate(image_bytes_list):
            if isinstance(mime_types, (list, tuple)) and idx < len(mime_types):
                m_type = mime_types[idx]
            elif isinstance(mime_types, str):
                m_type = mime_types
            else:
                m_type = "image/png" if img_bytes.startswith(b"\x89PNG") else "image/jpeg"

            if m_type == "image/jpeg" and img_bytes.startswith(b"\x89PNG"):
                m_type = "image/png"

            image_parts.append(
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type=m_type,
                )
            )

        prompt = """Analyze all attached angles/faces of this packaged commodity. A declaration may appear on any side (e.g., Net Quantity on front, MRP and Mfg Date on back, Consumer Care on side/flap). Synthesize and extract the unified statutory declarations across all provided photos. Only mark a field missing if it cannot be found across ANY of the provided angles.
Return a single JSON object with these exact keys:
{
    "mrp": "<raw MRP string>",
    "usp": "<raw unit sale price string>",
    "mfg_date": "<manufacturing or packing date, e.g. 18-Mar-20 or 03/2020>",
    "expiry_date": "<expiry or best before date>",
    "consumer_care": "<extracted contact info: phone, email, or address>",
    "raw_text": "<all detected text>"
}"""

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        )

        candidate_models = [
            self.model_name,
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-2.5-flash",
            "gemini-flash-latest",
        ]
        # Deduplicate while preserving order
        candidate_models = list(dict.fromkeys(candidate_models))

        contents = [*image_parts, prompt]

        response = None
        last_exc: Optional[Exception] = None
        for model in candidate_models:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                self.active_model = model
                break
            except Exception as e:
                last_exc = e
                err_str = f"{type(e).__name__}: {e}".lower()
                status_code = getattr(e, "code", getattr(e, "status_code", None))
                is_quota_or_not_found = (
                    status_code in (404, 429, 500, 502, 503, 504)
                    or any(
                        code in err_str
                        for code in [
                            "429",
                            "resource_exhausted",
                            "quota",
                            "404",
                            "not_found",
                            "not found",
                            "503",
                            "unavailable",
                        ]
                    )
                )
                if is_quota_or_not_found:
                    print(f"[GEMINI FALLBACK] Model '{model}' failed ({e}). Trying next candidate...")
                    continue
                print(f"[CRITICAL GEMINI ERROR]: {type(e).__name__}: {e}")
                raise

        if response is None:
            if last_exc:
                raise last_exc
            raise RuntimeError("Gemini content generation failed across all candidate models.")

        data = self._parse_gemini_response(response)
        return self._map_dict_to_declarations_and_ocr(data)

    def _parse_gemini_response(self, response: Any) -> dict[str, Any]:
        """Extracts JSON dictionary from Gemini API response object."""
        if hasattr(response, "parsed") and isinstance(response.parsed, dict):
            return response.parsed

        if hasattr(response, "parsed") and isinstance(
            response.parsed, PackagingDeclarationsSchema
        ):
            p = response.parsed
            return {
                "mrp": (
                    f"Rs. {p.mrp_amount:.2f}"
                    + (" (INCL. OF ALL TAXES)" if p.includes_all_taxes else "")
                    if p.mrp_amount is not None
                    else ""
                ),
                "mrp_amount": p.mrp_amount,
                "includes_all_taxes": p.includes_all_taxes,
                "net_quantity_value": p.net_quantity_value,
                "net_quantity_unit": p.net_quantity_unit,
                "usp": (
                    f"Rs. {p.unit_sale_price_amount:.2f} / {p.unit_sale_price_unit}"
                    if p.unit_sale_price_amount is not None
                    else ""
                ),
                "unit_sale_price_amount": p.unit_sale_price_amount,
                "unit_sale_price_unit": p.unit_sale_price_unit,
                "mfg_date": p.mfg_or_pkd_date,
                "expiry_date": p.use_by_or_expiry_date,
                "consumer_care_details": p.consumer_care_details,
                "consumer_care": p.consumer_care_details,
                "raw_text": p.raw_transcript,
            }

        text = getattr(response, "text", "")
        if text:
            clean_json = text.strip()
            if clean_json.startswith("```"):
                lines = clean_json.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean_json = "\n".join(lines).strip()
            import json

            try:
                parsed_json = json.loads(clean_json)
                if isinstance(parsed_json, dict):
                    return parsed_json
            except Exception:
                pass
            return {"raw_text": text}

        return {}

    def _parse_date_string(self, date_str: str) -> Optional[tuple[int, int, str]]:
        """Extracts (month, year, formatted_str) from date representation string."""
        if not date_str:
            return None

        clean_str = date_str.strip()

        # 1. Try alphanumeric DD-Mon-YY or DD-Mon-YYYY (e.g. 18-Mar-20, 18-Mar-2020, 18/Mar/20, 18 Mar 20)
        m_alpha_3p = re.search(
            r"\b(\d{1,2})[\/\-.\s]+([A-Za-z]{3,9})[\/\-.\s]+(\d{2,4})\b", clean_str
        )
        if m_alpha_3p:
            mon_key = m_alpha_3p.group(2).lower()
            if mon_key in MONTH_NAME_MAP:
                m = MONTH_NAME_MAP[mon_key]
                y = int(m_alpha_3p.group(3))
                if y < 100:
                    y += 2000
                return m, y, f"{m:02d}/{y}"

        # 2. Try alphanumeric Mon-DD-YYYY or Mon-DD-YY (e.g. Mar-18-20, Mar 18, 2020)
        m_alpha_m_d_y = re.search(
            r"\b([A-Za-z]{3,9})[\/\-.\s]+(\d{1,2})[\/\-.,\s]+(\d{2,4})\b", clean_str
        )
        if m_alpha_m_d_y:
            mon_key = m_alpha_m_d_y.group(1).lower()
            if mon_key in MONTH_NAME_MAP:
                m = MONTH_NAME_MAP[mon_key]
                y = int(m_alpha_m_d_y.group(3))
                if y < 100:
                    y += 2000
                return m, y, f"{m:02d}/{y}"

        # 3. Try alphanumeric Mon-YY or Mon-YYYY (e.g. Mar-20, Mar 2020, March 2020)
        m_alpha_2p = re.search(
            r"\b([A-Za-z]{3,9})[\/\-.\s]+(\d{2,4})\b", clean_str
        )
        if m_alpha_2p:
            mon_key = m_alpha_2p.group(1).lower()
            if mon_key in MONTH_NAME_MAP:
                m = MONTH_NAME_MAP[mon_key]
                y = int(m_alpha_2p.group(2))
                if y < 100:
                    y += 2000
                return m, y, f"{m:02d}/{y}"

        # 4. Try ISO YYYY-MM-DD
        m_iso = re.search(r"\b(20\d{2})[\/\-.](\d{1,2})[\/\-.](\d{1,2})\b", clean_str)
        if m_iso:
            y = int(m_iso.group(1))
            m = int(m_iso.group(2))
            if 1 <= m <= 12:
                return m, y, f"{m:02d}/{y}"

        # 5. Try numeric 3-part DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
        m_3part = re.search(r"\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\b", clean_str)
        if m_3part:
            d1 = int(m_3part.group(1))
            d2 = int(m_3part.group(2))
            y = int(m_3part.group(3))
            if y < 100:
                y += 2000
            # Disambiguate DD/MM vs MM/DD: Indian packaging standard is DD/MM/YYYY
            if d2 > 12 and 1 <= d1 <= 12:
                m = d1
            else:
                m = d2
            if 1 <= m <= 12:
                return m, y, f"{m:02d}/{y}"

        # 6. Try numeric 2-part MM/YYYY or MM-YYYY or MM/YY
        m_2part = re.search(r"\b(0[1-9]|1[0-2])[\/\-.](20\d{2}|\d{2})\b", clean_str)
        if m_2part:
            m = int(m_2part.group(1))
            y = int(m_2part.group(2))
            if y < 100:
                y += 2000
            return m, y, f"{m:02d}/{y}"

        # 7. Fallback: datetime.strptime attempts
        for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d/%b/%y", "%d/%b/%Y", "%b-%y", "%b-%Y", "%B %Y"):
            try:
                dt = datetime.strptime(clean_str, fmt)
                return dt.month, dt.year, f"{dt.month:02d}/{dt.year}"
            except Exception:
                pass

        return None

    def _parse_consumer_care_string(
        self, details: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Parses email and phone from consumer care string."""
        if not details:
            return None, None

        email_match = re.search(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", details
        )
        phone_match = re.search(
            r"\b(?:1800[- ]?\d{3,4}[- ]?\d{3,4}|(?:\+91[\-\s]?)?[6-9]\d{9}|0\d{2,4}\s*[-–]\s*\d+|0\d{2,4}\s*[-–]\s*|0\d{2,4}[-\s]?\d{4,8})",
            details,
        )

        email = email_match.group(0).strip() if email_match else None
        phone = phone_match.group(0).strip() if phone_match else None
        return email, phone

    def _map_schema_to_declarations_and_ocr(
        self, schema: Any
    ) -> tuple[ProductDeclarations, OCRResult]:
        """Backward compatibility wrapper for _map_dict_to_declarations_and_ocr."""
        if isinstance(schema, PackagingDeclarationsSchema):
            data = {
                "mrp_amount": schema.mrp_amount,
                "includes_all_taxes": schema.includes_all_taxes,
                "net_quantity_value": schema.net_quantity_value,
                "net_quantity_unit": schema.net_quantity_unit,
                "unit_sale_price_amount": schema.unit_sale_price_amount,
                "unit_sale_price_unit": schema.unit_sale_price_unit,
                "mfg_date": schema.mfg_or_pkd_date,
                "expiry_date": schema.use_by_or_expiry_date,
                "consumer_care_details": schema.consumer_care_details,
                "raw_text": schema.raw_transcript,
            }
            return self._map_dict_to_declarations_and_ocr(data)
        elif isinstance(schema, dict):
            return self._map_dict_to_declarations_and_ocr(schema)
        raise TypeError(f"Unexpected schema type: {type(schema)}")

    def _map_dict_to_declarations_and_ocr(
        self, data: dict[str, Any]
    ) -> tuple[ProductDeclarations, OCRResult]:
        """Maps structured dictionary into immutable ProductDeclarations and OCRResult."""
        raw_text = str(data.get("raw_text") or data.get("raw_transcript") or "").strip()
        lines: list[OCRLine] = []
        raw_lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        for l_text in raw_lines:
            lines.append(
                OCRLine(
                    text=l_text,
                    confidence=0.98,
                    bbox=BoundingBox(x1=0, y1=0, x2=0, y2=0),
                )
            )

        ocr_result = OCRResult(
            lines=lines,
            raw_text=raw_text,
            mean_confidence=0.98 if lines else 0.0,
            engine_used="GEMINI_MULTIMODAL",
        )

        mrp_field: Optional[ExtractedField[MRPData]] = None
        mrp_amount_val = data.get("mrp_amount")
        mrp_val = data.get("mrp")

        # Check taxes across mrp_val, data["includes_all_taxes"], and raw_text
        tax_patterns = [
            r"(?i)\bincl\b",
            r"(?i)incl\.",
            r"(?i)inclusive",
            r"(?i)of\s+all\s+taxes",
            r"(?i)all\s+taxes",
        ]
        has_tax_indication = (
            bool(data.get("includes_all_taxes"))
            or any(re.search(p, str(mrp_val or "")) for p in tax_patterns)
            or any(re.search(p, raw_text) for p in tax_patterns)
        )

        if mrp_amount_val is not None:
            mrp_field = ExtractedField(
                value=MRPData(
                    amount=float(mrp_amount_val),
                    currency="INR",
                    includes_taxes=has_tax_indication,
                ),
                raw_text=str(mrp_val or f"MRP Rs. {mrp_amount_val:.2f}"),
                confidence=0.98,
                bbox=None,
            )
        elif mrp_val and str(mrp_val).strip():
            mrp_str = str(mrp_val).strip()
            clean_mrp = mrp_str.replace(",", "")
            amt_match = re.search(r"(\d+(?:\.\d{1,2})?)", clean_mrp)
            if amt_match:
                amount = float(amt_match.group(1))
                mrp_field = ExtractedField(
                    value=MRPData(
                        amount=amount, currency="INR", includes_taxes=has_tax_indication
                    ),
                    raw_text=mrp_str,
                    confidence=0.98,
                    bbox=None,
                )

        if mrp_field is None and lines:
            from src.extraction.parser import DeclarationParser

            mrp_field = DeclarationParser().parse_mrp(lines)
            if mrp_field and not mrp_field.value.includes_taxes and has_tax_indication:
                mrp_field = ExtractedField(
                    value=MRPData(
                        amount=mrp_field.value.amount,
                        currency=mrp_field.value.currency,
                        includes_taxes=True,
                    ),
                    raw_text=mrp_field.raw_text,
                    confidence=mrp_field.confidence,
                    bbox=mrp_field.bbox,
                )

        net_qty_field: Optional[ExtractedField[NetQuantityData]] = None
        net_qty_val = data.get("net_quantity_value")
        if net_qty_val is not None:
            raw_unit = str(data.get("net_quantity_unit", "g")).strip()
            norm_unit = UNIT_NORMALIZATION_MAP.get(raw_unit.lower(), raw_unit)
            net_qty_field = ExtractedField(
                value=NetQuantityData(
                    magnitude=float(net_qty_val),
                    unit=norm_unit,
                    raw_unit=raw_unit,
                ),
                raw_text=f"Net Qty: {net_qty_val} {raw_unit}",
                confidence=0.98,
                bbox=None,
            )
        elif data.get("net_quantity"):
            nq_str = str(data.get("net_quantity")).strip()
            m = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)", nq_str)
            if m:
                mag = float(m.group(1))
                raw_u = m.group(2)
                norm_u = UNIT_NORMALIZATION_MAP.get(raw_u.lower(), raw_u)
                net_qty_field = ExtractedField(
                    value=NetQuantityData(magnitude=mag, unit=norm_u, raw_unit=raw_u),
                    raw_text=nq_str,
                    confidence=0.98,
                    bbox=None,
                )
        if net_qty_field is None and lines:
            from src.extraction.parser import DeclarationParser

            net_qty_field = DeclarationParser().parse_net_quantity(lines, mrp=mrp_field)

        usp_field: Optional[ExtractedField[UnitSalePriceData]] = None
        usp_amount_val = data.get("unit_sale_price_amount")
        usp_val = data.get("usp")
        if usp_amount_val is not None:
            raw_usp_unit = str(data.get("unit_sale_price_unit", "g")).strip()
            norm_usp_unit = UNIT_NORMALIZATION_MAP.get(raw_usp_unit.lower(), raw_usp_unit)
            usp_field = ExtractedField(
                value=UnitSalePriceData(
                    amount=float(usp_amount_val),
                    unit=norm_usp_unit,
                ),
                raw_text=str(usp_val or f"Rs. {usp_amount_val:.2f} per {raw_usp_unit}"),
                confidence=0.98,
                bbox=None,
            )
        elif usp_val and str(usp_val).strip():
            usp_str = str(usp_val).strip()
            clean_usp = usp_str.replace(",", "")
            amt_match = re.search(r"(\d+(?:\.\d{1,4})?)", clean_usp)
            if amt_match:
                amount = float(amt_match.group(1))
                u_match = re.search(
                    r"(?:/|per|\b)(g|gm|gms|gram|grams|kg|kgs|kilogram|ml|mls|l|ltr|litre|n|u|unit|piece)\b",
                    usp_str,
                    re.IGNORECASE,
                )
                raw_usp_unit = u_match.group(1) if u_match else "g"
                norm_usp_unit = UNIT_NORMALIZATION_MAP.get(raw_usp_unit.lower(), raw_usp_unit)
                usp_field = ExtractedField(
                    value=UnitSalePriceData(amount=amount, unit=norm_usp_unit),
                    raw_text=usp_str,
                    confidence=0.98,
                    bbox=None,
                )

        mfg_field: Optional[ExtractedField[DateData]] = None
        mfg_val = data.get("mfg_date") or data.get("mfg_or_pkd_date")
        if mfg_val and str(mfg_val).strip():
            mfg_str = str(mfg_val).strip()
            mfg_parsed = self._parse_date_string(mfg_str)
            if mfg_parsed:
                m, y, fmt_str = mfg_parsed
                mfg_field = ExtractedField(
                    value=DateData(month=m, year=y, raw_date_str=fmt_str),
                    raw_text=mfg_str,
                    confidence=0.98,
                    bbox=None,
                )

        if mfg_field is None:
            # Fallback to date parsing from raw_text or DeclarationParser
            if raw_text:
                mfg_parsed = self._parse_date_string(raw_text)
                if mfg_parsed:
                    m, y, fmt_str = mfg_parsed
                    mfg_field = ExtractedField(
                        value=DateData(month=m, year=y, raw_date_str=fmt_str),
                        raw_text=fmt_str,
                        confidence=0.98,
                        bbox=None,
                    )
            if mfg_field is None and lines:
                from src.extraction.parser import DeclarationParser

                mfg_field = DeclarationParser().parse_dates(lines)

        expiry_field: Optional[ExtractedField[DateData]] = None
        exp_val = data.get("expiry_date") or data.get("use_by_or_expiry_date")
        if exp_val and str(exp_val).strip():
            exp_str = str(exp_val).strip()
            exp_parsed = self._parse_date_string(exp_str)
            if exp_parsed:
                m, y, fmt_str = exp_parsed
                expiry_field = ExtractedField(
                    value=DateData(month=m, year=y, raw_date_str=fmt_str),
                    raw_text=exp_str,
                    confidence=0.98,
                    bbox=None,
                )

        consumer_care_field: Optional[ExtractedField[ConsumerCareData]] = None
        care_val = data.get("consumer_care") or data.get("consumer_care_details")
        if care_val and str(care_val).strip():
            care_str = str(care_val).strip()
            email, phone = self._parse_consumer_care_string(care_str)
            # If phone or email not found or incomplete in care_str, inspect raw_text
            if (not phone or phone.endswith("-")) and raw_text:
                _, raw_phone = self._parse_consumer_care_string(raw_text)
                if raw_phone and not raw_phone.endswith("-"):
                    phone = raw_phone
                elif not phone and raw_phone:
                    phone = raw_phone
            if not email and raw_text:
                raw_email, _ = self._parse_consumer_care_string(raw_text)
                if raw_email:
                    email = raw_email

            consumer_care_field = ExtractedField(
                value=ConsumerCareData(
                    email=email,
                    phone=phone,
                    address=care_str,
                ),
                raw_text=care_str,
                confidence=0.98,
                bbox=None,
            )
        elif lines:
            from src.extraction.parser import DeclarationParser

            consumer_care_field = DeclarationParser().parse_consumer_care(lines)

        populated_fields = [
            f
            for f in [
                mrp_field,
                net_qty_field,
                usp_field,
                mfg_field,
                expiry_field,
                consumer_care_field,
            ]
            if f is not None
        ]
        overall_conf = (
            round(
                sum(f.confidence for f in populated_fields) / len(populated_fields), 3
            )
            if populated_fields
            else 0.0
        )

        declarations = ProductDeclarations(
            mrp=mrp_field,
            net_quantity=net_qty_field,
            unit_sale_price=usp_field,
            mfg_date=mfg_field,
            expiry_date=expiry_field,
            consumer_care=consumer_care_field,
            generic_name=None,
            raw_full_text=raw_text,
            overall_extraction_confidence=overall_conf,
        )

        return declarations, ocr_result
