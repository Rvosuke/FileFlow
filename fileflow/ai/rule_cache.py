"""Three-level rule cache for classification results.

Level 1: Exact match — identical filename (e.g. monthly "工资条.pdf")
Level 2: Pattern match — filename matches regex (e.g. "meeting_*_2024.docx")
Level 3: Type+dir match — same extension + same source directory
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fileflow.ai.decision import ClassifyResult
from fileflow.db.operations import Database


class RuleCache:
    """Three-level rule cache backed by SQLite."""

    def __init__(self, db: Database):
        self.db = db

    def lookup(self, meta) -> Optional[ClassifyResult]:
        """Try to find a cached classification. Returns None on miss."""
        # Level 1: exact filename match
        result = self._lookup_exact(meta)
        if result:
            return result

        # Level 2: pattern match
        result = self._lookup_pattern(meta)
        if result:
            return result

        # Level 3: type + directory match
        result = self._lookup_type_dir(meta)
        if result:
            return result

        return None

    def store(self, result: ClassifyResult, meta) -> None:
        """Store a high-confidence result in the cache."""
        import sqlite3
        conn = sqlite3.connect(str(self.db.path))
        try:
            # Store as exact match
            self._upsert_rule(conn, "exact", meta.name + meta.extension,
                              result.target_path, result.confidence)

            # Also store as type_dir match
            type_dir_key = f"{meta.extension}:{meta.parent_dir}"
            self._upsert_rule(conn, "type_dir", type_dir_key,
                              result.target_path, result.confidence)
            conn.commit()
        finally:
            conn.close()

    def store_pattern(self, pattern: str, target_path: str,
                      confidence: float) -> None:
        """Manually add a pattern-based rule."""
        import sqlite3
        conn = sqlite3.connect(str(self.db.path))
        try:
            self._upsert_rule(conn, "pattern", pattern,
                              target_path, confidence)
            conn.commit()
        finally:
            conn.close()

    # ── Private lookup methods ──

    def _lookup_exact(self, meta) -> Optional[ClassifyResult]:
        """Level 1: exact filename match."""
        import sqlite3
        conn = sqlite3.connect(str(self.db.path))
        try:
            row = conn.execute(
                """SELECT target_path, confidence FROM rule_cache
                   WHERE match_type='exact' AND match_key=?""",
                (meta.name + meta.extension,),
            ).fetchone()
            if row and row[1] >= 0.8:
                self._bump_hit(conn, "exact", meta.name + meta.extension)
                conn.commit()
                return self._build_result(meta, row[0], row[1], "exact match")
        finally:
            conn.close()
        return None

    def _lookup_pattern(self, meta) -> Optional[ClassifyResult]:
        """Level 2: regex pattern match against filename."""
        import sqlite3
        conn = sqlite3.connect(str(self.db.path))
        try:
            rows = conn.execute(
                "SELECT match_key, target_path, confidence FROM rule_cache WHERE match_type='pattern'"
            ).fetchall()
            filename = meta.name + meta.extension
            for row in rows:
                try:
                    if re.fullmatch(row[0], filename):
                        self._bump_hit(conn, "pattern", row[0])
                        conn.commit()
                        return self._build_result(meta, row[1], row[2],
                                                  f"pattern match: {row[0]}")
                except re.error:
                    continue
        finally:
            conn.close()
        return None

    def _lookup_type_dir(self, meta) -> Optional[ClassifyResult]:
        """Level 3: extension + source directory match."""
        import sqlite3
        key = f"{meta.extension}:{meta.parent_dir}"
        conn = sqlite3.connect(str(self.db.path))
        try:
            row = conn.execute(
                """SELECT target_path, confidence FROM rule_cache
                   WHERE match_type='type_dir' AND match_key=?""",
                (key,),
            ).fetchone()
            if row and row[1] >= 0.7:
                self._bump_hit(conn, "type_dir", key)
                conn.commit()
                return self._build_result(meta, row[0], row[1],
                                          f"type+dir match: {key}")
        finally:
            conn.close()
        return None

    # ── Helpers ──

    @staticmethod
    def _build_result(meta, target_path: str, confidence: float,
                      reason: str) -> ClassifyResult:
        return ClassifyResult(
            original_path=meta.path,
            target_path=target_path,
            suggested_rename=None,
            confidence=confidence,
            action="move",
            reason=reason,
            source="rule_cache",
            broad_category=meta.broad_category,
        )

    @staticmethod
    def _upsert_rule(conn, match_type: str, match_key: str,
                     target_path: str, confidence: float) -> None:
        existing = conn.execute(
            "SELECT id FROM rule_cache WHERE match_type=? AND match_key=?",
            (match_type, match_key),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE rule_cache
                   SET hit_count = hit_count + 1, last_hit = CURRENT_TIMESTAMP,
                       target_path = ?, confidence = ?
                   WHERE id = ?""",
                (target_path, confidence, existing[0]),
            )
        else:
            conn.execute(
                """INSERT INTO rule_cache
                   (match_type, match_key, target_path, confidence, last_hit)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (match_type, match_key, target_path, confidence),
            )

    @staticmethod
    def _bump_hit(conn, match_type: str, match_key: str) -> None:
        conn.execute(
            """UPDATE rule_cache
               SET hit_count = hit_count + 1, last_hit = CURRENT_TIMESTAMP
               WHERE match_type = ? AND match_key = ?""",
            (match_type, match_key),
        )
