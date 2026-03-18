"""Tests for ai/engine.py — DecisionEngine orchestration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fileflow.ai.decision import ClassifyResult, HeuristicClassifier
from fileflow.ai.engine import DecisionEngine
from fileflow.ai.rule_cache import RuleCache
from fileflow.analyzer.meta import collect_file_meta
from fileflow.config import FileFlowConfig
from fileflow.db.operations import Database


def _setup(tmp_path: Path):
    """Create config, database, and engine for testing."""
    config = FileFlowConfig()
    config.general.target_root = str(tmp_path / "target")
    db = Database(tmp_path / "ff.db")
    db.initialize()
    engine = DecisionEngine(config, db)
    return config, db, engine


def _create_file(tmp_path: Path, name: str, content: str = "test content\n" * 64) -> Path:
    p = tmp_path / "source" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ── Heuristic fallback ──


class TestHeuristicFallback:
    def test_no_llm_falls_back_to_heuristic(self, tmp_path: Path) -> None:
        _, _, engine = _setup(tmp_path)
        f = _create_file(tmp_path, "report.pdf")
        meta = collect_file_meta(f)

        # No LLM client, so should fall back to heuristic
        engine._llm_client = None
        results = engine.classify([meta])

        assert len(results) == 1
        assert results[0].source == "heuristic"
        assert results[0].action == "move"

    def test_heuristic_for_unknown_extension(self, tmp_path: Path) -> None:
        _, _, engine = _setup(tmp_path)
        f = _create_file(tmp_path, "mystery.xyz", content="\x00" * 2048)
        meta = collect_file_meta(f)

        engine._llm_client = None
        results = engine.classify([meta])

        assert len(results) == 1
        assert results[0].action == "review"
        assert results[0].confidence < 0.6


# ── Cache hits ──


class TestCacheIntegration:
    def test_cache_hit_skips_llm(self, tmp_path: Path) -> None:
        _, db, engine = _setup(tmp_path)
        f = _create_file(tmp_path, "salary.pdf")
        meta = collect_file_meta(f)

        # Pre-populate cache
        cache = RuleCache(db)
        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("exact", meta.name + meta.extension, "文档/财务", 0.95),
            )

        # Track whether LLM was called
        llm_called = False
        original_try = engine._try_llm_classify

        def spy_llm(files):
            nonlocal llm_called
            llm_called = True
            return original_try(files)

        engine._try_llm_classify = spy_llm
        engine._llm_client = None  # no real LLM

        results = engine.classify([meta])

        assert len(results) == 1
        assert results[0].source == "rule_cache"
        assert results[0].target_path == "文档/财务"
        assert not llm_called

    def test_low_confidence_cache_falls_through(self, tmp_path: Path) -> None:
        _, db, engine = _setup(tmp_path)
        f = _create_file(tmp_path, "doc.pdf")
        meta = collect_file_meta(f)

        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("exact", meta.name + meta.extension, "文档/低", 0.5),
            )

        engine._llm_client = None
        results = engine.classify([meta])

        # Should NOT use the low-confidence cache entry
        assert results[0].source != "rule_cache" or results[0].confidence >= 0.8


# ── LLM integration with mock ──


class TestLLMIntegration:
    def test_llm_results_stored_in_cache(self, tmp_path: Path) -> None:
        _, db, engine = _setup(tmp_path)
        f = _create_file(tmp_path, "invoice.pdf")
        meta = collect_file_meta(f)

        def fake_llm(files):
            return [
                ClassifyResult(
                    original_path=files[0].path,
                    target_path="文档/发票",
                    suggested_rename=None,
                    confidence=0.92,
                    action="move",
                    reason="invoice",
                    source="llm",
                    broad_category="document",
                )
            ]

        engine._try_llm_classify = fake_llm
        results = engine.classify([meta])

        assert results[0].source == "llm"
        assert results[0].target_path == "文档/发票"

        # Verify it was cached
        cached = RuleCache(db).lookup(meta)
        assert cached is not None
        assert cached.target_path == "文档/发票"

    def test_llm_low_confidence_not_cached(self, tmp_path: Path) -> None:
        _, db, engine = _setup(tmp_path)
        f = _create_file(tmp_path, "unknown.dat")
        meta = collect_file_meta(f)

        def fake_llm(files):
            return [
                ClassifyResult(
                    original_path=files[0].path,
                    target_path="其他/不确定",
                    suggested_rename=None,
                    confidence=0.5,
                    action="review",
                    reason="unsure",
                    source="llm",
                    broad_category="other",
                )
            ]

        engine._try_llm_classify = fake_llm
        results = engine.classify([meta])

        assert results[0].source == "llm"
        # Should NOT be cached because confidence < 0.8
        cached = RuleCache(db)._lookup_exact(meta)
        assert cached is None

    def test_llm_failure_falls_back_to_heuristic(self, tmp_path: Path) -> None:
        _, _, engine = _setup(tmp_path)
        f = _create_file(tmp_path, "report.docx")
        meta = collect_file_meta(f)

        def failing_llm(files):
            return []  # LLM returned nothing

        engine._try_llm_classify = failing_llm
        results = engine.classify([meta])

        assert len(results) == 1
        assert results[0].source == "heuristic"

    def test_partial_llm_results_fill_with_heuristic(self, tmp_path: Path) -> None:
        _, _, engine = _setup(tmp_path)
        f1 = _create_file(tmp_path, "a.pdf")
        f2 = _create_file(tmp_path, "b.docx")
        meta1 = collect_file_meta(f1)
        meta2 = collect_file_meta(f2)

        def partial_llm(files):
            # Only classify the first file
            return [
                ClassifyResult(
                    original_path=files[0].path,
                    target_path="文档/LLM分类",
                    suggested_rename=None,
                    confidence=0.9,
                    action="move",
                    reason="llm",
                    source="llm",
                    broad_category="document",
                )
            ]

        engine._try_llm_classify = partial_llm
        results = engine.classify([meta1, meta2])

        assert len(results) == 2
        assert results[0].source == "llm"
        assert results[1].source == "heuristic"


# ── Mixed cache + LLM ──


class TestMixedFlow:
    def test_cached_and_uncached_files_combined(self, tmp_path: Path) -> None:
        _, db, engine = _setup(tmp_path)
        f_cached = _create_file(tmp_path, "salary.pdf")
        f_new = _create_file(tmp_path, "memo.txt")
        meta_cached = collect_file_meta(f_cached)
        meta_new = collect_file_meta(f_new)

        # Pre-populate cache for salary.pdf
        with sqlite3.connect(str(db.path)) as conn:
            conn.execute(
                "INSERT INTO rule_cache (match_type, match_key, target_path, confidence, last_hit) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("exact", meta_cached.name + meta_cached.extension, "文档/财务", 0.95),
            )

        engine._llm_client = None  # heuristic fallback for uncached
        results = engine.classify([meta_cached, meta_new])

        assert len(results) == 2
        assert results[0].source == "rule_cache"
        assert results[0].target_path == "文档/财务"
        assert results[1].source == "heuristic"

    def test_output_preserves_input_order(self, tmp_path: Path) -> None:
        _, _, engine = _setup(tmp_path)
        files = [_create_file(tmp_path, f"f{i}.txt") for i in range(5)]
        metas = [collect_file_meta(f) for f in files]

        engine._llm_client = None
        results = engine.classify(metas)

        assert [r.original_path for r in results] == [m.path for m in metas]
