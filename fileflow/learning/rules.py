from __future__ import annotations

from dataclasses import dataclass

from fileflow.db.operations import Database


@dataclass(slots=True)
class RuleEntry:
    match_type: str
    match_key: str
    target_path: str
    confidence: float
    hit_count: int
    last_hit: str | None
    created_at: str | None


class RuleManager:
    def __init__(self, db: Database):
        self.db = db

    def list_rules(self, limit: int = 20, match_type: str | None = None) -> list[RuleEntry]:
        rows = self.db.get_rule_cache_entries(limit=limit, match_type=match_type)
        return [
            RuleEntry(
                match_type=row["match_type"],
                match_key=row["match_key"],
                target_path=row["target_path"],
                confidence=float(row["confidence"] or 0.0),
                hit_count=int(row["hit_count"] or 0),
                last_hit=row["last_hit"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
