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
