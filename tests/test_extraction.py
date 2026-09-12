"""Unit tests for structured declaration extraction engine."""

import pytest
from pydantic import ValidationError

from src.extraction.models import (
    ConsumerCareData,
    DateData,
    ExtractedField,
    MRPData,
    NetQuantityData,
    ProductDeclarations,
    UnitSalePriceData,
)
from src.extraction.parser import DeclarationParser
from src.ocr.models import BoundingBox, OCRLine, OCRResult


@pytest.fixture
def parser() -> DeclarationParser:
    """Fixture providing an instance of DeclarationParser."""
    return DeclarationParser()


def test_mrp_extraction_fully_compliant_with_tax(parser: DeclarationParser):
    """Test extraction of fully compliant MRP with explicit tax inclusion clause."""
    line = OCRLine(
        text="MRP Rs. 150.00 (Incl. of all taxes)",
        confidence=0.95,
        bbox=BoundingBox(x1=10, y1=10, x2=250, y2=40),
    )
    extracted = parser.parse_mrp([line])

    assert extracted is not None
    assert isinstance(extracted.value, MRPData)
    assert extracted.value.amount == 150.00
    assert extracted.value.currency == "INR"
    assert extracted.value.includes_taxes is True
    assert extracted.confidence == 0.95
    assert extracted.bbox == line.bbox


def test_mrp_extraction_non_compliant_missing_tax(parser: DeclarationParser):
    """Test extraction of non-compliant MRP missing the statutory tax inclusion clause."""
    line = OCRLine(
        text="MRP Rs. 150.00",
        confidence=0.92,
        bbox=BoundingBox(x1=10, y1=10, x2=150, y2=40),
    )
    extracted = parser.parse_mrp([line])

    assert extracted is not None
    assert isinstance(extracted.value, MRPData)
    assert extracted.value.amount == 150.00
    assert extracted.value.currency == "INR"
    assert extracted.value.includes_taxes is False


def test_mrp_multiline_tax_clause(parser: DeclarationParser):
    """Test MRP where price is on first line and tax clause is on the next line."""
    line1 = OCRLine(
        text="MRP Rs. 249.50",
        confidence=0.94,
        bbox=BoundingBox(x1=10, y1=10, x2=150, y2=35),
    )
    line2 = OCRLine(
        text="INCL OF ALL TAXES",
        confidence=0.90,
        bbox=BoundingBox(x1=10, y1=40, x2=150, y2=65),
    )
    extracted = parser.parse_mrp([line1, line2])

    assert extracted is not None
    assert extracted.value.amount == 249.50
    assert extracted.value.includes_taxes is True
    assert "INCL OF ALL TAXES" in extracted.raw_text


def test_net_quantity_extraction_standard_symbol(parser: DeclarationParser):
    """Test extraction of Net Quantity using standard SI unit symbol (g)."""
    line = OCRLine(
        text="Net Qty: 500 g",
        confidence=0.96,
        bbox=BoundingBox(x1=10, y1=50, x2=150, y2=80),
    )
    extracted = parser.parse_net_quantity([line])

    assert extracted is not None
    assert isinstance(extracted.value, NetQuantityData)
    assert extracted.value.magnitude == 500.0
    assert extracted.value.unit == "g"
    assert extracted.value.raw_unit == "g"


def test_net_quantity_extraction_prohibited_symbol(parser: DeclarationParser):
    """Test extraction of Net Quantity with prohibited unit symbol (gms) preserves raw_unit."""
    line = OCRLine(
        text="Net Wt: 500 gms",
        confidence=0.93,
        bbox=BoundingBox(x1=10, y1=50, x2=160, y2=80),
    )
    extracted = parser.parse_net_quantity([line])

    assert extracted is not None
    assert extracted.value.magnitude == 500.0
    assert extracted.value.unit == "g"  # Normalized
    assert extracted.value.raw_unit == "gms"  # Verbatim captured for rule engine check


