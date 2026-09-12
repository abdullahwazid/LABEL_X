# 🛡️ LABEL-X — AI-Assisted Compliance Screening for Packaged Commodities

### Built for Smart India Hackathon (SIH 2026)
**Enforcing India's Legal Metrology (Packaged Commodities) Rules, 2011 • Department of Consumer Affairs**

---

## 📖 Overview

**LABEL-X** is an automated visual and statutory compliance screening system built to audit consumer product packaging against the statutory requirements of the **Legal Metrology Act, 2009** and the **Legal Metrology (Packaged Commodities) Rules, 2011** (as amended by G.S.R. 492(E) and G.S.R. 779(E)).

LABEL-X enforces a strict architectural boundary separating **probabilistic computer vision perception** from **deterministic statutory verification**, ensuring zero hallucination in legal adjudication and establishing an immutable, cryptographically verifiable evidentiary audit trail.

---

## ⚡ Core Features

1. **Optical Quality Gating (OpenCV Headless)**
   - High-precision blur detection using Laplacian operator variance ($\sigma^2_{\text{Laplacian}} \ge 80.0$).
   - Specular glare and overexposure saturation measurement ($\text{glare ratio} \le 5.0\%$).
   - Automatic rejection of unreadable, corrupted, or degraded images before downstream OCR.

2. **Spatial Text Perception & Entity Extraction**
   - Line-level text extraction and bounding box coordinate mapping `(x1, y1, x2, y2)`.
   - Confidence scoring ($0.0\text{--}1.0$) with seamless fallback mechanism for environments without local Tesseract binaries.
   - Structured parsing of mandatory packaging declarations: Maximum Retail Price (MRP), Net Quantity, Unit Sale Price (USP), Manufacturing/Packing Dates, and Consumer Care contact channels.

3. **Deterministic Statutory Rule Engine**
   - **Rule 6(1)(e)**: Compulsory Maximum Retail Price declaration with mandatory `"inclusive of all taxes"` statement.
   - **Rule 13 & Second Schedule**: Strict enforcement of standard SI metric unit symbols (`g`, `kg`, `ml`, `l`, `N`, `U`); outlaws non-standard abbreviations (`gms`, `gm`, `kilos`, `kgs`, `mls`, `nos`, `pcs`).
   - **Rule 6(11) / G.S.R. 779(E)**: Unit Sale Price (USP) mandate and arithmetic parity check ($|USP - (MRP / Qty)| \le 2\%$).
   - **Rule 6(1)(d)**: Manufacturing and packing month/year validation.
   - **Rule 6(2)**: Consumer grievance redressal helpline telephone and email validation.
   - **Rule 26**: Small-package statutory exemption logic ($\le 10\text{ g}$ or $\le 10\text{ ml}$).
   - **Rule 7**: Advisory font height and display area proportionality reporting.

4. **Three-State Compliance Adjudication**
   - `NO_OBVIOUS_ISSUE`: 100% statutory rule satisfaction with high optical clarity.
   - `NEEDS_REVIEW`: Optical degradation, low OCR confidence ($< 70\%$), or advisory requirements requiring human inspector sign-off.
   - `POTENTIAL_NON_COMPLIANCE`: Conclusive statutory violation detected (`CRITICAL` or `MAJOR`).

5. **Cryptographic Visual Evidence Dossier**
   - Padded image crops extracted for every detected statutory infraction.
   - Cryptographic SHA-256 hash generated for each crop to preserve tamper-evident chain of custody.

6. **Local SQLite Persistence & Statutory Notice Export**
   - Automatic local audit logging in SQLite (`data/inspections.db`).
   - Real-time download of official Statutory Screening Notices (`.txt`) for compounding documentation.

---

## 🏛️ System Architecture

