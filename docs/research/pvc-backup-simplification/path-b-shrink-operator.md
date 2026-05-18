# Path B — Shrink the operator to a per-app safety interlock

Author: research (study mode — design study, NOT an implementation plan yet)
Date: 2026-05-18
Decision inputs: Path B (keep fail-closed, move templating to declarative
Argo); risk posture = **mixed / per-app** (some PVCs are source-of-truth,
others are disposable/NAS-backed like the author's).

Companion reading: `../mirceanton-home-ops/01-backup-restore-end-to-end.md`
(his operator-free design), `docs/volsync-storage-recovery.md` (today's
operator design).

---

## 1. The thesis

pvc-plumber today does two unrelated jobs fused into one operator:

- **Bucket 1 — per-app boilerplate** (ExternalSecret + ReplicationSource +
  ReplicationDestination + PVC wiring, plus timing + cleanup). This is
  pure templating. The author proves it needs **no operator** — a
  Kustomize Component + Flux `postBuild.substitute` does it declaratively.
- **Bucket 2 — the fail-closed restore-vs-fresh gate.** A runtime check
  against external Kopia/S3 state at PVC admission. Irreducible: cannot be
  a static manifest. The author **does not have this at all** — he accepts
  silent-empty-on-uncertainty.

Path B = **make Bucket 1 declarative (Argo-native), keep only Bucket 2 in
the operator, and apply Bucket 2 only to the PVCs that actually need it.**

The mixed risk posture is what makes this elegant: the disposable-tier
PVCs end up running *exactly the author's operator-free model*, and the
operator survives only as a thin interlock on the critical tier.

---

## 2. Why Bucket 1 can go fully declarative under Argo

### 2.1 The Flux→Argo templating gap (the real structural difference)

His "2-line change" rests on **Flux `postBuild.substitute`** injecting
`${APP}`, `${VOLSYNC_CAPACITY}`, … into a shared Kustomize Component.
**Argo CD has no postBuild equivalent**, and plain Kustomize has no
variable substitution (`vars` removed; `replacements` are clumsy for
per-app fan-out). This gap is *part of why an operator looked necessary
for templating* — but it is solvable Argo-natively.

### 2.2 Argo-native replacement for postBuild substitution

Recommended: a **local Helm chart inflated through Kustomize** (`helmCharts`
in `kustomization.yaml`), so the existing "directory = app, discovered by
ApplicationSet, rendered by Kustomize" pattern is preserved while gaining
Helm's per-app value injection.

Per-app cost becomes ~5 lines in the app's `kustomization.yaml`:

```yaml
helmCharts:
  - name: volsync-backup
    repo: <local path or OCI>
    valuesInline:
      app: jellyfin
      capacity: 10Gi
      puid: 568
      pgid: 568
      tier: strict        # or: best-effort   (see §4)
```

That chart templates exactly the four resources the author's Component
does (ES / RS / RD / PVC), with the same `${default}`-style fallbacks.

**Validation needed (do not assume):**
- Argo Kustomize build must have Helm enabled
  (`kustomize.buildOptions: --enable-helm` in `argocd-cm`, or
  `ApplicationSet`/`Application` `kustomize` with helm). Confirm current
  argocd-cm before relying on this.
- Alternative if `--enable-helm` is undesirable: a Kustomize Component +
  `replacements` sourced from a per-app `ConfigMap`/values file. More
  verbose; keep as fallback, not first choice.

### 2.3 What Argo's own pruning gives us for free (replaces operator cleanup)

pvc-plumber's reconciler also *cleans up* RS/RD/ES when a PVC is deleted
or unlabeled. Declaratively this is **free**: RS/RD/ES are Git/Helm-owned,
so Argo prune removes them when the app (or the backup block) is removed.
Keep the data PVC protected from prune the way the author does
(`kustomize.toolkit.fluxcd.io/prune: disabled` → Argo equivalent:
`argocd.argoproj.io/sync-options: Prune=false` on the data PVC, or
`Delete=false`). The operator's cleanup logic becomes unnecessary.

### 2.4 The "RS only after Bound + 2h" timer — likely droppable (verify)

pvc-plumber delays ReplicationSource creation until the PVC is Bound and
≥2h old, to avoid backing up an empty volume before a restore finished.
In the declarative + VolumePopulator model this hazard is structurally
weaker: the VolSync **VolumePopulator restores before the PVC binds**, so
a Bound PVC is already populated, and the app does not start (and the RS
has nothing meaningful to capture) until then. The author runs **no such
timer**. Treat the 2h timer as *probably unnecessary in Path B*, but
**validate** with a deliberate test (deploy → confirm first scheduled RS
run does not capture a pre-restore empty state) before deleting it.

---

## 3. What irreducibly stays in the operator (and how small it gets)

Once RS/RD/PVC are declarative with a **static `dataSourceRef → <app>-dst`**
(exactly like the author), the operator's surface collapses:

| Operator function today | Path B fate |
|---|---|
| Reconciler generates ES/RS/RD | **Removed** — declarative Helm chart |
| Reconciler timing (Bound+2h) | **Removed** (pending §2.4 validation) |
| Reconciler cleanup on delete/unlabel | **Removed** — Argo prune |
| **Mutating webhook injects `dataSourceRef`** | **Removed** — chart sets it statically (author proves this works) |
| Post-mutate belt-and-suspenders race check | **Removed** — no mutation ⇒ no mutate/validate race exists |
| **Validating webhook: fail-closed deny on `unknown`** | **KEPT — this is the entire residual operator** |

So Path B's operator is a **validating-webhook-only** component: for a
selected PVC, ask Kopia "does a backup exist right now?":

- `restore` / authoritative `fresh` → **ALLOW** (the static
  `dataSourceRef` + VolumePopulator then does restore-or-empty exactly
  like the author).
- `unknown` / backend unreachable → **DENY** (HTTP 503); Argo retries with
  backoff.

No mutation, no reconciler, no cache-of-generated-resources lifecycle, no
CRD ownership. pvc-plumber already computes this tri-state decision, so
this is plausibly a **"validate-only" run mode** of the existing binary
(disable reconciler + mutating webhook) rather than new code — **confirm
the binary supports a validate-only mode**; if not, this is a small
upstream change, still far less surface than today.

Note: the static `dataSourceRef` does the restore-vs-fresh routing that
the mutating webhook used to do. The webhook is no longer *choosing* — it
is only *vetoing uncertainty*. That is the conceptual shrink: from
"decision-maker + generator" to "safety interlock."

---

## 4. The per-app tier model (the payoff of the mixed posture)

Introduce a tier on the PVC, e.g. label `restore-policy`:

| Tier | Meaning | Webhook applies? | Behaviour | Equivalent to |
|---|---|---|---|---|
| `strict` | Cluster-local PVC is a source of truth; empty-over-good-data is unacceptable | **Yes** (objectSelector matches) | Fail-closed: deny PVC create if Kopia uncertain; otherwise static `dataSourceRef` restores | Today's pvc-plumber guarantee |
| `best-effort` | Disposable / NAS-backed / reproducible; binding empty is acceptable | **No** (excluded from webhook objectSelector) | Pure declarative: static `dataSourceRef`, VolumePopulator restores if a backup exists, else binds empty silently | **Exactly the author's model** |

Mechanics:
- Webhook `objectSelector`: match `backup in (hourly,daily)` **AND**
  `restore-policy=strict`. Everything else (best-effort, unlabeled) is
  never intercepted.
- Both tiers use the **same declarative Helm chart** — the only difference
  is the `tier` value (sets the `restore-policy` label) and therefore
  whether the webhook selects it. No code branching.
- Default should be **`strict`** (safe by default; opt *into* the author's
  risk per app), matching "mixed but data-loss-averse".

This directly answers the original question — *"get as close to the
author's setup as possible with Argo"*: **best-effort tier IS his setup,
operator entirely out of the path.** strict tier re-adds only the
irreducible interlock, only where it earns its keep.

---

## 5. The author's ergonomics, ported (tier-independent, no operator)

His Taskfile + `.scripts/volsync-*.sh` are pure UX and operator-agnostic.
Port them with Argo substitutions:

| His step | Argo/Kopia equivalent |
|---|---|
| `flux suspend helmrelease` | `argocd app set <app> --sync-policy none` **or** `argocd.argoproj.io/refresh` off / `skip-reconcile` annotation (databases AppSet already uses `selfHeal: false`) |
| `flux resume` + `flux reconcile --force` | re-enable auto-sync / `argocd app sync <app>` |
| `restic snapshots` throwaway pod | `kopia` throwaway pod with the per-app volsync secret env |
| patch RS/RD `spec.trigger.manual` | identical (CRDs unchanged) |
| `restoreAsOf` point-in-time | Kopia mover equivalent — verify exact field name on the perfectra1n fork |

These are worth doing in **every** path; they remove the only ergonomic
area where his setup is currently ahead of ours.

---

## 6. What we keep that he doesn't (the point of Path B)

- **Fail-closed guarantee on the strict tier.** His design silently binds
  empty over restorable data on uncertainty/first-run; Path B refuses, for
  the PVCs that matter.
- **Deterministic schedule stagger** (existing `(len(ns)+len(pvc))%60`) —
  no MutatingAdmissionPolicy, no beta apiserver feature gate, no busybox
  jitter container. Keep as-is.
- **System-namespace deadlock guard.** A validate-only webhook still has
  `failurePolicy: Fail`, so the `namespaceSelector.NotIn` exclusion list
  (kube-system, argocd, longhorn-system, volsync-system, …) **must stay**.
  Tiering *reduces* blast radius (only strict-tier app PVCs are gated) but
  does not remove this requirement. (CLAUDE.md rule still binding.)

---

## 7. Net simplicity scorecard (qualitative)

| Dimension | Author | Today (full operator) | Path B |
|---|---|---|---|
| Per-app effort | ~2 lines (Flux subst) | 1 label | ~5 lines Helm values (1 line if defaulting) |
| Operator code in path | none | reconciler + 2 webhooks + cache + CRD lifecycle | 1 validating webhook (strict tier only) |
| Templating | declarative (Flux) | imperative (operator) | **declarative (Helm/Kustomize)** |
| Cleanup | Flux prune | operator reconciler | **Argo prune** |
| Restore-vs-fresh | static dataSourceRef | mutating webhook | **static dataSourceRef** |
| Empty-over-good-data safety | none | full | **full on strict, none on best-effort (by choice)** |
| Beta APIs / apiserver patches | yes (jitter) | no | no |

Path B keeps the one guarantee the author lacks while deleting ~90% of the
operator and making the rest declarative and Argo-native.

---

## 8. Open items to validate before any implementation

1. Argo Kustomize `--enable-helm` status in `argocd-cm` (or accept the
   `replacements` fallback).
2. Does the pvc-plumber binary support a **validate-only mode** (reconciler
   + mutating webhook disabled)? If not, scope the upstream change.
3. Confirm VolSync **VolumePopulator on the perfectra1n/Kopia fork** binds
   empty (not error) when no snapshot exists — the author demonstrates
   this on Restic; verify on our Kopia fork.
4. Validate the §2.4 claim that the "Bound + 2h" timer is unnecessary
   under declarative + VolumePopulator (deliberate empty-capture test).
5. Confirm `restoreAsOf`/point-in-time field name on the Kopia mover for
   the ported restore script.
6. Decide the tier label name/contract (`restore-policy: strict|best-effort`
   vs reusing `backup-exempt`/a new annotation) and the default (recommend
   `strict`).

None of the above is actioned here — this document is the study, not the
change.
