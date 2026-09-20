# Practice platform delivery with Radar and OpenTelemetry

**Status: desired configuration in Git; verify deployment after merging the PR.**
This exercise uses a small, read-only copy of your Radar API. It teaches node
placement, telemetry, environment promotion, HTTP traffic splits and autoscaling
on the existing cluster. The real Radar app and its data are separate.

## What changes

| Area | Desired behavior |
| --- | --- |
| Nodes | Keep `general`, `gpu`, `edge`, `disposable`; fill the GPU and control-plane `link=wired` labels in Omni. Physical-host zone names stay unchanged. |
| OTel gateway | Two replicas, preferred general pool, eligible general/GPU/Dell workers, required balanced physical-zone spread, one allowed voluntary disruption. |
| Practice apps | `radar-practice-int`, `radar-practice-cert`, `radar-practice-prod` namespaces; existing Radar image, synthetic fixture data, no PVCs or credentials. |
| Delivery | Independent release pins, prod v1/v2 Services, stable 99/1 route, direct v2 preview; only opted-in routes make backend weights Git-managed. |
| Signals | Existing Loki logs, Prometheus metrics and Tempo traces; Python auto-instrumentation, environment/version labels, 10% parent-based trace sampling. |

SSO, bootstrap, 1Password, Argo secret management, storage layouts and Coroot are
unchanged. Coroot remains an optional diagnostic tool; removing its separate
Prometheus/ClickHouse/Keeper stack requires a usage and dependency check. The
existing OTel pipeline is sufficient for this learning path. No Observe tenant
is configured: collector/instrumentation concepts transfer, while Observe's UI,
datasets and queries require that product.

## Small, explicit placement rules

A **pool** identifies an intended workload role. A **zone** identifies machines
that fail together. The SFF control-plane and worker VMs share `hp-sff`; `house`
currently means the Threadripper host, not all indoor machines. These home zones
share household dependencies and are not independent GKE availability zones.

| Workload | Preferred pool | Eligible fallback | Spread/data boundary |
| --- | --- | --- | --- |
| OTel gateway | general | GPU, Dell | Two replicas balanced by physical zone; no PVC. Agents remain on all relevant nodes. |
| Radar int/cert | disposable | general, GPU | One replica; soft zone preference. Synthetic data only. |
| Radar prod v1/v2 | general | GPU, Dell | Each release spreads independently across eligible physical zones. |
| Existing GPU/edge apps | Existing device selection | Existing policy | Device requirements remain authoritative; shed stays opt-in behind its Wi-Fi taint. |
| Existing stateful services/Coroot | Existing policy | No blanket move | Pod spread does not move Longhorn copies. Coroot's SFF confinement is intentional. |

The gateway and prod use `maxSkew: 1`, `DoNotSchedule`, and
`nodeTaintsPolicy: Honor`. Their selectors count replicas of the same release
and rollout. No `minDomains: 3` is imposed. Available capacity and eligible zones
still determine placement; two replicas do not guarantee survival of every
failure. A PDB controls voluntary eviction, not power loss. The sole control
plane remains a failure boundary.

The September 20 evidence showed limited unreserved memory on Elite and CPU
contention on SFF. This PR adds selected lightweight workloads rather than
moving all telemetry backends onto those machines. The two-copy
`longhorn-wired-ha` class is a separate data-placement mechanism; Longhorn's
`wired-storage` tag is not a Kubernetes Pod selector. See the
[dated capacity evidence](../../inventory/2026-09-20-capacity-and-benchmarks.md).

## Read the release layout

```text
my-apps/common/radar-practice/       shared workload and fixture configuration
my-apps/practice/radar-practice-int/ integration: one API copy
my-apps/practice/radar-practice-cert/ certification: one API copy
my-apps/practice/radar-practice-prod/ stable v1 plus candidate v2
                                      candidate/ owns its own image pin
```

The existing ApplicationSet discovers three separate roots. It already includes
shared components in its cache hints; CI renders shared changes and all three
stages. Existing Applications retain their names and ownership. Practice
Applications carry category/environment labels; labels do not schedule Pods.
Instrumentation is created at wave 0, Deployments at wave 1, and HPA/VPA at
wave 2. An HPA in an earlier wave would wait for a missing scale target and
could block first installation before that Deployment is created.

