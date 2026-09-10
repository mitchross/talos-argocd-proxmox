# Physical host metrics

This configuration supplies continuous physical disk, CPU, memory and I/O
metrics to the existing Prometheus/Grafana stack. It is a proposed deployment
until the PR is merged and the steps below are completed. These hosts are
outside Talos; ArgoCD does not apply this directory.

[inventory.yaml](inventory.yaml) identifies the five Proxmox hosts, Pi and
TrueNAS. [playbook.yaml](playbook.yaml) uses the upstream Prometheus Ansible
roles on Proxmox and Pi. [truenas-compose.yaml](truenas-compose.yaml) runs the
same exporters as a TrueNAS Custom App, without installing appliance packages.
No snapshots, textfile collectors or custom collection programs are involved.

## What each exporter provides

| Exporter | Source and purpose | Listen address |
| --- | --- | --- |
| node_exporter 1.12.1 | Host kernel CPU, RAM, pressure, per-device I/O, device identity, mdraid and ZFS/ARC statistics | Host LAN IP, port 9100 |
| smartctl_exporter 0.14.0 | Drive model, capacity, temperature, SMART status, ATA attributes and NVMe wear/error counters through smartctl | Host LAN IP, port 9633 |

SMART polling is once per minute on demand; automatic discovery rescans every
five minutes. Sleeping drives are not deliberately woken for SMART polling.
The native SMART process runs as root because device ioctls need elevated
access. The TrueNAS SMART container uses upstream's privileged deployment
model with the live host `/dev` mounted directly. Mounting only `/hostdev`
would leave smartctl scanning the container's stale device list.

The node container reads host `/proc`, `/sys` and udev through the recursive
read-only root mount and joins the host PID/network namespaces. Its 256 MiB
ceiling, and the SMART container's separate 256 MiB ceiling, leave substantial
headroom over the temporary container probes (about 24 and 23 MiB respectively).
The pinned images successfully read the NAS host identity, RAM, disks and ARC
through these mounts. Verify budgets and collector success after deployment;
temporary containers do not validate the TrueNAS app manager or persistence.

## Deploy after PR merge

Prerequisites: an Ansible control machine, existing SSH access, sudo access on
the Pi, TrueNAS Apps administration, and the existing Prometheus stack.
Credentials stay outside this inventory. Bindings are LAN-only, not an
authentication boundary; allow these ports only from the monitoring network
and do not publish them through an external HTTPRoute.

From the repository root, install the pinned upstream collection and inspect
the proposed host changes:

```sh
ansible-galaxy collection install -r host-monitoring/requirements.yaml
ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/playbook.yaml --syntax-check
ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/playbook.yaml --check --diff --limit gpu
```

Check mode previews the roles; it does not prove that uninstalled binaries can
collect metrics. After review, apply to one host first:

```sh
ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/playbook.yaml --limit gpu
```

Verify both endpoints from the monitoring network, current disk identities,
collector success and the Grafana host row before proceeding:

```sh
ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/playbook.yaml --limit dell,sff,elite,pi
```

The Pi needs the `smartmontools` package; it was absent at inspection. The
Proxmox hosts already have it. Leave Shed unavailable until its host/network
problem is resolved, then apply with `--limit shed`. Missing metrics must show
unknown/unreachable rather than an old healthy value.

In TrueNAS **Apps → Discover Apps → Install via YAML**, create a Custom App
named `physical-monitoring` from the committed `truenas-compose.yaml`.
Verify 10 physical drives, the actual NAS CPU/RAM totals and ARC metrics. The
built-in Netdata service currently disables its web endpoint; changing its
generated appliance configuration is not part of this deployment.

## Interpretation and acceptance

- Prometheus jobs `physical-node` and `physical-smartctl` must be up for each
  reachable host. Check `node_scrape_collector_success` for CPU, meminfo,
  diskstats, filesystem and ZFS where applicable. Optional collectors for
  absent hardware can fail; an HTTP 200 alone does not establish collection.
- Join drive metrics using the normalized physical host/device labels. Native
  SMART discovery reports NVMe controllers such as `nvme0`; node_exporter I/O
  reports namespaces such as `nvme0n1`. Verify persistent identity privately:
  the NAS SAS disks expose their WWN as node_exporter's `serial`, while SMART
  uses a different vendor serial. Literal serial equality would drop those
  disks. A future multi-namespace device needs explicit
  controller/namespace handling rather than duplicating controller capacity.
- `smartctl_device_smart_status=1` means **the drive reports OK**, not proven
  durability. Unsupported ATA wear attributes remain unknown; normalized
  vendor values are not interchangeable with NVMe percentage used.
- SMART exit status is a bitmask. The live HPE SATA drives returned 4 for a
  failed/unsupported optional command while reporting SMART OK. A nonzero
  exit status alone is not a failed-drive verdict.
- **Upstream freshness limitation:** version 0.14.0 retains its previous JSON
  after a failed SMART read and does not expose the last successful read
  timestamp. Its exit-status metric can also be cached. A new Prometheus
  scrape timestamp is not proof of a new successful disk read. Gate display
  on current host/device presence, show this limitation, and consult exporter
  logs when device access fails. Shortening the poll interval does not fix it.
- This exporter does not expose the NVMe unsafe-shutdown count. Keep that
  field unavailable rather than copying the audit's historical value.

Acceptance is live discovery of 22 currently reachable disks, two explicitly
unavailable Shed disks, advancing CPU/I/O counters, current temperatures and
stable exporter memory. Recheck after a normal NAS backup and a host reboot.
Drive serials are useful for private correlation; omit them from public
dashboard output and published evidence.

## Rollback

Stop and disable only the new native services on an affected host:

```sh
ansible -i host-monitoring/inventory.yaml gpu -b -m ansible.builtin.systemd_service -a 'name=node_exporter state=stopped enabled=false'
ansible -i host-monitoring/inventory.yaml gpu -b -m ansible.builtin.systemd_service -a 'name=smartctl_exporter state=stopped enabled=false'
```

Replace `gpu` with the affected inventory hostname. Stop the
`physical-monitoring` TrueNAS Custom App to roll back its exporters. Revert
scrape/dashboard configuration through a PR if retiring the deployment.
Do not remove Proxmox's pre-existing smartmontools package or smartd service.

Sources: [node_exporter](https://github.com/prometheus/node_exporter),
[smartctl_exporter](https://github.com/prometheus-community/smartctl_exporter),
[upstream cached-read behavior](https://github.com/prometheus-community/smartctl_exporter/blob/v0.14.0/readjson.go),
[pinned Ansible collection](https://github.com/prometheus-community/ansible/tree/0.30.1),
[TrueNAS Custom Apps](https://apps.truenas.com/managing-apps/installing-custom-apps/).
