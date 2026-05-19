# Compare & contrast — pvc-plumber vs author-spec (operator-free VolSync)

Status: analysis (study). Date: 2026-05-19. Branch: exploratory.
Inputs folded in: the author's (mirceanton) YouTube reply; the codebase map
(2026-05-19); the resolved stateless question.

Companion: `path-b-shrink-operator.md` (the middle option),
`migration-plan.md`, `test-plan.md`.

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

## 6. Scorecard

| Dimension | Author-spec | pvc-plumber | Migration target (this branch) |
|---|---|---|---|
| Empty-over-good, hard-unreachable | Fail-closed (accidental, T2) | Fail-closed (deny) | Author-spec + T2 gate |
| Empty-over-good, soft-no-snapshot | Fail-open | **Also fail-open** (§3) | Same as both — accept / tier |
| Failure visibility | Silent `Pending` | Loud deny | Silent unless residual webhook (Path B) |
| Per-app effort | ~2 lines | 1 label | ~6 lines helmCharts values |
| Operator in path | none | reconciler + 2 webhooks + cache | none (chart) |
| Blast radius if backup infra down | none | cluster-wide | none (or tier-scoped, Path B) |
| Templating | declarative (Flux) | imperative (operator) | declarative (Helm/Kustomize) |
| Cleanup | Flux prune | reconciler | ArgoCD prune |
| Restore-vs-fresh | static dataSourceRef | mutating webhook | static dataSourceRef |
| Beta APIs / apiserver patches | yes (jitter) | no | no (deterministic schedule kept) |

## 7. Conclusion feeding the migration

A near-full migration to author-spec is **defensible on data-safety
grounds** *iff* T2 passes on the Kopia fork, because pvc-plumber's only
unique data-safety branch (hard-unreachable) is then redundant. The genuine
loss is **failure visibility**, not data. Two ways to buy visibility back
without the operator are listed in `migration-plan.md` (a tiny residual
validate-only webhook = Path B, or an alerting-only watcher). The 50/50
Taskfile-ergonomics question is independent and also in the plan.
