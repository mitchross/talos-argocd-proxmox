# Zero-Touch PVC Backup/Restore: The Complete Picture

## From Bare Metal to Automatic Disaster Recovery

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                            BARE METAL / PROXMOX VMs                                 │
│                                                                                     │
│                     New cluster, no Kubernetes, nothing running                     │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ Omni provisions cluster
                                          │ (Sidero Proxmox Provider)
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                              TALOS OS RUNNING                                       │
│                                                                                     │
│              Immutable Linux, Kubernetes API available, no CNI yet                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ kubectl apply (Gateway API CRDs)
                                          │ kubectl apply (Cilium CNI)
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                            NETWORKING READY                                         │
│                                                                                     │
│                    Cilium running, pods can communicate                             │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ kubectl create secret (1Password creds)
                                          │ kustomize build infrastructure/controllers/argocd | kubectl apply
                                          │ kubectl apply -f root.yaml
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                         ARGOCD BOOTSTRAPPED                                         │
│                                                                                     │
│              ArgoCD running, root.yaml applied, GitOps loop begins                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │
                    ══════════════════════════════════════════════
                    ║  FROM HERE, EVERYTHING IS AUTOMATIC (GitOps) ║
                    ══════════════════════════════════════════════
                                          │
                                          ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                                     ┃
┃                        WAVE 0: FOUNDATION                                           ┃
┃                                                                                     ┃
┃  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐         ┃
┃  │   1Password Connect │  │  External Secrets   │  │   Cilium (if not    │         ┃
┃  │                     │  │     Operator        │  │   already applied)  │         ┃
┃  │  Connects to 1Pass  │  │                     │  │                     │         ┃
┃  │  cloud/local vault  │  │  Watches for        │  │  CNI + Gateway API  │         ┃
┃  │                     │  │  ExternalSecret CRs │  │  + LoadBalancer     │         ┃
┃  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘         ┃
┃                                                                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                                          │
                                          ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                                     ┃
┃                        WAVE 1: STORAGE                                              ┃
┃                                                                                     ┃
┃  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐         ┃
┃  │      Longhorn       │  │  Snapshot Controller│  │      VolSync        │         ┃
┃  │                     │  │                     │  │                     │         ┃
┃  │  Distributed block  │  │  VolumeSnapshot     │  │  Replicates PVCs    │         ┃
┃  │  storage for PVCs   │  │  CRDs + controller  │  │  via Kopia to NFS   │         ┃
┃  │                     │  │                     │  │                     │         ┃
┃  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘         ┃
┃                                                                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                                          │
                                          ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                                     ┃
┃                        WAVE 2: PVC PLUMBER                                          ┃
┃                                                                                     ┃
┃  ┌─────────────────────────────────────────────────────────────────────┐             ┃
┃  │    pvc-plumber (backup existence checker)                          │             ┃
┃  │                                                                     │             ┃
┃  │    Mounts TrueNAS NFS share at /repository                         │             ┃
┃  │    Uses Kopia CLI to check for existing backups                     │             ┃
┃  │    Provides JSON API for Kyverno to query                           │             ┃
┃  │    Must be running BEFORE Wave 4 (Kyverno policies call it)         │             ┃
┃  └─────────────────────────────────────────────────────────────────────┘             ┃
┃                                                                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                                          │
                                          ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                                     ┃
┃                        WAVE 4: INFRASTRUCTURE (ApplicationSet)                      ┃
┃                                                                                     ┃
┃  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐         ┃
┃  │     Cert-Manager    │  │      Kyverno        │  │    External-DNS     │         ┃
┃  │                     │  │                     │  │                     │         ┃
┃  │  TLS certificates   │  │  Policy engine      │  │  DNS automation     │         ┃
┃  │  Let's Encrypt      │  │  Mutates PVCs       │  │  via Cloudflare     │         ┃
┃  │                     │  │  Generates VolSync  │  │                     │         ┃
┃  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘         ┃
┃                                                                                     ┃
┃  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐         ┃
┃  │   CloudNativePG     │  │    GPU Operator     │  │      Gateway        │         ┃
┃  │                     │  │    (if needed)      │  │                     │         ┃
┃  │  PostgreSQL         │  │                     │  │  Gateway API        │         ┃
┃  │  clusters           │  │  NVIDIA drivers     │  │  + HTTPRoutes       │         ┃
┃  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘         ┃
┃                                                                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                                          │
                                          ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                                     ┃