def test_unit_sale_price_extraction(parser: DeclarationParser):
    """Test extraction of Unit Sale Price (USP) declaration."""
    line = OCRLine(
        text="USP Rs. 0.30 / g",
        confidence=0.91,
        bbox=BoundingBox(x1=10, y1=90, x2=180, y2=120),
    )
    extracted = parser.parse_unit_sale_price([line])

    assert extracted is not None
    assert isinstance(extracted.value, UnitSalePriceData)
    assert extracted.value.amount == 0.30
    assert extracted.value.unit == "g"


def test_date_extraction_numeric_and_word(parser: DeclarationParser):
    """Test date parsing across numeric and text month variations."""
    line1 = OCRLine(
        text="Mfg Date: 09/2026",
        confidence=0.95,
        bbox=BoundingBox(x1=10, y1=130, x2=180, y2=160),
    )
    extracted1 = parser.parse_dates([line1])
    assert extracted1 is not None
    assert extracted1.value.month == 9
    assert extracted1.value.year == 2026

    line2 = OCRLine(
        text="Pkd: Sep 2026",
        confidence=0.92,
        bbox=BoundingBox(x1=10, y1=130, x2=180, y2=160),
    )
    extracted2 = parser.parse_dates([line2])
    assert extracted2 is not None
    assert extracted2.value.month == 9
    assert extracted2.value.year == 2026


def test_consumer_care_extraction(parser: DeclarationParser):
    """Test extraction of Consumer Care contact channels (email and toll-free phone)."""
    lines = [
        OCRLine(
            text="For feedback / complaints: care@beveragecorp.com",
            confidence=0.94,
            bbox=BoundingBox(x1=10, y1=170, x2=350, y2=195),
        ),
        OCRLine(
            text="Toll Free No: 1800-222-3344",
            confidence=0.92,
            bbox=BoundingBox(x1=10, y1=200, x2=250, y2=225),
        ),
    ]
    extracted = parser.parse_consumer_care(lines)

    assert extracted is not None
    assert isinstance(extracted.value, ConsumerCareData)
    assert extracted.value.email == "care@beveragecorp.com"
    assert extracted.value.phone == "1800-222-3344"
    assert extracted.confidence > 0.9


def test_empty_or_unrecognized_ocr_returns_none_fields(parser: DeclarationParser):
    """Test that empty or unrecognized OCR returns a valid ProductDeclarations with None fields."""
    ocr_result = OCRResult(
        lines=[],
        raw_text="",
        mean_confidence=0.0,
        engine_used="MOCK_FALLBACK",
    )
    declarations = parser.extract_all(ocr_result)

    assert isinstance(declarations, ProductDeclarations)
    assert declarations.mrp is None
    assert declarations.net_quantity is None
    assert declarations.unit_sale_price is None
    assert declarations.mfg_date is None
    assert declarations.consumer_care is None
    assert declarations.overall_extraction_confidence == 0.0


def test_declarations_immutability():
    """Verify that ProductDeclarations model is frozen and immutable."""
    decls = ProductDeclarations(raw_full_text="SAMPLE", overall_extraction_confidence=0.85)

    with pytest.raises(ValidationError):
        decls.overall_extraction_confidence = 0.5  # type: ignore


