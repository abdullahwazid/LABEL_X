from dotenv import load_dotenv
import os

load_dotenv(override=True)
import base64
import hashlib
import html as _h
import importlib
from datetime import datetime, timezone
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


# =============================================================================
# Page shell
# =============================================================================
st.set_page_config(
    page_title="LABEL-X · Inspection Console",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

STYLESHEET = (Path(__file__).parent / "assets" / "console.css").read_text(encoding="utf-8")
st.markdown(f"<style>{STYLESHEET}</style>", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Markup helpers — the console is composed as one self-contained HTML document
# fragment, so every element can be styled and animated exactly as designed.
# -----------------------------------------------------------------------------
def e(value) -> str:
    """HTML-escape a value for safe interpolation."""
    return _h.escape(str(value if value is not None else ""))


def h(*parts: str) -> str:
    """Concatenate markup fragments without introducing markdown line breaks."""
    return "".join(parts)


def paint(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def sb(markup: str) -> None:
    st.sidebar.markdown(markup, unsafe_allow_html=True)


def data_uri(raw: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(bytes(raw)).decode('ascii')}"


TONE_HEX = {"ok": "#2fd6a0", "warn": "#ffb340", "bad": "#ff5c6c", "acc": "#6d6bf6"}
GLYPH = {"ok": "&#10003;", "bad": "&#10007;", "warn": "!", "idle": "&#8211;"}


# =============================================================================
# Audit storage
# =============================================================================
storage_repo = InspectionStorageRepository()

# =============================================================================
# Control console (sidebar)
# =============================================================================
sb('<div class="sbb"><div class="sbm">🛡️</div><div><b>LABEL-X</b><span>Control console</span></div></div>')

sb('<div class="sbl">Perception link</div>')
gemini_key = os.environ.get("GEMINI_API_KEY")
if gemini_key:
    sb(f'<div class="sbs on"><i></i><div>Gemini multimodal online<small>key {e(gemini_key[:8])}…</small></div></div>')
else:
    sb('<div class="sbs off"><i></i><div>Multimodal link down<small>GEMINI_API_KEY not set</small></div></div>')

sb('<div class="sbl">Ingestion mode</div>')
ingestion_mode = st.sidebar.radio(
    "Ingestion mode",
    ["Pick a Sample Package", "Upload Packaging Photo"],
    label_visibility="collapsed",
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


def command_bar(engine: str, audit: str, package: str, live: bool) -> str:
    cells = h(*[
        f'<div class="cell"><span>{e(k)}</span><b>{e(v)}</b></div>'
        for k, v in (
            ("Engine", engine),
            ("Audit ID", audit[:8] if audit else "—"),
            ("Captured", datetime.now(timezone.utc).strftime("%d %b · %H:%M UTC")),
        )
    ])
    link = (
        '<span class="tag acc"><i class="led pulse"></i>Multimodal link</span>'
        if live else '<span class="tag warn"><i class="led"></i>Local perception</span>'
    )
    return h(
        '<div class="cmd rise"><div class="brand"><div class="mark">🛡️</div><div>',
        '<b>LABEL&#8209;X <i>/</i> Inspection Console</b>',
        f'<span>Legal Metrology (Packaged Commodities) Rules, 2011 · {e(package)}</span>',
        '</div></div><div class="grow"></div>',
        f'<div class="cmdmeta">{link}{cells}</div></div>',
    )


def standby(message: str) -> None:
    paint(h(
        '<div class="lx">',
        command_bar("IDLE", "", "Department of Consumer Affairs", bool(gemini_key)),
        '<div class="panel standby rise"><div class="radar"><div class="sw"></div><div class="co">🛡️</div></div>',
        '<h3>Console on standby</h3>',
        f'<p>{e(message)}</p>',
        '<div class="kb">',
        h(*[f'<span class="tag">{e(s)}</span>' for s in
            ("Optical gate", "Perception", "Extraction", "Rule engine", "Arbitration")]),
        '</div></div></div>',
    ))


if ingestion_mode == "Upload Packaging Photo":
    sb('<div class="sbl">Package imagery</div>')
    uploaded_files = st.sidebar.file_uploader(
        "Upload packaging image(s) — JPEG / PNG",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        label_visibility="collapsed",
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
        with st.spinner("Screening package…"):
            result = pipeline.process_image(image_bytes_list)
        st.session_state["inspection_result"] = result
        st.session_state["pipeline"] = pipeline
        st.session_state["image_bytes_list"] = image_bytes_list
        st.session_state["image_file_names"] = image_file_names
    else:
        standby(
            "Upload one or more label photographs from the control console. Multiple angles of the "
            "same package widen declaration coverage and lift extraction confidence."
        )
        st.stop()

elif ingestion_mode == "Pick a Sample Package":
    sb('<div class="sbl">Benchmark sample</div>')
    choice = st.sidebar.selectbox(
        "Benchmark sample", list(sample_map.keys()), label_visibility="collapsed"
    )
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
        with st.spinner("Screening package…"):
            result = pipeline.process_image(image_bytes)
        st.session_state["inspection_result"] = result
        st.session_state["pipeline"] = pipeline
        st.session_state["image_bytes_list"] = image_bytes_list
        st.session_state["image_file_names"] = image_file_names
    else:
        st.sidebar.error(f"Sample file {sample_path} not found.")
        standby(f"Benchmark sample {sample_path} could not be located on disk.")
        st.stop()


# =============================================================================
# Console composition
# =============================================================================
def render_console(result, pipeline, inspection_id, package_name, images, names) -> None:
    dec = result.decision
    q = result.quality_metrics
    d = result.declarations
    ocr = result.ocr_result

    failed = [r for r in result.rule_results if r.status == RuleStatus.FAIL]
    passed = [r for r in result.rule_results if r.status == RuleStatus.PASS]

    # ---- spatial reference frame ------------------------------------------
    known = [l.bbox for l in ocr.lines if l.bbox and l.bbox.area() > 0]
    known += [c.bbox for c in result.evidence_dossier.crops if c.bbox.area() > 0]
    space_w = max([q.width] + [b.x2 for b in known]) if known else max(q.width, 1)
    space_h = max([q.height] + [b.y2 for b in known]) if known else max(q.height, 1)

    boxes: list[dict] = []

    def add_box(bbox, kind, text, label="", conf=None):
        if bbox is None or bbox.area() <= 0:
            return None
        boxes.append({"b": bbox, "kind": kind, "text": text, "label": label, "conf": conf})
        return len(boxes) - 1

    for line in ocr.lines:
        add_box(line.bbox, "line", line.text, "", line.confidence)

    # ---- mandatory declarations -------------------------------------------
    declarations: list[dict] = []

    def declare(name, field, value, note, state, tag):
        declarations.append({
            "name": name, "value": value, "note": note, "state": state, "tag": tag,
            "box": add_box(getattr(field, "bbox", None), "decl", value, name) if field else None,
        })

    if d.mrp:
        taxed = d.mrp.value.includes_taxes
        declare("Maximum Retail Price", d.mrp, f"Rs. {d.mrp.value.amount:.2f}",
                "inclusive of all taxes" if taxed else "no inclusive-of-taxes clause",
                "ok" if taxed else "bad", "Compliant" if taxed else "Tax clause")
    else:
        declare("Maximum Retail Price", None, "Not detected", "", "bad", "Missing")

    if d.net_quantity:
        nq = d.net_quantity.value
        unit_ok = nq.raw_unit == nq.unit
        declare("Net Quantity", d.net_quantity, f"{nq.magnitude} {nq.raw_unit}",
                "" if unit_ok else f"normalises to {nq.unit}",
                "ok" if unit_ok else "bad", "Valid SI" if unit_ok else "Bad unit")
    else:
        declare("Net Quantity", None, "Not detected", "", "bad", "Missing")

    if d.unit_sale_price:
        u = d.unit_sale_price.value
        declare("Unit Sale Price", d.unit_sale_price, f"Rs. {u.amount:.2f} / {u.unit}", "", "ok", "Declared")
    else:
        declare("Unit Sale Price", None, "Not declared", "", "idle", "N/A")

    if d.mfg_date:
        declare("Mfg / Packing Date", d.mfg_date, d.mfg_date.value.raw_date_str, "", "ok", "Declared")
    else:
        declare("Mfg / Packing Date", None, "Not detected", "", "bad", "Missing")

    care = (
        f"{d.consumer_care.value.email or ''} {d.consumer_care.value.phone or ''}".strip()
        if d.consumer_care and (d.consumer_care.value.email or d.consumer_care.value.phone)
        else ""
    )
    if care:
        declare("Consumer Grievance Care", d.consumer_care, care, "", "ok", "Declared")
    else:
        declare("Consumer Grievance Care", None, "Not detected", "", "bad", "Missing")

    declared_count = sum(1 for x in declarations if x["state"] == "ok")

    # ---- infractions + spatial evidence ------------------------------------
    crop_by_rule = {c.rule_id: c for c in result.evidence_dossier.crops}
    violations: list[dict] = []
    for r in failed:
        v = r.violation
        crop = crop_by_rule.get(r.rule_id)
        violations.append({
            "id": r.rule_id, "ref": r.rule_reference,
            "severity": v.severity.value if v else "FAIL",
            "critical": bool(v and v.severity.value == "CRITICAL"),
            "field": v.field if v else "—",
            "message": v.message if v else r.reason,
            "expected": v.expected_condition if v else "—",
            "detected": (v.detected_value if v else None) or "",
            "crop": data_uri(crop.crop_bytes) if crop else None,
            "hash": crop.sha256_hash if crop else "",
            "box": add_box(crop.bbox, "viol", crop.raw_text, crop.field_name) if crop else None,
        })

    has_viol_box = any(b["kind"] == "viol" for b in boxes)
    default_filter = "viol" if has_viol_box else "all"

    # ---- verdict ------------------------------------------------------------
    if dec.verdict == ScreeningVerdict.NO_OBVIOUS_ISSUE:
        tone, title = "ok", "No Obvious Issue"
        vtext = ("Every machine-checkable statutory declaration on this package conforms to the "
                 "Legal Metrology (Packaged Commodities) Rules, 2011.")
    elif dec.verdict == ScreeningVerdict.NEEDS_REVIEW:
        tone, title = "warn", "Needs Review"
        vtext = ("Ambiguous text clarity, optical degradation or advisory conditions prevent an "
                 "automated determination. Manual officer verification is required.")
    else:
        tone, title = "bad", "Potential Non-Compliance"
        vtext = (f"Explicit statutory infractions were localised on the package — "
                 f"{dec.critical_violations_count} critical and {dec.major_violations_count} major.")

    active_model = (
        getattr(pipeline.gemini_service, "active_model", "")
        if pipeline and pipeline.gemini_service else ""
    )
    engine_label = active_model if (ocr.engine_used == "GEMINI_MULTIMODAL" and active_model) else ocr.engine_used

    # =========================================================================
    # Fragment builders
    # =========================================================================
    def rail() -> str:
        stages = [
            ("&#9673;", "Ingest", f"{len(images)} frame{'s' if len(images) != 1 else ''}", ""),
            ("&#9678;", "Optical gate", "pass" if q.is_acceptable_for_screening else "degraded",
             "" if q.is_acceptable_for_screening else "caut"),
            ("&#9680;", "Perception", f"{ocr.engine_used.lower()} · {ocr.mean_confidence * 100:.0f}%", ""),
            ("&#9634;", "Extraction", f"{declared_count}/5 declarations", "" if declared_count >= 4 else "caut"),
            ("&#9670;", "Rule engine", f"{len(passed)}/{len(result.rule_results)} passed",
             "" if not failed else ("alert" if dec.critical_violations_count else "caut")),
            ("&#9878;", "Arbitration", title.lower(), {"ok": "", "warn": "caut", "bad": "alert"}[tone]),
        ]
        return h('<div class="panel rail rise" style="animation-delay:.05s">', h(*[
            f'<div class="node {t}"><div class="ndot">{ic}</div><div><div class="nn">{e(n)}</div>'
            f'<div class="nv">{e(val)}</div></div></div>'
            for ic, n, val, t in stages
        ]), '</div>')

    def deck() -> str:
        r = 58.0
        circ = 2 * 3.14159265 * r
        offset = circ * (1 - dec.confidence_score)
        counters = h(
            f'<div class="ctr {"bad" if dec.critical_violations_count else "ok"}">'
            f'<b>{dec.critical_violations_count}</b><span>Critical<br/>infractions</span></div>',
            f'<div class="ctr {"warn" if dec.major_violations_count else "ok"}">'
            f'<b>{dec.major_violations_count}</b><span>Major<br/>infractions</span></div>',
            f'<div class="ctr {"ok" if len(passed) == len(result.rule_results) else "warn"}">'
            f'<b>{len(passed)}/{len(result.rule_results)}</b><span>Statutory<br/>checkpoints</span></div>',
        )
        return h(
            f'<div class="panel deck {tone} rise" style="animation-delay:.1s">',
            '<div class="gauge"><div class="ticks"></div>',
            '<svg viewBox="0 0 134 134"><circle class="trk" cx="67" cy="67" r="58" fill="none" stroke-width="7"/>',
            f'<circle class="arc" cx="67" cy="67" r="58" fill="none" stroke-width="7" stroke="{TONE_HEX[tone]}" ',
            f'stroke-dasharray="{circ:.1f}" style="--c:{circ:.1f};--o:{offset:.1f}" stroke-dashoffset="{circ:.1f}"/></svg>',
            f'<div class="in"><div><div class="v" style="color:{TONE_HEX[tone]}">{dec.confidence_score * 100:.0f}%</div>',
            '<div class="l">Confidence</div></div></div></div>',
            f'<div><div class="vk">Screening verdict &nbsp;·&nbsp; {e(package_name)}</div>',
            f'<div class="vt">{e(title)}</div><div class="vx">{e(vtext)}</div>',
            f'<div class="vsum"><b>Adjudication summary —</b> {e(dec.summary)}</div></div>',
            f'<div class="ctrs">{counters}</div></div>',
        )

    def viewer() -> str:
        chips = ""
        if boxes:
            chips = h('<div class="chips">', h(*[
                f'<label class="chip" for="ovf-{k}">{e(lbl)}</label>'
                for k, lbl in (("all", "All lines"), ("decl", "Declarations"),
                               ("viol", "Violations"), ("off", "Off"))
            ]), '</div>')

        overlay = ""
        if boxes:
            cells = []
            for i, bx in enumerate(boxes):
                b = bx["b"]
                left = 100 * b.x1 / space_w
                top = 100 * b.y1 / space_h
                wid = 100 * (b.x2 - b.x1) / space_w
                hei = 100 * (b.y2 - b.y1) / space_h
                meta = bx["label"] or ("Infraction region" if bx["kind"] == "viol" else "Recognised line")
                if bx["conf"] is not None:
                    meta += f" · {bx['conf'] * 100:.0f}%"
                cells.append(h(
                    f'<div class="box {bx["kind"]}" id="box-{i}" data-b="{i}" ',
                    f'style="left:{left:.3f}%;top:{top:.3f}%;width:{wid:.3f}%;height:{hei:.3f}%;',
                    f'animation-delay:{0.75 + i * 0.035:.2f}s">',
                    f'<span class="bl">{e(meta)}</span>',
                    f'<span class="bt">{e(bx["text"])}</span></div>',
                ))
            overlay = f'<div class="ov">{h(*cells)}</div>'

        frames = h(*[
            f'<img data-i="{i}" class="{"on" if i == 0 else ""}" src="{im}" alt="package frame {i + 1}"/>'
            for i, im in enumerate(images)
        ])
        strip = ""
        if len(images) > 1:
            strip = h('<div class="strip">', h(*[
                f'<label class="shot" for="fr-{i}"><img src="{im}" alt=""/>'
                f'<span class="cap">{e(names[i] if i < len(names) else f"Angle {i + 1}")}</span></label>'
                for i, im in enumerate(images)
            ]), '</div>')

        note = "" if boxes else h(
            '<div class="nospace"><b>Spatial mapping unavailable.</b> The active perception engine returned '
            'text without pixel coordinates, so declaration regions cannot be plotted onto the label. '
            'Recognised text is listed in the perception log below.</div>'
        )
        return h(
            '<div class="panel rise" style="animation-delay:.16s"><div class="phead">',
            '<span class="eyebrow">Evidence viewer</span>',
            f'<span class="tag">{len(images)} frame{"s" if len(images) > 1 else ""}</span>',
            f'<span class="tag acc">{len(boxes)} regions</span>' if boxes else "",
            chips, '</div>',
            f'<div class="frame">{frames}{overlay}<div class="scan"></div>',
            '<i class="vf tl"></i><i class="vf tr"></i><i class="vf bl"></i><i class="vf br"></i></div>',
            note, strip, '</div>',
        )

    def dbox(idx) -> str:
        return f' data-b="{idx}"' if idx is not None else ""

    def decl_panel() -> str:
        rows = h(*[
            h('<div class="drow"', dbox(x["box"]), '>',
              f'<div class="dst {x["state"]}">{GLYPH[x["state"]]}</div>',
              f'<div class="dm"><div class="dn">{e(x["name"])}</div>',
              f'<div class="dv">{e(x["value"])}',
              f'<span class="dnote">{e(x["note"])}</span>' if x["note"] else "",
              '</div></div>',
              f'<span class="tag {x["state"]}">{e(x["tag"])}</span></div>')
            for x in declarations
        ])
        return h(
            '<div class="panel rise" style="animation-delay:.2s"><div class="phead">',
            '<span class="eyebrow">Mandatory declarations</span>',
            '<span class="tag">Rule 6 &amp; Rule 13</span></div>',
            f'<div class="decl">{rows}</div></div>',
        )

    def meter_panel() -> str:
        mp = (q.width * q.height) / 1_000_000.0
        specs = [
            ("Focus — Laplacian variance", f"{q.laplacian_variance:.1f}",
             max(2.0, min(100.0, q.laplacian_variance / 300.0 * 100.0)), 80 / 300 * 100,
             "ok" if q.is_sharp else "warn",
             "sharp · gate ≥ 80.0" if q.is_sharp else "below the 80.0 sharpness gate"),
            ("Specular glare coverage", f"{q.glare_ratio * 100:.1f}%",
             max(2.0, min(100.0, q.glare_ratio / 0.15 * 100.0)), 0.05 / 0.15 * 100,
             "ok" if q.has_acceptable_glare else "warn",
             "within tolerance · ceiling 5.0%" if q.has_acceptable_glare else "exceeds the 5.0% glare ceiling"),
            ("Capture resolution", f"{q.width}×{q.height}",
             max(4.0, min(100.0, mp / 2.0 * 100.0)), None,
             "ok" if q.is_acceptable_for_screening else "warn", f"{mp:.2f} megapixel frame"),
        ]
        rows = h(*[
            h('<div><div class="mh">', f'<span class="n">{e(name)}</span>',
              f'<span class="v" style="color:{TONE_HEX[t]}">{e(read)}</span></div>',
              f'<div class="track"><i class="{t}" style="--w:{pct:.1f}%"></i>',
              f'<span class="thr" style="left:{thr:.1f}%"></span>' if thr is not None else "",
              f'</div><div class="mf">{e(foot)}</div></div>')
            for name, read, pct, thr, t, foot in specs
        ])
        warnings = list(q.quality_warnings) + list(dec.advisory_notes)
        notes = h(*[f'<div class="note warn"><span>&#9888;</span><div>{e(w)}</div></div>' for w in warnings]) \
            or '<div class="note info"><span>&#10003;</span><div>Optical parameters satisfy every automated screening gate.</div></div>'
        return h(
            '<div class="panel rise" style="animation-delay:.26s"><div class="phead">',
            '<span class="eyebrow">Optical quality gate</span>',
            f'<span class="tag {"ok" if q.is_acceptable_for_screening else "warn"}">',
            f'{"Pass" if q.is_acceptable_for_screening else "Degraded"}</span></div>',
            f'<div class="meters">{rows}</div>',
            f'<div style="padding:0 17px 16px">{notes}</div></div>',
        )

    def findings() -> str:
        head = h('<div class="hsec"><span class="bar"></span><h2>Statutory findings</h2>',
                 f'<span class="num">{len(violations)} infraction{"s" if len(violations) != 1 else ""}</span>'
                 if violations else "", '<span class="ln"></span></div>')
        if not violations:
            return head + h(
                '<div class="panel clean rise"><div class="i">&#10003;</div><div>',
                '<b>No machine-checkable infraction detected</b>',
                f'<span>All {len(result.rule_results)} deterministic statutory checkpoints were satisfied. '
                'Physical verification by an authorised inspector remains the statutory determinant.</span>',
                '</div></div>',
            )
        cards = []
        for v in violations:
            evidence = ""
            if v["crop"]:
                locate = (f'<a class="chip" href="#box-{v["box"]}" style="margin-top:10px">'
                          '&#9678; Locate on label</a>') if v["box"] is not None else ""
                evidence = h(
                    f'<div class="vev"><img src="{v["crop"]}" alt="evidence crop"/><div class="hashb">',
                    '<div class="eyebrow" style="margin-bottom:6px">SHA&#8209;256 evidence digest</div>',
                    f'<div class="hash">{e(v["hash"])}</div>{locate}</div></div>',
                )
            cards.append(h(
                '<div class="panel viol ', "crit" if v["critical"] else "", ' rise"',
                dbox(v["box"]), '>',
                '<span class="rib"></span><div class="vh">',
                f'<span class="tag {"bad" if v["critical"] else "warn"}"><i class="led"></i>{e(v["severity"])}</span>',
                f'<span class="vref">{e(v["ref"])}</span>',
                f'<span class="tag">{e(v["id"])}</span>',
                f'<span class="tag idle" style="margin-left:auto">{e(v["field"])}</span></div>',
                f'<div class="vm">{e(v["message"])}</div><div class="cmpg">',
                f'<div class="cmp want"><div class="k">Statute requires</div><div class="v">{e(v["expected"])}</div></div>',
                '<div class="cmp got"><div class="k">Observed on package</div>',
                f'<div class="v">{e(v["detected"]) if v["detected"] else "— not present —"}</div></div></div>',
                evidence, '</div>',
            ))
        return head + h(*cards)

    def ocr_rows() -> str:
        if ocr.lines:
            log = h(*[
                h('<div class="lrow">', f'<span class="li">{i + 1:02d}</span>',
                  f'<span class="lt">{e(l.text)}</span>',
                  (f'<span class="lb">{l.bbox.x1},{l.bbox.y1} &#8594; {l.bbox.x2},{l.bbox.y2}</span>'
                   if l.bbox and l.bbox.area() > 0 else ""),
                  '<span class="lc"><span class="t">',
                  f'<i style="width:{l.confidence * 100:.0f}%;background:',
                  f'{TONE_HEX["ok" if l.confidence >= 0.85 else "warn" if l.confidence >= 0.6 else "bad"]}"></i></span>',
                  f'<span class="p" style="color:',
                  f'{TONE_HEX["ok" if l.confidence >= 0.85 else "warn" if l.confidence >= 0.6 else "bad"]}">',
                  f'{l.confidence * 100:.0f}%</span></span></div>')
                for i, l in enumerate(ocr.lines)
            ])
        else:
            log = '<div class="lrow"><span class="lt">No text lines were recovered from this frame.</span></div>'
        return log

    def log_panel() -> str:
        return h(
            '<div class="panel rise" style="animation-delay:.3s"><div class="phead">',
            '<span class="eyebrow">Perception log</span>',
            f'<span class="tag">{len(ocr.lines)} lines</span>',
            f'<span class="tag acc">mean {ocr.mean_confidence * 100:.0f}%</span>',
            f'<span class="tag idle" style="margin-left:auto">{e(ocr.engine_used)}</span></div>',
            f'<div class="logwrap">{ocr_rows()}</div></div>',
        )

    def folds() -> str:
        tone_map = {"PASS": "ok", "FAIL": "bad", "NEEDS_REVIEW": "warn"}
        ledger = h(*[
            h(f'<div class="drow"><div class="dst {tone_map.get(r.status.value, "idle")}">',
              f'{GLYPH[tone_map.get(r.status.value, "idle")]}</div><div class="dm">',
              f'<div class="dn">{e(r.rule_reference)}<span class="dnote">{e(r.rule_id)}</span></div>',
              f'<div class="dv" style="font-family:var(--ui);font-size:.775rem;color:#a9b3cb">{e(r.reason)}</div>',
              f'</div><span class="tag {tone_map.get(r.status.value, "idle")}">{e(r.status.value)}</span></div>')
            for r in result.rule_results
        ])

        records = storage_repo.get_recent_inspections(limit=10)
        vtone = {"NO_OBVIOUS_ISSUE": "ok", "NEEDS_REVIEW": "warn", "POTENTIAL_NON_COMPLIANCE": "bad"}
        vshort = {"NO_OBVIOUS_ISSUE": "Clear", "NEEDS_REVIEW": "Review", "POTENTIAL_NON_COMPLIANCE": "Breach"}
        if records:
            hist = h(
                '<table class="hist"><thead><tr><th>Timestamp (UTC)</th><th>Audit ID</th><th>Package</th>',
                '<th>Verdict</th><th>Infractions</th><th>Optics</th></tr></thead><tbody>',
                h(*[
                    h('<tr>', f'<td class="m">{e(r.timestamp[:19].replace("T", " "))}</td>',
                      f'<td class="m">{e(r.inspection_id[:8])}</td>', f'<td>{e(r.image_name)}</td>',
                      f'<td><span class="tag {vtone.get(r.verdict, "idle")}">{e(vshort.get(r.verdict, r.verdict))}</span></td>',
                      f'<td class="m">{r.critical_count}C · {r.major_count}M</td>',
                      f'<td class="m">{"sharp" if r.is_sharp else "degraded"}</td></tr>')
                    for r in records
                ]),
                '</tbody></table>',
            )
        else:
            hist = '<div class="note info"><span>&#8942;</span><div>No prior inspection records in the local audit ledger.</div></div>'

        def fold(label, sub, body):
            return h(
                f'<details class="panel fold"><summary><span class="car">&#9656;</span>{label}',
                f'<span class="sub">{e(sub)}</span></summary>',
                f'<div class="foldb">{body}</div></details>',
            )

        return h(
            '<div class="hsec"><span class="bar"></span><h2>Audit record</h2><span class="ln"></span></div>',
            fold("Rule evaluation ledger", f"{len(result.rule_results)} checkpoints", f'<div class="log">{ledger}</div>'),
            fold("Inspection history &amp; audit trail", f"{len(records)} records",
                 f'<div class="log" style="padding:4px 6px">{hist}</div>'),
        )

    # ---- state machinery: CSS-only filters, frame switching, region linking --
    chip_on = ("color:#fff;border-color:rgba(109,107,246,.65);"
               "background:linear-gradient(140deg,rgba(109,107,246,.9),rgba(63,61,201,.9));"
               "box-shadow:0 6px 16px -9px rgba(109,107,246,.95)")
    rules = [
        f'#ovf-{k}:checked ~ .split label.chip[for="ovf-{k}"]{{{chip_on}}}'
        for k in ("all", "decl", "viol", "off")
    ]
    rules += [
        "#ovf-off:checked ~ .split .box{display:none}",
        "#ovf-viol:checked ~ .split .box.line,#ovf-viol:checked ~ .split .box.decl{display:none}",
        "#ovf-decl:checked ~ .split .box.line{display:none}",
        ".ov{display:none}",
        "#fr-0:checked ~ .split .ov{display:block}",
    ]
    for i in range(len(images)):
        rules.append(f"#fr-{i}:checked ~ .split .frame img[data-i='{i}']{{display:block}}")
        rules.append(f"#fr-{i}:checked ~ .split .frame img:not([data-i='{i}']){{display:none}}")
        rules.append(f"#fr-{i}:checked ~ .split label.shot[for='fr-{i}']"
                     "{border-color:rgba(109,107,246,.8);box-shadow:0 0 0 2px rgba(109,107,246,.3)}")
    for i in range(len(boxes)):
        rules.append(
            f'.lx:has([data-b="{i}"]:hover) .box[data-b="{i}"]'
            "{display:block !important;opacity:1;background:rgba(109,107,246,.32);border-color:#c7c6ff;"
            "border-width:2px;box-shadow:0 0 0 3px rgba(109,107,246,.5),0 0 30px rgba(109,107,246,.75);z-index:9}"
            f'.lx:has([data-b="{i}"]:hover) .box[data-b="{i}"] .bl{{opacity:1}}'
        )
    rules.append(".box:target{display:block !important}")

    switches = h(*[
        f'<input class="lxf" type="radio" name="lxovf" id="ovf-{k}"{" checked" if k == default_filter else ""}/>'
        for k in ("all", "decl", "viol", "off")
    ]) + h(*[
        f'<input class="lxf" type="radio" name="lxfr" id="fr-{i}"{" checked" if i == 0 else ""}/>'
        for i in range(len(images))
    ])

    notices = ""
    if result.gemini_error:
        notices = h(
            '<div class="note bad rise"><span>&#9888;</span><div><b>Multimodal perception unavailable.</b> ',
            f'Screening fell back to local <code>{e(ocr.engine_used)}</code>. ',
            f'Root cause: <code>{e(result.gemini_error)}</code></div></div>',
        )

    paint(h(
        f"<style>{''.join(rules)}</style>",
        '<div class="lx">',
        switches,
        command_bar(engine_label, inspection_id, package_name, ocr.engine_used == "GEMINI_MULTIMODAL"),
        rail(), notices, deck(),
        f'<div class="split"><div class="col">{viewer()}{log_panel()}</div>',
        f'<div class="col">{decl_panel()}{meter_panel()}</div></div>',
        findings(), folds(),
        '</div>',
    ))


# =============================================================================
# Render
# =============================================================================
result = st.session_state.get("inspection_result")
pipeline = st.session_state.get("pipeline")

if result is not None and image_bytes is not None:
    if result.gemini_error:
        st.session_state["gemini_error"] = result.gemini_error

    inspection_id = storage_repo.save_inspection(result, image_name=image_label_name)

    display_images = st.session_state.get("image_bytes_list", [image_bytes])
    display_names = st.session_state.get("image_file_names", [image_label_name])

    render_console(
        result, pipeline, inspection_id, image_label_name,
        [data_uri(b) for b in display_images], display_names,
    )

    # ---- export dossier ----------------------------------------------------
    report = ReportGenerator().generate_text_report(inspection_id, result, image_label_name)
    sb('<div class="sbl">Export dossier</div>')
    pdf_bytes = build_pdf_report(result, audit_id=inspection_id)
    st.sidebar.download_button(
        label="📄  Screening dossier (.pdf)",
        data=bytes(pdf_bytes),
        file_name=f"LabelX_Inspection_{inspection_id[:8]}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
    st.sidebar.download_button(
        label="📥  Statutory notice (.txt)",
        data=report.report_text,
        file_name=f"Notice_{inspection_id[:8]}.txt",
        mime="text/plain",
        use_container_width=True,
    )
    sb(
        f'<div class="sbf"><b>Audit ID</b><br/><span class="id">{e(inspection_id)}</span><br/><br/>'
        "Preliminary administrative screening only. Statutory determinations and compounding notices "
        "remain subject to physical verification by an authorised Legal Metrology Inspector.</div>"
    )
else:
    standby(
        "Select a benchmark package or upload label photography from the control console "
        "to begin statutory screening."
    )
