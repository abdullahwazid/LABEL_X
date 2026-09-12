# Regulatory Sources & Statutory Mapping

## 1. Primary Statutory Authorities

LABEL-X is codified against the legislative and regulatory framework governing weights, measures, packaging, and consumer disclosures in the Republic of India:

1. **The Legal Metrology Act, 2009 (Act No. 1 of 2010)**
   - Enacted by the Parliament of India to establish and enforce standards of weights and measures, regulate trade and commerce in weights, measures and other goods which are sold or distributed by weight, measure or number.
   - **Section 18**: Prohibits the manufacture, pack, sell, import, distribute, deliver, offer, expose or possess for sale any pre-packaged commodity unless such package is in such standard quantities or number and bears thereon such declarations and particulars in such manner as may be prescribed.
   - **Section 36**: Prescribes penalties for manufacturing, packing, or selling non-standard or improperly declared pre-packaged commodities.

2. **The Legal Metrology (Packaged Commodities) Rules, 2011 (LMPC Rules, 2011)**
   - Notified vide G.S.R. 202(E) dated 7th March 2011, effective 1st April 2011 (as amended periodically).
   - Governs the mandatory declarations, placement, principal display panels, font size proportionality, permissible errors, and exemptions for all pre-packaged commodities.

3. **G.S.R. 492(E) (The Legal Metrology (Packaged Commodities) Amendment Rules, 2022)**
   - Notified by the Department of Consumer Affairs, Ministry of Consumer Affairs, Food and Public Distribution on 14th July 2022 (and subsequent operational notifications).
   - Modernized packaging rules for e-commerce platforms, standardized declaration prominence, updated multi-piece package declarations, and refined consumer care contact requirements.

4. **G.S.R. 779(E) (The Legal Metrology (Packaged Commodities) Second Amendment Rules, 2021)**
   - Notified on 2nd November 2021 (with phased enforcement through 2022/2023).
   - Mandated the declaration of the **Unit Sale Price (USP)** across pre-packaged commodities to enhance price transparency for consumers.

---

## 2. Rule-by-Rule Regulatory Mapping

| Rule Citation | Statutory Requirement | Statutory Constraint / Enforced Pattern | LabelX Rule Identifier |
| :--- | :--- | :--- | :--- |
| **Rule 6(1)(a)** | Name and address of Manufacturer, Packer, or Importer | Name and complete address including city, state, postal code (PIN code). Must specify capacity (e.g., "Mfg by", "Packed by", "Imported by"). | `RULE_MFR_IDENTITY` |
| **Rule 6(1)(b)** | Generic or Common Name | Common or generic name of commodity must appear prominently on Principal Display Panel. | `RULE_GENERIC_NAME` |
| **Rule 6(1)(c)** | Net Quantity Declaration | Expressed in standard metric units: mass (`g`, `kg`), volume (`ml`, `l`/`L`), length (`m`, `cm`), or number (`N`, `U`). Symbols must follow Second Schedule exactly. Prohibited: `gms`, `gm`, `g.m.`, `Kgs`, `ML`, `ltrs`, `pcs`. | `RULE_NET_QTY_UNITS` |
| **Rule 6(1)(d)** | Month and Year of Manufacture / Packing / Import | Format must be `MM/YYYY`, `MM/YY`, or month in words followed by year. Cannot be a future date beyond permitted packaging cycle. | `RULE_MFG_DATE_VALIDITY` |
| **Rule 6(1)(da)** | Maximum Retail Price (MRP) | Must state retail sale price as: `MRP Rs. X.XX (incl. of all taxes)` or `MRP ₹ X.XX incl. of all taxes`. Tax-inclusive clause is compulsory. | `RULE_MRP_TAX_INCLUSIVE` |
| **Rule 6(10) / GSR 779(E)** | Unit Sale Price (USP) | Mandatory when quantity is not equal to reference unit:<br>• $< 1\text{ kg} \implies \text{Rs. per g}$<br>• $> 1\text{ kg} \implies \text{Rs. per kg}$<br>• $< 1\text{ L} \implies \text{Rs. per ml}$<br>• $> 1\text{ L} \implies \text{Rs. per L}$<br>• By number $\implies \text{Rs. per N / piece}$. Rounded to 2 decimal places. | `RULE_USP_PRESENCE`<br>`RULE_USP_MATH_PARITY` |
| **Rule 6(1)(e)** | Consumer Care Details | Name, address, telephone number, and email address of person/office to contact for consumer grievances. | `RULE_CONSUMER_CARE` |
| **Rule 6(1)(b) Proviso** | Country of Origin | For imported packages, country of origin/manufacture must be stated explicitly. | `RULE_COUNTRY_OF_ORIGIN` |
| **Rule 7** | Units of Weight, Measure, or Number | Only units specified in the Second Schedule shall be used. Non-standard prefixes or suffixes violate statutory standards. | `RULE_STANDARD_SI_UNITS` |
| **Rule 9** | Manner of Declaration | Minimum font height based on area of principal display panel (requires calibrated reference metrics; see Known Limitations). | `RULE_FONT_METRICS` (Advisory) |

---

## 3. Second Schedule: Standard Units of Weight and Measure

Under the Second Schedule to the Legal Metrology (Packaged Commodities) Rules, 2011:

### Mass / Weight
- **Gram**: Symbol `g` (lowercase only). The symbols `gm`, `gms`, `g.`, `Gms` are illegal.
- **Kilogram**: Symbol `kg` (lowercase only). The symbols `Kg`, `KG`, `Kgs`, `kilog.` are illegal.
- **Milligram**: Symbol `mg`.

### Volume / Liquid Measure
- **Milliliter**: Symbol `ml` or `mL`.
- **Liter**: Symbol `l` or `L`. The abbreviations `ltr`, `ltrs`, `Lit.` are illegal.

### Number / Units
- **Number**: Symbol `N` or `U` (e.g., `10 N` or `10 U`). Symbols like `pcs`, `pieces`, `units`, `items` are non-standard under strict metrology definitions.

---

## 4. GSR 779(E) Unit Sale Price (USP) Mathematical Reference

Under GSR 779(E), the Unit Sale Price must be calculated strictly according to:

$$\text{USP} = \frac{\text{Maximum Retail Price}}{\text{Net Quantity in Standard Base Units}}$$

Where base units are defined as:
- Mass $< 1000\text{ g}$: Declared per $1\text{ g}$.
- Mass $\ge 1000\text{ g}$: Declared per $1\text{ kg}$.
- Volume $< 1000\text{ ml}$: Declared per $1\text{ ml}$.
- Volume $\ge 1000\text{ ml}$: Declared per $1\text{ L}$.
- Items $< 1\text{ piece}$: Declared per piece (`/ N`).

**Permissible Tolerance**:
Mathematical rounding differences are accepted up to $\pm 1$ Paisa ($\pm 0.01$ INR) due to half-up decimal rounding. Any larger discrepancy constitutes a pricing misstatement violation.
