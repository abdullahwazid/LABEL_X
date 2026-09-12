"""Unit tests for regulatory knowledge base and statutory provision registry."""

import pytest
from pydantic import ValidationError

from src.regulatory.models import RegulatoryProvision, ViolationSeverity
from src.regulatory.knowledge_base import RegulatoryKnowledgeBase


@pytest.fixture
def kb() -> RegulatoryKnowledgeBase:
    """Fixture providing an instance of RegulatoryKnowledgeBase."""
    return RegulatoryKnowledgeBase()


def test_knowledge_base_initialization_has_seven_provisions(kb: RegulatoryKnowledgeBase):
    """Test that default knowledge base initializes with all 7 core statutory provisions."""
    provisions = kb.get_all_provisions()
    assert len(provisions) == 7

    provision_ids = {p.provision_id for p in provisions}
    expected_ids = {
        "LMPC_R06_1_E",
        "LMPC_R13",
        "LMPC_R06_11",
        "LMPC_R06_1_D",
        "LMPC_R06_2",
        "LMPC_R07",
        "LMPC_R26",
    }
    assert expected_ids.issubset(provision_ids)


def test_get_provision_by_id(kb: RegulatoryKnowledgeBase):
    """Test retrieving provision by ID returns correct statutory citation and severity."""
    # Test LMPC_R06_1_E
    mrp_rule = kb.get_provision_by_id("LMPC_R06_1_E")
    assert mrp_rule is not None
    assert mrp_rule.rule_reference == "Rule 6(1)(e)"
    assert mrp_rule.severity == ViolationSeverity.CRITICAL
    assert "Maximum Retail Price" in mrp_rule.title

    # Test LMPC_R13
    units_rule = kb.get_provision_by_id("LMPC_R13")
    assert units_rule is not None
    assert units_rule.rule_reference == "Rule 13 read with Second Schedule"
    assert units_rule.severity == ViolationSeverity.CRITICAL

    # Test LMPC_R06_11
    usp_rule = kb.get_provision_by_id("LMPC_R06_11")
    assert usp_rule is not None
    assert usp_rule.amendment_reference == "G.S.R. 779(E)"
    assert usp_rule.severity == ViolationSeverity.MAJOR

    # Test non-existent ID returns None
    assert kb.get_provision_by_id("NON_EXISTENT_RULE") is None


def test_get_applicable_provisions_filtering(kb: RegulatoryKnowledgeBase):
    """Test filtering provisions by commodity category."""
    general_provisions = kb.get_applicable_provisions("GENERAL_COMMODITY")
    assert len(general_provisions) == 7

    small_package_provisions = kb.get_applicable_provisions("SMALL_PACKAGE")
    assert len(small_package_provisions) == 1
    assert small_package_provisions[0].provision_id == "LMPC_R26"

    empty_cat_provisions = kb.get_applicable_provisions("NON_EXISTENT_CATEGORY")
    assert len(empty_cat_provisions) == 0


def test_rule_26_small_package_exemption_helper(kb: RegulatoryKnowledgeBase):
    """Test Rule 26 exemption helper for packages <= 10g or <= 10ml."""
    # 5g -> Exempt
    assert kb.is_exempt_under_rule_26(5.0, "g") is True
    assert kb.is_exempt_under_rule_26(5.0, "G") is True

    # 10g -> Exempt (boundary condition)
    assert kb.is_exempt_under_rule_26(10.0, "g") is True

    # 10ml -> Exempt
    assert kb.is_exempt_under_rule_26(10.0, "ml") is True
    assert kb.is_exempt_under_rule_26(8.5, "ml") is True

    # 15g -> Not exempt
    assert kb.is_exempt_under_rule_26(15.0, "g") is False

    # 500g -> Not exempt
    assert kb.is_exempt_under_rule_26(500.0, "g") is False

    # 100ml -> Not exempt
    assert kb.is_exempt_under_rule_26(100.0, "ml") is False

    # Other units or None values -> Not exempt
    assert kb.is_exempt_under_rule_26(5.0, "kg") is False
    assert kb.is_exempt_under_rule_26(2.0, "N") is False
    assert kb.is_exempt_under_rule_26(None, "g") is False
    assert kb.is_exempt_under_rule_26(5.0, None) is False


def test_regulatory_provision_immutability(kb: RegulatoryKnowledgeBase):
    """Test that RegulatoryProvision instances are frozen and immutable."""
    provision = kb.get_provision_by_id("LMPC_R06_1_E")
    assert provision is not None

    with pytest.raises(ValidationError):
        provision.severity = ViolationSeverity.MINOR  # type: ignore

    with pytest.raises(ValidationError):
        provision.title = "Altered Title"  # type: ignore
