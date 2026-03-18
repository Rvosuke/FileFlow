from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

from fileflow.ai.decision import ClassifyResult, normalize_target_path
from fileflow.ai.rule_cache import RuleCache
from fileflow.db.operations import Database
from fileflow.utils.shortcut import create_windows_shortcut


@dataclass(slots=True)
class CorrectionResult:
    success: bool
    move_record_id: int
    original_target: str
    corrected_target: str
    final_path: str | None
    message: str


class FeedbackEngine:
    def __init__(self, config, db: Database):
        self.config = config
        self.db = db
        self.target_root = Path(config.general.target_root)
        self.rule_cache = RuleCache(db)

    def apply_correction(self, move_record_id: int, corrected_target: str) -> CorrectionResult:
        record = self.db.get_move_record(move_record_id)
        if record is None:
            return CorrectionResult(
                success=False,
                move_record_id=move_record_id,
                original_target="",
                corrected_target=corrected_target,
                final_path=None,
                message=f"move record {move_record_id} not found",
            )

        current_path = Path(record["target_path"])
        if not current_path.exists():
            return CorrectionResult(
                success=False,
                move_record_id=move_record_id,
                original_target=self._to_relative_target(record["target_path"]),
                corrected_target=corrected_target,
                final_path=None,
                message=f"current file not found: {current_path}",
            )

        safe_target = normalize_target_path(
            corrected_target,
            allowed_top_levels=self.config.categories.top_level,
            fallback_top_level="其他",
            max_depth=self.config.categories.max_depth,
        )
        destination_dir = self.target_root / safe_target
        destination_dir.mkdir(parents=True, exist_ok=True)
        final_path = destination_dir / self._resolve_conflict(destination_dir, current_path.name)

        shutil.move(str(current_path), str(final_path))
        self._refresh_shortcut(Path(record["source_path"]), final_path)

        original_target = self._to_relative_target(record["target_path"])
        self.db.record_correction(
            move_record_id=move_record_id,
            original_target=original_target,
            corrected_target=safe_target,
        )
        self.db.update_move_target_path(move_record_id, str(final_path))
        self._store_feedback_rule(record, safe_target)

        return CorrectionResult(
            success=True,
            move_record_id=move_record_id,
            original_target=original_target,
            corrected_target=safe_target,
            final_path=str(final_path),
            message=f"corrected move record {move_record_id} -> {safe_target}",
        )

    def _store_feedback_rule(self, record: dict, corrected_target: str) -> None:
        source_path = Path(record["source_path"])
        pseudo_meta = SimpleNamespace(
            path=source_path,
            name=source_path.stem,
            extension=source_path.suffix.lower(),
            parent_dir=source_path.parent.name,
            broad_category=record.get("category") or "other",
        )
        result = ClassifyResult(
            original_path=source_path,
            target_path=corrected_target,
            suggested_rename=None,
            confidence=1.0,
            action="move",
            reason="user correction",
            source="rule_cache",
            broad_category=pseudo_meta.broad_category,
        )
        self.rule_cache.store(result, pseudo_meta)

        derived_pattern = self._derive_pattern(source_path.name)
        if derived_pattern is not None:
            base_confidence = float(record.get("confidence") or 1.0)
            pattern_confidence = max(0.8, min(0.99, base_confidence * 0.9))
            self.rule_cache.store_pattern(derived_pattern, corrected_target, pattern_confidence)

    def _to_relative_target(self, target_path: str) -> str:
        path = Path(target_path)
        try:
            return path.relative_to(self.target_root).as_posix()
        except ValueError:
            return path.as_posix()

    @staticmethod
    def _resolve_conflict(target_dir: Path, file_name: str) -> str:
        target = target_dir / file_name
        if not target.exists():
            return file_name

        stem = Path(file_name).stem
        suffix = Path(file_name).suffix
        counter = 1
        while True:
            candidate = f"{stem}_{counter}{suffix}"
            if not (target_dir / candidate).exists():
                return candidate
            counter += 1

    @staticmethod
    def _refresh_shortcut(source_path: Path, final_path: Path) -> None:
        shortcut_path = source_path.with_suffix(".lnk")
        if shortcut_path.exists():
            shortcut_path.unlink()
        create_windows_shortcut(shortcut_path, final_path)

    @staticmethod
    def _derive_pattern(filename: str) -> str | None:
        escaped = re.escape(filename)
        pattern = re.sub(r"\d+", r"\\d+", escaped)
        if pattern == escaped:
            return None
        return pattern
