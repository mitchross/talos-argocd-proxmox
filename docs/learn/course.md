# Interactive course: how your data survives a cluster wipe

A guided walkthrough of backup and restore in this cluster. It follows one real app,
Karakeep, from a `git push` through a full cluster wipe and back. It shows the real manifests
from this repo next to plain-English explanations and animated diagrams. You need no
Kubernetes experience.

<div class="grid cards" markdown>

-   :material-backup-restore:{ .lg .middle } __Start the course__

    ---

    9 short lessons, about 14 minutes. You learn what a PVC is and which line (`dataSourceRef`)
    makes data restore itself. You see how sync waves order the boot. You see what does NOT
    use this path (databases, exempt disks) and what happens when the cluster is rebuilt from
    nothing. The course remembers your progress, so you can leave and come back.

    [:octicons-arrow-right-24: Open the course](backups-course/index.html){ .md-button .md-button--primary }

</div>

!!! tip "How it works"
    Instructions are on the left and the real file is on the right. Step through with **Continue**
    or the arrow keys. The diagrams animate on their own. Nothing in the course can break.

!!! note "Want the deep dive?"
    This course is a gentle introduction. For the full reference, see
    [kopiur backup architecture](../domains/storage/kopiur-backup-architecture.md) and the
    [storage architecture source-of-truth](../storage-architecture.md).
