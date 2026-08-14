# Talos 1.13 → 1.14 upgrade

**Purpose:** everything that changes for *this* cluster when moving from Talos
`v1.13.7` / Kubernetes `v1.36.3` to Talos `v1.14.0-beta.1` / Kubernetes
`v1.37.0-beta.0`, plus the pre-flight, verification, and rollback steps.

**Status:** runbook. The version pins in
[`omni/cluster-template/cluster-template.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/cluster-template/cluster-template.yaml)
and
[`cluster-template-threadripper-gpu-workers.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/cluster-template/cluster-template-threadripper-gpu-workers.yaml)
are the source of truth and already point at 1.14. The *rollout* is a manual
`omnictl` operation — committing this repo does not upgrade any node.

**Scope:** the node operating system, the Kubernetes control plane, and the Omni
server flags that gate them. It deliberately leaves ArgoCD, Cilium, Longhorn,
and the backup stack alone — those are versioned independently and are only
*verified* here, not changed.

---

## Read this first: it is a pre-release pin

Neither release line has a GA tag yet.

| | Pinned | Newest GA |
|---|---|---|
| Talos | `v1.14.0-beta.1` (2026-07-31) | `v1.13.7` |
| Kubernetes | `v1.37.0-beta.0` | `v1.36.3` |

Two consequences that change how you operate:

- **Omni hides pre-release versions by default** and rejects them during
  `omnictl cluster template sync`. `omni/omni/omni.env.example` now ships
  `VERSION_FLAGS=--enable-talos-pre-release-versions`, interpolated into the
  compose `command:`. If Omni accepts the Talos version but rejects the
  Kubernetes one, find its counterpart flag:
  `docker run --rm ghcr.io/siderolabs/omni:v1.10.1 --help | grep pre-release`.
- **There is no roll-forward.** A regression in beta.1 has no 1.14.x patch to
  escape to; the only recovery is rolling *back* to 1.13.7, which is an
  in-place Talos downgrade and is not guaranteed clean. Treat the etcd snapshot
  in the pre-flight as mandatory, not optional.

Move both templates to the GA tags and empty `VERSION_FLAGS` as soon as they
ship.

---

## What 1.14 changes that this cluster actually touches

### 1. `/var` is mounted `noexec` — breaks Longhorn V1

Talos 1.14 adds `noexec` to the EPHEMERAL volume (`/var`) alongside the
existing `nosuid` and `nodev`. Longhorn's **V1 engine execs its engine and
replica binaries out of `/var/lib/longhorn`**, so a machine provisioned under
the 1.14 default comes up with a dead instance-manager. This cluster runs V1 —
the V2/SPDK engine was retired 2026-06-12 after the full-DR fault loop.

Both templates carry the opt-out as a cluster-scope patch:

```yaml
- name: ephemeral-allow-exec
  inline:
    apiVersion: v1alpha1
    kind: VolumeConfig
    name: EPHEMERAL
    mount:
      secure: false
```

`secure` is all-or-nothing: disabling `noexec` also disables `nosuid` and
`nodev`. That is exactly the mount posture 1.13 ran with, so this is a
*hold-still*, not a regression.

The upstream-recommended alternative — a dedicated Longhorn disk on a
`UserVolumeConfig` mounted at `/var/mnt/longhorn` — is **not** usable on the
multi-node prod template: adding a second virtual disk introduces an extra
virtio-scsi controller, which shifts PCIe enumeration and renames the NIC. That
is precisely what left the GPU worker with no IP and no SideroLink on
2026-06-11 and required a reprovision. The Threadripper template *does* already
run UserVolume-backed Longhorn tiers (`/var/mnt/longhorn-nvme1`,
`/var/mnt/longhorn-ssd-flash` on the GPU worker, `/var/mnt/longhorn-dell-ssd`
on the Dell), but every node set still registers a `talos-ephemeral` Longhorn
disk at `/var/lib/longhorn`, so it needs the same opt-out. That includes the
Dell, whose `talos-ephemeral` entry is `allowScheduling: false` — unschedulable
for *replicas* is not the same as unused by the instance-manager.

!!! warning "This is a rebuild hazard, not an upgrade-day one"
    Only **newly provisioned** machines get `noexec`; nodes upgraded in place
    keep their existing mount options. An in-place 1.13 → 1.14 upgrade will
    look completely healthy while a future destroy-and-restore drill fails.
    Do not skip the rebuild verification in
    [disaster-recovery.md](../../disaster-recovery.md).

### 2. `ghcr.io/siderolabs/installer` is no longer published

The default installer moved to the Image Factory and the `installer` image is
not pushed with 1.14+ releases. Two follow-ons:

