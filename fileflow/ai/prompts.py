"""Prompt templates for LLM-based file classification."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fileflow.analyzer.meta import FileMeta

CLASSIFY_SYSTEM = """\
你是一个文件整理助手。你的任务是根据文件信息决定每个文件应该被归类到哪个目录。
你应该像一个有强迫症的人类那样整理文件——保持一致、整洁、语义化。"""

CLASSIFY_PROMPT = """\
## 可用的顶层分类
{top_level_categories}

## 已有的目录结构（供参考，你可以建议新的子目录）
{existing_tree}

## 待分类文件
{file_info_batch}

## 规则
1. 返回 JSON 格式，每个文件一条记录
2. target_path 是相对于目标根目录的路径，如 "文档/工作/会议纪要"
3. 如果多个文件属于同一个项目/主题，归到同一个子目录
4. 文件名如果有明显的日期信息，可以加入年份子目录
5. confidence 为 0-1 的置信度，低于 0.6 时建议人工确认
6. 如果文件看起来是临时文件或垃圾文件，标记 action 为 "skip"
7. suggested_rename 仅在文件名不清晰时建议重命名，否则为 null
8. 目录深度不超过 {max_depth} 层

## 输出格式
严格返回 JSON 数组，不要包含其他文本：
```json
[
  {{{{
    "original_path": "...",
    "target_path": "文档/工作/会议纪要",
    "suggested_rename": null,
    "confidence": 0.85,
    "action": "move",
    "reason": "文件名包含meeting_notes，内容为会议纪要"
  }}}}
]
```"""


def build_file_info(meta: "FileMeta") -> dict:
    """Build a file info dict for the prompt from FileMeta."""
    return {
        "path": str(meta.path),
        "name": meta.name,
        "extension": meta.extension,
        "size_kb": round(meta.size_bytes / 1024, 1),
        "parent_dir": meta.parent_dir,
        "mime_type": meta.mime_type,
        "broad_category": meta.broad_category,
        "content_preview": meta.content_preview[:200] if meta.content_preview else "",
    }


def build_classify_prompt(
    files: list["FileMeta"],
    top_level_categories: list[str],
    existing_tree: str = "(empty)",
    max_depth: int = 3,
) -> str:
    """Build the full classification prompt for a batch of files."""
    import json

    file_infos = [build_file_info(f) for f in files]

    return CLASSIFY_PROMPT.format(
        top_level_categories="\n".join(f"- {c}" for c in top_level_categories),
        existing_tree=existing_tree,
        file_info_batch=json.dumps(file_infos, ensure_ascii=False, indent=2),
        max_depth=max_depth,
    )
