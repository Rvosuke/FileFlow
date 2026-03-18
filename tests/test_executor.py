"""Tests for executor/mover.py and executor/rollback.py."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fileflow.ai.decision import ClassifyResult
from fileflow.db.models import SCHEMA
from fileflow.executor.mover import FileMover, MoveRecord
from fileflow.executor.rollback import RollbackEngine


def _init_db(db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(SCHEMA)


def _make_result(source: Path, target_path: str = "文档/PDF") -> ClassifyResult:
    return ClassifyResult(
        original_path=source,
        target_path=target_path,
        suggested_rename=None,
        confidence=0.85,
        action="move",
        reason="test",
        source="heuristic",
        broad_category="document",
    )


# ── FileMover ──


class TestFileMover:
    def test_dry_run_does_not_move(self, tmp_path: Path) -> None:
        db = tmp_path / "ff.db"
        _init_db(db)
        src = tmp_path / "src" / "note.txt"
        src.parent.mkdir()
        src.write_text("hello")

        mover = FileMover(tmp_path / "target", db, create_shortcut=False)
        result = _make_result(src)
        record = mover.execute(result, dry_run=True)

        assert record.status == "preview"
        assert src.exists(), "source should not be moved in dry-run"

    def test_move_creates_target_and_removes_source(self, tmp_path: Path) -> None:
        db = tmp_path / "ff.db"
        _init_db(db)
        src = tmp_path / "src" / "note.txt"
        src.parent.mkdir()
        src.write_text("hello")

        target_root = tmp_path / "target"
        mover = FileMover(target_root, db, create_shortcut=False)
        result = _make_result(src)
        record = mover.execute(result, dry_run=False)

        assert record.status == "completed"
        assert not src.exists()
        assert (target_root / "文档" / "PDF" / "note.txt").exists()
        assert record.id is not None

    def test_conflict_resolution_adds_suffix(self, tmp_path: Path) -> None:
        db = tmp_path / "ff.db"
        _init_db(db)
        target_root = tmp_path / "target"
        (target_root / "文档" / "PDF").mkdir(parents=True)
        (target_root / "文档" / "PDF" / "note.txt").write_text("existing")

        src = tmp_path / "src" / "note.txt"
        src.parent.mkdir()
        src.write_text("new")

        mover = FileMover(target_root, db, create_shortcut=False)
        record = mover.execute(_make_result(src), dry_run=False)

        assert record.status == "completed"
        assert "note_1.txt" in record.target_path

    def test_suggested_rename(self, tmp_path: Path) -> None:
        db = tmp_path / "ff.db"
        _init_db(db)
        src = tmp_path / "src" / "a.txt"
        src.parent.mkdir()
        src.write_text("content")

        target_root = tmp_path / "target"
        cr = ClassifyResult(
            original_path=src,
            target_path="文档/文本",
            suggested_rename="better_name.txt",
            confidence=0.9,
            action="move",
            reason="rename",
            source="llm",
        )
        mover = FileMover(target_root, db, create_shortcut=False)
        record = mover.execute(cr, dry_run=False)

        assert (target_root / "文档" / "文本" / "better_name.txt").exists()

    def test_execute_batch_skips_skip_action(self, tmp_path: Path) -> None:
        db = tmp_path / "ff.db"
        _init_db(db)
        src1 = tmp_path / "src" / "a.txt"
        src2 = tmp_path / "src" / "b.txt"
        src1.parent.mkdir()
        src1.write_text("a")
        src2.write_text("b")

        cr_move = _make_result(src1)
        cr_skip = ClassifyResult(
            original_path=src2,
            target_path="其他",
            suggested_rename=None,
            confidence=0.3,
            action="skip",
            reason="temp",
            source="heuristic",
        )

        mover = FileMover(tmp_path / "target", db, create_shortcut=False)
        records = mover.execute_batch([cr_move, cr_skip])

        assert len(records) == 1
        assert records[0].status == "completed"


# ── RollbackEngine ──


class TestRollbackEngine:
    def test_undo_last_moves_file_back(self, tmp_path: Path) -> None:
        db = tmp_path / "ff.db"
        _init_db(db)
        src = tmp_path / "src" / "note.txt"
        src.parent.mkdir()
        src.write_text("hello")
        target_root = tmp_path / "target"

        # Move the file
        mover = FileMover(target_root, db, create_shortcut=False)
        mover.execute(_make_result(src), dry_run=False)
        assert not src.exists()

        # Undo
        engine = RollbackEngine(db)
        results = engine.undo_last(1)

        assert len(results) == 1
        assert results[0]["success"] is True
        assert src.exists()

    def test_undo_with_no_records(self, tmp_path: Path) -> None:
        db = tmp_path / "ff.db"
        _init_db(db)
        engine = RollbackEngine(db)
        results = engine.undo_last(5)
        assert results == []

    def test_get_history(self, tmp_path: Path) -> None:
        db = tmp_path / "ff.db"
        _init_db(db)
        src = tmp_path / "src" / "a.txt"
        src.parent.mkdir()
        src.write_text("a")

        mover = FileMover(tmp_path / "target", db, create_shortcut=False)
        mover.execute(_make_result(src), dry_run=False)

        engine = RollbackEngine(db)
        history = engine.get_history()
        assert len(history) == 1
        assert history[0]["status"] == "completed"

    def test_undo_then_history_shows_rolled_back(self, tmp_path: Path) -> None:
        db = tmp_path / "ff.db"
        _init_db(db)
        src = tmp_path / "src" / "a.txt"
        src.parent.mkdir()
        src.write_text("a")

        mover = FileMover(tmp_path / "target", db, create_shortcut=False)
        mover.execute(_make_result(src), dry_run=False)

        engine = RollbackEngine(db)
        engine.undo_last(1)

        history = engine.get_history()
        assert history[0]["status"] == "rolled_back"
