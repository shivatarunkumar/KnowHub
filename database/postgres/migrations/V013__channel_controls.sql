-- Channel management: the uploader decides who can see each video and whether people
-- can comment on it. See project.md §2.5.

-- Comments can be switched off per video; existing videos keep them on.
ALTER TABLE videos ADD COLUMN comments_enabled boolean NOT NULL DEFAULT true;

-- 'restricted' joins the existing visibilities: only the people listed in
-- video_viewers (plus the owner) can watch. 'private' stays "only me".
ALTER TABLE videos DROP CONSTRAINT videos_visibility_check;
ALTER TABLE videos ADD CONSTRAINT videos_visibility_check
    CHECK (visibility IN ('internal', 'unlisted', 'restricted', 'private'));

-- The allow-list behind visibility = 'restricted'.
CREATE TABLE video_viewers (
    video_id    uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    added_by    uuid REFERENCES users (id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (video_id, user_id)
);

-- "which videos am I allowed to watch?" on the feed
CREATE INDEX video_viewers_user_idx ON video_viewers (user_id);

-- Channel actions land in the same audit trail as the upload itself.
ALTER TABLE upload_events DROP CONSTRAINT upload_events_event_check;
ALTER TABLE upload_events ADD CONSTRAINT upload_events_event_check
    CHECK (event IN (
        'initiated', 'uploaded', 'processing', 'ready', 'failed',
        'published', 'edited', 'visibility_changed', 'comments_changed', 'deleted'));
