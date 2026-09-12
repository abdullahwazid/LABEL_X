"""Regulatory knowledge base housing statutory provisions of the LMPC Rules, 2011."""

from typing import Optional

from src.regulatory.models import RegulatoryProvision, ViolationSeverity


DEFAULT_PROVISIONS: list[RegulatoryProvision] = [
    RegulatoryProvision(
        provision_id="LMPC_R06_1_E",
        rule_reference="Rule 6(1)(e)",
        title="Maximum Retail Price (MRP) Declaration",
        requirement_text=(
            "The retail sale price of the package shall be clearly indicated as Maximum Retail "
            "Price (MRP) inclusive of all taxes. The phrase 'inclusive of all taxes' or statutory "
            "equivalent must be explicitly declared."
        ),
        effective_date="2011-03-01",
        severity=ViolationSeverity.CRITICAL,
        applicable_categories=["GENERAL_COMMODITY"],
    ),
    RegulatoryProvision(
        provision_id="LMPC_R13",
        rule_reference="Rule 13 read with Second Schedule",
        title="Standard Metric Units of Weight, Measure, or Number",
        requirement_text=(
            "Every declaration of net quantity shall be expressed in terms of standard units of "
            "weight, measure, or number specified in the Second Schedule. Symbols must strictly "
            "adhere to SI standards ('g', 'kg', 'ml', 'l', 'N', 'U'). Prohibited abbreviations "
            "include 'gms', 'gm', 'kilos', 'mls', 'nos', 'pcs'."
        ),
        effective_date="2011-03-01",
        severity=ViolationSeverity.CRITICAL,
        applicable_categories=["GENERAL_COMMODITY"],
    ),
    RegulatoryProvision(
        provision_id="LMPC_R06_11",
        rule_reference="Rule 6(11)",
        title="Unit Sale Price (USP) Declaration",
        requirement_text=(
            "Pre-packaged commodities shall declare the Unit Sale Price (USP) per gram/kilogram/"
            "milliliter/liter/piece when the net quantity is not equal to standard base units. "
            "Declared USP must mathematically match MRP divided by Net Quantity within permissible "
            "rounding tolerances."
        ),
        amendment_reference="G.S.R. 779(E)",
        effective_date="2022-12-01",
        severity=ViolationSeverity.MAJOR,
        applicable_categories=["GENERAL_COMMODITY"],
    ),
    RegulatoryProvision(
        provision_id="LMPC_R06_1_D",
        rule_reference="Rule 6(1)(d)",
        title="Month and Year of Manufacture or Pre-packing",
        requirement_text=(
            "Every package shall bear the month and year in which the commodity is manufactured, "
            "pre-packed, or imported. Format must clearly indicate month and year (e.g. MM/YYYY or "
            "Month Year) and cannot be post-dated into the future."
        ),
        effective_date="2011-03-01",
        severity=ViolationSeverity.CRITICAL,
        applicable_categories=["GENERAL_COMMODITY"],
    ),
    RegulatoryProvision(
        provision_id="LMPC_R06_2",
        rule_reference="Rule 6(2)",
        title="Consumer Care and Grievance Redressal Contact Details",
        requirement_text=(
            "Every package shall mention the name, address, telephone number, and email address of "
            "the person or office who can be contacted in case of consumer complaints or queries."
        ),
        effective_date="2011-03-01",
        severity=ViolationSeverity.MAJOR,
        applicable_categories=["GENERAL_COMMODITY"],
    ),
    RegulatoryProvision(
        provision_id="LMPC_R07",
        rule_reference="Rule 7",
        title="Minimum Font Height and Display Area Proportionality",
        requirement_text=(
            "The height of letters and numerals in mandatory declarations shall not be less than "
            "specified minimums based on the principal display panel area. Note: Due to 2D photograph "
            "optical constraints, this check is advisory and requires physical metric calibration."
        ),
        effective_date="2011-03-01",
        severity=ViolationSeverity.ADVISORY,
        applicable_categories=["GENERAL_COMMODITY"],
    ),
    RegulatoryProvision(
        provision_id="LMPC_R26",
        rule_reference="Rule 26",
        title="Exemption for Small Packages",
        requirement_text=(
            "Packages containing commodities weighing 10 g or less, or measuring 10 ml or less, are "
            "exempt from certain mandatory declarations under Rule 6, subject to the conditions "
            "specified in Rule 26."
        ),
        effective_date="2011-03-01",
        severity=ViolationSeverity.ADVISORY,
        applicable_categories=["GENERAL_COMMODITY", "SMALL_PACKAGE"],
    ),
]


class RegulatoryKnowledgeBase:
    """Registry and query interface for statutory Legal Metrology provisions."""

    def __init__(self, provisions: Optional[list[RegulatoryProvision]] = None) -> None:
        """Initializes the knowledge base with given or default provisions."""
        provision_list = provisions if provisions is not None else DEFAULT_PROVISIONS
        self._provisions_by_id: dict[str, RegulatoryProvision] = {
            p.provision_id: p for p in provision_list
        }

    def get_all_provisions(self) -> list[RegulatoryProvision]:
        """Returns all registered regulatory provisions."""
        return list(self._provisions_by_id.values())

    def get_provision_by_id(self, provision_id: str) -> Optional[RegulatoryProvision]:
        """Retrieves a specific statutory provision by its unique identifier."""
        return self._provisions_by_id.get(provision_id)

    def get_applicable_provisions(
        self, category: str = "GENERAL_COMMODITY"
    ) -> list[RegulatoryProvision]:
        """Retrieves all provisions applicable to a given product category."""
        return [
            p
            for p in self._provisions_by_id.values()
            if category in p.applicable_categories
        ]

    def is_exempt_under_rule_26(
        self, net_qty_magnitude: Optional[float], unit: Optional[str]
    ) -> bool:
        """Determines whether a commodity package qualifies for small-package exemption under Rule 26.

        Packages of 10g or less, or 10ml or less, are granted statutory exemptions
        from certain mandatory declarations.

        Args:
            net_qty_magnitude: Numerical magnitude of net quantity.
            unit: Unit of measure.

        Returns:
            True if package is <= 10g or <= 10ml, False otherwise.
        """
        if net_qty_magnitude is None or unit is None:
            return False

        normalized_unit = unit.strip().lower()
        if normalized_unit in {"g", "ml"} and net_qty_magnitude <= 10.0:
            return True

        return False
