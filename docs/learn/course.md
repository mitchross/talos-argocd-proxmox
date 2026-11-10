# Course: how your data survives a cluster wipe

This course teaches backup and restore in this cluster, one short lesson at a time.
It is for a reader who is new to this lab. You need no Kubernetes experience.

The course follows one real app, Karakeep, through a `git push`, a full cluster
wipe, and the rebuild. Each lesson shows a real manifest from this Git repo next
to a plain-English explanation and an animated diagram.

<div class="grid cards" markdown>

-   :material-backup-restore:{ .lg .middle } __Start the course__

    ---

    The course has 9 short lessons and takes about 14 minutes. You learn what a
    PVC is and which line (`dataSourceRef`) makes data restore itself. You see how
    sync waves order the startup. You see how the cluster treats databases and
    backup-exempt disks. You see what happens when the cluster is rebuilt from
    nothing. The course
    remembers your progress, so you can leave and come back.

    [:octicons-arrow-right-24: Open the course](backups-course/index.html){ .md-button .md-button--primary }

</div>

!!! tip "How it works"
    The instructions are on the left, and the real file is on the right. Select
    **Continue** or press the arrow keys to move through a lesson. The diagrams
    animate without input. Nothing you do in the course changes the cluster.

!!! note "Where to go after the course"
    The course is an introduction. For the full reference, read
    [kopiur backup architecture](../domains/storage/kopiur-backup-architecture.md) and
    [storage architecture](../storage-architecture.md).
