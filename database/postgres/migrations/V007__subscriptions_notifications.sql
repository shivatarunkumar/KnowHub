-- Subscriptions (to topics and to channels) and the in-app notification inbox.

-- "Tell me when a BigQuery video is published."
CREATE TABLE topic_subscriptions (
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    topic_id    uuid NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    notify      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, topic_id)
);
CREATE INDEX topic_subscriptions_topic_idx ON topic_subscriptions (topic_id) WHERE notify;

-- "Tell me when this person publishes." (each user is a channel)
CREATE TABLE channel_subscriptions (
    subscriber_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    channel_user_id  uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    notify           boolean NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (subscriber_id, channel_user_id),
    CHECK (subscriber_id <> channel_user_id)
);
CREATE INDEX channel_subscriptions_channel_idx ON channel_subscriptions (channel_user_id) WHERE notify;

-- Denormalised count shown on channel pages.
ALTER TABLE users ADD COLUMN subscriber_count integer NOT NULL DEFAULT 0;

CREATE TABLE notifications (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    type        text NOT NULL CHECK (type IN (
                    'new_video_topic', 'new_video_channel', 'comment_reply',
                    'video_shared', 'video_ready', 'video_failed')),
    video_id    uuid REFERENCES videos (id) ON DELETE CASCADE,
    actor_id    uuid REFERENCES users (id) ON DELETE SET NULL,
    topic_id    uuid REFERENCES topics (id) ON DELETE SET NULL,
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    read_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_inbox_idx ON notifications (user_id, created_at DESC);
CREATE INDEX notifications_unread_idx ON notifications (user_id) WHERE read_at IS NULL;
