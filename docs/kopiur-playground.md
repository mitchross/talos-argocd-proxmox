# Interactive: the kopiur playground

Every backed-up PVC in this cluster follows one small state machine. It backs up on a cron. On any recreate, it does one of three things:

- Restores if a snapshot exists.
- Binds empty if the repository is reachable but has nothing.
- Holds `Pending` forever if the backend is down.

Here you can trigger each case yourself.

This is a simulation of the exact state machine in [kopiur backup architecture](domains/storage/kopiur-backup-architecture.md). It is not a real cluster. Ngrok's [Webernetes](https://github.com/ngrok/webernetes) inspired it. Webernetes is a TypeScript Kubernetes that runs in your browser. It suits pods and Deployments, but it has no volumes, and volumes are the whole story here.

<div id="kopiur-playground"></div>

## Five experiments worth running

1. **Day zero.** Click `Sync app from Git` on an empty repository. The PVC binds empty and backs up forward (`onMissingSnapshot: Continue`). Then click `Run backup now` and note the file count.
2. **Restore on recreate.** With a snapshot in the repository, click `Delete the PVC`. The PVC goes `Pending`, then binds with data. No human steps.
3. **The safety property.** Click `Take S3 offline`, then `Delete the PVC`. The PVC holds `Pending`, retries, and refuses to bind empty. Bring S3 back and watch it finish. Everything else depends on this guarantee.
4. **The DR gap.** Untick `dataSourceRef` in the Git panel, then click `Delete the PVC`. The PVC recreates **EMPTY** even though your snapshots still exist. This is the most important rule: no `dataSourceRef`, no restore.
5. **The full story.** Click `Nuke the cluster`. Git and the repository survive, the waves run in order, and the app comes back with its data. This is the 30-second pitch of [the easy guide](easy-guide.md), animated.

Bonus: back up an empty volume, then restore it. You will see why "the fresh instance's own backup can bury your real one". It also shows why the pre-nuke checklist says to verify snapshots first.

## What the simulation matches

- The Kubernetes volume-populator contract. With `dataSourceRef` present, binding waits until the populator finishes.
- kopiur's `onMissingSnapshot: Continue` (deploy-or-restore). Also its backend-error-before-decision ordering, so it never binds empty over a dead repository.
- Backup mechanics. A CSI snapshot comes first. Then a mover Job runs. Against an unreachable repository it fails and retries without writing garbage.
- ArgoCD's role. It recreates from Git, and app health gates the sync waves.

It skips real timings, Longhorn attach and detach states, and multi-PVC apps. It also skips mover permission failures, which [mover permissions](domains/storage/kopiur-mover-permissions.md) covers.
