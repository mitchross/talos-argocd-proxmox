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
cd cluster-template && omnictl cluster template sync -v -f cluster-template.yaml
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
- **hp-sff's second SSD belongs to etcd.** It holds only the control-plane VM
  (`hp-sff-cp-vmstore`); keep Longhorn disks off it
  ([why](threadripper-gpu-cluster.md#sizing)).
