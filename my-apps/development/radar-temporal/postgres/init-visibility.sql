-- Runs ONLY on first boot of an empty volume (docker-entrypoint-initdb.d);
-- a kopiur-restored volume skips initdb entirely and keeps its databases.
-- Temporal needs a second database for the visibility store and the chart
-- runs with createDatabase: false — the schema Jobs only create tables.
CREATE DATABASE temporal_visibility OWNER temporal;
