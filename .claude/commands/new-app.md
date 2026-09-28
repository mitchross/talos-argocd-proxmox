Create a new application at `$ARGUMENTS` following the project's GitOps patterns.

## Requirements

1. Determine what the app needs by checking its documentation:
   - Basic deployment only?
   - Web access (HTTPRoute)?
   - GPU requirements?
   - Persistent storage (with backup)?
   - Secrets from 1Password?
   - Database (plain Postgres + kopiur — see /project:new-database)?

2. Create the directory structure under the appropriate category:
   - `my-apps/ai/` - GPU/LLM serving and AI apps
   - `my-apps/knowledge/` - Search, reading, notes, documents, AI memory
   - `my-apps/home-automation/` - Home Assistant, cameras, energy
   - `my-apps/media/` - Media services
   - `my-apps/utility/` - Small browser tools and dashboards
   - `my-apps/storage-utility/` - File sharing and transfer
   - `my-apps/development/` - Dev tools (git, CI, Renovate)
   - `my-apps/development-infra/` - Services other apps run on (Temporal, PostHog, map tiles)
   - `my-apps/personal-projects/` - Apps built from your own images
   - `my-apps/demo/` - Toys and learning experiments
   - `my-apps/system/` - Cluster-side helpers (restore canary, Headlamp)
   - `my-apps/<category>/_archive/` - Retired apps: not deployed, backups kept

3. Required files for every app:
   - `namespace.yaml`
   - `kustomization.yaml` (must list ALL resource files under `resources:`)
   - `deployment.yaml` or appropriate workload

4. Follow these critical rules:
   - Services MUST have named ports (`name: http`) for HTTPRoute — fails silently without this
   - Use Gateway API HTTPRoute (NOT Ingress) — reference `infrastructure/networking/gateway/`
   - Use ExternalSecret for secrets (never hardcode) — reference any app with `externalsecret.yaml`
   - PVCs needing backup: use `storageClassName: longhorn` and follow `.claude/commands/add-backup.md` for the kopiur per-PVC stub + `../../common/kopiur-backup` component + restore-before-bind `dataSourceRef`
   - GPU apps: follow `my-apps/ai/CLAUDE.md` for node selection and whole-card allocation.
   - Add an app-owned VPA or record an intentional exemption, following root `CLAUDE.md` and `docs/domains/scheduling/vpa-and-topology.md`.

5. Reference examples:
   - Minimal: the "Minimal Application" template in `my-apps/CLAUDE.md`
   - GPU: `my-apps/ai/comfyui/`
   - Storage + secrets: `my-apps/media/immich/`
   - Database: `my-apps/development/gitea/postgres/` (plain Postgres + kopiur)

6. Apply common Kustomize components where appropriate:
   ```yaml
   components:
   - ../../common/deployment-defaults
   ```

ArgoCD will auto-discover the app from the directory structure. No manual Application resource needed.
