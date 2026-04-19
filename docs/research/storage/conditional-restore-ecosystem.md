# Conditional PVC Restore Ecosystem Research

This report answers a narrow but important question:

> Does the public Kubernetes / homelab ecosystem already have a clean, widely adopted solution for declarative "restore if backup exists, otherwise create empty" PVC behavior?

This was researched because the storage model in this repo can feel suspiciously custom. If the internet already had a standard answer, we should be using it. If it does not, that should be documented clearly.

## Research Question

The exact problem being evaluated is not generic backup.

It is this specific workflow:

1. A plain PVC is created from Git
2. The platform checks whether a prior backup exists
3. If a backup exists, restore automatically
4. If no backup exists, create an empty PVC
5. If backup truth is unknown, fail closed instead of booting fresh
6. Do all of this without a UI restore ritual or a one-off human runbook

That is a much narrower requirement than "does Kubernetes support backup and restore?"

## Executive Finding

After reviewing official docs, GitHub issues, public homelab discussions, blogs, and current search/video results, the conclusion is:

> There is **not** a widely adopted, mainstream, end-to-end solution that provides declarative conditional restore, create-time restore intent, and fail-closed behavior for modest homelab clusters.

What exists today is mostly one of the following:

- declarative backup + **explicit restore**
- declarative backup + **manual `ReplicationDestination` / restore CR**
- GitOps install + **taskfiles or scripts for restore orchestration**
- retained PVCs / existing claims to avoid the question entirely

The closest upstream pattern is **VolSync Volume Populator**, but it still does not cleanly match the full safety envelope used in this repo.

## Scope Of Sources Reviewed

The research included:

- official project docs
- GitHub issues and maintainer discussions
- Red Hat / reference-architecture content
- public homelab blog posts
- public Reddit discussions
- search/video result landscape for GitOps homelab restore tutorials

Representative sources are linked inline below.

## What Official Projects Actually Offer

### Longhorn: explicit restore mechanics, not restore intent

Official Longhorn restore docs show restore via UI or custom resource/CLI workflows, with the operator supplying the exact backup to restore from.

