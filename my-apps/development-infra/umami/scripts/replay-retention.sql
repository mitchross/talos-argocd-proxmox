-- Self-hosted Umami never purges replays. Keep 30 days; replays saved in the UI are kept.
\set ON_ERROR_STOP on
DELETE FROM session_replay r
WHERE r.created_at < now() - interval '30 days'
  AND NOT EXISTS (
    SELECT 1 FROM session_replay_saved s
    WHERE s.website_id = r.website_id AND s.visit_id = r.visit_id
  );
