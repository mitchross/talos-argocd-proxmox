# One-Shot Multicluster Kustomize and Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented and locally accepted on June 4, 2026. Live OpenShift
schema and controller verification remains an operator action.

**Goal:** Finish the cluster-centric multicluster migration so Talos and OpenShift independently bootstrap local Argo CD instances, discover all 44 app overlays per cluster without redundant metadata files, share genuinely portable infrastructure bases, and keep Kustomize patches readable.

**Architecture:** `manifests/` holds shared reusable definitions and `clusters/<cluster>/` remains the deployable overlay boundary. Talos and OpenShift each run one local upstream Helm Argo CD that deploys only to `https://kubernetes.default.svc`. App ApplicationSets derive metadata from directory paths; explicit infrastructure, database, monitoring, and standalone entrypoints retain their existing ordering controls.

**Tech Stack:** Kubernetes, Kustomize 5.x, Argo CD ApplicationSets, Bash, Helm, Cilium CLI, OpenShift/OKD 4.20 Gateway API, GitHub Actions

---

## Locked Boundaries

- Perform the migration in one feature branch; do not pilot only one app.
- Preserve all 44 Talos and 44 OpenShift app overlays.
- Preserve generated Application names, projects, namespaces, source paths,
  sync waves, and local destinations.
- Keep `targetRevision: main`.
- Keep one independent local upstream Helm Argo CD per cluster.
- Do not add a hub Argo CD, cluster registration, Matrix generator, OpenShift
  GitOps Operator, or ArgoCD custom resource.
- Do not implement a GKE profile in this migration; the profile interface must
  remain extensible for a future GKE cluster.
- Do not add a redundant `clusters/<cluster>/overlays` directory.
- Do not add Kustomize components in this migration.
- Do not neutralize all Talos-first app bases in this migration.
- Do not execute live `kubectl apply`, `oc apply`, `helm upgrade`, Cilium
  installation, or any other live mutation while implementing and validating
  the branch.

## Verified Starting Point

The following baseline was verified locally on June 4, 2026:

- 44 Talos app overlays.
- 44 OpenShift app overlays.
- 88 app `.argocd/config.json` files whose values are fully derivable.
- 30 non-app `.argocd/config.json` files that retain meaningful explicit
  metadata and remain in place.
- 25 multiline inline patches across five kustomizations.
- 155 cluster kustomizations render successfully.
- `1passwordconnect`, `cert-manager`, and `external-secrets` are byte-identical
  between Talos and OpenShift.
- Existing local validation scripts pass.
- OpenShift app render validation passes for all 44 overlays.

## File Map

### Create

- `scripts/bootstrap-cluster.sh`
- `scripts/validate-bootstrap-profiles.sh`
- `clusters/openshift/infra/gateway/gatewayclass.yaml`
- `manifests/infra/1passwordconnect/base/kustomization.yaml`
- `manifests/infra/1passwordconnect/base/values.yaml`
- `manifests/infra/cert-manager/base/kustomization.yaml`
- `manifests/infra/cert-manager/base/ns.yaml`
- `manifests/infra/cert-manager/base/cloudflare-external-secret.yaml`
- `manifests/infra/cert-manager/base/cluster-issuer.yaml`
- `manifests/infra/cert-manager/base/values.yaml`
- `manifests/infra/external-secrets/base/kustomization.yaml`
- `manifests/infra/external-secrets/base/cluster-secret-store.yaml`
- `manifests/infra/external-secrets/base/external-secret.yaml`
- `manifests/infra/external-secrets/base/values.yaml`
- `manifests/infra/external-secrets/base/patches/crd-externalsecrets-ssa.yaml`
- `manifests/infra/external-secrets/base/patches/crd-clustersecretstores-ssa.yaml`
- `manifests/infra/external-secrets/base/patches/crd-secretstores-ssa.yaml`
- `manifests/infra/external-secrets/base/patches/crd-clusterexternalsecrets-ssa.yaml`
- `manifests/infra/external-secrets/base/patches/crd-pushsecrets-ssa.yaml`
- `manifests/infra/external-secrets/base/patches/crd-clusterpushsecrets-ssa.yaml`
- `manifests/infra/external-secrets/base/patches/crd-clustergenerators-ssa.yaml`
- `manifests/infra/external-secrets/base/patches/crd-generatorstates-ssa.yaml`
- `clusters/talos/database/cloudnative-pg/cloudnative-pg-operator/patches/crd-clusters-sync-options.yaml`
- `clusters/talos/database/cloudnative-pg/cloudnative-pg-operator/patches/crd-poolers-sync-options.yaml`
- `clusters/talos/database/cnpg-barman-plugin/patches/delete-cnpg-system-namespace.yaml`
- `clusters/talos/monitoring/prometheus-stack/patches/alertmanager-config.yaml`
- `clusters/talos/monitoring/prometheus-stack/patches/crd-scrapeconfigs-sync-options.yaml`
- `clusters/talos/monitoring/prometheus-stack/patches/crd-thanosrulers-sync-options.yaml`
- `clusters/talos/monitoring/prometheus-stack/patches/crd-alertmanagerconfigs-sync-options.yaml`
- `clusters/talos/monitoring/prometheus-stack/patches/crd-alertmanagers-sync-options.yaml`
- `clusters/talos/monitoring/prometheus-stack/patches/crd-prometheusagents-sync-options.yaml`
- `clusters/talos/monitoring/prometheus-stack/patches/crd-prometheuses-sync-options.yaml`
- `manifests/apps/development/temporal/base/patches/delete-temporal-server-serviceaccount.yaml`
- `manifests/apps/development/gitea/base/patches/gitea-config-secret.yaml`

### Modify

- `clusters/talos/argocd/appsets/my-apps-appset.yaml`
- `clusters/openshift/argocd/appsets/apps-appset.yaml`
- All existing Argo CD files containing
  `argocd.argoproj.io/manifest-generate-paths` under:
  - `clusters/talos/argocd/`
  - `clusters/openshift/argocd/`
  - `clusters/talos/bootstrap/root.yaml`
  - `clusters/openshift/bootstrap/root.yaml`
