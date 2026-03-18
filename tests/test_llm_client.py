"""Tests for ai/llm_client.py — LLM response parsing and provider fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from fileflow.ai.llm_client import LLMClient
from fileflow.ai.decision import ClassifyResult


@dataclass
class _FakeFileMeta:
    path: Path
    name: str
    extension: str
    size_bytes: int
    created_at: datetime
    modified_at: datetime
    parent_dir: str
    sha256: str
    mime_type: str
    content_preview: str
    broad_category: str


@dataclass
class _FakeLLMConfig:
    provider: str = "openclaw"
    ollama_model: str = "qwen3:8b"
    ollama_url: str = "http://localhost:11434"
    max_tokens: int = 500
    temperature: float = 0.1
    batch_size: int = 10


@dataclass
class _FakeConfig:
    llm: _FakeLLMConfig


def _meta(tmp_path: Path, name: str = "report", ext: str = ".pdf") -> _FakeFileMeta:
    return _FakeFileMeta(
        path=tmp_path / f"{name}{ext}",
        name=name,
        extension=ext,
        size_bytes=1024,
        created_at=datetime.now(),
        modified_at=datetime.now(),
        parent_dir="Downloads",
        sha256="abc123",
        mime_type="application/pdf",
        content_preview="some content",
        broad_category="document",
    )


def _make_client(provider: str = "openclaw") -> LLMClient:
    config = _FakeConfig(llm=_FakeLLMConfig(provider=provider))
    return LLMClient(config)


# ── Response parsing ──


class TestParseResponse:
    def test_parse_valid_json_array(self, tmp_path: Path) -> None:
        client = _make_client()
        meta = _meta(tmp_path)
        raw = json.dumps([{
            "original_path": str(meta.path),
            "target_path": "文档/报告",
            "suggested_rename": None,
            "confidence": 0.9,
            "action": "move",
            "reason": "looks like a report",
        }])
        results = client._parse_response(
            raw, [meta],
            top_level_categories=["文档", "其他"],
            max_depth=3,
        )
        assert len(results) == 1
        assert results[0].target_path == "文档/报告"
        assert results[0].confidence == 0.9
        assert results[0].source == "llm"

    def test_parse_json_in_markdown_code_block(self, tmp_path: Path) -> None:
        client = _make_client()
        meta = _meta(tmp_path)
        # Use json.dumps to properly escape Windows backslashes in path
        inner = json.dumps([{
            "original_path": str(meta.path),
            "target_path": "文档/PDF",
            "confidence": 0.85,
            "action": "move",
            "reason": "pdf document",
        }])
        raw = f"```json\n{inner}\n```"
        results = client._parse_response(
            raw, [meta],
            top_level_categories=["文档", "其他"],
            max_depth=3,
        )
        assert len(results) == 1
        assert results[0].target_path == "文档/PDF"

    def test_parse_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        client = _make_client()
        meta = _meta(tmp_path)
        results = client._parse_response(
            "this is not json at all",
            [meta],
            top_level_categories=["文档"],
            max_depth=3,
        )
        assert results == []

    def test_parse_non_list_json_returns_empty(self, tmp_path: Path) -> None:
        client = _make_client()
        meta = _meta(tmp_path)
        results = client._parse_response(
            '{"single": "object"}',
            [meta],
            top_level_categories=["文档"],
            max_depth=3,
        )
        assert results == []

    def test_parse_unknown_path_skipped(self, tmp_path: Path) -> None:
        client = _make_client()
        meta = _meta(tmp_path)
        raw = json.dumps([{
            "original_path": "C:/nonexistent/file.pdf",
            "target_path": "文档/报告",
            "confidence": 0.9,
            "action": "move",
            "reason": "unknown",
        }])
        results = client._parse_response(
            raw, [meta],
            top_level_categories=["文档"],
            max_depth=3,
        )
        assert results == []
        assert client.last_parse_stats == {
            "raw_items": 1,
            "matched_items": 0,
            "unknown_paths": 1,
        }

    def test_low_confidence_becomes_review(self, tmp_path: Path) -> None:
        client = _make_client()
        meta = _meta(tmp_path)
        raw = json.dumps([{
            "original_path": str(meta.path),
            "target_path": "文档/不确定",
            "confidence": 0.4,
            "action": "move",
            "reason": "not sure",
        }])
        results = client._parse_response(
            raw, [meta],
            top_level_categories=["文档", "其他"],
            max_depth=3,
        )
        assert len(results) == 1
        assert results[0].action == "review"

    def test_invalid_action_defaults_to_move(self, tmp_path: Path) -> None:
        client = _make_client()
        meta = _meta(tmp_path)
        raw = json.dumps([{
            "original_path": str(meta.path),
            "target_path": "文档/报告",
            "confidence": 0.9,
            "action": "invalid_action",
            "reason": "test",
        }])
        results = client._parse_response(
            raw, [meta],
            top_level_categories=["文档", "其他"],
            max_depth=3,
        )
        assert results[0].action == "move"

    def test_target_path_normalized(self, tmp_path: Path) -> None:
        client = _make_client()
        meta = _meta(tmp_path)
        raw = json.dumps([{
            "original_path": str(meta.path),
            "target_path": "C:/absolute/path/evil",
            "confidence": 0.9,
            "action": "move",
            "reason": "test",
        }])
        results = client._parse_response(
            raw, [meta],
            top_level_categories=["文档", "其他"],
            max_depth=3,
        )
        # Absolute path should be rejected and fallback used
        assert not results[0].target_path.startswith("C:")

    def test_multiple_files_parsed(self, tmp_path: Path) -> None:
        client = _make_client()
        meta1 = _meta(tmp_path, name="a", ext=".pdf")
        meta2 = _meta(tmp_path, name="b", ext=".docx")
        raw = json.dumps([
            {
                "original_path": str(meta1.path),
                "target_path": "文档/PDF",
                "confidence": 0.9,
                "action": "move",
                "reason": "pdf",
            },
            {
                "original_path": str(meta2.path),
                "target_path": "文档/Word",
                "confidence": 0.85,
                "action": "move",
                "reason": "word doc",
            },
        ])
        results = client._parse_response(
            raw, [meta1, meta2],
            top_level_categories=["文档", "其他"],
            max_depth=3,
        )
        assert len(results) == 2


# ── Provider fallback ──


class TestProviderFallback:
    def test_openclaw_cmd_wrapper_uses_node_mjs(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        cmd_path = bin_dir / "openclaw.cmd"
        cmd_path.parent.mkdir(parents=True, exist_ok=True)
        cmd_path.write_text("@echo off\r\n", encoding="utf-8")

        mjs_path = tmp_path / "node_modules" / "openclaw" / "openclaw.mjs"
        mjs_path.parent.mkdir(parents=True, exist_ok=True)
        mjs_path.write_text("console.log('ok')\n", encoding="utf-8")

        node_path = tmp_path / "node.exe"
        node_path.write_text("", encoding="utf-8")

        def fake_which(name: str) -> str | None:
            mapping = {
                "openclaw": None,
                "openclaw.cmd": str(cmd_path),
                "openclaw.ps1": None,
                "node": str(node_path),
            }
            return mapping.get(name)

        with patch("fileflow.ai.llm_client.shutil.which", side_effect=fake_which):
            with patch("fileflow.ai.llm_client.sys.platform", "win32"):
                assert LLMClient._openclaw_node_cmd() == [str(node_path), str(mjs_path)]

    def test_openclaw_ps1_wrapper_uses_node_mjs(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        ps1_path = scripts_dir / "openclaw.ps1"
        ps1_path.parent.mkdir(parents=True, exist_ok=True)
        ps1_path.write_text("Write-Host ok\n", encoding="utf-8")

        mjs_path = scripts_dir / "node_modules" / "openclaw" / "openclaw.mjs"
        mjs_path.parent.mkdir(parents=True, exist_ok=True)
        mjs_path.write_text("console.log('ok')\n", encoding="utf-8")

        node_path = tmp_path / "node.exe"
        node_path.write_text("", encoding="utf-8")

        def fake_which(name: str) -> str | None:
            mapping = {
                "openclaw": None,
                "openclaw.cmd": None,
                "openclaw.ps1": str(ps1_path),
                "node": str(node_path),
            }
            return mapping.get(name)

        with patch("fileflow.ai.llm_client.shutil.which", side_effect=fake_which):
            with patch("fileflow.ai.llm_client.sys.platform", "win32"):
                assert LLMClient._openclaw_node_cmd() == [str(node_path), str(mjs_path)]

    def test_openclaw_returns_stdout_on_success(self) -> None:
        client = _make_client("openclaw")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'[{"test": true}]'

        with patch("fileflow.ai.llm_client.subprocess.run", return_value=mock_result) as mock_run:
            with patch.object(client, "_openclaw_node_cmd", return_value=["openclaw"]):
                result = client._call_openclaw("test prompt")

        assert result == '[{"test": true}]'
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "--local" in call_args

    def test_openclaw_returns_empty_on_failure(self) -> None:
        client = _make_client("openclaw")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"some error"
        mock_result.stdout = b""

        with patch("fileflow.ai.llm_client.subprocess.run", return_value=mock_result):
            with patch.object(client, "_openclaw_node_cmd", return_value=["openclaw"]):
                result = client._call_openclaw("test prompt")

        assert result == ""

    def test_openclaw_returns_empty_on_file_not_found(self) -> None:
        client = _make_client("openclaw")
        with patch("fileflow.ai.llm_client.subprocess.run", side_effect=FileNotFoundError("openclaw not found")):
            with patch.object(client, "_openclaw_node_cmd", return_value=["openclaw"]):
                result = client._call_openclaw("test prompt")
        assert result == ""

    def test_unsupported_provider_raises(self) -> None:
        client = _make_client("nonexistent")
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            client._call_llm("test")


# ── End-to-end with mocked HTTP ──


class TestClassifyWithMockedHTTP:
    def test_classify_calls_provider_and_parses(self, tmp_path: Path) -> None:
        client = _make_client("ollama")
        meta = _meta(tmp_path)

        llm_response = json.dumps([{
            "original_path": str(meta.path),
            "target_path": "文档/报告",
            "confidence": 0.88,
            "action": "move",
            "reason": "PDF report",
        }])

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": llm_response}}
        mock_resp.raise_for_status = MagicMock()

        with patch("fileflow.ai.llm_client.httpx.post", return_value=mock_resp):
            results = client.classify(
                [meta],
                top_level_categories=["文档", "其他"],
            )

        assert len(results) == 1
        assert results[0].target_path == "文档/报告"
        assert results[0].source == "llm"
