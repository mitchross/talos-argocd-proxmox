# Talos 1.14 Longhorn SELinux mount context

**Status:** staged remediation, pending a live canary remount. Local tests and
rendering validate the manifests and migration logic; they do not prove runtime
mount behavior. All deployment and remount changes go through reviewed GitOps
PRs. This procedure does not require replacing PVCs or rebuilding the cluster.

## Why the audit log floods

The September 2026 survey found Talos 1.14 running SELinux in permissive mode on
all six nodes. Busy processes accessing Longhorn filesystems produced audit
records with `tcontext=system_u:object_r:unlabeled_t:s0`, `permissive=1`, and
successful syscalls. The GPU worker's PostHog ClickHouse and radar-ng workers
were prominent sources. The kernel dropped audit records when their rate
exceeded 4096 messages per second. This is an audit-record limit, not a
Kubernetes request limit or evidence that the recorded I/O failed.

Talos's [v1.14 container policy](https://github.com/siderolabs/talos/blob/v1.14.0/internal/pkg/selinux/policy/selinux/services/cri.cil)
allows container access to `ephemeral_t` and explicitly describes using CSI
StorageClass mount options for this context. The intended mount option is:

```text
context=system_u:object_r:ephemeral_t:s0
```

`ephemeral_t` is a policy type name: it does not change volume durability. The
option supplies the mounted filesystem's effective SELinux context without a
recursive on-disk relabel. It does not provide separate labels for each pod.

## What Git owns

| Source | Responsibility |
| --- | --- |
| `infrastructure/storage/longhorn/storageclass-*.yaml` | Set the context for newly provisioned volumes in all four Longhorn classes. |
| `infrastructure/storage/longhorn/values.yaml` | Disable the chart's generated StorageClass ConfigMap; ArgoCD directly owns the default `longhorn` class with its existing name and parameters. |
| `infrastructure/storage/longhorn-selinux/policy.json` | Explicit namespace/claim allowlist and reconciliation mode. Initially only `posthog/clickhouse-data-clickhouse-0`. |
| `infrastructure/storage/longhorn-selinux/scripts/reconcile.py` | Patch existing bound PV mount options while preserving other options and checking UID/resource version. |
| Owning application's workload manifest | Stop and start consumers through separate replica-count PRs to obtain a fresh mount. |

The independent `infrastructure-longhorn-selinux` Application is discovered by
the infrastructure ApplicationSet at wave 4. Its Sync hook runs after its own
RBAC and generated ConfigMaps exist. It can list and patch PVs; it cannot modify
PVCs, pods, or workload replica counts. The script enforces the claim allowlist;
RBAC permits PV patches cluster-wide because PV names change after restores.

The script accepts only reviewed Longhorn classes, ext4 filesystems, and
`ReadWriteOnce` or `ReadWriteOncePod` access. It preflights all selected volumes
before writing and fails on conflicting SELinux options. Missing, unbound, and
deleting claims are skipped, allowing a fresh cluster to provision normally.
Check the hook's per-claim result: a successful hook can have skipped a target.
Retries re-read PVs after a resource-version conflict. A multi-PV run is not a
transaction: if a later API patch fails, earlier successful patches remain.

**PVC immutability does not block this change.** The PVC's storage class,
identity, binding, and capacity remain unchanged. Kubernetes permits updating
`PV.spec.mountOptions`. StorageClass changes alone do not update existing PVs.

## Roll out through PRs

Prerequisites: Talos 1.14's policy, Longhorn filesystem volumes, access to ArgoCD
and Longhorn status/logs, and a maintenance window for the selected application.
For durable applications, check their existing kopiur backup health before the
maintenance window. PostHog ClickHouse is intentionally backup-exempt in this
repository; this procedure preserves its existing volume.

1. **Merge the storage and migration PR after review.** Confirm the Longhorn
   Application is synced, all four StorageClasses contain the option, and the
   default class retains its original parameters. Confirm the
   `infrastructure-longhorn-selinux` hook completes with an `updated` or
   `unchanged` event for `posthog/clickhouse-data-clickhouse-0`. Inspect the
   bound PV's manifest to verify the option. Do not proceed if it was skipped
   or either Application failed to sync.
