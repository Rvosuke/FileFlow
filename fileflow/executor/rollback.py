"""Rollback engine — undo file moves."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

logger = logging.getLogger("fileflow.rollback")


class RollbackEngine:
    """Undo file moves using the operation log."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def undo_last(self, n: int = 1) -> list[dict]:
        """Undo the most recent n completed moves. Returns list of results."""
        records = self._get_recent_completed(n)
        results = []

        for record in records:
            result = self._undo_one(record)
            results.append(result)

        return results

    def undo_all_today(self) -> list[dict]:
        """Undo all moves made today."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT * FROM move_records
                   WHERE status = 'completed'
                   AND date(created_at) = date('now')
                   ORDER BY id DESC""",
            ).fetchall()
            records = [dict(r) for r in rows]
        finally:
            conn.close()

        results = []
        for record in records:
            result = self._undo_one(record)
            results.append(result)
        return results

    def _undo_one(self, record: dict) -> dict:
        """Undo a single move operation."""
        target = Path(record["target_path"])
        source = Path(record["source_path"])

        result = {
            "id": record["id"],
            "source": str(source),
            "target": str(target),
            "success": False,
            "message": "",
        }

        if not target.exists():
            result["message"] = f"Target file not found: {target}"
            logger.warning(result["message"])
            return result

        try:
            # Ensure source parent directory exists
            source.parent.mkdir(parents=True, exist_ok=True)

            # Move file back
            shutil.move(str(target), str(source))

            # Remove shortcut if it exists
            shortcut = source.with_suffix(".lnk")
            if shortcut.exists():
                shortcut.unlink()

            # Update database status
            self._update_status(record["id"], "rolled_back")

            result["success"] = True
            result["message"] = f"Rolled back: {target.name} -> {source}"
            logger.info(result["message"])

        except OSError as exc:
            result["message"] = f"Failed to rollback: {exc}"
            logger.error(result["message"])

        return result

    def _get_recent_completed(self, n: int) -> list[dict]:
        """Get the most recent n completed move records."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT * FROM move_records
                   WHERE status = 'completed'
                   ORDER BY id DESC LIMIT ?""",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _update_status(self, record_id: int, status: str) -> None:
        """Update the status of a move record."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                "UPDATE move_records SET status = ? WHERE id = ?",
                (status, record_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_history(self, limit: int = 50) -> list[dict]:
        """Get move history regardless of status."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM move_records ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
