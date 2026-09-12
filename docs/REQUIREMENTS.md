# Functional Requirements Specification: LABEL-X

## 1. Executive Summary & Purpose

LABEL-X is an automated visual and textual compliance screening system designed for pre-packaged commodities marketed and distributed in India. Its purpose is to assist regulatory compliance officers, quality assurance teams, brand owners, and e-commerce platforms in screening product package labels against the statutory requirements of the **Legal Metrology Act, 2009** and the **Legal Metrology (Packaged Commodities) Rules, 2011** (as amended, including GSR 492(E) and GSR 779(E)).

LABEL-X functions strictly as a **preliminary compliance screening and triage tool**. It detects potential statutory non-compliances, highlights missing or malformed declarations, flags OCR ambiguities, and produces an auditable evidentiary dossier for human review.

---

## 2. Statutory Scope & Mandated Declarations

Under Rule 6 of the Legal Metrology (Packaged Commodities) Rules, 2011, every package containing pre-packed commodities must bear conspicuous, legible, and definite declarations on the principal display panel (or designated label panels).

LABEL-X screens for the following primary statutory declarations:

### 2.1 Manufacturer / Packer / Importer Identity & Address (Rule 6(1)(a))
- **Requirement**: The name and complete address of the manufacturer, or where manufacturer is not the packer, the name and address of the manufacturer and packer. For imported goods, the name and complete address of the importer.
- **Verification Criteria**:
  - Presence of entity identification prefix (e.g., "Mfg by", "Manufactured by", "Packed by", "Imported & Marketed by").
  - Verification of complete geographic indicators (Pin Code / State / Country).

### 2.2 Generic / Common Name of Commodity (Rule 6(1)(b))
- **Requirement**: The common or generic name of the commodity contained in the package.
- **Verification Criteria**:
  - Clear identification distinct from the trademark/brand name.
  - Absence of misleading or ambiguous commodity classification.

### 2.3 Net Quantity Declaration (Rule 6(1)(c) & Rule 7)
- **Requirement**: Net quantity in terms of standard units of weight, measure, or number (in accordance with the metric system).
- **Verification Criteria**:
  - Use of standard SI symbols only: `g`, `kg`, `ml`, `l` (or `L`), `m`, `cm`, `N`, `U`.
  - Non-standard symbols (e.g., "gms", "gm", "g.", "Kgs", "ML", "ltrs", "pcs") constitute explicit statutory violations.
  - Space between number and unit (e.g., `500 g`, not `500g` where standard formatting applies).
  - Multi-piece and combo-pack quantity breakdowns where applicable.

### 2.4 Month and Year of Manufacture / Packing / Import (Rule 6(1)(d))
- **Requirement**: The month and year in which the commodity is manufactured, pre-packed, or imported.
- **Verification Criteria**:
  - Acceptable formats: `MM/YYYY`, `MM/YY`, `Month Year` (e.g., `09/2026`, `Sep 2026`).
  - Clear attribution ("Mfg Date", "Packed On", "Imported On").
  - Date sanity verification (cannot be post-dated into the future beyond permissible tolerances).

### 2.5 Maximum Retail Price (MRP) (Rule 6(1)(da))
- **Requirement**: The retail sale price of the package stated as Maximum Retail Price (MRP) inclusive of all taxes.
- **Verification Criteria**:
  - Acceptable prefix: `MRP Rs.` or `MRP ₹` or `Maximum Retail Price Rs.` / `₹`.
  - Compulsory qualifier: `"incl. of all taxes"` or `"inclusive of all taxes"`.
  - Ambiguous currency symbols, absence of tax inclusion statement, or predatory alteration markers trigger non-compliance or review flags.

### 2.6 Unit Sale Price (USP) (Rule 6(10) & GSR 779(E))
- **Requirement**: Mandatory declaration of Unit Sale Price for commodities where net quantity is greater than or less than statutory standard units:
  - If package net weight is $< 1\text{ kg}$, USP declared per gram (`Rs. X / g`).
  - If package net weight is $> 1\text{ kg}$, USP declared per kilogram (`Rs. X / kg`).
  - If package net volume is $< 1\text{ L}$, USP declared per milliliter (`Rs. X / ml`).
  - If package net volume is $> 1\text{ L}$, USP declared per liter (`Rs. X / L`).
  - If package is sold by number/length, USP declared per piece (`Rs. X / N` or `Rs. X / unit`).
- **Verification Criteria**:
  - Computed unit price vs declared unit price mathematical parity check (rounded to 2 decimal places).
  - Formatting and unit denominator correctness.

### 2.7 Consumer Care Details (Rule 6(1)(e))
- **Requirement**: Name, address, telephone number, and email address of the person/office to contact in case of consumer complaints.
- **Verification Criteria**:
  - Presence of designated grievance officer / consumer care manager title.
  - Valid telephone / toll-free number format.
  - Valid RFC 5322 compliant email address format.
  - Physical postal address or reference to corporate registered office.