**Initially every stage uses the same verified `v1.1.17` digest.** v1/v2 are
release slots, not a claim that different source versions were built. Stage a
new published Radar release to practice a real promotion. Image updates are
excluded from Renovate for these practice directories so a background update
cannot skip stages. Shared fixture/base changes can affect every stage together;
review them as platform changes, not as an independently gated image promotion.

## Verify after merge

Use the intended homelab context. The commands below read state; they do not
apply manifests. Tools: kubectl, kustomize, curl; Docker Buildx and Python/PyYAML
are needed for preparing image promotions, and k6 is optional for traffic tests.

1. Check the three generated Applications and the gateway:

   ```sh
   kubectl -n argocd get applications -l platform.vanillax.dev/category=practice
   kubectl -n opentelemetry get pods -l app.kubernetes.io/name=otel-gateway-collector -o wide
   kubectl get nodes -L node.vanillax.dev/pool,topology.kubernetes.io/zone,node.vanillax.dev/link
   ```

   Expect all three practice Applications Synced/Healthy and two Ready gateway
   Pods spread across different physical zones when capacity permits. The Omni
   label edit needs the existing Omni preview/sync workflow; a Git merge alone
   does not apply that template. It changes no machine sizes or disk definitions.

2. Check routes, replicas and scaling:

   ```sh
   kubectl -n radar-practice-prod get deploy,hpa,vpa,pdb
   kubectl -n radar-practice-prod get httproute -o yaml
   ```

   Expect HPA minimums of two v1 Pods and one v2 Pod; route conditions must show
   current-generation `Accepted=True` and `ResolvedRefs=True`. Int/cert have one
   Pod each. HPA owns prod replica counts; Argo ignores only prod practice Deployment
   replica fields. Memory-only VPA does not alter CPU utilization denominators.

3. Send a few requests from the LAN/VPN:

   ```sh
   curl --fail --resolve radar-practice-int.vanillax.me:443:192.168.10.52 https://radar-practice-int.vanillax.me/practice
   curl --fail --resolve radar-practice-prod.vanillax.me:443:192.168.10.52 https://radar-practice-prod.vanillax.me/practice
   curl --fail --resolve radar-practice-prod-v2.vanillax.me:443:192.168.10.52 https://radar-practice-prod-v2.vanillax.me/api/tropical
   ```

   Expect the environment/slot/version identity and the synthetic empty storm
   fixture. Responses are `no-store`. The internal Gateway uses the existing
   wildcard certificate. DNS depends on the existing wildcard/split-DNS setup;
   `--resolve` checks routing independently. No public tunnel route is added.

4. Inspect signals before increasing load. Grafana/Tempo should find
   `service.name=radar-practice`, `deployment.environment.name`, `service.version`
   and `release.slot`. Sampling is 10%, so a single request need not yield a trace.
   Loki receives existing agent-collected logs; gateway enrichment adds Pod
   environment/version and node `platform.pool`/`platform.zone` when Pod
   association succeeds. Prometheus scrapes `/api/metrics`; query
   `radar_ng_http_requests_total{namespace="radar-practice-prod"}` and group by
   `delivery_vanillax_dev_slot`. Validate actual discovered labels in Grafana.
   Collector queues/refusals already have alerts in the
   [collector runbook](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/controllers/opentelemetry-operator-observability/README.md).

The fixture exposes only GET `/practice`, `/api/livez`, `/api/tropical`, and
`/api/metrics`. Other routes return 404. Workflow routes are disabled, Temporal
and forecast addresses point to unused loopback, and the Pod has no Kubernetes
service-account token. An explicit Cilium deny blocks external/host destinations
and Pod namespaces other than `kube-system`/`opentelemetry`, despite the shared
cluster allow. This permits DNS and telemetry infrastructure; it is not a claim
of isolation from every service in those two namespaces. Verify policy verdicts
after merge before relying on the boundary.

### Instrumentation check

