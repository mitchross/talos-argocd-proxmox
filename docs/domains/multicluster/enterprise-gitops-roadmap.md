# Enterprise multi-cluster GitOps roadmap

> **Status: future plan, not current cluster state.** Nothing in this document
> authorizes a cluster migration, directory move, new policy controller, or
> production-style promotion gate. Re-read the live repository and approve each
> phase before implementation.

## Purpose

Keep the current homelab simple while providing a deliberate path toward the
operating model used by larger Kubernetes platforms: explicit ownership,
repeatable deploy targets, environment promotion, multi-cluster discovery,
policy tests, and incident-ready runbooks.

The goal is not to imitate organizational complexity. A pattern belongs here
only when it improves one of these properties:

- a change has a clear owner and review boundary;
- desired state can be rendered and validated before merge;
- the same application can target more than one cluster without copy/paste;
- promotion is visible in Git and reversible by PR;
- cluster, environment, and backup identities cannot be confused;
- an alert leads to a tested recovery action.

## Current strengths to preserve

The existing repository already has several enterprise-quality controls:

- self-managed Argo CD with explicit bootstrap and sync waves;
- strict ApplicationSet Go templates with `missingkey=error`;
- separate ApplicationSets for infrastructure, databases, monitoring, and apps;
- `FailOnSharedResource=true`, bounded retry, and server-side apply;
- renderer versions aligned between CI and Argo repo-server;
- strict schema validation and rejection of empty Applications;
- operator/controller resources separated from workload custom resources;
- External Secrets instead of plaintext credentials;
- Prometheus rules for Argo CD, storage, backup, and workload health;
- kopiur restore-before-bind coverage checks and database-native backup paths;
- explicit documentation of the current physical failure domain.

Multi-cluster expansion must extend these controls, not replace them with a larger
but weaker directory tree.

## Decision table

| Capability | Current posture | Trigger to adopt | Direction |
|---|---|---|---|
| PR contract | CI exists; no standard PR checklist | Repeated review omissions | Add a small Kubernetes/GitOps PR template |
| Alert runbooks | Some alerts link to upstream docs; others contain inline actions | Alerts are routed outside the cluster | Add repository runbooks and `runbook_url` annotations |
| Semantic policy tests | Schema and custom backup checks | A repeated selector, route, security, or ownership error | Add CI-only tests before considering admission enforcement |
| Base + overlays | Most apps are single-cluster directories | The same app is selected for a second cluster/environment | Extract only that app into a portable base and real overlays |
| Deploy-target descriptors | Directory discovery is sufficient | A second cluster needs explicit selection metadata | Add a minimal validated target contract |
| Matrix ApplicationSet | Not needed for one cluster | Two registered cluster identities exist | Combine cluster identity with deploy-target discovery |
| Environment promotion | Merge to `main` deploys the lab | A durable dev/cert/prod distinction exists | Promote immutable image digests through overlay PRs |
| AppProject tenancy | Primarily organization/UI grouping | Multiple people or automation identities gain write access | Restrict source repos, destinations, and resource kinds |
| Runtime admission policy | Intentionally absent | CI-only rules prove stable and bypass/recovery is designed | Introduce narrowly scoped policy enforcement with tests |
| Cross-cluster state recovery | One cluster writes each backup identity | A stateful app runs in two clusters | Qualify every backup lineage by cluster before deployment |

## Target ownership model

Use responsibility boundaries even if everything remains in one repository:

| Layer | Owns | Must not own |
|---|---|---|
| Bootstrap | Argo installation, root seed, irreducible secret handoff | Workloads |
| Platform | CRDs, operators, CNI, storage, Gateway, secret and backup controllers | Application instances/data |
| Observability | Prometheus, Grafana, log/trace pipelines, shared alert rules | Application business configuration |
| Workload | Namespace, Deployment/StatefulSet, Service, HTTPRoute, application CRs, backup intent | Cluster-wide operators or Argo control-plane policy |
| Governance | ApplicationSets, AppProjects, target contract, CI/policy tests | Application credentials |

The Strimzi/Kafka split is the reference: infrastructure owns the operator;
the Kafka app owns its namespace, Kafka resources, topic, and backup contract.

## Proposed multi-cluster shape

Do not perform a big-bang repository move. Introduce this shape additively for
the first shared application, then decide whether older single-cluster apps
benefit from migration.

```text
clusters/
  <cluster-id>/
    bootstrap/
    platform/
    monitoring/
    config.json

apps-shared/
  <app>/
    base/
    overlays/
      <cluster-id>/

deploy-targets/
  <cluster-id>/
    <environment>/
      <app>.json
```

The exact folders may change during implementation. The contracts matter more:

