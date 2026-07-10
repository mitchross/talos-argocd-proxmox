# Kafka learning cluster

This is a real, single-broker KRaft cluster managed by Strimzi. It is sized for
the current one-worker homelab while keeping an expansion path:

- `KafkaNodePool` uses a dual-role broker/controller today.
- JBOD storage starts with one persistent Longhorn volume; additional disk IDs
  can be added without changing the immutable storage type.
- `deleteClaim: false` preserves data across normal operator reconciliation.
- `dev-events` is GitOps-managed by the Topic Operator; automatic topic
  creation is disabled so topic intent stays visible in Git.

## Expansion trigger

After there are at least three schedulable workers on distinct physical
failure domains, scale the node pool to three and raise the default, offsets,
and transaction-state replication factors to three (`min.insync.replicas: 2`).
Add topology spread/anti-affinity only when the labels describe real failure
domains.

## Disaster recovery

The deterministic Strimzi claim `data-0-dev-kafka-dual-role-0` has a daily
kopiur recovery point. Kafka uses kopiur's direct-PVC variant because Strimzi,
not Git, normally creates the claim; the Argo health gate ensures restoration
finishes before Kafka mounts it. The capacity and storage class are copied from
the node-pool declaration with Kustomize replacements so the live and restore
contracts cannot drift independently.

The canonical backup mechanics and safety contract live in
[`docs/domains/storage/kopiur-backup-architecture.md`](../../../docs/domains/storage/kopiur-backup-architecture.md).
This file documents only Kafka's operator-owned-PVC exception.

This is a single-volume crash-consistent recovery point, not replication: both
Kafka logs and KRaft metadata share volume 0, and recovery resembles a sudden
power loss at the snapshot boundary. Run a real produce → snapshot → delete →
rebuild → consume drill before calling the path proven. When a second cluster
exists, Kafka-native replication such as MirrorMaker 2 is still the stronger
DR design for important streams.
