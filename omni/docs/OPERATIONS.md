# Operations guide

This guide explains how to use `omnictl` to manage machine classes and clusters in your Omni + Proxmox environment.

## 1. Setup `omnictl`

`omnictl` is the CLI tool for interacting with the Omni API.

### Installation

Download the latest version from the [Omni releases page](https://github.com/siderolabs/omni/releases):

```bash
# Example for Linux AMD64
curl -L https://github.com/siderolabs/omni/releases/latest/download/omnictl-linux-amd64 -o omnictl
chmod +x omnictl
sudo mv omnictl /usr/local/bin/
```

### Configuration & fresh start authentication

If you just performed a Fresh Start, your previously registered CLI keys will not work. Generate a new configuration to register your local public key with the new Omni database:

```bash
# Generate a new config (it will trigger the OIDC flow)
omnictl config new --url https://omni.vanillax.me --insecure-skip-tls-verify > ~/.talos/omni/config
```

*Note: If you are using OIDC/Auth0, this will provide a link to open in your browser to complete the authentication.*

### Using a local config (optional)

If you prefer to keep your config relative to the project:
```bash
# Export the path
export OMNICONFIG=$(pwd)/omni/omni.config

# Then generate the config
omnictl config new --url https://omni.vanillax.me --insecure-skip-tls-verify > $OMNICONFIG
```

## 2. Managing machine classes

Machine classes define the virtual hardware specifications for your Proxmox VMs.

### Applying machine classes

Apply each machine class individually using the `-f` flag:

```bash
omnictl apply -f machine-classes/hp-sff-control-plane.yaml
omnictl apply -f machine-classes/hp-sff-worker.yaml
omnictl apply -f machine-classes/hp-micro-worker.yaml
omnictl apply -f machine-classes/threadripper-gpu-worker.yaml
```

### Verifying machine classes

List applied classes to confirm they are registered:

```bash
omnictl get machineclasses
```

## 3. Managing clusters

### Syncing cluster template

The cluster template defines the high-level configuration for your Kubernetes clusters.

```bash
cd cluster-template && omnictl cluster template sync -v -f cluster-template-prod-v2.yaml
```

### Creating a cluster

After you apply the machine classes, create a cluster through the Omni Web UI or the CLI:

1. **Via UI**: 
   - Navigate to `Clusters` -> `Create New Cluster`
   - Select your Machine Classes for Control Plane and Workers
2. **Via CLI**:
   Apply a cluster resource definition (see `cluster-template/` for templates).

## 4. Troubleshooting provisioning

If machines are not appearing in Proxmox:
1. Check the Proxmox Infrastructure Provider logs:
   ```bash
   docker compose logs -f omni-infra-provider-proxmox
   ```
2. Ensure the `storage_selector` in your Machine Class matches a storage pool name in Proxmox.
3. Verify that the Proxmox Provider has a valid Infrastructure Provider Key.

## 5. Host maintenance and upgrade rules

- **Reboot Proxmox hosts one at a time.** Most Longhorn volumes have one
  replica and there is one control plane, so two hosts down at once takes
  apps (or the Kubernetes API) offline. Before the next host, wait until
  `kubectl get nodes` is all `Ready` and Longhorn shows no degraded volumes.
- **After a host reboot, check that every Talos VM started.** A failed
  autostart is silent. On the Proxmox host:
  ```bash
  qm list               # every Talos VM should be "running"
  qm start <vmid>       # a stopped VM prints the real error here
  ```
  If it fails with `missing expected property 'subsystem-id'`, the VM's PCI
  resource mapping predates that field. Re-select the device in
  **Datacenter → Resource Mappings**, or add it on the CLI, keeping the
  mapping's other values (`pvesh get /cluster/mapping/pci/<name>`;
  `lspci -nnv -s <pci-address>` shows the subsystem ID):
  ```bash
  pvesh set /cluster/mapping/pci/<name> \
    --map 'node=<host>,path=<pci-address>,id=<vendor:device>,subsystem-id=<subvendor:subdevice>,iommugroup=<n>'
  ```
- **One stuck node stalls a whole Talos upgrade.** Omni upgrades one node at
  a time and waits for the cluster to be ready before moving on. A node that
  reports `failed to pull installer image: deadline exceeded` is usually
  waiting on the Image Factory to finish building a large schematic (for
  example the NVIDIA extensions); it retries and succeeds once the image
  exists. Omni's primary factory is the self-hosted one on the Pi
  (`--primary-factory-url=https://factory.vanillax.me:8443`), with
  `factory.talos.dev` as the secondary. The Pi needs about 20 minutes for the first
  build of a schematic, so installer pulls time out until the image is cached. Wait
  for the build; do not change the schematic to retry. Find the blocker with
  `omnictl get clustermachinestatus` and fix
  that node; never delete the control plane to "unstick" an upgrade.
