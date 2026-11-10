# Omni machine contract in CI

The `Omni Machine Contract` workflow checks the machine definitions under `omni/` on every change to `omni/**`.
This page explains what the check covers, how to run it locally, and what a pass does not prove.
Read it before you open a PR that changes a machine class, a machine set, or a node label.

The check runs independently of Cluster CI.
Cluster CI renders Kubernetes manifests, and that render cannot validate MachineClass provider data or machine-set placement.

## What the check reads

The check reads the committed `cluster-template-prod-v2.yaml` and the `omni/machine-classes/<name>.yaml` files it references.
It checks these items:

- Class identity.
- Positive VM sizes.
- Disk selectors.
- Inline host zones.
- Unique Longhorn disk names and paths.
- The taint of the shed Wi-Fi worker, and its disabled Longhorn scheduling.

It uses no cluster API, SSH, credentials, or host command.
It never opens the referenced secret patches.

## How it treats hosts and capacity

In this repo, one Proxmox provider identifies one physical host.
Several VMs from that provider cannot claim different physical-host zones.

The reported CPU and memory totals add up the declared guests per provider.
**The totals are not measurements, reservations, or admission decisions. They do not prove that the physical host has capacity.**
The check never derives host limits from comments.
It never assumes that all vCPUs are independent physical cores.

## Run

```sh
python -m unittest discover -s scripts/tests -p test_omni_contract.py -v
python scripts/validate-omni-contract.py
```

The validator covers the production v2 template and its inline placement convention.
It does not cover every possible Omni layout.
A file-based topology patch needs explicit validator support first.

## What passing does not establish

This check validates the repository contract. It is not the version-matched Omni and Talos schema validator.
Before an approved provisioning change, run the official template validation and inspect the template sync dry run.

Applying a MachineClass does not prove that an already allocated VM changed.
Verify the actual Omni state and the VM hardware separately.

Do not add credentials to CI to turn these static tests into an integration test.

## What a hardware PR must record

A hardware PR records these items:

- The exact hosts affected.
- The current and proposed allocation.
- Storage ownership.
- The expected restart or replacement behavior.
- Backup acceptance evidence.
- Rollback.

Node replacement or data migration needs its own execution plan.
A green check does not authorize anyone to destroy provider-owned disks.

## The check is not an enforced approval

The workflow file does not enable branch protection.
A repository administrator must configure required status checks and branch rules separately.
Do not describe a workflow file as an enforced approval policy.

For this single-operator lab, an explicit emergency bypass can be better than a reviewer count that blocks normal changes.

The workflow validates only. It does not alter machines, templates, disk placement, networking, or any Kubernetes Application.
Removing the workflow removes the check and changes nothing else in the lab.