- `clusters/talos/infra/1passwordconnect/kustomization.yaml`
- `clusters/openshift/infra/1passwordconnect/kustomization.yaml`
- `clusters/talos/infra/cert-manager/kustomization.yaml`
- `clusters/openshift/infra/cert-manager/kustomization.yaml`
- `clusters/talos/infra/external-secrets/kustomization.yaml`
- `clusters/openshift/infra/external-secrets/kustomization.yaml`
- `clusters/talos/database/cloudnative-pg/cloudnative-pg-operator/kustomization.yaml`
- `clusters/talos/database/cnpg-barman-plugin/kustomization.yaml`
- `clusters/talos/monitoring/prometheus-stack/kustomization.yaml`
- `manifests/apps/development/temporal/base/kustomization.yaml`
- `manifests/apps/development/gitea/base/kustomization.yaml`
- `clusters/openshift/infra/gateway/kustomization.yaml`
- `clusters/openshift/infra/gateway/gateway.yaml`
- `clusters/openshift/infra/gateway/httproute-argocd.yaml`
- `scripts/bootstrap-argocd.sh`
- `scripts/validate-argocd-apps.sh`
- `scripts/validate-cluster-layout.sh`
- `.github/workflows/cluster-ci.yml`
- `README.md`
- `clusters/talos/bootstrap/README.md`
- `clusters/openshift/bootstrap/README.md`
- `docs/cluster-dr-nuke-restore-runbook.md`
- `docs/domains/argocd/entrypoints.md`
- `docs/domains/multicluster/handoff-notes.md`
- `docs/domains/multicluster/openshift-storage-and-app-migration.md`
- `docs/domains/multicluster/prd.md`
- `docs/superpowers/specs/2026-06-04-multicluster-kustomize-and-bootstrap-design.md`

### Delete

- `clusters/talos/apps/*/*/.argocd/config.json` (44 files)
- `clusters/openshift/apps/*/*/.argocd/config.json` (44 files)
- `clusters/talos/infra/1passwordconnect/values.yaml`
- `clusters/talos/infra/1passwordconnect/namespace.yaml`
- `clusters/openshift/infra/1passwordconnect/values.yaml`
- `clusters/openshift/infra/1passwordconnect/namespace.yaml`
- `clusters/talos/infra/cert-manager/ns.yaml`
- `clusters/talos/infra/cert-manager/cloudflare-external-secret.yaml`
- `clusters/talos/infra/cert-manager/cluster-issuer.yaml`
- `clusters/talos/infra/cert-manager/values.yaml`
- `clusters/openshift/infra/cert-manager/ns.yaml`
- `clusters/openshift/infra/cert-manager/cloudflare-external-secret.yaml`
- `clusters/openshift/infra/cert-manager/cluster-issuer.yaml`
- `clusters/openshift/infra/cert-manager/values.yaml`
- `clusters/talos/infra/external-secrets/cluster-secret-store.yaml`
- `clusters/talos/infra/external-secrets/external-secret.yaml`
- `clusters/talos/infra/external-secrets/ns.yaml`
- `clusters/talos/infra/external-secrets/values.yaml`
- `clusters/openshift/infra/external-secrets/cluster-secret-store.yaml`
- `clusters/openshift/infra/external-secrets/external-secret.yaml`
- `clusters/openshift/infra/external-secrets/ns.yaml`
- `clusters/openshift/infra/external-secrets/values.yaml`

The four namespace files above are currently unreferenced. Their deletion must
not change rendered output.

## Task 1: Capture the Pre-Migration Contract

**Files:**
- No tracked files change.
- Create temporary evidence under `/tmp/multicluster-kustomize-baseline`.

- [ ] **Step 1: Confirm the implementation branch and clean starting state**

Run:

```bash
git status --short --branch
git log -1 --oneline
```

Expected: branch is `feat/one-shot-multicluster-kustomize`; no unexpected
working-tree changes exist.

- [ ] **Step 2: Capture the current generated app contract**

Run:

```bash
rm -rf /tmp/multicluster-kustomize-baseline
mkdir -p /tmp/multicluster-kustomize-baseline

python3 - <<'PY' > /tmp/multicluster-kustomize-baseline/apps-before.tsv
import json
from pathlib import Path

for cluster in ("talos", "openshift"):
    pattern = Path(f"clusters/{cluster}/apps").glob("*/*/.argocd/config.json")
    for path in sorted(pattern):
        data = json.loads(path.read_text(encoding="utf-8"))
        print(
            data["applicationName"],
            data["project"],
            data["namespace"],
            data["syncWave"],
            data["sourcePath"],
            "https://kubernetes.default.svc",
            sep="\t",
        )
PY

wc -l /tmp/multicluster-kustomize-baseline/apps-before.tsv
```

Expected: `88` lines.

- [ ] **Step 3: Capture all app overlay renders**

Run:

```bash
mkdir -p /tmp/multicluster-kustomize-baseline/apps-before

for cluster in talos openshift; do
  while IFS= read -r file; do
    dir="${file%/kustomization.yaml}"
    rel="${dir#clusters/$cluster/apps/}"
    out="/tmp/multicluster-kustomize-baseline/apps-before/${cluster}-${rel//\//_}.yaml"
    kustomize build --enable-helm "$dir" >"$out"
  done < <(find "clusters/$cluster/apps" -mindepth 3 -maxdepth 3 \
    -type f -name kustomization.yaml -print | sort)
done

find /tmp/multicluster-kustomize-baseline/apps-before -type f | wc -l
```

Expected: `88` render files.

- [ ] **Step 4: Capture the render-sensitive infrastructure targets**

Run:

```bash
mkdir -p /tmp/multicluster-kustomize-baseline/targets-before

for dir in \
  clusters/talos/infra/1passwordconnect \
  clusters/openshift/infra/1passwordconnect \
  clusters/talos/infra/cert-manager \
  clusters/openshift/infra/cert-manager \
  clusters/talos/infra/external-secrets \
  clusters/openshift/infra/external-secrets \
  clusters/talos/database/cloudnative-pg/cloudnative-pg-operator \
  clusters/talos/database/cnpg-barman-plugin \
  clusters/talos/monitoring/prometheus-stack
do
  out="/tmp/multicluster-kustomize-baseline/targets-before/${dir//\//_}.yaml"
  kustomize build --enable-helm "$dir" >"$out"
done
```

