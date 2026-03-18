"""LLM abstraction layer — supports Ollama and OpenClaw agent."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, TYPE_CHECKING

import httpx

from fileflow.ai.decision import (
    ClassifyResult,
    fallback_top_level_for_category,
    normalize_target_path,
)
from fileflow.ai.prompts import CLASSIFY_SYSTEM, build_classify_prompt

if TYPE_CHECKING:
    from fileflow.analyzer.meta import FileMeta
    from fileflow.config import FileFlowConfig

logger = logging.getLogger("fileflow.llm")


class LLMClient:
    """Unified LLM client with provider routing."""

    def __init__(self, config: "FileFlowConfig"):
        self.config = config
        self.provider = config.llm.provider
        self.last_parse_stats = {
            "raw_items": 0,
            "matched_items": 0,
            "unknown_paths": 0,
        }

    def classify(
        self,
        files: list["FileMeta"],
        top_level_categories: list[str],
        existing_tree: str = "(empty)",
        max_depth: int = 3,
    ) -> list[ClassifyResult]:
        """Send a classification request to the configured LLM provider."""
        prompt = build_classify_prompt(
            files, top_level_categories, existing_tree, max_depth,
        )

        raw_response = self._call_llm(prompt)
        return self._parse_response(
            raw_response,
            files,
            top_level_categories=top_level_categories,
            max_depth=max_depth,
        )

    def _call_llm(self, prompt: str) -> str:
        """Route to the correct provider."""
        if self.provider == "ollama":
            return self._call_ollama(prompt)
        if self.provider == "openclaw":
            return self._call_openclaw(prompt)
        raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama local API."""
        url = f"{self.config.llm.ollama_url}/api/chat"
        payload = {
            "model": self.config.llm.ollama_model,
            "messages": [
                {"role": "system", "content": CLASSIFY_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self.config.llm.temperature,
                "num_predict": self.config.llm.max_tokens,
            },
        }
        logger.info("Calling Ollama: model=%s", self.config.llm.ollama_model)
        resp = httpx.post(url, json=payload, timeout=120.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    @staticmethod
    def _openclaw_node_cmd() -> list[str]:
        """Return [node, openclaw.mjs] to bypass .cmd wrapper encoding issues."""
        cmd_path = (
            shutil.which("openclaw")
            or shutil.which("openclaw.cmd")
            or shutil.which("openclaw.ps1")
        )
        if cmd_path is None:
            raise FileNotFoundError("openclaw not found in PATH")
        cmd = Path(cmd_path)
        if cmd.suffix.lower() in {".js", ".mjs"}:
            node = shutil.which("node")
            if node:
                return [node, str(cmd)]
            return [str(cmd)]

        if sys.platform == "win32" and cmd.suffix.lower() in {".cmd", ".ps1"}:
            candidates = [
                cmd.parent / "node_modules" / "openclaw" / "openclaw.mjs",
                cmd.parent.parent / "node_modules" / "openclaw" / "openclaw.mjs",
            ]
            node = shutil.which("node")
            if node:
                for mjs in candidates:
                    if mjs.exists():
                        return [node, str(mjs)]
        return [str(cmd)]

    def _call_openclaw(self, prompt: str) -> str:
        """Call OpenClaw via local agent subprocess."""
        agent_id = getattr(self.config.llm, "openclaw_agent", "main")
        # Combine system + user into one message so the agent outputs clean JSON.
        # On Windows, subprocess argument encoding can mangle non-ASCII chars.
        # Replace non-ASCII with \uXXXX escapes (leaving ASCII like \ unchanged).
        combined = f"{CLASSIFY_SYSTEM}\n\n{prompt}"
        if sys.platform == "win32":
            combined = "".join(
                c if ord(c) < 128 else f"\\u{ord(c):04x}" for c in combined
            )
        logger.info("Calling OpenClaw agent (id=%s)", agent_id)
        try:
            session_id = f"ff-classify-{uuid.uuid4().hex[:8]}"
            cmd = self._openclaw_node_cmd() + [
                "agent", "--local", "--agent", agent_id,
                "--session-id", session_id,
                "--message", combined,
            ]
            env = {**__import__("os").environ, "FORCE_COLOR": "0"}
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
                env=env,
            )
            if result.returncode != 0:
                logger.error("OpenClaw agent error: %s", result.stderr[:300])
                return ""
            # The model response is always UTF-8, regardless of platform
            return result.stdout.decode("utf-8", errors="replace").strip()
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.error("OpenClaw subprocess failed: %s", exc)
            return ""

    def _parse_response(
        self,
        raw: str,
        files: list["FileMeta"],
        *,
        top_level_categories: list[str],
        max_depth: int,
    ) -> list[ClassifyResult]:
        """Parse LLM JSON response into ClassifyResult list."""
        self.last_parse_stats = {
            "raw_items": 0,
            "matched_items": 0,
            "unknown_paths": 0,
        }
        # Extract JSON from markdown code blocks if present
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        json_str = json_match.group(1) if json_match else raw.strip()

        items = self._load_json_items(json_str)
        if items is None:
            logger.error("Failed to parse LLM response as JSON: %s", raw[:200])
            return []

        if not isinstance(items, list):
            logger.error("LLM response is not a list")
            return []

        self.last_parse_stats["raw_items"] = len(items)

        # Build path lookup for matching results back to files
        path_lookup = {str(f.path): f for f in files}

        results = []
        for item in items:
            original = item.get("original_path", "")
            meta = path_lookup.get(original)
            if not meta:
                self.last_parse_stats["unknown_paths"] += 1
                logger.warning("LLM returned unknown path: %s", original)
                continue

            action = item.get("action", "move")
            if action not in ("move", "skip", "review"):
                action = "move"

            confidence = float(item.get("confidence", 0.5))
            if confidence < 0.6:
                action = "review"

            safe_target_path = normalize_target_path(
                item.get("target_path", ""),
                allowed_top_levels=top_level_categories,
                fallback_top_level=fallback_top_level_for_category(meta.broad_category),
                max_depth=max_depth,
            )

            results.append(ClassifyResult(
                original_path=meta.path,
                target_path=safe_target_path,
                suggested_rename=item.get("suggested_rename"),
                confidence=confidence,
                action=action,
                reason=item.get("reason", ""),
                source="llm",
                broad_category=meta.broad_category,
            ))

        self.last_parse_stats["matched_items"] = len(results)
        return results

    @staticmethod
    def _load_json_items(raw: str) -> list[dict[str, Any]] | None:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            sanitized = re.sub(
                r'("(?:(?:original|target)_path|suggested_rename)"\s*:\s*")([^"]*)(")',
                lambda m: f'{m.group(1)}{m.group(2).replace("\\", "\\\\")}{m.group(3)}',
                raw,
            )
            sanitized = re.sub(r'(?<!\\)\\(?!["\\/])', r"\\\\", sanitized)
            if sanitized == raw:
                return None
            try:
                return json.loads(sanitized)
            except json.JSONDecodeError:
                return None
