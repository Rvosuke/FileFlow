"""Tests for analyzer/dedup.py."""

from __future__ import annotations

from pathlib import Path

from fileflow.analyzer.dedup import find_duplicates, sha256_file


def test_sha256_file(tmp_path: Path) -> None:
    f = tmp_path / "hello.txt"
    f.write_text("hello world")
    h = sha256_file(f)
    assert len(h) == 64
    assert h == sha256_file(f)  # deterministic


def test_find_duplicates_with_identical_files(tmp_path: Path) -> None:
    content = "duplicate content here"
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text(content)
    b.write_text(content)

    dupes = find_duplicates([a, b])
    assert len(dupes) == 1
    group = list(dupes.values())[0]
    assert len(group) == 2


def test_find_duplicates_no_duplicates(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("aaa")
    b.write_text("bbb")

    dupes = find_duplicates([a, b])
    assert dupes == {}


def test_find_duplicates_ignores_single_files(tmp_path: Path) -> None:
    a = tmp_path / "only.txt"
    a.write_text("unique")

    dupes = find_duplicates([a])
    assert dupes == {}


def test_find_duplicates_size_prefilter(tmp_path: Path) -> None:
    """Files with different sizes are never hashed."""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("short")
    b.write_text("this is much longer content")

    dupes = find_duplicates([a, b])
    assert dupes == {}


def test_find_duplicates_multiple_groups(tmp_path: Path) -> None:
    a1 = tmp_path / "a1.txt"
    a2 = tmp_path / "a2.txt"
    b1 = tmp_path / "b1.txt"
    b2 = tmp_path / "b2.txt"
    a1.write_text("group_a")
    a2.write_text("group_a")
    b1.write_text("group_b")
    b2.write_text("group_b")

    dupes = find_duplicates([a1, a2, b1, b2])
    assert len(dupes) == 2
