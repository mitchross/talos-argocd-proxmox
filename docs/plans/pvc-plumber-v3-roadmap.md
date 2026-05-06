# pvc-plumber v3 Roadmap

**Status**: Roadmap / pre-decision — captured 2026-05-06
**Companion to**: [`pvc-plumber-operator-design.md`](./pvc-plumber-operator-design.md) (v2 design, shipped)
**Relates to**:
  - [mitchross/pvc-plumber#3](https://github.com/mitchross/pvc-plumber/pull/3) — v2 operator binary
  - [mitchross/talos-argocd-proxmox#1270](https://github.com/mitchross/talos-argocd-proxmox/pull/1270) — v2 cluster manifests

---

## Why this document exists

After v2 was implemented and PRs were opened, an external design proposal landed (referred to here as "the v3 spec") proposing a meaningfully different architecture. This roadmap evaluates the v3 spec against what v2 actually shipped, identifies cheap wins to fold into a v2.1 follow-up, and lists the gates that would need to be cleared before committing to a full v3 rewrite.

The full v3 spec is preserved in the project Mink note at
`~/.mink/wiki/projects/talos-argocd-proxmox/pvc-plumber-v3-roadmap-catalog-native-cel-admission-policies-codex-spec-2026-05-.md`.

---

## What v2 shipped (the baseline)

- Go operator using `controller-runtime` v0.23.3.
- **Three classic admission webhooks** (`MutatingWebhookConfiguration` + `ValidatingWebhookConfiguration`), TLS via `cert-manager` namespace-scoped `Issuer`.
- **Per-request `kopia.CheckBackupExists` calls** during PVC admission — backup truth is always live, no caching of admission decisions.
- Single shared kopia client + cache between the legacy HTTP `/exists` endpoint and the new webhook handlers.
- ExternalSecret + ReplicationSource + ReplicationDestination managed via `unstructured.Unstructured` (no CRDs of our own).
- `OPERATOR_MODE=true` feature flag for cutover; HTTP-only mode = parity with v1.
- Schedule formula: `len(ns + "-" + pvcName) % 60` (Kyverno-compatible). Already documented as TEMPORARY in the source-of-truth Kyverno YAML — clusters PVCs of similar name length onto the same minute.
- Coexists with Kyverno during cutover; Kyverno volsync policies + `orphan-reaper` CronJob removed in a follow-up PR after live verification.
- 27 unit tests passing (7 controller, 20 webhook, plus `parseSystemNamespaces` additive-behavior tests).
- 9-entry `namespaceSelector` deadlock-prevention list, mirrored as default in `cmd/operator/main.go` and as the `SYSTEM_NAMESPACES` env var in the Deployment.

---

## What v3 proposes (key architectural deltas)

1. **Native CEL admission policies** instead of webhook server:
   - `ValidatingAdmissionPolicy` (stable `v1` since k8s 1.30)
   - `MutatingAdmissionPolicy` (k8s 1.34 beta / 1.36 `v1` — must confirm at runtime)
   - `paramKind: PVCBackupCatalog`
   Eliminates webhook TLS lifecycle, eliminates the "operator pod down → admission deadlock" failure mode, eliminates per-request kopia network calls during admission.

2. **Four CRDs** in `storage.vanillax.dev/v1alpha1`:
   - `PVCBackupRepository` (cluster, backend config: kopia repo, NFS, maintenance schedule)
   - `PVCProtectionClass` (cluster, policy: selector, restore policy, retention, volsync overrides) — abstracts policy from the label contract; supports multi-class (e.g. silver/gold tiers without code changes)
   - `PVCBackupCatalog` (cluster, the admission `paramKind`; entries map of `namespace/pvc → {decision: Restore|Fresh, restoreRefName, snapshotTime}`, with `authoritative` + `expiresAtEpoch` fields)
   - `PVCProtection` (namespaced, per-PVC status object for human visibility)

3. **Catalog model**: operator scans Kopia every `spec.catalog.refreshInterval` (default 90s, `maxStaleness: 5m`), writes `PVCBackupCatalog/default`. Native admission policies READ this CR; the operator is never on the admission hot path. If `authoritative=false` or `expiresAtEpoch < now`, deny protected PVC creation (fail-closed at the API server, not via webhook routing).

4. **SHA256-based schedule**: `minute = sha256(ns + "/" + pvc) % 60`. Replaces length-mod which clusters by name length.

5. **`backup-exempt` label + reason annotation** contract:
   ```yaml
   metadata:
     labels:
       backup-exempt: "true"
     annotations:
       storage.vanillax.dev/backup-exempt-reason: "<one of: cache, scratch, external-source, media-on-nas, database-native, test>"
   ```
   Pairs with the existing `volsync.backup/skip-restore` escape hatch.

6. **Operator-owned Kopia maintenance** — operator either creates/owns a `CronJob` or runs `Job`s itself. Single-binary ownership of repo lifecycle.

7. **7-phase migration plan**: observe-only → VAP Warn/Audit → MAP canary namespace → operator reconciliation in canary → VAP Deny in canary → per-namespace expansion → remove Kyverno entirely.

---

## What's genuinely better in v3

1. **Native CEL admission removes the webhook server.** No TLS cert lifecycle, no "operator pod restart → admission blip", no risk of repeating the 2026-04-08 Kyverno deadlock pattern. A stuck operator only freezes the catalog; a frozen catalog → `expiresAtEpoch` passes → fail-closed via static VAP rule, never via a webhook the cluster has to reach.
2. **First-class observability via CRDs.** `kubectl get pvcprotection,pvcbackupcatalog,pvcprotectionclass` is much nicer than tailing operator logs and inspecting unstructured ES/RS/RD by hand-rolled label.
3. **`PVCProtectionClass` decouples policy from labels** — silver/gold tiers, per-class retention, per-class schedule type, all without code changes.
4. **SHA256 schedule eliminates name-length clustering.**
5. **Catalog-decoupled admission removes per-request kopia I/O latency** from the admission hot path (currently 50–200ms per PVC create in v2, depending on Kopia repo size and NFS responsiveness).

---

## What needs more thought before cutover

### Staleness window — a real safety regression vs. v2

v2's invariant: *"`exists=false` is safe only when `authoritative=true`, evaluated **right now** against the live Kopia repo."* The webhook makes a per-request kopia call.

v3's catalog model: *"`exists=false` is safe when the catalog says so, evaluated **at most `maxStaleness` seconds ago**."*

That's a strictly weaker invariant. Failure scenario:

1. Catalog refreshes at `T=0`; no backup yet for `karakeep/data-pvc`.
2. `T+30s`: an `hourly` ReplicationSource completes a backup for `karakeep/data-pvc`.
3. `T+60s`: an operator deletes and recreates the PVC (node drain, schema rebuild, etc.).
4. The new PVC's admission reads the cached catalog from `T=0`, sees `Fresh`, allows empty PVC.
5. The backup from `T+30s` is silently orphaned in Kopia and the new PVC starts empty over restorable data.

Default `maxStaleness: 5m` makes this a 5-minute window of vulnerability. Tighten to 30s and the window shrinks but the operator hits Kopia 120×/hour just to write a CR most consumers don't read. **v2's per-request approach has zero staleness** because it always reads live truth.

To make the catalog model safe enough to replace v2, the v3 spec would need to add one of:

- **Admission-time live check fallback**: if the catalog is older than e.g. 10s AND no entry exists for the requested PVC, the admission policy `paramRef`s a synchronous lookup. Today CEL-based admission policies can't make HTTP calls — so this would still need a webhook, partially defeating the no-webhook win.
- **Write-through catalog updates** from the ReplicationSource controller: when a backup completes, the operator updates the catalog immediately, not on the next refresh tick. Shrinks the window to "between backup-finish and operator's RS event handler firing" — typically <1s. This is the cleaner path.

Either approach must be specified before the catalog model is safe to ship.

### `MutatingAdmissionPolicy` API readiness

The v3 spec correctly flags this needs runtime confirmation. As of writing, `MutatingAdmissionPolicy` is **beta in k8s 1.34** under `admissionregistration.k8s.io/v1beta1`, with `v1` arrival in 1.36. The Talos cluster's current k8s version dictates whether the v3 MAP manifests are even loadable.

The v3 spec's documented fallback ("standard `MutatingWebhookConfiguration` served by the operator") **is exactly v2's architecture**. In practice the v3 architecture's no-webhook win is gated on a Talos + k8s upgrade, not just on operator code.

### Migration complexity

The 7-phase plan is rigorous but requires **Kyverno still running as the source of truth through phases 0–5**. v2 already cut over from Kyverno on a single boundary because v2 was built to be idempotent with Kyverno's existing generators. Reintroducing Kyverno coexistence for the v3 migration window is a step backwards in operational simplicity vs. the cutover we already have lined up.

---

## Plan

### Now: ship v2

PRs `mitchross/pvc-plumber#3` and `mitchross/talos-argocd-proxmox#1270` are production-shaped, fail-closed, and don't depend on beta admission APIs. Merge, build image `2.0.0-rc1`, validate with `OPERATOR_MODE=false` (parity), then flip to `OPERATOR_MODE=true` and verify lifecycle on a test PVC. Follow-up PR removes Kyverno volsync policies + orphan-reaper.

### Next: v2.1 follow-up PR (additive only)

Cherry-pick the cheap, non-architectural wins from the v3 spec into a v2.1 PR on `pvc-plumber`:

| # | Change | Scope | Notes |
|---|--------|-------|-------|
| a | SHA256 schedule formula (`sha256(ns + "/" + pvc) % 60`) | Single function in `internal/controller/pvc_controller.go` | Lead's regression-pin test catches drift; update the test to assert hash spread instead of length-mod |
| b | `PVCProtection` namespaced status CR | New CRD + status writer in PVC reconciler | Purely additive observability; admission semantics unchanged |
| c | `backup-exempt: "true"` + `storage.vanillax.dev/backup-exempt-reason` contract | Validating webhook + cluster manifests | Fits existing `skip-restore` validation pattern |
| d | Operator-owned Kopia maintenance | Either CronJob owner or in-process Job runner | Folds in the existing maintenance CronJob |

### Gate before committing to v3

Run v2 in production for **4–6 weeks**. Measure two things:

1. **Per-request kopia admission latency.** If p99 PVC admission stays under ~200ms, the catalog model's primary speed argument is moot.
2. **Talos k8s version trajectory.** If Talos lands 1.36 with `admissionregistration.k8s.io/v1` MAP GA, v3's no-webhook win becomes available. If we're still on 1.30/1.32 by then, v3's webhook fallback is a wash with v2.

If both gates favor v3 *and* the staleness-window concern above is addressed in the design, revisit. Otherwise, v2 + v2.1 is the right shape for this homelab.

---

## Open questions for the v3 spec author

1. **Staleness mitigation**: how would you address the "catalog stale when a backup just completed" race? Write-through from the RS controller? Live-fallback path?
2. **MAP API readiness**: have you confirmed `MutatingAdmissionPolicy` at `admissionregistration.k8s.io/v1` (not `v1beta1`) on a target Talos version? If only `v1beta1` is available, would you ship v3 against the beta API and pin the cluster version?
3. **CRD versioning**: the spec is at `v1alpha1`. What's the contract for migrating to `v1beta1`/`v1`? Conversion webhooks required, given the catalog is read by admission policies?
4. **`PVCProtectionClass` selectors**: the spec uses `matchLabels: {backup: hourly}`. What's the conflict-resolution rule when a PVC matches multiple classes (e.g. `backup: hourly` + `backup-tier: gold`)?
5. **Coexistence**: phase 0 says "current Kyverno path remains source of truth." Given that v2 already replaces Kyverno cleanly, is that still required, or could v3 cut over directly from v2 (operator-managed → operator-managed-with-CRDs)?

---

## References

- v2 design doc: [`pvc-plumber-operator-design.md`](./pvc-plumber-operator-design.md)
- v2 operator PR: [mitchross/pvc-plumber#3](https://github.com/mitchross/pvc-plumber/pull/3)
- v2 cluster manifests PR: [mitchross/talos-argocd-proxmox#1270](https://github.com/mitchross/talos-argocd-proxmox/pull/1270)
- 2026-04-08 Kyverno webhook deadlock incident: [`infrastructure/controllers/kyverno/CLAUDE.md`](../../infrastructure/controllers/kyverno/CLAUDE.md) § "Critical: Webhook Deadlock Prevention"
- VolSync Volume Populator: <https://volsync.readthedocs.io/en/v0.8.0/usage/volume-populator/>
- ValidatingAdmissionPolicy: <https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy>
