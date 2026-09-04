"""MinIO object storage client with resilient local storage fallback."""

import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

from minio import Minio

from app.core.config import settings

logger = logging.getLogger("app.clients.minio")

_minio_client: Optional[Minio] = None

LOCAL_STORAGE_DIR = Path("/tmp/storage") if os.name != "nt" else Path("./data/storage")
LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_minio_client() -> Optional[Minio]:
    """Get or initialize the shared Minio client with graceful fallback."""
    global _minio_client
    if _minio_client is None:
        try:
            endpoint = settings.MINIO_ENDPOINT
            if endpoint.startswith("https://"):
                endpoint = endpoint[len("https://"):]
            elif endpoint.startswith("http://"):
                endpoint = endpoint[len("http://"):]
            endpoint = endpoint.rstrip("/")

            client = Minio(
                endpoint=endpoint,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
            # Ensure bucket exists
            if not client.bucket_exists(settings.MINIO_BUCKET_NAME):
                client.make_bucket(settings.MINIO_BUCKET_NAME)
            _minio_client = client
        except Exception as e:
            logger.info("Object storage using resilient local fallback (%s)", e)
            return None
    return _minio_client


class MinioClient:
    """Wrapper class for MinIO operations with local filesystem fallback."""

    def __init__(self) -> None:
        self.client = get_minio_client()
        self.bucket = settings.MINIO_BUCKET_NAME

    def upload_file(self, content: bytes, key: str, content_type: str = "application/octet-stream") -> str:
        """Upload file content (bytes) to MinIO or local storage and return storage URI."""
        if self.client:
            try:
                data_stream = BytesIO(content)
                self.client.put_object(
                    bucket_name=self.bucket,
                    object_name=key,
                    data=data_stream,
                    length=len(content),
                    content_type=content_type,
                )
                return f"s3://{self.bucket}/{key}"
            except Exception as e:
                logger.warning("MinIO put_object failed, falling back to local: %s", e)

        # Fallback to local storage
        file_path = LOCAL_STORAGE_DIR / key
        file_path.write_bytes(content)
        return f"file://{key}"

    def delete_file(self, key: str) -> None:
        """Delete object from MinIO or local storage."""
        clean_key = key.replace(f"s3://{self.bucket}/", "").replace("file://", "")
        if self.client:
            try:
                self.client.remove_object(bucket_name=self.bucket, object_name=clean_key)
                return
            except Exception:
                pass
        file_path = LOCAL_STORAGE_DIR / clean_key
        if file_path.exists():
            file_path.unlink()

    def get_presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        """Generate a presigned GET URL for an object or local download route."""
        clean_key = key.replace(f"s3://{self.bucket}/", "").replace("file://", "")
        if self.client:
            try:
                from datetime import timedelta
                return self.client.get_presigned_url(
                    method="GET",
                    bucket_name=self.bucket,
                    object_name=clean_key,
                    expires=timedelta(seconds=expires_seconds),
                )
            except Exception:
                pass
        return f"/api/v1/documents/raw/{clean_key}"
