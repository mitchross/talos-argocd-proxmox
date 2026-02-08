\c immich
BEGIN;
ALTER DATABASE "immich" OWNER TO "immich";
-- Immich expects public schema only; drop user-named schema if PGO created one
DROP SCHEMA IF EXISTS immich CASCADE;
CREATE EXTENSION IF NOT EXISTS vchord CASCADE;
CREATE EXTENSION IF NOT EXISTS vector CASCADE;
CREATE EXTENSION IF NOT EXISTS earthdistance CASCADE;
COMMIT;
