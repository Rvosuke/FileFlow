from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fileflow.ai.llm_client import LLMClient


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


def _make_client() -> LLMClient:
    return LLMClient(_FakeConfig(llm=_FakeLLMConfig()))


def _meta(tmp_path: Path) -> _FakeFileMeta:
    return _FakeFileMeta(
        path=tmp_path / "report.pdf",
        name="report",
        extension=".pdf",
        size_bytes=1024,
        created_at=datetime.now(),
        modified_at=datetime.now(),
        parent_dir="Downloads",
        sha256="abc123",
        mime_type="application/pdf",
        content_preview="some content",
        broad_category="document",
    )


def test_parse_response_accepts_markdown_code_block_with_windows_path(tmp_path: Path) -> None:
    import json as _json
    client = _make_client()
    meta = _meta(tmp_path)
    # Use json.dumps to properly escape Windows backslashes in the path
    inner = _json.dumps([{
        "original_path": str(meta.path),
        "target_path": "文档/PDF",
        "confidence": 0.85,
        "action": "move",
        "reason": "pdf document",
    }])
    raw = f"Here is the result:\n\n```json\n{inner}\n```\n"

    results = client._parse_response(
        raw,
        [meta],
        top_level_categories=["文档", "其他"],
        max_depth=3,
    )

    assert len(results) == 1
    assert results[0].target_path == "文档/PDF"
    assert results[0].source == "llm"