- `.github/renovate.json5` tracked Talos versions through that Docker tag and
  would have silently frozen at the last 1.13 tag. The rule now uses the
  `github-releases` datasource on `siderolabs/talos`, matches **both** cluster
  templates, and accepts pre-release suffixes. Renovate only proposes unstable
  versions when the current value is itself unstable, so it reverts to
  stable-only on its own once the pin moves to GA.
- Any hand-rolled `talosctl upgrade --image ghcr.io/siderolabs/installer:...`
  must become a Factory image reference. Omni-driven upgrades already resolve
  the image themselves and need no change.

### 3. etcd HTTP endpoints moved to port 2383

Upstream moved etcd's plain-HTTP endpoints off 2379 onto a dedicated 2383.
This cluster does **not** rely on the default: the `control-plane-performance`
patch sets `etcd.extraArgs.listen-metrics-urls: http://0.0.0.0:2381`, and
Prometheus scrapes control-plane node IPs on 2381 via
`monitoring/prometheus-stack/values.yaml` → `additionalScrapeConfigs` →
`kube-etcd`.

The explicit override should continue to win, but Talos maintains a denylist of
etcd arguments it manages itself. **Verify the `kube-etcd` scrape job still has
targets after the upgrade** (step 4 below) — if Talos has taken ownership of
`listen-metrics-urls`, the fix is to drop the extraArg and repoint the scrape
config at 2383.

### 4. Workload isolation (`sandboxd`) and in-tree volume plugins

1.14 runs the container runtime plane in a dedicated PID/mount namespace,
configured via a `SecurityProfileConfig` document. It is **enabled by default
on new clusters and disabled on upgrades** unless you add the document. The
same change is why 1.14 declares the in-tree iSCSI volume plugin non-functional
("use CSI drivers instead").

This repo is already CSI-only — Longhorn CSI and `nfs.csi.k8s.io` — so the
in-tree removal is a no-op today. The open question is what a **fresh** cluster
does: a rebuilt cluster gets `sandboxd` on by default, and Longhorn's CSI node
plugin reaches `iscsiadm` through the host mount namespace (the reason the
`siderolabs/iscsi-tools` extension is installed). Treat this as unproven until
a rebuild drill passes; the lever if it breaks is an explicit
`SecurityProfileConfig` patch disabling isolation.

### 5. NTS is on by default for time sync

1.14 enables Network Time Security for the default `time.cloudflare.com` server
(`TimeServerConfig.useNTS`). This cluster does not override time servers, so it
picks up the default. NTS key exchange runs over TCP/4460 — if the Firewalla
egress policy blocks it, nodes can fail to sync time, which manifests as
certificate and etcd errors rather than as an obvious clock problem. Checked in
step 4.

### 6. Deprecated v1alpha1 fields this repo still uses

All of these still work in 1.14; the multi-document replacements are additive.
**No migration is performed in this change** — a version bump and a config
schema migration should not fail together.

| Field in use | 1.14 replacement | Where |
|---|---|---|
| `.machine.install` | `UnattendedInstall` | `install-disk` patch, both templates |
| `.machine.sysctls` | `SysctlConfig` | `node-performance`, GPU worker patches |
| `.machine.udev.rules` | `UdevRulesConfig` | `node-performance` patch |
| `.machine.kernel.modules` | `KernelModuleConfig` | `patches/gpu-worker.yaml`, `patches/threadripper-gpu-workers.yaml` |
| `.cluster.network.cni` | `KubeNetworkConfig` | `disable-default-cni` patch |
| `.cluster.proxy` | `KubeProxyConfig` | `disable-default-cni` patch |
| `.cluster.apiServer` | `KubeAPIServerConfig` | `control-plane-performance` patch |
| `.cluster.controllerManager` | `KubeControllerManagerConfig` | `control-plane-performance` patch |
| `.cluster.scheduler` | `KubeSchedulerConfig` | `control-plane-performance` patch |
| `.machine.kubelet.*` | `KubeNodeConfig` | kubelet patches, `nodeIP.validSubnets` |

`.machine.features.hostDNS` moved to `ResolverConfig`, but this repo never set
it — the existing `dns-resolver` patch is already a `ResolverConfig` document
and needs no change.

### 7. Things that changed upstream and do not affect this repo

- `talosctl apply-config --mode=reboot` removed. This repo drives config through
  Omni template sync, not `apply-config`.
- FlexVolume host path `/usr/libexec/kubernetes` removed. Nothing uses it.
- TLS 1.3 minimum on etcd and kube-apiserver; custom cipher-suite settings are
  now ignored. This repo sets no cipher suites.
