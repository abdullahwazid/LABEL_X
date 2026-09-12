# Architecture Design Document: LABEL-X

## 1. System Overview & Core Design Philosophy

LABEL-X is architected around a non-negotiable architectural invariant:
**Strict Decoupling of Probabilistic Perception from Deterministic Regulatory Verification.**

In regulatory compliance screening, models that combine image perception and legal interpretation into an end-to-end black box (e.g., prompting a multimodal LLM to decide "Is this package legal?") are unacceptable for the following reasons:
1. **Hallucination Risk**: Large generative models frequently hallucinate legal standards or misread fractional numbers.
2. **Lack of Verifiability**: Regulators and legal departments require statutory citations and mathematical determinism, not probabilistic prose.
3. **Auditability**: If a package is cited for a non-compliance penalty, the decision must withstand judicial scrutiny with a verifiable chain of custody from pixel coordinates to statutory clause.

Therefore, LABEL-X enforces a clear **Perception-Verification Boundary**:
- **Perception Pipeline (CV / OCR / Extraction)**: Converts raw, unstructured 2D pixels into structured semantic candidate objects with associated spatial coordinates and confidence scores. This phase is probabilistic and fallible.
- **Verification Core (Rule Engine)**: Pure, zero-side-effect, deterministic Python rule functions that evaluate strongly-typed Pydantic schemas against statutory constraints. Given identical structured inputs, the rule engine **always** produces the exact same boolean outcome and citation trail.

---

## 2. High-Level Architecture

```
[Raw Package Image]
        |
        v
+-------------------------------------------------------------+
| LAYER 1: Image Quality Assessment & Preprocessing            |
| (OpenCV Headless: Blur, Glare, Skew, Resolution)            |
+-------------------------------------------------------------+
        |
        | Preprocessed Image + Quality Assessment
        v
+-------------------------------------------------------------+
| LAYER 2: Optical Character Recognition (OCR) Engine          |
| (PyTesseract: Word/Line Tokenization, Bounding Boxes, Conf) |
+-------------------------------------------------------------+
        |
        | OCR Tokens + Bounding Boxes + Confidence Scores
        v
+-------------------------------------------------------------+
| LAYER 3: Entity Extraction & Structured Field Parsing        |
| (Regex, Spatial Layout Heuristics, Pattern Analyzers)        |
+-------------------------------------------------------------+
        |
        | Raw Extracted Entities
        v
===============================================================
==== PERCEPTION / VERIFICATION BOUNDARY (Canonical Schema) ====
===============================================================
        |
        | Strongly-Typed Pydantic Regulatory Input Models
        v
+-------------------------------------------------------------+
| LAYER 4: Deterministic Compliance Rule Engine                |
| (Pure Python: Metric Units, MRP Format, USP Math, Dates)     |
+-------------------------------------------------------------+
        |
        | Rule Execution Verdicts + Statutory Citations
        v
+-------------------------------------------------------------+
| LAYER 5: Evidence Synthesizer & Decision Engine              |
| (3-State Output: NO_OBVIOUS_ISSUE / NEEDS_REVIEW / VIOLATION)|
+-------------------------------------------------------------+
        |
        | Auditable Compliance Dossier (JSON)
        v
+-------------------------------------------------------------+
| LAYER 6: Persistence & Presentation (Streamlit / API)        |
| (Visual Bounding Box Overlay, Inspector Review, CSV/JSON)    |
+-------------------------------------------------------------+
```

---

## 3. Detailed Component Breakdown

### 3.1 `src/image_quality/` (Image Quality Gate)
- **Role**: Determine if an uploaded image has sufficient perceptual fidelity to be reliably processed by the OCR engine.
- **Key Metrics**:
  - *Sharpness / Focus*: Variance of the Laplacian ($\sigma^2_{\text{Laplacian}}$). If below threshold, image is flagged as blurry.
  - *Illumination & Specular Glare*: Histograms for over-exposure saturation and deep shadows.
  - *Resolution & Aspect Ratio*: Validates DPI adequacy and pixel dimensions for text legibility.
- **Behavior**: If the image fails critical quality thresholds, the pipeline does not guess; it immediately emits `NEEDS_REVIEW` with an `ImageQualityWarning`.

### 3.2 `src/ocr/` (Optical Character Recognition)
- **Role**: Execute OCR extraction using lightweight, CPU-compatible engines (`pytesseract` / Tesseract OCR).
- **Output Structure**: Emits a token stream where every token has:
  - `text`: Extracted string.
  - `bbox`: Absolute pixel coordinates `(x, y, w, h)`.
  - `confidence`: Confidence score from $0.0$ to $100.0$.
  - `line_num`, `block_num`: Hierarchical spatial layout markers.