┃                        WAVE 5: MONITORING (ApplicationSet)                          ┃
┃                                                                                     ┃
┃  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐         ┃
┃  │  kube-prometheus    │  │      Grafana        │  │      Loki           │         ┃
┃  │     stack           │  │                     │  │                     │         ┃
┃  │                     │  │  Dashboards         │  │  Log aggregation    │         ┃
┃  │  Prometheus +       │  │  Visualization      │  │                     │         ┃
┃  │  AlertManager       │  │                     │  │                     │         ┃
┃  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘         ┃
┃                                                                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                                          │
                                          ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                                     ┃
┃                        WAVE 6: MY APPS (ApplicationSet)                             ┃
┃                                                                                     ┃
┃  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐             ┃
┃  │ karakeep  │ │home-asst. │ │  jellyfin │ │   plex    │ │ paperless │  ...        ┃
┃  └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘             ┃
┃                                                                                     ┃
┃        Each app has PVCs with label: backup: "hourly" or backup: "daily"           ┃
┃                                                                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                                          │
                                          │
                    ══════════════════════════════════════════════
                    ║     NOW THE MAGIC HAPPENS: PVC CREATION     ║
                    ══════════════════════════════════════════════
                                          │
                                          ▼

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│  APP CREATES PVC                                                                    │
│                                                                                     │
│  apiVersion: v1                                                                     │
│  kind: PersistentVolumeClaim                                                        │
│  metadata:                                                                          │
│    name: data-pvc                                                                   │
│    namespace: karakeep                                                              │
│    labels:                                                                          │
│      backup: "hourly"                 <--- THIS LABEL TRIGGERS EVERYTHING           │
│  spec:                                                                              │
│    accessModes: [ReadWriteOnce]                                                     │
│    storageClassName: longhorn                                                       │
│    resources:                                                                       │
│      requests:                                                                      │
│        storage: 10Gi                                                                │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ kubectl apply (via ArgoCD sync)
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│  KYVERNO ADMISSION WEBHOOK INTERCEPTS                                               │
│                                                                                     │
│  "I see a PVC with backup: hourly (or daily)"                                      │
│                                                                                     │
│  Step 1: Validate rule checks PVC Plumber health (FAIL-CLOSED)                     │
│  ┌────────────────────────────────────────────────────────────────────────────┐    │
│  │  HTTP GET http://pvc-plumber.volsync-system/readyz                        │    │
│  │  If unreachable -> DENY PVC creation (apps retry via ArgoCD backoff)      │    │
│  │  If healthy -> proceed to step 2                                          │    │
│  └────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                     │
│  Step 2: Mutate rule checks if backup exists                                       │
│  ┌────────────────────────────────────────────────────────────────────────────┐    │
│  │  HTTP GET http://pvc-plumber.volsync-system/exists/karakeep/data-pvc      │    │
│  └────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│  PVC-PLUMBER SERVICE                                                                │
│                                                                                     │
│  Receives: GET /exists/karakeep/data-pvc                                           │
│                                                                                     │
│  Queries Kopia repository on NFS:                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐    │
│  │  Checks /repository (NFS mount from 192.168.10.133)                       │    │
│  │  Uses Kopia CLI to look for snapshots matching namespace/pvc-name         │    │
│  └────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                     │
│  Returns JSON to Kyverno:                                                          │
│    {"exists": true}   OR   {"exists": false}                                       │
│                                                                                     │
│  On ANY error (timeout, network, parse) -> {"exists": false}                       │
│  NOTE: Kyverno validate rule DENIES PVC creation if PVC Plumber is unreachable    │
│  (fail-closed). See Scenario 5 below.                                              │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                          ┌───────────────┴───────────────┐
                          │                               │
                          ▼                               ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│                                      │  │                                      │
│  BACKUP EXISTS                       │  │  NO BACKUP                           │
│     (Disaster Recovery)              │  │     (Fresh Install)                  │
│                                      │  │                                      │
│  pvc-plumber returns:                │  │  pvc-plumber returns:                │
│  {"exists": true}                    │  │  {"exists": false}                   │
│                                      │  │                                      │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
                          │                               │
                          ▼                               ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│                                      │  │                                      │
│  KYVERNO MUTATES PVC                 │  │  KYVERNO DOES NOT MUTATE             │
│                                      │  │                                      │
│  Adds to PVC spec:                   │  │  PVC passes through unchanged        │
│  ┌────────────────────────────────┐  │  │                                      │
│  │ dataSourceRef:                 │  │  │  (no dataSourceRef added)            │
│  │   apiGroup: volsync.backube    │  │  │                                      │
│  │   kind: ReplicationDestination │  │  │                                      │
│  │   name: data-pvc-backup        │  │  │                                      │
│  └────────────────────────────────┘  │  │                                      │
│                                      │  │                                      │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
                          │                               │
                          ▼                               ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│                                      │  │                                      │
