"""SQLite-based result storage for tracking submission attempts."""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import logging

from models.submission_result import SubmissionResult
from models.enums import SubmissionStatus, FailureReason

logger = logging.getLogger(__name__)


class ResultStore:
    """
    SQLite storage for submission results.

    Provides:
    - Persistent storage of submission results
    - Resume capability (skip already-processed forms)
    - Reporting and statistics
    """

    def __init__(self, db_path: str = "data/results.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    form_entry_id TEXT NOT NULL,
                    census_id TEXT NOT NULL,
                    municipality TEXT NOT NULL,
                    state TEXT NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    failure_reason TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    confirmation_number TEXT,
                    confirmation_message TEXT,
                    screenshot_path TEXT,
                    pdf_downloaded_path TEXT,
                    pdf_filled_path TEXT,
                    email_sent_to TEXT,
                    email_sent_at TEXT,
                    error_message TEXT,
                    agent_output TEXT,
                    retry_count INTEGER DEFAULT 0,
                    form_type TEXT,
                    batch_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_form_entry_id
                ON submissions(form_entry_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_batch_id
                ON submissions(batch_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status
                ON submissions(status)
            """)

    def save_result(self, result: SubmissionResult, batch_id: Optional[str] = None):
        """Save a submission result to the database."""
        data = result.to_dict()
        data['batch_id'] = batch_id
        data['updated_at'] = datetime.now().isoformat()

        with self._get_connection() as conn:
            # Check if entry exists
            existing = conn.execute(
                "SELECT id FROM submissions WHERE form_entry_id = ?",
                (result.form_entry_id,)
            ).fetchone()

            if existing:
                # Update existing record
                columns = ', '.join(f"{k} = ?" for k in data.keys())
                values = list(data.values()) + [result.form_entry_id]
                conn.execute(
                    f"UPDATE submissions SET {columns} WHERE form_entry_id = ?",
                    values
                )
            else:
                # Insert new record
                columns = ', '.join(data.keys())
                placeholders = ', '.join('?' * len(data))
                conn.execute(
                    f"INSERT INTO submissions ({columns}) VALUES ({placeholders})",
                    list(data.values())
                )

    def get_result(self, form_entry_id: str) -> Optional[SubmissionResult]:
        """Get a submission result by form entry ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM submissions WHERE form_entry_id = ?",
                (form_entry_id,)
            ).fetchone()

            if row:
                return self._row_to_result(row)
        return None

    def get_processed_ids(self) -> set:
        """Get set of all form_entry_ids that have been successfully processed."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT form_entry_id FROM submissions WHERE status IN (?, ?, ?)",
                (
                    SubmissionStatus.SUCCESS.value,
                    SubmissionStatus.EMAIL_SENT.value,
                    SubmissionStatus.SKIPPED.value
                )
            ).fetchall()

            return {row['form_entry_id'] for row in rows}

    def get_failed_ids(self, max_retries: int = 3) -> List[str]:
        """Get list of form_entry_ids that failed and can be retried."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT form_entry_id FROM submissions
                   WHERE status = ? AND retry_count < ?""",
                (SubmissionStatus.FAILED.value, max_retries)
            ).fetchall()

            return [row['form_entry_id'] for row in rows]

    def get_all_results(self, batch_id: Optional[str] = None) -> List[SubmissionResult]:
        """Get all submission results, optionally filtered by batch."""
        with self._get_connection() as conn:
            if batch_id:
                rows = conn.execute(
                    "SELECT * FROM submissions WHERE batch_id = ? ORDER BY created_at",
                    (batch_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM submissions ORDER BY created_at"
                ).fetchall()

            return [self._row_to_result(row) for row in rows]

    def get_statistics(self, batch_id: Optional[str] = None) -> Dict[str, Any]:
        """Get submission statistics."""
        with self._get_connection() as conn:
            query = "SELECT status, COUNT(*) as count FROM submissions"
            params = []

            if batch_id:
                query += " WHERE batch_id = ?"
                params.append(batch_id)

            query += " GROUP BY status"

            rows = conn.execute(query, params).fetchall()

            stats = {
                'total': 0,
                'by_status': {},
                'by_failure_reason': {}
            }

            for row in rows:
                stats['by_status'][row['status']] = row['count']
                stats['total'] += row['count']

            # Get failure reasons
            failure_query = """
                SELECT failure_reason, COUNT(*) as count
                FROM submissions
                WHERE status = ?
            """
            failure_params = [SubmissionStatus.FAILED.value]

            if batch_id:
                failure_query += " AND batch_id = ?"
                failure_params.append(batch_id)

            failure_query += " GROUP BY failure_reason"

            rows = conn.execute(failure_query, failure_params).fetchall()

            for row in rows:
                if row['failure_reason']:
                    stats['by_failure_reason'][row['failure_reason']] = row['count']

            return stats

    def export_csv(self, output_path: str, batch_id: Optional[str] = None):
        """Export results to CSV file."""
        import csv

        with self._get_connection() as conn:
            query = "SELECT * FROM submissions"
            params = []

            if batch_id:
                query += " WHERE batch_id = ?"
                params.append(batch_id)

            query += " ORDER BY created_at"

            rows = conn.execute(query, params).fetchall()

            if not rows:
                logger.warning("No results to export")
                return

            with open(output_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(rows[0].keys())
                for row in rows:
                    writer.writerow(row)

            logger.info(f"Exported {len(rows)} results to {output_path}")

    def clear_batch(self, batch_id: str):
        """Clear all results for a specific batch."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM submissions WHERE batch_id = ?", (batch_id,))
            logger.info(f"Cleared batch {batch_id}")

    def _row_to_result(self, row: sqlite3.Row) -> SubmissionResult:
        """Convert database row to SubmissionResult."""
        return SubmissionResult(
            form_entry_id=row['form_entry_id'],
            census_id=row['census_id'],
            municipality=row['municipality'],
            state=row['state'],
            url=row['url'],
            status=SubmissionStatus(row['status']),
            failure_reason=FailureReason(row['failure_reason']) if row['failure_reason'] else FailureReason.NONE,
            started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
            completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
            confirmation_number=row['confirmation_number'],
            confirmation_message=row['confirmation_message'],
            screenshot_path=row['screenshot_path'],
            pdf_downloaded_path=row['pdf_downloaded_path'],
            pdf_filled_path=row['pdf_filled_path'],
            email_sent_to=row['email_sent_to'],
            email_sent_at=datetime.fromisoformat(row['email_sent_at']) if row['email_sent_at'] else None,
            error_message=row['error_message'],
            agent_output=row['agent_output'],
            retry_count=row['retry_count'],
            form_type=row['form_type'],
        )
