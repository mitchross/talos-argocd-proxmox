Create a new application at `$ARGUMENTS` following the project's GitOps patterns.

## Requirements

1. Determine what the app needs by checking its documentation:
   - Basic deployment only?
   - Web access (HTTPRoute)?
   - GPU requirements?
   - Persistent storage (with backup)?
   - Secrets from 1Password?
   - Database (CNPG)?

2. Create the shared workload source and per-cluster deployable overlays:
   - `manifests/apps/<category>/<app>/base/`
   - `clusters/talos/apps/<category>/<app>/`
   - `clusters/openshift/apps/<category>/<app>/` when the app is intended for OpenShift

   Categories currently include `ai`, `development`, `home`, `media`,
   `privacy`, and `utility`.

3. Required shared-base files for every app:
   - `namespace.yaml`
   - `kustomization.yaml` (must list ALL resource files under `resources:`)
   - `deployment.yaml` or appropriate workload

4. Follow these critical rules:
   - Services MUST have named ports (`name: http`) for HTTPRoute — fails silently without this
   - Use complete cluster-owned Gateway API HTTPRoutes (NOT Ingress); reference
     `clusters/talos/infra/gateway/` and `clusters/openshift/infra/gateway/`
   - Use ExternalSecret for secrets (never hardcode) — reference any app with `externalsecret.yaml`
   - Shared app PVCs use `storageClassName: vanillax-local-rwo`; follow
     `.claude/commands/add-backup.md` for Talos pvc-plumber labels and static
     `dataSourceRef`
   - GPU apps: use nodeSelector, runtimeClassName, tolerations, priorityClassName — reference `manifests/apps/ai/comfyui/base/`
   - CNPG databases go under `manifests/database/cloudnative-pg/<app>/` with
     a Talos deploy target under `clusters/talos/database/`, not under apps

5. Reference examples:
   - Minimal: `manifests/apps/development/nginx/base/` + `clusters/*/apps/development/nginx/`
   - GPU: `manifests/apps/ai/comfyui/base/`
   - Storage + secrets: `manifests/apps/media/immich/base/`
   - Database: `manifests/database/cloudnative-pg/immich/` + `clusters/talos/database/cloudnative-pg/immich/`

App ApplicationSets auto-discover `clusters/<cluster>/apps/*/*`. Do not add app
`.argocd/config.json` files or manual app `Application` resources.
