# Physical hosts with Ansible

Omni builds the Talos VMs and Argo CD runs everything inside Kubernetes. The
machines underneath them — five Proxmox hosts and the management Pi — are plain
Debian systems that Argo CD cannot reach. Their operating-system settings live
in [`host-monitoring/`][dir] and are applied with Ansible from a workstation.

**Status:** current. Playbooks are applied by hand. Merging a pull request
changes nothing on a host until someone runs the playbook against it.

## What Ansible manages

| Playbook | What it installs or changes | Hosts | Full guide |
|---|---|---|---|
| [`playbook.yaml`][metrics] | `node_exporter` (CPU, RAM, disk I/O on `:9100`) and `smartctl_exporter` (drive health on `:9633`) for Prometheus | Proxmox, Pi | [README][readme] |
| [`logging-playbook.yaml`][logging] | Persistent journal plus an OpenTelemetry Collector that ships it to Loki (Grafana **Nodes / Crash logs**) | Proxmox, Pi | [LOGGING.md][logging-doc] |
| [`crash-capture-playbook.yaml`][crash] | Lockups become panics that reboot, panic text saved to EFI pstore, chipset hardware watchdog, kernel messages streamed to the Pi with netconsole | Proxmox, one host at a time | [LOGGING.md § Crash capture][crash-doc] |

TrueNAS is an appliance and is not changed by Ansible. Its exporters run as a
TrueNAS Custom App from [`truenas-compose.yaml`][truenas].

Ansible does **not** manage the Talos VMs (the Omni Proxmox provider builds
them from `omni/machine-classes/`), Proxmox network interfaces, USB and PCI
resource mappings, or Proxmox package upgrades.

## The inventory

[`inventory.yaml`][inventory] names every machine. Use these names with
`--limit`.

| Group | Names | SSH user |
|---|---|---|
| `proxmox` | `gpu` (.14), `dell` (.16), `shed` (.20), `sff` (.21), `elite` (.22) | `root` |
| `management` | `pi` (.15) | `vanillax` with sudo |
| `appliances` | `nas` (.133) | listed for reference; no playbook targets it |

A setting that only one host needs is a host variable in the inventory, so it
survives the next run. Changing a host by hand works only until a playbook
runs again and puts the declared state back.

## Prerequisites

Run everything from the repository root.

1. Ansible on your workstation: `ansible-playbook --version` prints a version.
2. The pinned collection:
   `ansible-galaxy collection install -r host-monitoring/requirements.yaml`
3. SSH key login to each host, then confirm Ansible can reach them:

    ```sh
    ansible -i host-monitoring/inventory.yaml physical_linux -m ping
    ```

    Expected: every host answers `"ping": "pong"`. Fix SSH before continuing
    if any host is `UNREACHABLE`.

## Run a playbook safely

Replace `<playbook>` with a file from the table and `<host>` with an
inventory name.

1. **Check the syntax.**

    ```sh
    ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/<playbook> --syntax-check
    ```

2. **Preview one host.** `--check --diff` shows each file it would change
   without changing it.

    ```sh
    ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/<playbook> --limit <host> --check --diff
    ```

    Check mode skips shell and command steps, and a step can fail because a
    file created earlier in the same run does not exist yet. Read those
    failures; they do not always mean the real run will fail.

3. **Apply to that host.**

    ```sh
    ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/<playbook> --limit <host>
    ```

    Expected: `PLAY RECAP` shows `failed=0`. Running it again shows
    `changed=0`, because a playbook only changes what differs.

4. **Verify** with the checks in that playbook's guide.
5. **Repeat for the remaining hosts**, one at a time.

Playbooks never reboot a host. A kernel boot option they add takes effect at
the next reboot.

## Rollback

Each guide lists the files and services its playbook creates. To undo one,
stop or remove those on the affected host, then revert the pull request so the
next run does not put them back.

[dir]: https://github.com/mitchross/talos-argocd-proxmox/tree/main/host-monitoring
[readme]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/README.md
[inventory]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/inventory.yaml
[metrics]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/playbook.yaml
[logging]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/logging-playbook.yaml
[logging-doc]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/LOGGING.md
[crash]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/crash-capture-playbook.yaml
[crash-doc]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/LOGGING.md#crash-capture-for-hard-locks
[truenas]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/truenas-compose.yaml
