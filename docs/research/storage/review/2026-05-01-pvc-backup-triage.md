---
title: 17 unlabeled Longhorn PVCs — proposed triage
date: 2026-05-01
status: PROPOSAL — operator decisions still required
relates_to:
  - infrastructure/controllers/kyverno/policies/longhorn-pvc-backup-audit.yaml
  - docs/research/storage/review/2026-04-29-dr-drill-results.md
---

# PVC backup triage

The new `longhorn-pvc-backup-audit` ClusterPolicy surfaces 17 Longhorn PVCs
that declare neither `backup` nor `backup-exempt`. Each row below is a
proposal for what label to apply, with reasoning. **Don't run these blindly**
— skim the rationale, override per your judgment, then apply.

## Proposed labels

### Apply `backup-exempt: "true"` (cache / regenerable / transient)

| PVC | Why |
|-----|-----|
| `immich/immich-ml-cache` | ML model cache; Immich rebuilds on demand |
| `immich/library` | Photos library — large (~300Gi reserved). **Has its own dedicated migration plan** (NFS-CSI to TrueNAS, see open-todos mink note). Mark exempt for now; the migration path will move it off Longhorn entirely |
| `gitea-actions/act-runner-docker-cache` | Docker layer cache; rebuilds on next CI run |
| `gitea/valkey-data-gitea-valkey-primary-0` | Valkey (Redis fork) cache for Gitea sessions/queues; ephemeral by design |
| `project-nomad/embeddings-model-cache` | ML embedding model cache |
| `project-nomad/protomaps-data` | Map tile data; regenerable from upstream |
| `project-zomboid/zomboid-server-files` | SteamCMD-installed game files; regenerable via SteamCMD pre-warm (see mink) |
| `searxng/redis-data` | Search engine cache; ephemeral |
| `radar-ng/grids` | RWX, regenerable from MRMS upstream |
| `radar-ng/openmeteo-data` | RWX, regenerable from openmeteo API |
| `radar-ng/tiles` | RWX, generated from grids |
| `radar-ng/state` | RWX, transient state |
| `paperless-ngx/paperless-consume-pvc` | Inbox dir — files move to media after ingestion |
| `paperless-ngx/paperless-export-pvc` | Export dir — content rebuildable from media |

### Apply `backup: "daily"` (real app state worth backing up)

| PVC | Why |
|-----|-----|
| `frigate/mosquitto-storage-pvc` | MQTT broker retained messages + ACLs; small but losing it = HA integration breaks |
| `jellyfin/config` | Media library DB, watch progress, user accounts; lose this = re-scan everything |
| `open-webui/storage` | Chat history + saved conversations; user-facing data loss if gone |

## Apply commands (review before running)

```bash
# backup-exempt batch (14 PVCs)
kubectl label pvc -n immich immich-ml-cache 'backup-exempt=true'
kubectl label pvc -n immich library 'backup-exempt=true'
kubectl label pvc -n gitea-actions act-runner-docker-cache 'backup-exempt=true'
kubectl label pvc -n gitea valkey-data-gitea-valkey-primary-0 'backup-exempt=true'
kubectl label pvc -n project-nomad embeddings-model-cache 'backup-exempt=true'
kubectl label pvc -n project-nomad protomaps-data 'backup-exempt=true'
kubectl label pvc -n project-zomboid zomboid-server-files 'backup-exempt=true'
kubectl label pvc -n searxng redis-data 'backup-exempt=true'
kubectl label pvc -n radar-ng grids 'backup-exempt=true'
kubectl label pvc -n radar-ng openmeteo-data 'backup-exempt=true'
kubectl label pvc -n radar-ng tiles 'backup-exempt=true'
kubectl label pvc -n radar-ng state 'backup-exempt=true'
kubectl label pvc -n paperless-ngx paperless-consume-pvc 'backup-exempt=true'
kubectl label pvc -n paperless-ngx paperless-export-pvc 'backup-exempt=true'

# backup=daily batch (3 PVCs)
kubectl label pvc -n frigate mosquitto-storage-pvc 'backup=daily'
kubectl label pvc -n jellyfin config 'backup=daily'
kubectl label pvc -n open-webui storage 'backup=daily'
```

## After applying

Wait ~30s for the next Kyverno background scan, then verify the audit count:

```bash
kubectl get policyreport -A -o jsonpath='{range .items[*]}{range .results[?(@.policy=="longhorn-pvc-backup-audit")]}{.result}{"\n"}{end}{end}' \
  | sort | uniq -c
```

Should show `0 fail` once all 17 are labeled.

## GitOps note

These labels are applied **directly to the live cluster**, not via the
manifests in git. ArgoCD's `ignoreDifferences` for PVC `.metadata.labels`
isn't configured globally, so each app's manifest should ideally be updated
with the labels too — otherwise the next ArgoCD selfHeal cycle will revert
them. Quick check before you label:

```bash
# For each PVC, find its source app manifest
kubectl get pvc <name> -n <ns> -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/tracking-id}'
# then patch the manifest in git: add the label to spec.template... etc.
```

For PVCs whose manifests live in this repo (most of `my-apps/*`), edit the
PVC spec in the manifest file too. For PVCs created by Helm (CNPG, etc.),
labels in the chart values.

**Or**, accept that selfHeal might revert them and live with the audit
re-flagging until the manifests are updated. The audit is informational,
not blocking — no operational impact either way.
