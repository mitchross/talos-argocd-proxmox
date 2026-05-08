# ArgoCD vs External Secrets Operator: the "syncResult Synced but ES spec stale" race

> **Decision update 2026-05-08:** the §3 recommended Lua health check was
> evaluated AND rejected. Reason: the block (22 lines of Lua + header comments)
> hit the "tons of Lua scripts" feel the cluster has explicitly cleaned up
> once. The ArgoCD↔ESO race is now exclusively addressed at the application
> layer via pvc-plumber v3.1.0 lazy-credential-load (task #34). The other 30+
> ExternalSecrets in this cluster remain exposed to the race during any
> future schema change; documented unstick pattern is `kubectl apply
> --server-side --force-conflicts` + `kubectl annotate externalsecret
> force-sync=...` + `argocd refresh=hard`, cataloged in
> `~/.mink/wiki/resources/argocd-blocks-manifest-application-during-failing-deployment-rollout.md`.
> Full decision rationale:
> `~/.mink/wiki/resources/decision-2026-05-08-rejected-cluster-wide-es-lua-health-check-queued-pvc-plumber.md`.
> The §1, §2, §6 root-cause analysis remains accurate and useful — only the
> §3 recommendation has been superseded.


**Date:** 2026-05-08
**Trigger:** pvc-plumber v3.0.0 cutover (`dceee632`). New pod looped on
`CreateContainerConfigError: couldn't find key AWS_ACCESS_KEY_ID in Secret
volsync-system/pvc-plumber-kopia` while ArgoCD reported the parent ExternalSecret
as `Synced` and `secret synced`. Live ES still showed only `KOPIA_PASSWORD` in
its `data:` block.

## 1. What actually happened

Sequence on the cluster, fields cited from real APIs:

1. Argo applied the new `ExternalSecret` (wave 0). gitops-engine called
   `ApplyResource(...)` which is just a server-side apply of the manifest
   ([gitops-engine `pkg/utils/kube/resource_ops.go`][1]). Apply succeeded — the
   object's `spec.data` array became three entries on the API server.
2. Argo then evaluated **health** for the ES. There is no built-in
   `observedGeneration` on `ExternalSecret`: the [v1 `ExternalSecretStatus`
   struct][2] has `RefreshTime`, `SyncedResourceVersion`, `Conditions`, `Binding`
   — *no* `observedGeneration`. The [upstream ArgoCD health.lua][3] therefore
   only inspects `status.conditions[].type == "Ready"`:

   ```lua
   if condition.type == "Ready" and condition.status == "True" then
     hs.status = "Healthy"
     hs.message = condition.message
     return hs
   end
   ```

   ESO had not reconciled the new generation yet (default `refreshInterval: 1h`
   on this ES; the previous reconcile happened the day before). So the live
   `Ready` condition still carried the stale `status: True` /
   `message: "Secret synced successfully"` from the prior generation's success.
   The Lua returned **Healthy** with that stale message.

3. gitops-engine fed that `healthStatus.Message` straight into the per-resource
   `ResourceSyncResult.Message`
   ([`sync_context.go::setResourceResult` path][4]). That is where
   `syncResult.resources[…].message: "secret synced"` originated — **not from
   the apply**, and **not from the current generation**. It is a verbatim copy
   of the old `Ready` condition message.

4. Wave-0 marked Healthy → wave-1 ran. The Deployment's `secretKeyRef` for
   `AWS_ACCESS_KEY_ID` resolved against the still-stale rendered `Secret`
   (because step 2 was a lie), kubelet failed to start the container with
   `CreateContainerConfigError`, and Argo's outer `operationState.message`
   correctly said `"waiting for healthy state of apps/Deployment/pvc-plumber"`.

5. Manual `kubectl annotate externalsecret pvc-plumber-kopia
   force-sync=$(date +%s)` triggered an ESO reconcile that observed the new
   generation, fetched the two new properties from 1Password, regenerated the
   `Secret`, and the pod went Ready.

## 2. Why the two ArgoCD status fields disagreed

The two fields look at different things on different timelines:

| Field | What it means | When it's written |
| --- | --- | --- |
| `status.operationState.syncResult.resources[].status` / `.message` | Result of the sync **operation** that just ran. `message` is currently sourced from the post-apply health check, which on ES uses a stale `Ready` condition. | Once at the end of the operation. Frozen until the next sync. |
| `status.resources[].status` / `.health` | Live drift state from the next reconcile loop. Server-side dry-run apply against `argocd-cm`'s `ignoreDifferences` + the same Lua health check, but evaluated against the *current* live object. | Refreshed every reconciliation tick. |

After ArgoCD applied the new spec, the controller's next reconcile saw the ES
spec on the API server as the new shape, ran a server-side dry-run, observed
the rendered `Secret`'s `data` block did not yet match what the new spec would
produce, and wrote `status.resources[].status: OutOfSync`. The
`syncResult.resources[].message: "secret synced"` was already frozen from the
operation that completed before ESO reconciled — it never got rewritten.

So both fields were technically truthful: the apply *did* succeed, but the ES
health check was evaluated before ESO had observed the new generation. The
"smoking gun" is the [upstream ArgoCD `health.lua`][3] returning `Healthy` on
generation N+1 because ESO's `Ready` condition does not track generation. The
[upstream issue #22707][5] documents this exact gap and proposes (without
shipping) a Lua hash that mirrors ESO's `SyncedResourceVersion = generation +
hash(labels+annotations)` ([`pkg/controllers/util GetResourceVersion`][6]).

## 3. Recommended fix — generation-aware ES health check, globally

Add a custom Lua health check for `ExternalSecret` to the ArgoCD ConfigMap that
treats the ES as `Progressing` until ESO has observed the current generation.
This is a manifest-only change to `infrastructure/controllers/argocd/values.yaml`
and inherits to every ES across the cluster — wave 0 stops lying to wave 1
forever, not just for pvc-plumber.

```yaml
# infrastructure/controllers/argocd/values.yaml — add under configs.cm:
resource.customizations.health.external-secrets.io_ExternalSecret: |
  hs = {}
  hs.status = "Progressing"
  hs.message = "Waiting for ExternalSecret"
  if obj.status == nil then return hs end

  -- Mirror ESO's SyncedResourceVersion = "<generation>-<hash(labels+annotations)>".
  -- We can't reproduce the hash in Lua, but the generation prefix is enough:
  -- if the ES has been mutated and ESO hasn't reconciled it yet, the prefix
  -- of status.syncedResourceVersion will not match metadata.generation.
  local gen = obj.metadata and obj.metadata.generation or 0
  local srv = obj.status.syncedResourceVersion or ""
  local prefix = tostring(gen) .. "-"
  if srv == "" or string.sub(srv, 1, #prefix) ~= prefix then
    hs.status = "Progressing"
    hs.message = "ESO has not observed generation " .. tostring(gen)
                 .. " (syncedResourceVersion=" .. srv .. ")"
    return hs
  end

  if obj.status.conditions ~= nil then
    for _, c in ipairs(obj.status.conditions) do
      if c.type == "Ready" and c.status == "False" then
        hs.status = "Degraded"; hs.message = c.message; return hs
      end
      if c.type == "Ready" and c.status == "True" then
        hs.status = "Healthy"; hs.message = c.message; return hs
      end
    end
  end
  return hs
```

Pair it with one wave-bump on the `pvc-plumber` ES (already at wave 0 — that's
fine, the new health check carries the gate) **and** drop the ES
`refreshInterval` from `1h` to `1m` on the `pvc-plumber-kopia` ES so the worst
case wait between an Argo apply and ESO observing the new generation is bounded
even when controllers are catching up after a crash:

```diff
 # infrastructure/controllers/pvc-plumber/externalsecret.yaml
-  refreshInterval: 1h
+  refreshInterval: 1m
```

The ES still won't refresh data from 1Password unless its watch fires — but the
generation check above does not depend on `refreshInterval`; it depends only on
ESO's reconcile loop, which fires on spec writes via the controller-runtime
informer, typically within a second of the apply.

## 4. Why this fix wins

- **Zero new moving parts.** No PreSync hook Job (which would need ArgoCD hook
  annotations, Renovate awareness, and goes through the operator's own webhook
  — option 2 in the brief). No SealedSecret/SOPS schema sentinel (option 3,
  off-table per "no secrets in Git"). No operator code change (option 4 ships
  through a separate repo and ships a different bug class — pod Ready with a
  broken backend).
- **Failure mode is loud and obvious.** The ES sits at `Progressing` with
  `"ESO has not observed generation N (syncedResourceVersion=…)"`. That is
  exactly the diagnostic an operator wants the next time this happens: the gap
  is visible in `argocd app get` output and in the UI, not buried in logs.
- **Cluster-wide.** Every ExternalSecret in this repo (1Password Connect ES,
  app-secret ES, CNPG creds, etc.) gets the same gate, so the next ES-shape
  change to literally any application benefits without per-app annotation.
- **GitOps-native.** It's one block of Lua in `values.yaml`. The
  self-managed `argocd` Application picks it up on the next reconcile, the
  `argocd-cm` updates, all child Apps re-evaluate health on their next tick.
- **Survives ESO upgrades.** `SyncedResourceVersion`'s prefix format
  (`"<gen>-<hash>"`) has been stable since v0.7.x and is what the [upstream
  ArgoCD issue #22707][5] asks ArgoCD itself to adopt — we are shipping the
  community-recommended workaround, not inventing one.

The other options I considered:

| Option | Verdict |
| --- | --- |
| 1. Existing wave + default health.lua | This is what just failed. Default Lua doesn't read `syncedResourceVersion`. |
| 2. PreSync Job that polls keys | Too many moving parts, Jobs are immutable + need hook annotations + go through the very webhook we're trying to gate behind. |
| 3. SealedSecret/SOPS schema sentinel | Violates "never commit secrets to Git" if any secret material leaks, and adds a second secret backend. |
| 4. Operator-side lazy creds | Right idea long-term but ships in a separate repo + creates "Ready with broken backend" failure mode. Worth doing in pvc-plumber v3.1, but not the line of defense for the cluster generally. |
| 5. `refreshInterval: 0` / `dataFrom` | `dataFrom` would have masked the immediate symptom (one entry add covers the whole vault item) but doesn't fix the generation race for the *next* schema change. Worth doing in addition (see §5). |
| 6. `SkipDryRunOnMissingResource` / `RespectIgnoreDifferences` | Unrelated; the apply succeeded. |
| 7. `optional: true` on `secretKeyRef` | Pod starts with empty creds, kopia fails on first call. Same "Ready but broken" failure mode as option 4 with no benefit. |
| 8. ESO `pushSecret` | Wrong direction (pushes K8s → store). |
| 9. `argocd.argoproj.io/hook` on the ES | Hooks don't gate on health, only on apply success. Same hole. |

## 5. What this fix does NOT cover

- **First-time ES creation.** On the very first apply of a new ES,
  `status.syncedResourceVersion` is empty. The Lua above keeps the ES
  `Progressing` until ESO writes status — usually a couple of seconds. That's
  fine for sync waves but if ESO is **completely down**, every ES blocks
  forever. That's an *improvement* over today's silent failure but operators
  need to know to check ESO health, not the ES itself.
- **`refreshInterval` is still the only gate on stale 1Password data.** If
  someone changes a value in 1Password without bumping the ES generation,
  this fix doesn't help — but that's a different problem (ESO design choice;
  unrelated to ArgoCD).
- **In-cluster generation tracking only.** If the 1Password Connect pod is up
  but returning stale data (cache, propagation), ESO will mark Ready with the
  stale value. This race is at the ES↔Connect↔1Password level; the fix gates
  on ArgoCD↔ESO only.
- **Cluster-wide rollout.** Every existing ES is re-evaluated on the next
  reconcile, which means any ES whose `syncedResourceVersion` happens to be
  empty (very old, never reconciled since upgrade) will flicker to
  `Progressing` until ESO writes status. Expected to settle within one ESO
  reconcile loop (default 5s).
- **Does not protect against the operator-side failure** of pod-readyz lying
  about a kopia connection that hasn't authenticated yet. That's pvc-plumber
  v3.x scope (option 4 still recommended for v3.1), not an ArgoCD fix.

## References

- [1] gitops-engine apply path returning kubectl-style stdout:
  <https://github.com/argoproj/gitops-engine/blob/master/pkg/utils/kube/resource_ops.go>
- [2] ExternalSecret v1 `Status` struct (no `ObservedGeneration`):
  <https://github.com/external-secrets/external-secrets/blob/main/apis/externalsecrets/v1/externalsecret_types.go>
- [3] Upstream ArgoCD ExternalSecret `health.lua`:
  <https://github.com/argoproj/argo-cd/blob/master/resource_customizations/external-secrets.io/ExternalSecret/health.lua>
- [4] gitops-engine `setResourceResult` populates per-resource message from
  `healthStatus.Message`:
  <https://github.com/argoproj/gitops-engine/blob/master/pkg/sync/sync_context.go>
- [5] argo-cd #22707 — *ExternalSecret health check for OnChange refreshPolicy*
  (open, proposes the same hash-based check):
  <https://github.com/argoproj/argo-cd/issues/22707>
- [6] ESO `GetResourceVersion`:
  `func GetResourceVersion(meta metav1.ObjectMeta) string {
   return fmt.Sprintf("%d-%s", meta.GetGeneration(), HashMeta(meta)) }` —
  <https://github.com/external-secrets/external-secrets/blob/main/pkg/controllers/util/util.go>
- [7] argo-cd #13825 — *externalsecret resource always sync* (open, related):
  <https://github.com/argoproj/argo-cd/issues/13825>
- [8] argo-cd #24554 — *Refresh an ExternalSecret if RefreshPolicy is OnChange*:
  <https://github.com/argoproj/argo-cd/issues/24554>
- [9] external-secrets #4180 — *Newly added Secrets take 5–15 min to reconcile*
  (root cause of long propagation):
  <https://github.com/external-secrets/external-secrets/issues/4180>

**Canonical answer status:** there is no upstream fix yet ([#22707][5] is open
since 2025-04-17 with no PR). The Lua health check above is the
community-converging workaround.