Expected: all nine builds exit `0`.

- [ ] **Step 5: Prove the existing baseline is green**

Run:

```bash
./scripts/validate-cluster-layout.sh
./scripts/validate-argocd-apps.sh
./scripts/validate-openshift-app-renders.sh
shellcheck -S warning scripts/*.sh
```

Expected: every command exits `0`.

## Task 2: Replace App Metadata Files with Directory Discovery

**Files:**
- Modify: `clusters/talos/argocd/appsets/my-apps-appset.yaml`
- Modify: `clusters/openshift/argocd/appsets/apps-appset.yaml`
- Modify: `scripts/validate-argocd-apps.sh`
- Modify: `scripts/validate-cluster-layout.sh`
- Delete: `clusters/talos/apps/*/*/.argocd/config.json`
- Delete: `clusters/openshift/apps/*/*/.argocd/config.json`

- [ ] **Step 1: Add the failing app metadata guardrail**

Add this check to `scripts/validate-cluster-layout.sh`:

```bash
while IFS= read -r path; do
  fail "app overlay metadata is derivable and must not remain: $path"
done < <(
  find clusters/talos/apps clusters/openshift/apps \
    -path '*/.argocd/config.json' -type f -print | sort
)
```

Run:

```bash
./scripts/validate-cluster-layout.sh
```

Expected: failure listing exactly 88 app metadata files.

- [ ] **Step 2: Convert the Talos app ApplicationSet**

In `clusters/talos/argocd/appsets/my-apps-appset.yaml`, replace the Git file
generator and metadata-derived fields with:

```yaml
  generators:
  - git:
      repoURL: https://github.com/mitchross/talos-argocd-proxmox.git
      revision: main
      directories:
      - path: clusters/talos/apps/*/*
  template:
    metadata:
      name: "talos-apps-{{index .path.segments 3}}-{{.path.basename}}"
      annotations:
        argocd.argoproj.io/manifest-generate-paths: ".;/manifests/apps/{{index .path.segments 3}}/{{.path.basename}}/base"
        argocd.argoproj.io/sync-wave: "6"
    spec:
      project: talos-apps
      revisionHistoryLimit: 3
      source:
        repoURL: https://github.com/mitchross/talos-argocd-proxmox.git
        targetRevision: main
        path: "{{.path.path}}"
      destination:
        server: https://kubernetes.default.svc
        namespace: "{{.path.basename}}"
```

Preserve the existing Talos app sync policy, retry behavior,
`ignoreApplicationDifferences`, `ignoreDifferences`, and `info` blocks.
Change the existing `info` value from the removed `{{.namespace}}` metadata
field to:

```yaml
      info:
      - name: 'Description'
        value: "Application: {{.path.basename}}"
```

- [ ] **Step 3: Convert the OpenShift app ApplicationSet**

In `clusters/openshift/argocd/appsets/apps-appset.yaml`, use:

```yaml
  generators:
    - git:
        repoURL: https://github.com/mitchross/talos-argocd-proxmox.git
        revision: main
        directories:
          - path: clusters/openshift/apps/*/*
  template:
    metadata:
      name: "openshift-apps-{{index .path.segments 3}}-{{.path.basename}}"
      annotations:
        argocd.argoproj.io/manifest-generate-paths: ".;/manifests/apps/{{index .path.segments 3}}/{{.path.basename}}/base"
        argocd.argoproj.io/sync-wave: "6"
    spec:
      project: openshift-apps
      revisionHistoryLimit: 3
      source:
        repoURL: https://github.com/mitchross/talos-argocd-proxmox.git
        targetRevision: main
        path: "{{.path.path}}"
      destination:
        server: https://kubernetes.default.svc
        namespace: "{{.path.basename}}"
```

Preserve the existing OpenShift app sync policy and retry behavior.

- [ ] **Step 4: Teach Argo validation to derive app metadata**

In `scripts/validate-argocd-apps.sh`, keep `metadata_files()` for explicit
non-app metadata only:

```bash
metadata_files() {
  local cluster="$1"
  find "clusters/$cluster" -path "*/.argocd/config.json" -type f \
    ! -path "clusters/$cluster/apps/*/*/.argocd/config.json" | sort
}
```

Add:

```bash
app_overlay_dirs() {
  local cluster="$1"
  find "clusters/$cluster/apps" -mindepth 3 -maxdepth 3 \
    -type f -name kustomization.yaml -printf '%h\n' | sort
}

derived_app_name() {
  local cluster="$1"
  local dir="$2"
  local relative="${dir#clusters/$cluster/apps/}"
  local category="${relative%%/*}"
  local app="${relative#*/}"
  printf '%s-apps-%s-%s\n' "$cluster" "$category" "$app"
}
```

Use `app_overlay_dirs()` in duplicate-name, sync-wave, and source-path checks.
Every derived app contributes:

```text
name        = <cluster>-apps-<category>-<app>
project     = <cluster>-apps
namespace   = <app>
sync wave   = 6
source path = clusters/<cluster>/apps/<category>/<app>
destination = https://kubernetes.default.svc
```

Add a check that each cluster has exactly 44 app overlay directories.

- [ ] **Step 5: Delete the redundant app metadata**

Run:

```bash
find clusters/talos/apps clusters/openshift/apps \
  -path '*/.argocd/config.json' -type f -delete

find clusters/talos/apps clusters/openshift/apps \
  -path '*/.argocd/config.json' -type f -print | wc -l
```

Expected: `0`.

- [ ] **Step 6: Compare the derived Application contract to the baseline**

Run:

