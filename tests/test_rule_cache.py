"""Tests for ai/rule_cache.py — three-level rule cache."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from fileflow.ai.rule_cache import RuleCache
from fileflow.db.models import SCHEMA
from fileflow.db.operations import Database


def _init_db(db_path: Path) -> Database:
    db = Database(db_path)
    db.initialize()
    return db


@dataclass
class _FakeMeta:
    path: Path
    name: str
    extension: str
    parent_dir: str
    broad_category: str


def _meta(tmp_path: Path, name: str = "report", ext: str = ".pdf",
          parent: str = "Downloads", category: str = "document") -> _FakeMeta:
    return _FakeMeta(
        path=tmp_path / f"{name}{ext}",
        name=name,
        extension=ext,
        parent_dir=parent,
        broad_category=category,
    )


# ── Exact match ──


class TestExactLookup:
    def test_miss_returns_none(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path)
        assert cache.lookup(meta) is None

    def test_hit_returns_result(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path)

        # Manually insert an exact rule
        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("exact", "report.pdf", "文档/报告", 0.95),
            )

        result = cache.lookup(meta)
        assert result is not None
        assert result.target_path == "文档/报告"
        assert result.source == "rule_cache"
        assert result.confidence == 0.95

    def test_low_confidence_exact_ignored(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path)

        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("exact", "report.pdf", "文档/报告", 0.5),
            )

        # Confidence < 0.8 threshold for exact, should fall through
        result = cache._lookup_exact(meta)
        assert result is None


# ── Pattern match ──


class TestPatternLookup:
    def test_pattern_match(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path, name="invoice_202403", ext=".txt")

        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("pattern", r"invoice_\d+\.txt", "文档/归档", 0.85),
            )

        result = cache.lookup(meta)
        assert result is not None
        assert result.target_path == "文档/归档"
        assert "pattern match" in result.reason

    def test_pattern_no_match(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path, name="random_file", ext=".txt")

        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("pattern", r"invoice_\d+\.txt", "文档/归档", 0.85),
            )

        result = cache._lookup_pattern(meta)
        assert result is None

    def test_invalid_regex_skipped(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path, name="test", ext=".txt")

        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("pattern", "[invalid(regex", "somewhere", 0.9),
            )

        result = cache._lookup_pattern(meta)
        assert result is None


# ── Type+dir match ──


class TestTypeDirLookup:
    def test_type_dir_hit(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path, parent="Desktop")

        key = f".pdf:Desktop"
        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("type_dir", key, "文档/桌面PDF", 0.8),
            )

        result = cache.lookup(meta)
        assert result is not None
        assert result.target_path == "文档/桌面PDF"

    def test_type_dir_low_confidence_ignored(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path, parent="Desktop")

        key = f".pdf:Desktop"
        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("type_dir", key, "文档/桌面PDF", 0.5),
            )

        result = cache._lookup_type_dir(meta)
        assert result is None


# ── Store ──


class TestStore:
    def test_store_creates_exact_and_type_dir(self, tmp_path: Path) -> None:
        from fileflow.ai.decision import ClassifyResult

        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path, name="salary", ext=".pdf", parent="HR")

        cr = ClassifyResult(
            original_path=meta.path,
            target_path="文档/财务",
            suggested_rename=None,
            confidence=0.9,
            action="move",
            reason="test",
            source="llm",
        )
        cache.store(cr, meta)

        with sqlite3.connect(str(db.path)) as conn:
            exact = conn.execute(
                "SELECT target_path FROM rule_cache WHERE match_type='exact' AND match_key='salary.pdf'"
            ).fetchone()
            type_dir = conn.execute(
                "SELECT target_path FROM rule_cache WHERE match_type='type_dir' AND match_key='.pdf:HR'"
            ).fetchone()

        assert exact is not None
        assert exact[0] == "文档/财务"
        assert type_dir is not None
        assert type_dir[0] == "文档/财务"

    def test_store_pattern(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        cache.store_pattern(r"report_\d{4}\.pdf", "文档/年报", 0.88)

        with sqlite3.connect(str(db.path)) as conn:
            row = conn.execute(
                "SELECT target_path, confidence FROM rule_cache WHERE match_type='pattern'"
            ).fetchone()

        assert row is not None
        assert row[0] == "文档/年报"
        assert row[1] == pytest.approx(0.88)


# ── Hit count bumping ──


class TestHitCount:
    def test_lookup_bumps_hit_count(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path)

        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, hit_count, last_hit) "
                "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("exact", "report.pdf", "文档/报告", 0.95, 1),
            )

        cache.lookup(meta)
        cache.lookup(meta)

        with sqlite3.connect(str(db.path)) as conn:
            hit_count = conn.execute(
                "SELECT hit_count FROM rule_cache WHERE match_key='report.pdf'"
            ).fetchone()[0]

        assert hit_count == 3  # 1 initial + 2 lookups


# ── Lookup priority ──


class TestLookupPriority:
    def test_exact_takes_priority_over_pattern(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path, name="invoice_2024", ext=".txt")

        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("exact", "invoice_2024.txt", "文档/精确", 0.95),
            )
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("pattern", r"invoice_\d+\.txt", "文档/模式", 0.85),
            )

        result = cache.lookup(meta)
        assert result.target_path == "文档/精确"

    def test_pattern_takes_priority_over_type_dir(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path, name="invoice_2024", ext=".txt", parent="Downloads")

        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("pattern", r"invoice_\d+\.txt", "文档/模式", 0.85),
            )
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("type_dir", ".txt:Downloads", "文档/类型目录", 0.8),
            )

        result = cache.lookup(meta)
        assert result.target_path == "文档/模式"


# ── Upsert behavior ──


class TestUpsert:
    def test_store_twice_updates_existing(self, tmp_path: Path) -> None:
        from fileflow.ai.decision import ClassifyResult

        db = _init_db(tmp_path / "ff.db")
        cache = RuleCache(db)
        meta = _meta(tmp_path, name="doc", ext=".pdf", parent="src")

        cr1 = ClassifyResult(
            original_path=meta.path, target_path="旧路径",
            suggested_rename=None, confidence=0.85,
            action="move", reason="first", source="llm",
        )
        cr2 = ClassifyResult(
            original_path=meta.path, target_path="新路径",
            suggested_rename=None, confidence=0.95,
            action="move", reason="second", source="llm",
        )
        cache.store(cr1, meta)
        cache.store(cr2, meta)

        with sqlite3.connect(str(db.path)) as conn:
            rows = conn.execute(
                "SELECT target_path FROM rule_cache WHERE match_type='exact' AND match_key='doc.pdf'"
            ).fetchall()

        assert len(rows) == 1
        assert rows[0][0] == "新路径"
