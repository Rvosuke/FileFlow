from pathlib import Path
import zipfile

from fileflow.analyzer.meta import collect_file_meta


def test_collect_file_meta_for_code_file(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text("import os\n\nprint('hello')\n", encoding="utf-8")

    meta = collect_file_meta(source)

    assert meta.name == "example"
    assert meta.extension == ".py"
    assert meta.broad_category == "code"
    assert "import os" in meta.content_preview
    assert len(meta.sha256) == 64


def test_collect_file_meta_for_zip_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("nested/file.txt", "hello")

    meta = collect_file_meta(archive_path)

    assert meta.broad_category == "archive"
    assert "nested/file.txt" in meta.content_preview
