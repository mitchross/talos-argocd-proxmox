# The kopiur playground

This page is a browser simulation of how a backed-up PVC behaves in this cluster.
Use it to see restore-before-bind work, and fail safely, without a cluster. It is
for anyone who has read [the easy guide](easy-guide.md) and wants to test the idea.

A PVC is the request an app makes for a disk. Every backed-up PVC here follows
one small state machine. kopiur backs it up on a cron schedule. When the PVC is
recreated, one of three things happens:

| State of the Kopia repository | What the PVC does |
|---|---|
| Reachable, and a snapshot exists | It restores the snapshot, then binds with data. |
| Reachable, and no snapshot exists | It binds empty. |
| Unreachable | It stays `Pending` until the backend returns. It never binds empty. |

The simulation uses the state machine from
[kopiur backup architecture](domains/storage/kopiur-backup-architecture.md). It is
not a real cluster.

<div id="kopiur-playground"></div>

## Five experiments to run

1. Day zero. Click `Sync app from Git` with an empty repository. The PVC binds
   empty, and backups start from there (`onMissingSnapshot: Continue`). Then click
   `Run backup now` and note the file count.
2. Restore on recreate. With a snapshot in the repository, click `Delete the PVC`.
   The PVC goes `Pending` and then binds with data. You do nothing by hand.
3. The safety property. Click `Take S3 offline`, then `Delete the PVC`. The PVC
   stays `Pending`, retries, and does not bind empty. Bring S3 back and watch the
   restore finish. Every other part of the design depends on this behavior.
4. The missing `dataSourceRef`. Clear the `dataSourceRef` box in the Git panel,
   then click `Delete the PVC`. **The PVC is recreated empty, although the
   snapshots still exist.** Without a `dataSourceRef`, there is no restore.
5. The full rebuild. Click `Nuke the cluster`. Git and the repository survive,
   the sync waves run in order, and the app comes back with its data. This is the
   rebuild that [the easy guide](easy-guide.md#the-short-version) describes.

One more experiment: back up an empty volume, then restore it. The restore gives
you the empty volume, because the backup of a fresh instance can replace the
backup of your real data. For that reason, the pre-nuke checklist in
[disaster recovery](disaster-recovery.md) tells you to verify snapshots first.

## What the simulation matches

- The Kubernetes volume populator contract. When a PVC has a `dataSourceRef`, it
  does not bind until the populator finishes.
- The kopiur setting `onMissingSnapshot: Continue`, which means deploy or restore.
  kopiur checks for a backend error before it makes that decision, so it never
  binds empty when the repository is unreachable.
- The backup steps. kopiur takes a CSI snapshot first, and then a mover Job runs.
  When the repository is unreachable, the Job fails and retries, and it writes
  nothing.
- The role of Argo CD. It recreates objects from Git, and app health controls the
  sync waves.

## What the simulation leaves out

The simulation does not model real timings, Longhorn attach and detach states, or
apps with more than one PVC. It also does not model mover permission failures.
[Mover permissions](domains/storage/kopiur-mover-permissions.md) covers those.

## Where the idea came from

[Webernetes](https://github.com/ngrok/webernetes) from ngrok inspired this page.
Webernetes is a Kubernetes written in TypeScript that runs in your browser. It
models pods and Deployments but has no volumes, and this page is about volumes.
