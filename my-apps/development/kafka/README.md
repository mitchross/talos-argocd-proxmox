# Kafka learning cluster

This is a real, single-broker KRaft cluster managed by Strimzi. It is sized for
the current one-worker homelab while keeping an expansion path:

- `KafkaNodePool` uses a dual-role broker/controller today.
- JBOD storage starts with one persistent Longhorn volume; additional disk IDs
  can be added without changing the immutable storage type.
- `deleteClaim: false` preserves data across normal operator reconciliation.
- `dev-events` is GitOps-managed by the Topic Operator; automatic topic
  creation is disabled so topic intent stays visible in Git.
- `kafka-demo-seed` writes and verifies five deterministic JSON events once;
  later Argo syncs detect `demo-001` and do not duplicate the sample set.
- Kafbat UI provides a read-only browser on the internal Gateway. It can inspect
  brokers, topics, partitions, messages, and consumer groups, but cannot mutate
  the cluster.

## Interactive demo

Open `https://kafka.vanillax.me` from the LAN or VPN, then select:

1. **dev-kafka**
2. **Topics**
3. **dev-events**
4. **Messages**

Choose `String` for the key and value deserializers. The initial log is a small
order lifecycle with stable keys, so it demonstrates both partition affinity
and event-driven state transitions:

| Event | Key | Meaning |
|---|---|---|
| `demo-001` | `order-1001` | Order accepted |
| `demo-002` | `order-1001` | Payment authorized |
| `demo-003` | `sku-keyboard` | Inventory reserved |
| `demo-004` | `order-1001` | Warehouse fulfilled the order |
| `demo-005` | `order-1001` | Shipment dispatched |

The four `order-1001` records hash to the same partition and retain order within
that partition. The inventory event deliberately uses a different key, showing
that Kafka does not promise ordering across partitions.

### Verify without the UI

The seed hook verifies all five IDs before Argo marks the sync successful:

```bash
kubectl -n kafka logs job/kafka-demo-seed
```

To inspect the current log directly with the broker's matching Kafka CLI:

```bash
kubectl -n kafka exec dev-kafka-dual-role-0 -c kafka -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server dev-kafka-kafka-bootstrap.kafka.svc:9092 \
  --topic dev-events \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true \
  --property key.separator=' | '
```

Expected result: five JSON records appear, including `demo-001` through
`demo-005`. This is intentionally sample data, but it is real Kafka data: the
topic log lives on the kopiur-protected broker PVC and is included in future
recovery drills.

## Expansion trigger

After there are at least three schedulable workers on distinct physical
failure domains, scale the node pool to three and raise the default, offsets,
and transaction-state replication factors to three (`min.insync.replicas: 2`).
Add topology spread/anti-affinity only when the labels describe real failure
domains.

## Disaster recovery

The deterministic Strimzi claim `data-0-dev-kafka-dual-role-0` has a daily
kopiur recovery point. Kafka uses kopiur's direct-PVC variant because Strimzi,
not Git, normally creates the claim. A namespace-scoped Sync Job waits for the
Restore's standard `Ready=True` condition before Argo advances from wave -1 to
the Strimzi resources in wave 0. The capacity and storage class are copied from
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
