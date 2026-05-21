# Compare & contrast — pvc-plumber vs author-spec (operator-free VolSync)

Status: analysis (decision-locked). Date: 2026-05-21. Branch: exploratory.
Inputs folded in: author's YouTube reply; codebase map (2026-05-19);
stateless question resolved; **author's Discord follow-up** (MAP init
container on mover Jobs; he uses VolSync for SQLite and "never ran into"
the corruption-on-restore burn); author's actual repo manifests pulled
(`mirceanton/home-ops` components, MAP, Taskfile, DR scripts, Talos patch).

**Direction is locked**: full migration to author-spec + MAP-based
backend-availability init container (Option C below). pvc-plumber gone.
See `proposal/` for the concrete artifacts; `migration-plan.md` for phasing.

Companion: `path-b-shrink-operator.md` (rejected alternative),
`migration-plan.md`, `test-plan.md`, `proposal/README.md`.

---

## 0. The question that was load-bearing — now resolved

Earlier open item: *does pvc-plumber carry a persistent "this PVC should
have a backup" expectation, or is its restore-vs-fresh decision stateless?*

**Resolved from the codebase map: it is decision-stateless.** pvc-plumber
*is* a stateful operator in the sense that it owns and reconciles per-PVC
ES/RS/RD, keyed off the `backup` label selector. But those are **generated
artifacts**, not an expectation ledger. The restore-vs-fresh choice is still
a point-in-time Kopia query at admission ("does a snapshot exist for
ns/pvc?"). It has **no memory** that a PVC previously held data. So it
*cannot* distinguish "first-ever deploy" from "repo silently mispointed and
Kopia authoritatively answered none."

This collapses the perceived safety gap (see §3).

---

## 1. The one axis that actually separates the two designs

Everything else is downstream of: **what happens when the backup backend is
not authoritatively answerable at PVC-create time.**

- **Author-spec:** static `dataSourceRef` → VolSync populator. No component
  whose job is the NO-vs-UNKNOWN distinction. Safety = human runbook.
- **pvc-plumber:** validating webhook does an explicit Kopia probe;
  `UNKNOWN`/timeout → DENY (`failurePolicy: Fail`). Safety = automated,
  day-0 == day-N.

## 2. Split "UNKNOWN" in two (the author's reply forces this)

The author's reply ("the replication source will simply fail to reach the
S3 repo and keep failing → PVC stays Pending → app should not start"; his
own hedges: *not tested directly, afaik, Restic, "misconfigured ≈ down"*):

- **Hard-unreachable** (NFS unmounted, S3 unroutable, conn refused, DNS
  fail): mover errors and *keeps* erroring → PVC `Pending` → no empty init,
  no bad backup, self-heals when backend returns. **Author-spec is
  fail-closed here — accidentally but effectively.** This is the entire
  transient-DR-window class.
- **Soft authoritative "no snapshot"** (wrong repo path/prefix, creds
  rotated to empty scope, first boot post repo-migration, retention already
  pruned, selector mismatch): mover *reaches* the backend, gets a clean
  "nothing," exits success → **binds empty → fresh `sonarr.db` → next RS
  captures it.** Author-spec fails *open* here.

## 3. The surprise: pvc-plumber doesn't cover the soft class either

Because §0 proved it decision-stateless: on a silently-mispointed repo Kopia
also answers "no" authoritatively, and pvc-plumber treats authoritative-no
as `NO → genuine fresh → ALLOW empty`. Its *only* unique data-safety branch
is `UNKNOWN`/timeout — i.e. **the hard-unreachable class — which the author's
mover already covers by staying Pending** (pending T2 on the Kopia fork).

Net: if T2 confirms the Kopia mover behaves like the author's Restic,
**pvc-plumber's unique *data-loss-prevention* value over author-spec is
≈ zero.** What remains is *operational*, not data-safety:

| pvc-plumber still better at | Why it matters |
|---|---|
| Admission-time **deny** vs silent `Pending` PVC | Failure is *visible* + ArgoCD backs off immediately, instead of an app silently down for hours |
| Blast radius is *explicit & scoped* (objectSelector) | You know exactly what's gated |

That is a real but **weaker** mandate than "prevents silent data loss." It's
"fails *loudly* instead of *silently*."

## 4. What each design gets wrong

- **Author-spec is wrong** to treat unreachable == genuine-fresh for the
  *soft* class. For an embedded-SQLite app PVC (Sonarr) that's silent,
  automated loss with nothing to even make it visible. Survives only via an
  undocumented procedural "restore manually before app starts."
- **pvc-plumber is wrong** to fuse the discriminator with the templating
  engine, the cleanup controller, and a cluster-wide SPOF. The 2026-05-17
  SwarmUI incident (RustFS cred mismatch → 6-day CrashLoop → cluster-wide
  PVC-create denial) is the proof: the *guarantee* was correct; the
  *coupling of guarantee-to-operator* is the defect.

