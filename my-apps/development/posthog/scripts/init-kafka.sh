#!/bin/sh
set -x
echo "Waiting for Kafka broker to accept connections..."
TIMEOUT=120
ELAPSED=0
until rpk topic list --brokers kafka:9092 2>/dev/null; do
    echo "Kafka broker not ready yet (elapsed: ${ELAPSED}s)..."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "Timeout waiting for Kafka broker after ${TIMEOUT}s"
        exit 1
    fi
done
echo "Kafka broker is accepting requests, creating topics..."
for topic in events_plugin_ingestion events_plugin_ingestion_ai exceptions_ingestion clickhouse_events_json session_recording_events session_recording_events2 session_recording_snapshot_item_events clickhouse_app_metrics2 logs_ingestion ai_events_ingestion clickhouse_ai_events_json; do
    if rpk topic create "$topic" --brokers kafka:9092 -p 1 -r 1 2>&1; then
        echo "Topic $topic created successfully"
    else
        if rpk topic list --brokers kafka:9092 | grep -q "$topic"; then
            echo "Topic $topic already exists, continuing"
        else
            echo "Failed to create topic $topic"
            exit 1
        fi
    fi
done
echo "Topics ready"