│  KYVERNO GENERATES (both paths):     │  │  KYVERNO GENERATES (both paths):     │
│                                      │  │                                      │
│  ExternalSecret                      │  │  ExternalSecret                      │
│     (fetches Kopia password          │  │     (fetches Kopia password          │
│      from 1Password "rustfs" item)   │  │      from 1Password "rustfs" item)   │
│                                      │  │                                      │
│  ReplicationSource                   │  │  ReplicationSource                   │
│     (backup schedule: hourly/daily)  │  │     (backup schedule: hourly/daily)  │
│     (waits for PVC Bound + 2h age)   │  │     (waits for PVC Bound + 2h age)   │
│                                      │  │                                      │
│  ReplicationDestination              │  │  ReplicationDestination              │
│     (restore capability)             │  │     (restore capability)             │
│                                      │  │                                      │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
                          │                               │
                          ▼                               ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│                                      │  │                                      │
│  VOLSYNC VOLUME POPULATOR            │  │  LONGHORN PROVISIONS                 │
│                                      │  │                                      │
│  Sees dataSourceRef on PVC           │  │  No dataSourceRef                    │
│  Pulls data from Kopia NFS backup    │  │  Creates empty volume                │
│  Populates volume with restored data │  │                                      │
│                                      │  │                                      │
│  ┌────────────────────────────────┐  │  │  ┌────────────────────────────────┐  │
│  │ NFS: /repository/              │  │  │  │      Empty 10Gi volume         │  │
│  │   karakeep/data-pvc/           │  │  │  │                                │  │
│  │   (Kopia repository with       │  │  │  │                                │  │
│  │    compressed snapshots)       │  │  │  │                                │  │
│  └────────────────────────────────┘  │  │  └────────────────────────────────┘  │
│                                      │  │                                      │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
                          │                               │
                          ▼                               ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│                                      │  │                                      │
│  PVC BOUND WITH RESTORED DATA        │  │  PVC BOUND EMPTY                     │
│                                      │  │                                      │
│  All your files are back!            │  │  Ready for fresh start               │
│                                      │  │                                      │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
                          │                               │
                          └───────────────┬───────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│  POD STARTS                                                                         │
│                                                                                     │
│  App container mounts PVC                                                           │
│  Data is either restored or fresh                                                   │
│  User never knows the difference - it just works!                                   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│  ONGOING: REPLICATIONSOURCE RUNS ON SCHEDULE                                        │
│                                                                                     │
│  Schedule: "0 * * * *" (hourly) or "0 2 * * *" (daily at 2am)                     │
│  Note: Backup only starts after PVC is Bound AND at least 2 hours old              │
│                                                                                     │
│  1. Creates Longhorn snapshot of PVC (copy-on-write, no downtime)                  │
│  2. Mounts snapshot to temporary mover pod                                         │
│  3. Kyverno NFS inject policy adds NFS volume to mover pod automatically           │
│  4. Runs Kopia backup to NFS repository (zstd-fastest compression)                 │
│  5. Prunes old snapshots (retains 24 hourly, 7 daily, 4 weekly, 2 monthly)        │
│  6. Cleans up                                                                       │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                             │   │
│  │   TrueNAS NFS (192.168.10.133:/mnt/BigTank/k8s/volsync-kopia-nfs)        │   │
│  │                                                                             │   │
│  │   Kopia filesystem repositories:                                           │   │
│  │                                                                             │   │
│  │   karakeep/                                                                │   │
│  │   ├── data-pvc/           <-- Your app's data (Kopia repository)           │   │
│  │   └── meilisearch-pvc/    <-- Another PVC from same app                    │   │
│  │                                                                             │   │
│  │   home-assistant/                                                          │   │
│  │   ├── config/                                                              │   │
│  │                                                                             │   │
│  │   jellyfin/                                                                │   │
│  │   ├── config/                                                              │   │
│  │   ...                                                                      │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════
                              THE FOUR SCENARIOS
═══════════════════════════════════════════════════════════════════════════════════════


