-- migrate:requires-extension vector
-- AI: embeddings of title + description (for semantic search, Phase 9) and a log of
-- writing-assist requests.
--
-- NEEDS pgvector installed on the server (brew install pgvector, or a Postgres image
-- that bundles it, e.g. pgvector/pgvector). The dimension below must match
-- AI_EMBEDDING_DIM in .env; changing the model means re-embedding every video.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE video_embeddings (
    video_id      uuid PRIMARY KEY REFERENCES videos (id) ON DELETE CASCADE,
    embedding     vector(768) NOT NULL,
    model         text NOT NULL,
    dim           integer NOT NULL CHECK (dim > 0),
    -- hash of the embedded text (title + description + topics + tags): lets the worker
    -- skip re-embedding when nothing meaningful changed
    content_hash  text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX video_embeddings_hnsw_idx ON video_embeddings
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX video_embeddings_model_idx ON video_embeddings (model);

CREATE TRIGGER video_embeddings_set_updated_at BEFORE UPDATE ON video_embeddings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Usage and quality tracking for "Improve with AI" (accepted tells us if suggestions land).
CREATE TABLE ai_requests (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid REFERENCES users (id) ON DELETE SET NULL,
    video_id      uuid REFERENCES videos (id) ON DELETE SET NULL,
    field         text NOT NULL CHECK (field IN ('title', 'description', 'tags')),
    provider      text NOT NULL,
    model         text NOT NULL,
    input_chars   integer NOT NULL DEFAULT 0,
    output_chars  integer NOT NULL DEFAULT 0,
    latency_ms    integer,
    accepted      boolean,
    error         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ai_requests_user_idx ON ai_requests (user_id, created_at DESC);