```bash
python3 - <<'PY' > /tmp/multicluster-kustomize-baseline/apps-after.tsv
from pathlib import Path

for cluster in ("talos", "openshift"):
    root = Path(f"clusters/{cluster}/apps")
    for kustomization in sorted(root.glob("*/*/kustomization.yaml")):
        app_dir = kustomization.parent
        category = app_dir.parent.name
        app = app_dir.name
        print(
            f"{cluster}-apps-{category}-{app}",
            f"{cluster}-apps",
            app,
            "6",
            str(app_dir),
            "https://kubernetes.default.svc",
            sep="\t",
        )
PY

diff -u \
  /tmp/multicluster-kustomize-baseline/apps-before.tsv \
  /tmp/multicluster-kustomize-baseline/apps-after.tsv
```

Expected: no diff.

- [ ] **Step 7: Verify the generator migration**

Run:

```bash
./scripts/validate-cluster-layout.sh
./scripts/validate-argocd-apps.sh
kustomize build clusters/talos/argocd >/tmp/talos-argocd-after-appset.yaml
kustomize build clusters/openshift/argocd >/tmp/openshift-argocd-after-appset.yaml

! rg -n -F \
  -e '{{.applicationName}}' -e '{{.project}}' -e '{{.namespace}}' \
  -e '{{.syncWave}}' -e '{{.sourcePath}}' \
  clusters/talos/argocd/appsets/my-apps-appset.yaml \
  clusters/openshift/argocd/appsets/apps-appset.yaml
```

Expected: all commands exit `0`; validation reports 44 app overlays for each
cluster; neither app ApplicationSet references removed JSON metadata fields.

- [ ] **Step 8: Commit the app discovery migration**

```bash
git add clusters/talos/argocd/appsets/my-apps-appset.yaml \
  clusters/openshift/argocd/appsets/apps-appset.yaml \
  clusters/talos/apps clusters/openshift/apps \
  scripts/validate-argocd-apps.sh scripts/validate-cluster-layout.sh
git commit -m "refactor(argocd): derive app discovery from directories"
```

## Task 3: Correct Argo Manifest Generation Paths

**Files:**
- Modify every file returned by:

```bash
rg -l 'argocd.argoproj.io/manifest-generate-paths:' \
  clusters/talos/argocd clusters/openshift/argocd \
  clusters/talos/bootstrap clusters/openshift/bootstrap
```

- Modify: `scripts/validate-cluster-layout.sh`

- [ ] **Step 1: Add the failing manifest path guardrail**

Add checks to `scripts/validate-cluster-layout.sh` that reject:

```bash
rg -l 'manifest-generate-paths:[[:space:]]+clusters/' clusters --glob '*.yaml'
rg -l 'manifest-generate-paths:[[:space:]]+"{{\.sourcePath}}"' clusters --glob '*.yaml'
```

Each match must call `fail` because Argo interprets these values relative to
the Application source path.

Run:

```bash
./scripts/validate-cluster-layout.sh
```

Expected: failure listing the current invalid annotations.

- [ ] **Step 2: Correct root and standalone Application annotations**

Use these exact contracts:

```text
Root Applications:
  .

Standalone Applications whose source is under clusters/<cluster>/infra:
  .;/manifests/infra

Standalone cnpg-barman-plugin Application:
  .;/manifests/database
```

This changes only Application annotations. It does not change source paths,
projects, waves, or destinations.

- [ ] **Step 3: Correct explicit ApplicationSet annotations**

Use:

```text
Talos infrastructure AppSet:      .;/manifests/infra
OpenShift infrastructure AppSet:  .;/manifests/infra
Talos database AppSet:            .;/manifests/database
Talos monitoring AppSet:          .;/manifests/monitoring
```

Keep each existing file generator and explicit metadata contract unchanged.

- [ ] **Step 4: Verify the manifest path contract**

Run:

```bash
./scripts/validate-cluster-layout.sh
./scripts/validate-argocd-apps.sh

rg -n 'manifest-generate-paths:[[:space:]]+clusters/' clusters || true
rg -n 'manifest-generate-paths:[[:space:]]+"{{\.sourcePath}}"' clusters || true
```

Expected: validation passes and both `rg` commands produce no output.

- [ ] **Step 5: Commit the cache invalidation correction**

```bash
git add clusters/talos/argocd clusters/openshift/argocd \
  clusters/talos/bootstrap/root.yaml clusters/openshift/bootstrap/root.yaml \
  scripts/validate-cluster-layout.sh
git commit -m "fix(argocd): include shared bases in manifest paths"
```

## Task 4: Hoist Portable Infrastructure into Shared Bases

**Files:**
- Create: `manifests/infra/1passwordconnect/base/**`
- Create: `manifests/infra/cert-manager/base/**`
- Create: `manifests/infra/external-secrets/base/**`
- Modify: `clusters/{talos,openshift}/infra/{1passwordconnect,cert-manager,external-secrets}/kustomization.yaml`
- Delete duplicate cluster-owned source files listed in the File Map.

- [ ] **Step 1: Move the byte-identical portable sources**

Use the Talos copies as the source for the new shared bases. Preserve file
contents exactly before externalizing the External Secrets patches.

The final cluster entrypoint content is:

```yaml
# clusters/talos/infra/1passwordconnect/kustomization.yaml
# clusters/openshift/infra/1passwordconnect/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - "../../../../manifests/infra/1passwordconnect/base"
```

```yaml
# clusters/talos/infra/cert-manager/kustomization.yaml
# clusters/openshift/infra/cert-manager/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - "../../../../manifests/infra/cert-manager/base"
```

```yaml
# clusters/talos/infra/external-secrets/kustomization.yaml
# clusters/openshift/infra/external-secrets/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - "../../../../manifests/infra/external-secrets/base"
```

- [ ] **Step 2: Externalize the shared External Secrets CRD patches**

The shared External Secrets base kustomization must list:

```yaml
patches:
  - path: patches/crd-externalsecrets-ssa.yaml
  - path: patches/crd-clustersecretstores-ssa.yaml
  - path: patches/crd-secretstores-ssa.yaml
  - path: patches/crd-clusterexternalsecrets-ssa.yaml
  - path: patches/crd-pushsecrets-ssa.yaml
  - path: patches/crd-clusterpushsecrets-ssa.yaml
  - path: patches/crd-clustergenerators-ssa.yaml
  - path: patches/crd-generatorstates-ssa.yaml
```

