-- Videos and shorts plus their metadata: topics, tags, links and the upload audit trail.

CREATE TABLE videos (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id            uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    type                text NOT NULL CHECK (type IN ('video', 'short')),
    title               text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    description         text CHECK (length(description) <= 20000),
    category            text NOT NULL CHECK (category IN (
                            'bug_fix', 'incident_resolution', 'how_to',
                            'knowledge_share', 'demo', 'reusable_component')),
    primary_topic_id    uuid REFERENCES topics (id) ON DELETE RESTRICT,
    visibility          text NOT NULL DEFAULT 'internal'
                            CHECK (visibility IN ('internal', 'unlisted', 'private')),
    status              text NOT NULL DEFAULT 'UPLOADING'
                            CHECK (status IN ('DRAFT', 'UPLOADING', 'PROCESSING', 'READY', 'FAILED')),
    -- context for incident/bug-fix videos
    environment         text CHECK (environment IN ('prod', 'stage', 'dev', 'other')),
    severity            text CHECK (severity IN ('sev1', 'sev2', 'sev3', 'sev4')),
    -- storage
    original_filename   text,
    mime_type           text,
    raw_gcs_path        text,          -- gs://knowhub-raw/users/{user_id}/videos/{video_id}/source.mp4
    hls_path            text,          -- gs://knowhub-media/videos/{video_id}/v{n}/hls/master.m3u8
    thumbnail_path      text,
    -- probed from the processed video
    duration_sec        integer CHECK (duration_sec >= 0),
    width               integer,
    height              integer,
    size_bytes          bigint CHECK (size_bytes >= 0),
    -- denormalised counters, kept up to date by the API
    view_count          bigint NOT NULL DEFAULT 0,
    like_count          integer NOT NULL DEFAULT 0,
    comment_count       integer NOT NULL DEFAULT 0,
    processing_error    text,
    published_at        timestamptz,
    deleted_at          timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    -- full-text search: title weighted above description
    search_vector       tsvector GENERATED ALWAYS AS (
                            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                            setweight(to_tsvector('english', coalesce(description, '')), 'B')
                        ) STORED
);

-- home feed / channel pages: newest published first
CREATE INDEX videos_feed_idx ON videos (status, visibility, published_at DESC)
    WHERE deleted_at IS NULL;
CREATE INDEX videos_owner_idx ON videos (owner_id, created_at DESC);
CREATE INDEX videos_topic_idx ON videos (primary_topic_id, published_at DESC);
CREATE INDEX videos_type_idx ON videos (type, published_at DESC);
CREATE INDEX videos_search_idx ON videos USING gin (search_vector);
CREATE INDEX videos_title_trgm_idx ON videos USING gin (title gin_trgm_ops);

CREATE TRIGGER videos_set_updated_at BEFORE UPDATE ON videos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Additional topics beyond videos.primary_topic_id.
CREATE TABLE video_topics (
    video_id  uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    topic_id  uuid NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    PRIMARY KEY (video_id, topic_id)
);
CREATE INDEX video_topics_topic_idx ON video_topics (topic_id);

-- Free-form tags (kafka-lag, terraform, oom-kill, ...).
CREATE TABLE tags (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE video_tags (
    video_id  uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    tag_id    uuid NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    PRIMARY KEY (video_id, tag_id)
);
CREATE INDEX video_tags_tag_idx ON video_tags (tag_id);

-- Links shown under the video: incident, Jira ticket, repo, PR, doc.
CREATE TABLE video_links (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id    uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('incident', 'jira', 'repo', 'pr', 'doc', 'other')),
    url         text NOT NULL,
    label       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX video_links_video_idx ON video_links (video_id);

-- Audit trail: who uploaded what, when, and every state change after that.
CREATE TABLE upload_events (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id    uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    user_id     uuid REFERENCES users (id) ON DELETE SET NULL,
    event       text NOT NULL CHECK (event IN (
                    'initiated', 'uploaded', 'processing', 'ready',
                    'failed', 'published', 'edited', 'deleted')),
    metadata    jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX upload_events_video_idx ON upload_events (video_id, created_at);
CREATE INDEX upload_events_user_idx ON upload_events (user_id, created_at DESC);
