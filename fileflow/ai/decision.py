"""Unified classification data structures and classifier interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from fileflow.analyzer.meta import FileMeta

Action = Literal["move", "skip", "review"]

INVALID_PATH_CHARS = re.compile(r'[<>:"\\|?*]')


@dataclass(slots=True)
class ClassifyResult:
    """Unified classification result for both heuristic and AI classifiers."""
    original_path: Path
    target_path: str           # relative to target_root, e.g. "文档/工作/会议纪要"
    suggested_rename: str | None
    confidence: float
    action: Action
    reason: str
    source: str                # "heuristic" | "rule_cache" | "llm"
    broad_category: str = "other"


class BatchClassifier(Protocol):
    """Protocol for classifiers that handle a batch of files."""
    def classify_batch(self, files: list["FileMeta"]) -> list[ClassifyResult]:
        """Return stable classification results for a batch of files."""
        ...


def fallback_top_level_for_category(category: str) -> str:
    return HeuristicClassifier.CATEGORY_TO_DIR.get(category, "其他")


def normalize_target_path(
    target_path: str | None,
    *,
    allowed_top_levels: list[str],
    fallback_top_level: str,
    max_depth: int,
) -> str:
    """Normalize and clamp a relative target path for safe execution."""
    raw = (target_path or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return fallback_top_level

    parts: list[str] = []
    for segment in raw.split("/"):
        cleaned = INVALID_PATH_CHARS.sub("_", segment).strip().strip(".")
        if not cleaned or cleaned in {".", ".."}:
            continue
        parts.append(cleaned)

    if not parts:
        return fallback_top_level

    if parts[0] not in allowed_top_levels:
        parts.insert(0, fallback_top_level)

    return "/".join(parts[:max_depth])


class HeuristicClassifier:
    """Extension-based heuristic classifier (Phase 1 baseline)."""

    CATEGORY_TO_DIR: dict[str, str] = {
        "document": "文档",
        "code": "代码项目",
        "image": "图片与设计",
        "installer": "安装包",
        "archive": "压缩包",
        "media": "视频音频",
        "other": "其他",
    }

    def classify_batch(self, files: list["FileMeta"]) -> list[ClassifyResult]:
        results = []
        for meta in files:
            top_dir = fallback_top_level_for_category(meta.broad_category)
            sub_dir = self._suggest_subdir(meta)
            target = f"{top_dir}/{sub_dir}" if sub_dir else top_dir
            is_known_category = meta.broad_category != "other"

            results.append(ClassifyResult(
                original_path=meta.path,
                target_path=target,
                suggested_rename=None,
                confidence=0.65 if is_known_category else 0.4,
                action="move" if is_known_category else "review",
                reason=f"extension-based: {meta.extension} -> {meta.broad_category}",
                source="heuristic",
                broad_category=meta.broad_category,
            ))
        return results

    def _suggest_subdir(self, meta: "FileMeta") -> str:
        ext = meta.extension.lower()
        cat = meta.broad_category

        if cat == "document":
            if ext in (".pdf",):
                return "PDF"
            if ext in (".docx", ".doc"):
                return "Word"
            if ext in (".xlsx", ".xls", ".csv"):
                return "表格"
            if ext in (".pptx", ".ppt"):
                return "演示文稿"
            if ext in (".md", ".txt"):
                return "文本"
            return ""

        if cat == "image":
            if ext in (".psd", ".ai", ".svg"):
                return "设计文件"
            return "照片"

        if cat == "media":
            if ext in (".mp3", ".flac", ".wav", ".aac", ".m4a"):
                return "音频"
            return "视频"

        return ""
