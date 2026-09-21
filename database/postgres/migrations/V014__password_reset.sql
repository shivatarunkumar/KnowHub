-- Password reset: a single-use, short-lived token emailed (later) to the account owner.
-- Only the SHA-256 hash is stored, exactly like refresh_tokens, so the table is useless
-- to anyone who reads it.

CREATE TABLE password_reset_tokens (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash    text NOT NULL UNIQUE,
    expires_at    timestamptz NOT NULL,
    used_at       timestamptz,
    requested_ip  inet,
    user_agent    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT password_reset_tokens_expiry_check CHECK (expires_at > created_at)
);

-- "the newest token for this user", and the cleanup of expired ones
CREATE INDEX password_reset_tokens_user_idx ON password_reset_tokens (user_id, created_at DESC);
CREATE INDEX password_reset_tokens_expiry_idx ON password_reset_tokens (expires_at)
    WHERE used_at IS NULL;

-- Resetting a password signs every device out, which is a new reason for revoking a
-- refresh token; without this the reset fails on the CHECK constraint from V002.
ALTER TABLE refresh_tokens DROP CONSTRAINT refresh_tokens_revoked_reason_check;
ALTER TABLE refresh_tokens ADD CONSTRAINT refresh_tokens_revoked_reason_check
    CHECK (revoked_reason IN ('rotated', 'logout', 'reuse_detected', 'password_reset', 'admin'));
