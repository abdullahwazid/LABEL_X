"""Unit tests for Gemini Multimodal extraction service, schema mapping, and pipeline integration."""

import os
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import pytest

from src.decisions.models import ScreeningVerdict
from src.extraction.models import ProductDeclarations
from src.ocr.gemini_extractor import (
    GEMINI_SYSTEM_INSTRUCTION,
    GeminiPerceptionService,
    PackagingDeclarationsSchema,
    load_gemini_api_key,
)
from src.ocr.models import OCRResult
from src.pipeline import CompliancePipeline, PipelineResult
from src.rules.engine import LegalMetrologyRuleEngine
from src.rules.models import RuleStatus


@pytest.fixture
def sample_image_bytes() -> bytes:
    """Generates a small valid test PNG image."""
    img = np.full((100, 100, 3), 200, dtype=np.uint8)
    cv2.putText(img, "TEST", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    success, encoded = cv2.imencode(".png", img)
    assert success
    return encoded.tobytes()


@pytest.fixture
def mock_schema_payload() -> PackagingDeclarationsSchema:
    """Sample structured packaging declarations extracted by Gemini."""
    return PackagingDeclarationsSchema(
        mrp_amount=10.00,
        includes_all_taxes=True,
        net_quantity_value=60.0,
        net_quantity_unit="g",
        unit_sale_price_amount=0.17,
        unit_sale_price_unit="g",
        mfg_or_pkd_date="21/08/2026",
        use_by_or_expiry_date="20/02/2027",
        consumer_care_details="Feedback: care@brand.in Toll Free: 1800-123-4567 Address: Mumbai, India",
        raw_transcript=(
            "BRAND BOURBON BISCUITS\n"
            "MRP Rs. 10.00 (INCL. OF ALL TAXES)\n"
            "Net Qty: 60 g\n"
            "USP: Rs. 0.17 per g\n"
            "PKD. 21/08/2026\n"
            "USE BY 20/02/2027\n"
            "Consumer Care: care@brand.in 1800-123-4567"
        ),
    )


def test_packaging_declarations_schema_serialization(mock_schema_payload: PackagingDeclarationsSchema):
    """Test PackagingDeclarationsSchema validation and JSON serialization."""
    json_str = mock_schema_payload.model_dump_json()
    reconstructed = PackagingDeclarationsSchema.model_validate_json(json_str)

    assert reconstructed.mrp_amount == 10.00
    assert reconstructed.includes_all_taxes is True
    assert reconstructed.net_quantity_value == 60.0
    assert reconstructed.net_quantity_unit == "g"
    assert reconstructed.unit_sale_price_amount == 0.17
    assert reconstructed.unit_sale_price_unit == "g"
    assert reconstructed.mfg_or_pkd_date == "21/08/2026"
    assert reconstructed.use_by_or_expiry_date == "20/02/2027"
    assert "care@brand.in" in reconstructed.consumer_care_details
    assert "BRAND BOURBON" in reconstructed.raw_transcript


def test_load_gemini_api_key_from_env():
    """Test loading GEMINI_API_KEY from environment variables."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test_api_key_12345"}):
        key = load_gemini_api_key()
        assert key == "test_api_key_12345"


def test_load_gemini_api_key_from_dotenv(tmp_path):
    """Test loading GEMINI_API_KEY from a .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=test_key_from_dotenv_999\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=True):
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        key = load_gemini_api_key(env_path=env_file)
        assert key == "test_key_from_dotenv_999"


def test_gemini_service_availability_and_initialization():
    """Test GeminiPerceptionService availability checks."""
    service_no_key = GeminiPerceptionService(api_key="")
    assert not service_no_key.is_available()

    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
        _ = service_no_key.client

    service_with_key = GeminiPerceptionService(api_key="mock_key")
    assert service_with_key.is_available()


