from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import mimetypes
from pathlib import Path

from fileflow.analyzer.classifier import classify_broad_category
from fileflow.analyzer.content import extract_preview
from fileflow.analyzer.dedup import sha256_file


@dataclass(slots=True)
class FileMeta:
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


def collect_file_meta(path: Path) -> FileMeta:
    stat = path.stat()
    extension = path.suffix.lower()
    category = classify_broad_category(extension)
    mime_type, _ = mimetypes.guess_type(str(path))

    return FileMeta(
        path=path.resolve(strict=False),
        name=path.stem,
        extension=extension,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_ctime),
        modified_at=datetime.fromtimestamp(stat.st_mtime),
        parent_dir=path.parent.name,
        sha256=sha256_file(path),
        mime_type=mime_type or "application/octet-stream",
        content_preview=extract_preview(path, category),
        broad_category=category,
    )
