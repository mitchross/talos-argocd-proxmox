# talos-argocd-proxmox

A production-grade GitOps Kubernetes cluster running on **Talos OS** with
**self-managing ArgoCD**. ArgoCD manages its own configuration and discovers
applications by directory structure — no manual `Application` manifests
needed.

> Source repository: [`mitchross/talos-argocd-proxmox`](https://github.com/mitchross/talos-argocd-proxmox)
>
> This site is the rendered version of `docs/` from that repo. Pages link
> back to source files (✏️ edit icon, top right) for one-click PRs.

## Stack

- **OS**: Talos Linux on Proxmox VMs, provisioned via Omni / Sidero
- **CNI**: Cilium with Gateway API + LoadBalancer
- **GitOps**: ArgoCD (self-managing) + ApplicationSets for auto-discovery
- **Storage**: Longhorn (RWO block) + TrueNAS NFS (Kopia repository)
- **Backup**: VolSync + Kopia + custom [pvc-plumber](https://github.com/mitchross/pvc-plumber) admission gate
- **Database**: CloudNativePG (Postgres) with Barman backups to RustFS S3
- **Secrets**: 1Password Connect + External Secrets Operator
- **Policy**: Kyverno (admission, generation, mutation)
- **Observability**: kube-prometheus-stack, Loki, Tempo, OpenTelemetry, Grafana
- **AI**: llama-cpp (Qwen3.6-35B-A3B multimodal) on dedicated GPU

## Documentation

### Storage & disaster recovery

- **[PVC backup/restore (VolSync)](volsync-storage-recovery.md)** — the
  zero-touch system: add a label, get backup, encryption, dedup, and
  automatic restore-on-create. Designed for cluster rebuilds.
- **[Database DR (CloudNativePG)](cnpg-disaster-recovery.md)** — separate
  system: Barman → S3, lineage versioning (`-v1` / `-v2`), recovery
  overlay flag, runbook for in-place restore.

### GitOps architecture

- **[ArgoCD & sync waves](argocd.md)** — App-of-Apps pattern, sync wave
  strategy, ServerSideDiff, Lua health checks for non-standard CRDs.
- **[Root entrypoints](argocd-entrypoints.md)** — how the root Application
  bootstraps ApplicationSets and where each lives in the wave order.

### Networking

- **[Network topology](network-topology.md)** — single-network 10 G design,
  Cilium config, MetalLB scope, Cloudflare tunnel for external access.
- **[Cilium network policies](network-policy.md)** — namespace-level
  default-deny patterns, cluster-mesh-ready policy structure.

### Observability

- **[radar-ng cookbook](radar-ng-observability.md)** — the per-app
  observability layer (collectors, retention, storage backends).
- **[Tempo audit (2026-05-02)](tempo-audit-2026-05-02.md)** — historical
  audit of the Tempo deployment. Linked here for archival; current Tempo
  config has moved on.

## How to read these docs

- The **storage doc** progresses from plain English → simple flow diagrams
  → admission swimlane → operations → known limitations. Stop wherever
  the depth matches what you came for.
- The **CNPG DR doc** is runbook-shaped: read top-to-bottom only when
  doing recovery; the rest of the time use the table of contents.
- Diagrams are Mermaid; they render natively here and on GitHub.

## Adopting any of this

This is one operator's homelab, not a product. The patterns are portable
but the specific image tags, hostnames, and 1Password item names are not.
The [VolSync storage doc](volsync-storage-recovery.md#adapting-this-to-your-cluster)
has a minimum-viable-adoption section; the
[Known limitations](volsync-storage-recovery.md#known-limitations-and-non-goals)
section owns the trade-offs explicitly. Read both before lifting any of
this into your own cluster.