The pinned image was tested locally with the pinned Python injection SDK: the
fixture and metrics routes respond, other API routes return 404, and FastAPI
exports a server span with environment/version/slot attributes. Click
instrumentation is disabled because Uvicorn's CLI otherwise creates a process-long
parent span: the tested requests all became internal spans in one trace. This
setting restores independent request traces. Probe/metrics URLs are excluded.
See [Python agent configuration](https://opentelemetry.io/docs/zero-code/python/configuration/).
Local testing does not establish cluster admission, route acceptance or Cilium
policy enforcement; those remain the after-merge checks above.

## Promote through separate PRs

These commands **edit local Git files only**. Each promotion needs its own review,
merge, sync and verification before continuing; running the script repeatedly is
not a substitute for stage acceptance.

1. On a new branch, run `python scripts/platform-practice.py stage vX.Y.Z` with
   an actual published Radar tag. Buildx resolves its immutable digest. Render
   int with `kustomize build my-apps/practice/radar-practice-int`, review the diff,
   open a PR, merge when approved, and verify its fixture and telemetry.
2. Run `python scripts/platform-practice.py promote cert`; repeat the review and
   checks. The script verifies that the source tag still resolves to its recorded
   digest, rejecting a republished tag.
3. Set prod candidate traffic to zero with
   `python scripts/platform-practice.py weight 0`. Review/merge and verify the
   live split before `python scripts/platform-practice.py promote candidate`.
   Promote that change separately and verify the v2 preview.
4. Increase candidate share with `python scripts/platform-practice.py weight 1`,
   then 10, 50, 100 in separately checked PRs. This uses ordinary Deployments,
   Services and HTTPRoutes. Percentages approximate requests over a sufficient
   sample, not users; long-lived connections and uneven load can differ.
5. Once v2 at 100% has passed the chosen observation window, run
   `python scripts/platform-practice.py promote prod` to refresh the retained
   stable slot. Verify it before returning the split to 100/0. Updating v1 ends
   its old rollback window; its previous image/configuration remains in Git.

`python scripts/platform-practice.py status` shows desired pins and weights.
The script checks desired state, not live rollout success. A stage pass requires
Ready Pods, accepted routes, correct fixtures/version signals and acceptable
errors/latency; use the same checks for every release.

## Bounded load, budgets and rollback

`k6 run scripts/platform-practice/traffic.js` samples the stable route at 10
requests/second for 100 seconds, with at most four clients. Counters report v1/v2
responses. Resolve the internal hostname first. To exercise the candidate API,
use `MODE=load ORIGIN=https://radar-practice-prod-v2.vanillax.me k6 run scripts/platform-practice/traffic.js`:
30 requests/second for 30 seconds, max four clients, with abort-on-error threshold.
These are deliberate operator-run tests; no load Job starts on merge. This small
load may not trigger HPA; inspect CPU and metrics rather than assuming scaling.
Stop if latency/errors rise, Pods become Pending, or collector queues grow.

Baseline practice requests: five API Pods × 100m/512Mi = 0.5 CPU / 2.5 GiB,
plus the additional gateway's 100m/256Mi. Existing agents/backends remain.
Prod HPA caps are three v1 and two v2 Pods; int/cert stay at one. VPA can move
memory requests between 256 and 768 MiB, under a 1 GiB limit. Namespace quotas
also cover rollout surge: int/cert allow two Pods each, prod eight. This is a
budget, not proof that every eligible node can satisfy every burst.

For a failed candidate, set `weight 0` through a PR while the old v1 remains
available; this reverses traffic, not external effects or data migrations. If
v1 has already been replaced, restore its previous image **and configuration**
from Git and verify it before restoring traffic. For scheduling failures,
inspect Pod events and eligible zone capacity; do not drain production hosts as
a first test. Revert the focused placement change through Git if necessary.
To remove the exercise, remove the three practice app roots in a reviewed PR;
there is no persistent practice data to migrate. Coroot and real Radar are
separate applications.

Sources: [Kubernetes spread](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/),
[OTel Python injection](https://opentelemetry.io/docs/platforms/kubernetes/operator/automatic/),
[Gateway API weights](https://gateway-api.sigs.k8s.io/guides/user-guides/traffic-splitting/),
[Observe OTel integration](https://docs.observeinc.com/docs/configure-your-own-otel-collector).
