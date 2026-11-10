# Why the kopiur mover runs as the data owner

Read this page when a `Snapshot` fails with `PermissionDenied` or
"unable to open file ... permission denied". It also tells you which user ID to
put in a new stub, the per-PVC backup file `kopiur/<pvc>.yaml`.

## The short answer

The mover is the short-lived Job that kopiur starts to copy a PVC's data to or
from the Kopia repository. It must run as the user that owns the files on the
disk. Running it as root does not help. Set the owner in the stub, for both the
`SnapshotPolicy` and the `Restore`:

```yaml
mover:
  securityContext: { runAsUser: 1000, runAsGroup: 1000, runAsNonRoot: true }
  podSecurityContext: { fsGroup: 1000, supplementalGroups: [1000] }
```

Find the owner of the data with this command:

`kubectl -n <ns> exec <pod> -- stat -c '%u:%g' <data-mountpath>`

The output is `UID:GID`, for example `1000:1000`. Use those two numbers.

## Why root cannot read the files

On Linux, every file has an owner. The owner is a number, the UID. A process
can read a file in three cases:

- The process UID owns the file.
- The process GID is the file's group, and the file is group-readable.
- The file is readable by everyone.

Root normally skips these checks. Two Linux capabilities give root that right:
`CAP_DAC_READ_SEARCH` and `CAP_DAC_OVERRIDE`.

Every app namespace here enforces the Pod Security Admission level `baseline`.
Under `baseline`, the mover pod runs with
`securityContext.capabilities: drop: ["ALL"]`. That removes both capabilities.
A mover with `runAsUser: 0` is then a root UID that must pass the same three
checks as any other user.

A mover that runs as root therefore gets `PermissionDenied` on files with mode
`600` or `700` that another UID owns. A mover that runs as the owner reads them.

kopiur's `mover.privilegedMode: true` does not add capabilities. The pod still
runs with `drop: ["ALL"]`. The setting controls only the ownership change on
restore, where the mover sets the original owner on the files it writes back.
It does nothing for reading during a backup.

## Choose the mover identity

```text
 Who owns the data files?   (stat -c '%u:%g' <path>)
 │
 ├─ same UID the pod runs as ──────────► [OK]  explicit securityContext = that UID:GID
 │  (most bjw-s / single-UID apps)
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
 └─ several owners AND 600/700 modes ──► [STOP] consolidate ownership, or
                                                CAP_DAC_READ_SEARCH + privileged PSS
                                                (last resort)
```

The cases, from most common to least common:

1. **One owner, same as the app pod.** Set the mover `securityContext` to that
   UID:GID. Most apps are in this group.
2. **The pod starts as root, then switches user.** Some images start as root and
   change to another user before they write data. In mysql the pod runs as root,
   but `999:568` owns the database files. Set `runAsUser: 999, runAsGroup: 568`.
3. **Root owns the data (`0:0`).** Set `runAsUser: 0` and add the
   `privileged-movers` annotation to the namespace. Use this only for data that
   root owns. Do not use root to work around a permission error.
4. **A few owners that share a group.** Add `supplementalGroups: [<gid>]`. The
   mover can then read files that other UIDs own, if the files are
   group-readable (mode `g+r`, for example `660`).
5. **Several owners and owner-only modes.** See the next section.

kopiur also has `inheritSecurityContextFrom.pvcConsumer`, which copies the
security context of the pod that mounts the PVC. This cluster does not use it.
During restore-before-bind there is no app pod to copy from, so the `Restore`
mover always needs an explicit UID. The alternative for a `Restore` is
`runAsUser: 0` with `privilegedMode: true`, which uses root to set the original
ownership.

### Several owners and owner-only modes

Some volumes hold `700` or `600` files that several different UIDs own.
docker-mailserver and some nextcloud layouts work this way. No single UID can
read every file, and a shared group does not help. You have two options:

- Change the ownership of all files to one UID:GID, for example `1000:1000`.
  Prefer this option. The volume then fits case 1.
- Add `CAP_DAC_READ_SEARCH` to the mover's `securityContext.capabilities.add`.
  The `baseline` level rejects this, so you must raise that namespace to the
  `privileged` Pod Security level. This lowers the security of the whole
  namespace. Use it only for an app whose ownership you cannot change.

## How this cluster sets it

The shared `kopiur-backup` Kustomize component adds the fields that are the same
for every PVC: the Kopia repository, the copy method, the restore settings, and
the schedule defaults. It does not set the mover, because the UID differs per PVC.

Each stub sets its own mover `securityContext`. These UIDs are in use:

| Mover UID:GID | Examples |
|---|---|
| `568` | open-webui, immich library, copyparty, restore-canary |
| `1000` | paperless, jellyfin, gitea shared storage, homepage, deal-scout |
| `1001` | karakeep |
| `999` | plain Postgres databases (the official `postgres` image) |
| `0` | home-assistant, tubesync, nginx, frigate, perplexica |

Examples to copy:

- Component: [`my-apps/common/kopiur-backup/kustomization.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/common/kopiur-backup/kustomization.yaml)
- One owner: [`my-apps/ai/open-webui/kopiur/storage.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/open-webui/kopiur/storage.yaml) (uid `568`)
- Pod starts as root, data owned by another user (mysql): [`my-apps/knowledge/_archive/project-nomad/mysql/kopiur-backup.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/knowledge/_archive/project-nomad/mysql/kopiur-backup.yaml) (uid `999:568`)
- Root-owned data: [`my-apps/home-automation/home-assistant/kopiur/config.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/home-automation/home-assistant/kopiur/config.yaml) (uid `0`, plus the namespace `privileged-movers` annotation)

For the full procedure, see
[`.claude/commands/add-backup.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/.claude/commands/add-backup.md)
and the "Application with Persistent Storage + Backups" section of
[`my-apps/CLAUDE.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/CLAUDE.md).
