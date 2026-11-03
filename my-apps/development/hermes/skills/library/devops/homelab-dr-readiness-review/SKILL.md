---
name: homelab-dr-readiness-review
description: Check the cluster and Hermes can be rebuilt from zero.
version: 0.1.0
author: Hermes
metadata:
  hermes:
    tags: [Disaster Recovery, Kopiur, Backups, Hermes, GitOps]
---

# Homelab DR Readiness Review

Audits whether talos-argocd-proxmox and the Hermes agent can be rebuilt after losing PVCs, the cluster, the local Kopia repository, or all of these. It works read-only: inspect, compare Git against live state, then propose changes as one PR. It never deletes PVCs, rotates credentials, wipes buckets, or merges.

## When to Use
- "Could I nuke the cluster and get Hermes back?"
- "What can't be rebuilt from Git and 1Password?"
- "Do I need an offsite backup?" / "What if the Kopia repo dies?"
- "Make sure apps never start empty when a backup is missing."

## Prerequisites
- Read-only `kubectl` with the kopiur CRDs (`hermes-viewer`), plus `gh` and the talos repo checkout.
- Load the `homelab-gitops-change-prs` skill before writing the PR, and the `hermes-model-routing` skill when model routes are in scope.

## How to Run
Invoke `kubectl`, `gh` and `git` through the `terminal` tool. Read repo files with `git show origin/main:<path>`. Run `scripts/skills_drift.py` for the skills gap. Hand slow upstream source reading to `delegate_task`, and treat its findings as leads until you have checked them yourself.

## Quick Reference
- List the kopiur CRDs: `kubectl api-resources --api-group=kopiur.home-operations.com`. These include `SnapshotReplication`, `RepositoryReplication` and `Maintenance`.
- Read the field docs offline: `kubectl explain restore.spec.policy`, `clusterrepository.spec.seed`, `clusterrepository.spec.create`, `snapshotreplication.spec`, `snapshotpolicy.spec.repositories`, `snapshotpolicy.spec.verification`.
- Check freshness: `kubectl get snapshot -n <ns> --sort-by=.metadata.creationTimestamp` and `kubectl get snapshotpolicy,snapshotschedule,restore -n <ns>`.
- Check repository health: `kubectl get clusterrepository cluster-kopia -o jsonpath='{.status}'`.
- Repo files: `infrastructure/backup/kopiur/clusterrepository.yaml` (RustFS S3 `192.168.10.133:30292`, bucket `kopiur`), `my-apps/common/kopiur-backup/kustomization.yaml` (injects `onMissingSnapshot: Continue`), `docs/disaster-recovery.md`, README § Rebuild and Bootstrap, `omni/omni/README.md` (Omni state backup).
- Hermes files: `my-apps/development/hermes/{scripts/seed.sh, externalsecret.yaml, kopiur/hermes-data.yaml, config/config.yaml}`.
- Hermes's own backup: `hermes backup [-o OUT] [--quick]`, and `hermes import <zip>`.

## Procedure
1. Read the Hermes app: kustomization, seed, ExternalSecret, PVC, kopiur stub, config. List everything the seed creates "once" or "if missing". Those things survive only through the PVC backup.
2. Run `scripts/skills_drift.py` to list volume skills missing from Git or diverged from the library. Then compare `/opt/data/cron/jobs.json` with the seed's cron jobs, and `/opt/data/plugins` with the seed's plugin loop.
3. List the credentials that live only on the volume:
   - Codex: `~/.codex/auth.json`.
   - Hermes `openai-codex`: `$HERMES_HOME/auth.json`, which has no env-var path.
   - `gh` device login.
   - The Pi SSH key in `/opt/data/.ssh`.
   Then list the ones that come from 1Password (the ExternalSecret keys).
4. Check backups live. Each backed-up PVC needs a recent `Succeeded` Snapshot. Note the retention and the schedule (Hermes runs every 6 h; `hindsight-db-pvc` runs daily with a `CHECKPOINT` hook).
5. Check the empty-volume paths with `kubectl explain`:
   - `fromPolicy` defaults to `onMissingSnapshot: Continue`, which binds an empty PVC when the repo is reachable but holds no snapshot.
   - `Fail` makes the Restore terminally `Failed`.
   - An unreachable repo holds the Restore `Pending`.
6. Check repository loss:
   - A `ClusterRepository` that was already Ready pins `status.uniqueId`, so a wiped bucket gives `RepositoryReinitializeBlocked`.
   - A freshly recreated CR on a fresh cluster has no pin. With `create.enabled` (the default) it creates a NEW empty repo, and every `Continue` restore then comes up empty.
   - `spec.seed` replaces that fallback: the repo is seeded from a replica, or bootstrap fails.
7. Design the offsite copy. Use a different provider, for example a B2 or S3 bucket outside the house, so that a second TrueNAS dataset doesn't count. Use `SnapshotReplication` (`kopia snapshot migrate`, which gives a separate repo with its own password), not `RepositoryReplication` (`sync-to` reuses the source password and blobs). Put its credentials and password in 1Password. Keep a `seed.from.repository` pointing at the offsite repo so recovery is a sync, not a hand-run script.
8. List the bootstrap dependencies outside the cluster: GitHub and GHCR, 1Password and the Connect token, the Cloudflare token, RustFS/TrueNAS, the Omni Pi (manual etcd/sqlite tar), Proxmox storages, and the private `docker-hub-auth.yaml` patch.
9. Write the recovery matrix. Cover pod restart, PVC loss, cluster loss, Kopia repo loss, and cluster plus local backups lost. For each, give the restore source, the manual steps, the data-loss window and a test.
10. Open ONE focused PR, using the `homelab-gitops-change-prs` workflow. Prove kustomize changes with `kubectl kustomize`. List the manual items that need the user (new offsite account, 1Password items, device logins).

## Pitfalls
- `seed.sh` runs under `set -eu`, and its plugin install has no fallback. If GitHub is down, a fresh volume never starts Hermes.
- A missing delegation plugin fails closed: with `backend: model_map` set, `delegate_task` refuses every subagent.
- `onMissingSnapshot: Fail` breaks the first deploy of a new app. Keep `Continue` only for PVCs that have never had a Snapshot, and flip them once the first one succeeds.
- A component patch with `op: add /spec/policy` overrides the per-stub value. To exempt a PVC, use a second patch with a label selector, not an edit to the stub.
- The kopiur tag is `0.10.16` with no `v`. Inferences from reading its source (e.g. the missing uniqueId pin on a recreated CR) are hypotheses until a drill proves them.
- Subagents can export `HERMES_HOME` into the shared terminal. Check `echo $HERMES_HOME` before trusting Hermes CLI output.
- `du` over `/opt/data` takes more than 180 s. Use `df -h /opt/data` instead.

## Verification
The review is done when every scenario in the matrix names a restore source and a test, and `scripts/skills_drift.py` (invoked through the `terminal` tool from the talos checkout) prints `NOT IN GIT: []`.
