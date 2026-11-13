# Omni template, node resets and Longhorn

## Omni cluster template

- A set takes `machines:` OR `machineClass`, never both.
- Moving a worker into the control plane: delete its Workers set and move its patches/extensions into its `kind: Machine` doc, with the full extension list there. Move host-specific set labels (zone) into that host's Machine doc. Omni's per-machine vs per-set extension merge is undocumented, so trust `omnictl cluster template diff`.
- Never leave a comment-only YAML document between two `---` lines: `omnictl cluster template diff` fails with "unexpected node kind 8, expecting mapping" while pyyaml and CI pass. After editing, check every `safe_load_all` document is a dict and remove stray `---`/comment pairs left by cutting blocks.
- Reading a template diff the user pastes, confirm: (1) existing control-plane MachineSetNodes are not deleted, (2) moved machines flip role-worker to role-controlplane, (3) each Machine's ExtensionsConfigurations list is complete (e.g. NPU extension kept), (4) per-set patches reappear under new IDs with the same content, (5) old worker sets/patches are the only deletions.
- Control-plane HA does not cover management-plane single points of failure (the Pi running Omni/booter): say so, and add a pre-sync step to export break-glass kubeconfig/talosconfig (check `omnictl ... --help` for the flag) and copy the Omni state backup off the Pi.

## Before a node reset or sync

- List every pod on the affected nodes (`kubectl get pods -A -o wide --field-selector spec.nodeName=<n>`): the Hermes pod itself may sit there, and its volume may have one replica. Make the replica-raise patch a hard prerequisite, ahead of the sync.
- Count Longhorn replicas on the node (`replicas.longhorn.io` by `spec.nodeID`) and name the stateful pods that will go down.
- Quote node capacity only from `kubectl get nodes -o custom-columns=...capacity.memory,allocatable.memory` and `kubectl top nodes`, never from a screenshot or older notes; wrong sizing claims erode trust in the whole plan.

## Longhorn

- `numberOfReplicas` is fixed per volume at creation; StorageClass default changes don't touch existing volumes. Check single-writer apps for 1-replica volumes.
- `defaultSettings` in `infrastructure/storage/longhorn/values.yaml` do reach live `settings.longhorn.io`; confirm by comparing another setting's live value.
- Keep `allowRecurringJobWhileVolumeDetached: "false"`: with `true`, a `filesystem-trim` job attaches detached volumes without a mounted filesystem and the whole job fails with `Action [trimFilesystem] not available`.
- Diagnose a failing recurring job: pull its pod logs from Loki (`k8s_pod_name=~"<job>-.*"`), extract the failing `pvc-…` names, compare with `volumes.longhorn.io` `.status.state`. Prove a fix by running it once: `kubectl -n longhorn-system create job <name>-verify --from=cronjob/<job>`.

## Longhorn disk tags

- Never leave a disk tag on only one disk. A class whose `diskSelector` matches one disk pins every volume to one node, and that node's reboot waits on copies. Rule and current tags: `docs/domains/storage/disk-map.md`.
- Record every disk tag in the Omni template's `default-disks-config` too. Longhorn reads it only when a node first registers, so a rebuilt node loses a tag that was only patched live.
- Adding a tag to a second disk changes where new volumes of every class with that selector land. Check each class that selects the tag before the patch, not after.
- A `diskSelector` with several tags needs all of them on one disk. Use a combined selector (e.g. `flash,clone-ok`) to pin a benchmark volume to one disk; never repoint a shared class for it.
- Raise copies on an existing volume per volume (`numberOfReplicas`, `dataLocality: disabled`). Delete the old replica only after the volume is `healthy` with the new copy running, one volume at a time.
- Use one writer for live Longhorn changes. When another agent runs replica moves, hold benchmarks or copies that use the same disks until it reports done.
