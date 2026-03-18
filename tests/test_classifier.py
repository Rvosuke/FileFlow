"""Tests for fileflow.analyzer.classifier.classify_broad_category."""

import pytest

from fileflow.analyzer.classifier import classify_broad_category, CATEGORY_EXTENSIONS


# -- document extensions --

@pytest.mark.parametrize("ext", [".pdf", ".docx", ".txt", ".csv", ".xlsx", ".md", ".pptx", ".json"])
def test_document_extensions(ext: str) -> None:
    assert classify_broad_category(ext) == "document"


# -- code extensions --

@pytest.mark.parametrize("ext", [".py", ".js", ".ts", ".java", ".rs", ".go", ".cpp", ".html"])
def test_code_extensions(ext: str) -> None:
    assert classify_broad_category(ext) == "code"


# -- image extensions --

@pytest.mark.parametrize("ext", [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".psd", ".bmp"])
def test_image_extensions(ext: str) -> None:
    assert classify_broad_category(ext) == "image"


# -- installer extensions --

@pytest.mark.parametrize("ext", [".exe", ".msi", ".dmg", ".deb", ".pkg"])
def test_installer_extensions(ext: str) -> None:
    assert classify_broad_category(ext) == "installer"


# -- archive extensions --

@pytest.mark.parametrize("ext", [".zip", ".rar", ".7z", ".tar", ".gz"])
def test_archive_extensions(ext: str) -> None:
    assert classify_broad_category(ext) == "archive"


# -- media extensions --

@pytest.mark.parametrize("ext", [".mp4", ".mp3", ".wav", ".mkv", ".flac", ".avi"])
def test_media_extensions(ext: str) -> None:
    assert classify_broad_category(ext) == "media"


# -- unknown / other --

@pytest.mark.parametrize("ext", [".xyz", ".unknown", ".foobar", ""])
def test_unknown_extensions_return_other(ext: str) -> None:
    assert classify_broad_category(ext) == "other"


# -- case insensitivity --

@pytest.mark.parametrize("ext,expected", [
    (".PDF", "document"),
    (".Py", "code"),
    (".JPG", "image"),
    (".ZIP", "archive"),
    (".MP4", "media"),
    (".EXE", "installer"),
])
def test_case_insensitive_lookup(ext: str, expected: str) -> None:
    assert classify_broad_category(ext) == expected


# -- exhaustive: every registered extension maps to its category --

def test_all_registered_extensions_resolve_correctly() -> None:
    for category, extensions in CATEGORY_EXTENSIONS.items():
        for ext in extensions:
            result = classify_broad_category(ext)
            assert result == category, f"{ext} expected {category}, got {result}"