Every patch is a declarative `apiextensions.k8s.io/v1`
`CustomResourceDefinition` patch. Every file includes
`metadata.annotations.argocd.argoproj.io/sync-options: ServerSideApply=true`.
Use these exact CRD names and additional annotations:

| Patch file | CRD name | Additional annotations |
|---|---|---|
| `crd-externalsecrets-ssa.yaml` | `externalsecrets.external-secrets.io` | `api-approved.kubernetes.io: "unapproved, request-not-required"` and `external-secrets.io/conversion-strategy: "none"` |
| `crd-clustersecretstores-ssa.yaml` | `clustersecretstores.external-secrets.io` | `api-approved.kubernetes.io: "unapproved, request-not-required"` and `external-secrets.io/conversion-strategy: "none"` |
| `crd-secretstores-ssa.yaml` | `secretstores.external-secrets.io` | none |
| `crd-clusterexternalsecrets-ssa.yaml` | `clusterexternalsecrets.external-secrets.io` | none |
| `crd-pushsecrets-ssa.yaml` | `pushsecrets.external-secrets.io` | none |
| `crd-clusterpushsecrets-ssa.yaml` | `clusterpushsecrets.external-secrets.io` | none |
| `crd-clustergenerators-ssa.yaml` | `clustergenerators.generators.external-secrets.io` | none |
| `crd-generatorstates-ssa.yaml` | `generatorstates.generators.external-secrets.io` | none |

- [ ] **Step 3: Remove unreferenced duplicate namespace files**

Delete:

```text
clusters/talos/infra/1passwordconnect/namespace.yaml
clusters/openshift/infra/1passwordconnect/namespace.yaml
clusters/talos/infra/external-secrets/ns.yaml
clusters/openshift/infra/external-secrets/ns.yaml
```

These files are not listed by the current kustomizations, so render parity must
remain exact.

- [ ] **Step 4: Compare all six portable infrastructure renders**

Run:

```bash
mkdir -p /tmp/multicluster-kustomize-baseline/targets-after

for dir in \
  clusters/talos/infra/1passwordconnect \
  clusters/openshift/infra/1passwordconnect \
  clusters/talos/infra/cert-manager \
  clusters/openshift/infra/cert-manager \
  clusters/talos/infra/external-secrets \
  clusters/openshift/infra/external-secrets
do
  out="/tmp/multicluster-kustomize-baseline/targets-after/${dir//\//_}.yaml"
  before="/tmp/multicluster-kustomize-baseline/targets-before/${dir//\//_}.yaml"
  kustomize build --enable-helm "$dir" >"$out"
  diff -u "$before" "$out"
done
```

Expected: all six diffs are empty.

- [ ] **Step 5: Commit the portable shared bases**

```bash
git add manifests/infra/1passwordconnect manifests/infra/cert-manager \
  manifests/infra/external-secrets \
  clusters/talos/infra/1passwordconnect clusters/openshift/infra/1passwordconnect \
  clusters/talos/infra/cert-manager clusters/openshift/infra/cert-manager \
  clusters/talos/infra/external-secrets clusters/openshift/infra/external-secrets
git commit -m "refactor(kustomize): share portable infrastructure bases"
```

## Task 5: Externalize the Remaining Kustomize Patches

**Files:**
- Modify: `clusters/talos/database/cloudnative-pg/cloudnative-pg-operator/kustomization.yaml`
- Create: `clusters/talos/database/cloudnative-pg/cloudnative-pg-operator/patches/*.yaml`
- Modify: `clusters/talos/database/cnpg-barman-plugin/kustomization.yaml`
- Create: `clusters/talos/database/cnpg-barman-plugin/patches/delete-cnpg-system-namespace.yaml`
- Modify: `clusters/talos/monitoring/prometheus-stack/kustomization.yaml`
- Move: `clusters/talos/monitoring/prometheus-stack/alertmanager-config.yaml`
  to `clusters/talos/monitoring/prometheus-stack/patches/alertmanager-config.yaml`
- Create: `clusters/talos/monitoring/prometheus-stack/patches/crd-*-sync-options.yaml`
- Modify: `scripts/validate-cluster-layout.sh`

- [ ] **Step 1: Add failing Kustomize readability guardrails**

Add checks to `scripts/validate-cluster-layout.sh` that fail on:

```bash
rg -l '^[[:space:]]+patch:[[:space:]]+\|[-+]?$' clusters --glob 'kustomization.yaml'
rg -l '^[[:space:]]*(patchesStrategicMerge|patchesJson6902|bases):' \
  clusters --glob 'kustomization.yaml'
```

Run:

```bash
./scripts/validate-cluster-layout.sh
```

Expected: failure naming the remaining inline-patch kustomizations and
`clusters/talos/monitoring/prometheus-stack/kustomization.yaml` for
`patchesStrategicMerge`.

- [ ] **Step 2: Externalize CloudNativePG operator CRD annotations**

Create two declarative patch files:

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: clusters.postgresql.cnpg.io
  annotations:
    argocd.argoproj.io/sync-options: ServerSideApply=true,Replace=true
```

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: poolers.postgresql.cnpg.io
  annotations:
    argocd.argoproj.io/sync-options: ServerSideApply=true,Replace=true
```

Reference them with unified `patches:` and remove both inline JSON6902 blocks.

- [ ] **Step 3: Externalize the Barman namespace deletion**

Create `clusters/talos/database/cnpg-barman-plugin/patches/delete-cnpg-system-namespace.yaml`:

```yaml
$patch: delete
apiVersion: v1
kind: Namespace
metadata:
  name: cnpg-system
```

Reference it with:

```yaml
patches:
  - path: patches/delete-cnpg-system-namespace.yaml
```

- [ ] **Step 4: Externalize Prometheus stack patches**

Move `alertmanager-config.yaml` under `patches/` and reference every patch
through unified `patches:`.

Each CRD sync-options patch is a declarative `apiextensions.k8s.io/v1`
`CustomResourceDefinition` patch with
`metadata.annotations.argocd.argoproj.io/sync-options:
ServerSideApply=true,Replace=true`. Use these exact names:

