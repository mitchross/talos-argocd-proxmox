-- PersonHog reads require tombstone columns from upstream persons_migrations/20260727000002.
SET LOCAL lock_timeout = '2s';
ALTER TABLE public.posthog_person
    ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false;
ALTER TABLE public.posthog_persondistinctid
    ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false;
