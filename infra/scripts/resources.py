"""Declarative list of KnowHub cloud resources, built from environment config.

Resource names always come from .env so local, dev and prod can differ without code
changes. Add a new bucket, topic or subscription here and `provision.py` creates it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"[provision] ERROR: environment variable {name} is not set (see .env.example)")
    return value


@dataclass(frozen=True)
class BucketSpec:
    name: str
    purpose: str
    cors_origins: tuple[str, ...] = ()  # browser uploads (GCP only; fake-gcs allows all)
    coldline_after_days: int | None = None  # lifecycle rule on the raw prefix (GCP only)
    coldline_prefix: str = ""


@dataclass(frozen=True)
class TopicSpec:
    name: str
    purpose: str


@dataclass(frozen=True)
class SubscriptionSpec:
    name: str
    topic: str
    purpose: str
    ack_deadline_seconds: int = 60
    dead_letter: bool = True  # GCP only: failed messages go to <name>-dlq after N attempts


def buckets() -> list[BucketSpec]:
    """One bucket, two prefixes: raw/ (originals, one folder per user) and
    media/ (processed HLS + thumbnails, served to players)."""
    cors = tuple(o.strip() for o in os.environ.get("GCS_CORS_ORIGINS", "").split(",") if o.strip())
    raw_prefix = os.environ.get("GCS_RAW_PREFIX", "raw")
    return [
        BucketSpec(
            env("GCS_BUCKET"),
            f"{raw_prefix}/users/{{user_id}}/... originals; "
            f"{os.environ.get('GCS_MEDIA_PREFIX', 'media')}/videos/... processed output",
            cors_origins=cors,
            coldline_after_days=int(env("GCS_RAW_COLDLINE_AFTER_DAYS", "30")),
            coldline_prefix=f"{raw_prefix}/",
        ),
    ]


def topics() -> list[TopicSpec]:
    return [
        TopicSpec(env("PUBSUB_TOPIC_VIDEO_UPLOADED"), "raw file finished uploading → start processing"),
        TopicSpec(env("PUBSUB_TOPIC_TRANSCODE_EVENTS"), "transcoding job finished / failed"),
        TopicSpec(env("PUBSUB_TOPIC_VIDEO_PUBLISHED"), "video is live → notifications, embeddings"),
        TopicSpec(env("PUBSUB_TOPIC_VIDEO_METADATA_CHANGED"), "title/description/tags edited → re-embed"),
        TopicSpec(env("PUBSUB_TOPIC_ANALYTICS_EVENTS"), "view/like events → BigQuery (GCP)"),
    ]


def subscriptions() -> list[SubscriptionSpec]:
    return [
        SubscriptionSpec(
            env("PUBSUB_SUB_MEDIA_UPLOADED"),
            env("PUBSUB_TOPIC_VIDEO_UPLOADED"),
            "media-worker: probe + transcode",
            ack_deadline_seconds=600,
        ),
        SubscriptionSpec(
            env("PUBSUB_SUB_MEDIA_TRANSCODE"),
            env("PUBSUB_TOPIC_TRANSCODE_EVENTS"),
            "media-worker: mark READY/FAILED",
            ack_deadline_seconds=120,
        ),
        SubscriptionSpec(
            env("PUBSUB_SUB_NOTIFY_PUBLISHED"),
            env("PUBSUB_TOPIC_VIDEO_PUBLISHED"),
            "notify-worker: notify topic/channel subscribers",
        ),
        SubscriptionSpec(
            env("PUBSUB_SUB_EMBED_PUBLISHED"),
            env("PUBSUB_TOPIC_VIDEO_PUBLISHED"),
            "embed-worker: embed new videos",
            ack_deadline_seconds=120,
        ),
        SubscriptionSpec(
            env("PUBSUB_SUB_EMBED_METADATA"),
            env("PUBSUB_TOPIC_VIDEO_METADATA_CHANGED"),
            "embed-worker: re-embed edited videos",
            ack_deadline_seconds=120,
        ),
    ]


def ai_models() -> list[str]:
    return [env("AI_TEXT_MODEL"), env("AI_EMBEDDING_MODEL")]
