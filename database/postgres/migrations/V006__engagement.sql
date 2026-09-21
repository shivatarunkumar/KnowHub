-- Engagement: likes/dislikes, comments, in-app sharing, playlists and watch history.

-- One row per user per video: +1 like, -1 dislike. Removing a reaction deletes the row.
CREATE TABLE video_reactions (
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    video_id    uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    value       smallint NOT NULL CHECK (value IN (-1, 1)),
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, video_id)
);
CREATE INDEX video_reactions_video_idx ON video_reactions (video_id, value);

-- Comments with one level of replies (parent_id points at a top-level comment).
CREATE TABLE comments (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id    uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    parent_id   uuid REFERENCES comments (id) ON DELETE CASCADE,
    body        text NOT NULL CHECK (length(body) BETWEEN 1 AND 10000),
    like_count  integer NOT NULL DEFAULT 0,
    is_pinned   boolean NOT NULL DEFAULT false,
    edited_at   timestamptz,
    deleted_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX comments_video_idx ON comments (video_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX comments_parent_idx ON comments (parent_id, created_at) WHERE parent_id IS NOT NULL;
CREATE INDEX comments_user_idx ON comments (user_id, created_at DESC);

CREATE TRIGGER comments_set_updated_at BEFORE UPDATE ON comments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE comment_reactions (
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    comment_id  uuid NOT NULL REFERENCES comments (id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, comment_id)
);
CREATE INDEX comment_reactions_comment_idx ON comment_reactions (comment_id);

-- Sharing stays inside KnowHub: the recipient gets a notification and a "Shared with me" entry.
CREATE TABLE video_shares (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id      uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    from_user_id  uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    to_user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    message       text CHECK (length(message) <= 1000),
    at_seconds    integer CHECK (at_seconds >= 0),   -- share at a timestamp
    created_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (from_user_id <> to_user_id)
);
CREATE INDEX video_shares_to_idx ON video_shares (to_user_id, created_at DESC);
CREATE INDEX video_shares_video_idx ON video_shares (video_id);

-- Playlists. Watch Later is a system playlist created per user (system_kind = 'watch_later').
CREATE TABLE playlists (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title        text NOT NULL CHECK (length(title) BETWEEN 1 AND 150),
    description  text,
    visibility   text NOT NULL DEFAULT 'private'
                     CHECK (visibility IN ('internal', 'unlisted', 'private')),
    system_kind  text CHECK (system_kind IN ('watch_later')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX playlists_owner_idx ON playlists (owner_id, created_at DESC);
CREATE UNIQUE INDEX playlists_owner_system_key ON playlists (owner_id, system_kind)
    WHERE system_kind IS NOT NULL;

CREATE TRIGGER playlists_set_updated_at BEFORE UPDATE ON playlists
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE playlist_items (
    playlist_id  uuid NOT NULL REFERENCES playlists (id) ON DELETE CASCADE,
    video_id     uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    position     integer NOT NULL,
    added_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (playlist_id, video_id)
);
CREATE INDEX playlist_items_order_idx ON playlist_items (playlist_id, position);

-- Resume playback and the History page. One row per user per video.
CREATE TABLE watch_history (
    user_id            uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    video_id           uuid NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    last_position_sec  integer NOT NULL DEFAULT 0 CHECK (last_position_sec >= 0),
    watch_count        integer NOT NULL DEFAULT 1,
    completed          boolean NOT NULL DEFAULT false,
    watched_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, video_id)
);
CREATE INDEX watch_history_recent_idx ON watch_history (user_id, watched_at DESC);
