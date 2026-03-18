from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from fileflow.db.models import SCHEMA


@dataclass(slots=True)
class AppStats:
    move_records: int
    rule_cache_rows: int
    corrections: int
    scan_logs: int
    last_scan_at: str | None


class Database:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.executescript(SCHEMA)

    def record_scan(
        self,
        *,
        source_path: str,
        files_found: int,
        files_moved: int,
        files_skipped: int,
        files_cached: int,
        llm_calls: int,
        duration_ms: int,
    ) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO scan_logs (
                    source_path,
                    files_found,
                    files_moved,
                    files_skipped,
                    files_cached,
                    llm_calls,
                    duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_path,
                    files_found,
                    files_moved,
                    files_skipped,
                    files_cached,
                    llm_calls,
                    duration_ms,
                ),
            )

    def get_stats(self) -> AppStats:
        with sqlite3.connect(self.path) as connection:
            move_records = connection.execute("SELECT COUNT(*) FROM move_records").fetchone()[0]
            rule_cache_rows = connection.execute("SELECT COUNT(*) FROM rule_cache").fetchone()[0]
            corrections = connection.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
            scan_logs = connection.execute("SELECT COUNT(*) FROM scan_logs").fetchone()[0]
            last_scan_row = connection.execute(
                "SELECT created_at FROM scan_logs ORDER BY id DESC LIMIT 1"
            ).fetchone()

        return AppStats(
            move_records=move_records,
            rule_cache_rows=rule_cache_rows,
            corrections=corrections,
            scan_logs=scan_logs,
            last_scan_at=last_scan_row[0] if last_scan_row else None,
        )

    def get_move_record(self, move_record_id: int) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM move_records WHERE id = ?",
                (move_record_id,),
            ).fetchone()
        return dict(row) if row else None

    def record_correction(
        self,
        *,
        move_record_id: int,
        original_target: str,
        corrected_target: str,
    ) -> int:
        with sqlite3.connect(self.path) as connection:
            cur = connection.execute(
                """
                INSERT INTO corrections (
                    move_record_id,
                    original_target,
                    corrected_target
                ) VALUES (?, ?, ?)
                """,
                (move_record_id, original_target, corrected_target),
            )
            connection.commit()
            return cur.lastrowid

    def update_move_target_path(self, move_record_id: int, target_path: str) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "UPDATE move_records SET target_path = ? WHERE id = ?",
                (target_path, move_record_id),
            )
            connection.commit()

    def get_corrections(self, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT c.*, m.source_path
                FROM corrections c
                LEFT JOIN move_records m ON m.id = c.move_record_id
                ORDER BY c.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_rule_cache_entries(
        self,
        limit: int = 20,
        match_type: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT id, match_type, match_key, target_path, confidence, hit_count, last_hit, created_at
            FROM rule_cache
        """
        params: tuple[Any, ...]
        if match_type:
            query += " WHERE match_type = ?"
            params = (match_type,)
        else:
            params = ()
        query += " ORDER BY hit_count DESC, created_at DESC LIMIT ?"
        params = (*params, limit)

        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def delete_rule_cache_entry(self, rule_id: int) -> bool:
        with sqlite3.connect(self.path) as connection:
            cur = connection.execute("DELETE FROM rule_cache WHERE id = ?", (rule_id,))
            connection.commit()
            return cur.rowcount > 0

    def upsert_rule_cache(
        self,
        *,
        match_type: str,
        match_key: str,
        target_path: str,
        confidence: float,
    ) -> None:
        with sqlite3.connect(self.path) as connection:
            existing = connection.execute(
                "SELECT id FROM rule_cache WHERE match_type = ? AND match_key = ?",
                (match_type, match_key),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE rule_cache
                    SET target_path = ?, confidence = ?, hit_count = hit_count + 1, last_hit = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (target_path, confidence, existing[0]),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO rule_cache (
                        match_type, match_key, target_path, confidence, hit_count, last_hit
                    ) VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                    """,
                    (match_type, match_key, target_path, confidence),
                )
            connection.commit()
