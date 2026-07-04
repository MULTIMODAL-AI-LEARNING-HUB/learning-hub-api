"""MinIO object storage client."""

from io import BytesIO
from typing import Optional
from minio import Minio
from app.core.config import settings

_minio_client: Optional[Minio] = None


def get_minio_client() -> Minio:
    """Get or initialize the shared Minio client."""
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        # Ensure bucket exists
        if not _minio_client.bucket_exists(settings.MINIO_BUCKET_NAME):
            _minio_client.make_bucket(settings.MINIO_BUCKET_NAME)
    return _minio_client


class MinioClient:
    """Wrapper class for MinIO operations."""

    def __init__(self) -> None:
        self.client = get_minio_client()
        self.bucket = settings.MINIO_BUCKET_NAME

    def upload_file(self, content: bytes, key: str, content_type: str = "application/octet-stream") -> str:
        """Upload file content (bytes) to MinIO and return storage URI."""
        data_stream = BytesIO(content)
        self.client.put_object(
            bucket_name=self.bucket,
            object_name=key,
            data=data_stream,
            length=len(content),
            content_type=content_type
        )
        return f"s3://{self.bucket}/{key}"

    def delete_file(self, key: str) -> None:
        """Delete object from MinIO."""
        clean_key = key.replace(f"s3://{self.bucket}/", "")
        self.client.remove_object(bucket_name=self.bucket, object_name=clean_key)

    def get_presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        """Generate a presigned GET URL for an object."""
        # Clean key if it contains URI scheme prefix
        clean_key = key.replace(f"s3://{self.bucket}/", "")
        from datetime import timedelta
        return self.client.get_presigned_url(
            method="GET",
            bucket_name=self.bucket,
            object_name=clean_key,
            expires=timedelta(seconds=expires_seconds)
        )