- [Longhorn restore from backup docs](https://longhorn.io/docs/1.10.1/snapshots-and-backups/backup-and-restore/restore-from-a-backup/)

What Longhorn gives you:

- dynamic provisioning
- snapshots
- recurring backups
- restore from known backup targets

What it does **not** give you:

- "PVC created from Git → decide restore vs empty automatically"
- fail-closed behavior when backup truth is unknown

Longhorn solves storage and restore mechanics. It does not solve create-time restore intent.

### Velero: declarative backup, explicit restore

Velero restore is still driven by an explicit restore action / Restore CR.

- [Velero restore reference](https://velero.io/docs/main/restore-reference/)

Velero is excellent for:

- cluster-level backup
- restore workflows
- disaster recovery operations

But the core model is still:

> identify backup → create restore → execute restore

That is not the same as:

> plain PVC appears → platform decides whether to restore or create empty

### VolSync: closest upstream answer, still not the full answer

The most relevant upstream feature is **Volume Populator**.

- [VolSync Volume Populator docs](https://volsync.readthedocs.io/en/latest/usage/volume-populator/index.html)

Why it matters:

- a PVC can reference a `ReplicationDestination` through `dataSourceRef`
- the PVC can remain pending until VolSync has data to populate it
- this is the closest thing to a Kubernetes-native restore-on-create pattern

Why it still falls short of this repo's full safety bar:

- it assumes the restore resource path is already chosen
- it still does not fully solve the "does a backup exist, and should this PVC restore or start fresh?" decision
- it does not inherently provide the same fail-closed intent gate

There is also concrete evidence that the current behavior is not perfectly fail-closed when backups are missing or invalid:

- [VolSync issue #1211](https://github.com/backube/volsync/issues/1211)

That issue is important because it documents a user reporting that an empty PVC can still attach when no valid snapshot is found, and a maintainer states that the current behavior is not to fail when no snapshots are found.

That is incompatible with a strict "never boot fresh unless the platform knows that is correct" model.

## What Public Homelab Operators Actually Do

### onedr0p / VolSync discussion: taskfiles and restore choreography

One of the strongest signals found was a public VolSync discussion involving onedr0p:

- [VolSync issue #627](https://github.com/backube/volsync/issues/627)

What this shows:

- cluster rebuilds are real
- automatic backup is straightforward
- restore is still often orchestrated through scripts / taskfiles / sequencing
- users suspend GitOps, delete stale PVCs, apply restore resources, then resume

That is a strong public example of a respected homelab operator dealing with the same class of problem this repo is solving.

The important conclusion is not "VolSync is bad." The conclusion is:

> even advanced public homelab operators are still using scripts and restore choreography instead of a clean built-in conditional restore primitive.

### EDNZ guide: VolSync restore is manual

An example public guide for VolSync restore makes the manual nature explicit:

- [EDNZ: Restoring VolSync Restic Backups](https://ednz.fr/docs/kubernetes/snippets/restore-volsync-backups/)

Their documented flow is:

1. create a `ReplicationDestination`
2. wait for restore to finish
3. delete the restore object
4. restart workloads

The guide explicitly says this is a **manual process** and notes that the PVC must already exist. That is useful, but it is not automatic conditional restore.

### Longhorn homelab guides are still explicit restore runbooks

A representative homelab blog post on Longhorn restore:

- [Merox: Longhorn backup/restore](https://merox.dev/blog/longhorn-backup-restore/)

The pattern there is the familiar one:

- scale workloads down
- restore backup explicitly
- recreate or bind volumes
- start workloads again

Again: good backup/restore practice, but still an operator-driven runbook.

## What Reference / Enterprise Articles Show

Even the more polished reference material stops short of this repo's exact problem.

- [Red Hat: VolSync ACM add-on article](https://www.redhat.com/en/blog/volsync-acm-add-on)

The reference pattern is typically:

- replicate or protect data
- expose a restore destination
- attach or consume the restored data in disaster or migration scenarios

That is closer to "replication and explicit recovery" than to "PVC admission-time restore intent."

## What The Blog / YouTube Landscape Looks Like

Search results across DuckDuckGo and Google were useful because they show what public content is easy to find.

What those results mostly surfaced:

- Longhorn backup/restore explainers
- generic GitOps homelab tutorials
- VolSync backup demos
- Velero + GitOps install articles
- manual restore guides and ReplicationDestination examples

What they did **not** surface as a mature, repeated pattern:

- a standard "restore if backup exists, else create empty" control plane
- a common fail-closed admission design
- a widely copied zero-touch restore-intent layer

There are signs the community is beginning to move in this direction. For example, current search results surface newer content around VolSync + GitOps restore, including recent Reddit and YouTube posts. But those still cluster around:

- restore resources in Git
- VolSync restore walkthroughs
- backup/restore automation as a procedure

not a universally adopted create-time conditional restore primitive.

In other words:

> the ecosystem is discussing adjacent ideas, but it still has not converged on a simple public answer to this exact problem.

## Why This Gap Exists

This problem crosses several boundaries that most tools intentionally keep separate.

Storage tools know how to:

- provision
- snapshot
- restore

Backup tools know how to:

- store recovery points
- replay them on request

GitOps tools know how to:

- converge YAML
- retry failed applies

But none of those layers naturally answers this question:

> When a PVC is created, is this a first install, an intentional fresh start, a rebuild, a rename accident, a missing backup, or a temporarily unreachable backup backend?

That is a **restore intent** problem, not only a storage problem.

And because the wrong automatic answer can destroy data, most tools stop short and require an explicit restore step.

## What This Means For This Repo

The research supports the current architectural framing:

> This repo is not reinventing backup. It is adding a missing restore-intent layer above otherwise normal Kubernetes storage and backup primitives.

That does **not** mean the current implementation is beyond criticism.

It means the right next move is:

- keep the core design
- harden it
- document the sharp edges honestly
- prove it with drills

It does **not** suggest that there is already a cleaner off-the-shelf replacement that should obviously displace `pvc-plumber`.

## Verdict

### The strongest current upstream option

If someone wanted the closest non-custom approach today, the answer would be:

- **VolSync Volume Populator**

But it is still only the closest option, not the full answer.

### The most accurate summary of today's ecosystem

The public internet mostly has:

- **Longhorn** → explicit restore
- **Velero** → explicit restore
- **VolSync** → closest declarative restore building block, but not a full conditional restore intent layer
- **public homelab workflows** → scripts, runbooks, restore resources, and manual sequencing

### Final conclusion

There is currently **no clean, widely adopted, end-to-end internet-standard solution** for:

- declarative PVC creation
- automatic restore-if-backup-exists
- create-empty-if-not
- fail-closed-if-truth-unknown
- modest-hardware homelab compatibility

That gap appears to be real.

## Source List

- [VolSync Volume Populator docs](https://volsync.readthedocs.io/en/latest/usage/volume-populator/index.html)
- [VolSync issue #1211](https://github.com/backube/volsync/issues/1211)
- [VolSync issue #627](https://github.com/backube/volsync/issues/627)
- [Longhorn restore from backup docs](https://longhorn.io/docs/1.10.1/snapshots-and-backups/backup-and-restore/restore-from-a-backup/)
- [Velero restore reference](https://velero.io/docs/main/restore-reference/)
- [Merox: Longhorn backup/restore](https://merox.dev/blog/longhorn-backup-restore/)
- [EDNZ: Restoring VolSync Restic Backups](https://ednz.fr/docs/kubernetes/snippets/restore-volsync-backups/)
- [Red Hat: VolSync ACM add-on article](https://www.redhat.com/en/blog/volsync-acm-add-on)
- [Max Pfeiffer: Velero as backup solution for Kubernetes](https://max-pfeiffer.github.io/velero-as-backup-solution-for-kubernetes.html)