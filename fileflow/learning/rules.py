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

    def add_pattern_rule(self, pattern: str, target_path: str, confidence: float = 0.95) -> None:
        self.db.upsert_rule_cache(
            match_type="pattern",
            match_key=pattern,
            target_path=target_path,
            confidence=confidence,
        )

    def add_exact_rule(self, filename: str, target_path: str, confidence: float = 0.99) -> None:
        self.db.upsert_rule_cache(
            match_type="exact",
            match_key=filename,
            target_path=target_path,
            confidence=confidence,
        )

    def add_type_dir_rule(
        self,
        extension: str,
        parent_dir: str,
        target_path: str,
        confidence: float = 0.9,
    ) -> None:
        normalized_extension = extension if extension.startswith(".") else f".{extension}"
        self.db.upsert_rule_cache(
            match_type="type_dir",
            match_key=f"{normalized_extension.lower()}:{parent_dir}",
            target_path=target_path,
            confidence=confidence,
        )
