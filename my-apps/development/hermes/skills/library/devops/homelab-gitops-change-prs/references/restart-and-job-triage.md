# Triage restarts, crash loops and failed Jobs (live, read-only)

Use this before any "X restarted N times" or "jobs are failing" finding becomes a PR.

## 1. Turn cumulative counts into a rate
`restartCount` and `kube_pod_container_status_restarts_total` count since pod start, so 300+ can be weeks old.
- Windows: `sum by (pod) (increase(kube_pod_container_status_restarts_total{namespace="<ns>",container="<c>"}[24h]))`, then `[7d]` and `[30d]`.
- Timeline: run `query_range` on `sum(increase(...{pod="<pod>"}[1h]))` with `step=3600` over 4 days, wrapped in `sum()` because pod UIDs split the series. List only the hours with restarts.
- Read the pattern:
  - every node's pod bursting at the same hour means a shared dependency went down (a NAS reboot, a node reboot). That's an echo, not a defect.
  - one pod restarting steadily during the same clock hours every day is the real problem.

## 2. Read why it died
- `kubectl get pod <p> -o jsonpath='{range .status.containerStatuses[*]}{.name} {.restartCount} {.lastState.terminated.reason} {.lastState.terminated.exitCode} {.lastState.terminated.finishedAt}{"\n"}{end}'`
- Exit codes:
  - 143: SIGTERM, usually a liveness kill. A probe tied to a remote dependency restarts the pod for nothing while that dependency is down.
  - 137: SIGKILL. Check for OOM versus a probe kill in `kubectl describe` events.
  - 255 or 1: the app exited itself. Read `kubectl logs <p> -c <c> --previous | grep -E 'level=(fatal|error)'`.
- Compare the `finishedAt` times with known outage times (TrueNAS or Proxmox reboots, the Omni sync).

## 3. Correlate a node-local loop with the network
When one node's agent loops (e.g. cilium-agent `Timed out waiting for pre-existing resources ... never received event for resource "cilium/v2::CiliumEndpoint"`), put its restart hours next to these:
- `rate(node_netstat_Tcp_RetransSegs{instance=~"<node-ip>.*"}[1h])`. A jump of roughly 100x in the same hours means a lossy link.
- `rate(node_network_transmit_bytes_total{instance=~"<node-ip>.*",device="eth0"}[1h])`, to rule out the node saturating the link itself.
- The node labels (`node.vanillax.dev/link=wifi`, `topology.kubernetes.io/zone`).

The fix in Git can only treat the symptom (a longer sync timeout). Name the physical link as the cause, and give the hours, so the user can check it.

## 4. Failed Jobs
- `kubectl -n <ns> get jobs --sort-by=.metadata.creationTimestamp -o custom-columns=N:.metadata.name,S:.status.succeeded,F:.status.failed,START:.status.startTime,REASON:.status.conditions[-1].reason`. If the newest run succeeded, the alert is stale history: use `ttlSecondsAfterFinished`, see the SKILL pitfall.
- Loki keeps pod logs for only about 24 h (`{k8s_namespace_name="<ns>", k8s_pod_name=~"<job>.*"}`, header `X-Scope-OrgID: 1`). Read a failing Job's logs the same day, or say plainly that the reason is no longer recoverable.

## 5. Throttling
- Fraction of CPU periods throttled: `rate(container_cpu_cfs_throttled_periods_total[30m]) / rate(container_cpu_cfs_periods_total[30m])`.
- Compare usage with the limit: `quantile_over_time(0.95, ...[1d:2m])` and `max_over_time(...)` of `rate(container_cpu_usage_seconds_total[2m])`. A max at the limit together with steady throttling justifies raising the limit while keeping the request.
- Temporal Worker Controller pools roll out a new worker version on any pod-template change. Name that in Merge danger.
