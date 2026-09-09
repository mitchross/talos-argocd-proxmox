# Temporal manager identity recovery

The recovery CronJob clears only this controller's stale namespace-UID identity
after a namespace rebuild. Current identities, foreign managers and empty
identities are left alone. The owning configuration is
[manager-identity-recovery.yaml](manager-identity-recovery.yaml); the executable
[script](scripts/recover-manager-identity.sh) is packaged by Kustomize.

## Resource and runtime guardrails

The September 2026 inspection found the 549.5 MiB Temporal CLI trapped under a
128 MiB container limit: more than 43 TB of executable reads without finishing
its first read-only list command. This was file-cache reclaim, with no OOM kill.
The proposed 768 MiB request and 1 GiB limit reserve room for the executable and
runtime; they are an initial operating budget to verify after deployment.

The identical pinned image completed a local isolated `--help` startup at a
267 MiB cgroup peak and a read-only live worker list in 0.03 seconds with warm
cache. These checks confirm that the old limit was inadequate; they do not
measure the repaired Pod's peak on the affected node.

Each API/CLI command receives a 30-second timeout and a further 5 seconds before
SIGKILL. A failed or timed-out command fails the Job before its output is parsed.
The Job's 240-second active deadline bounds the complete run, including retries.
The five-minute schedule and `Forbid` policy remain unchanged.

## Rollout and verification

Status: repair requires PR merge and Argo reconciliation. No live repair was
performed while preparing this change. Use an authenticated cluster context;
the following commands are read-only:

```sh
kubectl -n temporal-worker-controller get cronjob temporal-worker-controller-identity-recovery -o yaml
kubectl -n temporal-worker-controller get jobs,pods -o wide
```

First verify the reconciled CronJob has `requests.memory: 768Mi`,
`limits.memory: 1Gi`, `activeDeadlineSeconds: 240`, and the new hash-suffixed
script ConfigMap reference. A CronJob update
[does not change an existing Job](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/#modifying-a-cronjob).
The old run will continue to block subsequent schedules under `Forbid`.

After the new template is confirmed, retire only the inspected stuck Job using
the approved operational cleanup. Before cleanup, reverify its namespace,
owner, Pod resources and immutable UID against the incident evidence:
`temporal-worker-controller-identity-recovery-29814005`, UID
`bb04f361-8e7c-4ef4-8541-fd29193da863`. Stop if any identity differs; do not use a
broad label deletion. Retain its diagnostic evidence before removing it.

The next scheduled Job should use the new budget and finish successfully. Check
its logs and exit code, and observe several five-minute cycles. Confirm that
the affected node's disk read rate, queue and file-cache refault rate fall;
then repeat the storage latency comparison. A timeout is a visible failed Job,
not a successful recovery. Diagnose repeated timeouts before raising deadlines.

If the recovery decisions regress, pause scheduled recovery through a follow-up
GitOps PR and inspect the script. Preserve the memory and deadline guardrails;
blindly reverting to the original 128 MiB limit recreates the incident.

## Local validation

```sh
python3 -m unittest discover -s infrastructure/controllers/temporal-worker-controller/tests -v
shellcheck infrastructure/controllers/temporal-worker-controller/scripts/recover-manager-identity.sh
kustomize build --enable-helm infrastructure/controllers/temporal-worker-controller
```

Tests use fake API/CLI executables, including failures with partial stdout and
commands that ignore SIGTERM. They never contact Kubernetes or Temporal.