2. **Open a canary stop PR.** In
   `my-apps/development/posthog/data-layer/clickhouse.yaml`, change only the
   `clickhouse` Deployment's `spec.replicas` from `1` to `0`. After the user
   merges it and ArgoCD applies it, wait for every pod consuming the claim to
   terminate and for the volume to fully unmount/unstage. Confirm Longhorn
   reports it detached. PostHog ingestion/querying is unavailable during this
   interval; dependent initialization hooks may wait or fail temporarily.
3. **Open a separate canary start PR after detachment.** Restore `replicas: 1`
   in the same manifest. Wait for ArgoCD to apply it, a fresh mount to succeed,
   ClickHouse to become ready, and PostHog's initialization/migration hooks and
   application operations to recover. Two commits merged before ArgoCD sees
   the stopped state are insufficient.
4. **Validate under real traffic.** Inspect the new mount's options and recent
   audit records through read-only diagnostics. ClickHouse access to this
   volume should no longer generate `unlabeled_t` AVCs. Confirm reads and
   writes work. Kernel `audit_lost` is cumulative and will not reset; compare
   increments over time. Other untreated volumes can still flood the node.
5. **Expand in follow-up PRs only after the canary passes.** Add a small set
   of explicit namespace/claim names to `policy.json`, let the hook update
   their PVs, and repeat the stop/wait/start sequence in their owning apps.
   For shared claims such as radar-ng tiles, identify every consumer and any
   autoscaler or worker controller that can recreate pods. All consumers must
   release the volume before starting any of them again.

A rolling restart or a pod annotation does not guarantee CSI staging unmounts.
The migration hook intentionally does not restart workloads or fight ArgoCD's
replica reconciliation. Until the remount phases finish, existing mounted
volumes can continue emitting the same audit messages.

## Failure and rollback

- **Hook rejects a target:** inspect its structured `failed` event. Correct the
  allowlist or investigate its filesystem/options in a PR. Do not remove the
  validation checks just to make the hook succeed.
- **Volume does not detach:** leave the canary stopped and identify remaining
  consumers or attachments. Do not force-delete pods, claims, or volumes.
- **Fresh mount fails or application checks fail:** keep the affected workload
  stopped through Git, set the migration policy's `mode` to `remove` for those
  claims in a PR, and wait for the hook to remove this exact context option.
  It preserves unrelated mount options. Then restore the workload's replica
  count in another PR so it mounts with the prior options.
- **Roll back the new-volume default too:** remove the option from the four
  StorageClass manifests in a PR. Keep the default class directly owned by
  ArgoCD. This does not undo mount options on already provisioned PVs; include
  any affected new claims in the rollback allowlist and remount them as above.

Simply deleting or reverting the migration Job does **not** undo its previous
PV patches. `mode: plan` logs intended additions without writes; `apply` adds
the context and `remove` removes it. Commit mode and allowlist changes through
PRs. Stop rollout if the canary does not reduce its corresponding audit events;
rebuilding the cluster with the same mount configuration would not address the
cause.

## Local validation and upstream references

Run these commands from the repository root; they do not change the cluster:

```bash
python3 -m unittest discover -s scripts/tests -p test_longhorn_mount_options.py
kustomize build infrastructure/storage/longhorn --enable-helm > /tmp/longhorn.yaml
kustomize build infrastructure/storage/longhorn-selinux > /tmp/longhorn-selinux.yaml
bash scripts/validate-argocd-apps.sh
bash scripts/validate-no-inline-scripts.sh
uv run --with-requirements requirements.txt mkdocs build --strict
```

- [Longhorn 1.12.1 StorageClass mount options](https://longhorn.io/docs/1.12.1/references/storage-class-parameters/)
- [Talos v1.14 audit daemon limits](https://github.com/siderolabs/talos/blob/v1.14.0/internal/app/auditd/auditd.go)
- [Kubernetes v1.37 PV update validation](https://github.com/kubernetes/kubernetes/blob/v1.37.0/pkg/apis/core/validation/validation.go)
- [Longhorn default StorageClass ConfigMap controller](https://github.com/longhorn/longhorn-manager/blob/v1.12.1/controller/kubernetes_configmap_controller.go)
- [Storage architecture](../../storage-architecture.md)
- [kopiur backup architecture](kopiur-backup-architecture.md)
