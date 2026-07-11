#!/usr/bin/env bash
set -euo pipefail

bootstrap="dev-kafka-kafka-bootstrap.kafka.svc:9092"
topic="dev-events"
producer="/opt/kafka/bin/kafka-console-producer.sh"
consumer="/opt/kafka/bin/kafka-console-consumer.sh"
events="/demo/events.jsonl"

echo "Waiting for ${topic} on ${bootstrap}"
for attempt in {1..24}; do
  if /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "${bootstrap}" \
    --describe \
    --topic "${topic}"; then
    break
  fi
  if [[ "${attempt}" == "24" ]]; then
    echo "${topic} was not ready after 120 seconds" >&2
    exit 1
  fi
  sleep 5
done

# The marker makes repeated Argo syncs idempotent. Kafka is an append-only log,
# so blindly producing on every sync would make the learning data noisy.
existing="$(timeout 15 "${consumer}" \
  --bootstrap-server "${bootstrap}" \
  --topic "${topic}" \
  --from-beginning \
  --max-messages 100 \
  --property print.key=true \
  --property key.separator='|' 2>/dev/null || true)"

if grep -q '"event_id":"demo-001"' <<<"${existing}"; then
  echo "Demo event set already exists; skipping produce"
else
  echo "Producing five deterministic order-lifecycle events"
  "${producer}" \
    --bootstrap-server "${bootstrap}" \
    --topic "${topic}" \
    --property parse.key=true \
    --property key.separator='|' \
    < "${events}"
fi

echo "Verifying all five event IDs can be consumed"
observed="$(timeout 20 "${consumer}" \
  --bootstrap-server "${bootstrap}" \
  --topic "${topic}" \
  --from-beginning \
  --max-messages 100 2>/dev/null || true)"

for id in demo-001 demo-002 demo-003 demo-004 demo-005; do
  grep -q "\"event_id\":\"${id}\"" <<<"${observed}"
done
echo "Verified demo-001 through demo-005"
