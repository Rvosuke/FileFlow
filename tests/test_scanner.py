"""Tests for scanner.py — file discovery and exclusion logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from fileflow.config import FileFlowConfig
from fileflow.scanner import FileScanner


def _make_scanner(tmp_path: Path, exclude_patterns: list[str] | None = None) -> FileScanner:
    config = FileFlowConfig()
    config.sources.paths = [str(tmp_path / "source")]
    if exclude_patterns is not None:
        config.sources.exclude_patterns = exclude_patterns
    config.sources.min_file_size_kb = 0  # allow tiny test files
    return FileScanner(config)


def _create_tree(tmp_path: Path, files: dict[str, str]) -> None:
    """Create a file tree under tmp_path/source. Keys are relative paths."""
    for rel, content in files.items():
        p = tmp_path / "source" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


class TestExcludePatterns:
    def test_simple_glob_excludes(self, tmp_path: Path) -> None:
        _create_tree(tmp_path, {
            "file.txt": "keep",
            "file.tmp": "skip",
        })
        scanner = _make_scanner(tmp_path, ["*.tmp"])
        result = scanner.scan()

        names = [f.name + f.extension for f in result.files]
        assert "file.txt" in names
        assert "file.tmp" not in names

    def test_nested_node_modules_excluded(self, tmp_path: Path) -> None:
        _create_tree(tmp_path, {
            "project/app.js": "code",
            "project/node_modules/pkg/index.js": "dep",
            "project/node_modules/pkg/lib/util.js": "dep",
        })
        scanner = _make_scanner(tmp_path, ["node_modules/**"])
        result = scanner.scan()

        names = [f.name + f.extension for f in result.files]
        assert "app.js" in names
        assert "index.js" not in names
        assert "util.js" not in names

    def test_nested_pycache_excluded(self, tmp_path: Path) -> None:
        _create_tree(tmp_path, {
            "main.py": "code",
            "pkg/__pycache__/main.cpython-312.pyc": "bytecode",
        })
        scanner = _make_scanner(tmp_path, ["__pycache__/**"])
        result = scanner.scan()

        names = [f.name + f.extension for f in result.files]
        assert "main.py" in names
        assert "main.cpython-312.pyc" not in names

    def test_nested_git_excluded(self, tmp_path: Path) -> None:
        _create_tree(tmp_path, {
            "readme.md": "docs",
            "subproject/.git/config": "git internal",
            "subproject/.git/HEAD": "git ref",
        })
        scanner = _make_scanner(tmp_path, [".git/**"])
        result = scanner.scan()

        names = [f.name + f.extension for f in result.files]
        assert "readme.md" in names
        assert "config" not in names
        assert "HEAD" not in names

    def test_top_level_node_modules_also_excluded(self, tmp_path: Path) -> None:
        _create_tree(tmp_path, {
            "node_modules/pkg/index.js": "dep",
            "app.py": "code",
        })
        scanner = _make_scanner(tmp_path, ["node_modules/**"])
        result = scanner.scan()

        names = [f.name + f.extension for f in result.files]
        assert "app.py" in names
        assert "index.js" not in names


class TestScanBasics:
    def test_empty_directory(self, tmp_path: Path) -> None:
        (tmp_path / "source").mkdir()
        scanner = _make_scanner(tmp_path)
        result = scanner.scan()
        assert result.files == []

    def test_nonexistent_source(self, tmp_path: Path) -> None:
        scanner = _make_scanner(tmp_path)  # source dir not created
        result = scanner.scan()
        assert result.files == []
        assert any("not found" in s.reason for s in result.skipped)

    def test_category_filter(self, tmp_path: Path) -> None:
        _create_tree(tmp_path, {
            "report.pdf": "pdf content here for size",
            "code.py": "python code here for size",
        })
        scanner = _make_scanner(tmp_path, [])
        result = scanner.scan(category_filter="document")

        categories = [f.broad_category for f in result.files]
        assert all(c == "document" for c in categories)

    def test_min_file_size_filter(self, tmp_path: Path) -> None:
        _create_tree(tmp_path, {
            "tiny.txt": "x",
        })
        config = FileFlowConfig()
        config.sources.paths = [str(tmp_path / "source")]
        config.sources.min_file_size_kb = 10  # 10KB min
        scanner = FileScanner(config)
        result = scanner.scan()

        assert result.files == []
        assert any("below min" in s.reason for s in result.skipped)
