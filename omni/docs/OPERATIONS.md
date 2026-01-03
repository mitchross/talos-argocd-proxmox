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
omnictl apply -f machine-classes/control-plane.yaml
omnictl apply -f machine-classes/worker.yaml
omnictl apply -f machine-classes/gpu-worker.yaml
omnictl apply -f machine-classes/test-multi-disk.yaml
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
   Apply a cluster resource definition (see `examples/` for templates).

## 4. Troubleshooting Provisioning

If machines are not appearing in Proxmox:
1. Check the Proxmox Infrastructure Provider logs:
   ```bash
   docker compose logs -f omni-infra-provider-proxmox
   ```
2. Ensure the `storage_selector` in your Machine Class matches a storage pool name in Proxmox.
3. Verify that the Proxmox Provider has a valid Infrastructure Provider Key.
