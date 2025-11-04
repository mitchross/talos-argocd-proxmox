# Talos Cluster Bootstrap

This directory contains scripts and templates to bootstrap a Talos cluster via Omni with proper hostnames and machine-specific configurations.

## Machine Inventory

Edit `machines.yaml` with your actual machine UUIDs:

```bash
# Get machine UUIDs from Omni
omnictl get machines -o json | jq -r '.[] | "\(.metadata.id) (\(.spec.managementaddress))"'
```

## Configuration Patches

- **Control Plane**: Basic Talos config (no special requirements)
- **GPU Workers**: NVIDIA runtime + kernel modules (from `gpu-workers.yaml`)
- **Regular Workers**: Longhorn volume config (from `non-gpu-workers.yaml`)

## Usage

### Step 1: Update Machine Inventory

```bash
vim machines.yaml
# Update UUIDs to match your machines
```

### Step 2: Generate Cluster Template

```bash
./generate-cluster-template.sh
```

This creates `cluster-template.yaml` with:
- Machine hostnames
- Role-specific patches (GPU/non-GPU)
- Longhorn storage configuration

### Step 3: Apply Template

```bash
omnictl cluster template sync -f cluster-template.yaml
```

Nodes will reconcile and reboot with new configurations.

### Step 4: Verify

```bash
# Check node names
kubectl get nodes

# Should show:
# talos-prod-control-01   Ready    control-plane
# talos-prod-control-02   Ready    control-plane
# talos-prod-control-03   Ready    control-plane
# talos-prod-worker-01    Ready    <none>
# talos-prod-worker-02    Ready    <none>
# talos-prod-gpu-worker-01 Ready   <none>
# talos-prod-gpu-worker-02 Ready   <none>
```

## Files

- `machines.yaml` - Machine inventory (edit this!)
- `generate-cluster-template.sh` - Main script to generate template
- `patches/` - Configuration patches for different machine types
  - `control-plane.yaml` - Control plane specific config
  - `gpu-worker.yaml` - GPU worker config with NVIDIA runtime
  - `regular-worker.yaml` - Non-GPU worker with Longhorn