- `net.ipv4.conf.all.send_redirects` now defaults to `0`. Cilium does not rely
  on ICMP redirects and the `node-performance` sysctl set does not touch it.
- Discovery cluster-ID encoding changed from URL-safe to standard base64. Omni
  owns discovery configuration for these clusters.

### Component versions in v1.14.0-beta.1

Linux 6.18.41 · Kubernetes 1.37.0-beta.0 · containerd 2.3.3 · etcd 3.7.1 ·
runc 1.5.1 · CoreDNS 1.14.6 · Flannel 0.28.8 (unused — Cilium is the CNI).

The matching `siderolabs/extensions` build for `v1.14.0-beta.1` carries NVIDIA
production **595.71.05** and container-toolkit **1.19.1** — the same driver
branch the RTX 3090 worker runs today, so no driver-generation change rides
along with this upgrade. (Post-beta.1 dev builds move to 595.91.07; the exact
`v1.14.0-beta.1` tag does not.) The RTX 3090 `gpu-workers` set is the only one
carrying NVIDIA extensions — the Dell is compute-only since 2026-08.

---

## Known risks not resolved by this change

| Risk | Why it is open | How you would find out |
|---|---|---|
| **Cilium 1.20.0 on Kubernetes 1.37** | Cilium's published compatibility matrix tops out below 1.37. Less exposed than it looks: the cluster moved to 1.20.0 and Gateway API v1.6.1 separately, so this is the newest Cilium against the newest Kubernetes rather than an old one stretched forward. | `cilium status` degraded, agents crash-looping, or Hubble certificate errors right after the control-plane upgrade. |
| **Longhorn 1.12.0 on Kubernetes 1.37** | The chart predates 1.37 and has not moved. This is the more exposed of the two. | Longhorn manager pods failing to list/watch after the upgrade. |
| **`sandboxd` on a rebuilt cluster** | Enabled by default only on new clusters, so an in-place upgrade cannot exercise it. | Next destroy-and-rebuild drill: Longhorn CSI node plugin failing to attach volumes. |
| **Beta Kubernetes API churn** | 1.37 is a beta; API removals may not be final. | Step 2 pre-flight scan below. |

---

## Procedure

### Prerequisites

- `omnictl` and the Omni server both on `v1.10.1` — mismatched versions fail
  with obscure gRPC errors. **v1.10 is what makes this upgrade supported**: it
  is the first Omni release that knows about Talos 1.14 and its multi-document
  configuration layouts, and it routes maintenance installs through Talos's
  LifecycleService on 1.13+. Do not attempt this on a 1.9.x Omni.
- Both Proxmox provider instances on `v0.2.0` and on the **same** digest —
  `omni/proxmox-provider/` and `omni/proxmox-provider-dell/`. Upgrade the
  providers *before* the cluster, so a provider restart is not competing with a
  rolling node upgrade for machine-request reconciliation.
- A current Omni etcd snapshot (`omni/omni/README.md` → Backup/Recovery).
- A current cluster etcd snapshot (step 1).
- Every kopiur `Snapshot` recently `Succeeded` — this is the real safety net if
  a node has to be reprovisioned. See
  [kopiur-backup-architecture.md](../storage/kopiur-backup-architecture.md).

### 1. Snapshot and record the starting state

```bash
talosctl -n <control-plane-ip> etcd snapshot /tmp/etcd-pre-1.14.snapshot
kubectl get nodes -o custom-columns='NAME:.metadata.name,OS:.status.nodeInfo.osImage,KUBELET:.status.nodeInfo.kubeletVersion'
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

**Expected:** every node reports Talos `v1.13.7` / kubelet `v1.36.3`, and the
not-Running list is empty or only contains known-idle workloads (llama-cpp and
ComfyUI sit at `replicas: 0` by design — see
[gpu-scale-swap.md](../ai-gpu/gpu-scale-swap.md)).

**Stop if** any node is already NotReady or etcd is not healthy
(`talosctl -n <cp-ip> etcd status`). Fix that first; an upgrade will not.

### 2. Scan for APIs removed in Kubernetes 1.37

```bash
kubectl get --raw /metrics | grep apiserver_requested_deprecated_apis
```

**Expected:** no series whose `removed_release` label is `1.37`.

**Stop if** any appear — a removed API in use means workloads break the moment
the control plane rolls, and ArgoCD will not self-heal a manifest the API
server no longer accepts.

### 3. Enable pre-release versions on Omni, then sync

Add the flag to your `omni.env` (copy the block from `omni.env.example`) and
restart the server:

```bash
cd omni/omni && docker compose up -d
docker compose logs -f omni | head -50
```

**Expected:** Omni starts cleanly and the UI lists `v1.14.0-beta.1` as a
selectable Talos version. If it does not, the flag did not take — check for a
`docker compose` warning about an unset `VERSION_FLAGS` variable.

Then sync the cluster template:

```bash
omnictl cluster template sync -v -f omni/cluster-template/cluster-template.yaml
```

**Expected:** the diff shows the Talos and Kubernetes version changes plus the
new `ephemeral-allow-exec` patch, and Omni begins a rolling upgrade — control
planes one at a time to preserve etcd quorum, then workers.

**Stop if** the sync errors with an unknown-version message: that is the
pre-release flag, not the template.

### 4. Verify

```bash
# OS and kubelet rolled everywhere
kubectl get nodes -o custom-columns='NAME:.metadata.name,OS:.status.nodeInfo.osImage,KUBELET:.status.nodeInfo.kubeletVersion'

