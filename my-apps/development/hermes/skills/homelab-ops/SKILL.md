---
name: homelab-ops
description: Read-only health checks for the talos-prod-cluster-v2 homelab (Argo CD, pods, Longhorn, kopiur backups, events) and the daily digest format.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [Kubernetes, Argo-CD, Longhorn, Kopiur, Homelab, Monitoring]
    category: devops
---

# Homelab ops: read-only cluster checks

You run inside the cluster with a read-only ServiceAccount. `kubectl` is on PATH and already authenticated.

## Rules

- Read only. Never run `delete`, `scale`, `patch`, `apply`, `edit`, `rollout restart`, `exec`, or `cordon`.
- If a fix is needed, describe it and name the Git path under `my-apps/` or `infrastructure/`. The user changes the cluster through pull requests only.
- Report observations, then hypotheses. A failed backup is an observation; its cause is a hypothesis until a log proves it.
- Keep the digest short. Only report what is not healthy. Say "all clear" for a section with nothing to report.

## Checks

Run each check with the terminal tool. Each one is fast and safe.

1. Nodes

```
kubectl get nodes --no-headers
```
Report any node that is not `Ready`.

2. Argo CD applications not Synced and Healthy

```
kubectl get applications.argoproj.io -A -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status' --no-headers | grep -vE 'Synced +Healthy'
```

3. Pods not Running or Succeeded, and pods with many restarts

```
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers
kubectl get pods -A -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount' --no-headers | awk '$3 ~ /^[0-9]+$/ && $3 > 5'
```

4. Longhorn volumes that are attached but not healthy

```
kubectl get volumes.longhorn.io -n longhorn-system -o custom-columns='NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness' --no-headers | awk '$2 == "attached" && $3 != "healthy"'
```
Detached volumes with robustness `unknown` are normal. Do not report them.

5. kopiur backups that failed

```
kubectl get snapshots.kopiur.home-operations.com -A -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,PHASE:.status.phase' --no-headers | grep -vE 'Succeeded|Running'
```
Report the namespace and the snapshot name. Names end with the start time.

6. Warning events in the last hour

```
kubectl get events -A --field-selector type=Warning --sort-by=.lastTimestamp --no-headers | tail -20
```
Group repeated warnings by object. Skip warnings already covered by checks 2 to 5.

## Digest format

```
Homelab digest <date>
Nodes: all clear | <names not Ready>
Argo CD: all clear | <app> <sync> <health>
Pods: all clear | <ns>/<pod> <state or restarts>
Longhorn: all clear | <volume> <state> <robustness>
Backups: all clear | <ns>/<snapshot> Failed
Warnings: all clear | <object>: <reason> (xN)
Suggested next step: <one line, or "none">
```

## When a fix is needed: hand it to Paseo

You cannot change the cluster. Paseo can: it runs Claude Code and Codex with the talos repo checked out at `/workspace/talos-argocd-proxmox` and a GitHub login that opens pull requests. The Paseo MCP tools are available in this session (`create_agent`, `send_agent_prompt`, `get_agent_status`, `get_agent_activity`, `list_agents`, `list_profiles`).

Only start a coding agent when the user asks for a fix, or when the digest prompt says so. Steps:

1. `list_profiles` and pick `implementation` (Codex) for a scoped change or `planning` (Claude) for a root-cause investigation.
2. `create_agent` with that profile in the Paseo workspace for `/workspace/talos-argocd-proxmox`. The prompt must contain: the evidence you collected, the Git directory that owns the app, and these rules: read the repo `CLAUDE.md` first, work on a feature branch, open a pull request, never push to `main`, never merge.
3. Poll `get_agent_status` until the agent finishes. Report the pull request link and a two-line summary. Do not merge; the user merges.
4. If the agent asks a question, relay it to the user instead of answering on their behalf.

## When asked about one app

Use the same read-only commands scoped with `-n <namespace>`. Read the last 50 log lines with `kubectl logs -n <ns> <pod> --tail=50`. Name the Git directory that owns the app: `my-apps/<category>/<app>/`.
