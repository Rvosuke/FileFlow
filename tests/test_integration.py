"""End-to-end integration tests — full scan -> classify -> move -> undo flow."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fileflow.ai.decision import HeuristicClassifier
from fileflow.analyzer.meta import collect_file_meta
from fileflow.config import FileFlowConfig, initialize_app
from fileflow.db.operations import Database
from fileflow.executor.mover import FileMover
from fileflow.executor.rollback import RollbackEngine
from fileflow.scanner import FileScanner


def _setup_env(tmp_path: Path, monkeypatch):
    """Set up a complete FileFlow environment in tmp_path."""
    app_home = tmp_path / "app"
    monkeypatch.setenv("FILEFLOW_HOME", str(app_home))
    paths = initialize_app(home=app_home)

    config = FileFlowConfig()
    source_dir = tmp_path / "Downloads"
    target_dir = tmp_path / "Organized"
    source_dir.mkdir()
    target_dir.mkdir()

    config.sources.paths = [str(source_dir)]
    config.sources.min_file_size_kb = 0
    config.general.target_root = str(target_dir)
    config.general.create_shortcut = False

    return config, paths, source_dir, target_dir


class TestFullFlow:
    def test_scan_classify_move_undo(self, tmp_path: Path, monkeypatch) -> None:
        config, paths, source_dir, target_dir = _setup_env(tmp_path, monkeypatch)

        # Create test files
        (source_dir / "report.pdf").write_text("PDF content " * 100)
        (source_dir / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        (source_dir / "setup.exe").write_bytes(b"MZ" + b"\x00" * 100)
        (source_dir / "notes.txt").write_text("Meeting notes " * 50)
        (source_dir / "data.csv").write_text("col1,col2\n1,2\n3,4\n" * 20)

        # Step 1: Scan
        scanner = FileScanner(config)
        result = scanner.scan()

        assert len(result.files) == 5
        categories = {f.broad_category for f in result.files}
        assert "document" in categories
        assert "image" in categories
        assert "installer" in categories

        # Step 2: Classify with heuristic
        classifier = HeuristicClassifier()
        classifications = classifier.classify_batch(result.files)

        assert len(classifications) == 5
        assert all(c.action in ("move", "review", "skip") for c in classifications)

        # Step 3: Move files
        db = Database(paths.database_file)
        mover = FileMover(target_dir, paths.database_file, create_shortcut=False)
        moved = []
        for cr in classifications:
            if cr.action == "move":
                record = mover.execute(cr, dry_run=False)
                if record.status == "completed":
                    moved.append(record)

        assert len(moved) >= 3  # at least pdf, png, exe should move

        # Verify source files are gone
        remaining = list(source_dir.iterdir())
        assert len(remaining) < 5

        # Verify target files exist
        target_files = list(target_dir.rglob("*"))
        target_file_count = sum(1 for f in target_files if f.is_file())
        assert target_file_count >= 3

        # Step 4: Undo all moves
        engine = RollbackEngine(paths.database_file)
        history = engine.get_history()
        assert len(history) == len(moved)

        undo_results = engine.undo_last(len(moved))
        assert all(r["success"] for r in undo_results)

        # Verify files are back in source
        restored = list(source_dir.iterdir())
        assert len(restored) == 5

    def test_scan_with_category_filter(self, tmp_path: Path, monkeypatch) -> None:
        config, paths, source_dir, target_dir = _setup_env(tmp_path, monkeypatch)

        (source_dir / "a.pdf").write_text("doc " * 100)
        (source_dir / "b.py").write_text("code " * 100)
        (source_dir / "c.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 100)

        scanner = FileScanner(config)
        result = scanner.scan(category_filter="document")

        assert len(result.files) == 1
        assert result.files[0].broad_category == "document"

    def test_dry_run_does_not_modify_filesystem(self, tmp_path: Path, monkeypatch) -> None:
        config, paths, source_dir, target_dir = _setup_env(tmp_path, monkeypatch)

        (source_dir / "report.pdf").write_text("content " * 100)

        scanner = FileScanner(config)
        result = scanner.scan()
        classifications = HeuristicClassifier().classify_batch(result.files)

        mover = FileMover(target_dir, paths.database_file, create_shortcut=False)
        for cr in classifications:
            if cr.action == "move":
                record = mover.execute(cr, dry_run=True)
                assert record.status == "preview"

        # Source should still have the file
        assert (source_dir / "report.pdf").exists()
        # Target should be empty
        assert not list(target_dir.rglob("*.pdf"))

    def test_dedup_finds_real_duplicates(self, tmp_path: Path, monkeypatch) -> None:
        config, paths, source_dir, target_dir = _setup_env(tmp_path, monkeypatch)

        content = "identical content " * 100
        (source_dir / "file1.txt").write_text(content)
        (source_dir / "file2.txt").write_text(content)
        (source_dir / "unique.txt").write_text("different")

        from fileflow.analyzer.dedup import find_duplicates
        all_files = list(source_dir.iterdir())
        dupes = find_duplicates(all_files)

        assert len(dupes) == 1  # one group of duplicates
        group = list(dupes.values())[0]
        assert len(group) == 2
        names = {f.name for f in group}
        assert names == {"file1.txt", "file2.txt"}

    def test_rule_cache_speeds_up_reclassification(self, tmp_path: Path, monkeypatch) -> None:
        config, paths, source_dir, target_dir = _setup_env(tmp_path, monkeypatch)

        from fileflow.ai.engine import DecisionEngine
        from fileflow.ai.rule_cache import RuleCache
        from fileflow.ai.decision import ClassifyResult

        db = Database(paths.database_file)
        cache = RuleCache(db)

        # Create and classify a file
        (source_dir / "monthly_report.pdf").write_text("report " * 100)
        meta = collect_file_meta(source_dir / "monthly_report.pdf")

        # Store a high-confidence rule
        cr = ClassifyResult(
            original_path=meta.path,
            target_path="文档/月报",
            suggested_rename=None,
            confidence=0.95,
            action="move",
            reason="monthly report",
            source="llm",
            broad_category="document",
        )
        cache.store(cr, meta)

        # Now engine should hit cache and skip LLM
        engine = DecisionEngine(config, db)
        engine._llm_client = None  # ensure no LLM
        results = engine.classify([meta])

        assert results[0].source == "rule_cache"
        assert results[0].target_path == "文档/月报"
        assert results[0].confidence == 0.95
