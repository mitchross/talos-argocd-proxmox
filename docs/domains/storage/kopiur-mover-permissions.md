# Why the kopiur mover runs as the data owner (file permissions)

> If a `Snapshot` fails with `PermissionDenied` or "unable to open
> file ... permission denied", this is why. The fix is one field.

## TL;DR

The kopiur mover is the short-lived pod that reads your PVC and copies it to the repository. It must run as the user that owns the data on disk, not as root. Set it per PVC in the stub:

```yaml
mover:
  securityContext: { runAsUser: 1000, runAsGroup: 1000, runAsNonRoot: true }
  podSecurityContext: { fsGroup: 1000, supplementalGroups: [1000] }
```

Find the right number with:
`kubectl -n <ns> exec <pod> -- stat -c '%u:%g' <data-mountpath>`

## In plain English

The backup tool doesn't copy your files itself. It starts a small temporary helper, the mover. The mover reads your app's files and copies them to backup storage.

On Linux, a user owns every file. That user is just a number, a "UID". To read a file you must be its owner, be in its group, or the file must be open to everyone. Normally root can read everything, like a building superintendent with a master key.

The cluster takes the master key away from the mover, on purpose, for security. So even a mover that runs "as root" is a declawed root. It can only read files it owns, like any normal user. kopiur's `privilegedMode` setting sounds like it would give the key back, but it doesn't. It only matters when restoring, not when reading.

A declawed-root mover that tries to read your app's data, owned by some normal user, gets "permission denied." The fix is to run the mover as the same user that owns the files. If user `1000` owns the data, run the mover as `1000`. It then owns the files and reads them fine, with no master key.

## The technical version

- Under Pod Security Admission `baseline`, which every app namespace enforces here, the mover pod runs with `securityContext.capabilities: drop: ["ALL"]`. That strips `CAP_DAC_READ_SEARCH` and `CAP_DAC_OVERRIDE`, the capabilities that let root bypass file-permission checks. So `runAsUser: 0` with capabilities dropped is a root UID with **no** permission-bypass power.
- kopiur's `mover.privilegedMode: true` does **not** add capabilities. The pod still runs `drop: ["ALL"]`. The setting only governs chown-on-restore, which re-creates original ownership when writing files back. It does nothing for the read path during a backup.
- So the mover can only read a file in three cases. Its UID owns the file. Its GID is the file's group and the file is group-readable. Or the file is world-readable. Mode-`600` or `700` files owned by another UID are unreadable and give `PermissionDenied`.

### Choosing the mover identity

```text
 Who owns the data files?   (stat -c '%u:%g' <path>)
 │
 ├─ same UID the pod runs as ──────────► [OK]  inheritSecurityContextFrom: pvcConsumer
 │  (most bjw-s / single-UID apps)              (backup only — restores have no pod
 │                                               to inherit from)
 │
 ├─ pod runs root but data isn't ──────► [OK]  explicit securityContext = data-owner UID:GID
 │  (daemon-drop, e.g. mysql 999:568)
 │
 ├─ root-owned data (0:0) ─────────────► [WARN] runAsUser: 0 + privileged-movers
 │                                               namespace annotation
 │
 ├─ several owners, files ─────────────► [OK]  supplementalGroups: [gid]
 │  group-readable (g+r)
 │
 └─ several owners AND 600/700 modes ──► [STOP] consolidate ownership — or
                                                CAP_DAC_READ_SEARCH + privileged PSS
                                                (last resort)
```

1. **`inheritSecurityContextFrom.pvcConsumer`** (recommended for backup). kopiur copies the security context of the pod that mounts the PVC. This works when the pod's UID equals the data owner, as in most bjw-s and single-UID apps.
2. **Explicit `securityContext` set to the data owner.** Use this when inherit can't give the right answer:
   - **Daemon-drop apps.** Some images start as root, then drop to another user to write data. Example: in mysql the pod runs as root, but `999:568` owns the database files. Inherit would copy root and fail. Set `runAsUser: 999, runAsGroup: 568` explicitly.
   - **Restore (cold DR).** During restore-before-bind there is no consumer pod to inherit from. The `Restore` mover always needs an explicit UID, or `runAsUser: 0` + `privilegedMode: true`. The second option uses root and chown to rebuild original ownership.
3. **`supplementalGroups: [<gid>]`** lets the mover read files owned by other UIDs, as long as they are group-readable (mode `g+r`, for example `660`). Use it for volumes with a few different owners that share a group.

### The genuinely hard case

Some volumes have mixed owners and owner-only modes. These are `700` or `600` files owned by several different UIDs, as in docker-mailserver and some nextcloud layouts. No single UID can read all of them, and group membership doesn't help. You have two options:

- **Consolidate ownership** to one UID/GID (for example everything `1000:1000`). This is the cleanest option. It makes `inheritSecurityContextFrom.pvcConsumer` work.
- **Give the mover the master key back.** Add `CAP_DAC_READ_SEARCH` to the mover `securityContext.capabilities.add`. `baseline` PSS rejects this, so you must raise that namespace to `privileged` Pod Security. This is the escape hatch for apps you can't consolidate. It relaxes that namespace.

## How this cluster does it

- The shared `kopiur-backup` Kustomize component injects the uniform fields: repository, copyMethod, populator, schedule defaults. It deliberately does **not** set the mover, because the UID varies per PVC.
- Each per-PVC stub sets its own mover `securityContext` to the data owner. UIDs in use here: `568` (open-webui, perplexica, immich, qdrant, copyparty, frigate, restore-canary), `1000` (paperless, flatnotes, zomboid, homepage, jellyfin, gitea), `1001` (karakeep), `999:568` (mysql), `0:0` (home-assistant, tubesync, nginx).

Examples to copy:
- Component: [`my-apps/common/kopiur-backup/kustomization.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/common/kopiur-backup/kustomization.yaml)
- Simple single-UID case: [`my-apps/ai/open-webui/kopiur/storage.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/open-webui/kopiur/storage.yaml) (uid `568`)
- Daemon-drop case (mysql): [`my-apps/knowledge/_archive/project-nomad/mysql/kopiur-backup.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/knowledge/_archive/project-nomad/mysql/kopiur-backup.yaml) (uid `999:568`)
- Root-owned case: [`my-apps/home-automation/home-assistant/kopiur/config.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/home-automation/home-assistant/kopiur/config.yaml) (uid `0`, + namespace privileged-movers annotation)

See also: [`my-apps/CLAUDE.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/CLAUDE.md) "Application with
Persistent Storage + Backups" and [`.claude/commands/add-backup.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/.claude/commands/add-backup.md).
