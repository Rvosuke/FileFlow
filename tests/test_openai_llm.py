"""Tests for direct OpenAI Responses API integration."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from fileflow.ai.llm_client import LLMClient


@dataclass
class _FakeLLMConfig:
    provider: str = "openai"
    ollama_model: str = "qwen3:8b"
    ollama_url: str = "http://localhost:11434"
    openclaw_agent: str = "main"
    openai_model: str = "gpt-6-astra"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_reasoning_effort: str = "low"
    max_tokens: int = 500
    temperature: float = 0.1
    batch_size: int = 10


@dataclass
class _FakeConfig:
    llm: _FakeLLMConfig


def _make_client() -> LLMClient:
    return LLMClient(_FakeConfig(llm=_FakeLLMConfig()))


def test_openai_uses_gpt_6_astra_responses_api() -> None:
    client = _make_client()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": '[{"original_path":"a","target_path":"文档"}]',
                    }
                ],
            }
        ]
    }

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
        with patch("fileflow.ai.llm_client.httpx.post", return_value=mock_response) as post:
            result = client._call_openai("classify this")

    assert result == '[{"original_path":"a","target_path":"文档"}]'
    mock_response.raise_for_status.assert_called_once_with()

    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == "https://api.openai.com/v1/responses"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["model"] == "gpt-6-astra"
    assert kwargs["json"]["reasoning"] == {"effort": "low"}
    assert kwargs["json"]["max_output_tokens"] == 500
    assert "temperature" not in kwargs["json"]
    assert "top_p" not in kwargs["json"]


def test_openai_extracts_direct_output_text() -> None:
    assert LLMClient._extract_openai_output_text(
        {"output_text": " direct response "}
    ) == "direct response"


def test_openai_missing_api_key_raises() -> None:
    client = _make_client()
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            client._call_openai("classify this")


def test_openai_rejects_invalid_reasoning_effort() -> None:
    config = _FakeConfig(llm=_FakeLLMConfig(openai_reasoning_effort="none"))
    client = LLMClient(config)

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
        with pytest.raises(ValueError, match="reasoning effort"):
            client._call_openai("classify this")
