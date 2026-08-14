# Dell Longhorn Compute-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the Dell GPU worker from accepting Longhorn replicas while preserving its existing replicas for a controlled, separately executed evacuation.

**Architecture:** The Omni machine template remains the durable owner of the Dell disk declaration. The disk stays registered at `/var/lib/longhorn`, but `allowScheduling` becomes `false`; the canonical storage docs describe the one-time Longhorn eviction and its safety gates.

**Tech Stack:** Omni cluster templates, Talos Linux, Longhorn 1.12, Kubernetes, MkDocs

## Global Constraints

- GitOps owns persistent configuration; no live mutation is part of this pull request.
- Do not delete or recreate any PVC or Longhorn replica.
- Keep `defaultClassReplicaCount: 1` and `storageOverProvisioningPercentage: "200"` unchanged.
- Keep the Dell disk registered until its replica count reaches zero.
- Leave pull-request merging to the operator.

---

### Task 1: Declare Dell's Longhorn disk unschedulable

**Files:**
- Modify: `omni/cluster-template/cluster-template-threadripper-gpu-workers.yaml`

**Interfaces:**
- Consumes: Longhorn's `node.longhorn.io/default-disks-config` node annotation.
- Produces: A Dell disk definition whose `allowScheduling` field is `false` while its name, path, type, reservation, and tags remain unchanged.

- [x] **Step 1: Run the desired-state assertion and verify it fails**

  Run a YAML query that asserts the Dell annotation contains
  `"allowScheduling":false`. Expected result before the change: exit status 1.

- [x] **Step 2: Change only the Dell disk scheduling field and explanatory comment**

  Set `allowScheduling` to `false`. Explain that the disk remains registered so
  existing replicas can be evacuated safely, but rebuilt nodes cannot accept
  new replicas.

- [x] **Step 3: Re-run the desired-state assertion**

  Expected result: exit status 0, with the Threadripper disk declarations still
  containing `"allowScheduling":true`.

### Task 2: Align Longhorn and storage documentation

**Files:**
- Modify: `infrastructure/storage/longhorn/values.yaml`
- Modify: `infrastructure/storage/CLAUDE.md`
- Modify: `docs/storage-architecture.md`

**Interfaces:**
- Consumes: The Dell disk desired state from Task 1 and Longhorn's documented disabled-disk eviction behavior.
- Produces: One canonical operator runbook with prerequisites, actions, expected results, stop conditions, and rollback.

- [x] **Step 1: Correct local configuration comments**

  Describe Dell as a registered but unschedulable evacuation source. Preserve
  the existing one-replica and 200% overprovisioning decisions.

- [x] **Step 2: Update the storage rules table**

  State that Dell is not a Longhorn replica target and that local block storage
  remains on Threadripper.

- [x] **Step 3: Add the controlled evacuation runbook**

  Include read-only inventory and capacity checks, backup readiness, the UI
  disable-and-evict sequence, success criteria, stop conditions, and rollback.
  Explicitly defer per-application NFS/SMB migrations.

### Task 3: Validate and publish

**Files:**
- Verify: all files in Tasks 1 and 2

**Interfaces:**
- Consumes: The completed manifest and documentation changes.
- Produces: A draft pull request with reproducible validation evidence.

- [x] **Step 1: Validate configuration invariants**

  Assert Dell is unschedulable, all three Threadripper disk definitions remain
  schedulable, replica count remains one, and overprovisioning remains 200%.

- [x] **Step 2: Run repository validation**

  Render the Longhorn Kustomize application, parse the modified YAML, run the
  relevant repository checks, and run `mkdocs build --strict`.

- [x] **Step 3: Inspect the full diff**

  Confirm the diff contains no secrets, live-cluster mutations, PVC changes,
  replica-count changes, or unrelated files.

- [x] **Step 4: Commit and push**

  Stage only the approved files, create a terse commit, and push the
  `agent/dell-longhorn-compute-only` branch.

- [x] **Step 5: Open an unmerged draft pull request**

  Describe the incident root cause, desired-state change, deferred evacuation,
  rollback, and validation evidence. Do not merge it.
