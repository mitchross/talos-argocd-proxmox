# Manage physical hosts with Ansible

This page explains which settings Ansible owns on the physical machines and how to
run a playbook safely. Read it before you change a Proxmox host or the management Pi.

Omni builds the Talos VMs, and Argo CD runs everything inside Kubernetes. The
machines underneath them, three Proxmox hosts and the management Pi, are plain
Debian systems that Argo CD cannot reach. Their operating-system settings are in
[`host-monitoring/`][dir]. Ansible, a tool that applies settings over SSH, applies
them from a workstation.

You apply playbooks by hand. A merged pull request changes nothing on a host until
someone runs the playbook against that host.

## What Ansible manages

| Playbook | What it installs or changes | Hosts | Full guide |
|---|---|---|---|
| [`playbook.yaml`][metrics] | `node_exporter` (CPU, RAM, disk I/O on `:9100`) and `smartctl_exporter` (drive health on `:9633`) for Prometheus | Proxmox, Pi | [README][readme] |
| [`logging-playbook.yaml`][logging] | Persistent journal plus an OpenTelemetry Collector that ships it to Loki (Grafana **Nodes / Crash logs**) | Proxmox, Pi | [LOGGING.md][logging-doc] |
| [`crash-capture-playbook.yaml`][crash] | Lockups become panics that reboot, panic text saved to EFI pstore, chipset hardware watchdog, kernel messages streamed to the Pi with netconsole | Proxmox, one host at a time | [LOGGING.md § Crash capture][crash-doc] |

Ansible does not change TrueNAS, because TrueNAS is an appliance. Its exporters run
as a TrueNAS Custom App from [`truenas-compose.yaml`][truenas].

Ansible does **not** manage the Talos VMs, Proxmox network interfaces, USB and PCI
resource mappings, or Proxmox package upgrades. The Omni Proxmox provider builds
the VMs from `omni/machine-classes/`.

## The inventory

[`inventory.yaml`][inventory] names every machine. Use these names with
`--limit`.

| Group | Names | SSH user |
|---|---|---|
| `proxmox` | `gpu` (.14), `shed` (.20), `sff` (.21) | `root` |
| `management` | `pi` (.15) | `vanillax` with sudo |
| `appliances` | `nas` (.133) | Listed for reference. No playbook targets it |

The `proxmox` and `management` groups together form the group `physical_linux`.

Put a setting that only one host needs in the inventory as a host variable, so it
survives the next run. A manual change on a host lasts only until a playbook runs
again and restores the declared state.

## Before you start

Run every command from the repository root.

1. Install Ansible on your workstation. `ansible-playbook --version` prints a version.
2. Install the pinned collection:
   `ansible-galaxy collection install -r host-monitoring/requirements.yaml`
3. Set up SSH key login to each host. Then confirm that Ansible can reach them:

    ```sh
    ansible -i host-monitoring/inventory.yaml physical_linux -m ping
    ```

    Expected result: every host answers `"ping": "pong"`. If a host is
    `UNREACHABLE`, fix SSH before you continue.

## Run a playbook safely

Replace `<playbook>` with a file from the table and `<host>` with an
inventory name.

1. Check the syntax.

    ```sh
    ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/<playbook> --syntax-check
    ```

2. Preview one host. `--check --diff` shows each file it would change
   without changing it.

    ```sh
    ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/<playbook> --limit <host> --check --diff
    ```

    Check mode skips shell and command steps. A step can also fail because a
    file that an earlier step creates does not exist yet. Read those failures.
    They do not always mean that the real run will fail.

3. Apply to that host.

    ```sh
    ansible-playbook -i host-monitoring/inventory.yaml host-monitoring/<playbook> --limit <host>
    ```

    Expected result: `PLAY RECAP` shows `failed=0`. A second run shows
    `changed=0`, because a playbook changes only what differs.

4. Verify with the checks in that playbook's guide.
5. Repeat for the remaining hosts, one at a time.

Playbooks never reboot a host. A kernel boot option that a playbook adds takes
effect at the next reboot.

## Roll back

Each guide lists the files and services that its playbook creates. To undo a
playbook, stop or remove those files and services on the affected host. Then revert
the pull request, so the next run does not put them back.

[dir]: https://github.com/mitchross/talos-argocd-proxmox/tree/main/host-monitoring
[readme]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/README.md
[inventory]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/inventory.yaml
[metrics]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/playbook.yaml
[logging]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/logging-playbook.yaml
[logging-doc]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/LOGGING.md
[crash]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/crash-capture-playbook.yaml
[crash-doc]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/LOGGING.md#crash-capture-for-hard-locks
[truenas]: https://github.com/mitchross/talos-argocd-proxmox/blob/main/host-monitoring/truenas-compose.yaml
