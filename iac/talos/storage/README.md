# Longhorn Disk Resizing Debugging Notes

This document summarizes the debugging process for an issue where Longhorn was not recognizing the increased size of a Proxmox virtual disk on a Talos worker node.

## Initial Problem

- Node: `192.168.10.200` (`talos-gpu-worker-00`)
- Issue: A secondary disk (`/dev/sdb`) attached to the VM was resized in Proxmox, but Longhorn did not reflect the new, larger size. The disk was intended for Longhorn storage, mounted at `/var/mnt/longhorn_sdb`.

## Debugging Steps & Findings

1.  **Initial Check (Node `192.168.10.200`)**:
    *   `talosctl -n 192.168.10.200 read /proc/partitions` showed:
        *   `/dev/sdb` (whole disk): ~456GB
        *   `/dev/sdb1` (partition): ~256GB
    *   `talosctl -n 192.168.10.200 mounts` showed:
        *   `/dev/sdb1` mounted at `/var/mnt/longhorn_sdb` with a capacity corresponding to ~256GB.
    *   **Conclusion**: The OS saw the larger disk (`sdb`) but was still using the old, smaller partition (`sdb1`).

2.  **Resolution Attempt (User Action)**:
    *   The user shut down the VM (`192.168.10.200`).
    *   In Proxmox, the virtual disk corresponding to `/dev/sdb` was detached/deleted and then re-added with the new (or intended) larger size (which turned out to be 512GB).
    *   The VM was started.

3.  **Post-Resolution Check (Node `192.168.10.200`)**:
    *   `talosctl -n 192.168.10.200 read /proc/partitions` showed:
        *   `/dev/sdb`: ~512GB
        *   `/dev/sdb1`: ~512GB
    *   `talosctl -n 192.168.10.200 mounts` showed:
        *   `/dev/sdb1` mounted at `/var/mnt/longhorn_sdb` with a capacity corresponding to ~512GB (reported as ~549GB by the filesystem, consistent with 512GiB).
    *   **Conclusion**: Detaching and re-adding the disk in Proxmox allowed Talos OS to correctly partition and format the disk to its full new size.

4.  **Verification on Other Worker Nodes**:
    *   **Node `192.168.10.201` (`talos-worker-01`)**:
        *   `/proc/partitions`: `/dev/sdb` ~512GB, `/dev/sdb1` ~512GB.
        *   `mounts`: `/dev/sdb1` mounted at `/var/mnt/longhorn_sdb` with ~512GB capacity.
    *   **Node `192.168.10.203` (`talos-worker-02`)**:
        *   `/proc/partitions`: `/dev/sdb` ~512GB, `/dev/sdb1` ~512GB.
        *   `mounts`: `/dev/sdb1` mounted at `/var/mnt/longhorn_sdb` with ~512GB capacity.
    *   **Conclusion**: These nodes were already configured correctly with ~512GB secondary disks.

5.  **Key Concepts Clarified**:
    *   `/dev/sdb`: Represents the entire block device (the virtual disk).
    *   `/dev/sdb1`: Represents the first partition on the `/dev/sdb` disk.
    *   It's standard for an OS to create a partition (e.g., `sdb1`) on a disk (`sdb`), even if that partition spans the entire disk. The filesystem is then created on the partition and mounted.
    *   The Talos machine configuration (`machine.disks`) for `/dev/sdb` with a `partitions.mountpoint` entry directs Talos to create a partition, format it, and mount it.

6.  **Final Confirmation**:
    *   For all checked worker nodes (`192.168.10.200`, `192.168.10.201`, `192.168.10.203`), the device `/dev/sdb1` is confirmed to be mounted at `/var/mnt/longhorn_sdb` and is reflecting the correct ~512GB size at the OS level.

## Summary
The issue on node `192.168.10.200` was resolved by detaching and re-adding the enlarged virtual disk in Proxmox. This allowed Talos to correctly re-partition and format the disk to its full new size. All checked worker nodes now show correct OS-level disk and partition sizes for Longhorn. If Longhorn UI still reports discrepancies, further investigation within Longhorn itself would be needed. 