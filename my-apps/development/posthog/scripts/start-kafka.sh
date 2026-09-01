#!/bin/sh
rpk redpanda config set redpanda.auto_create_topics_enabled true &&
rpk redpanda config set redpanda.empty_seed_starts_cluster true &&
exec rpk redpanda start \
  --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092 \
  --advertise-kafka-addr internal://kafka:9092,external://localhost:19092 \
  --pandaproxy-addr internal://0.0.0.0:8082,external://0.0.0.0:18082 \
  --advertise-pandaproxy-addr internal://kafka:8082,external://localhost:18082 \
  --schema-registry-addr internal://0.0.0.0:8081,external://0.0.0.0:18081 \
  --rpc-addr 0.0.0.0:33145 \
  --advertise-rpc-addr kafka:33145 \
  --smp 1 \
  --memory 1G \
  --reserve-memory 200M \
  --overprovisioned \
  --unsafe-bypass-fsync

