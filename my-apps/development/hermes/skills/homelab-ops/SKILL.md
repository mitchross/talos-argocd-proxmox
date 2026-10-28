---
name: homelab-ops
description: Read-only health checks for the talos-prod-cluster-v2 homelab (Argo CD, pods, Longhorn, kopiur backups, events), the daily digest format, and Omni, Talos and Pi access.
version: 1.3.0
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
- If a fix is needed, describe it and name the Git path under `my-apps/` or `infrastructure/`. The user changes the cluster through pull requests only. A coding agent in this pod can open that pull request (see below).
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

## When a fix is needed: run a coding agent in this pod

You cannot change the cluster. Claude Code (`claude`) and Codex (`codex`) are installed here, with the talos repo checked out at `/opt/data/workspace/talos-argocd-proxmox` and a GitHub login (`gh`) that opens pull requests.

Only start a coding agent when the user asks for a fix, or when the digest prompt says so. Steps:

1. Pick the agent. Codex for a scoped change you can describe exactly. Claude Code for a root-cause investigation first.
2. Refresh the checkout: `git -C /opt/data/workspace/talos-argocd-proxmox fetch --prune origin` then `git -C /opt/data/workspace/talos-argocd-proxmox checkout -B hermes/<short-name> origin/main`.
3. Start the agent in the background with the terminal tool (`workdir=/opt/data/workspace/talos-argocd-proxmox`, `background=true`). The prompt must contain: the evidence you collected, the Git directory that owns the app, and these rules: read the repo `CLAUDE.md` first, stay on the current branch, commit, push the branch, open a pull request with `gh pr create`, never push to `main`, never merge.

```
claude -p "<prompt>" --model claude-opus-5-5 --effort high --dangerously-skip-permissions --max-turns 60 --output-format json
codex exec -m gpt-6.1-sol -c model_reasoning_effort=high --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<prompt>"
```
   Coding always runs on Opus 5.5 at high effort or GPT-6.1-sol at high effort. Never drop these flags. Claude's JSON output ends with a `modelUsage` object; the keys are the models that ran. Codex prints `model:` and `reasoning effort:` lines at the top of its output.
   `kubectl` is read-only, but agents here also inherit the Omni Operator key and `ssh pi`. Tell them not to use Omni, Talos or the Pi; never pass the bypass flags anywhere else.
4. Poll the background process with `process_manage` until it exits. Report the pull request link, a two-line summary, and one line `Agent: <claude|codex>, model: <name>, effort: <level>` copied from the agent's own output. If the model is not `claude-opus-5-5` or `gpt-6.1-sol`, say so. Do not merge; the user merges.
5. If the agent stops with a question, relay it to the user instead of answering on their behalf.

If `claude` or `codex` fails to start (no login, no token), say so and stop. The Paseo fallback is gone (Paseo was turned off in PR #3072); hand the prompt to the owner to run in Claude Code on CachyOS instead.

## Omni, Talos and the Pi

These tools can change production. Act by risk:

- Reads run without asking: status, logs, `get`, `docker ps`, `journalctl`.
- Impactful actions need a short explanation of the effect first: restarting a container or service, rebooting one node, applying one machine config.
- Destructive or wide actions need an explicit yes for that exact command (list below).
- Declarative changes still go through Git, a PR and Argo CD. Direct maintenance on the Pi, Omni or Talos is allowed when Git does not own that state.

- `omnictl` uses the Operator service account from `OMNI_ENDPOINT` and `OMNI_SERVICE_ACCOUNT_KEY`. Start with `omnictl get clustermachinestatus` and `omnictl get machines`.
- `talosctl` reaches nodes through Omni with `~/.talos/config`. Start with `talosctl -n <node-ip> dmesg | tail -50` or `talosctl -n <node-ip> services`.
- `ssh pi` opens a shell on the rpi5 (192.168.10.15) as `vanillax`, with Docker and passwordless sudo. It runs Omni, the Proxmox infra providers, booter and Technitium DNS. Start with `ssh pi docker ps`.
- Never run `omnictl delete`, `omnictl cluster template sync`, `talosctl reset`, `talosctl upgrade` or `docker compose down` on the Pi without an explicit yes for that command.
- Proxmox hosts are not reachable from this pod. Hand those steps to the user.

## When asked about one app

Use the same read-only commands scoped with `-n <namespace>`. Read the last 50 log lines with `kubectl logs -n <ns> <pod> --tail=50`. Name the Git directory that owns the app: `my-apps/<category>/<app>/`.
