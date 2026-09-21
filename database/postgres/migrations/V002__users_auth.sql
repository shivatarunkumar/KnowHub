-- Users (each user is also a channel) and refresh tokens for JWT auth.

CREATE TABLE users (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- stored lowercase so the unique index and lookups agree; @ + domain required
    email              text NOT NULL CHECK (email = lower(email) AND email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    email_verified_at  timestamptz,
    -- argon2id hash; never a plaintext password
    password_hash      text NOT NULL,
    password_changed_at timestamptz NOT NULL DEFAULT now(),
    display_name       text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 100),
    -- channel handle: @tarun, lowercase, 3-30 chars
    handle             text NOT NULL CHECK (handle ~ '^[a-z0-9][a-z0-9_.-]{2,29}$'),
    avatar_url         text CHECK (length(avatar_url) <= 2048),
    banner_url         text CHECK (length(banner_url) <= 2048),
    bio                text CHECK (length(bio) <= 1000),
    role               text NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    is_active          boolean NOT NULL DEFAULT true,
    last_login_at      timestamptz,
    -- brute-force protection for the login endpoint
    failed_login_count integer NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    locked_until       timestamptz,
    -- soft delete: keeps their videos and comments attributable
    deleted_at         timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX users_email_key ON users (email);
CREATE UNIQUE INDEX users_handle_key ON users (handle);
-- admin user list / directory search
CREATE INDEX users_display_name_trgm_idx ON users USING gin (display_name gin_trgm_ops);

CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Refresh tokens are stored hashed (never in plaintext) and rotated on every use:
-- using one marks it revoked and points replaced_by at its successor, so a replayed
-- token reveals a stolen session.
CREATE TABLE refresh_tokens (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash    text NOT NULL UNIQUE,
    expires_at    timestamptz NOT NULL,
    last_used_at  timestamptz,
    revoked_at    timestamptz,
    revoked_reason text CHECK (revoked_reason IN ('rotated', 'logout', 'reuse_detected', 'admin')),
    replaced_by   uuid REFERENCES refresh_tokens (id) ON DELETE SET NULL,
    user_agent    text CHECK (length(user_agent) <= 500),
    ip            inet,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > created_at)
);

-- "all my active sessions" and "revoke everything for this user"
CREATE INDEX refresh_tokens_active_idx ON refresh_tokens (user_id, expires_at DESC)
    WHERE revoked_at IS NULL;
-- nightly cleanup of expired rows
CREATE INDEX refresh_tokens_expires_idx ON refresh_tokens (expires_at);
