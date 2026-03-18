"""File mover — moves files to target directories with conflict handling."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from fileflow.ai.decision import ClassifyResult

logger = logging.getLogger("fileflow.mover")


@dataclass(slots=True)
class MoveRecord:
    source_path: str
    target_path: str
    file_hash: str | None
    file_size: int | None
    category: str | None
    confidence: float | None
    reason: str | None
    status: str  # completed | rolled_back | preview
    id: int | None = None
    created_at: str | None = None


class FileMover:
    """Moves files and logs operations for rollback."""

    def __init__(self, target_root: Path, db_path: Path,
                 create_shortcut: bool = True):
        self.target_root = target_root
        self.db_path = db_path
        self.create_shortcut = create_shortcut

    def execute(self, result: ClassifyResult, meta=None,
                dry_run: bool = False) -> MoveRecord:
        """Execute a file move based on classification result."""
        source = result.original_path
        target_dir = self.target_root / result.target_path
        file_name = result.suggested_rename or source.name

        record = MoveRecord(
            source_path=str(source),
            target_path="",
            file_hash=meta.sha256 if meta else None,
            file_size=meta.size_bytes if meta else None,
            category=result.broad_category,
            confidence=result.confidence,
            reason=result.reason,
            status="preview" if dry_run else "completed",
        )

        if dry_run:
            record.target_path = str(target_dir / file_name)
            return record

        # 1. Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # 2. Handle filename conflicts
        final_name = self._resolve_conflict(target_dir, file_name)
        final_path = target_dir / final_name

        # 3. Move the file
        try:
            shutil.move(str(source), str(final_path))
            logger.info("Moved: %s -> %s", source, final_path)
        except OSError as exc:
            logger.error("Failed to move %s: %s", source, exc)
            record.status = "failed"
            record.target_path = str(final_path)
            return record

        # 4. Create shortcut at original location
        if self.create_shortcut:
            self._create_shortcut(source, final_path)

        # 5. Log the operation
        record.target_path = str(final_path)
        record.id = self._save_record(record)

        return record

    def execute_batch(self, classifications: list[ClassifyResult],
                      metas: list = None,
                      dry_run: bool = False) -> list[MoveRecord]:
        """Execute a batch of moves."""
        meta_lookup = {}
        if metas:
            meta_lookup = {str(m.path): m for m in metas}

        records = []
        for cr in classifications:
            if cr.action == "skip":
                continue
            meta = meta_lookup.get(str(cr.original_path))
            record = self.execute(cr, meta=meta, dry_run=dry_run)
            records.append(record)
        return records

    def _resolve_conflict(self, target_dir: Path, file_name: str) -> str:
        """Add _1, _2, etc. suffix if file already exists."""
        target = target_dir / file_name
        if not target.exists():
            return file_name

        stem = Path(file_name).stem
        suffix = Path(file_name).suffix
        counter = 1
        while True:
            new_name = f"{stem}_{counter}{suffix}"
            if not (target_dir / new_name).exists():
                return new_name
            counter += 1

    def _create_shortcut(self, original: Path, target: Path) -> None:
        """Create Windows shortcut at original location."""
        try:
            from fileflow.utils.shortcut import create_windows_shortcut
            shortcut_path = original.with_suffix(".lnk")
            create_windows_shortcut(shortcut_path, target)
            logger.info("Created shortcut: %s", shortcut_path)
        except Exception as exc:
            logger.warning("Failed to create shortcut: %s", exc)

    def _save_record(self, record: MoveRecord) -> int:
        """Save move record to database."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.execute(
                """INSERT INTO move_records
                   (source_path, target_path, file_hash, file_size,
                    category, confidence, reason, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.source_path, record.target_path, record.file_hash,
                 record.file_size, record.category, record.confidence,
                 record.reason, record.status),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()