- **A full EFI partition fails the install.** The installer writes a new boot image
  of about 575 MB to the node's EFI partition (2.1 GB on the GPU worker). If hand-saved
  boot images fill it, the upgrade fails with `no space left on device`. Lock the
  machine to stop Omni's retries, delete the extra images, then unlock it.
- **Treat kernel arguments as risky.** Cluster templates cannot set
  `kernelArgs` on machine sets that use a machine class, and Omni has an open
  reboot-loop bug with kernel arguments
  ([siderolabs/omni#2382](https://github.com/siderolabs/omni/issues/2382)).
  Try any kernel-argument change on one worker first.
- **Adding a disk to a VM is four steps**, not one: Proxmox storage on the host,
  the machine class, `qm set` on the running VM, then the cluster template and the
  Longhorn node. Walkthrough: [disk map](../../docs/domains/storage/disk-map.md#adding-a-disk-to-a-running-node).
- **hp-sff's second SSD belongs to etcd.** It holds only the control-plane VM
  (`hp-sff-cp-vmstore`); keep Longhorn disks off it
  ([why](threadripper-gpu-cluster.md#sizing)).

### A drain is stuck on a Longhorn volume

Longhorn's `node-drain-policy` is `block-for-eviction-if-contains-last-replica`.
Before a node can drain, Longhorn moves each single-replica volume to another disk
that matches the volume's disk tags. The GPU node's `ssd-flash` disk is the only
disk with the `flash` and `clone-ok` tags, and its `gpu-bulk` disk is the only one
with the `gpu-bulk` tag. Volumes with those tags have no other disk, so the drain
waits forever.

**Symptom.** The upgrade stops on the GPU node. `omnictl get clustermachinestatus <id> -o yaml`
shows `lastconfigerror: ... cordon/drain before reboot failed ... evicting pods/"instance-manager-..."`.
Replicas on the node show `evictionRequested: true`, and the new replicas never get a node:

```bash
kubectl -n longhorn-system get replicas.longhorn.io -o json \
  | jq -r '.items[] | select(.spec.nodeID=="") | .spec.volumeName'
# each volume's Scheduled condition says "tags not fulfilled"
```

**Fix.** Give the stuck tags a temporary second disk on a wired node, then remove them.

1. Add the tags to `hp-sff-ssd`. It is wired and has the most free space:
   ```bash
   kubectl -n longhorn-system patch nodes.longhorn.io talos-prod-cluster-v2-hp-sff-workers-h76ncc --type=json \
     -p='[{"op":"add","path":"/spec/disks/hp-sff-ssd/tags/-","value":"flash"},
          {"op":"add","path":"/spec/disks/hp-sff-ssd/tags/-","value":"gpu-bulk"}]'
   ```
2. Wait until no replica on the GPU node has `evictionRequested: true`. Longhorn also
   attaches detached volumes to move them. On 2026-11-10 about 150 GiB moved in
   45 minutes, about 48 MB/s in total and 26-51 MB/s per volume.
   Omni retries the drain by itself. Do not scale the workloads to 0: Longhorn must
   move a detached single-copy volume too, so the wait stays the same. Watch the copy:
   ```bash
   kubectl -n longhorn-system get engines.longhorn.io -o json \
     | jq -r '.items[] | select(.status.rebuildStatus | length > 0)
         | "\(.spec.volumeName) \(.status.rebuildStatus | map(.progress) | join(","))%"'
   ```
3. When the GPU node is `Ready` and uncordoned, restore the original tags:
   ```bash
   kubectl -n longhorn-system patch nodes.longhorn.io talos-prod-cluster-v2-hp-sff-workers-h76ncc --type=merge \
     -p='{"spec":{"disks":{"hp-sff-ssd":{"tags":["hp-sff-ssd"]}}}}'
   ```

Restoring the tags does not move a copy back. A `longhorn-flash` volume returns to
`ssd-flash` only when its pod runs on the GPU node, because best-effort data locality
copies to the pod's node. A pod on another node gets a local copy that fails with
"tags not fulfilled", and the data stays on `hp-sff-ssd`. On 2026-11-10 that happened
to all four PostHog volumes. List the volumes still outside `ssd-flash`:

```bash
kubectl -n longhorn-system get replicas.longhorn.io -o json | jq -r '.items[]
  | select(.spec.nodeID != "" and (.spec.diskPath | test("ssd-flash") | not))
  | .spec.volumeName' | sort -u > /tmp/off-flash
kubectl -n longhorn-system get volumes.longhorn.io -o json | jq -r --rawfile off /tmp/off-flash '.items[]
  | select((.spec.diskSelector // []) | index("flash")) | select(.metadata.name as $v | $off | contains($v))
  | .status.kubernetesStatus | "\(.namespace)/\(.pvcName)"'
```

Do not leave the tags in place. `hp-sff-ssd` is a consumer drive, and the
`flash` class holds the heavy writers.
