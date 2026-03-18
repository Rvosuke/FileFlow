from pathlib import Path
import zipfile
import tarfile
import json
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


def test_collect_file_meta_for_tar_file(tmp_path: Path) -> None:
    tar_path = tmp_path / "archive.tar"
    with tarfile.open(tar_path, "w") as archive:
        info = tarfile.TarInfo(name="nested/file.txt")
        import io
        archive.addfile(info, fileobj=io.BytesIO(b"hello"))

    meta = collect_file_meta(tar_path)

    assert meta.broad_category == "archive"
    assert "nested/file.txt" in meta.content_preview


def test_collect_file_meta_for_json_file(tmp_path: Path) -> None:
    json_path = tmp_path / "data.json"
    data = {"key": "value", "list": [1, 2, 3]}
    json_path.write_text(json.dumps(data), encoding="utf-8")

    meta = collect_file_meta(json_path)

    assert meta.broad_category == "document"
    assert '"key": "value"' in meta.content_preview


def test_collect_file_meta_for_image_file(tmp_path: Path) -> None:
    png_path = tmp_path / "test.png"
    # Valid PNG header + IHDR chunk with 100x200 dimensions
    import struct
    png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 100, 200) + b"\x08\x02\x00\x00\x00"
    png_path.write_bytes(png_header)

    meta = collect_file_meta(png_path)

    assert meta.broad_category == "image"
    assert "100x200" in meta.content_preview