```text
scrapeconfigs.monitoring.coreos.com
thanosrulers.monitoring.coreos.com
alertmanagerconfigs.monitoring.coreos.com
alertmanagers.monitoring.coreos.com
prometheusagents.monitoring.coreos.com
prometheuses.monitoring.coreos.com
```

Remove `patchesStrategicMerge:` and all six inline JSON6902 blocks.

- [ ] **Step 5: Compare render output for all remaining patch targets**

Run:

```bash
for dir in \
  clusters/talos/database/cloudnative-pg/cloudnative-pg-operator \
  clusters/talos/database/cnpg-barman-plugin \
  clusters/talos/monitoring/prometheus-stack
do
  out="/tmp/multicluster-kustomize-baseline/targets-after/${dir//\//_}.yaml"
  before="/tmp/multicluster-kustomize-baseline/targets-before/${dir//\//_}.yaml"
  kustomize build --enable-helm "$dir" >"$out"
  diff -u "$before" "$out"
done
```

Expected: all three diffs are empty.

- [ ] **Step 6: Verify and commit the patch cleanup**

Run:

```bash
./scripts/validate-cluster-layout.sh
rg -n '^[[:space:]]+patch:[[:space:]]+\|[-+]?$' clusters --glob 'kustomization.yaml' || true
rg -n '^[[:space:]]*(patchesStrategicMerge|patchesJson6902|bases):' \
  clusters --glob 'kustomization.yaml' || true
```

Expected: validation passes and both `rg` commands produce no output.

Commit:

```bash
git add clusters/talos/database/cloudnative-pg/cloudnative-pg-operator \
  clusters/talos/database/cnpg-barman-plugin \
  clusters/talos/monitoring/prometheus-stack \
  scripts/validate-cluster-layout.sh
git commit -m "refactor(kustomize): externalize remaining patches"
```

## Task 6: Add OpenShift GatewayClass and Profile-Driven Bootstrap

**Files:**
- Create: `clusters/openshift/infra/gateway/gatewayclass.yaml`
- Modify: `clusters/openshift/infra/gateway/kustomization.yaml`
- Modify: `clusters/openshift/infra/gateway/gateway.yaml`
- Modify: `clusters/openshift/infra/gateway/httproute-argocd.yaml`
- Create: `scripts/bootstrap-cluster.sh`
- Modify: `scripts/bootstrap-argocd.sh`
- Create: `scripts/validate-bootstrap-profiles.sh`
- Modify: `.github/workflows/cluster-ci.yml`

- [ ] **Step 1: Add the Git-owned OpenShift GatewayClass**

Create:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: openshift-default
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
spec:
  controllerName: openshift.io/gateway-controller/v1
```

List `gatewayclass.yaml` before `gateway.yaml` in the gateway kustomization.
Add internal sync wave `"0"` to `gateway.yaml` and `"1"` to
`httproute-argocd.yaml`.

- [ ] **Step 2: Write the profile wrapper interface**

`scripts/bootstrap-cluster.sh` must accept:

```text
./scripts/bootstrap-cluster.sh talos [--cilium=auto|install|skip] [--dry-run]
./scripts/bootstrap-cluster.sh openshift [--cilium=auto|skip] [--dry-run]
```

Rules:

- Default `--cilium=auto`.
- `talos --cilium=auto`: install Cilium when absent, otherwise verify it.
- `talos --cilium=install`: run the pinned Cilium install path.
- `talos --cilium=skip`: skip Cilium actions but still handle Gateway API CRDs.
- `openshift --cilium=auto|skip`: never install Cilium.
- `openshift --cilium=install`: fail before any mutation.
- `--dry-run`: print the selected actions, require no cluster access, and do
  not call `kubectl`, Helm, the Cilium CLI, or any mutating command.
- Cluster access remains an explicit prerequisite for a live run.
- After profile prerequisites, verify the three pre-seeded 1Password secrets
  read-only, then call `scripts/bootstrap-argocd.sh <cluster>`:

```bash
kubectl get secret -n 1passwordconnect 1password-credentials
kubectl get secret -n 1passwordconnect 1password-operator-token
kubectl get secret -n external-secrets 1passwordconnect
```

If any secret is absent, stop before Argo CD or root-Application mutation and
print the existing manual pre-seed instructions. On a freshly reset Talos
cluster, Cilium and Gateway API setup may already have completed before this
gate; after pre-seeding, rerunning the same command continues safely. The
wrapper must not read secrets from 1Password.

- [ ] **Step 3: Implement the Talos profile**

Use the full existing Talos bootstrap Cilium contract:

```bash
"$CILIUM_CMD" install \
  --version "$CILIUM_VERSION" \
  --set "cluster.name=$CILIUM_CLUSTER_NAME" \
  --set ipam.mode=kubernetes \
  --set kubeProxyReplacement=true \
  --set 'securityContext.capabilities.ciliumAgent={CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}' \
  --set 'securityContext.capabilities.cleanCiliumState={NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}' \
  --set cgroup.autoMount.enabled=false \
  --set cgroup.hostRoot=/sys/fs/cgroup \
  --set k8sServiceHost=localhost \
  --set k8sServicePort=7445 \
  --set hubble.enabled=false \
  --set hubble.relay.enabled=false \
  --set hubble.ui.enabled=false \
  --set gatewayAPI.enabled=true \
  --set gatewayAPI.enableAlpn=true \
  --set gatewayAPI.enableAppProtocol=true
```

Read `CILIUM_VERSION` from
`clusters/talos/infra/cilium/kustomization.yaml` and `CILIUM_CLUSTER_NAME` from
`clusters/talos/infra/cilium/values.yaml`.

Install the pinned Gateway API CRDs only for Talos:

```bash
kubectl apply -f \
  https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.1/standard-install.yaml
kubectl apply --server-side -f \
  https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.1/experimental-install.yaml