- `base/` is platform-neutral and independently renderable;
- an overlay contains only real cluster/environment differences;
- a deploy target explicitly selects a cluster, environment, and overlay;
- an Application name remains stable when files are reorganized;
- each cluster runs its own Argo CD and manages only its local API server;
- Git connects the fleet; cross-cluster service-account credentials do not.

### Minimal deploy-target contract

Avoid duplicating values already encoded in the path. A future descriptor
should contain only metadata the generator cannot safely derive, for example:

```json
{
  "application": "example",
  "cluster": "lab-dev",
  "environment": "dev",
  "overlay": "apps-shared/example/overlays/lab-dev"
}
```

CI must validate:

- the referenced overlay exists and renders non-empty;
- cluster/environment values are from an allow-list;
- the generated Application name, project, destination, and path are unique;
- path-derived and file-derived identity cannot disagree;
- every image is immutable or explicitly exempted;
- namespaces and cluster-scoped resources have one intended Argo owner.

## Promotion model

Do not use long-lived Git branches as environments. Keep all environment intent
visible together and promote with a reviewed change to an overlay.

Recommended progression:

1. CI builds an image once and records its immutable digest.
2. A PR updates the dev overlay to that digest.
3. Automated sync deploys and validates dev.
4. A later PR copies the same digest into cert/prod.
5. Reverting the promotion PR restores the prior desired digest.

Git tags/releases are useful only if Argo or the promotion workflow consumes
them. Creating release tags while every Application tracks `main` is version
bookkeeping, not a deployment control.

Automated sync can remain enabled in every environment when merge permissions,
required checks, and promotion PRs are the approval gate. A conditional
`templatePatch` that disables prod automation is optional, not an automatic
enterprise improvement.

## Kustomize guidance

### Use a base when

- the same workload runs in at least two targets;
- most resources are identical;
- the base can render with safe values (often zero replicas or a placeholder
  image that cannot accidentally deploy);
- overlay differences are easy to name: hostname, Gateway parent, image digest,
  replica count, storage class, resource sizing, or platform security context.

### Use a Component when

- the feature is optional and cross-cutting;
- multiple unrelated apps consume the same resource/patch contract;
- the Component is safe when rendered through every supported app shape;
- CI renders both with and without the Component.

Good candidates: backup wiring, environment alert routing, standard labels, or
a narrowly defined trust bundle. Avoid a universal Component that mutates every
container, probe, or security context; admission/CI policy is clearer for those
contracts.

### Keep an app single-cluster when

- no second target exists;
- storage, hardware, or networking makes it intentionally cluster-specific;
- extracting a base would create placeholders and patches with no consumer;
- the app is a learning experiment whose value is in its local implementation.

## Multi-cluster ApplicationSet strategy

When a second cluster exists, use a purpose-scoped matrix generator:

```text
registered cluster identity/labels
×
validated deploy-target descriptors
→
one thin Application per target
```

Guardrails:

- strict Go templates and `missingkey=error`;
- stable Application names before and after layout migrations;
- AppProjects applied before ApplicationSets;
- generated Applications remain thin: path, destination, project, sync policy;
- Kustomize/Helm configuration stays in the target overlay so it renders locally;
- do not mix platform controllers and workloads in one ApplicationSet;
- preserve bounded retry, `FailOnSharedResource`, and explicit health gates;
- test generated Application objects before merging any path migration.

## Tenancy and policy progression

Repository separation alone is not a security boundary if AppProjects still
permit every namespace and cluster-scoped kind.

Adopt controls in this order:

1. **Ownership documentation:** declare which layer owns each resource.
2. **CI semantic checks:** selectors match pod labels, routes use approved
   Gateways, namespaces are unique, backups have restore contracts, and
   privileged fields require explicit exceptions.
3. **AppProject restrictions:** allow only the required source paths/repos,
   generated destination namespaces, and resource kinds.
4. **Runtime policy:** only after rules have unit tests, audit-mode evidence,
   documented exemptions, and a bootstrap/recovery bypass.

Policy-as-code tests are valuable before a runtime admission controller is.
They teach the same contract design without risking a blocked rebuild.

## Observability and incident readiness

Enterprise alerting means an actionable ownership chain, not merely more rules:

```text
metric → focused alert → owner/severity/environment → runbook → tested action
```

Future improvements:

- add repository `runbook_url` links to Argo CD and kopiur alerts;
- add `cluster` and `environment` labels to every metric/log/trace pipeline;
- route dev warnings differently from production-critical alerts;
- test alert expressions with `promtool` and test receiver routing separately;
- retain an internal/null receiver until a real destination is deliberately
  selected—never use placeholder webhooks that silently discard notifications.