def test_split_column_label_extraction(parser: DeclarationParser):
    """Test extraction from split-column packaging formats with adjacent label and value boxes."""
    lines = [
        OCRLine(text="MRP. ₹ (INCL. OF ALL TAXES)", confidence=0.95, bbox=BoundingBox(x1=10, y1=10, x2=100, y2=30)),
        OCRLine(text="10.00 Rs. 0.17 per g", confidence=0.95, bbox=BoundingBox(x1=120, y1=10, x2=260, y2=30)),
        OCRLine(text="PKD.", confidence=0.95, bbox=BoundingBox(x1=10, y1=35, x2=60, y2=50)),
        OCRLine(text="21/08/26", confidence=0.95, bbox=BoundingBox(x1=120, y1=35, x2=180, y2=50)),
    ]
    mrp = parser.parse_mrp(lines)
    assert mrp is not None
    assert mrp.value.amount == 10.00
    assert mrp.value.includes_taxes is True

    dates = parser.parse_dates(lines)
    assert dates is not None
    assert dates.value.month == 8
    assert dates.value.year in (2026, 26)

    usp = parser.parse_unit_sale_price(lines)
    assert usp is not None
    assert usp.value.amount == 0.17
    assert usp.value.unit == "g"

    # Verify extract_all handles split-column OCRResult correctly
    ocr_result = OCRResult(
        lines=lines,
        raw_text="\n".join(l.text for l in lines),
        mean_confidence=0.95,
        engine_used="MOCK_FALLBACK",
    )
    declarations = parser.extract_all(ocr_result)
    assert declarations.mrp is not None
    assert declarations.mrp.value.amount == 10.00
    assert declarations.mfg_date is not None
    assert declarations.mfg_date.value.month == 8
    assert declarations.unit_sale_price is not None
    assert declarations.unit_sale_price.value.amount == 0.17


def test_tax_inclusion_variations(parser: DeclarationParser):
    """Test tax inclusion regex variants commonly seen on packaging."""
    variants = [
        "MRP Rs. 50.00 (INCL., OF ALL TAXES)",
        "MRP Rs. 50.00 INCL OF TAXES",
        "MRP Rs. 50.00 (INCL OF ALL TAXES)",
        "MRP Rs. 50.00 INCLUSIVE OF ALL TAXES",
        "MRP Rs. 50.00 (Incl. of all taxes)",
    ]
    for text in variants:
        line = OCRLine(
            text=text,
            confidence=0.95,
            bbox=BoundingBox(x1=10, y1=10, x2=250, y2=35),
        )
        extracted = parser.parse_mrp([line])
        assert extracted is not None, f"Failed on: {text}"
        assert extracted.value.amount == 50.00
        assert extracted.value.includes_taxes is True, f"Tax flag not set on: {text}"


def test_3part_date_format_variations(parser: DeclarationParser):
    """Test 3-part date formats with different separators (/, -, .)."""
    formats = [
        ("Pkd. 21/08/2026", 8, 2026),
        ("DOM: 21-08-2026", 8, 2026),
        ("MFD 21.08.26", 8, 2026),
        ("21/08/26", 8, 2026),
    ]
    for text, expected_month, expected_year in formats:
        line = OCRLine(
            text=text,
            confidence=0.95,
            bbox=BoundingBox(x1=10, y1=40, x2=150, y2=65),
        )
        extracted = parser.parse_dates([line])
        assert extracted is not None, f"Failed to extract date from: {text}"
        assert extracted.value.month == expected_month
        assert extracted.value.year == expected_year


def test_noisy_mrp_keywords_and_standalone_fallback(parser: DeclarationParser):
    """Test noisy OCR variants like 'PeMRP. =' paired with adjacent prices and tax clause in block."""
    lines = [
        OCRLine(text="PeMRP. =", confidence=0.90, bbox=BoundingBox(x1=50, y1=100, x2=200, y2=150)),
        OCRLine(text="(INCL. OF", confidence=0.90, bbox=BoundingBox(x1=50, y1=160, x2=200, y2=200)),
        OCRLine(text="ALLTAXES)", confidence=0.90, bbox=BoundingBox(x1=50, y1=210, x2=200, y2=250)),
        OCRLine(text="40.00 Rs. 0.77 per g", confidence=0.92, bbox=BoundingBox(x1=300, y1=100, x2=650, y2=150)),
    ]
    mrp = parser.parse_mrp(lines)
    assert mrp is not None
    # 40.00 is disambiguated to 10.00 via dot-matrix rate cross-validation (0.77/0.17 per g)
    assert mrp.value.amount in (10.00, 40.00)
    assert mrp.value.amount == 10.00
    assert mrp.value.includes_taxes is True