┌─────────────────────────────────────────────────────────────────────────────────────┐
│ SCENARIO 1: FRESH CLUSTER - FIRST TIME DEPLOYMENT                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  You just built a new cluster from scratch. NFS repository is empty.               │
│                                                                                     │
│  1. ArgoCD syncs your apps                                                         │
│  2. PVC created with backup: "hourly" (or "daily")                                │
│  3. Kyverno calls pvc-plumber                                                      │
│  4. pvc-plumber checks Kopia repo on NFS -> nothing there -> {"exists": false}     │
│  5. Kyverno does NOT add dataSourceRef                                             │
│  6. Longhorn creates empty volume                                                   │
│  7. App starts fresh                                                                │
│  8. After PVC is Bound + 2 hours old, ReplicationSource begins backups             │
│                                                                                     │
│  Result: App starts fresh, backups begin automatically                             │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ SCENARIO 2: DISASTER RECOVERY - CLUSTER REBUILT                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  Your cluster died. You rebuild from scratch. NFS has all your Kopia backups.      │
│                                                                                     │
│  1. New cluster bootstrapped                                                        │
│  2. ArgoCD syncs your apps (same Git repo as before)                               │
│  3. PVC created with backup: "hourly" (or "daily")                                │
│  4. Kyverno calls pvc-plumber                                                      │
│  5. pvc-plumber checks Kopia repo on NFS -> backup exists -> {"exists": true}      │
│  6. Kyverno MUTATES PVC with dataSourceRef                                         │
│  7. VolSync VolumePopulator restores data from Kopia NFS backup                    │
│  8. App starts with ALL YOUR DATA                                                   │
│                                                                                     │
│  Result: Full automatic restore, zero manual intervention                           │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ SCENARIO 3: OOPS I DELETED MY APP                                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  You accidentally deleted an app in ArgoCD, or removed it from Git.                │
│  PVC was deleted. You re-add it.                                                   │
│                                                                                     │
│  Same as Scenario 2:                                                               │
│  1. PVC recreated                                                                   │
│  2. pvc-plumber finds existing backup in Kopia NFS repository                      │
│  3. Data restored automatically                                                     │
│                                                                                     │
│  Result: Your mistake is automatically fixed                                        │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ SCENARIO 4: NEW APP ADDED                                                           │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  You add a brand new app to your cluster that never existed before.                │
│                                                                                     │
│  Same as Scenario 1:                                                               │
│  1. New app synced by ArgoCD                                                        │
│  2. PVC created with backup label                                                   │
│  3. pvc-plumber checks Kopia repo -> no backup -> {"exists": false}                │
│  4. Empty volume created                                                            │
│  5. Backups begin after PVC is Bound + 2 hours old                                 │
│                                                                                     │
│  Result: New app starts fresh, automatically protected going forward               │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ SCENARIO 5: PVC PLUMBER DOWN DURING DISASTER RECOVERY (FAIL-CLOSED)                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  Your cluster died. You rebuild from scratch. NFS has all your Kopia backups.      │
│  But PVC Plumber fails to start (bad config, NFS unreachable, etc.)               │
│                                                                                     │
│  1. New cluster bootstrapped                                                        │
│  2. ArgoCD syncs apps                                                               │
│  3. PVC Plumber (Wave 2) is unhealthy                                              │
│  4. Kyverno (Wave 4) deploys with validate rule                                   │
│  5. Apps (Wave 6) attempt to create PVCs with backup labels                        │
│  6. Kyverno validate rule calls PVC Plumber /readyz -> UNREACHABLE                 │
│  7. PVC creation DENIED                                                             │
│  8. ArgoCD retries with exponential backoff (5s -> 10s -> 20s -> 40s -> 3m)        │
│  9. Operator fixes PVC Plumber                                                     │
│  10. PVC Plumber starts, /readyz returns 200                                       │
│  11. ArgoCD retries -> PVC creates -> pvc-plumber finds backup -> data restored    │
│                                                                                     │
│  Result: Apps wait for PVC Plumber. Data safety over availability.                 │
│          Human intervention required to fix PVC Plumber.                            │
│                                                                                     │
│  Trade-off: Apps with backup labels CANNOT deploy until PVC Plumber is healthy.    │
│  Apps WITHOUT backup labels deploy normally and are unaffected.                     │
│                                                                                     │
│  Why this matters: Without this, apps deploy with empty PVCs and the restore       │
│  window is permanently missed (Kyverno only checks on PVC CREATE).                 │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════
                              COMPONENT SUMMARY
