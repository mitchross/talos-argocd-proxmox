# Operations

This part explains how the deployed platform works and how to operate it.
Read [the easy guide](../easy-guide.md) first, then work through the chapters
below. Each runbook carries its own prerequisites, checks, and recovery steps.

| Chapter | What you will learn | Start here |
| --- | --- | --- |
| GitOps & ArgoCD | How changes in Git become running applications | [ArgoCD architecture](../domains/argocd/argocd.md) |
| Temporal | How worker versions roll out safely, and what breaks them | [Worker versioning guide](../domains/temporal/worker-versioning-guide.md) |
| Storage | Where application data lives and how volumes are attached | [Storage architecture](../storage-architecture.md) |
| Backups & disaster recovery | How data is protected and restored | [kopiur backup architecture](../domains/storage/kopiur-backup-architecture.md) |
| Databases | How this lab runs and protects Postgres | [Run Postgres here](../domains/cnpg/run-postgres-plain-english.md) |
| Networking | How clients and applications reach each other | [Network topology](../domains/networking/topology.md) |
| Physical hosts | How the Proxmox hosts and Pi are configured with Ansible, outside Argo CD | [Physical hosts with Ansible](../domains/hosts/physical-hosts-ansible.md) |
| Bare-metal nodes | Add a machine or convert a Proxmox host to bare-metal Talos, wipe reused disks, register Longhorn disks | [Bare-metal Talos workers](../domains/hosts/bare-metal-talos.md) |
| Local AI | The parts of self-hosted AI, how models are served, GPU capacity | [Local AI starter kit](../domains/ai-gpu/index.md) |
| Reference & ops | Scheduling policy, observability, and maintenance | [VPA and topology](../domains/scheduling/vpa-and-topology.md) |

Next, explore the machines that run these services in [Inventory](../inventory/index.md).
Then use [Audits](../audits/index.md) to understand their measured limits, and
[Ongoing research](../research/index.md) for possible future changes.
