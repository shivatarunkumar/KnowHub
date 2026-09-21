-- Resources attached to a video: code snippets people can copy instead of transcribing
-- from the screen. (Links already live in video_links, added in V004.)

CREATE TABLE video_snippets (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id    uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    title       text CHECK (length(title) <= 200),
    language    text NOT NULL DEFAULT 'text'
                    CHECK (language ~ '^[a-z0-9+#.-]{1,20}$'),
    code        text NOT NULL CHECK (length(code) BETWEEN 1 AND 20000),
    sort_order  integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX video_snippets_video_idx ON video_snippets (video_id, sort_order);

-- 'confluence' joins the existing link kinds (incident, jira, repo, pr, doc, other)
ALTER TABLE video_links DROP CONSTRAINT video_links_kind_check;
ALTER TABLE video_links ADD CONSTRAINT video_links_kind_check
    CHECK (kind IN ('incident', 'jira', 'repo', 'pr', 'doc', 'confluence', 'other'));
