# Operations

This part explains how the deployed platform works and how to operate it.
Read [the easy guide](../easy-guide.md) first, then work through the chapters
below. Each runbook carries its own prerequisites, checks, and recovery steps.

| Chapter | What you will learn | Start here |
| --- | --- | --- |
| GitOps & ArgoCD | How changes in Git become running applications | [ArgoCD architecture](../domains/argocd/argocd.md) |
| Storage | Where application data lives and how volumes are attached | [Storage architecture](../storage-architecture.md) |
| Backups & disaster recovery | How data is protected and restored | [kopiur backup architecture](../domains/storage/kopiur-backup-architecture.md) |
| Databases | How this lab runs and protects Postgres | [Run Postgres here](../domains/cnpg/run-postgres-plain-english.md) |
| Networking | How clients and applications reach each other | [Network topology](../domains/networking/topology.md) |
| AI / GPU | How models are served and GPU capacity is managed | [Model catalog](../domains/ai-gpu/model-catalog.md) |
| Reference & ops | Scheduling policy, observability, and maintenance | [VPA and topology](../domains/scheduling/vpa-and-topology.md) |

Next, explore the machines that run these services in [Inventory](../inventory/index.md).
Then use [Audits](../audits/index.md) to understand their measured limits, and
[Ongoing research](../research/index.md) for possible future changes.
