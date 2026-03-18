from __future__ import annotations

from pathlib import Path
import zipfile
import tarfile
import json


PREVIEW_CHAR_LIMIT = 500


def truncate_preview(value: str, limit: int = PREVIEW_CHAR_LIMIT) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def read_text_with_fallbacks(path: Path, max_bytes: int = 8192) -> str:
    payload = path.read_bytes()[:max_bytes]
    for encoding in ("utf-8", "utf-16", "gb18030", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def extract_text_preview(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "PDF preview requires a parser and is deferred to a later phase."
    if suffix == ".json":
        return extract_json_preview(path)
    return truncate_preview(read_text_with_fallbacks(path))


def extract_json_preview(path: Path) -> str:
    try:
        data = json.loads(read_text_with_fallbacks(path))
        return truncate_preview(json.dumps(data, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        return truncate_preview(read_text_with_fallbacks(path))


def extract_code_header(path: Path) -> str:
    text = read_text_with_fallbacks(path)
    head = text.splitlines()[:20]
    imports = [
        line.strip()
        for line in head
        if line.lstrip().startswith(("import ", "from ", "using ", "#include ", "package "))
    ]
    body = "\n".join(head)
    if imports:
        body = "imports: " + "; ".join(imports[:5]) + "\n" + body
    return truncate_preview(body)


import struct


def extract_image_exif(path: Path) -> str:
    """Extract basic image dimensions without external dependencies."""
    suffix = path.suffix.lower()
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            data = f.read(32)
            
            if suffix == ".png":
                # PNG dimensions are at offset 16
                if data[12:16] == b"IHDR":
                    w, h = struct.unpack(">II", data[16:24])
                    return f"PNG Image, {w}x{h}, {size} bytes"
            
            elif suffix in (".jpg", ".jpeg"):
                # JPEG is more complex to parse without a library, but we can try to find the SOF marker
                f.seek(0)
                data = f.read(2)
                if data == b"\xff\xd8": # SOI
                    while True:
                        marker = f.read(2)
                        if not marker or marker[0] != 0xff:
                            break
                        if marker[1] in (0xc0, 0xc1, 0xc2, 0xc3): # SOF markers
                            f.read(3) # length + precision
                            h, w = struct.unpack(">HH", f.read(4))
                            return f"JPEG Image, {w}x{h}, {size} bytes"
                        # Skip this segment
                        seg_len_data = f.read(2)
                        if not seg_len_data:
                            break
                        seg_len = struct.unpack(">H", seg_len_data)[0]
                        f.seek(seg_len - 2, 1)
        
        return f"Image, {path.suffix.upper()[1:]} format, {size} bytes (Full EXIF requires Pillow)"
    except Exception as exc:
        return f"image preview unavailable: {exc}"


def extract_archive_listing(path: Path) -> str:
    suffix = path.suffix.lower()
    names = []
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()[:10]
        elif suffix in (".tar", ".gz", ".bz2", ".xz", ".tgz"):
            with tarfile.open(path) as archive:
                names = [m.name for m in archive.getmembers()[:10]]
        else:
            return f"archive listing preview pending for {suffix} files"
    except (zipfile.BadZipFile, tarfile.TarError) as exc:
        return f"archive error: {exc}"
    
    if not names:
        return "empty archive"
    return truncate_preview("\n".join(names))


def extract_installer_info(path: Path) -> str:
    return f"installer metadata preview pending for {path.suffix.lower()} files"


def extract_media_info(path: Path) -> str:
    return f"media metadata preview pending for {path.suffix.lower()} files"


PREVIEW_STRATEGIES = {
    "document": extract_text_preview,
    "code": extract_code_header,
    "image": extract_image_exif,
    "archive": extract_archive_listing,
    "installer": extract_installer_info,
    "media": extract_media_info,
}


def extract_preview(path: Path, category: str) -> str:
    strategy = PREVIEW_STRATEGIES.get(category, extract_text_preview)
    try:
        return truncate_preview(strategy(path))
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        return f"preview unavailable: {exc}"
