"""Unit tests for SQLite inspection audit storage repository."""

from pathlib import Path
import sqlite3
import uuid
import pytest
from pydantic import ValidationError

from src.mock_generator import SyntheticPackageGenerator
from src.pipeline import CompliancePipeline, PipelineResult
from src.storage.models import InspectionRecord
from src.storage.repository import InspectionStorageRepository


@pytest.fixture
def repo(tmp_path: Path) -> InspectionStorageRepository:
    """Fixture providing an InspectionStorageRepository with a temporary database."""
    db_file = tmp_path / "test_inspections.db"
    return InspectionStorageRepository(db_path=str(db_file))


@pytest.fixture
def pipeline_result() -> PipelineResult:
    """Fixture providing a sample PipelineResult."""
    generator = SyntheticPackageGenerator()
    pipeline = CompliancePipeline()
    img_bytes = generator.generate_compliant_label()

    if not pipeline.ocr_service.is_tesseract_available:
        pipeline.set_injected_text(generator.COMPLIANT_TEXT)

    return pipeline.process_package(img_bytes)


def test_storage_init_creates_database_and_schema(tmp_path: Path):
    """Test that repository initializes database file and creates the inspections table."""
    db_path = tmp_path / "schema_test.db"
    assert not db_path.exists()

    repo = InspectionStorageRepository(db_path=str(db_path))
    assert db_path.exists()

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inspections'")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "inspections"


def test_save_inspection_inserts_record_and_returns_uuid(
    repo: InspectionStorageRepository, pipeline_result: PipelineResult
):
    """Test saving a pipeline result returns a valid UUID and correctly populates SQLite."""
    image_name = "test_biscuit_carton.png"
    inspection_id = repo.save_inspection(pipeline_result, image_name)

    # Verify UUID format
    parsed_uuid = uuid.UUID(inspection_id)
    assert str(parsed_uuid) == inspection_id

    # Verify direct SQLite record content
    with sqlite3.connect(str(repo.db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inspections WHERE inspection_id = ?", (inspection_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == inspection_id
        assert row[2] == image_name
        assert row[3] == pipeline_result.decision.verdict.value
        assert row[4] == pipeline_result.decision.critical_violations_count
        assert row[5] == pipeline_result.decision.major_violations_count
        assert row[7] == (1 if pipeline_result.quality_metrics.is_sharp else 0)


def test_get_recent_inspections_chronological_order(
    repo: InspectionStorageRepository, pipeline_result: PipelineResult
):
    """Test retrieving recent inspections orders by timestamp descending."""
    # Insert multiple inspections
    id1 = repo.save_inspection(pipeline_result, "first_sample.png")
    id2 = repo.save_inspection(pipeline_result, "second_sample.png")
    id3 = repo.save_inspection(pipeline_result, "third_sample.png")

    recent = repo.get_recent_inspections(limit=10)
    assert len(recent) == 3

    assert isinstance(recent[0], InspectionRecord)
    assert recent[0].inspection_id == id3
    assert recent[1].inspection_id == id2
    assert recent[2].inspection_id == id1

    # Verify timestamp ordering (descending)
    assert recent[0].timestamp >= recent[1].timestamp >= recent[2].timestamp

    # Test limit constraint
    limited = repo.get_recent_inspections(limit=2)
    assert len(limited) == 2


def test_inspection_record_immutability():
    """Verify that InspectionRecord is frozen and immutable."""
    record = InspectionRecord(
        inspection_id="123e4567-e89b-12d3-a456-426614174000",
        timestamp="2026-09-11T12:00:00Z",
        image_name="sample.png",
        verdict="NO_OBVIOUS_ISSUE",
        critical_count=0,
        major_count=0,
        summary="All verified",
        is_sharp=True,
        glare_ratio=0.01,
    )

    with pytest.raises(ValidationError):
        record.verdict = "POTENTIAL_NON_COMPLIANCE"  # type: ignore

    with pytest.raises(ValidationError):
        record.critical_count = 10  # type: ignore
