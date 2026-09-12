"""SQLite-backed inspection audit persistence repository."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Optional
import uuid

from src.pipeline import PipelineResult
from src.storage.models import InspectionRecord


class InspectionStorageRepository:
    """Provides local SQLite persistence and historical retrieval for screening inspections."""

    def __init__(self, db_path: str = "data/inspections.db") -> None:
        """Initializes repository and ensures database table schema exists.

        Args:
            db_path: Filesystem path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a database connection."""
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        """Creates the inspections table if it does not already exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS inspections (
                    inspection_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    image_name TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    critical_count INTEGER NOT NULL,
                    major_count INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    is_sharp INTEGER NOT NULL,
                    glare_ratio REAL NOT NULL
                )
                """
            )
            conn.commit()

    def save_inspection(self, result: PipelineResult, image_name: str) -> str:
        """Persists a pipeline screening result to SQLite.

        Args:
            result: Complete PipelineResult from compliance screening.
            image_name: Name or path descriptor of the screened packaging image.

        Returns:
            Generated inspection UUID string.
        """
        inspection_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO inspections (
                    inspection_id,
                    timestamp,
                    image_name,
                    verdict,
                    critical_count,
                    major_count,
                    summary,
                    is_sharp,
                    glare_ratio
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inspection_id,
                    timestamp,
                    image_name,
                    result.decision.verdict.value,
                    result.decision.critical_violations_count,
                    result.decision.major_violations_count,
                    result.decision.summary,
                    1 if result.quality_metrics.is_sharp else 0,
                    float(result.quality_metrics.glare_ratio),
                ),
            )
            conn.commit()

        return inspection_id

    def get_recent_inspections(self, limit: int = 20) -> list[InspectionRecord]:
        """Retrieves historical inspection records ordered by timestamp descending.

        Args:
            limit: Maximum number of recent records to return.

        Returns:
            List of InspectionRecord models.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    inspection_id,
                    timestamp,
                    image_name,
                    verdict,
                    critical_count,
                    major_count,
                    summary,
                    is_sharp,
                    glare_ratio
                FROM inspections
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        records: list[InspectionRecord] = []
        for row in rows:
            records.append(
                InspectionRecord(
                    inspection_id=row[0],
                    timestamp=row[1],
                    image_name=row[2],
                    verdict=row[3],
                    critical_count=row[4],
                    major_count=row[5],
                    summary=row[6],
                    is_sharp=bool(row[7]),
                    glare_ratio=row[8],
                )
            )

        return records
