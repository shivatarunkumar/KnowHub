"""Object storage adapter. fake-gcs-server locally, real GCS on GCP; chosen by config."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from functools import lru_cache
from typing import BinaryIO, Protocol

from google.auth.credentials import AnonymousCredentials
from google.cloud import storage

from app.core.config import Settings, get_settings

log = logging.getLogger("knowhub.storage")

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
        started = time.perf_counter()
        missing = [name for name in names if self._client.lookup_bucket(name, timeout=5) is None]
        log.debug(
            "  gcs lookup %d bucket(s) in %dms%s",
            len(names),
            int((time.perf_counter() - started) * 1000),
            f", missing {missing}" if missing else "",
        )
        return missing

    def upload(self, object_name: str, stream: BinaryIO, content_type: str) -> int:
        """Store the object and return its size in bytes."""
        started = time.perf_counter()
        blob = self._bucket.blob(object_name)
        blob.upload_from_file(stream, content_type=content_type, rewind=True)
        blob.reload()
        log.debug(
            "  gcs upload %s (%s, %s bytes) in %dms",
            object_name,
            content_type,
            blob.size,
            int((time.perf_counter() - started) * 1000),
        )
        return blob.size or 0

    def resumable_session(self, object_name: str, content_type: str, size: int, origin: str) -> str:
        """Start a resumable upload and return the session URL.

        The browser PUTs the file to that URL in chunks, so video bytes never pass through
        the API: no request-size limits, and a dropped connection resumes where it stopped.
        The URL is a capability (it carries its own authorisation), short-lived, and only
        allows writing this one object.
        """
        started = time.perf_counter()
        blob = self._bucket.blob(object_name)
        url = blob.create_resumable_upload_session(
            content_type=content_type, size=size, origin=origin, timeout=30
        )
        log.debug(
            "  gcs resumable session for %s (%s, %d bytes, origin %s) in %dms",
            object_name,
            content_type,
            size,
            origin,
            int((time.perf_counter() - started) * 1000),
        )
        return url

    def stat(self, object_name: str) -> tuple[int, str] | None:
        """(size, content type), or None when the object is missing."""
        started = time.perf_counter()
        blob = self._bucket.get_blob(object_name)
        elapsed = int((time.perf_counter() - started) * 1000)
        if blob is None:
            log.debug("  gcs stat %s: missing (%dms)", object_name, elapsed)
            return None
        log.debug("  gcs stat %s: %s bytes (%dms)", object_name, blob.size, elapsed)
        return blob.size or 0, blob.content_type or "application/octet-stream"

    def download(self, object_name: str, start: int, end: int) -> Iterator[bytes]:
        """Yield bytes [start, end] in chunks. The byte range is what makes seeking in
        the player work: the browser asks for the part of the file it needs."""
        log.debug("  gcs download %s bytes %d-%d", object_name, start, end)
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
            log.debug("  gcs delete %s", object_name)
        else:
            log.debug("  gcs delete %s: already gone", object_name)


@lru_cache
def get_storage() -> StorageService:
    return GcsStorage(get_settings())
