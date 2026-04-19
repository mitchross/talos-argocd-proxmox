# news-reader (app source)

Next.js 16 frontend for the `news-reader` cluster app. This directory is the
source tree that gets built into the container image referenced by
`../deployment.yaml` (`registry.vanillax.me/news-reader:latest`).

The surrounding Kubernetes manifests (`../deployment.yaml`, `../service.yaml`,
`../httproute.yaml`, `../namespace.yaml`, `../kustomization.yaml`) are what
ArgoCD actually deploys. This folder is *just* the app source + Dockerfile.

## Stack

| Piece            | Version / Note                                                  |
|------------------|-----------------------------------------------------------------|
| Next.js          | 16.2.2 (standalone output — required by the multi-stage Dockerfile) |
| React            | 19.2.4                                                          |
| Tailwind         | v4 (via `@tailwindcss/postcss`)                                 |
| Temporal client  | `@temporalio/client` 1.15 — talks to the Temporal frontend in-cluster |
| Node runtime     | `node:24-slim` (builder + runner stages)                        |

> ⚠️ **Not vanilla Next.js.** See `AGENTS.md` — this Next.js has breaking
> changes vs. training-data-era Next.js. When editing, read the relevant guide
> in `node_modules/next/dist/docs/` first. Heed deprecation notices.

## How it fits in the cluster

```
user → news.vanillax.me (Cloudflare tunnel)
     → gateway-external (Cilium, sectionName: https)
     → HTTPRoute: news-reader
     → Service: news-reader:3000
     → Deployment: news-reader (this image)
     → Temporal (in-cluster, via @temporalio/client)
```

- **Namespace**: `news-reader`
- **Deployment strategy**: `Recreate` (no PVCs today, but kept consistent with
  the project pattern so adding a PVC later doesn't silently deadlock).
- **HTTPRoute**: external — has the three required pieces (`external-dns: "true"`
  label, `external-dns.alpha.kubernetes.io/target: vanillax.me` annotation,
  `sectionName: https` on the parentRef). Drop any of those and DNS/routing
  fails silently — see root `CLAUDE.md`.
- **Port**: container listens on `3000`, Service exposes `3000`, port named
  `http` on the container (required for HTTPRoute matching).

## Local development

```bash
# From this directory (my-apps/development/news-reader/app/)
npm install
npm run dev           # http://localhost:3000
```

`HOSTNAME=0.0.0.0` is set in the Deployment so the standalone server binds
to all interfaces inside the pod. You don't need it locally.

## Building the container

The Dockerfile is a two-stage build that relies on Next's
**standalone output** (`.next/standalone` + `.next/static`). If you change
`next.config.ts` to disable standalone, the runner stage will break — the
`server.js` entrypoint won't exist.

```bash
# From this directory
docker build -t registry.vanillax.me/news-reader:latest .
docker push registry.vanillax.me/news-reader:latest
```

ArgoCD picks up the new image on the next sync (image tag is pinned to
`:latest` — no automated bump wiring today, you push, you sync).

## Environment variables

Set on the Deployment, not baked into the image:

| Var        | Value       | Why                                                    |
|------------|-------------|--------------------------------------------------------|
| `HOSTNAME` | `0.0.0.0`   | Bind to all interfaces inside the pod (pods get unique IPs, not localhost). Without this, Next 16 standalone defaults to `localhost` and the probe/service traffic can't reach it. |

Add secrets via `ExternalSecret` → `envFrom: secretRef:` if/when this grows —
don't hardcode into the Deployment or the image. See root `my-apps/CLAUDE.md`
for the 1Password / ExternalSecret pattern.

## Resource budget

Current Deployment requests/limits (tight — it's a small SSR app):

```
requests: cpu 50m,  memory 128Mi
limits:   cpu 300m, memory 384Mi
```

If Temporal workflows start pulling large payloads through the client, bump
memory first — the client library buffers per-workflow.

## Files that matter

```
app/                 # Next.js app router pages & layouts
public/              # Static assets served from /
Dockerfile           # Two-stage build → standalone runner
next.config.ts       # Next config (keep output: 'standalone')
package.json         # Pinned versions — don't yolo-bump Next major
tsconfig.json        # Strict TS, path aliases
AGENTS.md            # Read before editing — Next 16 has breaking changes
```

## Gotchas

- **Standalone output is load-bearing.** The Dockerfile copies from
  `.next/standalone` — if you remove `output: 'standalone'` from
  `next.config.ts`, the image builds but won't run.
- **Temporal namespace/endpoint.** The Temporal client reads its connection
  config from env. Today it relies on defaults; if you add multi-tenancy or
  point at a different Temporal cluster, wire it through an `ExternalSecret`.
- **`:latest` tag.** No Renovate/digest pinning on this image yet — a rebuild
  with the same tag requires a manual ArgoCD hard refresh to redeploy, or
  switch to a digest / immutable tag.