## Stateful multi-cluster safety

This is the highest-risk part of expansion.

### Backup identity isolation

Two clusters must never write indistinguishable backup identities to the same
repository. Today a kopiur identity commonly derives from application/PVC and
namespace. Deploying the same app and namespace in a second cluster could make
"latest" select the other cluster's snapshot.

Before the first stateful shared app, choose and test one approach:

- include `cluster-id` in kopiur hostname/username identity;
- use a distinct repository/bucket/prefix per cluster;
- or replicate between repositories with explicit source/destination identity.

CI should fail duplicate `(repository, hostname, username, sourcePath)` tuples
across cluster targets. Restore drills must prove each cluster restores its own
lineage.

### Database lineage isolation

Database-native backups need the same rule. Barman server names/prefixes and
recovery sources must include the cluster identity, and only one active writer
may own a lineage. Major-version upgrade and credential-rotation runbooks stay
separate from filesystem restore.

### Kafka

The single-cluster kopiur recovery point is a learning DR mechanism. For an
important multi-cluster stream, prefer Kafka-native replication and treat PVC
snapshots as secondary recovery. Never restore two active Kafka clusters from
one unqualified KRaft identity.

## Phased plan

### Phase 0 — workflow polish (safe anytime)

- [ ] Add a concise GitOps PR template.
- [ ] Add runbook links to the highest-value Argo CD and kopiur alerts.
- [ ] Add CI checks for selector/label agreement, target uniqueness, and
      cluster-scoped ownership.
- [ ] Document the operator-versus-workload ownership convention.

### Phase 1 — second-cluster identity

- [ ] Assign an immutable `cluster-id`, platform, environment, region, and
      failure-domain description.
- [ ] Bootstrap a local self-managed Argo CD without remote cluster credentials.
- [ ] Ensure observability signals include `cluster-id`.
- [ ] Render platform foundations independently before any shared app.

### Phase 2 — stateless shared-app pilot

- [ ] Select one disposable HTTP application.
- [ ] Extract a portable base and two cluster overlays.
- [ ] Add validated deploy-target descriptors.
- [ ] Generate Applications through a new isolated matrix ApplicationSet.
- [ ] Prove stable names, independent rendering, Gateway routing, and rollback.

### Phase 3 — environment promotion

- [ ] Introduce dev/cert/prod only when each has a real operational meaning.
- [ ] Promote one immutable image digest through overlay PRs.
- [ ] Add environment-specific alert routing and resource sizing.
- [ ] Decide whether automated prod sync remains enabled based on the approval
      model, not on convention alone.

### Phase 4 — tenancy and policy

- [ ] Restrict AppProject sources and destinations to generated targets.
- [ ] Add tested resource-kind limits.
- [ ] Run policy checks in CI, then audit mode in-cluster.
- [ ] Enable deny enforcement only with recovery bypass documentation.

### Phase 5 — stateful pilot

- [ ] Define cluster-qualified kopiur and database backup identities.
- [ ] Select one non-critical single-PVC app.
- [ ] Prove backup, deletion, rebuild, restore, and data verification per cluster.
- [ ] Confirm one cluster cannot accidentally restore the other's latest data.
- [ ] Document RPO/RTO and storage/failure-domain assumptions.

### Phase 6 — optional repository boundaries

- [ ] Split repositories only if separate owners, credentials, release cadence,
      or blast-radius controls justify it.
- [ ] Keep Argo control-plane policy in the platform boundary.
- [ ] Ensure workload repositories cannot widen their own AppProject access.
- [ ] Preserve a single local developer command that renders every target.

## Explicitly deferred

- a big-bang move of all current directories under `clusters/`;
- repository-per-domain or repository-per-application sprawl;
- central Argo managing remote cluster credentials;
- long-lived environment branches;
- runtime admission enforcement before CI/audit maturity;
- blanket observability injection into every workload;
- cross-cluster traffic failover before deployment and state recovery are proven;
- calling the current one-host topology highly available.

## Acceptance standard

A phase is complete only when:

- Git renders the exact intended objects with pinned tool versions;
- generated Application identity is reviewed before merge;
- rollback is a documented Git operation;
- alerts and runbooks describe the real failure mode;
- stateful recovery is demonstrated, not inferred;
- the result still works on the smallest supported cluster topology;
- added complexity has a named consumer and an observable benefit.

## Related planning

- [Concrete heterogeneous fleet PRD](prd.md)
- [Argo CD architecture](../argocd/argocd.md)
- [kopiur backup architecture](../storage/kopiur-backup-architecture.md)
- [Disaster recovery runbook](../../disaster-recovery.md)
