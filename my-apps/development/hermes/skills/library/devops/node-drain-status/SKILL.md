---
name: node-drain-status
description: "Use before or during a node drain. Posts blockers and ETA."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [homelab, longhorn, drain, reboot, omni, talos, storage]
    related_skills: [homelab-ops, homelab-triage]
---

# Node drain status

Answer "what blocks this drain, and how long" with one read-only command.

## When to use

- Mitch plans to reboot, upgrade or drain a node. Run it with `--node` first.
- A drain or Omni upgrade seems stuck. Run it every few minutes and post the result.

## Run it

```bash
source /opt/data/tools/talos-env.sh
python3 scripts/drain_status.py --node <node-name>
```

Leave out `--node` for a cluster-wide view. Post the output as is. It is already short Markdown.

## What it reads

| Line | Source |
|---|---|
| Cordoned nodes | `kubectl get nodes` |
| Longhorn eviction | `replicas.longhorn.io` with `spec.evictionRequested` |
| Copies in progress, minutes left | Prometheus `longhorn_engine_rebuild_progress` |
| PDBs at zero | Prometheus `kube_poddisruptionbudget_status_pod_disruptions_allowed` |
| Omni machines | `omnictl get clustermachinestatus` (stage, ready, config apply, last error) |
| Single-copy volumes, GiB to copy | Longhorn replicas and volumes |
| Disk selectors that match too few nodes | Longhorn StorageClasses against node and disk tags |

The Grafana board "Node drains & storage moves" (Cluster folder) shows the same data over time.

## Read the result

- Eight Longhorn instance-manager PDBs at zero is normal. Longhorn keeps them while an instance manager runs engines or replicas.
- "Longhorn must copy N volumes" means the drain waits for those copies. On 2026-11-10 about 155 GiB left the GPU worker in 40 minutes (26-51 MB/s per volume). Prefer the minutes-left line to a size-over-speed guess.
- After the uncordon, `best-effort` data locality copies the same volumes back. On 2026-11-10 that was another ~110 GiB in 20 minutes. Report it as part of the reboot cost.
- The minutes-left estimate is a straight line from the last 10 minutes. It is wrong at the start of a copy.
- Omni stage numbers come from `ClusterMachineStatusSpec.Stage` in Omni's `omni.proto`. 4 is RUNNING.

## Do not

- Change anything. This skill only reads. Evictions, disk tags, replica counts and Omni actions go to Mitch.
- Cancel a stuck drain. Follow `omni/docs/OPERATIONS.md`, section "A drain is stuck on a Longhorn volume".
