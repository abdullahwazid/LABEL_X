"""Scaffolding and repository structure verification tests for Milestone 1."""

from pathlib import Path
import re
import pytest
from packaging.requirements import Requirement

# Project root is the parent directory of tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

MANDATORY_DIRECTORIES = [
    "docs",
    "src/image_quality",
    "src/ocr",
    "src/extraction",
    "src/regulatory",
    "src/rules",
    "src/evidence",
    "src/decisions",
    "src/storage",
    "tests",
    "data/samples",
]

MANDATORY_DOCS = [
    "docs/REQUIREMENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/REGULATORY_SOURCES.md",
    "docs/KNOWN_LIMITATIONS.md",
]

REQUIRED_PACKAGES = [
    "streamlit",
    "opencv-python-headless",
    "pillow",
    "pydantic",
    "pytesseract",
    "numpy",
    "pytest",
]


def test_mandatory_directories_exist():
    """Verify that all required scaffolding directories exist."""
    for rel_path in MANDATORY_DIRECTORIES:
        dir_path = PROJECT_ROOT / rel_path
        assert dir_path.exists(), f"Mandatory directory missing: {rel_path}"
        assert dir_path.is_dir(), f"Path is not a directory: {rel_path}"


def test_src_packages_have_init():
    """Verify that src and all src subdirectories have __init__.py files."""
    src_dir = PROJECT_ROOT / "src"
    assert (src_dir / "__init__.py").exists(), "Missing src/__init__.py"

    subpackages = [
        "image_quality",
        "ocr",
        "extraction",
        "regulatory",
        "rules",
        "evidence",
        "decisions",
        "storage",
    ]
    for pkg in subpackages:
        init_file = src_dir / pkg / "__init__.py"
        assert init_file.exists(), f"Missing __init__.py in src/{pkg}"


def test_mandatory_documentation_exists_and_populated():
    """Verify that all mandatory technical documentation files exist and are not empty."""
    for doc_rel in MANDATORY_DOCS:
        doc_path = PROJECT_ROOT / doc_rel
        assert doc_path.exists(), f"Documentation file missing: {doc_rel}"
        assert doc_path.is_file(), f"Path is not a file: {doc_rel}"
        content = doc_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 100, f"Documentation file too brief or empty: {doc_rel}"


def test_requirements_file_parseable():
    """Verify requirements.txt exists and each line can be parsed into a valid Requirement."""
    req_file = PROJECT_ROOT / "requirements.txt"
    assert req_file.exists(), "requirements.txt does not exist"

    lines = [
        line.strip()
        for line in req_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert len(lines) >= len(REQUIRED_PACKAGES), "requirements.txt has fewer dependencies than required"

    parsed_names = set()
    for line in lines:
        req = Requirement(line)
        parsed_names.add(req.name.lower())

    for expected_pkg in REQUIRED_PACKAGES:
        assert (
            expected_pkg.lower() in parsed_names
        ), f"Expected package '{expected_pkg}' not found in requirements.txt"


def test_gitignore_covers_essentials():
    """Verify .gitignore exists and covers virtual environments, __pycache__, local storage, and .env."""
    gitignore_file = PROJECT_ROOT / ".gitignore"
    assert gitignore_file.exists(), ".gitignore does not exist"
    content = gitignore_file.read_text(encoding="utf-8")

    essential_patterns = [
        r"__pycache__",
        r"\.venv|venv",
        r"\.env",
        r"storage",
    ]

    for pattern in essential_patterns:
        assert re.search(pattern, content), f".gitignore missing pattern for: {pattern}"
