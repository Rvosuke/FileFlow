"""Tests for watcher.py — debounce and event handling."""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fileflow.watcher import _FileFlowHandler, DEBOUNCE_SECONDS


@dataclass
class _FakeConfig:
    @dataclass
    class _General:
        target_root: str = "target"
        create_shortcut: bool = False
    @dataclass
    class _Sources:
        paths: list[str] = field(default_factory=list)
    general: _General = field(default_factory=_General)
    sources: _Sources = field(default_factory=_Sources)


def _make_handler(tmp_path: Path, execute: bool = False, use_ai: bool = False):
    config = _FakeConfig()
    db_path = tmp_path / "ff.db"
    return _FileFlowHandler(config, db_path, execute=execute, use_ai=use_ai)


# ── Event filtering ──


class TestEventFiltering:
    def test_directory_created_ignored(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        event = MagicMock()
        event.is_directory = True
        event.src_path = str(tmp_path / "somedir")
        handler.on_created(event)
        assert handler._pending == {}

    def test_directory_moved_ignored(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        event = MagicMock()
        event.is_directory = True
        event.dest_path = str(tmp_path / "somedir")
        handler.on_moved(event)
        assert handler._pending == {}

    def test_file_created_schedules(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "test.txt")
        handler.on_created(event)
        assert str(tmp_path / "test.txt") in handler._pending
        # Cancel timer to avoid side effects
        if handler._timer:
            handler._timer.cancel()

    def test_file_moved_schedules_dest(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        event = MagicMock()
        event.is_directory = False
        event.dest_path = str(tmp_path / "moved.txt")
        handler.on_moved(event)
        assert str(tmp_path / "moved.txt") in handler._pending
        if handler._timer:
            handler._timer.cancel()


# ── Debounce ──


class TestDebounce:
    def test_schedule_sets_timer(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        handler._schedule(str(tmp_path / "a.txt"))
        assert handler._timer is not None
        assert handler._timer.is_alive()
        handler._timer.cancel()

    def test_rapid_events_reset_timer(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        handler._schedule(str(tmp_path / "a.txt"))
        first_timer = handler._timer
        handler._schedule(str(tmp_path / "b.txt"))
        second_timer = handler._timer

        assert first_timer is not second_timer
        assert len(handler._pending) == 2
        second_timer.cancel()

    def test_process_pending_clears_ready(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        # Manually set a pending file with old timestamp
        old_time = time.time() - DEBOUNCE_SECONDS - 1
        path_str = str(tmp_path / "old.txt")
        handler._pending[path_str] = old_time

        # Mock _classify_and_act to prevent actual classification
        handler._classify_and_act = MagicMock()
        handler._process_pending()

        # The entry should be removed from pending since file doesn't exist
        assert path_str not in handler._pending

    def test_recent_files_not_processed(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        path_str = str(tmp_path / "recent.txt")
        handler._pending[path_str] = time.time()  # just now

        handler._classify_and_act = MagicMock()
        handler._process_pending()

        # Should still be pending since it's too recent
        assert path_str in handler._pending
        handler._classify_and_act.assert_not_called()


# ── Classification integration ──


class TestClassifyAndAct:
    def test_preview_mode_does_not_move(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path, execute=False)

        src = tmp_path / "test.pdf"
        src.write_text("content")

        with patch("fileflow.ai.decision.HeuristicClassifier") as MockClassifier:
            from fileflow.ai.decision import ClassifyResult
            mock_cr = ClassifyResult(
                original_path=src,
                target_path="文档/PDF",
                suggested_rename=None,
                confidence=0.65,
                action="move",
                reason="heuristic",
                source="heuristic",
                broad_category="document",
            )
            MockClassifier.return_value.classify_batch.return_value = [mock_cr]

            handler._classify_and_act([src])

        assert src.exists(), "preview mode should not move files"

    def test_skip_action_ignored(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path, execute=True)

        src = tmp_path / "temp.tmp"
        src.write_text("tmp")

        with patch("fileflow.ai.decision.HeuristicClassifier") as MockClassifier:
            from fileflow.ai.decision import ClassifyResult
            mock_cr = ClassifyResult(
                original_path=src,
                target_path="其他",
                suggested_rename=None,
                confidence=0.3,
                action="skip",
                reason="low confidence",
                source="heuristic",
            )
            MockClassifier.return_value.classify_batch.return_value = [mock_cr]

            handler._classify_and_act([src])

        assert src.exists(), "skip action should not move files"

    def test_empty_paths_no_error(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        # Should not raise
        handler._classify_and_act([])


# ── Handler state ──


class TestHandlerState:
    def test_initial_state(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        assert handler._pending == {}
        assert handler._timer is None
        assert handler.execute is False
        assert handler.use_ai is False

    def test_execute_flag(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path, execute=True, use_ai=True)
        assert handler.execute is True
        assert handler.use_ai is True
