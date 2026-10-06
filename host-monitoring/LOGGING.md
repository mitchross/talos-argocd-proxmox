# Node crash logs

Grafana **Nodes / Crash logs** (`/d/node-crash-logs`) combines node logs,
availability, reboot timestamps, OOM counters, and log-delivery health.
Select a physical host or Talos node; search for `panic`, `watchdog`, `oom`,
`I/O error`, or `shutdown`. Journal fields, including `_BOOT_ID` and
`_SYSTEMD_UNIT`, remain attached to each physical-host log record.

Logging is an optional add-on. Talos and Proxmox boot and run without
Collectors, Loki, or Grafana. A Talos cluster rebuild keeps the physical-host
collectors installed; the normal Omni template restores Talos forwarding and
Argo redeploys cluster monitoring. No host playbook rerun is needed unless
the host OS or logging configuration changes. While Loki is down, local
queues and journals retain what fits; older logs can be lost.

Talos sends service and kernel JSON lines to its local OTEL agent on
`127.0.0.1:6050`. The agent labels the originating node and sends directly to
Loki. Physical Linux hosts use the upstream OTEL Contrib Debian package,
reading the system journal as an unprivileged user in `systemd-journal`.
The existing Ansible inventory covers five Proxmox hosts and the management
Pi. TrueNAS is an appliance and is not changed by this playbook.

## Initial enablement

Argo deploys the Collector, Loki retention, Grafana dashboard and alerts.
For an existing cluster, sync the updated Omni template once to enable Talos
forwarding. Fresh rebuilds get this configuration through their normal
template sync:

```sh
omnictl cluster template sync -f omni/cluster-template/cluster-template-prod-v2.yaml
```

Optionally install host logging once through the committed playbook, one host
at a time (`serial: 1`). This installs a service and configures journald; it does not
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

## Crash capture for hard locks

The journal cannot record a freeze that also stops the disk and the
Collector. [crash-capture-playbook.yaml](crash-capture-playbook.yaml) adds
three paths that work without them:

| Layer | What it does | Where to read it |
| --- | --- | --- |
| Lockup → panic | `softlockup_panic`, `hardlockup_panic`, `panic_on_oops`, `panic=10`: a silent freeze becomes a panic and reboots after 10 s | — |
| EFI pstore | On panic the kernel saves its last messages in UEFI variables; `systemd-pstore` copies them to `/var/lib/systemd/pstore/` and the journal on the next boot | Grafana **Nodes / Crash logs**, search `pstore` |
| netconsole | Each kernel line leaves the NIC immediately as UDP | Pi `192.168.10.15:/var/log/netconsole/<host-ip>.log` |
| Hardware watchdog | `iTCO_wdt` + systemd `RuntimeWatchdogSec=60s` resets a host whose kernel stops running | — |

Run it on one host at a time:

```sh
ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/crash-capture-playbook.yaml --limit shed
```

Expected: `sysctl kernel.panic` prints `10`, `/dev/watchdog0` exists, and
`systemctl status netconsole` is active. The playbook refuses a host where
Proxmox HA's `watchdog-mux` is running, because both need `/dev/watchdog`.

netconsole only attaches when every port of `vmbr0` supports netpoll. A VM NIC
with `firewall=1` adds an `fwpr` veth that does not, and `dmesg` reports
`Netpoll setup failed`. The Proxmox firewall is disabled here, so set
`network_firewall: false` in the machine class and untick **Firewall** on
existing VM NICs.

Hosts with `nvme_apst_disabled: true` in the inventory also get
`nvme_core.default_ps_max_latency_us=0`, which keeps the NVMe out of its deep
power states (APST). It applies immediately through sysfs and on every boot
through `/etc/default/grub.d/60-nvme-apst.cfg`. Check with
`cat /sys/class/nvme/nvme0/power/pm_qos_latency_tolerance_us` (expected `0`).

Hosts with `cpu_max_cstate` set get `intel_idle.max_cstate=<n>`, which stops
the CPU from entering idle states deeper than the first `<n>` (1 = C1 only).
Deep package states can freeze some Intel platforms silently at idle power.
It applies immediately through each state's sysfs `disable` file and on every
boot through `/etc/default/grub.d/60-cpu-cstate.cfg`; it raises idle power.
Check with `grep . /sys/devices/system/cpu/cpu0/cpuidle/state*/disable`
(expected `0` for POLL and C1, `1` for the rest).

How to read the next crash: panic text in pstore or netconsole points to
software (a kernel, driver or USB fault). A reset with nothing in either points
to hardware (RAM, board or power supply).

Rollback: delete `/etc/sysctl.d/60-crash-capture.conf`,
`/etc/modules-load.d/crash-capture.conf`,
`/etc/systemd/system.conf.d/60-watchdog.conf`, `/etc/modprobe.d/netconsole.conf`,
`netconsole.service`, `/etc/default/grub.d/60-nvme-apst.cfg` and
`/etc/default/grub.d/60-cpu-cstate.cfg`, run
`update-grub`, then reboot the host.