```
[Package Photo Payload]
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Image Quality Gating (Sharpness, Glare, Resolution)      │
└─────────────────────────────────────────────────────────────┘
         │  (Preprocessed Image Array + Quality Metrics)
         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Optical Character Recognition (Tokens, BBoxes, Conf)     │
└─────────────────────────────────────────────────────────────┘
         │  (OCR Lines + Spatial Geometry)
         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Structured Declaration Parsing (MRP, Qty, USP, Dates)    │
└─────────────────────────────────────────────────────────────┘
         │  (Normalized Pydantic Contracts)
═════════╪═════════════════════════════════════════════════════
         │  PERCEPTION / DETERMINISTIC VERIFICATION BOUNDARY
═════════╪═════════════════════════════════════════════════════
         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Deterministic Legal Metrology Rule Engine (Rules 6,13,26)│
└─────────────────────────────────────────────────────────────┘
         │  (Rule Outcomes + Statutory Citations)
         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Visual Evidence Generator (SHA-256 Hashed Crops)         │
└─────────────────────────────────────────────────────────────┘
         │  (Evidence Dossier + Rule Results)
         ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Three-State Decision Arbiter                             │
│    [ NO_OBVIOUS_ISSUE | NEEDS_REVIEW | NON_COMPLIANCE ]     │
└─────────────────────────────────────────────────────────────┘
         │
         ├──────────────────────────────┐
         ▼                              ▼
┌─────────────────────────────┐  ┌────────────────────────────┐
│ Streamlit Visual Dashboard  │  │ SQLite Audit DB & Notices  │
└─────────────────────────────┘  └────────────────────────────┘
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.14)
- Pip

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/your-org/LABEL-X.git
cd LABEL-X

# Install dependencies (CPU-only wheels)
pip install -r requirements.txt
```

### 3. Generate Benchmark Sample Assets
```bash
python -m src.mock_generator
```
This generates three standard packaging fixtures in `data/samples/`:
- `sample_compliant.png` (Fully compliant packaging)
- `sample_violation_units.png` (Infraction: `"500 gms"`)
- `sample_violation_mrp.png` (Infraction: Missing tax statement on MRP)

### 4. Running the Test Suite
Execute the comprehensive automated test suite (65+ test cases covering quality, perception, extraction, rules, arbitration, persistence, and production hardening):
```bash
pytest -v
```

### 5. Launch the Streamlit Dashboard
```bash
python -m streamlit run app.py
```
Open your browser and navigate to:
```
http://localhost:8501
```

---

## 📁 Repository Scaffolding

```
E:/LabelX/
├── app.py                     # Streamlit Operator Dashboard
├── requirements.txt           # Minimal CPU-only dependencies
├── pyproject.toml             # Pytest configuration
├── README.md                  # System documentation & quickstart
├── data/
│   ├── samples/               # Benchmark packaging image samples
│   └── inspections.db         # SQLite local audit database
├── docs/
│   ├── ARCHITECTURE.md        # Detailed pipeline architecture design
│   ├── KNOWN_LIMITATIONS.md   # Optical & physical metric boundaries
│   ├── REGULATORY_SOURCES.md  # Statutory law & gazette notification citations
│   └── REQUIREMENTS.md        # Three-state model & functional specs
├── src/
│   ├── pipeline.py            # End-to-end compliance screening orchestrator
│   ├── mock_generator.py      # Synthetic benchmark sample generator
│   ├── image_quality/         # OpenCV blur, glare, and resolution gating
│   ├── ocr/                   # Spatial text perception & bounding box extraction
│   ├── extraction/            # Structured regulatory field extraction
│   ├── regulatory/            # Codified statutory knowledge base (LMPC Rules)
│   ├── rules/                 # Pure deterministic compliance rule engine
│   ├── evidence/              # Visual image crop extraction & SHA-256 digests
│   ├── decisions/             # Three-state decision arbitration engine
│   ├── storage/               # SQLite persistence repository
│   └── reports/               # Statutory notice and report generator
└── tests/
    ├── test_scaffold.py
    ├── test_image_quality.py
    ├── test_ocr.py
    ├── test_extraction.py
    ├── test_regulatory.py
    ├── test_rules.py
    ├── test_decisions_and_evidence.py
    ├── test_pipeline.py
    ├── test_storage.py
    ├── test_reports.py
    └── test_hardening.py
```

---

## ⚖️ Statutory & Regulatory Disclaimer

**PRELIMINARY ADMINISTRATIVE TRIAGE TOOL ONLY.**  
LABEL-X is an automated screening and evidentiary compilation tool designed to assist regulatory enforcement officers, e-commerce compliance teams, and quality assurance personnel.

1. **Non-Judicial Authority**: Screening verdicts, confidence scores, and advisory notices generated by LABEL-X do **not** constitute legal advice, judicial determinations, or statutory compounding orders under Section 36 of the Legal Metrology Act, 2009.
2. **Physical Metric Limitation**: In accordance with optical physics, 2D uncalibrated photographs cannot certify physical character dimensions in millimeters without a co-planar metric reference scale.
3. **Human-in-the-Loop Requirement**: All flagged non-compliances and review notices must be physically verified by an authorized Legal Metrology Inspector prior to issuing formal legal notices or seizing goods.
