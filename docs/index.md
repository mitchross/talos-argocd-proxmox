# talos-argocd-proxmox

<div class="docs-hero" markdown>

<span class="docs-eyebrow">The homelab field guide</span>

## Build it. Understand it. Keep it healthy.

A GitOps Kubernetes homelab on **Talos Linux** with **self-managing ArgoCD**.
Follow the hardware, understand the controllers, and use the runbooks to keep
services and protected data recoverable.

<div class="docs-actions" markdown>

[Explore the lab](lab.md){ .md-button .md-button--primary }
[Read the easy guide](easy-guide.md){ .md-button }

</div>
</div>

ApplicationSets discover app directories. Per-PVC Kopiur resources declare
backup and restore behavior. After the operator rebuilds Talos and seeds Argo,
protected volumes restore automatically from the off-cluster repository.

> Source: [`mitchross/talos-argocd-proxmox`](https://github.com/mitchross/talos-argocd-proxmox)
> · This site renders `docs/` from that repo.

![Logical overview of the Proxmox, Talos, Argo CD, networking, secrets, storage, and backup platform](assets/platform-overview.svg)

*Git reconstructs desired state, 1Password reconstructs credentials, and RustFS
reconstructs protected data. [Open the full-size platform map](assets/platform-overview.svg).*

!!! tip "The point"
    The whole cluster can be destroyed and rebuilt with every protected volume
    restored automatically from the off-cluster Kopia repository — no manual storage
    steps. See [disaster recovery](disaster-recovery.md).

## Under the hood

**Measured September 8, 2026, beginning 23:41 UTC.** This is a recorded inspection,
not a live status feed. Open **Diagnostics Hardware Report** in the
[lab explorer](lab.md) for disk health, benchmarks, workloads and repair priorities.

<div class="docs-stats" role="group" aria-label="September 8 inspection coverage">
<div class="docs-stat"><strong>7</strong><span>physical hosts</span></div>
<div class="docs-stat"><strong>24</strong><span>physical drives</span></div>
<div class="docs-stat"><strong>6</strong><span>Talos nodes</span></div>
<div class="docs-stat"><strong>90</strong><span>persistent volume claims</span></div>
</div>

<div class="docs-chart-grid">
<figure class="docs-chart docs-chart--cpu">
<figcaption>Container CPU use</figcaption>
<span class="docs-chart-subtitle">Observed use as a percentage of each node’s allocatable capacity · 0–100%</span>
<div class="docs-chart-row" title="SFF control plane: 0.66 of 3.95 vCPU"><span>SFF control plane</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 16.63%"></span></span><span class="docs-chart-value">16.6%</span></div>
<div class="docs-chart-row" title="Dell worker: 1.60 of 5.95 vCPU"><span>Dell worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 26.97%"></span></span><span class="docs-chart-value">27.0%</span></div>
<div class="docs-chart-row" title="GPU worker: 5.24 of 29.95 vCPU"><span>GPU worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 17.48%"></span></span><span class="docs-chart-value">17.5%</span></div>
<div class="docs-chart-row" title="Elite worker: 0.97 of 15.95 vCPU"><span>Elite worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 6.06%"></span></span><span class="docs-chart-value">6.1%</span></div>
<div class="docs-chart-row" title="Shed worker: 0.09 of 3.95 vCPU"><span>Shed worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 2.38%"></span></span><span class="docs-chart-value">2.4%</span></div>
<div class="docs-chart-row" title="SFF worker: 1.17 of 5.95 vCPU"><span>SFF worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 19.74%"></span></span><span class="docs-chart-value">19.7%</span></div>
</figure>
<figure class="docs-chart docs-chart--memory">
<figcaption>Container memory use</figcaption>
<span class="docs-chart-subtitle">Observed use as a percentage of each node’s allocatable capacity · 0–100%</span>
<div class="docs-chart-row" title="SFF control plane: 4.93 of 11.07 GiB"><span>SFF control plane</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 44.54%"></span></span><span class="docs-chart-value">44.5%</span></div>
<div class="docs-chart-row" title="Dell worker: 9.82 of 28.89 GiB"><span>Dell worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 33.98%"></span></span><span class="docs-chart-value">34.0%</span></div>
<div class="docs-chart-row" title="GPU worker: 36.33 of 97.67 GiB"><span>GPU worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 37.20%"></span></span><span class="docs-chart-value">37.2%</span></div>
<div class="docs-chart-row" title="Elite worker: 10.42 of 22.98 GiB"><span>Elite worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 45.36%"></span></span><span class="docs-chart-value">45.4%</span></div>
<div class="docs-chart-row" title="Shed worker: 1.39 of 23.39 GiB"><span>Shed worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 5.94%"></span></span><span class="docs-chart-value">5.9%</span></div>
<div class="docs-chart-row" title="SFF worker: 12.05 of 38.68 GiB"><span>SFF worker</span><span class="docs-chart-track" aria-hidden="true"><span class="docs-chart-fill" style="width: 31.15%"></span></span><span class="docs-chart-value">31.1%</span></div>
</figure>
</div>

<p class="docs-chart-note">Container working-set memory and container CPU usage from the inspection;
these exclude host overhead and do not measure disk wait or per-container memory pressure.
Aggregate headroom can coexist with a badly constrained Job.</p>

[Read the measured findings](audits/2026-09-08-live-audit.md) ·
[Download the source inventory](assets/inspection/inventory.json)

## Stack

- **OS**: Talos Linux on Proxmox VMs, provisioned via Omni / Sidero
- **CNI**: Cilium with Gateway API + LoadBalancer
- **GitOps**: ArgoCD (self-managing) + ApplicationSets for auto-discovery
- **Storage**: Longhorn V1, mostly one replica despite multiple physical hosts;
  Temporal Postgres uses the wired two-replica class. NAS provides bulk files and
  off-cluster backups. [Failure domains and disk inventory](audits/2026-09-05-inventory.md).
- **Backup**: [kopiur](https://github.com/home-operations/kopiur) (Kopia-native) → RustFS S3, per-PVC `SnapshotPolicy`/`Restore` with restore-before-bind
- **Database**: plain Postgres Deployments backed up by kopiur — hourly snapshots, restore-before-bind (CNPG retired 2026-08-13)
- **Secrets**: 1Password Connect + External Secrets Operator
- **Observability**: kube-prometheus-stack, Loki, Tempo, OpenTelemetry
- **AI**: the production backend serves official `qwen3.8-27b` FP8 through vLLM
  on both RTX 3090s; llama.cpp is retained for rollback. The [model catalog](domains/ai-gpu/model-catalog.md)
  owns the current backend settings; use the [scale-swap runbook](domains/ai-gpu/gpu-scale-swap.md) to change the card owner.

## Documentation

[**Explore the lab →**](lab.md) Click through the machines, IPs, disks, VMs and
what depends on each host. Includes the proposed jobs for each machine.

For the latest measured state, open the [September 8 live inspection](audits/2026-09-08-live-audit.md)
and its [interactive device and workload inventory](assets/inspection/index.html).

Start with the [hardware, disk placement and GitOps review](audits/2026-09-05-hardware-and-placement-review.md)
for the engineering recommendation, proposed workload pools and disk move priorities.
Those proposals are explicitly separate from deployed state.

The [September 5 architecture audit](audits/2026-09-05-architecture-audit.md) and
[dated repository/host inventory](audits/2026-09-05-inventory.md) record verified
findings, proposed fixes, and current-state differences that still need reconciliation.

Every page follows the [documentation reader contract](documentation-standard.md):
state the current posture, explain unfamiliar choices, provide verifiable steps,
and include failure/rollback guidance for risky operations.

<div class="grid cards" markdown>

-   📖 **The easy guide** — *share this one*

    ---

    The whole system from zero: GitOps → sync waves → Kustomize components →
    kopiur → restore-before-bind. Real YAML, an adoption ladder for
    "I just want to try kopiur", and the colleague FAQ.

    [→ easy-guide.md](easy-guide.md)

-   💾 **kopiur backup architecture** — *the one doc*

    ---

    The pieces, the component pattern, backup + restore flow diagrams, and
    the 6-step add-a-backup checklist.

    [→ kopiur-backup-architecture.md](domains/storage/kopiur-backup-architecture.md)

-   ☠️ **Disaster recovery** — *the runbook*

    ---

    Destroy → rebuild → restore: pre-nuke checklist, restore-wave
    expectations, and the restore canary.

    [→ disaster-recovery.md](disaster-recovery.md)

-   🗄️ **Storage architecture** — *operator's reference*

    ---

    Design decisions, who-provides-what, day-2 operations
    (enable / exempt / drill), troubleshooting, and the honest limitations.

    [→ storage-architecture.md](storage-architecture.md)

</div>

### 💾 More storage & backups

Backups are **kopiur** (Kopia-native operator).

- **[kopiur-playground.md](kopiur-playground.md)** — 🕹️ interactive, in-browser
  simulation of backup + restore-before-bind: delete a PVC, take S3 offline,
  nuke the cluster, watch what happens.
- **[domains/storage/kopiur-mover-permissions.md](domains/storage/kopiur-mover-permissions.md)** —
  why the backup mover runs as the data owner (the #1 gotcha), plain English + technical.
- **[backup-repository-setup.md](backup-repository-setup.md)** — the one-time backend
  setup: RustFS S3 bucket, credentials, the kopiur `ClusterRepository`.

### 🗃️ Domains

- **Databases**: [Run Postgres here — plain-English operator guide](domains/cnpg/run-postgres-plain-english.md) · [Plain Postgres pattern & CNPG retirement](domains/cnpg/plain-postgres-migration.md)
- **GitOps / ArgoCD**: [argocd](domains/argocd/argocd.md) · [entrypoints & waves](domains/argocd/entrypoints.md)
- **Enterprise multi-cluster planning**: [roadmap](domains/multicluster/enterprise-gitops-roadmap.md) · [concrete fleet PRD](domains/multicluster/prd.md)
- **Networking**: [topology](domains/networking/topology.md) · [Dell Proxmox Talos worker](domains/networking/dell-proxmox-talos-worker.md) · [policy](domains/networking/policy.md) · [Technitium `vanillax.me` migration](domains/networking/technitium-vanillax-me-migration.md)
- **Storage**: [Talos SELinux audit remediation](domains/storage/selinux-mount-context.md) · [move a PVC to another StorageClass](domains/storage/pvc-storageclass-migration.md) · [kopia maintenance](domains/storage/kopia-maintenance-plan.md) · [RWO/RWX model & sizing](domains/storage/storage-model-rwo-rwx-and-sizing.md) · [RustFS credentials](domains/rustfs/credential-runbook.md) · [future: tiered storage](domains/storage/architecture-future.md)
- **Observability**: [radar-ng](domains/observability/radar-ng.md)
- **Scheduling**: [VPA policy ownership and topology](domains/scheduling/vpa-and-topology.md)
- **Power**: [wall-plug metering, cost model and the power-off lockout](domains/power/metering.md)
- **Apps**: [Self-hosting PostHog on Kubernetes](posthog-self-host-k8s.md) — the full recipe (topology, single-node ClickHouse, routing, upgrade checklist), portable to any cluster
- **AI / GPU**: [model catalog](domains/ai-gpu/model-catalog.md) · [one vs two 3090s](domains/ai-gpu/single-vs-dual-3090.md) · [3090 LLM optimization](domains/ai-gpu/3090-llm-optimization.md) · [pi agent local-dev guide](domains/ai-gpu/pi-agent-local-dev.md)

## Adopting any of this

This is one operator's homelab, not a product. The patterns are portable —
the label-driven backup contract, the off-cluster repository, the
restore-canary idea, the sync-wave bootstrap — but the image tags, hostnames,
and 1Password item names are not. Start with
[storage-architecture.md](storage-architecture.md).
