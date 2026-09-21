-- Topics: the admin-managed list of GCP services / areas videos are filed under
-- (BigQuery, Pub/Sub, GKE, ...). Users subscribe to topics for notifications.

CREATE TABLE topics (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug         text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    name         text NOT NULL,
    description  text,
    icon         text,
    sort_order   integer NOT NULL DEFAULT 0,
    is_active    boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX topics_active_sort_idx ON topics (is_active, sort_order, name);

CREATE TRIGGER topics_set_updated_at BEFORE UPDATE ON topics
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