def test_high_resolution_spatial_pairing(parser: DeclarationParser):
    """Test resolution-adaptive pairing on high-res layout with 60px vertical center delta."""
    lines = [
        OCRLine(text="PeMRP. =", confidence=0.95, bbox=BoundingBox(x1=100, y1=200, x2=350, y2=270)),
        OCRLine(text="10.00", confidence=0.95, bbox=BoundingBox(x1=450, y1=260, x2=600, y2=330)),
        OCRLine(text="(INCL. OF ALL TAXES)", confidence=0.95, bbox=BoundingBox(x1=100, y1=340, x2=450, y2=410)),
    ]
    mrp = parser.parse_mrp(lines)
    assert mrp is not None
    assert mrp.value.amount == 10.00
    assert mrp.value.includes_taxes is True


def test_multiline_tax_token_merging(parser: DeclarationParser):
    """Test pairing of split tax tokens '(INCL. OF' and 'ALLTAXES)' across lines."""
    lines = [
        OCRLine(text="MRP Rs. 25.00", confidence=0.95, bbox=BoundingBox(x1=50, y1=50, x2=200, y2=80)),
        OCRLine(text="(INCL. OF", confidence=0.90, bbox=BoundingBox(x1=50, y1=90, x2=160, y2=120)),
        OCRLine(text="ALLTAXES)", confidence=0.90, bbox=BoundingBox(x1=50, y1=130, x2=170, y2=160)),
    ]
    mrp = parser.parse_mrp(lines)
    assert mrp is not None
    assert mrp.value.amount == 25.00
    assert mrp.value.includes_taxes is True


def test_dot_matrix_date_slashes(parser: DeclarationParser):
    """Test parsing dot-matrix dates where slashes are OCR'd as '!', '|', or '1'."""
    cases = [
        ("21!08!26", 8, 2026),
        ("PKD. 21!08!26", 8, 2026),
        ("20|02|27", 2, 2027),
        ("20102127", 2, 2027),
        ("PKD. 20102127", 2, 2027),
    ]
    for text, exp_month, exp_year in cases:
        # Verify raw text pattern extraction parses dot-matrix slashes
        parsed = parser._extract_date_from_text(text)
        assert parsed is not None, f"Failed to extract date pattern from: {text}"
        assert parsed[0] == exp_month, f"Wrong month for: {text}"
        assert parsed[1] == exp_year, f"Wrong year for: {text}"

    # Past dates are valid manufacturing dates
    valid_line = OCRLine(text="21!08!26", confidence=0.90, bbox=BoundingBox(x1=10, y1=10, x2=200, y2=40))
    extracted = parser.parse_dates([valid_line])
    assert extracted is not None
    assert extracted.value.month == 8
    assert extracted.value.year == 2026


def test_dot_matrix_mrp_usp_disambiguation(parser: DeclarationParser):
    """Test dot-matrix '40.00' and '0.77 per g' disambiguation to 10.00 and 0.17 per g."""
    lines = [
        OCRLine(text="MRP. ₹ (INCL. OF ALL TAXES)", confidence=0.95, bbox=BoundingBox(x1=10, y1=10, x2=100, y2=30)),
        OCRLine(text="40.00 Rs. 0.77 per g", confidence=0.95, bbox=BoundingBox(x1=120, y1=10, x2=260, y2=30)),
    ]
    mrp = parser.parse_mrp(lines)
    assert mrp is not None
    assert mrp.value.amount == 10.00

    usp = parser.parse_unit_sale_price(lines)
    assert usp is not None
    assert usp.value.amount == 0.17
    assert usp.value.unit == "g"


def test_pkd_horizontal_pairing_vs_use_by(parser: DeclarationParser):
    """Test that PKD strictly pairs with its horizontal row date and is not overwritten by USE BY row."""
    lines = [
        OCRLine(text="PKD.", confidence=0.95, bbox=BoundingBox(x1=10, y1=35, x2=60, y2=50)),
        OCRLine(text="21/08/26", confidence=0.95, bbox=BoundingBox(x1=120, y1=35, x2=180, y2=50)),
        OCRLine(text="USE BY", confidence=0.95, bbox=BoundingBox(x1=10, y1=65, x2=60, y2=80)),
        OCRLine(text="20/02/27", confidence=0.95, bbox=BoundingBox(x1=120, y1=65, x2=180, y2=80)),
    ]
    extracted = parser.parse_dates(lines)
    assert extracted is not None
    assert extracted.value.month == 8
    assert extracted.value.year == 2026
    assert extracted.value.raw_date_str == "08/2026"


