# Omni machine contract in CI

The `Omni Machine Contract` workflow runs for `omni/**` changes independently
of Cluster CI. Kubernetes manifest rendering cannot validate the separate
MachineClass provider data and machine-set placement contract.

The check reads the committed `cluster-template-prod-v2.yaml` and its referenced
`omni/machine-classes/<name>.yaml` files. It checks class identity, positive VM
sizes, disk selectors, inline host zones, unique Longhorn disk names/paths,
and the shed Wi-Fi worker's taint and disabled Longhorn scheduling.
Both legacy placement fields and `KubeNodeConfig` are understood. Fresh-install
checks require a uniquely smallest boot disk, a single match per volume selector,
disjoint data disks and bounded control-plane partitions that leave boot space.
The static selector evaluator supports this template's size comparisons only;
an unsupported expression fails until evaluator support is added.

In this repository one Proxmox provider identifies one physical host. Multiple
VMs from that provider cannot claim different physical-host zones. Reported
CPU/memory totals sum declared guests per provider; they are NOT measurements,
reservations, admission decisions, or proof that the physical host has capacity.
The check never derives host limits from comments or assumes all vCPUs are
independent physical cores.

## Run

```sh
python -m unittest discover -s scripts/tests -p test_omni_contract.py -v
python scripts/validate-omni-contract.py
python scripts/validate-omni-fresh-configs.py
```

No cluster API, SSH, credentials, or host command is used. Referenced secret
patches are deliberately not opened. The validator is scoped to the production
v2 template and its inline placement convention, not every future Omni layout.
A future file-based topology patch needs explicit validator support.

The fresh-config command uses the template's exact `talosctl` version to generate
and validate all six machine roles with synthetic cluster secrets. It also checks
the control-plane taint, Cilium ownership, worker node IP selection, Longhorn's
shared writable kubelet bind, kubelet version and the fresh security defaults.
CI downloads the matching release binary and verifies its published SHA-256.

CI skips only `patches/docker-hub-auth.yaml`. On the rebuild workstation, add
`--include-private-patches` to validate that actual credential patch too. The
script deletes temporary generated configs by default; `--output-dir <new-directory>`
retains owner-only configs and logs for diagnosis. Treat that directory as secret
recovery material, especially when including the private patch.

## What passing does not establish

The placement check is a repository contract; the separate fresh-config check
runs the native Talos schema validator. Also run official Omni template validation
and inspect the template sync dry run before provisioning. Applying a MachineClass does
not prove an already allocated VM changed. Verify actual Omni state and the VM
hardware separately. Do not add credentials to CI to make these static tests
pretend to be an integration test.

A hardware PR should record the exact hosts affected, current and proposed
allocation, storage ownership, expected restart/replacement behavior, backup
acceptance evidence, and rollback. Node replacement or data migration requires
its own explicit execution plan; a green check is not authorization to destroy
provider-owned disks.

## Delivery gate

Repository administrators must separately configure required status checks and
branch rules. Adding this workflow does not enable branch protection. For the
single-operator lab, an explicit emergency bypass can be preferable to a
reviewer count that makes normal changes impossible. Do not represent a
workflow file as an enforced approval policy.

Running either validator does not apply configuration or change the lab.
These checks do not boot a VM, exercise storage/GPU devices, or restore a PVC.
