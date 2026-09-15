# Node crash logs

Grafana **Nodes / Crash logs** (`/d/node-crash-logs`) combines node logs,
availability, reboot timestamps, OOM counters, and log-delivery health.
Select a physical host or Talos node; search for `panic`, `watchdog`, `oom`,
`I/O error`, or `shutdown`. Journal fields, including `_BOOT_ID` and
`_SYSTEMD_UNIT`, remain attached to each physical-host log record.

Talos sends service and kernel JSON lines to its local OTEL agent on
`127.0.0.1:6050`. The agent labels the originating node and sends directly to
Loki. Physical Linux hosts use the upstream OTEL Contrib Debian package,
reading the system journal as an unprivileged user in `systemd-journal`.
The existing Ansible inventory covers five Proxmox hosts and the management
Pi. TrueNAS is an appliance and is not changed by this playbook.

## Deploy after merge

Argo deploys the Collector, Loki retention, Grafana dashboard and alerts.
Then enable logging on all Talos machine sets from the repository root:

```sh
omnictl cluster template sync -f omni/cluster-template/cluster-template-prod-v2.yaml
```

Install host logging through the committed playbook, one host at a time
(`serial: 1`). This installs a service and configures journald; it does not
reboot hosts or change VMs. Existing SSH and sudo access are required:

```sh
ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/logging-playbook.yaml --syntax-check
ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/logging-playbook.yaml --limit shed
ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/logging-playbook.yaml --limit gpu,dell,sff,elite,pi
```

Confirm advancing `talos-system` and `host-journal` streams for every expected
node in Grafana. Host Collector metrics listen on the host LAN IP at `:8889`;
`physical-logs` must be up. Existing `PrometheusTargetDown` alerts cover hosts
whose collectors have not been installed. The log receiver is loopback-only;
the existing Loki LAN endpoint `192.168.10.48` is not a public route.

## What survives an outage

Node streams have seven-day Loki retention; application logs retain 24 hours.
Physical journals retain up to seven days/256 MiB locally and sync every five
seconds. Persistent export queues hold up to 32 MiB of serialized Talos logs
per node and 64 MiB per physical host, plus database overhead. Queues retry
network/server failures and survive Collector restarts; they are finite and
depend on writable local disks. Permanent Loki rejections can still drop logs.

This captures logs, not memory dumps. Sudden power loss or a hard lock can
prevent the final message from being written or sent. Talos logging starts
when the node-local Collector is available, so early boot is not guaranteed.
Use the physical journal and reboot history to distinguish a host reboot from
a guest restart. A reboot alert does not establish a crash or its cause.

Rollback through a PR: remove the two Omni logging patches and the node log
pipeline, then sync the template. Stop/disable `otelcol-contrib` on physical
hosts through Ansible; remove only this playbook's journald drop-in if reverting
its retention. Keep the existing pod-log pipeline and host metrics exporters.

Sources: [Talos logging](https://docs.siderolabs.com/talos/v1.10/configure-your-talos-cluster/logging-and-telemetry/logging),
[Talos 1.14 kernel-log configuration](https://github.com/siderolabs/talos/blob/v1.14.0/website/content/v1.14/reference/configuration/runtime/kmsglogconfig.md),
[OTEL journal receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.158.0/receiver/journaldreceiver),
[persistent export queues](https://github.com/open-telemetry/opentelemetry-collector/blob/v0.158.0/exporter/exporterhelper/README.md).
