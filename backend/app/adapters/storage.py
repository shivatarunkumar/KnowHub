"""Object storage adapter. fake-gcs-server locally, real GCS on GCP; chosen by config."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import BinaryIO, Protocol

from google.auth.credentials import AnonymousCredentials
from google.cloud import storage

from app.core.config import Settings, get_settings

DOWNLOAD_CHUNK_BYTES = 1024 * 1024


class StorageService(Protocol):
    def missing_buckets(self, names: list[str]) -> list[str]: ...
    def upload(self, object_name: str, stream: BinaryIO, content_type: str) -> int: ...
    def resumable_session(self, object_name: str, content_type: str, size: int, origin: str) -> str: ...
    def stat(self, object_name: str) -> tuple[int, str] | None: ...
    def download(self, object_name: str, start: int, end: int) -> Iterator[bytes]: ...
    def delete(self, object_name: str) -> None: ...


class GcsStorage:
    def __init__(self, settings: Settings) -> None:
        if settings.gcs_endpoint_url:
            self._client = storage.Client(
                project=settings.gcp_project_id,
                credentials=AnonymousCredentials(),
                client_options={"api_endpoint": settings.gcs_endpoint_url},
            )
        else:
            self._client = storage.Client(project=settings.gcp_project_id)
        self._bucket_name = settings.gcs_bucket

    @property
    def _bucket(self) -> storage.Bucket:
        return self._client.bucket(self._bucket_name)

    def missing_buckets(self, names: list[str]) -> list[str]:
        return [name for name in names if self._client.lookup_bucket(name, timeout=5) is None]

    def upload(self, object_name: str, stream: BinaryIO, content_type: str) -> int:
        """Store the object and return its size in bytes."""
        blob = self._bucket.blob(object_name)
        blob.upload_from_file(stream, content_type=content_type, rewind=True)
        blob.reload()
        return blob.size or 0

    def resumable_session(self, object_name: str, content_type: str, size: int, origin: str) -> str:
        """Start a resumable upload and return the session URL.

        The browser PUTs the file to that URL in chunks, so video bytes never pass through
        the API: no request-size limits, and a dropped connection resumes where it stopped.
        The URL is a capability (it carries its own authorisation), short-lived, and only
        allows writing this one object.
        """
        blob = self._bucket.blob(object_name)
        return blob.create_resumable_upload_session(
            content_type=content_type, size=size, origin=origin, timeout=30
        )

    def stat(self, object_name: str) -> tuple[int, str] | None:
        """(size, content type), or None when the object is missing."""
        blob = self._bucket.get_blob(object_name)
        if blob is None:
            return None
        return blob.size or 0, blob.content_type or "application/octet-stream"

    def download(self, object_name: str, start: int, end: int) -> Iterator[bytes]:
        """Yield bytes [start, end] in chunks. The byte range is what makes seeking in
        the player work: the browser asks for the part of the file it needs."""
        blob = self._bucket.blob(object_name)
        position = start
        while position <= end:
            last = min(position + DOWNLOAD_CHUNK_BYTES - 1, end)
            chunk = blob.download_as_bytes(start=position, end=last, raw_download=True)
            if not chunk:
                return
            yield chunk
            position += len(chunk)

    def delete(self, object_name: str) -> None:
        blob = self._bucket.blob(object_name)
        if blob.exists():
            blob.delete()


@lru_cache
def get_storage() -> StorageService:
    return GcsStorage(get_settings())
