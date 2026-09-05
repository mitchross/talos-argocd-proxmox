# Omni machine contract in CI

The `Omni Machine Contract` workflow runs for `omni/**` changes independently
of Cluster CI. Kubernetes manifest rendering cannot validate the separate
MachineClass provider data and machine-set placement contract.

The check reads the committed `cluster-template-prod-v2.yaml` and its referenced
`omni/machine-classes/<name>.yaml` files. It checks class identity, positive VM
sizes, disk selectors, inline host zones, unique Longhorn disk names/paths,
and the shed Wi-Fi worker's taint and disabled Longhorn scheduling.

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
```

No cluster API, SSH, credentials, or host command is used. Referenced secret
patches are deliberately not opened. The validator is scoped to the production
v2 template and its inline placement convention, not every future Omni layout.
A future file-based topology patch needs explicit validator support.

## What passing does not establish

This is a repository contract check, not the version-matched Omni/Talos schema
validator. Run the official template validation and inspect the template sync
dry run before an approved provisioning change. Applying a MachineClass does
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

This PR changes validation only. It does not alter machines, templates, disk
placement, networking, or any Kubernetes Application. Reverting it removes the
additional check without changing the lab.