### 3.3 `src/extraction/` (Entity & Field Extraction)
- **Role**: Transform noisy OCR tokens into candidate regulatory fields:
  - `net_quantity`: Quantity magnitude, unit symbol, multi-pack indicators.
  - `mrp`: Currency symbol, numeric value, tax qualifier ("incl. of all taxes").
  - `unit_sale_price`: Declared unit price, unit denominator.
  - `dates`: Month and year of manufacture/packing/import.
  - `consumer_care`: Phone, email, postal address, designation.
  - `manufacturer_details`: Manufacturer/packer names, addresses, pin codes.
- **Confidence Computation**: Extracts aggregate confidence based on constituent OCR token scores and regex match fidelity.

### 3.4 `src/regulatory/` (Canonical Data Contracts)
- **Role**: Houses immutable Pydantic models serving as the contract between perception and deterministic verification.
- **Core Entities**:
  - `ScannedLabelData`: Normalized representation of all parsed fields.
  - `QuantityDeclaration`: Structured representation of numerical quantity and unit.
  - `PriceDeclaration`: MRP, currency, tax clause status.
  - `UnitSalePriceDeclaration`: Declared USP value, denominator unit, verified match.
  - `DateDeclaration`: Month, year, date type (mfg, packed, import).
  - `ConsumerCareDeclaration`: Contact channels and validity flags.

### 3.5 `src/rules/` (Deterministic Rule Engine)
- **Role**: Collection of pure Python functions implementing statutory constraints.
- **Rule Signature**:
  ```python
  def verify_rule_xxx(label_data: ScannedLabelData) -> RuleResult:
      ...
  ```
- **Key Rule Sets**:
  - `rule_net_quantity_units`: Enforces standard SI symbols (`g`, `kg`, `ml`, `l`, `m`, `cm`, `N`, `U`). Explicitly rejects `gms`, `Kgs`, `ML`, etc.
  - `rule_mrp_tax_inclusive`: Enforces presence of `"inclusive of all taxes"` or statutory abbreviations.
  - `rule_unit_sale_price_presence`: Verifies presence of USP for packages subject to GSR 779(E).
  - `rule_unit_sale_price_math`: Checks mathematical consistency: $|USP_{\text{declared}} - (MRP / NetQty)| \le \epsilon$.
  - `rule_date_validity`: Validates month/year formatting and rejects impossible future dates.
  - `rule_consumer_care_completeness`: Validates presence of at least phone/email + postal address.

### 3.6 `src/evidence/` (Evidence & Audit Binding)
- **Role**: Binds visual bounding boxes, cropped image patches, raw OCR snippets, and rule evaluation traces into a tamper-evident audit record.
- **Data Integrity**: Computes cryptographic checksums (SHA-256) of input images and rule configurations to ensure complete audit reproducibility.

### 3.7 `src/decisions/` (Decision Synthesizer)
- **Role**: Aggregates individual `RuleResult` outputs and image quality scores to produce the top-level Three-State Verdict:
  - `NO_OBVIOUS_ISSUE`: All mandatory rules passed; OCR confidence $\ge \tau_{\text{conf}}$; Image quality acceptable.
  - `NEEDS_REVIEW`: Image degraded, low OCR confidence, ambiguous field formatting, or missing field on partial-panel capture.
  - `POTENTIAL_NON_COMPLIANCE`: At least one deterministic statutory rule returned a failure verdict.

### 3.8 `src/storage/` (Session & Persistence Layer)
- **Role**: Lightweight local persistence for screening results, run sessions, and audit exports (JSON / CSV). Zero external database dependency required for single-node CPU operation.

---

## 4. Architectural Invariants & Constraints

1. **CPU Execution Only**: All algorithms, image transforms, and regex pipelines must run efficiently on standard x86_64 CPU cores without requiring CUDA or GPU acceleration.
2. **Stateless Rule Verification**: Rules cannot depend on external API lookups or stateful databases; all decisions are pure functions of the provided input data.
3. **No Silent Failures**: If OCR fails or an image is too blurry, the system must not emit a false pass; it must explicitly degrade to `NEEDS_REVIEW`.
4. **Traceable Citations**: Every non-compliance finding must provide the statutory rule number (e.g., `Rule 6(1)(c)`, `GSR 779(E)`), the exact offending text, and bounding box coordinates.