def test_gemini_perception_service_extract_mapping(
    sample_image_bytes: bytes, mock_schema_payload: PackagingDeclarationsSchema
):
    """Test GeminiPerceptionService mapping from Gemini response to ProductDeclarations & OCRResult."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = mock_schema_payload
    mock_client.models.generate_content.return_value = mock_response

    service = GeminiPerceptionService(api_key="dummy_key", client=mock_client)
    decls, ocr_res = service.extract(sample_image_bytes)

    # Verify Gemini API call arguments
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].response_mime_type == "application/json"
    assert call_kwargs["config"].temperature == 0.0
    assert getattr(call_kwargs["config"], "response_schema", None) is None

    # Verify ProductDeclarations mapping
    assert isinstance(decls, ProductDeclarations)
    assert decls.mrp is not None
    assert decls.mrp.value.amount == 10.00
    assert decls.mrp.value.includes_taxes is True
    assert decls.mrp.confidence == 0.98

    assert decls.net_quantity is not None
    assert decls.net_quantity.value.magnitude == 60.0
    assert decls.net_quantity.value.unit == "g"
    assert decls.net_quantity.value.raw_unit == "g"

    assert decls.unit_sale_price is not None
    assert decls.unit_sale_price.value.amount == 0.17
    assert decls.unit_sale_price.value.unit == "g"

    assert decls.mfg_date is not None
    assert decls.mfg_date.value.month == 8
    assert decls.mfg_date.value.year == 2026
    assert decls.mfg_date.value.raw_date_str == "08/2026"

    assert decls.expiry_date is not None
    assert decls.expiry_date.value.month == 2
    assert decls.expiry_date.value.year == 2027
    assert decls.expiry_date.value.raw_date_str == "02/2027"

    assert decls.consumer_care is not None
    assert decls.consumer_care.value.email == "care@brand.in"
    assert decls.consumer_care.value.phone == "1800-123-4567"

    assert decls.overall_extraction_confidence == 0.98

    # Verify OCRResult mapping
    assert isinstance(ocr_res, OCRResult)
    assert ocr_res.engine_used == "GEMINI_MULTIMODAL"
    assert ocr_res.mean_confidence == 0.98
    assert len(ocr_res.lines) == 7
    assert ocr_res.lines[0].text == "BRAND BOURBON BISCUITS"


def test_gemini_declarations_feed_rule_engine(mock_schema_payload: PackagingDeclarationsSchema):
    """Test that declarations mapped from Gemini cleanly evaluate in LegalMetrologyRuleEngine."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = mock_schema_payload
    mock_client.models.generate_content.return_value = mock_response

    service = GeminiPerceptionService(api_key="dummy_key", client=mock_client)
    decls, _ = service.extract(np.zeros((50, 50, 3), dtype=np.uint8))

    engine = LegalMetrologyRuleEngine()
    results = engine.evaluate(decls, is_quality_acceptable=True)

    # Verify key rules pass without violation
    mrp_res = next(r for r in results if r.rule_id == "LMPC_R06_1_E")
    assert mrp_res.status == RuleStatus.PASS

    units_res = next(r for r in results if r.rule_id == "LMPC_R13")
    assert units_res.status == RuleStatus.PASS

    usp_res = next(r for r in results if r.rule_id == "LMPC_R06_11")
    assert usp_res.status == RuleStatus.PASS

    date_res = next(r for r in results if r.rule_id == "LMPC_R06_1_D")
    assert date_res.status == RuleStatus.PASS


