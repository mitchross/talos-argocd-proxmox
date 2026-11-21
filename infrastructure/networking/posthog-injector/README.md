# posthog-injector

nginx between cloudflared and the external Gateway. On eligible pages (GET, 2xx, `text/html`,
not an asset path, injectable host) it adds one analytics block before `</head>`. Everything else
passes through untouched, compressed, with its validators. One `sub_filter`, `sub_filter_once on`.

## What is enabled

| Provider | State |
|---|---|
| PostHog | On for every injectable `*.vanillax.me` host, byte-for-byte as before. |
| Umami | Off for every host. `umami-sites.map` has no entries. |

Never injected: `radar` (loads PostHog and Umami itself), `posthog`, `ingest-posthog`, `umami`,
`ingest-umami`, `redlib`, `libreddit`, `otel`, `radar-ng-api`, `argocd-webhook`. That list is the
`$ph_host` map in `default.conf`; Umami entries can't override it.

## How the Umami loader behaves

A host listed in `umami-sites.map` gets a small inline loader after the PostHog snippet. It loads
`https://ingest-umami.vanillax.me/script.js` only when all of these hold:

- the visitor called `umamiConsent.grant()` (stored as `localStorage["umami.consent"] = "granted"`);
- no Do Not Track or Global Privacy Control signal;
- `localStorage` works (any error means no);
- no `umami.disabled` key and no PostHog opt-out (`__ph_opt_in_out_*` = `0`);
- the page has no Umami tracker of its own.

`?ph_optout=1` still opts the browser out of PostHog, and now also writes `umami.disabled=1` and
`umami.consent=denied`, so both stay off for that browser. `umamiConsent.revoke()` does the same
and reloads the page. A `beforeSend` hook re-checks consent on every event, so a revoke in another
tab stops sends too. The tracker gets `data-do-not-track="true"` and `data-domains=<this host>`.

The recorder (`recorder.js`) is never loaded: it ignores `umami.disabled` and DNT, and can't be
stopped once running. The public route doesn't expose it either.

## Still blocked

- **Website UUIDs.** None exist yet. Create each website in the Umami dashboard
  (`umami.vanillax.me`), then add `<host> <uuid>;` to `umami-sites.map`. Never add a placeholder.
- **A consent prompt.** Nothing calls `umamiConsent.grant()` yet, so even a listed host records
  nothing until a site (or a future injected banner) asks the visitor.
- **Ingest route.** The loader targets `ingest-umami.vanillax.me`; its route and cloudflared
  bypass are a separate PR.

## Cutover

1. Merge the ingest route; check `/script.js` loads publicly.
2. Create a website in Umami for one host, add its UUID here, merge. Check in a browser that no
   request reaches `ingest-umami` before `umamiConsent.grant()`, and that one arrives after.
3. Repeat per host. PostHog keeps running alongside for the comparison period.
4. To retire PostHog, empty the `$ph_snippet` value and update `POSTHOG_SHA256` in
   `tests/test_umami_sites.py`; nothing else changes.

## Tests

```bash
python3 -m unittest discover -s infrastructure/networking/posthog-injector/tests -v
```

`test_proxy.py` runs the real nginx image against a TLS origin and needs Docker. It writes a
temporary `umami-sites.map` with a UUID generated per run, so no UUID lives in the repo.
`test_umami_sites.py` validates the map and runs `umami_loader.test.cjs` with `node`.