```

These commands exist in the script but are not run during branch validation.

- [ ] **Step 4: Implement the OpenShift profile**

Before calling the focused Argo bootstrap:

```bash
kubectl get crd gatewayclasses.gateway.networking.k8s.io
kubectl get crd gateways.gateway.networking.k8s.io
kubectl get crd httproutes.gateway.networking.k8s.io
```

Read all OLM subscriptions and fail if an installed Service Mesh Operator v2
subscription is detected:

```bash
subscriptions="$(
  kubectl get subscriptions.operators.coreos.com -A \
  -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.spec.name}{"\t"}{.status.installedCSV}{"\n"}{end}'
)"

if grep -Eiq 'servicemeshoperator.*(servicemeshoperator\.v2|v2\.)' <<<"$subscriptions"; then
  echo "OpenShift Service Mesh Operator v2 conflicts with the OpenShift Gateway API implementation." >&2
  exit 1
fi
```

Do not install upstream Gateway API CRDs and do not require
`openshift-default` to exist before Argo sync; Git owns that GatewayClass.

- [ ] **Step 5: Make `bootstrap-argocd.sh` focused**

Remove platform prerequisite logic from `scripts/bootstrap-argocd.sh`.
Preserve:

- `[talos|openshift]` cluster selection;
- cluster-specific namespace, Helm values, and root paths;
- Argo CD chart version `9.5.17`;
- Redis secret bootstrap;
- upstream Helm Argo CD install;
- CRD/server waits;
- local root Application apply;
- sync-wave summary.

Update its header to state that `bootstrap-cluster.sh` is the recommended
operator entrypoint and direct invocation assumes platform prerequisites are
already complete.

- [ ] **Step 6: Add non-mutating bootstrap profile tests**

`scripts/validate-bootstrap-profiles.sh` must assert:

```text
talos --dry-run:
  includes Cilium install/verify behavior
  includes both upstream Gateway API CRD URLs
  includes the pre-seeded secret gate before Argo CD
  ends with bootstrap-argocd.sh talos

openshift --dry-run:
  excludes Cilium installation
  excludes upstream Gateway API CRD apply
  includes Gateway API CRD verification
  includes OSSM v2 conflict verification
  includes the pre-seeded secret gate before Argo CD
  ends with bootstrap-argocd.sh openshift

openshift --cilium=install --dry-run:
  exits nonzero

unknown profile:
  exits nonzero
```

Add this command to the `argocd-structure` job in
`.github/workflows/cluster-ci.yml`:

```bash
bash ./scripts/validate-bootstrap-profiles.sh
```

- [ ] **Step 7: Verify the Gateway and bootstrap work locally**

Run:

```bash
./scripts/validate-bootstrap-profiles.sh
shellcheck -S warning scripts/*.sh
kustomize build clusters/openshift/infra/gateway >/tmp/openshift-gateway.yaml
kustomize build clusters/openshift/argocd >/tmp/openshift-argocd.yaml
kustomize build --enable-helm clusters/talos/bootstrap >/tmp/talos-bootstrap.yaml
kustomize build --enable-helm clusters/openshift/bootstrap >/tmp/openshift-bootstrap.yaml
```

Expected: all commands exit `0`. No live cluster command is executed.

- [ ] **Step 8: Commit Gateway and bootstrap behavior**

```bash
git add clusters/openshift/infra/gateway scripts/bootstrap-cluster.sh \
  scripts/bootstrap-argocd.sh scripts/validate-bootstrap-profiles.sh \
  .github/workflows/cluster-ci.yml
git commit -m "feat(bootstrap): add cluster profiles and openshift gateway class"
```

## Task 7: Update Current Documentation and Mink

**Files:**
- Modify: `README.md`
- Modify: `clusters/talos/bootstrap/README.md`
- Modify: `clusters/openshift/bootstrap/README.md`
- Modify: `docs/cluster-dr-nuke-restore-runbook.md`
- Modify: `docs/domains/argocd/entrypoints.md`
- Modify: `docs/domains/multicluster/handoff-notes.md`
- Modify: `docs/domains/multicluster/openshift-storage-and-app-migration.md`
- Modify: `docs/domains/multicluster/prd.md`
- Modify: `docs/superpowers/specs/2026-06-04-multicluster-kustomize-and-bootstrap-design.md`

- [ ] **Step 1: Update the operator bootstrap path**

Make `./scripts/bootstrap-cluster.sh talos` and
`./scripts/bootstrap-cluster.sh openshift` the recommended commands.
Document `scripts/bootstrap-argocd.sh <cluster>` as the focused/manual Argo
step.

Document:

- Talos profile owns Cilium and upstream Gateway API CRD setup.
- OpenShift profile never installs Cilium or upstream Gateway API CRDs.
- OpenShift GitOps owns `openshift-default`.
- The OpenShift profile checks for an OSSM v2 conflict.
- Both profiles stop before Argo CD until the operator-managed 1Password
  bootstrap secrets exist.
- A fresh Talos bootstrap can require two invocations of the same profile
  command: platform setup, manual secret pre-seed, then Argo CD bootstrap.

- [ ] **Step 2: Update app discovery and shared-base documentation**

Replace statements that all AppSets are metadata-driven with:

```text
App overlays are directory-discovered from clusters/<cluster>/apps/*/*.
Explicit infra/database/monitoring entrypoints retain .argocd/config.json
where metadata carries real ordering or exception information.
```

Document the three portable shared infrastructure bases and the
`manifest-generate-paths` rule:

```text
Use "." for the Application source path and absolute "/manifests/..." paths
for consumed shared bases.
```

- [ ] **Step 3: Keep completion claims behind the final acceptance gate**

Update the docs to describe the resulting architecture, but keep the design
status at `Approved design` until Task 8 completes. Record the branch name in
the handoff notes; add final commit IDs only after the final acceptance run.

- [ ] **Step 4: Verify and commit documentation**

Run:

```bash
git diff --check
rg -n 'targetRevision: HEAD' \
  README.md clusters/talos/bootstrap/README.md clusters/openshift/bootstrap/README.md \
  docs/domains/multicluster docs/domains/argocd docs/cluster-dr-nuke-restore-runbook.md || true
