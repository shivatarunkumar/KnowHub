"""Event bus adapter over Pub/Sub. The client library uses the emulator when
PUBSUB_EMULATOR_HOST is set, so the same code runs locally and on GCP."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Protocol

from google.api_core import exceptions
from google.cloud import pubsub_v1

from app.core.config import Settings, get_settings


class EventBus(Protocol):
    def publish(self, topic: str, payload: dict[str, Any], **attributes: str) -> str: ...
    def missing_topics(self, names: list[str]) -> list[str]: ...


class PubSubEventBus:
    def __init__(self, settings: Settings) -> None:
        if settings.pubsub_emulator_host:
            os.environ["PUBSUB_EMULATOR_HOST"] = settings.pubsub_emulator_host
        self._project = settings.gcp_project_id
        self._publisher = pubsub_v1.PublisherClient()

    def publish(self, topic: str, payload: dict[str, Any], **attributes: str) -> str:
        data = json.dumps(payload, default=str).encode("utf-8")
        future = self._publisher.publish(self._publisher.topic_path(self._project, topic), data, **attributes)
        return future.result(timeout=10)

    def missing_topics(self, names: list[str]) -> list[str]:
        missing = []
        for name in names:
            try:
                self._publisher.get_topic(
                    request={"topic": self._publisher.topic_path(self._project, name)}, timeout=5
                )
            except exceptions.NotFound:
                missing.append(name)
        return missing


@lru_cache
def get_event_bus() -> EventBus:
    return PubSubEventBus(get_settings())
