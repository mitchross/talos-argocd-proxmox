# Immich — Self-Hosted Photos

Immich photo/video library running on K8s with CloudNativePG, Valkey, and
a read-only NFS mount pointing at the TrueNAS photo archive. The original
photos stay on the NAS as the source of truth — Immich only writes
thumbnails, ML embeddings, and DB rows.

## Architecture

```
 User → https://photos.vanillax.me (gateway-internal, HTTPS)
       │
       ▼
 immich-server (Deployment)  ──── reads /mnt/photos (RO, NFS)
       │
       ├── Postgres (CNPG) ──── Longhorn PVC (20Gi) + Barman → RustFS S3
       ├── Valkey (Redis-ish) ─ ephemeral
       ├── immich-machine-learning (Deployment, co-located via podAffinity)
       │      └── ML cache PVC (10Gi, Longhorn) — CLIP + face detection models
       └── library PVC (50Gi, Longhorn) — thumbnails, previews, transcoded video
```

Co-location: `immich-machine-learning` has a `podAffinity` on the server
pod's hostname. They run on the same node so the server can hit the ML
service on localhost / pod-network with no extra hops. No
`runtimeClassName: nvidia` — ML runs on CPU here (set the nodeSelector +
runtimeClass if you move it to a GPU worker).

## Storage breakdown

| Data                        | Location                          | Size / Reclaim |
|-----------------------------|-----------------------------------|----------------|
| Original photos/videos      | TrueNAS NFS (read-only, static PV)| ~1.27 TiB (source of truth) |
| Thumbnails + previews       | `library` PVC (Longhorn RWO)      | 50Gi           |
| ML models (CLIP + face)     | `immich-ml-cache` PVC (Longhorn)  | 10Gi           |
| DB (metadata, embeddings)   | Immich CNPG cluster (Longhorn PVC) | 20Gi           |
| DB WAL + base backups       | RustFS S3 (`cnpg` bucket, Barman) | rolling, ~daily |

> ⚠️ **Do NOT add `backup: "daily"` labels to the CNPG PVC.** CNPG uses
> Barman to S3 for DR, not Kyverno/VolSync. Mixing both layers is a known
> footgun — see `infrastructure/database/CLAUDE.md`.

The `library` PVC is not currently VolSync-backed. It's large and the
contents are regenerable from originals + DB (see `docs/cnpg-disaster-recovery.md`
for the full recovery flow). Enable later if re-generating thumbnails for
1.27 TiB of photos on every rebuild starts to feel slow.

## NFS static PV — why not dynamic

The `nfs-immich-photos` PV is defined in
`infrastructure/storage/csi-driver-nfs/storage-class.yaml`. It's a
**static** PV, not a dynamic one, because:

- Dynamic NFS CSI creates a *new subdirectory per PVC*. That's fine for
  volumes that start empty, but we're mounting **existing data**.
- A static PV points directly at the existing share
  (`192.168.10.133:/mnt/BigTank/photos/All`) with no subdirectory.
- Mount options (`ro`, `nfsvers`, `nconnect`, …) only get honored when
  using the CSI driver. Don't use the legacy `nfs:` block — mountOptions
  silently fail there.

Mount spec:
- **Server:** `192.168.10.133`
- **Share:** `/mnt/BigTank/photos/All`
- **Mode:** read-only (`ro` mount option)
- **In-pod path:** `/mnt/photos` on both `immich-server` and `immich-machine-learning`

## Database — Postgres via CNPG

Manifests: `infrastructure/database/cloudnative-pg/immich/`

- **Image:** `ghcr.io/tensorchord/cloudnative-vectorchord:17.5-0.4.3` (Postgres 17.5 + VectorChord 0.4.3)
- **Extensions:** `vchord` (CASCADE-installs pgvector), `vector`, `earthdistance` (CASCADE-installs cube)
- **Service:** `immich-database-rw.cloudnative-pg.svc.cluster.local:5432`
- **Creds:** ExternalSecret pulls `immich-db-credentials` (immich ns) + `immich-app-secret` (cnpg ns) from 1Password
- **Backups:** Barman → RustFS S3 (`192.168.10.133:30293`). Daily base backup at **02:00**, continuous WAL archival.

### Why CNPG and not CrunchyData PGO

PGO uses Patroni for HA. Patroni's DCS (leader election) corrupts when
pods are hard-killed — exactly what happens during a Talos
upgrade/reboot on a single-replica homelab cluster. The corruption
manifests as a standby loop that doesn't self-heal. CNPG has no Patroni,
no leader election, just a primary + optional standbys + Barman. Simpler
recovery, no Patroni DCS to unstick.

## Deploying

ArgoCD picks this up automatically via the my-apps AppSet. Files:

