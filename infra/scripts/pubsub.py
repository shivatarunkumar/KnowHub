"""Create Pub/Sub topics and subscriptions (emulator locally, real Pub/Sub on GCP). Idempotent.

The emulator keeps state in memory, so these are re-created on every bootstrap.
The client libraries talk to the emulator automatically when PUBSUB_EMULATOR_HOST is set.
"""

from __future__ import annotations

import time

from google.api_core import exceptions
from google.cloud import pubsub_v1
from resources import SubscriptionSpec, TopicSpec, env

DEAD_LETTER_SUFFIX = "-dlq"


def wait_ready(publisher: pubsub_v1.PublisherClient, project: str, seconds: int = 60) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            list(publisher.list_topics(request={"project": f"projects/{project}"}, timeout=5))
            return
        except Exception as exc:
            if time.monotonic() >= deadline:
                raise SystemExit(f"[provision] ERROR: Pub/Sub not reachable: {exc}") from exc
            time.sleep(1)


def ensure_topic(publisher: pubsub_v1.PublisherClient, project: str, name: str, purpose: str = "") -> str:
    path = publisher.topic_path(project, name)
    try:
        publisher.create_topic(request={"name": path})
        print(f"[provision] topic {name}: created {f'({purpose})' if purpose else ''}")
    except exceptions.AlreadyExists:
        print(f"[provision] topic {name}: exists")
    return path


def ensure_pubsub(target: str, topic_specs: list[TopicSpec], sub_specs: list[SubscriptionSpec]) -> None:
    project = env("GCP_PROJECT_ID")
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    wait_ready(publisher, project)

    for spec in topic_specs:
        ensure_topic(publisher, project, spec.name, spec.purpose)

    max_attempts = int(env("PUBSUB_DEAD_LETTER_MAX_ATTEMPTS", "5"))
    for spec in sub_specs:
        request = {
            "name": subscriber.subscription_path(project, spec.name),
            "topic": publisher.topic_path(project, spec.topic),
            "ack_deadline_seconds": spec.ack_deadline_seconds,
        }
        # Dead-lettering needs IAM grants for the Pub/Sub service agent (Phase 10),
        # and the emulator doesn't need it, so it is only set up on GCP.
        if target == "gcp" and spec.dead_letter:
            dlq = ensure_topic(publisher, project, spec.name + DEAD_LETTER_SUFFIX, "dead letters")
            request["dead_letter_policy"] = {
                "dead_letter_topic": dlq,
                "max_delivery_attempts": max_attempts,
            }
        try:
            subscriber.create_subscription(request=request)
            print(f"[provision] subscription {spec.name} → {spec.topic}: created ({spec.purpose})")
        except exceptions.AlreadyExists:
            print(f"[provision] subscription {spec.name}: exists")
