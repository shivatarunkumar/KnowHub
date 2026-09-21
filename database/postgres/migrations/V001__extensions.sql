-- Extensions and shared helpers used by every later migration.
-- init_db.sql already creates these extensions as the admin role (managed Postgres
-- often won't let the app role do it); the statements below are a no-op safety net.

CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- trigram search on titles
-- pgvector (embeddings for semantic search) is created by the embeddings migration,
-- so a plain Postgres without the pgvector package can run everything up to that point.

-- Keeps updated_at current on every UPDATE. Attach with:
--   CREATE TRIGGER <table>_set_updated_at BEFORE UPDATE ON <table>
--     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;
