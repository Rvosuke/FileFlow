from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from fileflow.db.models import SCHEMA


@dataclass(slots=True)
class AppStats:
    move_records: int
    rule_cache_rows: int
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
            scan_logs = connection.execute("SELECT COUNT(*) FROM scan_logs").fetchone()[0]
            last_scan_row = connection.execute(
                "SELECT created_at FROM scan_logs ORDER BY id DESC LIMIT 1"
            ).fetchone()

        return AppStats(
            move_records=move_records,
            rule_cache_rows=rule_cache_rows,
            scan_logs=scan_logs,
            last_scan_at=last_scan_row[0] if last_scan_row else None,
        )
