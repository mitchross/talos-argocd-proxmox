# Architecture audit — 5 September 2026

**Status:** evidence-backed audit with implementation underway. The owner merged
Fizzy/Mailpit removal [#2238](https://github.com/mitchross/talos-argocd-proxmox/pull/2238),
Cilium metrics/exporter fixes [#2241](https://github.com/mitchross/talos-argocd-proxmox/pull/2241),
and parked-Zomboid PDB/docs [#2242](https://github.com/mitchross/talos-argocd-proxmox/pull/2242). This document answers what the
repository actually builds, which failure modes it covers, and what to fix next.

**Scope:** GitOps, Cilium, workloads, storage, security, observability, documentation,
the last ten merged PRs, and supporting physical-host evidence. Hardware is a
secondary workstream. Kiwix/Nomad consolidation and Radar NG refactoring are deferred
at the owner's request. Bulk comment cleanup is also deferred. Final work includes
reconciling the documentation and validating the GitHub Pages build and published
site after the audit decisions are settled.

**Evidence:** repository commit `cbda78a03e2dfeca226bfeb8db141b2f432007f5`; isolated
renders; read-only Kubernetes/Prometheus queries; SSH inventory of five Proxmox
hosts, TrueNAS, and the Omni/DNS Pi; relevant Mink incident records; owner-confirmed
constraints. Runtime observations were taken on September 5 and are snapshots,
not uptime guarantees. The [inventory](2026-09-05-inventory.md) contains the physical
map, evidence limits, documentation inventory, and downloadable resource lists.

## Implementation tracking

| PR | Scope | State at this checkpoint |
| --- | --- | --- |
| [#2238](https://github.com/mitchross/talos-argocd-proxmox/pull/2238) | Retire Fizzy and Mailpit | Merged; removal reconciled |
| [#2241](https://github.com/mitchross/talos-argocd-proxmox/pull/2241) | Cilium metrics and exporter resources | Merged; 14 Cilium targets up |
| [#2242](https://github.com/mitchross/talos-argocd-proxmox/pull/2242) | Retain parked Zomboid, correct PDB | Merged; zero replicas and both claims retained |
| [#2243](https://github.com/mitchross/talos-argocd-proxmox/pull/2243) | Remove Headlamp Secret read permission | Merged; explicit authorization reviews deny Secrets and allow pods/logs |
| [#2244](https://github.com/mitchross/talos-argocd-proxmox/pull/2244) | Remove automatic Keep-to-Holmes calls | Merged; previous Holmes workflow is marked deleted in Keep |
| [#2245](https://github.com/mitchross/talos-argocd-proxmox/pull/2245) | Snapshot replicas, controller resources, VPA coverage | Merged; snapshot controller has two healthy pods on separate hosts |

The dependency pass merged 15 of the 16 requested updates. PostHog
[#2249](https://github.com/mitchross/talos-argocd-proxmox/pull/2249) is held because
the proposed feature-flags image queries a database column that is absent in the
running database. Its application and schema need a coordinated upgrade.
[#2237](https://github.com/mitchross/talos-argocd-proxmox/pull/2237) now includes the
GPU replacement disk finding and the single-control-plane recovery correction.
Talos remains 1.13.9 and Kubernetes remains 1.36.4 until the separate live rollout.

After these merges, Grafana is healthy on `13.2.1-distroless`, all 97 Prometheus
targets are up (including 14 Cilium targets), and VPA has 120 recommendations
across 124 policies. Immich Postgres now has a recommendation. These are live
checks at this checkpoint, not availability guarantees.

PostHog's pinned monolith image was built June 15 and its pinned node image
March 31; the proposed Rust images were built September 4. The new feature-flags
query references `feature_flags_teamfeatureflagsconfig.property_matching_version`.
The live schema lacks that column, and its feature-flags migration history ends
at `0010`. A coordinated upgrade must bring the monolith, node services and
schema into agreement; a green manifest render does not validate that contract.
See the [application upgrade checklist](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/posthog/UPGRADE.md)
before resuming that PR. No production migration was run.

Original findings below refer to the dated evidence snapshot unless marked
resolved. Further work includes bootstrap failure handling, narrowed Argo diff
ignores, credential migration, tested namespace isolation, and the storage
recovery design. MQTT broker and Frigate credentials currently differ; client
inventory must precede a broker credential cutover.

## Assessment

Keep the existing GitOps/Kustomize/Kopiur design. Directory discovery is coherent,
the backup component removes useful repetition, and recent PRs fix real contract
and monitoring defects. A platform replacement would add recovery work without
addressing the strongest findings.

The main mismatch is between **repeatable reconstruction** and **automatic service
recovery after an ordinary node failure**. The former has substantial operational
history. The latter is limited by single-copy volumes, one control-plane host,
placement constraints, and missing runtime checks. Rebuild success is valuable;
it does not make those different failure modes equivalent.

At collection time, 98 of 99 live Argo Applications were Synced/Healthy; Project
Nomad was Synced/Progressing. All six Kubernetes nodes were Ready. All 83 discovered
Prometheus targets were up. No Longhorn volume in the collected PVC inventory was
faulted. These observations rule out a blanket claim that the platform is broken.
They do not validate missing scrape targets or simulate a host loss.

## Critical / Technical Debt

### C1 — One-copy storage prevents the requested automatic node-loss recovery

**Priority: P1; confirmed design gap.** Of 75 Longhorn-backed live claims, 74 had
one desired replica; Temporal's Postgres volume was the only two-replica claim.
Detached/staging claims are included in that count. Temporal's running copies
were on the Dell and HP Elite. The Dell is an exposed motherboard on acrylic with an adapted MacBook SSD
and an improvised cooler. The owner considers it temporary capacity, not
long-term availability hardware; no specific crash history is asserted.

Owning files: `infrastructure/storage/longhorn/values.yaml`,
`storageclass-flash.yaml`, `storageclass-wired-ha.yaml`, `node-failure-settings.yaml`
in the same directory; `omni/cluster-template/cluster-template-prod-v2.yaml`;
the application PVCs and Kopiur stubs.

The node-down pod deletion settings already exist. They can release an attachment
and permit rescheduling; they cannot create a surviving copy of data whose sole
replica is on the missing host. Longhorn documents this distinction in its
[node-down settings](https://longhorn.io/docs/1.12.1/references/settings/).

**Fix:** extend the existing wired two-copy tier to ordinary, valuable application
state on qualified hosts, starting with the HP SFF and HP Elite after storage
qualification. Keep disposable caches single-copy. Account for Postgres, file
state, and dependencies together: protecting only the database does not restore a
service whose required file volume is still unavailable. Existing StorageClass
changes do not retroactively migrate existing PVCs or their replica settings.

### C2 — The control plane is both a host failure boundary and a measured latency problem

**Priority: P1; topology and latency confirmed, cause not isolated.** The only
control plane shares the HP SFF chassis with a worker. It has a dedicated 100 GiB
virtual disk on a PNY CS900 1 TB SATA device. A failure of that chassis stops
scheduling, controllers, and automatic failover, even if other hosts retain data.
Existing networked workloads may continue running; that is not control-plane HA.

Prometheus reported WAL fsync p99 of approximately 49 ms over five minutes and
59 ms at the worst five-minute sample over 24 hours. Backend commit p99 was about
62 ms. etcd's diagnostic reference suggests WAL p99 below 10 ms and backend commit
p99 below 25 ms. This makes the control-plane storage path a concrete performance
priority, without proving the PNY device alone is responsible. See the
[etcd FAQ](https://etcd.io/docs/v3.6/faq/).

**Fix:** qualify a PLP SSD for the control plane first, including Proxmox cache,
flush, and discard settings. Consider three control-plane members on three
qualified wired physical hosts, with workloads permitted where useful and explicit
CPU/memory/disk reservations. Two members do not tolerate a member loss. Do not
place quorum on the shed media bridge merely to reuse idle RAM. With the Dell
uncertain and the Threadripper a future retirement target, a third trusted wired
host remains a real constraint; do not hide that behind VM counts.

### C3 — Broad Cilium allows defeat the claimed workload isolation

**Priority: P1; confirmed configuration semantics and prior incident evidence.**
`infrastructure/networking/cilium/policies/block-lan-access.yaml` selects every
endpoint and allows ingress from cluster/host/world, cluster-wide egress, public
IPv4 egress, and shared NAS/IoT/API exceptions. Narrower allow policies do not
subtract these grants. The September 4 Temporal cutover in Mink already records
this issue: a conventional NetworkPolicy failed to isolate traffic, whereas an
explicit Cilium ingress deny did.

`monitoring/holmesgpt/egress-policy.yaml` therefore does not enforce its advertised
no-internet boundary. Its `app: holmes` selector does match the rendered workload;
the problem is additive allows, plus its stale vLLM allowlist while the configured
backend is llama.cpp. Holmes is currently scaled to zero, reducing immediate
exposure. Its rendered RBAC is read-only and does not grant Secret reads or pod
exec; retain that useful boundary.

**Fix:** introduce an opt-in isolated namespace policy, removing those namespaces
from the permissive umbrella before relying on scoped allowlists. Alternatively,
use explicit, narrowly scoped deny rules where they express the intended boundary.
Do not roll a blanket deny over storage/controllers. Verify DNS, API, backup,
gateway ingress identity, and application dependencies in a canary namespace.
[Kubernetes policy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
and [Cilium deny precedence](https://docs.cilium.io/en/stable/security/policy/deny/)
support this finding.

### C4 — Cilium monitoring exists as objects, but not as scrape targets

**Priority: P1; confirmed render and live discovery defect.**
`monitoring/prometheus-stack/custom-servicemonitors.yaml` names Cilium agent and
operator monitors with endpoint port `prometheus`; no matching metrics Services
were rendered. The gateway monitor selects `app.kubernetes.io/name: gateway`, but
the gateway data plane is Cilium Envoy, not such a metrics Service. Live Prometheus
had no Cilium targets despite every discovered target being healthy.

The isolated fix experiment verified that agent/operator metrics need both
`enabled: true` and `metricsService: true` when chart-owned ServiceMonitors are
disabled. The resulting Service port name is `metrics`, targeting container port
`prometheus`. Envoy's Service port is `envoy-metrics`. See PR 1 below.

### C5 — CI omits API capabilities that Argo supplies when rendering Helm

**Priority: P2; confirmed validation gap, not missing live ownership.** Four Argo
ServiceMonitors are tracked by the Argo Application, Synced, and scraping
successfully. The pinned chart conditionally renders them when Helm capabilities
contain the monitoring API. CI's plain `kustomize build --enable-helm` omits that
API, so its output contains none. Argo v3.5.2 supplies cluster Kubernetes/API
versions to Kustomize; the live objects are expected, not orphaned Helm leftovers.
The [pinned Argo rendering implementation](https://github.com/argoproj/argo-cd/blob/v3.5.2/util/kustomize/kustomize.go)
and an isolated capability-aware render confirm this distinction.

**Fix:** test both bootstrap capabilities and installed-cluster capabilities in
`.github/workflows/cluster-ci.yml`, using a repository-maintained API set for CI.
Keep Prometheus CRDs owned by kube-prometheus-stack and retain current Argo monitor
ownership unless a separate simplification justifies moving it. A local render
without cluster capabilities is not a complete reproduction of Argo's output.

### C6 — ApplicationSet wave annotations are not a child-application readiness barrier

**Priority: P2; bootstrap race risk.** Root's custom Application health checks gate
its direct child Applications. The wave on an ApplicationSet gates creation of
that ApplicationSet, not completion of every generated Application. For example,
monitoring wave 5 does not itself prove Prometheus CRDs exist before wave 6
observability overlays start.

Files: `infrastructure/controllers/argocd/apps/appsets/`,
`infrastructure/controllers/argocd/values.yaml`, root `CLAUDE.md` wave table.
Do not describe the entire graph as strictly ordered. The current render does not
establish a deterministic early-core ServiceMonitor deadlock; retries can recover
later CRD races.

**Fix:** health-gate the small set of actual CRD dependencies, and document the
remaining eventual convergence. Keep directory discovery. Evaluate any proposed
ApplicationSet health aggregation against the pinned Argo release; do not assume
one Lua snippet can look up child objects. Progressive Syncs also change autosync
behavior, so adopting them is not a harmless annotation cleanup.
[Argo waves](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/) and
[Progressive Syncs](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Progressive-Syncs/).

### C7 — Bootstrap error handling can report success for an unrelated Helm failure

**Priority: P2.** `scripts/bootstrap-argocd.sh` accepts any Helm failure if an
existing argocd-server Deployment is Available. An old healthy server does not
prove the requested installation succeeded.

**Owner clarification:** the bootstrap password setting intentionally preserves
the login stored in 1Password across rebuilds, and Argo is internal-only. The
initial proposal to replace it with a generated password was withdrawn from
PR #2247. Preserve this authentication behavior.

**Fix:** distinguish actual Helm failures from the known rerun ownership conflict.
If tolerating a known SSA ownership conflict, match that specific error and verify
the intended resources/version before proceeding. Exercise first install,
successful rerun, known conflict, and an unrelated failure with shell-command
fixtures; a running old server must not turn the last case green.

### C8 — Secret handling has two concrete exceptions worth fixing

**Priority: P1 for credentials, P2 for scope.**
`my-apps/home/frigate/mqtt/mqtt.yaml` commits a base64-encoded default MQTT credential
in an active Secret. Frigate separately sources its MQTT credentials through
1Password, so the two paths can also drift. Replace the raw Secret with an
ExternalSecret and rotate the broker credential. No credential values belong in
this report.

`my-apps/development/headlamp/metrics-role.yaml` grants read access to `*` resources
in the core API group, which includes Secrets. The associated long-lived token is
declared in `token-secret.yaml`. A live authorization check confirmed that
`system:serviceaccount:kube-system:headlamp-admin` can read Secrets cluster-wide.
This is not a cluster-admin binding, but it exposes credentials from every
namespace to that identity. Restrict the core resource list and use short-lived
login tokens or the operator's existing identity path. The route is internal;
do not misreport Headlamp as publicly exposed.

### C9 — CI is useful but not an enforced merge boundary

**Priority: P2.** GitHub returned no repository rulesets and reported `main` as
unprotected. Existing checks can detect failures without preventing their merge.
This matters because child Applications automatically reconcile main.

**Fix:** require the relevant aggregate validation checks, while keeping an
intentional owner recovery bypass. Account for path-filtered jobs so a docs-only
PR does not wait forever for a check that never starts. Pin third-party Actions
by commit where practical; do not invent a large signing platform for this repo.

### C10 — TrueNAS synchronous-write behavior is a hidden storage-class assumption

**Priority: P2; verified external configuration.** `BigTank/k8s` has `sync=disabled`.
Its NFS/iSCSI descendants and multiple application datasets inherit it. RustFS's
dataset explicitly overrides this to `sync=standard`; do not conflate the backup
repository with the permissive parent. See the inventory for the observed scope.

Accepting a planned NAS outage is different from accepting loss of recently
acknowledged writes after an unexpected NAS crash. `sync=disabled` does not honor
applications' synchronous persistence requests. Document per-dataset durability
before moving more application state onto NFS, and preserve RustFS's override.
Use `standard` for valuable application state; any intentional exception should
name the tolerable loss. A UPS does not cover every software/device failure.
[OpenZFS property semantics](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html).

### C11 — HTTPRoute differences and TLS exceptions can conceal meaningful changes

**Priority: P2.** Argo globally ignores HTTPRoute backend weights, whole CRD
conversion configuration, and whole OpenTelemetryCollector annotations in
`infrastructure/controllers/argocd/values.yaml`. These scopes include real desired
changes. PVC data-source ignores address immutable populator fields and should
not simply be deleted with the others.

`infrastructure/networking/cloudflared/config.yaml` disables origin certificate
verification even though the Gateway has managed certificates. Internal routes
commonly attach to both HTTP and HTTPS listeners without a redirect. A tunnel is
transport, not Cloudflare Access; no Access requirement is assumed here.

**Fix:** narrow each ignore to controller-managed fields, prove a Git weight change
reconciles, and verify tunnel origin TLS using a hostname covered by the actual
certificate. Define the internal HTTP policy explicitly instead of silently
assuming every internal request is HTTPS.

### C12 — Parked Zomboid had an impossible availability budget

**Resolved by #2242; live reconciliation verified.** The Deployment already had
zero replicas. Its PDB requested `minAvailable: 1`, triggering
`KubePdbNotEnoughHealthyPods`; it would also block voluntary eviction when the
single server resumed. The merged PDB permits `maxUnavailable: 1`. Zomboid stays
0/0, both PVCs remain Bound, and its manifests and backup remain for later use.
A PDB does not protect against abrupt host loss.

### C13 — Snapshot-controller replica and placement values were ignored

**Priority: P2; confirmed in the replica follow-up.** The values file declared two
replicas and anti-affinity at the root. Chart 5.2.0 reads these under `controller`.
It rendered and ran one replica with no resource requests and no placement rule.
The controller image happened to match the desired version through the chart
default; the root-level image pin was also ineffective. Move these settings under
`controller`, add a small resource baseline, and verify the actual rendered
replica count and placement policy in CI.

## Refactoring & Simplification

| Finding | Concrete direction |
| --- | --- |
| **R1 — Layout is mostly sound; do not manufacture overlays.** One cluster does not need base/dev/prod copies. `my-apps/common/kopiur-backup` is a useful Component and app-owned scripts are a useful boundary. The expanded graph has 98 child Applications and no duplicate rendered resource ownership. | Keep one app directory per deployed app. Extract genuinely repeated Postgres defaults only if UID, image, backup identity and VPA remain explicit per app; avoid a generic abstraction with dozens of switches. |
| **R2 — Rendered truth is harder to read than necessary.** PR 2227 fixes cache annotations through the parent Kustomization, leaving misleading source annotations. Appset basename naming can also collide if future categories reuse an app basename. | Eventually move the corrected values into their owning templates while preserving identical output; make topology validation expand actual discovery paths and check unique Application names. Do not undo the shared-component cache fix. |
| **R3 — A Cilium comment claims a setting that has no effect.** `gatewayAPI.sessionAffinity` and `sessionAffinityTimeoutSeconds` are not consumed by chart 1.20.1. Removing them produced identical non-Secret output. | Delete those unused values and their claim. Do not change VXLAN, BIG TCP, or xDS mode as part of this cleanup. |
| **R4 — Keep calls a parked investigator.** `monitoring/keep/values.yaml` dispatches every critical alert to Holmes while `monitoring/holmesgpt/kustomization.yaml` sets replicas to zero. The Holmes console from PR 2230 is source only. | Disable the automatic investigation workflow. Keep investigations explicitly requested by the operator. Update the stale Holmes CNPG/vLLM context before activation; keep its read-only tools. |
| **R5 — Observability has overlapping costs without a chosen daily interface.** Coroot contains its own Prometheus, ClickHouse and Keeper, is restricted to the HP SFF, and has profiling/tracing/log collection disabled after an observed read storm. Keep uses roughly 1 GiB; Coroot roughly 2.6 GiB at sampling. | Choose the app overview experience before scaling Coroot or adding another backend. Reuse existing Prometheus/Loki/Tempo queries and Lens links. Keep Trivy; deduplicate by image and affected app. No routine LLM calls. |
| **R6 — Loki's topology is more elaborate than its replica count suggests.** `monitoring/loki-stack/` runs a split read/write/backend stack with caches, while each role is a singleton. | Measure the benefit before retaining every component. A simpler topology is a candidate, not an immediate migration: account for ingestion, S3 layout and retention first. |
| **R7 — Immich's placement couples server availability to ML.** `my-apps/media/immich/` gives ML a library mount and pod affinity, and server placement depends on ML. ML also uses RollingUpdate with RWO volumes. | Verify the required library access against the pinned app, remove unnecessary mounts/affinity, and use a storage-compatible rollout. RWO can be shared by pods on one node, so this is a cross-node rollout risk, not proof that every RollingUpdate deadlocks. |
| **R8 — Fizzy and Mailpit retired together.** Fizzy's SMTP dependency initially prevented removing Mailpit alone. The owner confirmed both are unused. | Merged in #2238. Both Argo Applications and namespaces are gone. Fizzy's policy was configured with `onPolicyDelete: Retain` before removal; this preserves backup history under that policy, not the deleted live PVC. |
| **R9 — Storage device selection encodes today's capacity layout.** The Omni template chooses disks by size, including SFF data >=600 GB and shed data >=700 GB. | A move to ~480 GB drives must change those selectors and VM disk layouts together. Add tests for ambiguous/missing candidates; a cheaper drive must not silently select the wrong disk. Keep filesystem mounts and Longhorn disk tags explicit. |

## Missing Baseline

| Gap | Smallest useful improvement |
| --- | --- |
| **B1 — Resource values silently ignored by Helm.** `nodeExporter.resources` and `kubeStateMetrics.resources` in Prometheus values are wrong subchart paths. All six live node-exporter pods were BestEffort. | Move resource declarations to `prometheus-node-exporter.resources` and `kube-state-metrics.resources`. Isolated render verified the intended requests and limits appear. Preserve the separate enable switches. |
| **B2 — Critical runtime pods remain BestEffort.** All six Cilium Envoy pods, External Secrets, snapshot-controller and multiple Longhorn-generated helpers appeared in this class. Static counts alone miss chart-created controllers and VPA admission. | Give essential controllers explicit initial requests and sensible memory limits using their owning chart/operator settings. Do not force CPU limits or Guaranteed QoS on every workload; verify admitted pods and eviction behavior. |
| **B3 — User-facing apps lack readiness in several places.** Some simple utility deployments and other entries are listed in the workload inventory; the original snapshot also includes now-retired Fizzy. Controllers/sidecars without HTTP probes are not automatically defects. | Prioritize real traffic-serving containers: readiness first, startup for slow initialization, liveness only for a demonstrated unrecoverable state. A Postgres outage should not make every frontend liveness probe trigger a restart storm. |
| **B4 — VPA contract warnings remain.** Gitea, Temporal and Paperless Postgres use wildcard ceilings in two-container pods; Immich Postgres lacks a VPA or documented exemption. | The exporters already have explicit `mode: Off` overrides, so the wildcard warnings do not prove exporter inflation. Name the Postgres container to make scope explicit and add the missing app-owned VPA. Keep CPU-utilization HPA targets memory-only under VPA. |
| **B5 — Successful snapshots are not a service recovery test.** The rendered backup contract passes for all 34 policies; live success-age metrics exist for all 34. Restore correctness still includes application semantics. | Extend the existing canary pattern to verify restored application state, not just Bound PVCs. Gitea file/DB restore timestamps must be compatible; Temporal schedule timers have required rearming after a prior restore. Keep these checks in their owning runbooks. |
| **B6 — Backup freshness does not reflect hourly tiers.** The existing 26-hour threshold deliberately covers daily schedules. | Add a small tier-aware stale threshold or show age versus expected cadence in the app overview. Reuse the existing tested label normalization from PR 2236. Do not add another alerting framework. |
| **B7 — Logs can disappear during the outage being investigated.** OTEL agents use `start_at: end` without durable file offsets; exporter queues are in memory and retries bounded. | Persist offsets and use bounded on-disk queues where loss matters. Set a disk budget and test a backend outage followed by a collector restart. Preserve exclusions preventing collector/Loki recursion. |
| **B8 — Public OTLP request size is not an ingestion budget.** The gateway caps one request at 4 MiB and accepts anonymous writes; that does not bound request rate or trust client-supplied identity labels. | Separate external telemetry identity from trusted cluster telemetry, normalize reserved attributes, and apply a rate/volume budget. Do not embed a durable shared secret in a distributable mobile client and call that authentication. |
| **B9 — Gateway health lacks an external observation.** Gateway Programmed and healthy Cilium pods have previously coexisted with 403s or missing listeners. | Add a small HTTP check from outside the cluster through internal DNS/VIP, and an optional public tunnel check. A Pi-based read-only checker can reuse existing hardware; record that it shares Omni/DNS failure fate. |
| **B10 — Mutable images weaken rebuild reproducibility.** Redis and its exporter use undigested `latest`; n8n does too. Most other workloads pin versions/digests. | Pin these remaining images and let Renovate propose updates. Treat version tags with digests differently from genuinely mutable latest tags. |
| **B11 — Root drift is intentional but under-documented.** Git's root seed enables autosync; the observed live root has none. Prior Mink notes say that was intentionally preserved. | Decide and record a separate root reconciliation policy. Do not silently reapply the seed and restore autosync. Child app autosync remains independent. |

## Automatic recovery design

Use **surviving replicas for routine node loss**, Kopiur for recovering lost or
damaged state. Replacing Longhorn with an automatic PVC-deletion loop would add
exactly the races the owner wants to avoid.

| Failure | Intended response | Boundary |
| --- | --- | --- |
| App process failure | Existing controller/probes restart it | Liveness must not restart healthy processes because a dependency is down. |
| Worker/host loss, qualified replica survives | Longhorn attachment recovery and Kubernetes rescheduling | Requires a working control plane, enough eligible compute, and all required app state/dependencies. |
| NAS temporarily unavailable | Dependent workloads wait and resume | Explicitly accepted by owner. This does not justify returning empty data or ignoring sync writes. |
| Only replica unavailable | Wait for host or escalate to a recovery state machine | A partition is not proof of disk loss. Fence the old writer before a replacement can serve traffic. |
| Confirmed lost/corrupt data | Restore to a new target, validate, switch once | Lock per workload; retain original data; pin restore identity/snapshot; bounded retries; stop on ambiguity. |
| Whole cluster intentionally rebuilt | Existing documented Git + secrets + Kopiur reconstruction | Preserve current tested backup identities; do not reintroduce retired operators. |

Kopiur's `Restore` is not a continuously changing "latest backup" alias. A completed
or terminal failed Restore may need a new identity for another attempt, as the
existing DR runbook explains. Deleting only a PVC is not a safe general refresh
procedure. `onMissingSnapshot: Continue` supports first deployment against a
reachable empty repository; automatic recovery of an enrolled app must not mistake
a missing snapshot for a new installation. A backend outage already leaves restore
PVCs Pending under the current implementation; preserve that behavior.

Plain Postgres on a consistent filesystem snapshot can be recoverable when data
and WAL are captured together. The current approach is not inherently invalid
because it lacks an operator. It provides snapshot-time recovery, not PITR or a
transactionally coordinated snapshot of multiple application volumes. The owner
has substantial rebuild history. The recent Gitea incident identified a zero-byte
Longhorn replica metadata file; that is not evidence that Postgres backup theory
caused the failure. See [PostgreSQL filesystem backup requirements](https://www.postgresql.org/docs/16/backup-file.html).

**Next experiment:** a disposable, Git-managed two-copy canary on two qualified
wired hosts, with a sequence-number writer and an independent HTTP reader. Prove
planned relocation first. A later physical-host outage drill must record affected
production dependencies and an exit path. Check writer fencing, replica survival,
time to successful reads/writes, and original-node return. No destructive live
experiment was performed for this checkpoint.

## Cilium decisions

Keep VXLAN for the ASUS Merlin media bridge, BIG TCP disabled, kubePrism endpoint,
split xDS mode, and the one-at-a-time agent rollout. These encode observed cluster
requirements. The existing random Hubble certificate ignores address that chart's
generated material; do not report that as an unfixed general drift issue.

Restrict L2 announcer eligibility to explicitly labeled, qualified wired nodes,
including an appropriate control-plane candidate if needed. The current
`l2-policy.yaml` selects all nodes, including the shed; a NoSchedule taint does
not exclude a node from lease participation. Its interface regex matches eth/ens
numbered names, not every `eno`/`enp` name claimed by its comment. Validate the
interfaces actually exposed by Talos before changing it. Live leases were held by
the SFF worker and Dell; the internal gateway was on the Dell.

Do not mechanically equate ordinary LoadBalancer `externalTrafficPolicy: Local`
limitations with Cilium Gateway behavior. Cilium's per-node Envoy path preserves
the visible source address for both Cluster and Local, with special health-check
handling. The comment that Local is required for source-IP preservation is wrong;
changing that value alone is not a demonstrated fix for this cluster. Read the
[Gateway behavior](https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/gateway-api/)
alongside [L2 announcement constraints](https://docs.cilium.io/en/stable/network/l2-announcements/).

## Proposed PRs, in order

These are review descriptions, not claims of deployed fixes. Validate changes in
the repository and use its GitOps workflow for rollout.

### PR 1 — Fix Cilium scrape targets and cover Argo's render capabilities

**Description:** Enable Cilium agent/operator metrics Services and point monitoring
at their actual Service ports. Replace the nonexistent gateway target with Envoy.
Test both bootstrap and installed-cluster API capabilities so CI covers the Argo
ServiceMonitors already managed live. Add a check that each repository-owned monitor
selects a rendered Service and named endpoint, with documented exceptions for
operator-generated Services.

Merge this into `infrastructure/networking/cilium/values.yaml`, preserving existing
operator/Envoy settings:

```yaml
prometheus:
  enabled: true
  metricsService: true
  serviceMonitor:
    enabled: false
operator:
  prometheus:
    enabled: true
    metricsService: true
    serviceMonitor:
      enabled: false
```

In `custom-servicemonitors.yaml`, keep the agent/operator selectors and change
their endpoint port to `metrics`. Replace the gateway monitor with:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: cilium-envoy-metrics
  namespace: prometheus-stack
  labels:
    release: kube-prometheus-stack
spec:
  namespaceSelector:
    matchNames: [kube-system]
  selector:
    matchLabels:
      k8s-app: cilium-envoy
  endpoints:
    - port: envoy-metrics
      interval: 30s
```

**Acceptance:** ordinary Kustomize render has no monitoring CRDs in the Cilium
bootstrap app; generated Services have the expected ports; live targets appear
for agent/operator/Envoy and existing Argo scrape targets remain healthy.
Test missing discovery as well as `up == 0`. Revert monitor/config changes to roll
back; no PVC migration is involved.

### PR 2 — Fix ignored exporter resources and essential controller baselines

**Description:** Move node-exporter and kube-state-metrics resource settings under
their real subchart names. Add explicit initial requests for essential BestEffort
controllers, and fix the four remaining database VPA warnings.

```yaml
prometheus-node-exporter:
  resources:
    requests: {cpu: 50m, memory: 128Mi}
    limits: {memory: 256Mi}
kube-state-metrics:
  resources:
    requests: {cpu: 50m, memory: 256Mi}
    limits: {memory: 512Mi}
```

These values reuse the existing declared budget, rather than inventing a new one.
Merge into the existing `kube-state-metrics` mapping so its custom metric/RBAC
configuration remains intact. Acceptance is rendered resources plus admitted pod
requests and successful controller operation; Guaranteed QoS is not the goal.

### PR 3 — Make isolated workloads actually isolated

**Description:** Exclude opted-in namespaces from the broad shared Cilium allow
policy and give them explicit dependency rules. Start with a disposable canary;
then update Holmes's namespace, llama.cpp and telemetry dependencies before any
activation. Preserve its no-write/no-exec RBAC.

**Acceptance:** demonstrate allowed DNS/API/backend calls and rejected unrelated
internet/LAN/namespace calls from the selected workload, plus continued gateway
and backup operation. Reverting the opt-in restores the existing permissive
behavior. Do not combine this rollout with CNI or Gateway version changes.

### PR 4 — Give ordinary application state a surviving wired copy

**Description:** Qualify SFF/Elite storage, define which hosts are eligible, and
move selected valuable state to the existing two-replica tier. Keep Kopiur stubs
and identities. Document per-app file/database dependencies and perform one
canary failover before broader migration.

For a newly provisioned backed-up PVC, the intended shape is:

```yaml
spec:
  storageClassName: longhorn-wired-ha
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
  dataSourceRef:
    apiGroup: kopiur.home-operations.com
    kind: Restore
    name: app-data-restore
```

This is a new-PVC example, not a patch to an existing immutable StorageClass field.
For existing data, write the per-app migration sequence: backup freshness,
compatible restore point, stop/fence writer, preserve source, restore and validate
new target, switch, and retain a rollback path. Never submit a bulk PVC deletion
as the migration plan. Acceptance includes physical-host placement, available
capacity during staging/rebuild, and application reads/writes after relocation.

### PR 5 — Remove the known maintenance and credential traps

**Description:** Zomboid's parked-state budget is fixed in #2242. Replace MQTT's committed
credential with the existing ExternalSecret pattern and rotate it. Restrict
Headlamp Secret access and remove its durable login token once the replacement
login method is tested. Fizzy/Mailpit removal is merged as #2238; restoration
would require restoring the app in Git and using its retained backup identity,
not assuming its deleted live PVC still exists.

Keep these as separate small commits or PRs if rollout/credential handling needs
different timing. Do not bundle secret rotation into an unrelated storage move.

### PR 6 — Provide a useful app overview without automatic AI calls

**Description:** Disable Keep's per-critical Holmes workflow. Build the smallest
read-only app view around existing data: current symptom, last Git/rollout change,
pod restarts, dependencies, PVC replica placement, backup age versus cadence, and
deduplicated image findings. Link to Lens, logs and existing dashboards. Make
investigation an explicit action with a bounded time window.

Acceptance is that the operator can identify the affected app and next check in
one screen. Use a few actionable notifications only after a delivery path and
owner preference are chosen. Do not make the app overview depend on a GPU-backed
model being available, and do not deploy another telemetry database by default.

### PR 7 — Reconcile the documentation and root contract

**Description:** Update the current-state landing page and storage/scheduling
references to the observed multi-host topology and active llama.cpp backend.
Correct the strict-AppSet-wave claim, distinguish repeatable DR from node-loss
recovery, document root's intended autosync policy, and link current procedures
to the existing canary and application checks. Mark historical migration steps
as historical instead of copying them into new instructions.

Acceptance: current manifests and docs agree; obsolete CNPG statements no longer
guide active recovery; links resolve; `mkdocs build --strict` passes. Keep the
older incident records as dated evidence.

## Last ten merged PRs reviewed

All ten were merged by the audit snapshot. Some PR bodies retain draft/future
language; current GitHub state and rendered output take precedence.

| PR | Change | Audit conclusion |
| --- | --- | --- |
| [2227](https://github.com/mitchross/talos-argocd-proxmox/pull/2227) | Argo cache paths and shared Component coverage | Real fix; do not re-report as open. Root still requires separate seed management, and live autosync is intentionally absent. |
| [2228](https://github.com/mitchross/talos-argocd-proxmox/pull/2228) | Backup Restore reference contract | Good coverage improvement; current contract reports zero broken links. Does not prove restored app behavior. |
| [2229](https://github.com/mitchross/talos-argocd-proxmox/pull/2229) | Collector missing/down targets and stable labels | Useful scenario tests; missing-target thinking should extend to Cilium. |
| [2230](https://github.com/mitchross/talos-argocd-proxmox/pull/2230) | Holmes console source/prototype | Not deployed. Do not count it as an available operational interface. |
| [2231](https://github.com/mitchross/talos-argocd-proxmox/pull/2231) | Omni machine contract | Validates declared allocations and placement; live Proxmox drift remains outside its scope. Shed memory differs from Git. |
| [2232](https://github.com/mitchross/talos-argocd-proxmox/pull/2232) | Read-only storage evidence collector | Useful and used here. Appropriately separates configured replicas, actual placement and unproven durability. |
| [2233](https://github.com/mitchross/talos-argocd-proxmox/pull/2233) | Shed solar scrape and dashboards | Current scrape port correction already exists; do not propose it again. Power data can support hardware decisions. |
| [2234](https://github.com/mitchross/talos-argocd-proxmox/pull/2234) | Consumers Energy sync timing/image | Fix addresses delayed upstream data; success of a CronJob alone still does not mean fresh source data. |
| [2235](https://github.com/mitchross/talos-argocd-proxmox/pull/2235) | Power dashboard and gaming sessions | Owner's actual electricity tools are present; use measured cost history rather than TDP estimates. |
| [2236](https://github.com/mitchross/talos-argocd-proxmox/pull/2236) | Backup alert identity and dead Longhorn rules | Corrects known flaws; not an argument for a new alert platform. Tier-aware age remains a separate improvement. |

## Validation and remaining questions

- All 102 Kustomizations under infrastructure, monitoring and my-apps rendered in
  an isolated archive, including the intentionally empty shared Component.
- Expanded 98 child Applications and checked object ownership; no duplicate
  rendered resource ownership found. Helm/operator runtime children are outside
  static controller counts and were examined separately through live state.
- 53 script unit tests passed. Argo topology, inline-script and Omni contract
  checks passed. Backup coverage: 34 policies/restores, zero broken links and
  zero warnings. VPA: zero errors and four warnings described above.
- Isolated chart experiments verified Cilium's unused affinity values, the
  corrected Cilium metrics Services/port names, exporter resource paths, and the
  Argo ServiceMonitors rendered with monitoring API capabilities supplied.
- Local Kustomize was 5.8.1; Helm 4.2.2 versus CI's 4.2.1. Full schema validation
  and every application-level integration test were not rerun. Passing rendering
  is not represented as a full production compatibility certification.
- Read-only host samples and Prometheus history were collected. No failure was
  induced, no disk benchmark wrote to production, and no restore was triggered.

The CSVs retain the original pre-removal snapshot. Hardware movement, NAS ARC
caps, and a production node-loss drill remain proposed work. The Dell is temporary
capacity by owner decision. After the implementation PRs, review upgrade PR
[#2237](https://github.com/mitchross/talos-argocd-proxmox/pull/2237), including its disk
finding, and guidance PR [#2239](https://github.com/mitchross/talos-argocd-proxmox/pull/2239).

## Follow-up live checks after the first fixes

- Cilium: six agent, six Envoy and two operator scrape targets are now discovered
  and up. Argo's existing four targets remain up. The Cilium rollout completed
  with six agents, six Envoys and two operators Ready.
- Zomboid: still zero replicas; both original PVCs Bound; PDB updated.
- VPA: 123 policies, 120 `InPlaceOrRecreate` and three `Off`; 119 have
  recommendations. The no-pod conditions match parked targets. 118 pods carry
  VPA update annotations, including 74 marked in-place updated. Recent
  `ResizeCompleted` events for Deal Scout, Gitea Actions and Surfsense confirm
  actuation. No active pending-resize conditions were found in this sample.
  Temporal Postgres deliberately remains recommendation-only.
- Replica placement: 1Password Connect, Cloudflared, CoreDNS, Cilium operator
  and the Longhorn CSI controller replicas were Ready across separate physical
  hosts. Coroot's three Keeper pods all run on the HP SFF; their count does not
  provide chassis fault tolerance. Both nginx-example pods run on Threadripper.
  Most app controllers remain singletons; whether they can recover elsewhere
  still depends on storage copies, scheduling and surviving control plane.

These checks prove the sampled behavior, not a completed node-failure drill.
