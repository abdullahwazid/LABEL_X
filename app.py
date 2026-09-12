from dotenv import load_dotenv
import os

load_dotenv(override=True)
import hashlib
import importlib
from pathlib import Path
import streamlit as st

import src.ocr.gemini_extractor
import src.pipeline
importlib.reload(src.ocr.gemini_extractor)
importlib.reload(src.pipeline)

from src.decisions.models import ScreeningVerdict
from src.mock_generator import SyntheticPackageGenerator
from src.pipeline import CompliancePipeline
from src.rules.models import RuleStatus
from src.storage.repository import InspectionStorageRepository
from src.reports.generator import ReportGenerator
from src.report.pdf_generator import build_pdf_report


# Page configuration
st.set_page_config(
    page_title="LABEL-X Screener",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Top Header refinement */
    h1 {
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        font-size: 2.1rem !important;
        margin-bottom: 0.2rem !important;
    }

    /* Glassmorphic Callout Cards */
    div[data-testid="stNotification"], div[data-testid="stAlert"] {
        border-radius: 10px !important;
        backdrop-filter: blur(8px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
    }

    /* Metric cards styling & truncation prevention */
    div[data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.03) !important;
        border: 1px solid rgba(255, 255, 255, 0.07) !important;
        padding: 14px 18px !important;
        border-radius: 10px !important;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    div[data-testid="metric-container"]:hover {
        border-color: rgba(99, 102, 241, 0.4) !important;
        transform: translateY(-2px);
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.55rem !important;
        font-weight: 700 !important;
        font-family: 'JetBrains Mono', monospace !important;
        overflow: visible !important;
        text-overflow: unset !important;
        white-space: normal !important;
    }

    /* Clean Enterprise Tables */
    div[data-testid="stTable"] table {
        border-collapse: separate !important;
        border-spacing: 0 !important;
        border-radius: 8px !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        overflow: hidden !important;
    }
    div[data-testid="stTable"] th {
        background-color: rgba(255, 255, 255, 0.04) !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        color: #94a3b8 !important;
        padding: 12px 16px !important;
    }
    div[data-testid="stTable"] td {
        padding: 12px 16px !important;
        border-top: 1px solid rgba(255, 255, 255, 0.04) !important;
        font-size: 0.92rem !important;
    }

    /* Minimalist Pill Badges */
    code {
        font-family: 'JetBrains Mono', monospace !important;
        padding: 2px 7px !important;
        border-radius: 6px !important;
        background: rgba(99, 102, 241, 0.12) !important;
        color: #818cf8 !important;
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
    }

    /* Primary Action Buttons */
    div.stButton > button, div.stDownloadButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em !important;
        padding: 0.55rem 1.25rem !important;
        border: 1px solid rgba(99, 102, 241, 0.3) !important;
        background: linear-gradient(135deg, #4f46e5 0%, #3730a3 100%) !important;
        color: #ffffff !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button:hover, div.stDownloadButton > button:hover {
        border-color: #818cf8 !important;
        box-shadow: 0 4px 14px 0 rgba(79, 70, 229, 0.35) !important;
        transform: translateY(-1px);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize audit storage repository
storage_repo = InspectionStorageRepository()

# Header Section
st.title("🛡️ LABEL-X: AI-Assisted Compliance Screening for Packaged Commodities")
st.caption("Legal Metrology (Packaged Commodities) Rules, 2011 • Department of Consumer Affairs")

st.info(
    "⚖️ **Preliminary Administrative Screening Tool** — This system performs automated compliance "
    "triage and visual evidence collection under the Legal Metrology Act, 2009. Final statutory "
    "determinations and compounding notices remain subject to authorized physical verification by Legal Metrology Inspectors."
)

# Sidebar Controls
st.sidebar.header("🕹️ Inspection Controls")

gemini_key = os.environ.get("GEMINI_API_KEY")
if gemini_key:
    st.sidebar.success(f"🟢 Gemini Multimodal Active ({gemini_key[:8]}...)")
else:
    st.sidebar.error("🔴 GEMINI_API_KEY not found in os.environ")

ingestion_mode = st.sidebar.radio(
    "Screening Ingestion Mode:",
    ["Pick a Sample Package", "Upload Packaging Photo"],
)

sample_map = {
    "Compliant Biscuit Carton (sample_compliant.png)": {
        "file": "data/samples/sample_compliant.png",
        "injected": SyntheticPackageGenerator.COMPLIANT_TEXT,
    },
    "Prohibited Unit Violation - 'gms' (sample_violation_units.png)": {
        "file": "data/samples/sample_violation_units.png",
        "injected": SyntheticPackageGenerator.UNIT_VIOLATION_TEXT,
    },
    "Missing Tax Clause on MRP (sample_violation_mrp.png)": {
        "file": "data/samples/sample_violation_mrp.png",
        "injected": SyntheticPackageGenerator.MRP_VIOLATION_TEXT,
    },
}

image_bytes: bytes | None = None
image_bytes_list: list[bytes] = []
image_label_name: str = "Unknown Package"
image_file_names: list[str] = []
injected_text: list[str] | None = None
uploaded_files = None

if ingestion_mode == "Upload Packaging Photo":
    uploaded_files = st.sidebar.file_uploader(
        "Upload Packaging Image(s) (JPEG, PNG):",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        image_bytes_list = [f.getvalue() for f in uploaded_files]
        image_file_names = [f.name for f in uploaded_files]
        image_bytes = image_bytes_list[0]
        image_label_name = (
            uploaded_files[0].name
            if len(uploaded_files) == 1
            else f"{len(uploaded_files)} Angles ({', '.join(f.name for f in uploaded_files)})"
        )
        gemini_key = os.environ.get("GEMINI_API_KEY")
        pipeline = CompliancePipeline(gemini_api_key=gemini_key)
        result = pipeline.process_image(image_bytes_list)
        st.session_state["inspection_result"] = result
        st.session_state["pipeline"] = pipeline
        st.session_state["image_bytes_list"] = image_bytes_list
        st.session_state["image_file_names"] = image_file_names
    else:
        st.info("👈 Please upload packaging image(s) in the sidebar to begin compliance screening.")
        st.stop()

elif ingestion_mode == "Pick a Sample Package":
    choice = st.sidebar.selectbox("Select Benchmark Sample:", list(sample_map.keys()))
    sample_info = sample_map[choice]
    sample_path = Path(sample_info["file"])
    image_label_name = sample_path.name
    image_file_names = [sample_path.name]

    if not sample_path.exists():
        SyntheticPackageGenerator().save_samples_to_disk("data/samples")

    if sample_path.exists():
        image_bytes = sample_path.read_bytes()
        image_bytes_list = [image_bytes]
        injected_text = sample_info["injected"]
        gemini_key = os.environ.get("GEMINI_API_KEY")
        pipeline = CompliancePipeline(gemini_api_key=gemini_key)
        if injected_text and not pipeline.ocr_service.is_tesseract_available:
            pipeline.set_injected_text(injected_text)
        result = pipeline.process_image(image_bytes)
        st.session_state["inspection_result"] = result
        st.session_state["pipeline"] = pipeline
        st.session_state["image_bytes_list"] = image_bytes_list
        st.session_state["image_file_names"] = image_file_names
    else:
        st.sidebar.error(f"Sample file {sample_path} not found.")
        st.stop()

# Main Execution Layout
result = st.session_state.get("inspection_result")
pipeline = st.session_state.get("pipeline")

if result is not None and image_bytes is not None:
    # Surface Gemini fallback/error in UI, session state, and sidebar
    if result.gemini_error:
        st.error(f"Gemini perception failed with error: {result.gemini_error}")
        st.session_state["gemini_error"] = result.gemini_error
        if gemini_key:
            st.sidebar.warning(f"⚠️ **Gemini Fallback Triggered**:\n`{result.gemini_error}`")

    # Persist audit record in SQLite
    inspection_id = storage_repo.save_inspection(result, image_name=image_label_name)

    col_left, col_right = st.columns(2)

    # -------------------------------------------------------------
    # Left Column: Perception & Optical Quality
    # -------------------------------------------------------------
    with col_left:
        st.subheader("📷 Perception & Optical Quality")
        
        display_images = st.session_state.get("image_bytes_list", [image_bytes] if image_bytes else [])
        display_names = st.session_state.get("image_file_names", [image_label_name])

        if len(display_images) > 1:
            st.markdown(f"**Multi-Angle Package Ingestion ({len(display_images)} angles uploaded):**")
            gallery_cols = st.columns(min(len(display_images), 3))
            for idx, img_data in enumerate(display_images):
                with gallery_cols[idx % len(gallery_cols)]:
                    cap = display_names[idx] if idx < len(display_names) else f"Angle {idx+1}"
                    st.image(img_data, caption=cap, use_container_width=True)
        elif display_images:
            st.image(display_images[0], caption=f"Uploaded Package: {image_label_name}", use_container_width=True)

        if result.ocr_result.engine_used == "GEMINI_MULTIMODAL":
            active_model = (
                getattr(pipeline.gemini_service, "active_model", "gemini-3.5-flash-lite")
                if pipeline and pipeline.gemini_service
                else "gemini-3.5-flash-lite"
            )
            st.success(f"🟢 **Perception Engine Active**: `GEMINI_MULTIMODAL` ({active_model})")
        elif result.gemini_error and gemini_key:
            st.warning(
                f"⚠️ **Gemini Perception Notice**: System fell back to local `{result.ocr_result.engine_used}`.\n\n"
                f"**Root Cause:** `{result.gemini_error}`"
            )
        else:
            st.info(f"ℹ️ **Perception Engine Active**: `{result.ocr_result.engine_used}`")

        st.markdown("#### 🔬 Image Quality Gate")
        q = result.quality_metrics
        m1, m2, m3 = st.columns(3)

        with m1:
            sharp_badge = "✅ Pass" if q.is_sharp else "⚠️ Blurry"
            st.metric("Sharpness (Laplacian)", f"{q.laplacian_variance:.1f}", sharp_badge)

        with m2:
            glare_badge = "✅ Pass" if q.has_acceptable_glare else "⚠️ Glare"
            st.metric("Glare Ratio", f"{q.glare_ratio * 100:.1f}%", glare_badge)

        with m3:
            res_badge = "✅ Clear" if q.is_acceptable_for_screening else "⚠️ Degraded"
            st.metric("Resolution", f"{q.width}×{q.height} px", res_badge)

        if q.quality_warnings:
            st.markdown("##### ⚠️ Optical Degradation Warnings")
            for warning in q.quality_warnings:
                st.warning(warning)
        else:
            st.success("Optical quality parameters satisfy automated screening gates.")

        # OCR Inspection Expander
        with st.expander("🔍 Show Extracted OCR Lines & Bounding Boxes", expanded=False):
            st.caption(
                f"**Engine Used:** `{result.ocr_result.engine_used}` | "
                f"**Mean Confidence:** `{result.ocr_result.mean_confidence * 100:.1f}%`"
            )
            for idx, line in enumerate(result.ocr_result.lines):
                st.markdown(
                    f"- **Line {idx + 1}** (`conf: {line.confidence * 100:.0f}%`): "
                    f"`{line.text}` — [bbox: `({line.bbox.x1}, {line.bbox.y1})` to `({line.bbox.x2}, {line.bbox.y2})`]"
                )

    # -------------------------------------------------------------
    # Right Column: Adjudication & Evidence Dossier
    # -------------------------------------------------------------
    with col_right:
        st.subheader("⚖️ Adjudication & Evidence Dossier")
        st.caption(f"**Inspection Audit ID:** `{inspection_id}`")

        # Three-State Verdict Banner
        dec = result.decision
        if dec.verdict == ScreeningVerdict.NO_OBVIOUS_ISSUE:
            st.success(
                "### ✅ VERDICT: NO OBVIOUS ISSUE\n"
                "All machine-checkable statutory declarations comply with the Legal Metrology Rules, 2011."
            )
        elif dec.verdict == ScreeningVerdict.NEEDS_REVIEW:
            st.warning(
                "### ⚠️ VERDICT: NEEDS REVIEW\n"
                "Ambiguous text clarity, optical degradation, or advisory conditions require manual officer verification."
            )
        else:
            st.error(
                f"### 🚨 VERDICT: POTENTIAL NON-COMPLIANCE\n"
                f"Explicit statutory infractions detected ({dec.critical_violations_count} critical, {dec.major_violations_count} major)."
            )

        st.info(f"**Executive Summary:** {dec.summary}")

        # Extracted Declarations Table
        st.markdown("#### 📋 Extracted Statutory Declarations")
        d = result.declarations

        mrp_display = (
            f"Rs. {d.mrp.value.amount:.2f} ({'Incl. of taxes' if d.mrp.value.includes_taxes else 'MISSING TAX CLAUSE'})"
            if d.mrp
            else "❌ Missing"
        )
        qty_display = (
            f"{d.net_quantity.value.magnitude} {d.net_quantity.value.raw_unit} "
            f"({'Normalized: ' + d.net_quantity.value.unit if d.net_quantity.value.raw_unit != d.net_quantity.value.unit else 'Valid SI'})"
            if d.net_quantity
            else "❌ Missing"
        )
        usp_display = (
            f"Rs. {d.unit_sale_price.value.amount:.2f} / {d.unit_sale_price.value.unit}"
            if d.unit_sale_price
            else "Not Declared / N/A"
        )
        mfg_display = d.mfg_date.value.raw_date_str if d.mfg_date else "❌ Missing"
        care_display = (
            f"{d.consumer_care.value.email or ''} {d.consumer_care.value.phone or ''}".strip()
            if d.consumer_care and (d.consumer_care.value.email or d.consumer_care.value.phone)
            else "❌ Missing"
        )

        st.table(
            [
                {"Mandatory Declaration": "Maximum Retail Price (MRP)", "Observed Value": mrp_display},
                {"Mandatory Declaration": "Net Quantity", "Observed Value": qty_display},
                {"Mandatory Declaration": "Unit Sale Price (USP)", "Observed Value": usp_display},
                {"Mandatory Declaration": "Mfg / Packing Date", "Observed Value": mfg_display},
                {"Mandatory Declaration": "Consumer Grievance Care", "Observed Value": care_display},
            ]
        )

        # Statutory Infractions List
        failed_rules = [r for r in result.rule_results if r.status == RuleStatus.FAIL]
        if failed_rules:
            st.markdown("#### 🚨 Identified Statutory Infractions")
            for r in failed_rules:
                v = r.violation
                severity_badge = f"🔴 {v.severity.value}" if v and v.severity.value == "CRITICAL" else f"🟠 {v.severity.value if v else 'FAIL'}"
                with st.container(border=True):
                    st.markdown(f"**{r.rule_reference}** — `{r.rule_id}` [{severity_badge}]")
                    if v:
                        st.markdown(f"**Violation:** {v.message}")
                        st.markdown(f"**Expected Standard:** `{v.expected_condition}`")
                        if v.detected_value:
                            st.markdown(f"**Extracted Input:** `{v.detected_value}`")
        else:
            st.markdown("#### ✅ Statutory Rules Compliance")
            st.success("All 6 evaluated statutory rule checkpoints satisfied.")

        # Cryptographic Evidence Dossier
        if result.evidence_dossier.crops:
            st.markdown("#### 🔍 Visual Evidence Dossier (Audit Trail)")
            for crop in result.evidence_dossier.crops:
                with st.container(border=True):
                    c_col1, c_col2 = st.columns([1, 2])
                    with c_col1:
                        st.image(crop.crop_bytes, caption=f"Field: {crop.field_name}")
                    with c_col2:
                        st.markdown(f"**Rule:** {crop.rule_reference} (`{crop.rule_id}`)")
                        st.markdown(f"**Extracted Text:** `{crop.raw_text}`")
                        st.markdown(f"**SHA-256 Hash:**")
                        st.code(crop.sha256_hash, language="text")

        # Statutory Inspection Notice Generation & Download
        st.markdown("#### 📜 Statutory Notice Generation")
        report = ReportGenerator().generate_text_report(inspection_id, result, image_label_name)

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            pdf_bytes = build_pdf_report(result, audit_id=inspection_id)
            st.download_button(
                label="📄 Download Statutory Screening Dossier (.pdf)",
                data=bytes(pdf_bytes),
                file_name=f"LabelX_Inspection_{inspection_id[:8]}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with btn_col2:
            st.download_button(
                label="📥 Download Statutory Screening Notice (.txt)",
                data=report.report_text,
                file_name=f"Notice_{inspection_id[:8]}.txt",
                mime="text/plain",
                use_container_width=True,
            )

else:
    st.info("👈 Please select a sample package from the sidebar or upload an image to begin compliance screening.")

# -------------------------------------------------------------
# Historical Audit Trail Section
# -------------------------------------------------------------
st.divider()
with st.expander("📋 Inspection History & Audit Trail", expanded=False):
    recent_records = storage_repo.get_recent_inspections(limit=10)
    if recent_records:
        history_data = [
            {
                "Timestamp (UTC)": r.timestamp[:19].replace("T", " "),
                "Inspection ID": r.inspection_id[:8] + "...",
                "Package Name": r.image_name,
                "Verdict": r.verdict,
                "Infractions": f"{r.critical_count} Crit, {r.major_count} Maj",
                "Quality": "Sharp" if r.is_sharp else "Degraded",
            }
            for r in recent_records
        ]
        st.dataframe(history_data, use_container_width=True)
    else:
        st.info("No prior inspection records found in local audit database.")
