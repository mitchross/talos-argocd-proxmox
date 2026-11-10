# Longhorn volumes and SELinux labels

This page explains why every Longhorn volume is mounted with an SELinux label, how to
check that a volume has the label, and what to do when it does not. You need it when a
volume shows `seclabel` in its mount options or when audit records fill the node logs.

Talos runs SELinux in permissive mode. SELinux blocks nothing, but it writes a record to
the audit log for every access that its policy does not allow. SELinux needs a label on
every file to make that check. Longhorn volumes get their label from a mount option, so a
pod can write to its volume without an audit record for each write.

## How it works

- Every Longhorn StorageClass, and so every Longhorn PV, carries
  `mountOptions: [context=system_u:object_r:ephemeral_t:s0]`. That is the label that the
  Talos container policy lets pods write to.
- The `mount` command inside the `longhorn-csi-plugin` container obeys SELinux options
  only when it can see `/etc/selinux/config`. Longhorn creates that DaemonSet itself, so a
  MutatingAdmissionPolicy adds a minimal config file to the container when the pod is
  created.
- The node applies the label when it mounts the volume. A volume that is already mounted
  keeps its old options until its node reboots or the volume moves to another node.

## Check a volume

Run this in a pod that uses the volume:

```bash
grep ' <mount-path> ' /proc/mounts
```

Expect `context="system_u:object_r:ephemeral_t:s0"` in the options. If you see `seclabel`
instead, the volume was mounted without the label.

Check the CSI plugin on a node:

```bash
kubectl -n longhorn-system exec <longhorn-csi-plugin-pod> -c longhorn-csi-plugin -- \
  python3 -c 'import ctypes; print(ctypes.CDLL("libselinux.so.1").is_selinux_enabled())'
```

Expect `1`. A result of `0` means the config file was not added. Delete the pod, so the
admission policy adds the file when the DaemonSet re-creates it.

## A volume still shows `seclabel`

The volume was mounted before its PV had the mount option, or by a CSI pod without the
config file. It gets the label at its next real mount. A real mount happens when the node
reboots or when the workload moves to another node. A pod restart on the same node is not
enough, because the node keeps the volume mounted.

## Audit records

The node-log pipeline drops `auditd` records
(`infrastructure/controllers/opentelemetry-operator/collector-agent.yaml`). An unlabeled
volume therefore costs no disk writes and no Loki space. The label stops the records where
they start.

## Files

| File | Purpose |
|---|---|
| `infrastructure/storage/longhorn/storageclass-*.yaml` | `context=` mount option on every Longhorn StorageClass |
| `infrastructure/storage/longhorn/csi-selinux-config.yaml` | ConfigMap and admission policy that let the CSI plugin apply the option |
| `infrastructure/storage/longhorn-selinux/` | Sync hook that adds the mount option to existing PVs |
