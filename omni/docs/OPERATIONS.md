# Operations Guide

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

### Configuration & Fresh Start Authentication

If you just performed a **Fresh Start**, your previously registered CLI keys will not work. You must generate a new configuration to register your local public key with the new Omni database:

```bash
# Generate a new config (it will trigger the OIDC flow)
omnictl config new --url https://omni.vanillax.me --insecure-skip-tls-verify > ~/.talos/omni/config
```

*Note: If you are using OIDC/Auth0, this will provide a link to open in your browser to complete the authentication.*

### Using a Local Config (Optional)

If you prefer to keep your config relative to the project:
```bash
# Export the path
export OMNICONFIG=$(pwd)/omni/omni.config

# Then generate the config
omnictl config new --url https://omni.vanillax.me --insecure-skip-tls-verify > $OMNICONFIG
```

## 2. Managing Machine Classes

Machine classes define the virtual hardware specifications for your Proxmox VMs.

### Applying Machine Classes

Apply each machine class individually using the `-f` flag:

```bash
omnictl apply -f machine-classes/hp-sff-control-plane.yaml
omnictl apply -f machine-classes/hp-sff-worker.yaml
omnictl apply -f machine-classes/hp-elite-worker.yaml
omnictl apply -f machine-classes/dell-worker.yaml
omnictl apply -f machine-classes/hp-micro-worker.yaml
omnictl apply -f machine-classes/threadripper-gpu-worker.yaml
```

### Verifying Machine Classes

List applied classes to ensure they are registered:

```bash
omnictl get machineclasses
```

## 3. Managing Clusters

### Syncing Cluster Template

The cluster template defines the high-level configuration for your Kubernetes clusters.

```bash
cd cluster-template && omnictl cluster template sync -v -f cluster-template-prod-v2.yaml
```

### Creating a Cluster

Once machine classes are applied, you can create a cluster through the Omni Web UI or via CLI:

1. **Via UI**: 
   - Navigate to `Clusters` -> `Create New Cluster`
   - Select your Machine Classes for Control Plane and Workers
2. **Via CLI**:
   Apply a cluster resource definition (see `cluster-template/` for templates).

## 4. Troubleshooting Provisioning

If machines are not appearing in Proxmox:
1. Check the Proxmox Infrastructure Provider logs:
   ```bash
   docker compose logs -f omni-infra-provider-proxmox
   ```
2. Ensure the `storage_selector` in your Machine Class matches a storage pool name in Proxmox.
3. Verify that the Proxmox Provider has a valid Infrastructure Provider Key.

## 5. Host Maintenance and Upgrade Rules

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
  exists. Find the blocker with `omnictl get clustermachinestatus` and fix
  that node; never delete the control plane to "unstick" an upgrade.
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
   attaches detached volumes to move them, so expect about 200 GiB and 45 minutes.
   Omni retries the drain by itself.
3. When the GPU node is `Ready` and uncordoned, restore the original tags:
   ```bash
   kubectl -n longhorn-system patch nodes.longhorn.io talos-prod-cluster-v2-hp-sff-workers-h76ncc --type=merge \
     -p='{"spec":{"disks":{"hp-sff-ssd":{"tags":["hp-sff-ssd"]}}}}'
   ```

Expected result: `longhorn-flash` volumes move back to `ssd-flash` through
best-effort data locality, and the rest move back when hp-sff drains.
Do not leave the tags in place: `hp-sff-ssd` is a consumer drive, and the
`flash` class holds the heavy writers.
