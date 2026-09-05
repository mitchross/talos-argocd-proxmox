# Is the telemetry pipeline itself working?

This optional, post-Prometheus overlay observes the OTel agents and gateway. It
must not move Prometheus CRDs or monitoring resources into the bootstrap operator
application. The collectors, storage, retention and replica counts are unchanged.

The ServiceMonitor selects the operator's monitoring-service label by existence,
not by a hard-coded label value. Target relabeling identifies the homelab stack
and the expected `otel-agent`/`otel-gateway` monitoring Services. Verify these
names against the rendered operator output when changing collector names.

## What the alerts mean

- **TargetsMissing:** no discovered target for a required collector role. Check
  ServiceMonitor, Service labels/ports, endpoints, and Prometheus selection. This
  detects the case where `up == 0` cannot fire because `up` does not exist.
- **TargetDown:** a discovered endpoint is not scrapeable. Check its pod and
  networking. Other pipeline rules cannot establish health for this target.
- **Backpressure:** a named pod is refusing logs/traces or failing exports. This
  is not automatically permanent data loss: retries can succeed. Inspect the
  queue, backend status, and receiver/exporter together. Both cumulative-counter
  naming forms (with or without `_total`) are covered across collector versions.
- **QueueNearCapacity:** a named exporter queue is above 80% for ten minutes.
  Check whether the downstream backend is slow/unavailable before increasing
  buffers. Zero-capacity queues are excluded rather than dividing by zero.

PromQL to start an investigation:

```promql
up{telemetry_stack="homelab"}
otelcol_exporter_queue_size{telemetry_stack="homelab"}
otelcol_exporter_queue_capacity{telemetry_stack="homelab"}
```

Collector and Loki pod logs are deliberately excluded from the Loki ingestion
pipeline to avoid recursive failure storms. Use Kubernetes pod logs for these
components (including through a read-only investigation agent). Do not interpret
an empty Loki query for them as "no errors".

## Verification and limitations

The workflow extracts `spec.groups` from the actual PrometheusRule and tests it
with promtool. Tests cover a healthy pipeline, absent discovery, trace-export
failures, legacy log counter names, full queues, and zero-capacity queues. No
parallel manually maintained copy of the rules is used.

After sync, verify one gateway target and the expected agent targets exist. Use
a disposable telemetry event to check end-to-end delivery. These rules cannot
detect silent data loss inside an application SDK, prove trace completeness,
prove zero event loss, or alert when Prometheus/the entire cluster is down.
That last case still requires an outside observer.

Rollback is a Git revert of this overlay change. It changes observation only,
not the telemetry data path, storage, or application workloads.