```

Expected: no whitespace errors and no `targetRevision: HEAD`.

Commit:

```bash
git add README.md clusters/talos/bootstrap/README.md clusters/openshift/bootstrap/README.md \
  docs/cluster-dr-nuke-restore-runbook.md docs/domains/argocd/entrypoints.md \
  docs/domains/multicluster/handoff-notes.md \
  docs/domains/multicluster/openshift-storage-and-app-migration.md \
  docs/domains/multicluster/prd.md \
  docs/superpowers/specs/2026-06-04-multicluster-kustomize-and-bootstrap-design.md
git commit -m "docs(multicluster): document one-shot cluster bootstrap"
```

## Task 8: Run Full Local Acceptance and Publish the Branch

**Files:**
- Modify after acceptance:
  - `docs/superpowers/specs/2026-06-04-multicluster-kustomize-and-bootstrap-design.md`
  - `docs/domains/multicluster/handoff-notes.md`

- [ ] **Step 1: Prove app render parity**

Run:

```bash
mkdir -p /tmp/multicluster-kustomize-baseline/apps-after

for cluster in talos openshift; do
  while IFS= read -r file; do
    dir="${file%/kustomization.yaml}"
    rel="${dir#clusters/$cluster/apps/}"
    out="/tmp/multicluster-kustomize-baseline/apps-after/${cluster}-${rel//\//_}.yaml"
    before="/tmp/multicluster-kustomize-baseline/apps-before/${cluster}-${rel//\//_}.yaml"
    kustomize build --enable-helm "$dir" >"$out"
    diff -u "$before" "$out"
  done < <(find "clusters/$cluster/apps" -mindepth 3 -maxdepth 3 \
    -type f -name kustomization.yaml -print | sort)
done
```

Expected: all 88 diffs are empty.

- [ ] **Step 2: Run every repository-local guardrail**

Run:

```bash
./scripts/validate-cluster-layout.sh
./scripts/validate-argocd-apps.sh
./scripts/validate-openshift-app-renders.sh
./scripts/validate-bootstrap-profiles.sh
./scripts/validate-backup-exempt-keys.sh
./scripts/validate-kyverno-policies.sh
./scripts/validate-otel-configs.sh
./scripts/validate-posthog-clickhouse-config.sh
shellcheck -S warning scripts/*.sh
```

Expected: every command exits `0`.

- [ ] **Step 3: Render all cluster kustomizations**

Run:

```bash
set -euo pipefail
count=0
while IFS= read -r file; do
  kustomize build --enable-helm "$(dirname "$file")" >/dev/null
  count=$((count + 1))
done < <(find clusters -type f -name kustomization.yaml -print | sort)
printf 'rendered=%s\n' "$count"
```

Expected: every build exits `0`; the final count is at least the current
baseline of `155`.

- [ ] **Step 4: Run final structural assertions**

Run:

```bash
test "$(find clusters/talos/apps -mindepth 3 -maxdepth 3 \
  -type f -name kustomization.yaml | wc -l)" -eq 44
test "$(find clusters/openshift/apps -mindepth 3 -maxdepth 3 \
  -type f -name kustomization.yaml | wc -l)" -eq 44
test "$(find clusters/talos/apps clusters/openshift/apps \
  -path '*/.argocd/config.json' -type f | wc -l)" -eq 0

! rg -n 'patch:[[:space:]]*".*\\n' clusters manifests --glob 'kustomization.yaml'
! rg -n '^[[:space:]]+patch:[[:space:]]+\|[-+]?$' \
  clusters manifests --glob 'kustomization.yaml'
! rg -n '^[[:space:]]*(patchesStrategicMerge|patchesJson6902|bases):' \
  clusters manifests --glob 'kustomization.yaml'
! rg -n 'manifest-generate-paths:[[:space:]]+clusters/' clusters --glob '*.yaml'
! rg -n 'targetRevision:[[:space:]]+HEAD' clusters --glob '*.yaml'

git diff --check
git status --short --branch
```

Expected: every assertion exits `0`; the working tree is clean.

- [ ] **Step 5: Record final acceptance in docs and Mink**

After Steps 1-4 pass, update the design status to implemented, add the final
commit IDs and acceptance evidence to the handoff notes, and save:

```bash
mink note --project talos-argocd-proxmox \
  --category projects \
  --tags "multicluster,kustomize,argocd,bootstrap,gateway-api" \
  --title "IMPLEMENTED: one-shot multicluster Kustomize and bootstrap migration" \
  --body "Record the final architecture, validation evidence, commit IDs, remaining live OpenShift schema checks, and the explicit rule that no live cluster mutation occurred during branch implementation."
```

Commit the final evidence:

```bash
git add docs/superpowers/specs/2026-06-04-multicluster-kustomize-and-bootstrap-design.md \
  docs/domains/multicluster/handoff-notes.md
git commit -m "docs(multicluster): record local acceptance"
```

- [ ] **Step 6: Push the completed feature branch**

Run:

```bash
git diff --check
git status --short --branch
git log -1 --oneline
git push origin feat/one-shot-multicluster-kustomize
```

Expected: no whitespace errors, the working tree is clean, the final evidence
commit is at `HEAD`, and the remote branch advances to that verified commit.

## Operator-Approved Live Verification After Branch Review

These are read-only until the operator explicitly chooses to run the bootstrap
script. They are not executed during implementation:

```bash
oc get clusterversion
oc get crd gatewayclasses.gateway.networking.k8s.io
oc get crd gateways.gateway.networking.k8s.io
oc get crd httproutes.gateway.networking.k8s.io
oc get subscriptions.operators.coreos.com -A \
  -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,PACKAGE:.spec.name,CSV:.status.installedCSV
oc explain gatewayclass.spec.controllerName
oc explain lvmcluster.spec
```

After the operator runs `./scripts/bootstrap-cluster.sh openshift` and Argo
syncs:

```bash
oc get gatewayclass openshift-default -o yaml
oc get gateway -n openshift-ingress openshift-gateway -o yaml
oc get httproute -A
oc get applications -n argocd
```

Verify the GatewayClass is accepted by
`openshift.io/gateway-controller/v1`, the Gateway becomes programmed, and all
generated Applications remain local to the OpenShift cluster.