def test_pipeline_integration_with_gemini_service(
    sample_image_bytes: bytes, mock_schema_payload: PackagingDeclarationsSchema
):
    """Test full CompliancePipeline execution using GeminiPerceptionService."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = mock_schema_payload
    mock_client.models.generate_content.return_value = mock_response

    service = GeminiPerceptionService(api_key="dummy_key", client=mock_client)
    pipeline = CompliancePipeline(gemini_service=service)

    result = pipeline.process_package(sample_image_bytes)

    assert isinstance(result, PipelineResult)
    assert result.ocr_result.engine_used == "GEMINI_MULTIMODAL"
    assert result.declarations.mrp is not None
    assert result.declarations.mrp.value.amount == 10.00
    assert result.decision.verdict == ScreeningVerdict.NO_OBVIOUS_ISSUE
    assert result.gemini_error is None
    assert pipeline.last_gemini_error is None


def test_pipeline_fallback_to_local_ocr_on_gemini_error(sample_image_bytes: bytes):
    """Test that CompliancePipeline gracefully falls back to local OCR if Gemini raises an exception."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API Quota Exceeded (429)")

    failing_service = GeminiPerceptionService(api_key="dummy_key", client=mock_client)
    pipeline = CompliancePipeline(gemini_service=failing_service)

    # Process image - should NOT raise exception, must seamlessly fall back to local OCR
    result = pipeline.process_package(sample_image_bytes)

    assert isinstance(result, PipelineResult)
    # Engine should be local Tesseract or mock fallback, NOT gemini
    assert result.ocr_result.engine_used != "GEMINI_MULTIMODAL"
    assert result.gemini_error is not None
    assert pipeline.last_gemini_error is not None
    assert "API Quota Exceeded (429)" in pipeline.last_gemini_error


def test_gemini_perception_service_extract_standard_json(sample_image_bytes: bytes):
    """Test GeminiPerceptionService extraction from standard JSON string response without schema."""
    json_text = """
    {
        "mrp": "Rs. 10.00 (Incl. of all taxes)",
        "usp": "Rs. 0.17 / g",
        "mfg_date": "21/08/26",
        "expiry_date": "20/02/27",
        "consumer_care": "care@brand.in 1800-123-4567",
        "raw_text": "BRAND BOURBON BISCUITS\\nMRP Rs. 10.00 (INCL. OF ALL TAXES)\\nNet Qty: 60 g\\nUSP: Rs. 0.17 per g\\nPKD. 21/08/26\\nUSE BY 20/02/27\\nConsumer Care: care@brand.in 1800-123-4567"
    }
    """
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json_text
    del mock_response.parsed  # Ensure it falls back to text JSON parsing
    mock_client.models.generate_content.return_value = mock_response

    service = GeminiPerceptionService(api_key="dummy_key", client=mock_client)
    decls, ocr_res = service.extract(sample_image_bytes)

    assert decls.mrp is not None
    assert decls.mrp.value.amount == 10.00
    assert decls.mrp.value.includes_taxes is True

    assert decls.unit_sale_price is not None
    assert decls.unit_sale_price.value.amount == 0.17
    assert decls.unit_sale_price.value.unit == "g"

    assert decls.mfg_date is not None
    assert decls.mfg_date.value.month == 8
    assert decls.mfg_date.value.year == 2026

    assert decls.expiry_date is not None
    assert decls.expiry_date.value.month == 2
    assert decls.expiry_date.value.year == 2027

    # Net quantity parsed from raw_text
    assert decls.net_quantity is not None
    assert decls.net_quantity.value.magnitude == 60.0
    assert decls.net_quantity.value.unit == "g"

    # Consumer care parsed from raw_text
    assert decls.consumer_care is not None
    assert decls.consumer_care.value.email == "care@brand.in"
    assert decls.consumer_care.value.phone == "1800-123-4567"


