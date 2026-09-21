-- Local stand-in for BigQuery: view, watch-time and engagement events.
-- On GCP the same events go to Pub/Sub → BigQuery (ANALYTICS_BACKEND=bigquery) and this
-- table stays empty. No foreign keys: events outlive deleted videos and cover anonymous
-- viewers, and writes must never be blocked by a missing row.

CREATE TABLE analytics_events (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type   text NOT NULL CHECK (event_type IN (
                     'video_view', 'video_progress', 'video_complete',
                     'video_like', 'video_share', 'search', 'ai_enhance')),
    video_id     uuid,
    user_id      uuid,                 -- null for anonymous viewers
    session_id   text,
    position_sec integer,
    payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX analytics_events_time_idx ON analytics_events (occurred_at DESC);
CREATE INDEX analytics_events_video_idx ON analytics_events (video_id, occurred_at DESC);
CREATE INDEX analytics_events_type_idx ON analytics_events (event_type, occurred_at DESC);
