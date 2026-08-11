# Dell Longhorn Compute-Only Design

**Status:** Approved for implementation

## Problem

The Dell GPU worker has a 100 GiB Talos system disk registered as a schedulable
Longhorn disk. Longhorn placed the only replica of 18 single-replica volumes on
that disk. When its instance manager lost those replicas, the disk's declared
PVC allocation was slightly above the 200% scheduling budget. Longhorn could
not schedule the replacement needed for salvage even though the filesystem had
free bytes, so the affected workloads remained unable to mount their PVCs.

The Dell worker crosses the yard Wi-Fi media bridge and has no trustworthy
dedicated storage device. Its useful role is compute: stateless workloads and
workloads whose persistence is supplied by NFS or SMB. It must not be a target
for Longhorn replicas.

## Decision

Keep the Dell Longhorn disk registered, but declare it with
`allowScheduling: false` in the Omni cluster template. Keeping the disk
registered allows existing replicas to remain readable during a controlled
evacuation. Disabling scheduling prevents a rebuilt Dell worker from accepting
new replicas.

After the desired state is merged, perform the existing-node transition as an
operator-controlled action:

1. Verify the affected volumes are healthy and protected workloads have recent
   Kopiur snapshots.
2. Disable scheduling on the existing Dell Longhorn disk.
3. Request disk eviction. Longhorn rebuilds each replacement on a suitable
   Threadripper disk before deleting the Dell replica, preserving the configured
   replica count during the move.
4. Wait for the Dell disk's replica count to reach zero and verify all active
   volumes are healthy.
5. Clear the eviction request while leaving disk scheduling disabled.

This follows Longhorn's documented disabled-disk eviction flow:
<https://longhorn.io/docs/1.12.0/nodes-and-volumes/nodes/disks-or-nodes-eviction/>.

## Scope

This change:

- changes the Dell default disk declaration from schedulable to unschedulable;
- updates the Longhorn configuration comments and storage documentation to
  describe Dell as compute-only for Longhorn;
- documents preconditions, success checks, stop conditions, and rollback for
  the one-time evacuation.

This change deliberately does not:

- delete, recreate, or move a live PVC or replica as part of Argo CD sync;
- change the cluster-wide Longhorn replica count from one;
- raise the storage overprovisioning percentage;
- migrate individual application PVCs to NFS or SMB;
- add broad pod scheduling rules across unrelated applications.

Application-level enforcement of "Dell only runs stateless or remote-file
storage workloads" is a separate inventory and migration phase. Some workloads,
including hardware-bound services, need an explicit decision between remote
file storage and placement on the Threadripper worker.

## Alternatives Considered

### Keep Dell schedulable and increase its logical budget

Rejected. This makes the immediate scheduler condition disappear but continues
placing sole replicas on an unreliable, undersized system disk. It preserves
the failure mode.

### Add a second replica to every volume

Rejected for this change. Synchronous replicas across the Wi-Fi media bridge
change latency and failure behavior for every default-class PVC. A second
replica is useful only after adding another reliable wired storage worker or
selectively validating an appropriate path.

### Remove the Dell disk immediately

Rejected. Removing a disk that still owns the only replica of a volume risks
data loss. The disk stays registered until controlled eviction reaches zero
replicas.

## Validation

Static validation must prove that the Dell disk renders with
`allowScheduling: false`, the Threadripper disks remain schedulable, YAML is
valid, repository policy checks pass, and the documentation site builds
strictly. Before the live evacuation, read-only cluster checks must prove the
Dell replica inventory, target-disk scheduling headroom, volume health, and
Kopiur snapshot readiness.

## Rollback

Before or during eviction, set `Eviction Requested` back to `false`; Longhorn
leaves remaining replicas in place. Do not re-enable Dell scheduling merely to
cancel an eviction. Reverting the Git commit changes future Dell provisioning
back to schedulable, but that is an emergency rollback only because it restores
the incident's unsafe placement policy.
