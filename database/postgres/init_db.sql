-- KnowHub database bootstrap: role, database, privileges, extensions.
-- FIRST script of any database setup; run as a superuser against the maintenance
-- database (usually "postgres"), then migrations, then seeds:
--
--   psql "postgresql://<superuser>@host:5432/postgres" -f database/postgres/init_db.sql
--   python database/scripts/migrate.py up
--   python database/scripts/seed.py
--
-- Defaults are knowhub / tarun / 12345; override them without editing this file:
--   psql ... -v db_name=knowhub -v db_user=tarun -v db_password=secret -f init_db.sql
-- database/scripts/init_db.sh passes the values from DATABASE_URL in .env.
-- Idempotent: safe to run again on an existing database.

\set ON_ERROR_STOP on

\if :{?db_name}     \else \set db_name     knowhub \endif
\if :{?db_user}     \else \set db_user     tarun   \endif
\if :{?db_password} \else \set db_password 12345   \endif

\echo '== init_db: role' :db_user ', database' :db_name

-- 1. Application role (login user). Created once, password kept in sync afterwards.
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'db_user')
\gexec

SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_password')
\gexec

-- 2. Database, owned by that role.
SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name')
\gexec

GRANT ALL PRIVILEGES ON DATABASE :"db_name" TO :"db_user";

-- 3. Everything below applies inside the new database.
\connect :"db_name"

-- Owning the schema lets the role create tables, and every future object in it.
ALTER SCHEMA public OWNER TO :"db_user";
GRANT ALL ON SCHEMA public TO :"db_user";

-- Objects that already exist (re-runs, or a database created by someone else).
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO :"db_user";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO :"db_user";
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO :"db_user";

-- Objects created later by anyone else in this schema.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO :"db_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO :"db_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO :"db_user";

-- 4. Extensions: created here because they need superuser rights on most servers.
--    pg_trgm: fuzzy title search. vector (pgvector): embeddings for semantic search,
--    installed only when the server has the package, so plain Postgres still works
--    (the embeddings migration is what actually requires it).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

SELECT 'CREATE EXTENSION IF NOT EXISTS vector'
WHERE EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')
\gexec

SELECT :'db_name' AS database, :'db_user' AS owner,
       (SELECT string_agg(extname, ', ' ORDER BY extname)
        FROM pg_extension WHERE extname IN ('pg_trgm', 'vector')) AS extensions;

\echo '== init_db: done'
