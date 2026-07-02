# Interactive: the kopiur playground

Every backed-up PVC in this cluster lives inside one small state machine —
backup on a cron, and on any recreate: **restore if a snapshot exists, bind
empty if the repo is reachable but has nothing, hold `Pending` forever if the
backend is down**. Reading about it is one thing; here you can pull the levers
yourself.

This is a **simulation of the exact state machine** documented in
[kopiur backup architecture](domains/storage/kopiur-backup-architecture.md) —
not a real cluster. (Idea sparked by ngrok's
[Webernetes](https://github.com/ngrok/webernetes), a TypeScript Kubernetes
that runs in your browser — brilliant for interactive pods-and-Deployments
content, but it has no volumes, and volumes are the whole story here.)

<div id="kopiur-playground"></div>

## Five experiments worth running

1. **Day zero.** `Sync app from Git` on an empty repo → the PVC binds
   **empty** and backs up forward (`onMissingSnapshot: Continue`). Then
   `Run backup now` and note the file count.
2. **The money shot.** With a snapshot in the repo, `Delete the PVC` → watch
   it come back `Pending` → **bound with data**. No human steps.
3. **The safety property.** `Take S3 offline`, then `Delete the PVC` → it
   holds `Pending` and retries, refusing to bind empty. Bring S3 back and
   watch it finish. *This is the guarantee everything else is built on.*
4. **The DR gap.** Untick `dataSourceRef` in the Git panel, then
   `Delete the PVC` → it recreates **EMPTY** even though your snapshots still
   exist. This is the #1 rule: no `dataSourceRef`, no restore.
5. **The full story.** `Nuke the cluster` → Git and the repo survive, the
   waves walk, and the app comes back with its data — the 30-second pitch of
   [the easy guide](easy-guide.md), animated.

Bonus: back up an **empty** volume and then restore it — the playground lets
you experience why "the fresh instance's own backup can bury your real one"
(and why the pre-nuke checklist insists on verifying snapshots first).

## What the simulation is faithful to

- The Kubernetes volume-populator contract: `dataSourceRef` present →
  binding withheld until the populator finishes.
- kopiur's `onMissingSnapshot: Continue` (deploy-or-restore) and its
  backend-error-before-decision ordering (never bind empty over a dead repo).
- Backup mechanics: CSI snapshot first, then a mover Job that fails-and-retries
  against an unreachable repo without writing garbage.
- ArgoCD's role: recreating from Git, and app health gating the sync waves.

What it skips: real timings, Longhorn attach/detach states, mover permission
failures (see [mover permissions](domains/storage/kopiur-mover-permissions.md)
for that story), and multi-PVC apps.
