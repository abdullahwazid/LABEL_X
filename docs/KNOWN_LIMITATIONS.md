# Known Technical & Regulatory Limitations

## 1. Physical Metric Limitations (2D Photographs vs Physical Objects)

### 1.1 Inability to Certify Physical Font Size in Millimeters
- **Statutory Context**: Rule 9 and the First Schedule of the Legal Metrology (Packaged Commodities) Rules, 2011 specify minimum font heights in millimeters (e.g., $1.0\text{ mm}$, $1.5\text{ mm}$, $2.0\text{ mm}$, $3.0\text{ mm}$, $4.0\text{ mm}$) depending on the net quantity and the surface area of the Principal Display Panel (PDP).
- **Technical Barrier**: In an arbitrary 2D photograph taken from an uncalibrated smartphone camera, webcam, or flatbed scan, there is **no intrinsic physical scale**:
  - Pixel dimensions $(w \times h)$ do not translate into physical millimeters ($\text{mm}$) without known camera sensor metrics, optical focal distance, and image resolution (DPI).
  - Perspective distortions, skew, and digital zoom dynamically alter the apparent pixel height of text characters.
- **System Constraint**:
  - LABEL-X **cannot and does not** certify compliance with physical font height requirements in millimeters from standard 2D photographs lacking a calibrated fiducial marker (e.g., a millimeter reference scale or ArUco tag photographed co-planar with the label).
  - Any font height checks performed without reference metrics are strictly relative or advisory.

### 1.2 Surface Area & Principal Display Panel (PDP) Ratio
- Calculating the exact percentage of surface area occupied by declarations requires the total 3D package surface area. Single-plane photos cannot determine the full surface area of bottles, cartons, or pouches.

---

## 2. Regulatory & Legal Disclaimer

### 2.1 Preliminary Automated Screening Only
- **Non-Judicial Nature**: LABEL-X is a technical quality control, risk triage, and compliance assistance tool. **Its screening outputs, confidence scores, and verdicts do not constitute legal advice, official statutory certificates, or judicial determination of compliance.**
- **Enforcement Authority**: The legal authority to issue notices, seize non-compliant goods, or initiate compounding / prosecution under the Legal Metrology Act, 2009 rests exclusively with statutory Legal Metrology Inspectors and authorized regulatory magistrates.
- **Human-in-the-Loop Obligation**: Any flag marked as `POTENTIAL_NON_COMPLIANCE` or `NEEDS_REVIEW` must be reviewed and verified by a qualified human compliance officer before taking punitive, commercial, or legal action against a vendor, manufacturer, or distributor.

---

## 3. Optical & Perceptual Limitations

### 3.1 Single-Panel Capture vs Multi-Panel Packaging
- Pre-packaged commodities frequently distribute mandatory declarations across multiple surfaces (e.g., brand and net quantity on the front panel; manufacturer, MRP, and consumer care on the back or side panel).
- If a user uploads only one image (e.g., front panel), missing fields like "Consumer Care" or "Manufacturer Address" **must not** be marked as a statutory violation (`POTENTIAL_NON_COMPLIANCE`). Instead, the system must emit `NEEDS_REVIEW` to prompt the operator to supply remaining package surfaces.

### 3.2 Specular Reflection, Foil Stamping, and Laminates
- Metallized films, holographic security seals, and high-gloss plastic wrappers frequently produce blinding specular glare under direct lighting.
- Glare can completely wash out text tokens (e.g., MRP numbers stamped on metallic surfaces), leading to OCR dropouts. Such instances trigger `NEEDS_REVIEW` with an image quality alert.

### 3.3 Cylindrical & Curved Surface Distortion
- Labels applied to bottles, cans, and tubes exhibit non-linear cylindrical projection distortion.
- Text towards the lateral horizons of the cylinder suffers perspective foreshortening, reducing OCR confidence and spatial character segmentation accuracy.

### 3.4 Multi-Lingual & Vernacular Declarations
- While English and Hindi (in Devanagari script) are primary languages under LMPC rules, regional distribution labels may contain text in other Indian languages (Tamil, Telugu, Bengali, Marathi, etc.).
- Default OCR models configured for Latin/English script may fail to parse vernacular declarations, requiring language-specific OCR pipelines.

---

## 4. Summary Matrix of Automated Capabilities

| Requirement | Automated Capability | Operational Status |
| :--- | :--- | :--- |
| **Unit Symbol Syntax** (`g`, `kg`, `ml` vs `gms`) | Exact Regex & AST Match | Fully Automated & Deterministic |
| **MRP Tax Qualification** (`incl. of all taxes`) | Exact Phrase & Regex Match | Fully Automated & Deterministic |
| **Unit Sale Price (USP) Math Parity** | Arithmetic Verification ($MRP / Qty$) | Fully Automated & Deterministic |
| **Mandatory Field Presence (Multi-panel)** | Token Extraction & Completeness Check | Triage to `NEEDS_REVIEW` if incomplete |
| **Physical Font Height ($\text{mm}$)** | Metric scaling from uncalibrated 2D photo | **Unsupported without Physical Scale** |
| **Principal Display Panel % Area** | 3D package surface calculation | **Unsupported from Single 2D Photo** |
| **Judicial Certification** | Legal immunity or enforcement order | **Explicitly Out of Scope** |