| File | Purpose |
|------|---------|
| `namespace.yaml` | `immich` namespace |
| `kustomization.yaml` | Ties everything together (also generates config ConfigMap) |
| `deployment-server.yaml` | Immich API/web server. OTEL Node.js auto-instrumentation annotated. Uses `RollingUpdate` because it's the only RWO PVC it touches is the `library` volume in RWX-ish mode (ReadWriteOncePod on Longhorn still allows same-node re-mount) — watch for Multi-Attach if you scale replicas. |
| `deployment-machine-learning.yaml` | Immich ML. Co-located via `podAffinity` on server hostname. |
| `deployment-valkey.yaml` | Redis-compatible cache. Ephemeral. |
| `services.yaml` | Three ClusterIPs — named ports matter for HTTPRoute + Prometheus scrape. |
| `httproute.yaml` | **Internal** HTTPRoute → `photos.vanillax.me` via `gateway-internal`. No Cloudflare tunnel — LAN only. |
| `library-pvc.yaml` | 50Gi Longhorn PVC. |
| `ml-cache-pvc.yaml` | 10Gi Longhorn PVC. |
| `nfs-photos-pvc.yaml` | Claims the static NFS PV. |
| `externalsecret.yaml` | Pulls DB creds, JWT secret, etc. from 1Password. |

## Initial setup (first deploy)

Immich doesn't auto-create an admin. First run:

1. Port-forward the UI (or use the HTTPRoute once DNS is live):
   ```bash
   kubectl port-forward -n immich svc/immich-server 2283:2283
   # open http://localhost:2283
   ```
2. The first page is **"Getting Started" → admin account creation**.
   Pick your admin email + password. **This account cannot be recovered
   without DB access** — store the password in 1Password before you forget.
3. Log in. You'll be prompted to invite other users if you want.
4. **Add the external library:**
   - `Administration → External Libraries → Create Library`
   - Import path: `/mnt/photos`
   - Owner: the admin (or any user)
   - **Scan schedule: every 6 hours** (or whatever cadence matches your
     upload pattern). inotify does NOT work over NFS — you must poll.
5. Click **Scan**. The library enters "scanning" state immediately but
   doesn't start generating thumbnails until it finishes the initial
   file walk.

## What to expect on first ML scan

On a 1.27 TiB library with ~100k photos/videos, expect:

| Phase                      | Duration (rough, CPU-only ML) |
|----------------------------|-------------------------------|
| File discovery walk        | 30 min – 2 hr                 |
| Thumbnail + preview gen    | **1–3 days**                   |
| CLIP embeddings (search)   | 2–5 days                      |
| Face detection + clustering| 3–7 days                      |

The ML service runs per-photo, not per-batch-blast, so throughput is
bounded by CPU. If it feels stuck, check
`kubectl logs -n immich deploy/immich-machine-learning` — it logs each
processed file.

Accelerate:
- Move `immich-machine-learning` to the GPU worker (add nodeSelector +
  `runtimeClassName: nvidia` + GPU resource request). Will need to
  coordinate with llama-cpp/ComfyUI priority — pick `gpu-workload-preemptible`.
- Bump the ML `concurrency` in Immich's server settings (Admin →
  Settings → Jobs).

## Networking

- **HTTPRoute:** `photos.vanillax.me` via `gateway-internal` (HTTPS).
  **Not public** — LAN-only, no Cloudflare tunnel.
- **Cilium policy:** NFS traffic to TrueNAS (port 2049 TCP/UDP) is
  allowed in `block-lan-access.yaml`. Without that exemption the
  default-deny egress would kill the photo mount.
- **Database:** server + ML pods connect to
  `immich-database-rw.cloudnative-pg` on 5432 (Cilium allows intra-cluster
  traffic by default; no explicit rule needed for in-cluster services).

## Gotchas

- **No file watching over NFS.** Periodic scan only (set in Immich UI).
  Any kernel that tells you it supports `inotify` over NFS is lying.
- **Read-only NFS mount.** Edits in the Immich UI (rotate, delete, move)
  won't touch originals on TrueNAS. Deletes happen inside Immich's DB
  only; the file on NAS stays. If you want true deletion, delete on
  the NAS, then re-scan.
- **Moving files on NAS breaks associations.** Immich tracks by path,
  not content hash. Rename a folder on TrueNAS and Immich sees the old
  photos as deleted + new photos as new — losing albums, likes, face
  assignments. Use the Immich UI move, or accept the re-scan cost.
- **RWO on Longhorn means Deployment strategy matters.** If you scale
  `immich-server` beyond 1 replica, switch to `strategy: Recreate`
  (or use `ReadWriteMany`). The default `RollingUpdate` will deadlock
  on Multi-Attach.
- **Deleting the namespace ≠ deleting your photos.** The NFS mount is
  read-only and points at the NAS. But it **does** delete the `library`
  PVC (thumbnails) and the CNPG cluster (DB, including face tags and
  albums). Don't delete the namespace casually.

## Recovery / DR

See [`docs/cnpg-disaster-recovery.md`](../../../docs/cnpg-disaster-recovery.md)
for the authoritative DR procedure (rewritten against the April 2026
CNPG clean-slate baseline). Summary:

1. NFS share survives — originals are safe as long as TrueNAS survives.
2. CNPG cluster restores from Barman S3 — brings back metadata, album
   structure, face tags.
3. `library` PVC is empty on rebuild — Immich will regenerate thumbnails
   on next scan (slow, see timing table above). No data loss, just
   compute to rebuild.
