# Official TrueNAS CSI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the undeployed Democratic CSI GitOps application with the
official TrueNAS CSI driver and an NFS-only canary rollout.

**Architecture:** Vendor the official v1.0.4 deployment resources under a new
Kustomize application, inject the API key through External Secrets, and expose
one retained NFS StorageClass. Existing Longhorn, static NFS CSI, and SMB CSI
resources remain untouched.

**Tech Stack:** Kubernetes 1.36, Talos 1.13, Argo CD, Kustomize, External
Secrets, Cilium, TrueNAS SCALE 26, TrueNAS CSI v1.0.4

---

### Task 1: Add repository contract validation

**Files:**
- Create: `scripts/validate-truenas-csi.sh`
- Modify: `.github/workflows/cluster-ci.yml`

- [ ] **Step 1: Write a validation script that expresses the migration contract**

The script must render `infrastructure/storage/truenas-csi`, then assert:

```bash
rg -q 'name: csi.truenas.io' "$rendered"
rg -q 'ghcr.io/truenas/truenas-csi:v1.0.4@sha256:' "$rendered"
rg -q 'provisioner: csi.truenas.io' "$rendered"
rg -q 'reclaimPolicy: Retain' "$rendered"
! rg -q 'org.democratic-csi|kind: StorageClass.*truenas-iscsi' "$rendered"
```

It must also verify the AppSet path, ExternalSecret key shape, Longhorn default
class, and Cilium TCP `443` allowance.

- [ ] **Step 2: Run the validator and confirm RED**

Run:

```bash
bash scripts/validate-truenas-csi.sh
```

Expected: failure because `infrastructure/storage/truenas-csi/` does not exist.

- [ ] **Step 3: Add the validator to Cluster CI**

Add a `truenas-csi-contract` job that installs Kustomize and executes the
script.

### Task 2: Add the official driver application

**Files:**
- Delete: `infrastructure/storage/democratic-csi/`
- Create: `infrastructure/storage/truenas-csi/kustomization.yaml`
- Create: `infrastructure/storage/truenas-csi/namespace.yaml`
- Create: `infrastructure/storage/truenas-csi/rbac.yaml`
- Create: `infrastructure/storage/truenas-csi/driver.yaml`
- Create: `infrastructure/storage/truenas-csi/configmap.yaml`
- Create: `infrastructure/storage/truenas-csi/externalsecret.yaml`

- [ ] **Step 1: Vendor upstream v1.0.4 workload resources**

Use `csi.truenas.io` and pin:

```yaml
image: ghcr.io/truenas/truenas-csi:v1.0.4@sha256:05b99f5ced0bda9ea832ae28d91c5acd4a0f61d6e3aa52d2ef0daebfe156a2f4
```

Preserve the upstream controller sidecars, privileged node plugin, host paths,
mount propagation, resource requests, and probes.

- [ ] **Step 2: Configure TrueNAS connectivity**

Create:

```yaml
data:
  truenasURL: wss://192.168.10.133/api/current
  truenasInsecure: "true"
  defaultPool: BigTank
  nfsServer: 192.168.10.133
  iscsiPortal: 192.168.10.133:3260
  iscsiIQNBase: iqn.2000-01.io.truenas
```

- [ ] **Step 3: Supply credentials with External Secrets**

Render Kubernetes Secret `truenas-api-credentials` with key `api-key`, sourced
from the dedicated 1Password item `truenas-csi`, property `apiKey`. A missing
item must fail closed instead of falling back to the old Democratic CSI key.

### Task 3: Add NFS provisioning policy

**Files:**
- Create: `infrastructure/storage/truenas-csi/storageclass.yaml`
- Create: `infrastructure/storage/truenas-csi/volumesnapshotclass.yaml`

- [ ] **Step 1: Define the retained NFS class**

```yaml
provisioner: csi.truenas.io
parameters:
  protocol: nfs
  pool: BigTank
  datasetPath: k8s/nfs/v
  compression: LZ4
  sync: STANDARD
  nfs.networks: 192.168.10.0/24
  nfs.mountOptions: hard,nfsvers=4.1,tcp,rsize=1048576,wsize=1048576,noatime,nconnect=16
reclaimPolicy: Retain
volumeBindingMode: Immediate
allowVolumeExpansion: true
```

- [ ] **Step 2: Define the snapshot class**

Use driver `csi.truenas.io` and deletion policy `Retain`.

### Task 4: Switch Argo CD and networking atomically

**Files:**
- Modify: `infrastructure/controllers/argocd/apps/appsets/infrastructure-appset.yaml`
- Modify: `infrastructure/networking/cilium/policies/block-lan-access.yaml`

- [ ] **Step 1: Replace the AppSet directory**

Replace `infrastructure/storage/democratic-csi` with
`infrastructure/storage/truenas-csi`.

- [ ] **Step 2: Permit the management API**

Add TCP `443` to the existing TrueNAS egress port list. Do not add TCP `3260`.

### Task 5: Add a disposable canary

**Files:**
- Create: `infrastructure/storage/truenas-csi/canary/nfs-canary.yaml`
- Create: `infrastructure/storage/truenas-csi/CANARY.md`

- [ ] **Step 1: Define manual canary resources**

Create a namespace, 1 GiB RWX PVC, root writer, UID/GID 1000 writer, and second
reader pod. Keep these resources out of the parent Kustomization.

- [ ] **Step 2: Document the test matrix and cleanup**

Include commands for binding, cross-node reads, ownership inspection, resize,
snapshot, clone, retained PV cleanup, and rollback.

### Task 6: Verify

- [ ] **Step 1: Run the contract validator**

```bash
bash scripts/validate-truenas-csi.sh
```

Expected: PASS.

- [ ] **Step 2: Render and validate schemas**

```bash
kustomize build infrastructure/storage/truenas-csi > /tmp/truenas-csi.yaml
kubeconform -summary -ignore-missing-schemas /tmp/truenas-csi.yaml
```

Expected: successful render and zero invalid resources.

- [ ] **Step 3: Run repository validation**

```bash
bash scripts/validate-argocd-apps.sh
```

Expected: zero errors.

- [ ] **Step 4: Run API-server dry-run**

Create the namespace in dry-run input first, then validate the remaining
rendered resources with server-side dry-run. No live resources or PVCs are
created during repository implementation.
