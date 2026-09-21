-- Non-destructive video editing: the edit list is stored, the original file is kept,
-- and a worker renders each version. Re-editing creates a new version, so the live
-- version keeps playing until the new one is ready.

CREATE TABLE video_edits (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id    uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    version     integer NOT NULL CHECK (version > 0),
    -- { "keep": [{"start": 0, "end": 42.5}], "crop": {"x":0,"y":0,"w":1920,"h":1080},
    --   "rotate": 0, "mute_ranges": [], "thumbnail_time": 12.0 }
    edit_list   jsonb NOT NULL DEFAULT '{}'::jsonb,
    status      text NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'processing', 'applied', 'failed')),
    error       text,
    output_path text,          -- gs://knowhub-media/videos/{video_id}/v{version}/hls/master.m3u8
    created_by  uuid REFERENCES users (id) ON DELETE SET NULL,
    applied_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (video_id, version)
);
CREATE INDEX video_edits_video_idx ON video_edits (video_id, version DESC);

CREATE TRIGGER video_edits_set_updated_at BEFORE UPDATE ON video_edits
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Which rendered version is currently served for this video.
ALTER TABLE videos ADD COLUMN current_edit_version integer;