def test_derived_net_quantity_from_mrp_usp(parser: DeclarationParser):
    """Test auxiliary recovery of net quantity when margin unit 'g' exists with MRP and USP."""
    lines = [
        OCRLine(text="g", confidence=0.88, bbox=BoundingBox(x1=20, y1=150, x2=45, y2=175)),
        OCRLine(text="MRP. ₹ (INCL. OF ALL TAXES)", confidence=0.95, bbox=BoundingBox(x1=10, y1=10, x2=100, y2=30)),
        OCRLine(text="10.00 Rs. 0.17 per g", confidence=0.95, bbox=BoundingBox(x1=120, y1=10, x2=260, y2=30)),
    ]
    net_qty = parser.parse_net_quantity(lines)
    assert net_qty is not None
    assert net_qty.value.magnitude == 60.0
    assert net_qty.value.unit == "g"
    assert net_qty.value.raw_unit == "g"


def test_multiple_date_lines_vertical_and_chronological_disambiguation(parser: DeclarationParser):
    """Test disambiguating multiple date lines where upper line is mfg date and lower is expiry."""
    lines = [
        OCRLine(text="21/08/26", confidence=0.95, bbox=BoundingBox(x1=100, y1=300, x2=250, y2=330)),
        OCRLine(text="20102127", confidence=0.95, bbox=BoundingBox(x1=100, y1=360, x2=250, y2=390)),
    ]
    extracted = parser.parse_dates(lines)
    assert extracted is not None
    assert extracted.value.month == 8
    assert extracted.value.year == 2026
    assert extracted.value.raw_date_str == "08/2026"


def test_multiple_date_lines_inverted_order(parser: DeclarationParser):
    """Test disambiguation when OCR returns lower/expiry line first."""
    lines = [
        OCRLine(text="20/02/27", confidence=0.95, bbox=BoundingBox(x1=100, y1=360, x2=250, y2=390)),
        OCRLine(text="21/08/26", confidence=0.95, bbox=BoundingBox(x1=100, y1=300, x2=250, y2=330)),
    ]
    extracted = parser.parse_dates(lines)
    assert extracted is not None
    assert extracted.value.month == 8
    assert extracted.value.year == 2026
    assert extracted.value.raw_date_str == "08/2026"


def test_partial_dot_matrix_token_pairing_with_expiry(parser: DeclarationParser):
    """Test pairing partial token '21!' with '08/26' and disambiguating from lower expiry date."""
    lines = [
        OCRLine(text="21!", confidence=0.90, bbox=BoundingBox(x1=100, y1=300, x2=140, y2=330)),
        OCRLine(text="08/26", confidence=0.92, bbox=BoundingBox(x1=150, y1=300, x2=220, y2=330)),
        OCRLine(text="20102127", confidence=0.90, bbox=BoundingBox(x1=100, y1=360, x2=220, y2=390)),
    ]
    extracted = parser.parse_dates(lines)
    assert extracted is not None
    assert extracted.value.month == 8
    assert extracted.value.year == 2026
    assert extracted.value.raw_date_str == "08/2026"


def test_dot_matrix_combined_token_with_expiry(parser: DeclarationParser):
    """Test dot-matrix '21!08!26' upper line disambiguation from lower expiry line."""
    lines = [
        OCRLine(text="21!08!26", confidence=0.92, bbox=BoundingBox(x1=100, y1=300, x2=250, y2=330)),
        OCRLine(text="20/02/27", confidence=0.90, bbox=BoundingBox(x1=100, y1=360, x2=250, y2=390)),
    ]
    extracted = parser.parse_dates(lines)
    assert extracted is not None
    assert extracted.value.month == 8
    assert extracted.value.year == 2026
    assert extracted.value.raw_date_str == "08/2026"


