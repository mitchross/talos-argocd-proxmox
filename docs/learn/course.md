# Interactive course — how your data survives a cluster wipe

A guided, beginner-friendly walkthrough of the backup & restore story in this cluster. It
follows one real app — **Karakeep** — from a `git push` through a full cluster wipe and back,
showing the **real manifests** from this repo alongside plain-English explanations and
animated diagrams. No Kubernetes experience needed.

<div class="grid cards" markdown>

-   :material-backup-restore:{ .lg .middle } __Start the course__

    ---

    8 short lessons · ~12 min. Learn what a PVC is, the one line (`dataSourceRef`) that makes
    data restore itself, how sync waves order the boot, and what actually happens when the
    cluster is rebuilt from nothing.

    [:octicons-arrow-right-24: Open the course](../backups-course/){ .md-button .md-button--primary }

</div>

!!! tip "How it works"
    Instructions on the left, the real file on the right — step through with **Continue** (or
    the arrow keys). The diagrams animate on their own; there's nothing to run or break.

!!! note "Want the deep dive?"
    This course is the gentle on-ramp. For the full reference, see
    [kopiur backup architecture](../domains/storage/kopiur-backup-architecture.md) and the
    [storage architecture source-of-truth](../storage-architecture.md).
