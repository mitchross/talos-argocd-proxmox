# Talos ArgoCD Proxmox Cluster

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/mitchross/talos-argocd-proxmox)

> Production-grade GitOps Kubernetes cluster on Talos OS with self-managing ArgoCD, Cilium, and zero-touch PVC backup/restore.

A GitOps-driven Kubernetes cluster on **Talos OS** (secure, immutable Linux for K8s) with **ArgoCD** and **Cilium**, running on Proxmox. Nodes are provisioned and managed through **[Omni](https://github.com/siderolabs/omni)** (Sidero's Talos platform) with the **[Proxmox Infrastructure Provider](https://github.com/siderolabs/omni-infra-provider-proxmox)** — no SSH, no manual node config.

The cluster rebuild follows one ordered runbook below. Omni provisions Talos,
then the one-time bootstrap seeds Gateway API CRDs, Cilium, 1Password
credentials, and ArgoCD. ArgoCD takes over and deploys everything else from
this repo.

## Key Features

- **Self-Managing ArgoCD** — ArgoCD manages its own install, upgrades, and ApplicationSets from Git
- **Directory = Application** — apps are discovered by directory path; no hand-written `Application` manifests
- **Sync Wave Ordering** — strict deployment order prevents race conditions
- **Zero-Touch Backups** — label a namespace + drop a per-PVC stub, get automatic [kopiur](https://github.com/home-operations/kopiur) (Kopia-native) backups to RustFS/S3 with restore-before-bind DR
- **Gateway API** — modern ingress via Cilium Gateway API (not legacy Ingress)
- **GPU Support** — full NVIDIA GPU support via Talos system extensions + GPU Operator
- **Zero SSH** — all node management via Omni UI or the Talos API

## Repositories & Resources

| Resource | Description |
|----------|-------------|
| [Omni](https://github.com/siderolabs/omni) | Talos cluster management platform |
| [Proxmox Infra Provider](https://github.com/siderolabs/omni-infra-provider-proxmox) | Proxmox infrastructure provider for Omni |
| [Starter Repo](https://github.com/mitchross/sidero-omni-talos-proxmox-starter) | Full config & automation for Sidero Omni + Talos + Proxmox |
| [Reference Guide](https://www.virtualizationhowto.com/2025/08/how-to-install-talos-omni-on-prem-for-effortless-kubernetes-management/) | VirtualizationHowTo guide for Talos Omni on-prem setup |

## How It Works

![Argo CD bootstrap and dependency-gated sync waves](docs/assets/argocd-sync-waves.svg)

*Wave numbers establish order; health checks make Argo CD wait.
[Open the Argo CD flow full size](docs/assets/argocd-sync-waves.svg).*

**The core idea: a directory *is* an application.** Add a directory with a `kustomization.yaml` under `my-apps/`, `infrastructure/`, or `monitoring/`, push to Git, and an ApplicationSet discovers it and creates the ArgoCD `Application` automatically. No manual `Application` resources.

```
my-apps/ai/comfyui/              → ArgoCD Application "my-apps-comfyui"
infrastructure/storage/longhorn/ → ArgoCD Application "longhorn"
monitoring/prometheus-stack/     → ArgoCD Application "monitoring-prometheus-stack"
```

### Sync Wave Architecture

ArgoCD deploys in strict order so dependencies land before the things that need them:

| Wave | Component | Purpose |
|------|-----------|---------|
| **0** | Foundation | Cilium (CNI), ArgoCD, 1Password Connect, External Secrets, AppProjects |
| **1** | Core controllers | cert-manager, Longhorn, VolumeSnapshot Controller |
| **2** | kopiur operator | Kopia-native backup operator (CRDs + controller + webhook); serves the volume populator for restore-before-bind |
| **3** | kopiur config | kopiur `ClusterRepository` + credential fanout + `VolumeSnapshotClass` |
| **4** | Infrastructure AppSet + custom entrypoints + Database AppSet | cert-manager extras, GPU Operators, Gateway, KEDA, VPA, Temporal Worker Controller; Database AppSet (Redis + shared DB support) fully auto-syncs |
| **5** | OTEL Operator + Monitoring AppSet | OpenTelemetry Operator, Prometheus, Grafana, Loki |
| **6** | Observability overlays + My-Apps AppSet | KEDA/OTEL ServiceMonitors (after monitoring CRDs exist) and `my-apps/*/*` user apps |

> The backup stack is **kopiur** (since 2026-06-27). The retired pvc-plumber + VolSync stack is gone — if you see those names in old docs or git history, ignore them. See [Backup System](#backup-system).

## Prerequisites

1. **Omni + the Proxmox provider are running** and reachable — see [Omni Setup Guide](omni/omni/README.md) and [proxmox-providers/](omni/proxmox-providers/)
2. **An Omni service-account key** stored in 1Password (item `talos-prod-sa`) — see [Cluster Access](#cluster-access-omni-service-account) to create one
3. **Local tools**: `omnictl`, `talosctl`, `kubectl`, `kustomize`, Cilium CLI (`cilium` or `cilium-cli`), 1Password CLI (`op`), and `helm`

### Version pins

| Component | Version | Source of truth |
|-----------|---------|-----------------|
| Omni server + `omnictl` | `v1.10.4` | `omni/omni/omni.env.example` |
| Talos Linux | `v1.13.9` | `omni/cluster-template/cluster-template-prod-v2.yaml` |
| Kubernetes | `v1.36.4` | `omni/cluster-template/cluster-template-prod-v2.yaml` |
| Cilium | `1.20.0` | `infrastructure/networking/cilium/kustomization.yaml` |
| Gateway API CRDs | `v1.6.1` | bootstrap commands below |
| ArgoCD Helm chart | `10.3.0` (Argo CD `v3.5.0`) | `scripts/bootstrap-argocd.sh` |
| Proxmox provider | `v0.2.0@sha256:c0d068…` | `omni/proxmox-providers/docker-compose.yml` |

Keep the Omni server and local `omnictl` on the **same** release — mismatched versions fail with obscure gRPC errors.

> **Keep the Gateway API CRDs on the version Cilium declares support for.** Cilium 1.20 supports Gateway API `v1.6.1`. Bumping the CRDs ahead of Cilium breaks route reconciliation — check the Cilium release's Gateway API docs before moving either one.

---

## Rebuild and Bootstrap

> **Two clusters live here.** Everything below uses the **Threadripper GPU + workers** cluster. For the multi-node prod cluster, swap the names/files:
>
> | | Threadripper GPU + workers | Multi-node prod |
> |---|---|---|
> | Cluster | `talos-prod-cluster-v2` | `talos-prod-cluster` |
> | Machine classes | `hp-sff-control-plane.yaml` + `hp-sff-worker.yaml` + `hp-elite-worker.yaml` + `threadripper-gpu-worker.yaml` + `hp-micro-worker.yaml` + `dell-worker.yaml` | `omni/machine-classes/` |
> | Template | `omni/cluster-template/cluster-template-prod-v2.yaml` | `omni/cluster-template/cluster-template.yaml` |
> | Topology | HP SFF (house, wired): 1 CP + 1 worker; HP Elite (house, wired): 1 large worker; Threadripper: 1 GPU worker; Dell (house, wired): 1 worker; HP micro (shed, wifi): 1 worker | 3 CP + 3 workers + 1 GPU |

The Threadripper classes intentionally allocate 100 GiB total: 12 GiB to the
control plane, 24 GiB to the regular worker, and 64 GiB to the GPU worker. This
leaves roughly 25.67 GiB of the host's 125.67 GiB usable RAM for Proxmox and
QEMU overhead. The HP micro worker receives 12 GiB of its host's 16 GiB and the
HP SFF worker 40 GiB of its host's 48 GiB. The HP Elite worker receives 24 GiB
and 16 vCPU from its 30 GiB, 20-thread host.

This is the only rebuild procedure in this README. Run it from the repository
root, in order. Every required command is shown in full; there are no
placeholder commands or omitted flags.

### 1. Remove the old cluster

Skip this step when provisioning for the first time.

```bash
omnictl cluster delete talos-prod-cluster-v2 --destroy-disconnected-machines
omnictl get machines
```

Do not continue until the old machines disappear from Omni and their VMs
disappear from Proxmox.

### 2. Apply the machine classes and provision Talos

Machine classes and the cluster template are **snapshots stored inside Omni**.
Apply all six classes before syncing the template; template sync owns the
MachineSets. Applying a class does not mutate an existing VM: CPU, RAM, disks,
and the visible machine identity change only when Omni provisions a replacement
from that class.

```bash
omnictl apply -f omni/machine-classes/hp-sff-control-plane.yaml
omnictl apply -f omni/machine-classes/hp-sff-worker.yaml
omnictl apply -f omni/machine-classes/hp-elite-worker.yaml
omnictl apply -f omni/machine-classes/threadripper-gpu-worker.yaml
omnictl apply -f omni/machine-classes/hp-micro-worker.yaml
omnictl apply -f omni/machine-classes/dell-worker.yaml
omnictl get machineclasses

omnictl cluster template validate \
  -f omni/cluster-template/cluster-template-prod-v2.yaml
omnictl cluster template sync -v \
  -f omni/cluster-template/cluster-template-prod-v2.yaml \
  --dry-run
omnictl cluster template sync -v \
  -f omni/cluster-template/cluster-template-prod-v2.yaml

omnictl get machinerequeststatuses -w
```

Stop the watch with `Ctrl-C` after all six requests show
`Provision Complete`. Do not use `cluster template status --wait` here: the
cluster cannot become healthy until Cilium is installed in step 5.

> **Sync this template, not a stale working copy.** A 2026-06-11 rebuild used
> a stale template snapshot and produced the wrong disk layout plus a
> mid-bootstrap Talos upgrade, forcing another reprovision.

### 3. Authenticate and get cluster access

```bash
eval "$(op signin)"

export OMNI_ENDPOINT=https://omni.vanillax.me:443
export OMNI_SERVICE_ACCOUNT_KEY="$(op read 'op://homelab-prod/talos-prod-sa/OMNI_SERVICE_ACCOUNT_KEY')"

omnictl kubeconfig \
  --cluster talos-prod-cluster-v2 \
  --service-account \
  --user talos-prod-sa \
  --force

talosctl config remove omni-prod-talos-prod-cluster-v2 -y 2>/dev/null || true
omnictl talosconfig --cluster talos-prod-cluster-v2

kubectl get nodes -o wide
```

> **`OMNI_ENDPOINT` is mandatory whenever `OMNI_SERVICE_ACCOUNT_KEY` is set.** With the key exported, omnictl ignores config-file contexts entirely; forgetting the endpoint fails with the cryptic `delegating_resolver: invalid target address "": missing address`.

The nodes are expected to be `NotReady` until Cilium is installed in step 5.
The explicit `talosctl config remove` prevents `omnictl talosconfig` from
creating a suffixed duplicate context after a rebuild. First time on a fresh
Omni? Create the service account first — see
[Cluster Access](#cluster-access-omni-service-account).

### 4. Install Gateway API CRDs

Install the complete standard channel before enabling Cilium Gateway API support:

```bash
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml
```

Do not apply the full experimental bundle afterward: Gateway API v1.6.1's
safe-upgrades policy rejects mixing the two channels. This cluster does not use
experimental `TLSRoute` resources.

### 5. Install Cilium (CNI)

Omni provisions Talos without a CNI. This one-time seed gives ArgoCD enough
pod networking to start; ArgoCD assumes management of the same Cilium release
at Wave 0.

```bash
if command -v cilium >/dev/null 2>&1; then
  CILIUM_CMD=cilium
else
  CILIUM_CMD=cilium-cli
fi

"$CILIUM_CMD" install \
    --version 1.20.1 \
    --set cluster.name=talos-prod-cluster-v2 \
    --set ipam.mode=kubernetes \
    --set kubeProxyReplacement=true \
    --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
    --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
    --set cgroup.autoMount.enabled=false \
    --set cgroup.hostRoot=/sys/fs/cgroup \
    --set k8sServiceHost=localhost \
    --set k8sServicePort=7445 \
    --set hubble.enabled=false \
    --set hubble.relay.enabled=false \
    --set hubble.ui.enabled=false \
    --set gatewayAPI.enabled=true \
    --set gatewayAPI.enableAlpn=true \
    --set gatewayAPI.enableAppProtocol=true \
    --set envoy.xdsMode=split
"$CILIUM_CMD" status --wait --wait-duration 5m
kubectl get nodes
```

All nodes must become `Ready` before continuing. These settings must match
what ArgoCD renders at Wave 0 (`infrastructure/networking/cilium/`), or Wave 0
will immediately reconfigure the seed install:

> - **Routing mode matches by default**: the CLI's default (`tunnel`/vxlan) equals `values.yaml`'s `routingMode: tunnel`. If the managed values ever change routing mode, add the matching `--set routingMode=...` here or Wave 0 restarts every agent mid-bootstrap.
> - **`--version 1.20.1`** must match `infrastructure/networking/cilium/kustomization.yaml`. A mismatch makes ArgoCD upgrade Cilium at Wave 0, regenerating some Hubble certs but not others → `x509: certificate signed by unknown authority` blocks every later wave.
> - **`--set envoy.xdsMode=split`** must match `values.yaml`. Seeding without it leaves envoy on the ADS default while Wave 0 flips the agents to split — envoy then holds zero listeners (every Gateway VIP refuses TCP) until `cilium-envoy` is restarted (2026-08-24 rebuild outage).
> - **`cluster.name`** must match `values.yaml` (Hubble cert SANs). Run without it and certs are issued for `default`/`kind-kind` → TLS failures.
> - **Hubble stays disabled at bootstrap on purpose** — ArgoCD enables it at Wave 0 so it's the sole owner of the Hubble TLS certs (no CLI-vs-ArgoCD cert mismatch).

### 6. Pre-seed 1Password secrets

These secrets bootstrap 1Password Connect + External Secrets, which then sync
every other secret from the vault. The dry-run/apply form makes the commands
safe to rerun.

```bash
export OP_CREDENTIALS="$(op read op://homelab-prod/1passwordconnect/1password-credentials.json)"
export OP_CONNECT_TOKEN="$(op read 'op://homelab-prod/1password-operator-token/credential')"

kubectl create namespace 1passwordconnect \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace external-secrets \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic 1password-credentials \
  --namespace 1passwordconnect \
  --from-literal=1password-credentials.json="$OP_CREDENTIALS" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic 1password-operator-token \
  --namespace 1passwordconnect \
  --from-literal=token="$OP_CONNECT_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic 1passwordconnect \
  --namespace external-secrets \
  --from-literal=token="$OP_CONNECT_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 7. Bootstrap ArgoCD

```bash
./scripts/bootstrap-argocd.sh
```

The script pre-flights Cilium, installs ArgoCD via Helm, seeds the `argocd-redis` auth secret (so a fresh cluster doesn't wedge), and applies `root.yaml` to hand control to GitOps self-management.

### 8. Verify

There are no database-specific recovery steps: every database is a plain
Postgres Deployment whose PVC restores via kopiur restore-before-bind at
Wave 6, exactly like every other backed-up PVC (CNPG and its guarded
recovery script were retired 2026-08-13). Backed-up PVCs sit `Pending`
while they hydrate — that is the restore working, not a fault. Once apps
are up, confirm each database's first post-rebuild snapshot succeeds:
`kubectl -n <ns> get snapshot` → newest `Succeeded` with non-zero files.

```bash
omnictl cluster template status \
  -f omni/cluster-template/cluster-template-prod-v2.yaml \
  --wait 30m

kubectl get nodes

# Watch applications sync (all should reach 'Synced')
kubectl get applications -n argocd -w

# View sync-wave order
kubectl get applications -n argocd \
  -o custom-columns=NAME:.metadata.name,WAVE:.metadata.annotations.argocd\\.argoproj\\.io/sync-wave,STATUS:.status.sync.status

# (Optional) ArgoCD UI — a fresh install generates argocd-initial-admin-secret
kubectl port-forward svc/argocd-server -n argocd 8080:443
# open https://localhost:8080
```

## What Happens After Bootstrap

ArgoCD takes over and deploys everything from Git in the order shown in the [Sync Wave Architecture](#sync-wave-architecture) table — Wave 0 (Cilium, secrets) through Wave 6 (user apps). There are **zero manual storage steps**: Longhorn registers the filesystem disks declared by each node template (the active Threadripper worker uses `/var/lib/longhorn` and `/var/mnt/longhorn-nvme1`), the kopiur operator comes up at Wave 2, and any restore-before-bind PVCs populate unattended.

From here, new applications are discovered automatically — add a directory with a `kustomization.yaml` and push to Git.

> **Multi-node prod only** — confirm storage nodes were born with the expected layout (catches a stale-Omni-config failure at provision time instead of at Longhorn bootstrap):
>
> ```bash
> kubectl get nodes -o custom-columns='NAME:.metadata.name,OS:.status.nodeInfo.osImage'  # expect every node Talos (v1.13.9)
> talosctl -n <worker-ip> get disks               # expect a single ~800G sda (sda+sdb = STALE 2-disk layout)
> kubectl get nodes.longhorn.io -n longhorn-system # expect 4 Ready storage nodes after Longhorn starts
> ```

### Mass-restore stability notes

- **Replica rebuilds are throttled to 1/node in Git** (`infrastructure/storage/longhorn/node-failure-settings.yaml`). Full-cluster restores overload any engine on this hardware — don't raise the limit mid-bootstrap.
- A mover pod stuck >15 min on `MountVolume … hasn't been attached yet` with an old VolumeAttachment = stale CSI state — delete the mover pod (its Job recreates it, forcing a fresh attach).
- Pods crashlooping on `read-only file system` after a storage disruption: the volume must FULLY detach (or the pod must land on another node) to drop the stale ro mount — scale to 0, wait for the Longhorn volume to show `detached`, scale back (databases: scale the postgres Deployment).
- History: the Longhorn V2/SPDK engine was tried and retired here (2026-06-12, open Longhorn bugs #13315/#13314). Do not re-enable V2 without a fixed release and a passed DR drill — short version in [docs/disaster-recovery.md](docs/disaster-recovery.md).

## Cluster Access (Omni Service Account)

The default `omnictl kubeconfig` uses OIDC exec auth, which expires and needs a browser login. For long-lived access, create a **service account** with a bearer token.

> **Use the CLI, not the Omni UI.** UI-generated PGP keys are incompatible with the CLI's gopenpgp library (`EdDSA verification failure`).

```bash
# 1. Create the service account (1 year max TTL)
omnictl serviceaccount create talos-prod-sa --use-user-role

# 2. Save BOTH OMNI_ENDPOINT and OMNI_SERVICE_ACCOUNT_KEY into 1Password immediately — the key is shown ONCE.

# 3. Generate a bearer-token kubeconfig (NOT OIDC)
OMNI_ENDPOINT=https://omni.vanillax.me:443 \
OMNI_SERVICE_ACCOUNT_KEY="<key-from-step-2>" \
omnictl kubeconfig --cluster talos-prod-cluster-v2 --service-account --user talos-prod-sa --force

# 4. Verify
kubectl get nodes
```

**Renewal** (expires after 1 year):

```bash
omnictl serviceaccount destroy talos-prod-sa
omnictl serviceaccount create talos-prod-sa --use-user-role
# Regenerate the kubeconfig with step 3 above, then update the key in 1Password.
```

**Gotchas**
- Create via **CLI** — UI keys fail with `gopenpgp: EdDSA verification failure`.
- `--service-account` is what gives you a bearer token; without it you get OIDC exec (the thing that expires).
- If the key fails with signature errors, write it to a file and use `$(cat /tmp/key.txt)` instead of inline quoting.
- Node management (upgrades, config, patches) is done through the Omni web UI.

### Bootstrap authentication and failures

A fresh Argo installation generates a random admin password in
`argocd/argocd-initial-admin-secret`. Retrieve it through Lens or the Argo CLI
(`argocd admin initial-password -n argocd`) when logging in, then change it and
store the chosen credential in 1Password. The bootstrap script no longer seeds a
shared password hash. This Git change does not rotate an existing cluster's
admin credential.

A Helm error stops bootstrap before applying the root Application. This includes
SSA ownership conflicts on a rerun: an already Available server does not prove
the requested install succeeded. Inspect the Helm error and current Argo state;
do not treat a failed installation as a successful upgrade or delete application
data to clear it. The running cluster continues to manage normal Argo upgrades
through its Git-owned Application.

## Backup System

Normal application PVC backups use **[kopiur](https://github.com/home-operations/kopiur)** — a Kopia-native Kubernetes operator — to the RustFS/S3 repository. It replaced the retired pvc-plumber + VolSync stack on 2026-06-27.

- **How a PVC opts in**: label the namespace `kopiur.home-operations.com/repo: cluster-kopia`, add a per-PVC stub (`SnapshotPolicy` + `SnapshotSchedule` + `Restore`) via the shared `my-apps/common/kopiur-backup` Kustomize component, and point the PVC's `dataSourceRef` at `<pvc>-restore`. See [`.claude/commands/add-backup.md`](.claude/commands/add-backup.md).
- **Restore-before-bind DR**: a restore against an **unreachable** repo leaves the PVC `Pending` (never binds an empty volume); a brand-new PVC against a **reachable** repo with no snapshot binds empty and backs up forward (`onMissingSnapshot: Continue` = deploy-or-restore).
- **Mover permissions**: the mover runs as the **data owner's uid:gid**, not root — under baseline Pod Security, root can't read non-root data. See [docs/domains/storage/kopiur-mover-permissions.md](docs/domains/storage/kopiur-mover-permissions.md).
- **Databases included**: every Postgres is a plain Deployment on the same kopiur pipeline (hourly tier). Redis and PostHog's ClickHouse/Kafka are backup-exempt and disposable.
- **Read first**: [docs/domains/storage/kopiur-backup-architecture.md](docs/domains/storage/kopiur-backup-architecture.md), then [docs/disaster-recovery.md](docs/disaster-recovery.md) and [docs/domains/cnpg/run-postgres-plain-english.md](docs/domains/cnpg/run-postgres-plain-english.md) (the database operator guide).

## Cluster Upgrades & Talos 1.13 Notes

The cluster runs Talos **1.13.9**. A few things changed at 1.13 that you'll hit when you spin up or rebuild — read this before touching the cluster template.

### Never pin below Talos 1.13.4

1.13.3 fixed containerd mount propagation and concurrent config-apply; 1.13.4 added a kube-scheduler integer-marshalling fix. This template sets scheduler integer args, so 1.13.4 is the floor — use it or a newer 1.13 patch.

**Observed 1.13.2 failure:** freshly provisioned nodes repeatedly failed to create pod sandboxes (`lstat /proc/.../ns/ipc: no such file or directory`, `can't find shim for sandbox`, `ttrpc: closed`). Rebooting and reinstalling Cilium didn't help; moving them to 1.13.4 restored containerd, control-plane pods, and Cilium. For a stuck rollout, reprovision one machine at a time (preserves etcd quorum for control planes):

```bash
omnictl cluster machine delete <machine-id> --timeout 15m   # wait for Ready before the next
```

### `machine.install.disk` is now mandatory

Talos 1.13 replaced the old install/upgrade flow with the **LifecycleService API**. Earlier versions auto-detected a system disk during `maintenanceUpgrade`; 1.13 requires an explicit `machine.install.disk`.

**Symptom if missing:** fresh VMs boot, but control planes stick in `stage=7 (UPGRADING)` with `configuptodate=false` forever, the LoadBalancer never goes healthy, and Kubernetes never bootstraps — **with no error surfaced anywhere**. The repo ships the fix as a cluster-level patch in both cluster templates:

```yaml
- name: install-disk
  inline:
    machine:
      install:
        disk: /dev/sda   # Proxmox virtio-scsi-single + scsi0 presents as /dev/sda
```

All machine classes (CP / worker / GPU) share the bus layout, so the patch goes at cluster scope. A class with a different disk presentation (e.g. NVMe passthrough → `/dev/nvme0n1`) needs a per-machineset override.

### Upgrading Omni / omnictl

Run Omni and `omnictl` **on the same release** (currently `v1.10.4`, pinned in `omni/omni/omni.env.example`). When upgrading:

1. Take an Omni etcd snapshot (`omni/omni/README.md` → Backup/Recovery).
2. Upgrade the Omni container, restart, and confirm the UI loads and existing clusters stay healthy.
3. Upgrade `omnictl` on your workstation to match — mismatched versions fail with obscure gRPC errors.
4. Regenerate the service-account kubeconfig if it's older than ~30 days (token rotation lags server upgrades).

## Hardware

Five Proxmox hosts run the cluster. Four are wired to the 10G switch; the HP
micro sits in the shed behind a Wi-Fi media bridge.

| Host | Address | CPU / RAM | Role |
|------|---------|-----------|------|
| Threadripper (X399) | 192.168.10.14 | 2950X 16c/32t · 128 GB ECC | GPU worker (1x RTX 3090 passthrough) + general worker |
| Dell Optiplex | 192.168.10.16 | i5-8500 6c · 39 GB | CPU worker (2.5 GbE add-in NIC) |
| HP micro (shed) | 192.168.10.20 | i5-8500T 6c · 31 GB | CPU worker, USB radios, Wi-Fi-bridged and solar-fed |
| HP SFF (ProDesk) | 192.168.10.21 | i5-8500 6c · 63 GB | Control plane + CPU worker |
| HP Elite | 192.168.10.22 | i5-13500T 20c · 31 GB | CPU worker (NVMe Longhorn disk) |

```
Storage
├── TrueNAS (192.168.10.133) — ZFS, NFS/SMB, RustFS S3 for backups
├── Longhorn distributed storage for K8s
└── Local NVMe AI model cache on the Threadripper host

Network
├── 10G switch (2.5 GbE to the Optiplex, Wi-Fi bridge to the shed)
├── Firewalla Gold
└── Internal DNS Resolution (Technitium on the rpi5)
```

The second RTX 3090 lives in a 7800X3D workstation outside the cluster. Wall-plug
power and cost for every host are metered — see
[docs/domains/power/metering.md](docs/domains/power/metering.md).

## Troubleshooting

| Issue | Steps |
|-------|-------|
| **ArgoCD not syncing** | `kubectl get applicationsets -n argocd` · `kubectl describe applicationset infrastructure -n argocd` · check for stale operations before reverting Git: `kubectl get application argocd -n argocd -o yaml` |
| **Cilium issues** | `cilium status` · `kubectl logs -n kube-system -l k8s-app=cilium` · `cilium connectivity test` |
| **Storage issues** | `kubectl get pvc -A` · `kubectl get pods -n longhorn-system` |
| **Longhorn manager crashlooping on the webhook / every PVC Pending** | Check cross-node pod networking first: `kubectl exec -n kube-system <cilium-pod> -c cilium-agent -- cilium-health status`. `Node 1/1` with `Endpoints 0/1` means the pod overlay is broken to that node, not Longhorn — see [Dell worker: nodes Ready but pods cannot cross nodes](docs/domains/networking/dell-proxmox-talos-worker.md#known-failure-nodes-are-ready-but-pods-cannot-cross-nodes) |
| **Secrets not syncing** | `kubectl get externalsecret -A` · `kubectl get pods -n 1passwordconnect` · `kubectl describe clustersecretstore 1password` |
| **GPU issues** | `kubectl get nodes -l feature.node.kubernetes.io/pci-0300_10de.present=true` · `kubectl get pods -n gpu-operator` |
| **Backup issues** | `kubectl -n <ns> get snapshotpolicy,snapshotschedule,restore,snapshot` (Snapshot should reach `Succeeded` with non-zero files) · `kubectl -n <ns> get secret kopiur-rustfs` · `kubectl get pods -n kopiur-system` |

### Emergency reset

```bash
# Remove finalizers and delete all applications, then re-bootstrap
kubectl get applications -n argocd -o name \
  | xargs -I{} kubectl patch {} -n argocd --type json -p '[{"op":"remove","path":"/metadata/finalizers"}]'
kubectl delete applications --all -n argocd
./scripts/bootstrap-argocd.sh
```

## Documentation

- **[CLAUDE.md](CLAUDE.md)** — full development guide and patterns for this repo
- **[docs/index.md](docs/index.md)** — documentation landing page + doc map
- **[docs/easy-guide.md](docs/easy-guide.md)** — the whole system explained from zero (GitOps → sync waves → components → kopiur → DR) — the doc to share
- **[docs/domains/storage/kopiur-backup-architecture.md](docs/domains/storage/kopiur-backup-architecture.md)** — kopiur backup/restore architecture (start here for backups)
- **[docs/disaster-recovery.md](docs/disaster-recovery.md)** — full-cluster destroy/rebuild runbook
- **[docs/domains/argocd/argocd.md](docs/domains/argocd/argocd.md)** · **[entrypoints.md](docs/domains/argocd/entrypoints.md)** — ArgoCD patterns, root entrypoints, and waves
- **[docs/domains/networking/topology.md](docs/domains/networking/topology.md)** · **[policy.md](docs/domains/networking/policy.md)** — network architecture and Cilium policies
- **[omni/](omni/)** — Omni deployment configs, machine classes, and cluster templates ([Omni setup](omni/omni/README.md))

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

MIT License