def test_gemini_candidate_models_fallback(
    sample_image_bytes: bytes, mock_schema_payload: PackagingDeclarationsSchema
):
    """Test fallback across candidate models when primary candidate encounters 429 or 404."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = mock_schema_payload

    # First model call raises 429 quota error, second model call succeeds
    mock_client.models.generate_content.side_effect = [
        RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded"),
        mock_response,
    ]

    service = GeminiPerceptionService(api_key="dummy_key", client=mock_client)
    assert service.model_name == "gemini-3.5-flash-lite"
    assert service.active_model == "gemini-3.5-flash-lite"

    decls, ocr_res = service.extract(sample_image_bytes)

    assert mock_client.models.generate_content.call_count == 2
    first_call_model = mock_client.models.generate_content.call_args_list[0].kwargs["model"]
    second_call_model = mock_client.models.generate_content.call_args_list[1].kwargs["model"]
    assert first_call_model == "gemini-3.5-flash-lite"
    assert second_call_model == "gemini-3.5-flash"
    assert service.active_model == "gemini-3.5-flash"
    assert decls.mrp is not None
    assert decls.mrp.value.amount == 10.00
    assert ocr_res.engine_used == "GEMINI_MULTIMODAL"


def test_gemini_alphanumeric_date_parsing():
    """Test alphanumeric month parsing (e.g. 18-Mar-20, 18-Mar-2020, Mar-2020)."""
    service = GeminiPerceptionService(api_key="dummy_key")

    res_18_mar_20 = service._parse_date_string("18-Mar-20")
    assert res_18_mar_20 == (3, 2020, "03/2020")

    res_18_mar_2020 = service._parse_date_string("18-Mar-2020")
    assert res_18_mar_2020 == (3, 2020, "03/2020")

    res_mar_20 = service._parse_date_string("Mar-20")
    assert res_mar_20 == (3, 2020, "03/2020")

    res_mar_2020 = service._parse_date_string("Mar 2020")
    assert res_mar_2020 == (3, 2020, "03/2020")

    res_slash = service._parse_date_string("18/Mar/20")
    assert res_slash == (3, 2020, "03/2020")


def test_gemini_consumer_care_std_landline_and_rule_6_2(sample_image_bytes: bytes):
    """Test STD code landline parsing and Rule 6(2) compliance with contact details/website."""
    json_text = """
    {
        "mrp": "Rs. 70.00",
        "usp": "Rs. 0.35 / g",
        "mfg_date": "18-Mar-20",
        "consumer_care": "0265 - \\nwww.shreerasanandsweets.com",
        "raw_text": "SHREE RASANAND\\nMRP Rs. 70.00 (incl. of all taxes)\\nNet Qty: 200 g\\nPkd: 18-Mar-20\\nCustomer Care: 0265 - \\nwww.shreerasanandsweets.com"
    }
    """
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json_text
    del mock_response.parsed
    mock_client.models.generate_content.return_value = mock_response

    service = GeminiPerceptionService(api_key="dummy_key", client=mock_client)
    decls, _ = service.extract(sample_image_bytes)

    # 1. Verify mfg_date parsed
    assert decls.mfg_date is not None
    assert decls.mfg_date.value.month == 3
    assert decls.mfg_date.value.year == 2020
    assert decls.mfg_date.value.raw_date_str == "03/2020"

    # 2. Verify consumer_care phone and address
    assert decls.consumer_care is not None
    assert decls.consumer_care.value.phone == "0265 -" or decls.consumer_care.value.phone == "0265 - "
    assert "www.shreerasanandsweets.com" in decls.consumer_care.value.address

    # 3. Verify includes_taxes detected from raw_text
    assert decls.mrp is not None
    assert decls.mrp.value.amount == 70.00
    assert decls.mrp.value.includes_taxes is True

    # 4. Verify Rule 6(2) passes
    engine = LegalMetrologyRuleEngine()
    results = engine.evaluate(decls, is_quality_acceptable=True)
    care_res = next(r for r in results if r.rule_id == "LMPC_R06_2")
    assert care_res.status == RuleStatus.PASS
    assert care_res.violation is None


def test_gemini_includes_taxes_detection_truth_and_falsehood():
    """Test includes_taxes is True when tax clause is in raw_text, and False when omitted everywhere."""
    service = GeminiPerceptionService(api_key="dummy_key")

    # Case 1: Tax clause in raw_text only
    data_with_tax = {
        "mrp": "Rs. 70.00",
        "raw_text": "BRAND SWEETS\nMRP Rs. 70.00\n(Incl. of all taxes)",
    }
    decls1, _ = service._map_dict_to_declarations_and_ocr(data_with_tax)
    assert decls1.mrp is not None
    assert decls1.mrp.value.amount == 70.00
    assert decls1.mrp.value.includes_taxes is True

    # Case 2: No tax clause anywhere
    data_no_tax = {
        "mrp": "Rs. 70.00",
        "raw_text": "BRAND SWEETS\nMRP Rs. 70.00\nBest Before 6 months",
    }
    decls2, _ = service._map_dict_to_declarations_and_ocr(data_no_tax)
    assert decls2.mrp is not None
    assert decls2.mrp.value.amount == 70.00
    assert decls2.mrp.value.includes_taxes is False


def test_gemini_multi_image_extraction(sample_image_bytes: bytes):
    """Verify GeminiPerceptionService handles multiple images and bundles them into contents."""
    json_text = """
    {
        "mrp": "Rs. 99.00 (INCL. OF ALL TAXES)",
        "usp": "Rs. 0.50 / g",
        "net_quantity_value": 200,
        "net_quantity_unit": "g",
        "mfg_date": "15/08/2026",
        "consumer_care": "care@brand.com 1800-111-222",
        "raw_text": "FRONT: NET QTY 200g\\nBACK: MRP Rs. 99.00 (INCL. OF ALL TAXES)\\nMFG: 15/08/2026\\nCARE: care@brand.com"
    }
    """
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json_text
    del mock_response.parsed
    mock_client.models.generate_content.return_value = mock_response

    service = GeminiPerceptionService(api_key="dummy_key", client=mock_client)
    
    # Pass two distinct image payloads (representing front and back packaging angles)
    img1 = sample_image_bytes
    img2 = sample_image_bytes
    decls, ocr_res = service.extract([img1, img2])

    assert mock_client.models.generate_content.call_count == 1
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]
    
    # 2 image parts + 1 prompt = 3 items in contents
    assert len(contents) == 3
    prompt_str = contents[-1]
    assert "Analyze all attached angles/faces of this packaged commodity" in prompt_str
    assert "Synthesize and extract the unified statutory declarations across all provided photos" in prompt_str

    # Verify synthesized declarations
    assert decls.mrp is not None
    assert decls.mrp.value.amount == 99.00
    assert decls.mrp.value.includes_taxes is True
    assert decls.net_quantity is not None
    assert decls.net_quantity.value.magnitude == 200.0
    assert decls.net_quantity.value.unit == "g"
    assert decls.mfg_date is not None
    assert decls.consumer_care is not None
    assert ocr_res.engine_used == "GEMINI_MULTIMODAL"


def test_pipeline_multi_angle_processing(sample_image_bytes: bytes):
    """Verify CompliancePipeline processes multiple packaging angles with unified quality and extraction."""
    json_text = """
    {
        "mrp": "Rs. 50.00 (INCL. OF ALL TAXES)",
        "usp": "Rs. 0.25 / g",
        "net_quantity_value": 200,
        "net_quantity_unit": "g",
        "mfg_date": "08/2026",
        "consumer_care": "support@brand.com",
        "raw_text": "BRAND\\nMRP Rs. 50.00 (INCL. OF ALL TAXES)\\nNet Qty: 200 g\\nPkd: 08/2026\\nsupport@brand.com"
    }
    """
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json_text
    del mock_response.parsed
    mock_client.models.generate_content.return_value = mock_response

    mock_service = GeminiPerceptionService(api_key="dummy_key", client=mock_client)
    pipeline = CompliancePipeline(gemini_service=mock_service)

    # Ingest list of 2 angles
    res = pipeline.process_image([sample_image_bytes, sample_image_bytes])

    assert isinstance(res, PipelineResult)
    assert res.ocr_result.engine_used == "GEMINI_MULTIMODAL"
    assert res.declarations.mrp is not None
    assert res.declarations.mrp.value.amount == 50.00
    assert res.declarations.net_quantity is not None
    assert res.declarations.net_quantity.value.magnitude == 200.0
    # Optical quality gate metrics aggregated
    assert res.quality_metrics.laplacian_variance >= 0.0



