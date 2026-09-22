-- Teams: which part of the organisation a video comes from (Payments, Fraud, Core
-- Banking, ...). Topics say what a video is about; a team says who owns it, so the two
-- filters are independent and combine.

CREATE TABLE teams (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug         text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    name         text NOT NULL,
    description  text,
    -- the larger part of the bank a team sits in, for grouping in the UI later
    division     text,
    sort_order   integer NOT NULL DEFAULT 0,
    is_active    boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX teams_active_sort_idx ON teams (is_active, sort_order, name);

CREATE TRIGGER teams_set_updated_at BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Which team a video belongs to. Nullable: videos uploaded before this existed, and
-- anything that genuinely belongs to no one team. RESTRICT so a team that still owns
-- videos cannot be deleted out from under them.
ALTER TABLE videos ADD COLUMN team_id uuid REFERENCES teams (id) ON DELETE RESTRICT;

-- the team filter on the home feed: newest published first, within a team
CREATE INDEX videos_team_idx ON videos (team_id, published_at DESC) WHERE deleted_at IS NULL;

-- Which team a person belongs to, so the upload form can default to it.
ALTER TABLE users ADD COLUMN team_id uuid REFERENCES teams (id) ON DELETE SET NULL;
CREATE INDEX users_team_idx ON users (team_id);
