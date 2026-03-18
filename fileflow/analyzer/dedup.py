from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(paths: list[Path]) -> dict[str, list[Path]]:
    """Find duplicate files by SHA-256 hash.

    Returns a dict mapping hash -> list of paths (only entries with 2+ files).
    """
    # First pass: group by file size (cheap filter)
    size_groups: dict[int, list[Path]] = defaultdict(list)
    for p in paths:
        if p.is_file():
            try:
                size_groups[p.stat().st_size].append(p)
            except OSError:
                continue

    # Second pass: hash only files with matching sizes
    hash_groups: dict[str, list[Path]] = defaultdict(list)
    for size, group in size_groups.items():
        if len(group) < 2:
            continue
        for p in group:
            try:
                h = sha256_file(p)
                hash_groups[h].append(p)
            except OSError:
                continue

    # Filter to actual duplicates (2+ files with same hash)
    return {h: files for h, files in hash_groups.items() if len(files) >= 2}