# CNI healthy — the component most at risk on a beta Kubernetes
cilium status
kubectl -n kube-system get pods -l k8s-app=cilium

# Storage healthy — the component most at risk from the noexec change
kubectl -n longhorn-system get nodes.longhorn.io
kubectl get pvc -A | grep -v Bound

# Time sync — NTS is newly on by default (see change 5)
talosctl -n <control-plane-ip> time

# etcd metrics still reachable on 2381 (see change 3)
kubectl -n monitoring exec -it <prometheus-pod> -- \
  wget -qO- 'http://localhost:9090/api/v1/targets?state=active' | grep -c kube-etcd
```

**Expected:** every node on Talos `v1.14.0-beta.1` / kubelet `v1.37.0-beta.0`;
`cilium status` all green; all Longhorn nodes `Ready`; no PVC outside `Bound`;
`talosctl time` returns a small offset without an NTS error; the `kube-etcd`
scrape job has one target per control-plane node.

Then confirm the GitOps layer reconverged:

```bash
kubectl get applications -n argocd -o wide | grep -v 'Synced.*Healthy'
```

**Expected:** empty. There are no manual DR gates left to except — CNPG was
retired on 2026-08-13 and every database is now a plain Postgres Deployment
that restores through kopiur like any other PVC.

### 5. Prove the rebuild path separately

The `noexec` change only lands on newly provisioned machines, so an in-place
upgrade proves nothing about DR. Before trusting this cluster's recovery story
again, reprovision one worker and confirm Longhorn comes back:

```bash
omnictl cluster machine delete <worker-machine-id> --timeout 15m
# wait for Ready, then:
kubectl -n longhorn-system get nodes.longhorn.io <node> -o yaml | grep -A5 conditions
kubectl -n longhorn-system logs -l app=longhorn-manager --tail=50 | grep -i 'permission denied\|exec format\|noexec'
```

**Expected:** the node rejoins with its disks registered and no `noexec` or
`permission denied` errors from the instance-manager. That is the direct proof
the `ephemeral-allow-exec` patch is doing its job.

---

## Rollback

There is no 1.14 patch to roll forward to, so rollback means going back to
1.13.7 / 1.36.3.

1. Revert the version pins (and only the version pins) in both templates:
   ```bash
   git revert <commit> -- omni/cluster-template/
   ```
   Keep `VERSION_FLAGS` set — an unused flag is harmless and you will likely
   retry.
2. Sync the template again. Omni drives a rolling downgrade.
3. **Kubernetes does not support downgrades.** If the control plane will not
   come back on 1.36.3, restore from the etcd snapshot taken in step 1:
   `talosctl -n <cp-ip> etcd recover --from /tmp/etcd-pre-1.14.snapshot` and
   follow [disaster-recovery.md](../../disaster-recovery.md).
4. If a single node is wedged rather than the cluster, reprovision it one at a
   time — this preserves etcd quorum for control planes:
   ```bash
   omnictl cluster machine delete <machine-id> --timeout 15m
   ```

Leaving `ephemeral-allow-exec` in place while on 1.13 is safe: 1.13 already
mounts `/var` without `noexec`, and `VolumeConfig.mount.secure` exists in 1.13
(it gated `nosuid`/`nodev` there). Do not revert that patch separately.

---

## Source of truth

- Version pins: `omni/cluster-template/cluster-template.yaml` and
  `cluster-template-threadripper-gpu-workers.yaml`
- Omni server flags: `omni/omni/omni.env.example` + `docker-compose.yml`
- Renovate tracking: `.github/renovate.json5` (Talos + Kubernetes custom managers)
- Upstream: [Talos v1.14 release notes](https://github.com/siderolabs/talos/releases/tag/v1.14.0-beta.1)
  · [What's new in Talos 1.14](https://docs.siderolabs.com/talos/v1.14/getting-started/what%27s-new-in-talos)
