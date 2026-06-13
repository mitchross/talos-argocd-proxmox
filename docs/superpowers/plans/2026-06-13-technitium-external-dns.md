# Technitium ExternalDNS Implementation Plan

> ⚠️ **SUPERSEDED / HISTORICAL.** This plan describes the original
> `internal.vanillax.me` *test* zone, which has been retired. Production uses
> split DNS on real names under `vanillax.me` (no `internal.` prefix). For the
> live design, cutover order, and known pitfalls see
> [`docs/domains/networking/technitium-vanillax-me-migration.md`](../../domains/networking/technitium-vanillax-me-migration.md).
> Kept only as a dated record of how the test instance was built.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an isolated RFC2136 ExternalDNS instance and test Gateway for `internal.vanillax.me`.

**Architecture:** Render a second release of the repository's existing ExternalDNS Helm chart inside the current Argo CD application. Use a dedicated Cilium Gateway at `192.168.10.52`, label-filter route discovery, and reuse the existing Cloudflare DNS-01 ClusterIssuer for TLS.

**Tech Stack:** Argo CD, Kustomize, Helm, ExternalDNS, External Secrets, 1Password Connect, Cilium Gateway API, cert-manager, Technitium RFC2136

---

### Task 1: Add The Technitium ExternalDNS Release

**Files:**
- Create: `infrastructure/controllers/external-dns/technitium-external-secret.yaml`
- Create: `infrastructure/controllers/external-dns/values-technitium.yaml`
- Modify: `infrastructure/controllers/external-dns/kustomization.yaml`

- [x] Add an ExternalSecret mapping `external-dns-technitium/tsig-secret` to the namespaced Kubernetes Secret.
- [x] Add Helm values for RFC2136, Gateway HTTPRoute discovery, domain filtering, TXT ownership, and safe upsert-only policy.
- [x] Add the resource and second Helm release to the existing Kustomization.
- [x] Render with `kubectl kustomize infrastructure/controllers/external-dns --enable-helm`.

### Task 2: Add The Isolated Gateway

**Files:**
- Create: `infrastructure/networking/gateway/gateway-internal-technitium.yaml`
- Modify: `infrastructure/networking/gateway/kustomization.yaml`

- [x] Add a Cilium Gateway pinned to `192.168.10.52`.
- [x] Add HTTP and HTTPS listeners for `*.internal.vanillax.me`.
- [x] Reference `cert-internal-vanillax` so cert-manager creates the wildcard certificate.
- [x] Add the Gateway to the Kustomization and render it.

### Task 3: Document Operation And IP Ownership

**Files:**
- Create: `infrastructure/controllers/external-dns/README.md`
- Modify: `infrastructure/networking/cilium/ip-pool.yaml`
- Modify: `infrastructure/networking/README.md`

- [x] Document the Technitium endpoint, zone, 1Password reference, safe policy, route labels, and `dig` checks.
- [x] Reserve `192.168.10.52` in the IP pool comments and networking assignment table.

### Task 4: Validate The GitOps Output

**Files:**
- Test: rendered manifests from both changed Kustomizations

- [x] Run `./scripts/validate-argocd-apps.sh`.
- [x] Render both changed Kustomizations with Helm enabled.
- [x] Assert the rendered Deployment has the expected name, arguments, and Secret environment reference.
- [x] Assert the existing Cloudflare Deployment arguments remain unchanged.
- [x] Run `kubectl apply --dry-run=client` on the rendered manifests.
- [x] Review `git diff --check` and the final diff for secret leakage.
