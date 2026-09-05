"""Safe file upload handling and sanitization utility."""

import os
import re
from fastapi import HTTPException, UploadFile, status

DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
CHUNK_SIZE = 64 * 1024  # 64 KB


def sanitize_filename(raw_filename: str | None) -> str:
    """Sanitize filename to prevent path traversal and shell execution risks."""
    if not raw_filename:
        return "uploaded_file"

    # Remove path directory separators (normalize backslashes for cross-platform POSIX/Windows safety)
    normalized = raw_filename.replace("\\", "/")
    filename = os.path.basename(normalized)
    # Remove null bytes
    filename = filename.replace("\0", "")
    # Remove any leading/trailing spaces or dots
    filename = filename.strip(". ")
    # Replace dangerous or control characters
    filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
    
    if not filename:
        return "uploaded_file"
    return filename


async def read_upload_file_safely(
    file: UploadFile,
    max_size_bytes: int = DEFAULT_MAX_FILE_SIZE
) -> bytes:
    """Read an uploaded file in chunks with strict size bounding.
    
    Prevents Out-Of-Memory (OOM) Denial of Service (DoS) attacks
    caused by reading unbounded payloads directly into RAM.
    """
    total_bytes = 0
    chunks = []

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_size_bytes:
            max_mb = max_size_bytes // (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum allowed size is {max_mb}MB."
            )
        chunks.append(chunk)

    return b"".join(chunks)


def validate_file_magic_bytes(content: bytes, ext: str) -> bool:
    """Validate that file content matches expected binary header signatures for the extension."""
    if not content:
        return False

    normalized_ext = ext.lower().strip(".")
    if normalized_ext == "pdf":
        return content.startswith(b"%PDF")
    if normalized_ext == "png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if normalized_ext in ("jpg", "jpeg"):
        return content.startswith(b"\xff\xd8\xff")
    if normalized_ext == "mp4":
        return len(content) >= 8 and content[4:8] == b"ftyp"
    if normalized_ext == "webm":
        return content.startswith(b"\x1a\x45\xdf\xa3")
    if normalized_ext == "mp3":
        return content.startswith(b"ID3") or (len(content) >= 2 and content[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"))
    if normalized_ext in ("zip", "docx"):
        return content.startswith(b"PK\x03\x04")
    if normalized_ext == "doc":
        return content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if normalized_ext == "txt":
        try:
            content[:1024].decode("utf-8")
            return b"\x00" not in content[:1024]
        except UnicodeDecodeError:
            return False
    return True
