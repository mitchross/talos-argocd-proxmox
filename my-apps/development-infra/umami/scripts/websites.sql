-- One Umami website per public site. IDs are fixed because the injector's nginx map
-- (infrastructure/networking/posthog-injector/default.conf) hard-codes them.
-- ON CONFLICT DO NOTHING: renames or deletes made in the UI are kept.
\set ON_ERROR_STOP on
-- Session replay for every site: all sessions, inputs masked, 30-minute cap per recording.
-- Radar masks all text (place names), matching its no-location analytics promise.
\set replay '{"replayEnabled": true, "sampleRate": 1, "maskLevel": "moderate", "maxDuration": 1800000}'
INSERT INTO website (website_id, name, domain, user_id, created_by, created_at, recorder_enabled, replay_config)
SELECT v.id::uuid, v.name, v.domain, u.user_id, u.user_id, now(), true,
  CASE WHEN v.id = '0fc02131-8623-4e19-87ee-25adb67064ee' THEN jsonb_set(:'replay'::jsonb, '{maskLevel}', '"strict"') ELSE :'replay'::jsonb END
FROM (VALUES
  ('c87c8c44-69f3-4647-bb5c-12c810aa7aef', 'Apps',            'apps.vanillax.me'),
  ('05113581-12df-4529-a771-240073ea3bd9', 'Product bench',   'bench.vanillax.me'),
  ('0d25cd9d-b47e-4ec1-b688-4199890f8d49', 'Deal scout',      'deals.vanillax.me'),
  ('a8b10991-46b2-4283-bd35-1ccb23bfc139', 'Excalidraw',      'excalidraw.vanillax.me'),
  ('f9178010-2df1-4d81-b20c-094aa9c4694b', 'Geocoder',        'geocode.vanillax.me'),
  ('2f6a027a-b8c1-4ed4-9605-d2a408441525', 'Homelab rack',    'homelab.vanillax.me'),
  ('a0a55c1e-e018-4757-a350-4fa16b13f66f', 'IT tools',        'it-tools.vanillax.me'),
  ('2da77add-7f25-433e-b30d-bec623cf0bc1', 'Karakeep',        'karakeep.vanillax.me'),
  ('94b3c7f2-8ff3-4b94-8d9d-3e0a3ede03ba', 'Kiwix',           'kiwix.vanillax.me'),
  ('b10d6cdd-a11e-420b-be47-528568deba09', 'Maps',            'maps.vanillax.me'),
  ('a3e06ce0-7d7b-405d-83d2-50d173fa94e4', 'News',            'news.vanillax.me'),
  ('0fc02131-8623-4e19-87ee-25adb67064ee', 'Radar',           'radar.vanillax.me'),
  ('d33a4be6-a593-4fe0-8795-b9214ce263c5', 'Redlib',          'redlib.vanillax.me'),
  ('f0c551a0-826d-41e6-90fa-d769bbb153e9', 'Search',          'search.vanillax.me'),
  ('43c210fb-4112-47c2-9ad8-ddd6ff12da97', 'Vert',            'vert.vanillax.me'),
  ('20e07135-77fd-4d0c-ac83-266d7b4bdab8', 'World monitor',   'worldmonitor.vanillax.me'),
  ('5c437932-a77e-4246-b52f-2899204818c1', 'Other vanillax.me', 'vanillax.me')
) AS v(id, name, domain)
CROSS JOIN (SELECT user_id FROM "user" WHERE username = 'admin' AND deleted_at IS NULL) u
ON CONFLICT (website_id) DO NOTHING;

-- Turn replay on for rows that never had recorder settings; a choice made in the UI is kept.
UPDATE website SET recorder_enabled = true, replay_config =
  CASE WHEN website_id = '0fc02131-8623-4e19-87ee-25adb67064ee' THEN jsonb_set(:'replay'::jsonb, '{maskLevel}', '"strict"') ELSE :'replay'::jsonb END
WHERE recorder_enabled = false AND replay_config IS NULL;