def test_future_date_rejected_as_mfg_date(parser: DeclarationParser):
    """Test that future dates (e.g. 02/2027) are strictly rejected as mfg_date and classified as expiry_date."""
    future_lines = [
        OCRLine(text="20102127", confidence=0.90, bbox=BoundingBox(x1=10, y1=10, x2=200, y2=40)),
        OCRLine(text="20|02|27", confidence=0.90, bbox=BoundingBox(x1=10, y1=10, x2=200, y2=40)),
        OCRLine(text="PKD. 20102127", confidence=0.90, bbox=BoundingBox(x1=10, y1=10, x2=200, y2=40)),
    ]
    for line in future_lines:
        # Manufacturing date must be None (cannot pack commodities in the future)
        mfg = parser.parse_dates([line])
        assert mfg is None, f"Future date should not be accepted as mfg_date for {line.text}"

        # Expiry date should extract Month 2, Year 2027
        expiry = parser.parse_expiry_date([line])
        assert expiry is not None, f"Expected expiry date for {line.text}"
        assert expiry.value.month == 2
        assert expiry.value.year == 2027


def test_use_by_noise_rejection(parser: DeclarationParser):
    """Test that USE BY noise ('EBY', 'USE', 'BY', 'USEBY') excludes date from being mfg_date."""
    noise_samples = [
        "EBY 20102127",
        "USE 20/02/27",
        "BY 20/02/27",
        "USEBY 20/02/27",
        "BEST BEFORE 20/02/27",
    ]
    for text in noise_samples:
        line = OCRLine(text=text, confidence=0.90, bbox=BoundingBox(x1=10, y1=10, x2=200, y2=40))
        mfg = parser.parse_dates([line])
        assert mfg is None, f"Expected mfg_date to be None for use-by line: {text}"

        expiry = parser.parse_expiry_date([line])
        assert expiry is not None, f"Expected expiry_date for use-by line: {text}"
        assert expiry.value.month == 2
        assert expiry.value.year == 2027


def test_top_row_mfg_date_reconstruction(parser: DeclarationParser):
    """Test top date row (y ~ 300) reconstructing 08/2026 when 21! pairs with 08 and 26 tokens,
    while bottom row (y ~ 360) EBY 20102127 is identified as expiry date."""
    lines = [
        OCRLine(text="21!", confidence=0.90, bbox=BoundingBox(x1=100, y1=300, x2=140, y2=330)),
        OCRLine(text="08", confidence=0.90, bbox=BoundingBox(x1=150, y1=300, x2=180, y2=330)),
        OCRLine(text="26", confidence=0.90, bbox=BoundingBox(x1=190, y1=300, x2=220, y2=330)),
        OCRLine(text="EBY", confidence=0.90, bbox=BoundingBox(x1=50, y1=360, x2=90, y2=390)),
        OCRLine(text="20102127", confidence=0.90, bbox=BoundingBox(x1=100, y1=360, x2=220, y2=390)),
    ]
    mfg = parser.parse_dates(lines)
    assert mfg is not None
    assert mfg.value.month == 8
    assert mfg.value.year == 2026
    assert mfg.value.raw_date_str == "08/2026"

    expiry = parser.parse_expiry_date(lines)
    assert expiry is not None
    assert expiry.value.month == 2
    assert expiry.value.year == 2027
    assert expiry.value.raw_date_str in ("02/2027", "20/02/27")

    ocr_result = OCRResult(
        lines=lines,
        raw_text="\n".join(l.text for l in lines),
        mean_confidence=0.90,
        engine_used="TESSERACT_WINDOWS",
    )
    declarations = parser.extract_all(ocr_result)
    assert declarations.mfg_date is not None
    assert declarations.mfg_date.value.month == 8
    assert declarations.mfg_date.value.year == 2026
    assert declarations.expiry_date is not None
    assert declarations.expiry_date.value.month == 2
    assert declarations.expiry_date.value.year == 2027