## 5. Severity nuance (append-only repo)

Kopia is append-only + retention. A fresh-init backup is a *new snapshot*,
not an overwrite — the good snapshot is `restoreAsOf`-recoverable **until
prune/retention removes it**. So real-world severity is "bad snapshot added
+ prune window before a human notices," not instant annihilation. This is
what legitimises a **best-effort tier** (loss recoverable-until-prune ⇒
accepting author-spec is reasonable, not reckless).

## 6. Option C — MAP-based init container on the mover Job (CHOSEN)

Surfaced by the author on Discord after he saw the Path B sketch. He
already runs a `MutatingAdmissionPolicy` in his repo
(`apps/storage-system/volsync/app/mutating-admission-policy.yaml`) that
injects a jitter init container into VolSync mover Jobs. Same shape, swap
the init container: probe RustFS reachability; exit non-zero on failure;
Kubernetes Job backoff retries with exponential delay until the backend
comes back. Concrete manifest in `proposal/cluster/`.

Coverage vs the failure classes in §2:

- **Hard-unreachable**: covered. The init container fails fast → Job
  fails → backoff. For *restore* (RD) movers this means the populator
  never completes → PVC `Pending`. For *backup* (RS) movers this means no
  empty fresh-init gets captured. Same fail-closed-on-unreachable
  semantics as pvc-plumber's webhook used to give, but at the Job level.
- **Soft authoritative-no-snapshot**: still not covered, same as
  everywhere — accepted future-burn (§5, the append-only severity nuance
  makes this recoverable until prune).

Why it beats Path B *and* the alerting-watcher idea:

| Property | pvc-plumber | Path B residual webhook | Alerting watcher | **Option C (MAP)** |
|---|---|---|---|---|
| Operator pod | yes (SPOF binary) | yes (smaller) | small CronJob | **none** |
| Blast radius if "down" | **cluster-wide PVC deny** | tier-scoped PVC deny | nothing (zero side effects) | **scoped to one Job** |
| Hard-unreachable fail-closed | yes (admission deny) | yes (admission deny) | no (post-hoc only) | yes (Job fail+backoff) |
| Failure visibility | loudest (admission deny) | loud (admission deny) | dashboard | clear (Job backoff + init log) |
| Beta-API dependency | none | none | none | **MAP feature gate (4-line Talos patch)** |

The one cost is the MAP/`v1beta1` Talos patch — the only beta-API
dependency the migration takes on, and it's the same one the author
already uses. Worth it to delete the operator entirely.

## 7. Scorecard (decision-locked)

| Dimension | Author-spec alone | pvc-plumber (old) | **This migration: author-spec + Option C + chart** |
|---|---|---|---|
| Empty-over-good, hard-unreachable | Fail-closed (accidental, T2) | Fail-closed (deny) | **Fail-closed (MAP Job-fail), independent of T2** |
| Empty-over-good, soft-no-snapshot | Fail-open | **Also fail-open** (§3) | Fail-open — accepted future-burn |
| Failure visibility | Silent `Pending` | Loud deny | Job backoff + init log + status |
| Per-app effort | ~2 lines | 1 label | ~10 lines helmCharts values + PVC ref |
| Operator in path | none | reconciler + 2 webhooks + cache | **none** |
| Blast radius if backup infra down | none | cluster-wide | scoped to per-Job failure |
| Templating | declarative (Flux postBuild) | imperative (operator) | declarative (Helm-via-Kustomize, `--enable-helm` already on) |
| Cleanup | Flux prune | reconciler | ArgoCD prune |
| Restore-vs-fresh | static dataSourceRef | mutating webhook | **static dataSourceRef** |
| Beta APIs / apiserver patches | yes (jitter MAP) | no | **yes (MAP feature gate, 4-line Talos patch)** |
| SQLite-on-VolSync corruption (your original burn) | author "never ran into" | what motivated pvc-plumber | T3 sub-test reproduces under new pattern or refutes |

## 8. Conclusion

The full-migration direction is **defensible on data safety, strictly
better on blast radius, and ergonomically closer to author**. The one
trade you take on is the MAP beta-API dependency; the one risk you
explicitly accept is the soft-no-snapshot class (mitigated by Kopia
append-only + `restoreAsOf`). T2 was the gate when MAP wasn't on the
table; with Option C it becomes an *alignment check* rather than a gate
— the MAP fail-closes the mover regardless of populator behaviour.

Open decisions from earlier are all resolved:

- **D1** (Taskfile manual DR ergonomics): port them. Done in `proposal/ops/`.
- **D2** (visibility buy-back): Option C MAP. Done in `proposal/cluster/`.
- **D3** (chart owns PVC vs app keeps it): app keeps it during migration
  (smaller per-app diff, easier rollback). Flip to chart-owned for new
  apps post-migration if it feels right.