### 2.8 Country of Origin (Rule 6(1)(b) proviso)
- **Requirement**: Mandatory declaration of country of origin / manufacture for imported packages or e-commerce catalog visibility.
- **Verification Criteria**:
  - Explicit `"Country of Origin: <Country>"` or `"Made in <Country>"`.

---

## 3. Three-State Output Model

To ensure regulatory defensibility and avoid false accusations arising from imperfect computer vision or multi-panel occlusion, LABEL-X enforces a strict **Three-State Output Model**:

```
+---------------------------------------------------------------------------------+
|                               THREE-STATE VERDICT                               |
+--------------------------+------------------------------+-----------------------+
|    NO_OBVIOUS_ISSUE      |         NEEDS_REVIEW         | POTENTIAL_NON_COMPLIANCE|
+--------------------------+------------------------------+-----------------------+
| High confidence          | Ambiguous OCR / low contrast | Explicit statutory    |
| All required fields seen | Occluded / cropped text      | violation detected    |
| Rules strictly satisfied | Field missing on 1-panel pic | Prohibited unit symbol|
| Format validated         | Human adjudication required | Math mismatch in USP  |
+--------------------------+------------------------------+-----------------------+
```

### 3.1 `NO_OBVIOUS_ISSUE` (Green)
- **Definition**: Every mandatory statutory field required for the detected product class is present on the scanned label surface with high OCR extraction confidence ($\ge \tau_{\text{conf}}$).
- **Rule Engine Evaluation**: All deterministic regulatory validation rules passed with zero violations.
- **Legal Context**: Does not constitute a government certificate of immunity; indicates that within the scanned visual evidence, no violation of LMPC rules could be detected.

### 3.2 `NEEDS_REVIEW` (Amber)
- **Definition**: The automated pipeline cannot reach a definitive compliance verdict due to perceptual or evidentiary ambiguity.
- **Trigger Conditions**:
  - **Image Quality Degradation**: Blur metric (Laplacian variance $< \tau_{\text{blur}}$), excessive glare/reflection, extreme perspective skew, or low resolution.
  - **OCR Uncertainty**: OCR confidence score below operational threshold ($\text{conf} < \tau_{\text{conf}}$) on critical text tokens.
  - **Single-Panel Partial Evidence**: A mandatory field (such as Consumer Care or Manufacturer Address) is absent from the provided image, but the submitted image only covers a single panel of a multi-panel container (e.g., front of a cereal box or cylinder label).
  - **Borderline Parsing**: Text extracted contains ambiguous abbreviations or atypical phrasing that requires human legal/linguistic interpretation.
- **Action Required**: Escalated to a human reviewer with highlighted bounding boxes and confidence scores.

### 3.3 `POTENTIAL_NON_COMPLIANCE` (Red)
- **Definition**: The visual and textual evidence conclusively demonstrates an explicit violation of the statutory rules.
- **Trigger Conditions**:
  - **Prohibited Unit Symbol**: Extracted unit explicitly uses forbidden abbreviations such as `gms`, `gm`, `Kgs`, `ML`, `ltrs`, `g.m.s.` in violation of Rule 7 and the Second Schedule.
  - **Missing Tax Qualification on MRP**: Price declaration states `MRP Rs. 100` without declaring `"inclusive of all taxes"` or `"incl. of all taxes"`.
  - **USP Discrepancy**: Unit Sale Price is completely absent on packages where net quantity triggers mandatory USP under GSR 779(E), or declared USP contradicts calculated mathematical quotient $(MRP / NetQty)$.
  - **Future Post-Dating**: Declared manufacturing date is post-dated beyond legally permitted warehousing advance margins.
  - **Dual MRP / Predatory Overwriting**: Multiple conflicting MRP figures detected without an authorized statutory amendment sticker.
- **Action Required**: Generates an infraction audit dossier citing specific rule sections and coordinates of the offending label tokens.

---

## 4. Evidence Audit Trail & Defensibility

Every screening session must produce an immutable structured JSON dossier containing:
1. **Raw Artifact Hashes**: SHA-256 hash of original image and cropped bounding boxes.
2. **Quality Metrics**: Sharpness, brightness, resolution, and contrast scores.
3. **Perception Tokens**: Normalized text, bounding box coordinates $(x_1, y_1, x_2, y_2)$, and OCR engine confidence.
4. **Rule Execution Trace**: Explicit record of every rule evaluated, the input parameters passed, the deterministic boolean outcome, and statutory citations.
5. **Human Override Audit**: Capability for human reviewers to append notes, override verdicts, and sign off on compliance decisions.
