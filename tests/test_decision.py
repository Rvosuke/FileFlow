from fileflow.ai.decision import ClassifyResult, HeuristicClassifier, normalize_target_path
from fileflow.ai.engine import DecisionEngine
from fileflow.ai.rule_cache import RuleCache
from fileflow.analyzer.meta import collect_file_meta
from fileflow.config import FileFlowConfig
from fileflow.db.operations import Database
from fileflow.learning.feedback import FeedbackEngine


def test_normalize_target_path_rejects_absolute_and_limits_depth() -> None:
    assert normalize_target_path(
        "C:/Windows/System32",
        allowed_top_levels=["文档", "其他"],
        fallback_top_level="其他",
        max_depth=3,
    ) == "其他"

    assert normalize_target_path(
        "陌生分类/项目/阶段/最终版",
        allowed_top_levels=["文档", "其他"],
        fallback_top_level="其他",
        max_depth=3,
    ) == "其他/陌生分类/项目"


def test_decision_engine_preserves_input_order_when_llm_returns_out_of_order(tmp_path) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("alpha\n" * 128, encoding="utf-8")
    second.write_text("beta\n" * 128, encoding="utf-8")

    metas = [collect_file_meta(first), collect_file_meta(second)]
    config = FileFlowConfig()
    database = Database(tmp_path / "fileflow.db")
    database.initialize()
    engine = DecisionEngine(config, database)

    def fake_llm(files):
        return [
            ClassifyResult(
                original_path=files[1].path,
                target_path="文档/文本",
                suggested_rename=None,
                confidence=0.9,
                action="move",
                reason="second",
                source="llm",
                broad_category=files[1].broad_category,
            ),
            ClassifyResult(
                original_path=files[0].path,
                target_path="文档/文本",
                suggested_rename=None,
                confidence=0.9,
                action="move",
                reason="first",
                source="llm",
                broad_category=files[0].broad_category,
            ),
        ]

    engine._try_llm_classify = fake_llm  # type: ignore[method-assign]

    results = engine.classify(metas)

    assert [result.original_path for result in results] == [meta.path for meta in metas]


def test_heuristic_classifier_marks_unknown_types_for_review(tmp_path) -> None:
    unknown = tmp_path / "blob.bin"
    unknown.write_bytes(b"\x00" * 2048)

    meta = collect_file_meta(unknown)
    result = HeuristicClassifier().classify_batch([meta])[0]

    assert result.action == "review"
    assert result.confidence < 0.6


def test_feedback_engine_stores_corrected_rule_cache(tmp_path) -> None:
    source_dir = tmp_path / "Downloads"
    target_dir = tmp_path / "Organized"
    source_dir.mkdir()
    target_dir.mkdir()

    source_file = source_dir / "invoice_202403.txt"
    source_file.write_text("hello\n" * 128, encoding="utf-8")
    original_target = target_dir / "文档" / "文本"
    original_target.mkdir(parents=True)
    moved_file = original_target / "invoice_202403.txt"
    moved_file.write_text("hello\n" * 128, encoding="utf-8")

    config = FileFlowConfig()
    config.general.target_root = str(target_dir)
    database = Database(tmp_path / "fileflow.db")
    database.initialize()
    move_id = 0
    import sqlite3
    with sqlite3.connect(database.path) as connection:
        cur = connection.execute(
            """
            INSERT INTO move_records (
                source_path, target_path, file_hash, file_size,
                category, confidence, reason, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(source_file),
                str(moved_file),
                None,
                moved_file.stat().st_size,
                "document",
                0.65,
                "heuristic",
                "completed",
            ),
        )
        connection.commit()
        move_id = cur.lastrowid

    engine = FeedbackEngine(config, database)
    result = engine.apply_correction(move_id, "文档/归档")

    assert result.success is True
    assert (target_dir / "文档" / "归档" / "invoice_202403.txt").exists()

    replacement = source_dir / "invoice_202404.txt"
    replacement.write_text("hello\n" * 128, encoding="utf-8")
    replacement_meta = collect_file_meta(replacement)
    replacement_meta.name = "invoice_202404"  # type: ignore[misc]
    replacement_meta.extension = ".txt"  # type: ignore[misc]
    replacement_meta.parent_dir = source_dir.name  # type: ignore[misc]

    cached = RuleCache(database).lookup(replacement_meta)
    assert cached is not None
    assert cached.target_path == "文档/归档"
    assert cached.source == "rule_cache"

    pattern_rows = database.get_rule_cache_entries(match_type="pattern")
    assert pattern_rows
    assert pattern_rows[0]["confidence"] == 0.8
