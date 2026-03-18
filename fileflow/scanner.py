from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from time import perf_counter

from fileflow.analyzer.meta import FileMeta, collect_file_meta
from fileflow.config import FileFlowConfig


@dataclass(slots=True)
class SkippedFile:
    path: Path
    reason: str


@dataclass(slots=True)
class ScanResult:
    files: list[FileMeta]
    skipped: list[SkippedFile]
    duration_ms: int


class FileScanner:
    def __init__(self, config: FileFlowConfig):
        self.config = config

    def scan(self, scan_path: Path | None = None, category_filter: str | None = None) -> ScanResult:
        roots = [scan_path] if scan_path else [Path(path) for path in self.config.sources.paths]
        files: list[FileMeta] = []
        skipped: list[SkippedFile] = []
        started = perf_counter()

        for root in roots:
            resolved_root = Path(root).expanduser().resolve(strict=False)
            if not resolved_root.exists():
                skipped.append(SkippedFile(path=resolved_root, reason="source path not found"))
                continue

            for candidate in self._iter_candidates(resolved_root):
                if not candidate.is_file():
                    continue

                try:
                    reason = self._skip_reason(candidate, resolved_root)
                except OSError as exc:
                    skipped.append(SkippedFile(path=candidate, reason=str(exc)))
                    continue

                if reason is not None:
                    skipped.append(SkippedFile(path=candidate, reason=reason))
                    continue

                try:
                    meta = collect_file_meta(candidate)
                except OSError as exc:
                    skipped.append(SkippedFile(path=candidate, reason=str(exc)))
                    continue

                if category_filter and meta.broad_category != category_filter:
                    continue
                files.append(meta)

        duration_ms = int((perf_counter() - started) * 1000)
        return ScanResult(files=files, skipped=skipped, duration_ms=duration_ms)

    def _iter_candidates(self, root: Path):
        if self.config.sources.scan_recursive:
            return root.rglob("*")
        return root.iterdir()

    def _skip_reason(self, path: Path, root: Path) -> str | None:
        if self._is_under_protected_path(path):
            return "protected path"
        if self._matches_exclude(path, root):
            return "excluded by pattern"

        size_bytes = path.stat().st_size
        if size_bytes < self.config.sources.min_file_size_kb * 1024:
            return "below min file size"
        if size_bytes > self.config.sources.max_file_size_mb * 1024 * 1024:
            return "above max file size"
        return None

    def _is_under_protected_path(self, path: Path) -> bool:
        resolved = path.resolve(strict=False)
        for protected in self.config.safety.protected_paths:
            protected_path = Path(protected).expanduser().resolve(strict=False)
            if resolved == protected_path or resolved.is_relative_to(protected_path):
                return True
        return False

    def _matches_exclude(self, path: Path, root: Path) -> bool:
        relative = path.relative_to(root).as_posix()
        name = path.name
        for pattern in self.config.sources.exclude_patterns:
            if fnmatch(relative, pattern) or fnmatch(name, pattern):
                return True
            # Handle directory-based patterns like "node_modules/**":
            # check if any ancestor directory matches the pattern prefix
            dir_pattern = pattern.rstrip("/*")
            if dir_pattern != pattern:
                for part in path.relative_to(root).parts:
                    if fnmatch(part, dir_pattern):
                        return True
        return False
