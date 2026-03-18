Create a new application at `$ARGUMENTS` following the project's GitOps patterns.

## Requirements

1. Determine what the app needs by checking its documentation:
   - Basic deployment only?
   - Web access (HTTPRoute)?
   - GPU requirements?
   - Persistent storage (with backup)?
   - Secrets from 1Password?
   - Database (CNPG)?

2. Create the directory structure under the appropriate category:
   - `my-apps/ai/` - GPU/AI workloads
   - `my-apps/development/` - Dev tools
   - `my-apps/home/` - Home automation
   - `my-apps/media/` - Media services

3. Required files for every app:
   - `namespace.yaml`
   - `kustomization.yaml` (must list ALL resource files under `resources:`)
   - `deployment.yaml` or appropriate workload

4. Follow these critical rules:
   - Services MUST have named ports (`name: http`) for HTTPRoute — fails silently without this
   - Use Gateway API HTTPRoute (NOT Ingress) — reference `infrastructure/networking/gateway/`
   - Use ExternalSecret for secrets (never hardcode) — reference any app with `externalsecret.yaml`
   - PVCs needing backup: add `backup: "daily"` or `backup: "hourly"` label, use `storageClassName: longhorn`
   - GPU apps: use nodeSelector, runtimeClassName, tolerations, priorityClassName — reference `my-apps/ai/comfyui/`
   - CNPG databases go in `infrastructure/database/cloudnative-pg/<app>/` not in `my-apps/`

5. Reference examples:
   - Minimal: `my-apps/development/nginx/`
   - GPU: `my-apps/ai/comfyui/`
   - Storage + secrets: `my-apps/media/immich/`
   - Database: `infrastructure/database/cloudnative-pg/immich/`

6. Apply common Kustomize components where appropriate:
   ```yaml
   components:
   - ../../common/deployment-defaults
   ```

ArgoCD will auto-discover the app from the directory structure. No manual Application resource needed.