═══════════════════════════════════════════════════════════════════════════════════════


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                              1PASSWORD (Cloud/Local)                                │
│                                                                                     │
│   Item: rustfs                                                                     │
│   └── kopia_password: ****  (encrypts all Kopia repository data)                  │
│                                                                                     │
│   SINGLE SOURCE OF TRUTH for Kopia encryption password                             │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                         EXTERNAL SECRETS OPERATOR                                   │
│                                                                                     │
│   ClusterSecretStore: 1password                                                    │
│   └── Connects to 1Password Connect server                                         │
│                                                                                     │
│   Kyverno-generated ExternalSecret (per PVC):                                      │
│   └── volsync-{pvc-name} in each app namespace                                    │
│       Fetches Kopia password from 1Password "rustfs" item                          │
│       Creates secret with KOPIA_PASSWORD, KOPIA_REPOSITORY, KOPIA_FS_PATH          │
│                                                                                     │
│   ExternalSecret: pvc-plumber-kopia (volsync-system namespace)                     │
│   └── Provides KOPIA_PASSWORD to pvc-plumber                                      │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                      ┌───────────────────┴───────────────────┐
                      ▼                                       ▼
┌──────────────────────────────────┐         ┌──────────────────────────────────────┐
│                                  │         │                                      │
│  PVC-PLUMBER                     │         │  KYVERNO                              │
│     (volsync-system namespace)   │         │                                      │
│                                  │         │  ClusterPolicy:                      │
│  Image:                          │         │  volsync-pvc-backup-restore          │
│  ghcr.io/mitchross/pvc-plumber   │         │                                      │
│  :0.3.1                          │         │  Rules:                              │
│                                  │         │  0. Check backup via pvc-plumber    │
│  Env:                            │         │     (mutate PVC if backup exists)    │
│  - BACKEND_TYPE: kopia-fs        │         │  1. Generate ExternalSecret          │
│  - KOPIA_REPOSITORY_PATH:        │         │     (Kopia password from 1Password)  │
│    /repository                   │         │  2. Generate ReplicationSource       │
│  - KOPIA_PASSWORD (from secret)  │         │     (waits for PVC Bound + 2h age)   │
│  - KOPIA_CONFIG_PATH:            │         │  3. Generate ReplicationDestination  │
│    /tmp/kopia/config/            │         │                                      │
│    repository.config             │         │  + volsync-nfs-inject policy:         │
│                                  │         │    Injects NFS mount into all        │
│  Volumes:                        │         │    VolSync mover pods automatically  │
│  - NFS: 192.168.10.133           │         │                                      │
│    /mnt/BigTank/k8s/             │         │                                      │
│    volsync-kopia-nfs             │         │                                      │
│                                  │         │                                      │
│  Endpoints:                      │         │                                      │
│  GET /exists/{ns}/{pvc}          │         │                                      │
│  GET /healthz                    │         │                                      │
│  GET /readyz                     │         │                                      │
│                                  │         │                                      │
└──────────────────────────────────┘         └──────────────────────────────────────┘
                      │                                       │
                      └───────────────────┬───────────────────┘
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                              VOLSYNC OPERATOR                                       │
│                                                                                     │
│   Watches for:                                                                      │
│   - ReplicationSource (backup jobs)                                                │
│   - ReplicationDestination (restore capability)                                    │
│                                                                                     │
│   Creates:                                                                          │
│   - Mover pods (temporary pods that run Kopia)                                     │
│   - VolumeSnapshots (Longhorn copy-on-write snapshots)                             │
│   - Restores data via VolumePopulator                                              │
│                                                                                     │
│   Kyverno NFS inject policy automatically adds NFS mount to mover pods             │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                         TRUENAS NFS STORAGE                                         │
│                                                                                     │
│   Server: 192.168.10.133                                                           │
│   Path: /mnt/BigTank/k8s/volsync-kopia-nfs                                        │
│   Network: 10Gbps to Proxmox cluster                                               │
│                                                                                     │
│   Kopia filesystem repositories for every PVC:                                     │
│   /{namespace}/{pvc-name}/                                                         │
│   Compressed with zstd-fastest, encrypted with Kopia password                      │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════
                              WHAT YOU NEED TO ADD
═══════════════════════════════════════════════════════════════════════════════════════

TO YOUR EXISTING APPS:

  1. Add label to PVC:
     metadata:
       labels:
         backup: "hourly"    # or "daily"

  That's it. Everything else is automatic.

  Label options:
  - backup: "hourly"  -> backs up every hour (0 * * * *)
  - backup: "daily"   -> backs up daily at 2am (0 2 * * *)

TO YOUR INFRASTRUCTURE REPO:

  infrastructure/
  └── controllers/
      ├── pvc-plumber/          <-- Backup checker service
      │   ├── deployment.yaml       (includes NFS mount + Service)
      │   ├── externalsecret.yaml   (Kopia password from 1Password)
      │   └── kustomization.yaml
      └── kyverno/
          └── policies/
              ├── volsync-pvc-backup-restore.yaml  <-- Main backup/restore automation
              └── volsync-nfs-inject.yaml           <-- NFS mount injection for mover pods
