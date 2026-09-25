-- Runs once when the local Postgres volume is first created.
-- The app connects as `meyora`, a non-superuser role, so row-level security
-- is enforced (superusers bypass RLS).
\set app_password `echo "$MEYORA_DB_PASSWORD"`

CREATE ROLE meyora LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB PASSWORD :'app_password';

CREATE DATABASE meyora OWNER meyora;
CREATE DATABASE meyora_test OWNER meyora;

\connect meyora
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\connect meyora_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
