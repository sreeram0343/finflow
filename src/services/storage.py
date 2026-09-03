import io
import os
import hashlib
import logging
from typing import Optional, Tuple
from pathlib import Path

from src.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Storage client with MinIO S3 support and local filesystem fallback."""

    def __init__(self):
        self.minio_client = None
        self.bucket_name = settings.minio_bucket
        self.local_storage_dir = Path("./local_storage")
        self.local_storage_dir.mkdir(parents=True, exist_ok=True)

        try:
            from minio import Minio
            self.minio_client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            # Try to ensure bucket exists if server is reachable
            # We don't block constructor on network failure
        except Exception as e:
            logger.warning(f"MinIO client initialization fallback to local storage: {e}")
            self.minio_client = None

        self._minio_failed = False

    def _ensure_bucket(self) -> bool:
        if not self.minio_client or self._minio_failed:
            return False
        try:
            if not self.minio_client.bucket_exists(self.bucket_name):
                self.minio_client.make_bucket(self.bucket_name)
            return True
        except Exception as e:
            logger.warning(f"Could not connect to MinIO bucket '{self.bucket_name}': {e}. Disabling MinIO for this session.")
            self._minio_failed = True
            return False

    async def upload_document(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "application/pdf"
    ) -> Tuple[str, str]:
        """
        Uploads document bytes to MinIO S3 or local directory fallback.
        Returns (file_hash, file_url_or_path).
        """
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        ext = Path(filename).suffix or ".pdf"
        object_name = f"{file_hash}{ext}"

        if self.minio_client and self._ensure_bucket():
            try:
                data_stream = io.BytesIO(file_bytes)
                self.minio_client.put_object(
                    bucket_name=self.bucket_name,
                    object_name=object_name,
                    data=data_stream,
                    length=len(file_bytes),
                    content_type=content_type
                )
                file_url = f"s3://{self.bucket_name}/{object_name}"
                logger.info(f"Uploaded {filename} to MinIO: {file_url}")
                return file_hash, file_url
            except Exception as e:
                logger.error(f"Failed MinIO upload, falling back to local: {e}")

        # Local storage fallback
        dest_path = self.local_storage_dir / object_name
        with open(dest_path, "wb") as f:
            f.write(file_bytes)
        file_url = str(dest_path.as_posix())
        logger.info(f"Saved {filename} locally to: {file_url}")
        return file_hash, file_url

    async def get_document_bytes(self, file_url: str) -> Optional[bytes]:
        """Retrieves raw document bytes from S3 or local storage."""
        if file_url.startswith("s3://") and self.minio_client:
            try:
                parts = file_url.replace("s3://", "").split("/", 1)
                bucket = parts[0]
                object_name = parts[1]
                response = self.minio_client.get_object(bucket, object_name)
                return response.read()
            except Exception as e:
                logger.error(f"Failed to fetch document from MinIO: {e}")
                return None

        # Try local filesystem
        try:
            path = Path(file_url)
            if path.exists():
                with open(path, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.error(f"Failed to read local file: {e}")

        return None


storage_service = StorageService()
