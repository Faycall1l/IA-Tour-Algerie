from __future__ import annotations

import io
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import UploadFile

from app.core.config import settings

if TYPE_CHECKING:
    from minio import Minio

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class StorageService:
    def __init__(self) -> None:
        self.client: Minio | None = None
        self.bucket = settings.minio.bucket
        self._init_client()

    def _init_client(self) -> None:
        try:
            from minio import Minio

            self.client = Minio(
                endpoint=settings.minio.endpoint,
                access_key=settings.minio.access_key,
                secret_key=settings.minio.secret_key,
                secure=settings.minio.secure,
            )
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
            self._set_public_policy()
            logger.info("StorageService connected to MinIO at %s", settings.minio.endpoint)
        except Exception as exc:
            logger.warning("MinIO unavailable (uploads will fail): %s", exc)
            self.client = None

    def _set_public_policy(self) -> None:
        if not self.client:
            return
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{self.bucket}/*"],
                }
            ],
        }
        self.client.set_bucket_policy(self.bucket, json.dumps(policy))

    def _public_url(self, object_name: str) -> str:
        endpoint = settings.minio.endpoint
        return f"http://{endpoint}/{self.bucket}/{object_name}"

    def _validate(self, file: UploadFile) -> None:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise ValueError(f"Unsupported file type '{ext}'. Allowed: {allowed}")
        if file.size and file.size > MAX_FILE_SIZE:
            max_mb = MAX_FILE_SIZE // 1024 // 1024
            raise ValueError(f"File too large ({file.size} bytes). Max: {max_mb} MB")

    async def upload(self, file: UploadFile, folder: str = "general") -> str:
        self._validate(file)

        if not self.client:
            raise RuntimeError("MinIO not available")

        ext = Path(file.filename or "image.jpg").suffix.lower()
        object_name = f"{folder}/{uuid.uuid4().hex}{ext}"
        content = await file.read()

        self.client.put_object(
            bucket_name=self.bucket,
            object_name=object_name,
            data=io.BytesIO(content),
            length=len(content),
            content_type=file.content_type or "application/octet-stream",
        )

        return self._public_url(object_name)
