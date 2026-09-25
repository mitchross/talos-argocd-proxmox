# Longhorn volumes and SELinux labels

Talos runs SELinux in permissive mode: nothing is blocked, but any access that
the policy doesn't allow is written to the audit log. Every file needs a label
for that check. Longhorn volumes get theirs from a mount option, so pods can
write to them without generating an audit line per write.

## How it works

- Every Longhorn StorageClass (and so every Longhorn PV) carries
  `mountOptions: [context=system_u:object_r:ephemeral_t:s0]`, the pod-writable
  label from Talos's container policy.
- The `mount` inside the `longhorn-csi-plugin` container only honours SELinux
  options when it can see `/etc/selinux/config`. Longhorn creates that DaemonSet
  itself, so a MutatingAdmissionPolicy adds a minimal config file to the
  container when the pod is created.
- The label is applied when a volume is mounted on a node (staged). A volume
  already mounted keeps whatever it had until its node reboots or it moves.

## Check a volume

In a pod that uses the volume:

```bash
grep ' <mount-path> ' /proc/mounts
```

Expected: `context="system_u:object_r:ephemeral_t:s0"` in the options.
`seclabel` instead means the volume was mounted without the label.

Check the CSI plugin on a node:

```bash
kubectl -n longhorn-system exec <longhorn-csi-plugin-pod> -c longhorn-csi-plugin -- \
  python3 -c 'import ctypes; print(ctypes.CDLL("libselinux.so.1").is_selinux_enabled())'
```

Expected: `1`. `0` means the config file wasn't injected; delete the pod so it
is re-created through the admission policy.

## A volume still shows `seclabel`

It was mounted before the fix or by a CSI pod without the config. It picks up
the label at its next real mount: a node reboot, or the workload moving to
another node. Restarting the pod on the same node is not enough, because the
node keeps the volume mounted.

## Audit noise

The node-log pipeline drops `auditd` records
(`infrastructure/controllers/opentelemetry-operator/collector-agent.yaml`), so
unlabeled volumes don't cost disk writes or Loki space. Labels stop the records
at the source.

## Files

| File | Purpose |
|---|---|
| `infrastructure/storage/longhorn/storageclass-*.yaml` | `context=` mount option on every Longhorn StorageClass |
| `infrastructure/storage/longhorn/csi-selinux-config.yaml` | ConfigMap + admission policy that let the CSI plugin apply it |
| `infrastructure/storage/longhorn-selinux/` | Sync hook that adds the mount option to existing PVs |
