"""Tests for learning/feedback.py — correction engine and pattern derivation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fileflow.config import FileFlowConfig
from fileflow.db.models import SCHEMA
from fileflow.db.operations import Database
from fileflow.learning.feedback import FeedbackEngine


def _setup(tmp_path: Path):
    """Create environment with config, database, source/target dirs."""
    config = FileFlowConfig()
    target_dir = tmp_path / "Organized"
    target_dir.mkdir()
    config.general.target_root = str(target_dir)
    config.general.create_shortcut = False

    db = Database(tmp_path / "ff.db")
    db.initialize()
    return config, db, target_dir


def _insert_move_record(db: Database, source: Path, target: Path, category: str = "document", confidence: float = 0.65):
    """Insert a move record and return the record ID."""
    with sqlite3.connect(str(db.path)) as conn:
        cur = conn.execute(
            """INSERT INTO move_records
               (source_path, target_path, file_hash, file_size, category, confidence, reason, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(source), str(target), None, target.stat().st_size,
             category, confidence, "heuristic", "completed"),
        )
        conn.commit()
        return cur.lastrowid


# ── Pattern derivation ──


class TestDerivePattern:
    def test_digits_replaced(self) -> None:
        p = FeedbackEngine._derive_pattern("invoice_202403.txt")
        assert p is not None
        assert r"\d+" in p

    def test_no_digits_returns_none(self) -> None:
        p = FeedbackEngine._derive_pattern("readme.txt")
        assert p is None

    def test_multiple_digit_groups(self) -> None:
        p = FeedbackEngine._derive_pattern("report_2024_q1.pdf")
        assert p is not None
        assert p.count(r"\d+") == 2

    def test_special_chars_escaped(self) -> None:
        p = FeedbackEngine._derive_pattern("file[1].txt")
        assert p is not None
        # Square brackets should be escaped
        assert r"\[" in p


# ── Apply correction ──


class TestApplyCorrection:
    def test_successful_correction(self, tmp_path: Path) -> None:
        config, db, target_dir = _setup(tmp_path)

        source_file = tmp_path / "Downloads" / "invoice_2024.txt"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("invoice content")

        # Simulate the file having been moved to wrong location
        wrong_dir = target_dir / "文档" / "文本"
        wrong_dir.mkdir(parents=True)
        moved_file = wrong_dir / "invoice_2024.txt"
        moved_file.write_text("invoice content")

        move_id = _insert_move_record(db, source_file, moved_file)

        engine = FeedbackEngine(config, db)
        result = engine.apply_correction(move_id, "文档/发票")

        assert result.success is True
        assert result.corrected_target == "文档/发票"
        assert (target_dir / "文档" / "发票" / "invoice_2024.txt").exists()
        assert not moved_file.exists()

    def test_correction_stores_exact_rule(self, tmp_path: Path) -> None:
        config, db, target_dir = _setup(tmp_path)

        source_file = tmp_path / "src" / "salary.pdf"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("salary")

        wrong_dir = target_dir / "文档" / "PDF"
        wrong_dir.mkdir(parents=True)
        moved_file = wrong_dir / "salary.pdf"
        moved_file.write_text("salary")

        move_id = _insert_move_record(db, source_file, moved_file)

        engine = FeedbackEngine(config, db)
        engine.apply_correction(move_id, "文档/财务")

        # Check that exact rule was stored
        entries = db.get_rule_cache_entries(match_type="exact")
        assert any(e["match_key"] == "salary.pdf" for e in entries)

    def test_correction_derives_pattern_rule(self, tmp_path: Path) -> None:
        config, db, target_dir = _setup(tmp_path)

        source_file = tmp_path / "src" / "report_2024.pdf"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("report")

        wrong_dir = target_dir / "其他"
        wrong_dir.mkdir(parents=True)
        moved_file = wrong_dir / "report_2024.pdf"
        moved_file.write_text("report")

        move_id = _insert_move_record(db, source_file, moved_file)

        engine = FeedbackEngine(config, db)
        engine.apply_correction(move_id, "文档/年报")

        # Pattern rule should be derived from "report_2024.pdf"
        entries = db.get_rule_cache_entries(match_type="pattern")
        assert len(entries) >= 1
        assert entries[0]["target_path"] == "文档/年报"

    def test_nonexistent_record_fails(self, tmp_path: Path) -> None:
        config, db, target_dir = _setup(tmp_path)
        engine = FeedbackEngine(config, db)
        result = engine.apply_correction(9999, "文档/不存在")
        assert result.success is False
        assert "not found" in result.message

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        config, db, target_dir = _setup(tmp_path)

        source_file = tmp_path / "src" / "gone.txt"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("temp")

        # Record points to a file that no longer exists
        fake_target = target_dir / "文档" / "gone.txt"
        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                """INSERT INTO move_records
                   (source_path, target_path, file_hash, file_size, category, confidence, reason, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(source_file), str(fake_target), None, 0,
                 "document", 0.5, "test", "completed"),
            )
            conn.commit()

        engine = FeedbackEngine(config, db)
        result = engine.apply_correction(1, "文档/修正")
        assert result.success is False
        assert "not found" in result.message


# ── Conflict resolution ──


class TestFeedbackConflictResolution:
    def test_conflict_adds_suffix(self, tmp_path: Path) -> None:
        config, db, target_dir = _setup(tmp_path)

        source_file = tmp_path / "src" / "doc.txt"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("content")

        wrong_dir = target_dir / "其他"
        wrong_dir.mkdir(parents=True)
        moved_file = wrong_dir / "doc.txt"
        moved_file.write_text("content")

        # Pre-create the target to cause conflict
        correct_dir = target_dir / "文档" / "文本"
        correct_dir.mkdir(parents=True)
        (correct_dir / "doc.txt").write_text("existing")

        move_id = _insert_move_record(db, source_file, moved_file)

        engine = FeedbackEngine(config, db)
        result = engine.apply_correction(move_id, "文档/文本")

        assert result.success is True
        assert "doc_1.txt" in result.final_path
