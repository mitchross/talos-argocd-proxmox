window.HOMELAB_INVENTORY = {
  "fleetPerformance": {
    "date": "2026-09-20",
    "scope": "Latest dated storage measurements; older September 8/9 latency records below are preserved as history.",
    "rootMethod": "Proxmox root ext4: 1 GiB, one process, fsync every 64 MiB and at end; read backed by physical disk counters. Root disks often differ from VM data disks.",
    "guestMethod": "Mounted Kubernetes paths: 512 MiB, one process, QD1 direct sequential I/O; 128 separate 8 KiB write+fsync samples. Upstream caches and production background activity remain.",
    "referenceNote": "Verdicts are workload-fit assessments, not industry percentiles. Vendor numbers are bare-drive sequential peaks under different conditions, not matched averages or fsync latency targets.",
    "incident": "The first 1 GiB buffered Copyparty attempt caused an OOM restart at 17:54:04 UTC; the app recovered and its scratch file was removed. Completed results use the revised 512 MiB direct-I/O method.",
    "rootResults": [
      {
        "hostId": "gpu",
        "name": "Threadripper",
        "ip": "192.168.10.14",
        "path": "PNY CS900 root SSD; excludes enterprise mirror and GPU NVMe tiers",
        "writeMBs": 359.7,
        "readMBs": 406.5,
        "syncP99Ms": 2.313,
        "verdict": "Normal SATA-class bulk; good small-write tail.",
        "reference": "PNY 1 TB vendor peak: 535 read / 515 write MB/s.",
        "referenceUrl": "https://www.pny.com/ssd-cs900?iscommercial=true",
        "checkedAt": "2026-09-20T17:56:23.348042+00:00",
        "suggested": "Keep GPU workloads; reduce ordinary-service dependencies",
        "advice": "September 20: preserve dual-GPU placement. Default EDILOCA and enterprise-mirror volume paths differ; the mirror sample had heavy background I/O and needs a comparable retest."
      },
      {
        "hostId": "dell",
        "name": "Dell",
        "ip": "192.168.10.16",
        "path": "Apple root SSD; excludes Samsung SSD VM data tier",
        "writeMBs": 635.7,
        "readMBs": 1926.3,
        "syncP99Ms": 10.834,
        "verdict": "Fast reads; slow small-write tail compared with other tested roots.",
        "reference": "Other roots: 0.91\u20138.46 ms p99. No matched official Apple OEM throughput baseline.",
        "referenceUrl": null,
        "checkedAt": "2026-09-20T17:56:20.542457+00:00",
        "suggested": "Keep until data and recovery placement are ready",
        "advice": "September 20: eventual consolidation candidate, but two volumes have their only copy here and five two-copy volumes depend on Dell plus SFF. Move data and verify recovery first."
      },
      {
        "hostId": "shed",
        "name": "Shed Micro",
        "ip": "192.168.10.20",
        "path": "SK hynix root NVMe; excludes PNY VM data tier",
        "writeMBs": 638.6,
        "readMBs": 1159.8,
        "syncP99Ms": 1.175,
        "verdict": "Fast burst throughput and small writes within this fleet.",
        "reference": "No matched official BC501 OEM baseline; not sustained-write evidence.",
        "referenceUrl": null,
        "checkedAt": "2026-09-20T17:56:20.003731+00:00",
        "suggested": "Keep radio workloads selective",
        "advice": "September 20: spare RAM does not make the Wi-Fi host equivalent to wired compute. Intercept storage is on SFF; its measured remote write tail was 39.70 ms."
      },
      {
        "hostId": "sff",
        "name": "HP SFF",
        "ip": "192.168.10.21",
        "path": "PNY root SSD; shares physical drive with worker VM, excludes separate control-plane SSD",
        "writeMBs": 83.1,
        "readMBs": 401.3,
        "syncP99Ms": 8.464,
        "verdict": "Slow bulk writes; investigate the path before replacing hardware.",
        "reference": "Other PNY host wrote 359.7 MB/s; PNY vendor peak: 535 read / 515 write MB/s.",
        "referenceUrl": "https://www.pny.com/ssd-cs900?iscommercial=true",
        "checkedAt": "2026-09-20T17:56:33.321896+00:00",
        "suggested": "Keep control plane and worker roles distinct",
        "advice": "September 20: investigate guest CPU steal and the slow root/worker write path. The control plane uses a separate SSD; the older 49 ms WAL sample is historical."
      },
      {
        "hostId": "elite",
        "name": "HP Elite",
        "ip": "192.168.10.22",
        "path": "WDC root NVMe; excludes Intel SSD VM data tier",
        "writeMBs": 638.2,
        "readMBs": 888.7,
        "syncP99Ms": 0.91,
        "verdict": "Fast root responsiveness; this does not measure the Intel VM tier.",
        "reference": "256 GB SN530 vendor peak: 2400 read / 950 write MB/s.",
        "referenceUrl": "https://downloads.sandisk.com/downloads/datasheet/pcsn530-datasheet.pdf",
        "checkedAt": "2026-09-20T17:56:20.184620+00:00",
        "suggested": "Keep hardware-bound services; watch RAM headroom",
        "advice": "September 20: about 4 GiB host memory was available. Check eligible app placement and real peaks before increasing allocations; the Intel VM SSD has 75% endurance used."
      }
    ],
    "guestResults": [
      {
        "name": "Elite: Immich cache",
        "path": "/cache",
        "backend": "One copy on Intel NVMe",
        "writeMBs": 157.5,
        "readMBs": 240.0,
        "syncP99Ms": 1.29,
        "verdict": "Fastest measured local one-copy app path; good for light state in this sample.",
        "reference": "Bare 512 GB Intel 660p peak: 1500 read / 1000 write MB/s; not matched Longhorn conditions.",
        "referenceUrl": "https://www.solidigm.com/content/dam/solidigm/en/site/products/client/d6/660p/documents/ssd-660p-series-512gb-m-2-80mm-pcie-3-0-x4-3d2-qlc-spec-sheet.pdf",
        "durability": "Client fsync requested after each 8 KiB write.",
        "checkedAt": "2026-09-20T17:57:56.964021+00:00"
      },
      {
        "name": "SFF: Open-Meteo data",
        "path": "/app/data",
        "backend": "One copy on PNY worker tier",
        "writeMBs": 58.3,
        "readMBs": 138.0,
        "syncP99Ms": 3.468,
        "verdict": "Normal for light state; modest bulk throughput.",
        "reference": "Bare PNY peak: 535 read / 515 write MB/s; different VM/storage path.",
        "referenceUrl": "https://www.pny.com/ssd-cs900?iscommercial=true",
        "durability": "Client fsync requested after each 8 KiB write.",
        "checkedAt": "2026-09-20T17:58:11.057051+00:00"
      },
      {
        "name": "GPU: Paperless data",
        "path": "/usr/src/paperless/data",
        "backend": "One copy on EDILOCA 434 GiB default Longhorn tier",
        "writeMBs": 56.1,
        "readMBs": 123.0,
        "syncP99Ms": 7.094,
        "verdict": "Slow bulk versus Elite; higher small-write tail than SFF.",
        "reference": "Compare measured one-copy paths. No matched EDILOCA/Longhorn industry baseline.",
        "referenceUrl": null,
        "durability": "Client fsync requested after each 8 KiB write.",
        "checkedAt": "2026-09-20T17:58:26.848736+00:00"
      },
      {
        "name": "Dell: SurfSense object store",
        "path": "/app/.local_object_store",
        "backend": "Two copies: Dell Samsung + SFF PNY",
        "writeMBs": 37.1,
        "readMBs": 102.4,
        "syncP99Ms": 9.417,
        "verdict": "Slow bulk; moderate write tail. Replication cost was not isolated.",
        "reference": "No matched two-copy industry baseline; both replicas are in the measured path.",
        "referenceUrl": null,
        "durability": "Client fsync requested after each 8 KiB write.",
        "checkedAt": "2026-09-20T17:58:48.231416+00:00"
      },
      {
        "name": "Shed: Intercept data",
        "path": "/app/data/weather_sat",
        "backend": "App on Shed; one running copy on SFF across Wi-Fi",
        "writeMBs": 18.8,
        "readMBs": 22.0,
        "syncP99Ms": 39.703,
        "verdict": "Slow for interactive writes; this does not measure the local Shed SSD.",
        "reference": "Wired consumer-tier app paths: 1.29\u20139.42 ms p99; network/client conditions differ.",
        "referenceUrl": null,
        "durability": "Client fsync requested after each 8 KiB write.",
        "checkedAt": "2026-09-20T17:59:45.427899+00:00"
      },
      {
        "name": "GPU: Radar state",
        "path": "/data/state",
        "backend": "One copy on HPE enterprise mirror",
        "writeMBs": 33.9,
        "readMBs": 95.4,
        "syncP99Ms": 46.783,
        "verdict": "Slow in this loaded test; repeat before judging hardware.",
        "reference": "About 8.1 GB concurrent disk reads confound comparison; no matched idle-mirror baseline.",
        "referenceUrl": null,
        "durability": "Client fsync requested after each 8 KiB write.",
        "checkedAt": "2026-09-20T18:00:52.720751+00:00"
      },
      {
        "name": "TubeSync: SMB downloads",
        "path": "/downloads",
        "backend": "NAS BigTank/k8s/tubearchivist; sync=disabled",
        "writeMBs": 135.5,
        "readMBs": 174.9,
        "syncP99Ms": 3.499,
        "verdict": "Useful bulk throughput; exclude from durable-write rankings.",
        "reference": "About 1.40 Gbit/s read payload. No matched SMB industry baseline.",
        "referenceUrl": null,
        "durability": "Client fsync is not a durability guarantee: NAS sync=disabled.",
        "checkedAt": "2026-09-20T18:02:51.009077+00:00"
      }
    ]
  },
  "nasPerformance": {
    "date": "2026-09-20",
    "checkedAt": "2026-09-20T17:54:53.649948+00:00",
    "sourceArtifact": "nas-benchmarks/2026-09-20/summary.json",
    "summary": "Separate disk-backed reads, flushed writes and repeated reads from the RAM cache across BigTank, ai-pool and Backup10T.",
    "scope": "NAS-local fio tests: one reader/writer, queue depth 1, 4 GiB file, 128 KiB ZFS records, compression off, sync=standard. Network and SMB/NFS are excluded.",
    "cacheNote": "ARC means RAM cache. There are no L2ARC SSD cache devices, so no L2ARC comparison was possible.",
    "limitations": "These are bounded samples under live background activity, not maximum parallel or sustained throughput. A warm 4 GiB file demonstrates cache benefit but cannot establish the minimum RAM for the real working set. MB/s is decimal; IOPS counts operations per second.",
    "memory": {
      "checkedAt": "2026-09-20T17:16:08.100Z",
      "arcGiB": 341.407,
      "otherGiB": 13.8294,
      "freeGiB": 22.3338
    },
    "results": [
      {
        "pool": "BigTank",
        "mode": "Sequential write, final flush",
        "throughput": "203.4 MB/s",
        "durability": "sync=standard; fsync at end of 4 GiB write",
        "limitations": "Bounded write including final flush; not sustained SSD speed beyond its cache.",
        "measuredAt": "2026-09-20T17:46:37.284819+00:00",
        "benchmark": "sequential-write-flushed"
      },
      {
        "pool": "BigTank",
        "mode": "Sequential read, direct I/O",
        "throughput": "254.9 MB/s",
        "durability": "Read operation",
        "limitations": "One reader, queue depth 1; data reads bypass RAM ARC.",
        "measuredAt": "2026-09-20T17:47:02.909344+00:00",
        "benchmark": "sequential-read-direct"
      },
      {
        "pool": "BigTank",
        "mode": "Sequential read, disk with prefetch",
        "throughput": "480.4 MB/s",
        "durability": "Read operation",
        "limitations": "Data retention in ARC disabled; prefetch still operates. Not the same path as direct I/O.",
        "measuredAt": "2026-09-20T17:47:20.347244+00:00",
        "benchmark": "sequential-read-prefetch-cache-disabled"
      },
      {
        "pool": "BigTank",
        "mode": "4 KiB random read, disk",
        "throughput": "98 IOPS (0.40 MB/s)",
        "durability": "Read operation",
        "limitations": "Queue depth 1 on 128 KiB records; record-size amplification matters.",
        "measuredAt": "2026-09-20T17:47:43.789018+00:00",
        "benchmark": "random-read-4k-disk"
      },
      {
        "pool": "BigTank",
        "mode": "4 KiB random write, fsync each",
        "throughput": "61 IOPS (0.25 MB/s)",
        "durability": "sync=standard; fsync after every write",
        "limitations": "IOPS includes write and sync waits. This is a short random-write probe.",
        "measuredAt": "2026-09-20T17:48:06.216596+00:00",
        "benchmark": "random-write-4k-fsync-each"
      },
      {
        "pool": "BigTank",
        "mode": "Sequential read, warm RAM ARC",
        "throughput": "5,335.4 MB/s",
        "durability": "Read operation",
        "limitations": "Repeated 4 GiB file fits in RAM; not SMB/NFS throughput.",
        "measuredAt": "2026-09-20T17:48:33.518143+00:00",
        "benchmark": "sequential-read-warm-arc"
      },
      {
        "pool": "BigTank",
        "mode": "4 KiB random read, warm RAM ARC",
        "throughput": "173,072 IOPS (708.90 MB/s)",
        "durability": "Read operation",
        "limitations": "Queue depth 1, RAM-resident test file; not uncached disk IOPS.",
        "measuredAt": "2026-09-20T17:48:55.537349+00:00",
        "benchmark": "random-read-4k-warm-arc"
      },
      {
        "pool": "ai-pool",
        "mode": "Sequential write, final flush",
        "throughput": "396.3 MB/s",
        "durability": "sync=standard; fsync at end of 4 GiB write",
        "limitations": "Bounded write including final flush; not sustained SSD speed beyond its cache.",
        "measuredAt": "2026-09-20T17:49:19.512953+00:00",
        "benchmark": "sequential-write-flushed"
      },
      {
        "pool": "ai-pool",
        "mode": "Sequential read, direct I/O",
        "throughput": "274.1 MB/s",
        "durability": "Read operation",
        "limitations": "One reader, queue depth 1; data reads bypass RAM ARC.",
        "measuredAt": "2026-09-20T17:49:43.840238+00:00",
        "benchmark": "sequential-read-direct"
      },
      {
        "pool": "ai-pool",
        "mode": "Sequential read, disk with prefetch",
        "throughput": "1,066.0 MB/s",
        "durability": "Read operation",
        "limitations": "Data retention in ARC disabled; prefetch still operates. Not the same path as direct I/O.",
        "measuredAt": "2026-09-20T17:49:56.336294+00:00",
        "benchmark": "sequential-read-prefetch-cache-disabled"
      },
      {
        "pool": "ai-pool",
        "mode": "4 KiB random read, disk",
        "throughput": "1,502 IOPS (6.15 MB/s)",
        "durability": "Read operation",
        "limitations": "Queue depth 1 on 128 KiB records; record-size amplification matters.",
        "measuredAt": "2026-09-20T17:50:19.744940+00:00",
        "benchmark": "random-read-4k-disk"
      },
      {
        "pool": "ai-pool",
        "mode": "4 KiB random write, fsync each",
        "throughput": "416 IOPS (1.70 MB/s)",
        "durability": "sync=standard; fsync after every write",
        "limitations": "IOPS includes write and sync waits. This is a short random-write probe.",
        "measuredAt": "2026-09-20T17:50:41.957044+00:00",
        "benchmark": "random-write-4k-fsync-each"
      },
      {
        "pool": "ai-pool",
        "mode": "Sequential read, warm RAM ARC",
        "throughput": "5,499.3 MB/s",
        "durability": "Read operation",
        "limitations": "Repeated 4 GiB file fits in RAM; not SMB/NFS throughput.",
        "measuredAt": "2026-09-20T17:51:03.541904+00:00",
        "benchmark": "sequential-read-warm-arc"
      },
      {
        "pool": "ai-pool",
        "mode": "4 KiB random read, warm RAM ARC",
        "throughput": "177,745 IOPS (728.04 MB/s)",
        "durability": "Read operation",
        "limitations": "Queue depth 1, RAM-resident test file; not uncached disk IOPS.",
        "measuredAt": "2026-09-20T17:51:25.992535+00:00",
        "benchmark": "random-read-4k-warm-arc"
      },
      {
        "pool": "Backup10T",
        "mode": "Sequential write, final flush",
        "throughput": "170.5 MB/s",
        "durability": "sync=standard; fsync at end of 4 GiB write",
        "limitations": "Bounded write including final flush; not sustained SSD speed beyond its cache.",
        "measuredAt": "2026-09-20T17:52:04.954420+00:00",
        "benchmark": "sequential-write-flushed"
      },
      {
        "pool": "Backup10T",
        "mode": "Sequential read, direct I/O",
        "throughput": "190.5 MB/s",
        "durability": "Read operation",
        "limitations": "One reader, queue depth 1; data reads bypass RAM ARC.",
        "measuredAt": "2026-09-20T17:52:35.988403+00:00",
        "benchmark": "sequential-read-direct"
      },
      {
        "pool": "Backup10T",
        "mode": "Sequential read, disk with prefetch",
        "throughput": "203.5 MB/s",
        "durability": "Read operation",
        "limitations": "Data retention in ARC disabled; prefetch still operates. Not the same path as direct I/O.",
        "measuredAt": "2026-09-20T17:53:05.472416+00:00",
        "benchmark": "sequential-read-prefetch-cache-disabled"
      },
      {
        "pool": "Backup10T",
        "mode": "4 KiB random read, disk",
        "throughput": "130 IOPS (0.53 MB/s)",
        "durability": "Read operation",
        "limitations": "Queue depth 1 on 128 KiB records; record-size amplification matters.",
        "measuredAt": "2026-09-20T17:53:29.347847+00:00",
        "benchmark": "random-read-4k-disk"
      },
      {
        "pool": "Backup10T",
        "mode": "4 KiB random write, fsync each",
        "throughput": "123 IOPS (0.50 MB/s)",
        "durability": "sync=standard; fsync after every write",
        "limitations": "IOPS includes write and sync waits. This is a short random-write probe.",
        "measuredAt": "2026-09-20T17:53:51.626278+00:00",
        "benchmark": "random-write-4k-fsync-each"
      },
      {
        "pool": "Backup10T",
        "mode": "Sequential read, warm RAM ARC",
        "throughput": "5,499.3 MB/s",
        "durability": "Read operation",
        "limitations": "Repeated 4 GiB file fits in RAM; not SMB/NFS throughput.",
        "measuredAt": "2026-09-20T17:54:31.524534+00:00",
        "benchmark": "sequential-read-warm-arc"
      },
      {
        "pool": "Backup10T",
        "mode": "4 KiB random read, warm RAM ARC",
        "throughput": "166,158 IOPS (680.58 MB/s)",
        "durability": "Read operation",
        "limitations": "Queue depth 1, RAM-resident test file; not uncached disk IOPS.",
        "measuredAt": "2026-09-20T17:54:53.649948+00:00",
        "benchmark": "random-read-4k-warm-arc"
      }
    ]
  },
  "date": "2026-10-15",
  "assembledAt": "2026-10-15T04:08:38.371121+00:00",
  "sourceCommit": "57233c8bc",
  "runtimeVersionsCheckedAt": "2026-10-15T04:08:38.371121+00:00",
  "hosts": [
    {
      "id": "sff",
      "name": "HP SFF",
      "model": "ProDesk 600 G4 SFF",
      "cpu": "Intel(R) Core(TM) i5-8500 CPU @ 3.00GHz \u00b7 6 threads",
      "ram": "64 GB",
      "zone": "hp-sff",
      "link": "Wired \u00b7 2.5 GbE",
      "role": "Control plane + everyday apps",
      "suggested": "Everyday apps + protected state",
      "summary": "One control plane and one worker share this host. The third disk is an unassigned PNY SSD.",
      "advice": "The control plane now uses the Intel S3610. Preserve its separate storage and account for the shared host.",
      "loss": "The Kubernetes API and scheduling stop. Existing pods on other hosts may keep serving, but the cluster cannot arrange new failover.",
      "power": null,
      "ip": "192.168.10.21",
      "kind": "Proxmox",
      "disks": [
        {
          "device": "sda",
          "model": "PNY CS900 1TB SSD",
          "bytes": 1000204886016,
          "interface": "sata",
          "role": "Spare; orphan LVM PV",
          "path": "No volume group",
          "note": "SMART overall passed; 33 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 33,
            "powerOnHours": 25462,
            "ataCounters": [
              {
                "id": 231,
                "name": "SSD_Life_Left",
                "raw": 93,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "sdb",
          "model": "INTEL SSDSC2BX400G4R",
          "bytes": 400088457216,
          "interface": "sata",
          "role": "Control plane / etcd",
          "path": "hp-sff-cp \u2192 VM 101 scsi0 (100 GiB)",
          "note": "SMART overall passed; 30 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 30,
            "powerOnHours": 43291,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 198,
                "name": "Offline_Uncorrectable",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 199,
                "name": "CRC_Error_Count",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 202,
                "name": "Unknown_SSD_Attribute",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 233,
                "name": "Media_Wearout_Indicator",
                "raw": 195899,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "sdc",
          "model": "PNY CS900 1TB SSD",
          "bytes": 1000204886016,
          "interface": "sata",
          "role": "Proxmox + worker",
          "path": "pve / hp-prodesk-vmstore \u2192 VM 100 scsi0 + scsi1",
          "note": "SMART overall passed; 33 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 33,
            "powerOnHours": 25637,
            "ataCounters": [
              {
                "id": 231,
                "name": "SSD_Life_Left",
                "raw": 92,
                "normalized": 100
              }
            ]
          }
        }
      ],
      "vms": [
        {
          "id": "100",
          "name": "talos-prod-cluster-v2-hp-sff-workers-h76ncc",
          "ramMiB": 40960,
          "vcpus": 6,
          "state": "running",
          "ip": "192.168.10.173",
          "disks": [
            {
              "slot": "scsi0",
              "backing": "hp-prodesk-vmstore:vm-100-disk-0",
              "size": "128 GiB"
            },
            {
              "slot": "scsi1",
              "backing": "hp-prodesk-vmstore:vm-100-disk-1",
              "size": "690 GiB"
            }
          ],
          "namespaces": [
            {
              "name": "1passwordconnect",
              "pods": 1
            },
            {
              "name": "cobalt",
              "pods": 2
            },
            {
              "name": "container-registry",
              "pods": 1
            },
            {
              "name": "csi-driver-nfs",
              "pods": 1
            },
            {
              "name": "csi-driver-smb",
              "pods": 1
            },
            {
              "name": "external-dns",
              "pods": 2
            },
            {
              "name": "external-secrets",
              "pods": 1
            },
            {
              "name": "geocoder",
              "pods": 2
            },
            {
              "name": "gitea",
              "pods": 1
            },
            {
              "name": "gitea-actions",
              "pods": 1
            },
            {
              "name": "hindsight",
              "pods": 1
            },
            {
              "name": "homepage-dashboard",
              "pods": 1
            },
            {
              "name": "imagery",
              "pods": 1
            },
            {
              "name": "immich",
              "pods": 1
            },
            {
              "name": "intel-gpu-plugin",
              "pods": 1
            },
            {
              "name": "jellyfin",
              "pods": 1
            },
            {
              "name": "keda",
              "pods": 1
            },
            {
              "name": "kopiur-system",
              "pods": 1
            },
            {
              "name": "kube-system",
              "pods": 3
            },
            {
              "name": "langfuse",
              "pods": 2
            },
            {
              "name": "litellm",
              "pods": 1
            },
            {
              "name": "loki-stack",
              "pods": 4
            },
            {
              "name": "longhorn-system",
              "pods": 10
            },
            {
              "name": "node-feature-discovery",
              "pods": 2
            },
            {
              "name": "opentelemetry",
              "pods": 3
            },
            {
              "name": "paperless-ngx",
              "pods": 3
            },
            {
              "name": "paseo",
              "pods": 1
            },
            {
              "name": "posthog-injector",
              "pods": 1
            },
            {
              "name": "product-bench",
              "pods": 2
            },
            {
              "name": "project-nomad",
              "pods": 7
            },
            {
              "name": "prometheus-stack",
              "pods": 3
            },
            {
              "name": "redis-instance",
              "pods": 1
            },
            {
              "name": "redlib",
              "pods": 2
            },
            {
              "name": "snapshot-controller",
              "pods": 1
            },
            {
              "name": "surfsense",
              "pods": 1
            },
            {
              "name": "temporal",
              "pods": 3
            },
            {
              "name": "temporal-worker-controller",
              "pods": 1
            },
            {
              "name": "truenas-csi",
              "pods": 1
            },
            {
              "name": "versatiles",
              "pods": 1
            },
            {
              "name": "vert",
              "pods": 1
            },
            {
              "name": "vertical-pod-autoscaler",
              "pods": 2
            },
            {
              "name": "worldmonitor",
              "pods": 2
            }
          ],
          "passthrough": {
            "hostpci0": "mapping=intel-igpu,pcie=1"
          },
          "talos": "Talos (v1.14.2)",
          "kubernetes": "v1.37.1"
        },
        {
          "id": "101",
          "name": "talos-prod-cluster-v2-control-planes-7mxjxv",
          "ramMiB": 12288,
          "vcpus": 4,
          "state": "running",
          "ip": "192.168.10.94",
          "disks": [
            {
              "slot": "scsi0",
              "backing": "hp-sff-cp-vmstore:vm-101-disk-0",
              "size": "100 GiB"
            }
          ],
          "namespaces": [
            {
              "name": "cert-manager",
              "pods": 3
            },
            {
              "name": "csi-driver-nfs",
              "pods": 2
            },
            {
              "name": "csi-driver-smb",
              "pods": 2
            },
            {
              "name": "gpu-operator",
              "pods": 1
            },
            {
              "name": "kube-system",
              "pods": 6
            },
            {
              "name": "node-feature-discovery",
              "pods": 1
            },
            {
              "name": "opentelemetry",
              "pods": 1
            },
            {
              "name": "prometheus-stack",
              "pods": 1
            },
            {
              "name": "truenas-csi",
              "pods": 1
            },
            {
              "name": "vertical-pod-autoscaler",
              "pods": 1
            }
          ],
          "passthrough": {},
          "talos": "Talos (v1.14.2)",
          "kubernetes": "v1.37.1"
        }
      ],
      "ramBytes": 67223859200,
      "memoryAvailableBytes": 10764496896,
      "software": "pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-20-pve)",
      "storages": [
        {
          "name": "hp-prodesk-vmstore",
          "type": "lvm",
          "status": "active",
          "totalKiB": "975171584",
          "usedKiB": "966787072",
          "availableKiB": "8384512",
          "percent": "99.14%"
        },
        {
          "name": "hp-sff-cp-vmstore",
          "type": "lvm",
          "status": "active",
          "totalKiB": "390709248",
          "usedKiB": "104857600",
          "availableKiB": "285851648",
          "percent": "26.84%"
        },
        {
          "name": "local",
          "type": "dir",
          "status": "active",
          "totalKiB": "98497780",
          "usedKiB": "13746504",
          "availableKiB": "79701728",
          "percent": "13.96%"
        }
      ],
      "pciDevices": [
        "00:00.0 Host bridge: Intel Corporation 8th Gen Core Processor Host Bridge/DRAM Registers (rev 07)",
        "00:02.0 VGA compatible controller: Intel Corporation CoffeeLake-S GT2 [UHD Graphics 630]",
        "00:12.0 Signal processing controller: Intel Corporation Cannon Lake PCH Thermal Controller (rev 10)",
        "00:14.0 USB controller: Intel Corporation Cannon Lake PCH USB 3.1 xHCI Host Controller (rev 10)",
        "00:14.2 RAM memory: Intel Corporation Cannon Lake PCH Shared SRAM (rev 10)",
        "00:16.0 Communication controller: Intel Corporation Cannon Lake PCH HECI Controller (rev 10)",
        "00:16.3 Serial controller: Intel Corporation Cannon Lake PCH Active Management Technology - SOL (rev 10)",
        "00:17.0 SATA controller: Intel Corporation Cannon Lake PCH SATA AHCI Controller (rev 10)",
        "00:1d.0 PCI bridge: Intel Corporation Cannon Lake PCH PCI Express Root Port #9 (rev f0)",
        "00:1f.0 ISA bridge: Intel Corporation Q370 Chipset LPC/eSPI Controller (rev 10)",
        "00:1f.4 SMBus: Intel Corporation Cannon Lake PCH SMBus Controller (rev 10)",
        "00:1f.5 Serial bus controller: Intel Corporation Cannon Lake PCH SPI Controller (rev 10)",
        "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection (7) I219-LM (rev 10)",
        "01:00.0 Ethernet controller: Realtek Semiconductor Co., Ltd. RTL8125 2.5GbE Controller (rev 04)"
      ],
      "usbDevices": [
        "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub"
      ],
      "networkAdapters": [
        "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection (7) I219-LM (rev 10)",
        "01:00.0 Ethernet controller: Realtek Semiconductor Co., Ltd. RTL8125 2.5GbE Controller (rev 04)"
      ]
    },
    {
      "id": "elite",
      "name": "HP Elite Mini",
      "model": "Elite Mini 600 G9",
      "cpu": "13th Gen Intel(R) Core(TM) i5-13500T \u00b7 20 threads",
      "ram": "32 GB",
      "zone": "hp-elite",
      "link": "Wired",
      "role": "Everyday apps + Zigbee",
      "suggested": "Everyday apps + protected state",
      "summary": "The other sensible home for everyday services. The Zigbee coordinator lives here too.",
      "advice": "Plan the data SSD replacement. Check the SATA carrier/cable before buying a 2.5-inch drive.",
      "loss": "Pods here stop, along with the attached Zigbee coordinator. Single-copy volumes on this host have no surviving live copy.",
      "power": null,
      "ip": "192.168.10.22",
      "kind": "Proxmox",
      "disks": [
        {
          "device": "nvme0n1",
          "model": "INTEL SSDPEKNW512G8",
          "bytes": 512110190592,
          "interface": "nvme",
          "role": "Longhorn data",
          "path": "hp-elite-vmstore \u2192 VM 100 scsi1 (440 GiB)",
          "note": "SMART overall passed; 35 \u00b0C at collection. NVMe endurance used: 76%; media errors: 0.",
          "health": {
            "passed": true,
            "temperatureC": 35,
            "powerOnHours": 57362,
            "percentage_used": 76,
            "media_errors": 0,
            "critical_warning": 0,
            "data_units_written": 420700210,
            "ataCounters": []
          }
        },
        {
          "device": "nvme1n1",
          "model": "WDC PC SN530 SDBPMPZ-256G-1101",
          "bytes": 256060514304,
          "interface": "nvme",
          "role": "Proxmox + Talos system",
          "path": "pve / local-lvm \u2192 VM 100 scsi0 (128 GiB)",
          "note": "SMART overall passed; 44 \u00b0C at collection. NVMe endurance used: 3%; media errors: 0.",
          "health": {
            "passed": true,
            "temperatureC": 44,
            "powerOnHours": 12778,
            "percentage_used": 3,
            "media_errors": 0,
            "critical_warning": 0,
            "data_units_written": 26596213,
            "ataCounters": []
          }
        }
      ],
      "vms": [
        {
          "id": "100",
          "name": "talos-prod-cluster-v2-hp-elite-workers-l5zlgr",
          "ramMiB": 26624,
          "vcpus": 16,
          "state": "running",
          "ip": "192.168.10.129",
          "disks": [
            {
              "slot": "scsi0",
              "backing": "local-lvm:vm-100-disk-0",
              "size": "128 GiB"
            },
            {
              "slot": "scsi1",
              "backing": "hp-elite-vmstore:vm-100-disk-0",
              "size": "440 GiB"
            }
          ],
          "namespaces": [
            {
              "name": "1passwordconnect",
              "pods": 1
            },
            {
              "name": "cloudflared",
              "pods": 1
            },
            {
              "name": "convertx",
              "pods": 1
            },
            {
              "name": "csi-driver-nfs",
              "pods": 1
            },
            {
              "name": "csi-driver-smb",
              "pods": 1
            },
            {
              "name": "echo-server",
              "pods": 1
            },
            {
              "name": "excalidraw",
              "pods": 1
            },
            {
              "name": "frigate",
              "pods": 1
            },
            {
              "name": "gitea",
              "pods": 1
            },
            {
              "name": "gitea-actions",
              "pods": 1
            },
            {
              "name": "home-assistant",
              "pods": 1
            },
            {
              "name": "immich",
              "pods": 2
            },
            {
              "name": "intel-gpu-plugin",
              "pods": 1
            },
            {
              "name": "kafka",
              "pods": 1
            },
            {
              "name": "karakeep",
              "pods": 1
            },
            {
              "name": "keda",
              "pods": 1
            },
            {
              "name": "kiwix",
              "pods": 1
            },
            {
              "name": "kube-system",
              "pods": 5
            },
            {
              "name": "langfuse",
              "pods": 1
            },
            {
              "name": "loki-stack",
              "pods": 1
            },
            {
              "name": "longhorn-system",
              "pods": 9
            },
            {
              "name": "map-raster",
              "pods": 1
            },
            {
              "name": "mcp-grafana",
              "pods": 1
            },
            {
              "name": "metrics-server",
              "pods": 1
            },
            {
              "name": "nginx-example",
              "pods": 1
            },
            {
              "name": "node-feature-discovery",
              "pods": 1
            },
            {
              "name": "open-webui",
              "pods": 3
            },
            {
              "name": "opentelemetry",
              "pods": 2
            },
            {
              "name": "posthog-injector",
              "pods": 1
            },
            {
              "name": "product-bench",
              "pods": 1
            },
            {
              "name": "project-nomad",
              "pods": 1
            },
            {
              "name": "prometheus-stack",
              "pods": 1
            },
            {
              "name": "radar-ng",
              "pods": 2
            },
            {
              "name": "redis",
              "pods": 1
            },
            {
              "name": "searxng",
              "pods": 1
            },
            {
              "name": "snapshot-controller",
              "pods": 1
            },
            {
              "name": "surfsense",
              "pods": 4
            },
            {
              "name": "temporal",
              "pods": 2
            },
            {
              "name": "truenas-csi",
              "pods": 1
            },
            {
              "name": "versatiles",
              "pods": 1
            },
            {
              "name": "vert",
              "pods": 1
            },
            {
              "name": "worldmonitor",
              "pods": 1
            }
          ],
          "passthrough": {
            "hostpci0": "mapping=intel-igpu,pcie=1",
            "usb0": "mapping=zigbee,usb3=1",
            "usb1": "host=2-3,usb3=1"
          },
          "talos": "Talos (v1.14.2)",
          "kubernetes": "v1.37.1"
        }
      ],
      "ramBytes": 32843304960,
      "memoryAvailableBytes": 2105970688,
      "software": "pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-20-pve)",
      "storages": [
        {
          "name": "hp-elite-vmstore",
          "type": "lvm",
          "status": "active",
          "totalKiB": "500105216",
          "usedKiB": "471859200",
          "availableKiB": "28246016",
          "percent": "94.35%"
        },
        {
          "name": "local",
          "type": "dir",
          "status": "active",
          "totalKiB": "71017632",
          "usedKiB": "13327660",
          "availableKiB": "54036752",
          "percent": "18.77%"
        },
        {
          "name": "local-lvm",
          "type": "lvmthin",
          "status": "active",
          "totalKiB": "148086784",
          "usedKiB": "62551857",
          "availableKiB": "85534926",
          "percent": "42.24%"
        }
      ],
      "pciDevices": [
        "00:00.0 Host bridge: Intel Corporation Device 4640 (rev 02)",
        "00:02.0 VGA compatible controller: Intel Corporation AlderLake-S GT1 (rev 0c)",
        "00:14.0 USB controller: Intel Corporation Alder Lake-S PCH USB 3.2 Gen 2x2 XHCI Controller (rev 11)",
        "00:14.2 RAM memory: Intel Corporation Alder Lake-S PCH Shared SRAM (rev 11)",
        "00:14.3 Network controller: Intel Corporation Alder Lake-S PCH CNVi WiFi (rev 11)",
        "00:16.0 Communication controller: Intel Corporation Alder Lake-S PCH HECI Controller #1 (rev 11)",
        "00:16.3 Serial controller: Intel Corporation Alder Lake-S Keyboard and Text (KT) Redirection (rev 11)",
        "00:17.0 SATA controller: Intel Corporation Alder Lake-S PCH SATA Controller [AHCI Mode] (rev 11)",
        "00:1a.0 PCI bridge: Intel Corporation Alder Lake-S PCH PCI Express Root Port #25 (rev 11)",
        "00:1b.0 PCI bridge: Intel Corporation Alder Lake-S PCH PCI Express Root Port #21 (rev 11)",
        "00:1f.0 ISA bridge: Intel Corporation Q670 Chipset LPC/eSPI Controller (rev 11)",
        "00:1f.3 Audio device: Intel Corporation Alder Lake-S HD Audio Controller (rev 11)",
        "00:1f.4 SMBus: Intel Corporation Alder Lake-S PCH SMBus Controller (rev 11)",
        "00:1f.5 Serial bus controller: Intel Corporation Alder Lake-S PCH SPI Controller (rev 11)",
        "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection (17) I219-LM (rev 11)",
        "01:00.0 Non-Volatile memory controller: Intel Corporation SSD 660P Series (rev 03)",
        "02:00.0 Non-Volatile memory controller: Sandisk Corp PC SN530 NVMe SSD (DRAM-less) (rev 01)"
      ],
      "usbDevices": [
        "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 001 Device 002: ID 10c4:ea60 Silicon Labs CP210x UART Bridge",
        "Bus 001 Device 003: ID 8087:0033 Intel Corp. AX211 Bluetooth",
        "Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub",
        "Bus 002 Device 003: ID 0b05:1976 ASUSTek Computer, Inc. USB 10/100/1G/2.5G LAN",
        "Bus 002 Device 004: ID 18d1:9302 Google Inc. "
      ],
      "networkAdapters": [
        "00:14.3 Network controller: Intel Corporation Alder Lake-S PCH CNVi WiFi (rev 11)",
        "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection (17) I219-LM (rev 11)"
      ]
    },
    {
      "id": "gpu",
      "name": "Threadripper",
      "model": "X399 \u00b7 Ryzen Threadripper 2950X",
      "cpu": "AMD Ryzen Threadripper 2950X 16-Core Processor \u00b7 32 threads",
      "ram": "128 GB",
      "zone": "house",
      "link": "Wired",
      "role": "GPU + heavy jobs + app storage",
      "suggested": "GPU + selected heavy jobs",
      "summary": "Two RTX 3090s, an enterprise SSD mirror, and separate Talos, model-cache and bulk-storage paths.",
      "advice": "The enterprise mirror protects against one member failure, not loss of this host.",
      "loss": "The GPU stops, as expected. The flash mirror and many single-copy app volumes also disappear with this host; mirroring disks inside it cannot prevent that.",
      "power": null,
      "ip": "192.168.10.14",
      "kind": "Proxmox",
      "disks": [
        {
          "device": "sda",
          "model": "PNY CS900 1TB SSD",
          "bytes": 1000204886016,
          "interface": "sata",
          "role": "Proxmox + bulk app storage",
          "path": "pve / tr-sda-vmstore \u2192 VM 100 scsi4 (800 GiB)",
          "note": "SMART overall passed; 33 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 33,
            "powerOnHours": 25651,
            "ataCounters": [
              {
                "id": 231,
                "name": "SSD_Life_Left",
                "raw": 93,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "sdb",
          "model": "MK000480GWCEV",
          "bytes": 480103981056,
          "interface": "sata",
          "role": "Enterprise RAID1 member",
          "path": "md0 \u2192 ssd-ent \u2192 VM 100 scsi3 (440 GiB)",
          "note": "SMART overall passed; 18 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 18,
            "powerOnHours": 53697,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 202,
                "name": "Unknown_SSD_Attribute",
                "raw": 0,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "sdc",
          "model": "MK000480GWCEV",
          "bytes": 480103981056,
          "interface": "sata",
          "role": "Enterprise RAID1 member",
          "path": "md0 \u2192 ssd-ent \u2192 VM 100 scsi3 (440 GiB)",
          "note": "SMART overall passed; 24 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 24,
            "powerOnHours": 48973,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 202,
                "name": "Unknown_SSD_Attribute",
                "raw": 0,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "nvme0n1",
          "model": "EDILOCA EN605 512GB",
          "bytes": 512110190592,
          "interface": "nvme",
          "role": "Talos system",
          "path": "nvme0-vmstore \u2192 VM 100 scsi0 (16 GiB) + scsi1 (434 GiB)",
          "note": "SMART overall passed; 54 \u00b0C at collection. NVMe endurance used: 16%; media errors: 0.",
          "health": {
            "passed": true,
            "temperatureC": 54,
            "powerOnHours": 17564,
            "percentage_used": 16,
            "media_errors": 0,
            "critical_warning": 0,
            "data_units_written": 156636352,
            "ataCounters": []
          }
        },
        {
          "device": "nvme1n1",
          "model": "EDILOCA EN605 512GB",
          "bytes": 512110190592,
          "interface": "nvme",
          "role": "AI model cache",
          "path": "nvme1-vmstore \u2192 VM 100 scsi2 (450 GiB)",
          "note": "SMART overall passed; 54 \u00b0C at collection. NVMe endurance used: 20%; media errors: 0.",
          "health": {
            "passed": true,
            "temperatureC": 54,
            "powerOnHours": 22806,
            "percentage_used": 20,
            "media_errors": 0,
            "critical_warning": 0,
            "data_units_written": 177986476,
            "ataCounters": []
          }
        }
      ],
      "vms": [
        {
          "id": "100",
          "name": "talos-prod-cluster-v2-gpu-workers-jxfkdr",
          "ramMiB": 102400,
          "vcpus": 30,
          "state": "running",
          "ip": "192.168.10.187",
          "disks": [
            {
              "slot": "scsi0",
              "backing": "nvme0-vmstore:vm-100-disk-1",
              "size": "16 GiB"
            },
            {
              "slot": "scsi1",
              "backing": "nvme0-vmstore:vm-100-disk-2",
              "size": "434 GiB"
            },
            {
              "slot": "scsi2",
              "backing": "nvme1-vmstore:vm-100-disk-0",
              "size": "450 GiB"
            },
            {
              "slot": "scsi3",
              "backing": "ssd-ent:vm-100-disk-0",
              "size": "440 GiB"
            },
            {
              "slot": "scsi4",
              "backing": "tr-sda-vmstore:vm-100-disk-0",
              "size": "800 GiB"
            }
          ],
          "namespaces": [
            {
              "name": "1passwordconnect",
              "pods": 1
            },
            {
              "name": "argocd",
              "pods": 5
            },
            {
              "name": "cloudflared",
              "pods": 1
            },
            {
              "name": "copyparty",
              "pods": 1
            },
            {
              "name": "csi-driver-nfs",
              "pods": 1
            },
            {
              "name": "csi-driver-smb",
              "pods": 1
            },
            {
              "name": "deal-scout",
              "pods": 2
            },
            {
              "name": "dozzle",
              "pods": 1
            },
            {
              "name": "frigate",
              "pods": 1
            },
            {
              "name": "geocoder",
              "pods": 1
            },
            {
              "name": "gitea",
              "pods": 1
            },
            {
              "name": "gpu-operator",
              "pods": 5
            },
            {
              "name": "hindsight",
              "pods": 1
            },
            {
              "name": "immich",
              "pods": 1
            },
            {
              "name": "intercept",
              "pods": 1
            },
            {
              "name": "it-tools",
              "pods": 1
            },
            {
              "name": "karakeep",
              "pods": 2
            },
            {
              "name": "keda",
              "pods": 1
            },
            {
              "name": "kopiur-system",
              "pods": 1
            },
            {
              "name": "kube-system",
              "pods": 4
            },
            {
              "name": "langfuse",
              "pods": 2
            },
            {
              "name": "loki-stack",
              "pods": 4
            },
            {
              "name": "longhorn-system",
              "pods": 10
            },
            {
              "name": "monitoring",
              "pods": 1
            },
            {
              "name": "news-reader",
              "pods": 2
            },
            {
              "name": "nginx-example",
              "pods": 1
            },
            {
              "name": "node-feature-discovery",
              "pods": 1
            },
            {
              "name": "opentelemetry",
              "pods": 1
            },
            {
              "name": "pairdrop",
              "pods": 1
            },
            {
              "name": "paperless-ngx",
              "pods": 1
            },
            {
              "name": "perplexica",
              "pods": 1
            },
            {
              "name": "posthog",
              "pods": 21
            },
            {
              "name": "presenton",
              "pods": 1
            },
            {
              "name": "product-bench",
              "pods": 1
            },
            {
              "name": "project-nomad",
              "pods": 1
            },
            {
              "name": "prometheus-stack",
              "pods": 5
            },
            {
              "name": "radar-ng",
              "pods": 8
            },
            {
              "name": "restore-canary",
              "pods": 1
            },
            {
              "name": "searxng",
              "pods": 2
            },
            {
              "name": "stirling-pdf",
              "pods": 1
            },
            {
              "name": "surfsense",
              "pods": 1
            },
            {
              "name": "temporal",
              "pods": 2
            },
            {
              "name": "truenas-csi",
              "pods": 2
            },
            {
              "name": "vllm",
              "pods": 1
            },
            {
              "name": "worldmonitor",
              "pods": 1
            }
          ],
          "passthrough": {
            "hostpci0": "mapping=gpu-1,pcie=1",
            "hostpci1": "mapping=gpu-2,pcie=1"
          },
          "talos": "Talos (v1.14.2)",
          "kubernetes": "v1.37.1"
        },
        {
          "id": "102",
          "name": "kali-linux",
          "ramMiB": 12000,
          "vcpus": 4,
          "state": "stopped",
          "ip": null,
          "disks": [
            {
              "slot": "scsi0",
              "backing": "truenas-smb:102/vm-102-disk-0.raw",
              "size": "305 GiB"
            }
          ],
          "namespaces": [],
          "passthrough": {}
        }
      ],
      "ramBytes": 134941495296,
      "memoryAvailableBytes": 21291954176,
      "software": "pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-20-pve)",
      "storages": [
        {
          "name": "local",
          "type": "dir",
          "status": "active",
          "totalKiB": "98497960",
          "usedKiB": "42934696",
          "availableKiB": "50793340",
          "percent": "43.59%"
        },
        {
          "name": "nvme0-vmstore",
          "type": "lvmthin",
          "status": "active",
          "totalKiB": "489975808",
          "usedKiB": "241558073",
          "availableKiB": "248417734",
          "percent": "49.30%"
        },
        {
          "name": "nvme1-vmstore",
          "type": "lvmthin",
          "status": "active",
          "totalKiB": "489975808",
          "usedKiB": "30378500",
          "availableKiB": "459597307",
          "percent": "6.20%"
        },
        {
          "name": "ssd-ent",
          "type": "lvm",
          "status": "active",
          "totalKiB": "468717568",
          "usedKiB": "461373440",
          "availableKiB": "7344128",
          "percent": "98.43%"
        },
        {
          "name": "tr-sda-vmstore",
          "type": "lvm",
          "status": "active",
          "totalKiB": "975708160",
          "usedKiB": "947912704",
          "availableKiB": "27795456",
          "percent": "97.15%"
        },
        {
          "name": "truenas-smb",
          "type": "cifs",
          "status": "active",
          "totalKiB": "8879492224",
          "usedKiB": "532885248",
          "availableKiB": "8346606976",
          "percent": "6.00%"
        }
      ],
      "pciDevices": [
        "00:00.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Root Complex",
        "00:00.2 IOMMU: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) I/O Memory Management Unit",
        "00:01.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "00:01.1 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) PCIe GPP Bridge",
        "00:01.2 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) PCIe GPP Bridge",
        "00:01.3 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) PCIe GPP Bridge",
        "00:02.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "00:03.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "00:04.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "00:07.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "00:07.1 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Internal PCIe GPP Bridge 0 to Bus B",
        "00:08.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "00:08.1 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Internal PCIe GPP Bridge 0 to Bus B",
        "00:14.0 SMBus: Advanced Micro Devices, Inc. [AMD] FCH SMBus Controller (rev 59)",
        "00:14.3 ISA bridge: Advanced Micro Devices, Inc. [AMD] FCH LPC Bridge (rev 51)",
        "00:18.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 0",
        "00:18.1 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 1",
        "00:18.2 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 2",
        "00:18.3 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 3",
        "00:18.4 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 4",
        "00:18.5 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 5",
        "00:18.6 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 6",
        "00:18.7 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 7",
        "00:19.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 0",
        "00:19.1 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 1",
        "00:19.2 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 2",
        "00:19.3 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 3",
        "00:19.4 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 4",
        "00:19.5 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 5",
        "00:19.6 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 6",
        "00:19.7 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Data Fabric: Device 18h; Function 7",
        "01:00.0 USB controller: Advanced Micro Devices, Inc. [AMD] X399 Series Chipset USB 3.1 xHCI Controller (rev 02)",
        "01:00.1 SATA controller: Advanced Micro Devices, Inc. [AMD] X399 Series Chipset SATA Controller (rev 02)",
        "01:00.2 PCI bridge: Advanced Micro Devices, Inc. [AMD] X399 Series Chipset PCIe Bridge (rev 02)",
        "02:00.0 PCI bridge: Advanced Micro Devices, Inc. [AMD] 300 Series Chipset PCIe Port (rev 02)",
        "02:04.0 PCI bridge: Advanced Micro Devices, Inc. [AMD] 300 Series Chipset PCIe Port (rev 02)",
        "02:05.0 PCI bridge: Advanced Micro Devices, Inc. [AMD] 300 Series Chipset PCIe Port (rev 02)",
        "02:06.0 PCI bridge: Advanced Micro Devices, Inc. [AMD] 300 Series Chipset PCIe Port (rev 02)",
        "02:07.0 PCI bridge: Advanced Micro Devices, Inc. [AMD] 300 Series Chipset PCIe Port (rev 02)",
        "08:00.0 SATA controller: ASMedia Technology Inc. ASM1166 Serial ATA Controller (rev 02)",
        "09:00.0 VGA compatible controller: NVIDIA Corporation GA102 [GeForce RTX 3090] (rev a1)",
        "09:00.1 Audio device: NVIDIA Corporation GA102 High Definition Audio Controller (rev a1)",
        "0a:00.0 Non-Essential Instrumentation [1300]: Advanced Micro Devices, Inc. [AMD] Zeppelin/Raven/Raven2 PCIe Dummy Function",
        "0a:00.2 Encryption controller: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Platform Security Processor (PSP) 3.0 Device",
        "0a:00.3 USB controller: Advanced Micro Devices, Inc. [AMD] Zeppelin USB 3.0 xHCI Compliant Host Controller",
        "0b:00.0 Non-Essential Instrumentation [1300]: Advanced Micro Devices, Inc. [AMD] Zeppelin/Renoir PCIe Dummy Function",
        "0b:00.2 SATA controller: Advanced Micro Devices, Inc. [AMD] FCH SATA Controller [AHCI mode] (rev 51)",
        "0b:00.3 Audio device: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) HD Audio Controller",
        "40:00.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Root Complex",
        "40:00.2 IOMMU: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) I/O Memory Management Unit",
        "40:01.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "40:01.1 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) PCIe GPP Bridge",
        "40:01.2 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) PCIe GPP Bridge",
        "40:01.3 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) PCIe GPP Bridge",
        "40:02.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "40:03.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "40:03.1 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) PCIe GPP Bridge",
        "40:04.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "40:07.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "40:07.1 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Internal PCIe GPP Bridge 0 to Bus B",
        "40:08.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-1fh) PCIe Dummy Host Bridge",
        "40:08.1 PCI bridge: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Internal PCIe GPP Bridge 0 to Bus B",
        "41:00.0 Non-Volatile memory controller: Realtek Semiconductor Co., Ltd. RTS5765DL NVMe SSD Controller (DRAM-less) (rev 01)",
        "42:00.0 Non-Volatile memory controller: Realtek Semiconductor Co., Ltd. RTS5765DL NVMe SSD Controller (DRAM-less) (rev 01)",
        "43:00.0 VGA compatible controller: NVIDIA Corporation GA102 [GeForce RTX 3090] (rev a1)",
        "43:00.1 Audio device: NVIDIA Corporation GA102 High Definition Audio Controller (rev a1)",
        "44:00.0 Ethernet controller: Mellanox Technologies MT27500 Family [ConnectX-3]",
        "45:00.0 Non-Essential Instrumentation [1300]: Advanced Micro Devices, Inc. [AMD] Zeppelin/Raven/Raven2 PCIe Dummy Function",
        "45:00.2 Encryption controller: Advanced Micro Devices, Inc. [AMD] Family 17h (Models 00h-0fh) Platform Security Processor (PSP) 3.0 Device",
        "45:00.3 USB controller: Advanced Micro Devices, Inc. [AMD] Zeppelin USB 3.0 xHCI Compliant Host Controller",
        "46:00.0 Non-Essential Instrumentation [1300]: Advanced Micro Devices, Inc. [AMD] Zeppelin/Renoir PCIe Dummy Function",
        "46:00.2 SATA controller: Advanced Micro Devices, Inc. [AMD] FCH SATA Controller [AHCI mode] (rev 51)"
      ],
      "usbDevices": [
        "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub",
        "Bus 003 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 004 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub",
        "Bus 005 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 005 Device 002: ID 040b:2000 Weltrend Semiconductor wired Keyboard [Dynex DX-WRK1401]",
        "Bus 006 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub"
      ],
      "networkAdapters": [
        "44:00.0 Ethernet controller: Mellanox Technologies MT27500 Family [ConnectX-3]"
      ]
    },
    {
      "id": "dell",
      "name": "Dell OptiPlex",
      "model": "OptiPlex 7060 \u00b7 exposed motherboard",
      "cpu": "Intel(R) Core(TM) i5-8500 CPU @ 3.00GHz \u00b7 6 threads",
      "ram": "40 GB",
      "zone": "dell",
      "link": "Wired \u00b7 2.5 GbE",
      "role": "Temporary worker + live storage",
      "suggested": "Restartable jobs and experiments",
      "summary": "Two physical drives visible. The configured T-FORCE data path is absent from host block-device discovery.",
      "advice": "Investigate inactive dell-ssd-vmstore before relying on its guest mount or Longhorn status.",
      "loss": "Work here stops. The owner accepts temporary hardware, but its current single-copy volumes are still real dependencies.",
      "power": null,
      "ip": "192.168.10.16",
      "kind": "Proxmox",
      "disks": [
        {
          "device": "sdb",
          "model": "R9M2SH6Q240GQF72C",
          "bytes": 240057409536,
          "interface": "sata",
          "role": "Proxmox + Talos system",
          "path": "pve / local-lvm \u2192 VM 100 scsi0 (128 GiB)",
          "note": "SMART overall passed; 31 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 31,
            "powerOnHours": 95,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 187,
                "name": "Reported_Uncorrect",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 198,
                "name": "Offline_Uncorrectable",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 199,
                "name": "UDMA_CRC_Error_Count",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 202,
                "name": "Unknown_SSD_Attribute",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 231,
                "name": "Unknown_SSD_Attribute",
                "raw": 100,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "sdc",
          "model": "APPLE SSD SM0256G",
          "bytes": 251000193024,
          "interface": "sata",
          "role": "Longhorn data",
          "path": "dell-apple-vmstore \u2192 VM 100 scsi2 (220 GiB)",
          "note": "SMART overall passed; 29 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 29,
            "powerOnHours": 35731,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 197,
                "name": "Current_Pending_Sector",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 199,
                "name": "UDMA_CRC_Error_Count",
                "raw": 0,
                "normalized": 200
              }
            ]
          }
        }
      ],
      "vms": [
        {
          "id": "100",
          "name": "talos-prod-cluster-v2-dell-workers-2jfrb8",
          "ramMiB": 30720,
          "vcpus": 6,
          "state": "running",
          "ip": "192.168.10.84",
          "disks": [
            {
              "slot": "scsi0",
              "backing": "local-lvm:vm-100-disk-0",
              "size": "128 GiB"
            },
            {
              "slot": "scsi1",
              "backing": "dell-ssd-vmstore:vm-100-disk-0",
              "size": "400 GiB"
            },
            {
              "slot": "scsi2",
              "backing": "dell-apple-vmstore:vm-100-disk-0",
              "size": "220 GiB"
            }
          ],
          "namespaces": [
            {
              "name": "cloudflared",
              "pods": 1
            },
            {
              "name": "csi-driver-nfs",
              "pods": 1
            },
            {
              "name": "csi-driver-smb",
              "pods": 1
            },
            {
              "name": "intel-gpu-plugin",
              "pods": 1
            },
            {
              "name": "kube-system",
              "pods": 2
            },
            {
              "name": "loki-stack",
              "pods": 1
            },
            {
              "name": "longhorn-system",
              "pods": 4
            },
            {
              "name": "node-feature-discovery",
              "pods": 1
            },
            {
              "name": "opentelemetry",
              "pods": 1
            },
            {
              "name": "prometheus-stack",
              "pods": 1
            },
            {
              "name": "truenas-csi",
              "pods": 1
            },
            {
              "name": "tubesync",
              "pods": 1
            }
          ],
          "passthrough": {
            "hostpci0": "mapping=intel-igpu,pcie=1"
          },
          "talos": "Talos (v1.14.2)",
          "kubernetes": "v1.37.1"
        }
      ],
      "ramBytes": 41846075392,
      "memoryAvailableBytes": 7199395840,
      "software": "pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-23-pve)",
      "storages": [
        {
          "name": "dell-apple-vmstore",
          "type": "lvm",
          "status": "active",
          "totalKiB": "245112832",
          "usedKiB": "230686720",
          "availableKiB": "14426112",
          "percent": "94.11%"
        },
        {
          "name": "dell-ssd-vmstore",
          "type": "lvm",
          "status": "inactive",
          "totalKiB": "0",
          "usedKiB": "0",
          "availableKiB": "0",
          "percent": "0.00%"
        },
        {
          "name": "local",
          "type": "dir",
          "status": "active",
          "totalKiB": "69799144",
          "usedKiB": "16102220",
          "availableKiB": "50105552",
          "percent": "23.07%"
        },
        {
          "name": "local-lvm",
          "type": "lvmthin",
          "status": "active",
          "totalKiB": "146800640",
          "usedKiB": "96682901",
          "availableKiB": "50117738",
          "percent": "65.86%"
        }
      ],
      "pciDevices": [
        "00:00.0 Host bridge: Intel Corporation 8th Gen Core Processor Host Bridge/DRAM Registers (rev 07)",
        "00:02.0 VGA compatible controller: Intel Corporation CoffeeLake-S GT2 [UHD Graphics 630]",
        "00:08.0 System peripheral: Intel Corporation Xeon E3-1200 v5/v6 / E3-1500 v5 / 6th/7th/8th Gen Core Processor Gaussian Mixture Model",
        "00:12.0 Signal processing controller: Intel Corporation Cannon Lake PCH Thermal Controller (rev 10)",
        "00:14.0 USB controller: Intel Corporation Cannon Lake PCH USB 3.1 xHCI Host Controller (rev 10)",
        "00:14.2 RAM memory: Intel Corporation Cannon Lake PCH Shared SRAM (rev 10)",
        "00:15.0 Serial bus controller: Intel Corporation Cannon Lake PCH Serial IO I2C Controller #0 (rev 10)",
        "00:16.0 Communication controller: Intel Corporation Cannon Lake PCH HECI Controller (rev 10)",
        "00:16.3 Serial controller: Intel Corporation Cannon Lake PCH Active Management Technology - SOL (rev 10)",
        "00:17.0 SATA controller: Intel Corporation Cannon Lake PCH SATA AHCI Controller (rev 10)",
        "00:1b.0 PCI bridge: Intel Corporation Cannon Lake PCH PCI Express Root Port #17 (rev f0)",
        "00:1d.0 PCI bridge: Intel Corporation Cannon Lake PCH PCI Express Root Port #9 (rev f0)",
        "00:1f.0 ISA bridge: Intel Corporation Q370 Chipset LPC/eSPI Controller (rev 10)",
        "00:1f.3 Audio device: Intel Corporation Cannon Lake PCH cAVS (rev 10)",
        "00:1f.4 SMBus: Intel Corporation Cannon Lake PCH SMBus Controller (rev 10)",
        "00:1f.5 Serial bus controller: Intel Corporation Cannon Lake PCH SPI Controller (rev 10)",
        "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection (7) I219-LM (rev 10)",
        "01:00.0 SATA controller: Samsung Electronics Co Ltd S4LN058A01[SSUBX] AHCI SSD Controller (Apple slot) (rev 01)",
        "02:00.0 Ethernet controller: Realtek Semiconductor Co., Ltd. RTL8125 2.5GbE Controller (rev 04)"
      ],
      "usbDevices": [
        "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub"
      ],
      "networkAdapters": [
        "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection (7) I219-LM (rev 10)",
        "02:00.0 Ethernet controller: Realtek Semiconductor Co., Ltd. RTL8125 2.5GbE Controller (rev 04)"
      ]
    },
    {
      "id": "shed",
      "name": "Shed HP Mini",
      "model": "ProDesk 600 G4 DM",
      "cpu": "Intel(R) Core(TM) i5-8500T CPU @ 2.10GHz \u00b7 6 threads",
      "ram": "32 GB",
      "zone": "shed",
      "link": "Ethernet \u2192 ASUS Wi-Fi media bridge",
      "role": "Radio / USB edge worker",
      "suggested": "Attached devices + edge jobs",
      "summary": "Talos sees Ethernet; the trip back to the house crosses Wi-Fi.",
      "advice": "Keep it out of storage replication and quorum. Its Longhorn disks are already unschedulable.",
      "loss": "Attached radio/USB jobs stop. No Longhorn replicas were scheduled here in the audit.",
      "power": null,
      "ip": "192.168.10.20",
      "kind": "Proxmox",
      "disks": [
        {
          "device": "sda",
          "model": "PNY CS900 1TB SSD",
          "bytes": 1000204886016,
          "interface": "sata",
          "role": "Longhorn scheduling disabled",
          "path": "hp-ssd-vmstore \u2192 VM 100 scsi1 (850 GiB)",
          "note": "SMART overall passed; 33 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 33,
            "powerOnHours": 25327,
            "ataCounters": [
              {
                "id": 231,
                "name": "SSD_Life_Left",
                "raw": 93,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "nvme0n1",
          "model": "SK hynix BC501 HFM256GDJTNG-8310A",
          "bytes": 256060514304,
          "interface": "nvme",
          "role": "Proxmox + Talos system",
          "path": "pve / local-lvm \u2192 VM 100 scsi0 (128 GiB)",
          "note": "SMART overall passed; 41 \u00b0C at collection. NVMe endurance used: 6%; media errors: 0.",
          "health": {
            "passed": true,
            "temperatureC": 41,
            "powerOnHours": 50406,
            "percentage_used": 6,
            "media_errors": 0,
            "critical_warning": 0,
            "data_units_written": 45183533,
            "ataCounters": []
          }
        }
      ],
      "vms": [
        {
          "id": "100",
          "name": "talos-prod-cluster-v2-hp-micro-workers-pstbbd",
          "ramMiB": 12288,
          "vcpus": 4,
          "state": "running",
          "ip": "192.168.10.128",
          "disks": [
            {
              "slot": "scsi0",
              "backing": "local-lvm:vm-100-disk-0",
              "size": "128 GiB"
            },
            {
              "slot": "scsi1",
              "backing": "hp-ssd-vmstore:vm-100-disk-0",
              "size": "850 GiB"
            }
          ],
          "namespaces": [
            {
              "name": "csi-driver-nfs",
              "pods": 1
            },
            {
              "name": "csi-driver-smb",
              "pods": 1
            },
            {
              "name": "intercept",
              "pods": 1
            },
            {
              "name": "kube-system",
              "pods": 2
            },
            {
              "name": "longhorn-system",
              "pods": 4
            },
            {
              "name": "node-feature-discovery",
              "pods": 1
            },
            {
              "name": "opentelemetry",
              "pods": 1
            },
            {
              "name": "prometheus-stack",
              "pods": 1
            },
            {
              "name": "truenas-csi",
              "pods": 1
            }
          ],
          "passthrough": {
            "usb0": "mapping=sdr-blogv4,usb3=1",
            "usb1": "mapping=sdr-adsb,usb3=1",
            "usb2": "mapping=wifi-usb,usb3=1"
          },
          "talos": "Talos (v1.14.2)",
          "kubernetes": "v1.37.1"
        }
      ],
      "ramBytes": 33419886592,
      "memoryAvailableBytes": 25823387648,
      "software": "pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-20-pve)",
      "storages": [
        {
          "name": "hp-ssd-vmstore",
          "type": "lvm",
          "status": "active",
          "totalKiB": "976760832",
          "usedKiB": "891289600",
          "availableKiB": "85471232",
          "percent": "91.25%"
        },
        {
          "name": "local",
          "type": "dir",
          "status": "active",
          "totalKiB": "71017632",
          "usedKiB": "14320980",
          "availableKiB": "53043432",
          "percent": "20.17%"
        },
        {
          "name": "local-lvm",
          "type": "lvmthin",
          "status": "active",
          "totalKiB": "160669696",
          "usedKiB": "15119018",
          "availableKiB": "145550677",
          "percent": "9.41%"
        }
      ],
      "pciDevices": [
        "00:00.0 Host bridge: Intel Corporation 8th Gen Core Processor Host Bridge/DRAM Registers (rev 07)",
        "00:02.0 VGA compatible controller: Intel Corporation CoffeeLake-S GT2 [UHD Graphics 630]",
        "00:12.0 Signal processing controller: Intel Corporation Cannon Lake PCH Thermal Controller (rev 10)",
        "00:14.0 USB controller: Intel Corporation Cannon Lake PCH USB 3.1 xHCI Host Controller (rev 10)",
        "00:14.2 RAM memory: Intel Corporation Cannon Lake PCH Shared SRAM (rev 10)",
        "00:14.3 Network controller: Intel Corporation Cannon Lake PCH CNVi WiFi (rev 10)",
        "00:16.0 Communication controller: Intel Corporation Cannon Lake PCH HECI Controller (rev 10)",
        "00:16.3 Serial controller: Intel Corporation Cannon Lake PCH Active Management Technology - SOL (rev 10)",
        "00:17.0 SATA controller: Intel Corporation Cannon Lake PCH SATA AHCI Controller (rev 10)",
        "00:1b.0 PCI bridge: Intel Corporation Cannon Lake PCH PCI Express Root Port #21 (rev f0)",
        "00:1f.0 ISA bridge: Intel Corporation Q370 Chipset LPC/eSPI Controller (rev 10)",
        "00:1f.3 Audio device: Intel Corporation Cannon Lake PCH cAVS (rev 10)",
        "00:1f.4 SMBus: Intel Corporation Cannon Lake PCH SMBus Controller (rev 10)",
        "00:1f.5 Serial bus controller: Intel Corporation Cannon Lake PCH SPI Controller (rev 10)",
        "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection (7) I219-LM (rev 10)",
        "01:00.0 Non-Volatile memory controller: SK hynix BC501 NVMe Solid State Drive"
      ],
      "usbDevices": [
        "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 001 Device 003: ID 2109:2812 VIA Labs, Inc. VL812 Hub",
        "Bus 001 Device 004: ID 8087:0aaa Intel Corp. Bluetooth 9460/9560 Jefferson Peak (JfP)",
        "Bus 001 Device 005: ID 0bda:2838 Realtek Semiconductor Corp. RTL2838 DVB-T",
        "Bus 001 Device 006: ID 0bda:2838 Realtek Semiconductor Corp. RTL2838 DVB-T",
        "Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub",
        "Bus 002 Device 002: ID 2109:0812 VIA Labs, Inc. VL812 Hub",
        "Bus 002 Device 003: ID 0bda:8153 Realtek Semiconductor Corp. RTL8153 Gigabit Ethernet Adapter",
        "Bus 002 Device 004: ID 2357:0138 TP-Link 802.11ac NIC"
      ],
      "networkAdapters": [
        "00:14.3 Network controller: Intel Corporation Cannon Lake PCH CNVi WiFi (rev 10)",
        "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection (7) I219-LM (rev 10)"
      ]
    },
    {
      "id": "pi",
      "name": "Omni / DNS Pi",
      "model": "Raspberry Pi 5",
      "cpu": "Cortex-A76 \u00b7 4 threads",
      "ram": "8 GB",
      "ramBytes": 8317272064,
      "zone": null,
      "link": "LAN; link speed not captured",
      "ip": "192.168.10.15",
      "kind": "External management",
      "role": "Omni + Technitium DNS",
      "suggested": "Keep management outside Kubernetes",
      "summary": "Small box, big job: management and internal DNS live together here.",
      "advice": "Keep the NVMe setup. Document how to recover this Pi because Omni and DNS share it.",
      "loss": "Omni management and Technitium DNS become unavailable. Existing Kubernetes processes can continue, but management and new DNS lookups are affected.",
      "power": null,
      "disks": [
        {
          "device": "nvme0n1",
          "model": "Patriot M.2 P300 256GB",
          "bytes": 256060514304,
          "interface": "nvme",
          "role": "Management system",
          "path": "Ubuntu root; Docker services",
          "note": "SMART overall passed; 32 \u00b0C at collection. NVMe endurance used: 13%; media errors: 0.",
          "health": {
            "passed": true,
            "temperatureC": 32,
            "powerOnHours": 14194,
            "percentage_used": 13,
            "media_errors": 0,
            "critical_warning": 0,
            "data_units_written": 82877960,
            "ataCounters": []
          }
        }
      ],
      "vms": [],
      "memoryAvailableBytes": 6148456448,
      "software": "Ubuntu 26.04 LTS",
      "services": [
        {
          "name": "proxcenter-frontend",
          "image": "ghcr.io/adminsyspro/proxcenter-frontend:1.4.10-arm64-20261001",
          "status": "Up 13 days (healthy)"
        },
        {
          "name": "proxcenter-postgres",
          "image": "postgres:16.15-alpine3.24",
          "status": "Up 13 days (healthy)"
        },
        {
          "name": "omni",
          "image": "ghcr.io/siderolabs/omni:v1.12.3",
          "status": "Up 13 days"
        },
        {
          "name": "technitium-dns",
          "image": "technitium/dns-server:15.5.1",
          "status": "Up 13 days"
        },
        {
          "name": "omni-infra-provider-proxmox-hp-micro",
          "image": "ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0",
          "status": "Up 13 days"
        },
        {
          "name": "omni-infra-provider-proxmox-hp-elite",
          "image": "ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0",
          "status": "Up 13 days"
        },
        {
          "name": "omni-infra-provider-proxmox-hp-sff",
          "image": "ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0",
          "status": "Up 13 days"
        },
        {
          "name": "omni-infra-provider-proxmox-dell",
          "image": "ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0",
          "status": "Up 13 days"
        },
        {
          "name": "omni-infra-provider-proxmox-threadripper",
          "image": "ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0",
          "status": "Up 13 days"
        }
      ],
      "pciDevices": [
        "0001:00:00.0 PCI bridge: Broadcom Inc. and subsidiaries BCM2712 PCIe Bridge (rev 21)",
        "0001:01:00.0 Non-Volatile memory controller: Silicon Motion, Inc. SM2263EN/SM2263XT (DRAM-less) NVMe SSD Controllers (rev 03)",
        "0002:00:00.0 PCI bridge: Broadcom Inc. and subsidiaries BCM2712 PCIe Bridge (rev 21)",
        "0002:01:00.0 Ethernet controller: Raspberry Pi Ltd RP1 PCIe 2.0 South Bridge"
      ],
      "usbDevices": [
        "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 002 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 003 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub",
        "Bus 004 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 005 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub",
        "Bus 005 Device 002: ID 0b05:1976 ASUSTek Computer, Inc. USB 10/100/1G/2.5G LAN"
      ]
    },
    {
      "id": "nas",
      "name": "TrueNAS",
      "model": "HPE DL360 \u00b7 one Xeon",
      "cpu": "Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz \u00b7 28 threads",
      "ram": "384 GB ECC",
      "ramBytes": 405414486016,
      "zone": null,
      "link": "10 GbE",
      "ip": "192.168.10.133",
      "kind": "NAS",
      "role": "Shared files + RustFS backups",
      "suggested": "Measure working-set needs before sizing replacement RAM",
      "summary": "Four imported pools, eleven physical drives, and external RustFS backups. Pool ONLINE state does not verify backups.",
      "advice": "Use the dated NAS benchmarks to compare pool and cache performance. Choose durability before moving database writes here; short tests do not establish minimum RAM.",
      "loss": "NAS-backed workloads can stall, and backup/restore jobs cannot reach RustFS. This outage trade-off is accepted; it is not permission to restore empty data.",
      "power": null,
      "disks": [
        {
          "device": "sda",
          "model": "HP SSD S700 500GB",
          "bytes": 500107862016,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "ai-pool",
          "note": "SMART overall passed; 44 \u00b0C at collection. Lifetime CRC counter: 816; this alone does not prove current errors.",
          "health": {
            "passed": true,
            "temperatureC": 44,
            "powerOnHours": 51391,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 187,
                "name": "Reported_Uncorrect",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 198,
                "name": "Offline_Uncorrectable",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 199,
                "name": "UDMA_CRC_Error_Count",
                "raw": 816,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "sdb",
          "model": "Samsung SSD 860 EVO 1TB",
          "bytes": 1000204886016,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "ai-pool",
          "note": "SMART overall passed; 32 \u00b0C at collection. Lifetime CRC counter: 4; this alone does not prove current errors.",
          "health": {
            "passed": true,
            "temperatureC": 32,
            "powerOnHours": 47995,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 187,
                "name": "Uncorrectable_Error_Cnt",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 199,
                "name": "CRC_Error_Count",
                "raw": 4,
                "normalized": 99
              }
            ]
          }
        },
        {
          "device": "sdc",
          "model": "HUH721010AL4200",
          "bytes": 10000831348736,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "BigTank mirror-0",
          "note": "SMART overall passed; 37 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 37,
            "powerOnHours": 8372,
            "ataCounters": []
          }
        },
        {
          "device": "sdd",
          "model": "HUH721010AL4200",
          "bytes": 10000831348736,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "BigTank mirror-1",
          "note": "SMART overall passed; 50 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 50,
            "powerOnHours": 15324,
            "ataCounters": []
          }
        },
        {
          "device": "sde",
          "model": "T-FORCE 512GB",
          "bytes": 512110190592,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "boot-pool mirror",
          "note": "SMART overall passed; 33 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 33,
            "powerOnHours": 27729,
            "ataCounters": [
              {
                "id": 231,
                "name": "Unknown_SSD_Attribute",
                "raw": 96,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "sdf",
          "model": "HUH721010AL4200",
          "bytes": 10000831348736,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "BigTank mirror-0",
          "note": "SMART overall passed; 45 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 45,
            "powerOnHours": 8639,
            "ataCounters": []
          }
        },
        {
          "device": "sdg",
          "model": "P3-512",
          "bytes": 512110190592,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "ai-pool",
          "note": "SMART overall passed; 30 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 30,
            "powerOnHours": 8551,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 197,
                "name": "Current_Pending_Sector",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 198,
                "name": "Offline_Uncorrectable",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 199,
                "name": "UDMA_CRC_Error_Count",
                "raw": 0,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "sdh",
          "model": "HUH721010AL4200",
          "bytes": 10000831348736,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "BigTank mirror-1",
          "note": "SMART overall passed; 50 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 50,
            "powerOnHours": 15053,
            "ataCounters": []
          }
        },
        {
          "device": "sdi",
          "model": "MK000480GWCEV",
          "bytes": 480103981056,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "boot-pool mirror",
          "note": "SMART overall passed; 19 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 19,
            "powerOnHours": 56353,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 202,
                "name": "Unknown_SSD_Attribute",
                "raw": 0,
                "normalized": 100
              }
            ]
          }
        },
        {
          "device": "sdj",
          "model": "ST10000NM0096",
          "bytes": 10000831348736,
          "interface": "sas",
          "role": "NAS pool member",
          "path": "Backup10T single disk",
          "note": "SMART overall passed; 32 \u00b0C at collection.",
          "health": {
            "passed": true,
            "temperatureC": 32,
            "powerOnHours": 58401,
            "ataCounters": []
          }
        },
        {
          "device": "sdk",
          "model": "Samsung SSD 850 EVO 500GB",
          "bytes": 500107862016,
          "interface": "sas",
          "role": "Unassigned physical disk",
          "path": "No imported pool membership observed",
          "note": "SMART overall passed; 31 \u00b0C at collection. Lifetime CRC counter: 8162; this alone does not prove current errors. Samsung 850 EVO retired from Dell in PR #2946; SMART pass does not reverse the recorded load-test failure.",
          "health": {
            "passed": true,
            "temperatureC": 31,
            "powerOnHours": 75027,
            "ataCounters": [
              {
                "id": 5,
                "name": "Reallocated_Sector_Ct",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 187,
                "name": "Uncorrectable_Error_Cnt",
                "raw": 0,
                "normalized": 100
              },
              {
                "id": 199,
                "name": "CRC_Error_Count",
                "raw": 8162,
                "normalized": 91
              }
            ]
          }
        }
      ],
      "vms": [],
      "memoryCheckedAt": "2026-10-15T04:08:38.371121+00:00",
      "memory": [
        {
          "name": "ZFS cache",
          "gib": 83.3
        },
        {
          "name": "OS, apps and other allocations",
          "gib": 11.2
        },
        {
          "name": "Free",
          "gib": 283.0
        }
      ],
      "pools": [
        {
          "name": "Backup10T",
          "size": "9.08 TiB",
          "used": 68,
          "layout": "One 10 TB disk",
          "note": "A separate pool on the same NAS, with no member-disk redundancy."
        },
        {
          "name": "BigTank",
          "size": "18.16 TiB",
          "used": 56,
          "layout": "Two mirrors \u00b7 four 10 TB disks",
          "note": "Main files and RustFS. One disk can fail in each mirror; losing both members of the same mirror loses the pool."
        },
        {
          "name": "ai-pool",
          "size": "1.82 TiB",
          "used": 76,
          "layout": "Three SSDs striped",
          "note": "No mirror/parity. Any member loss threatens the whole pool."
        },
        {
          "name": "boot-pool",
          "size": "0.22 TiB",
          "used": 25,
          "layout": "T-FORCE + HPE mirror",
          "note": "The HPE is a boot mirror member, not a spare. Pool size is not the raw sum of member capacities."
        }
      ],
      "memoryAvailableBytes": 304401170432,
      "software": "TrueNAS-28.0.0-MASTER+20261012-230219",
      "applianceVMs": [
        {
          "id": 5,
          "name": "talos_prod_control_03",
          "memory": 8000,
          "vcpus": 1,
          "cores": 2,
          "threads": 1,
          "autostart": false,
          "status": {
            "state": "STOPPED",
            "pid": null,
            "domain_state": null
          }
        }
      ],
      "services": [
        {
          "name": "tailscale",
          "state": "RUNNING",
          "version": "1.4.16"
        },
        {
          "name": "rustfs",
          "state": "RUNNING",
          "version": "1.1.31"
        },
        {
          "name": "physical-monitoring",
          "state": "RUNNING",
          "version": "1.0.0"
        }
      ],
      "pciDevices": [
        "00:00.0 Host bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DMI2 (rev 01)",
        "00:01.0 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 1 (rev 01)",
        "00:01.1 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 1 (rev 01)",
        "00:02.0 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 2 (rev 01)",
        "00:02.1 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 2 (rev 01)",
        "00:02.2 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 2 (rev 01)",
        "00:02.3 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 2 (rev 01)",
        "00:03.0 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 3 (rev 01)",
        "00:03.1 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 3 (rev 01)",
        "00:03.2 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 3 (rev 01)",
        "00:03.3 PCI bridge: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D PCI Express Root Port 3 (rev 01)",
        "00:04.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Crystal Beach DMA Channel 0 (rev 01)",
        "00:04.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Crystal Beach DMA Channel 1 (rev 01)",
        "00:04.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Crystal Beach DMA Channel 2 (rev 01)",
        "00:04.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Crystal Beach DMA Channel 3 (rev 01)",
        "00:04.4 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Crystal Beach DMA Channel 4 (rev 01)",
        "00:04.5 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Crystal Beach DMA Channel 5 (rev 01)",
        "00:04.6 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Crystal Beach DMA Channel 6 (rev 01)",
        "00:04.7 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Crystal Beach DMA Channel 7 (rev 01)",
        "00:05.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Map/VTd_Misc/System Management (rev 01)",
        "00:05.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D IIO Hot Plug (rev 01)",
        "00:05.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D IIO RAS/Control Status/Global Errors (rev 01)",
        "00:05.4 PIC: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D I/O APIC (rev 01)",
        "00:11.0 Unassigned class [ff00]: Intel Corporation C610/X99 series chipset SPSR (rev 05)",
        "00:14.0 USB controller: Intel Corporation C610/X99 series chipset USB xHCI Host Controller (rev 05)",
        "00:1a.0 USB controller: Intel Corporation C610/X99 series chipset USB Enhanced Host Controller #2 (rev 05)",
        "00:1c.0 PCI bridge: Intel Corporation C610/X99 series chipset PCI Express Root Port #1 (rev d5)",
        "00:1c.2 PCI bridge: Intel Corporation C610/X99 series chipset PCI Express Root Port #3 (rev d5)",
        "00:1c.4 PCI bridge: Intel Corporation C610/X99 series chipset PCI Express Root Port #5 (rev d5)",
        "00:1c.6 PCI bridge: Intel Corporation C610/X99 series chipset PCI Express Root Port #7 (rev d5)",
        "00:1c.7 PCI bridge: Intel Corporation C610/X99 series chipset PCI Express Root Port #8 (rev d5)",
        "00:1d.0 USB controller: Intel Corporation C610/X99 series chipset USB Enhanced Host Controller #1 (rev 05)",
        "00:1f.0 ISA bridge: Intel Corporation C610/X99 series chipset LPC Controller (rev 05)",
        "00:1f.3 SMBus: Intel Corporation C610/X99 series chipset SMBus Controller (rev 05)",
        "01:00.0 System peripheral: Hewlett-Packard Company Integrated Lights-Out Standard Slave Instrumentation & System Support (rev 06)",
        "01:00.1 VGA compatible controller: Matrox Electronics Systems Ltd. MGA G200EH (rev 01)",
        "01:00.2 System peripheral: Hewlett-Packard Company Integrated Lights-Out Standard Management Processor Support and Messaging (rev 06)",
        "01:00.4 USB controller: Hewlett-Packard Company Integrated Lights-Out Standard Virtual USB Controller (rev 03)",
        "02:00.0 Ethernet controller: Broadcom Inc. and subsidiaries NetXtreme BCM5719 Gigabit Ethernet PCIe (rev 01)",
        "02:00.1 Ethernet controller: Broadcom Inc. and subsidiaries NetXtreme BCM5719 Gigabit Ethernet PCIe (rev 01)",
        "02:00.2 Ethernet controller: Broadcom Inc. and subsidiaries NetXtreme BCM5719 Gigabit Ethernet PCIe (rev 01)",
        "02:00.3 Ethernet controller: Broadcom Inc. and subsidiaries NetXtreme BCM5719 Gigabit Ethernet PCIe (rev 01)",
        "03:00.0 Serial Attached SCSI controller: Hewlett-Packard Company Smart Array Gen9 Controllers (rev 01)",
        "04:00.0 Ethernet controller: Intel Corporation 82599ES 10-Gigabit SFI/SFP+ Network Connection (rev 01)",
        "04:00.1 Ethernet controller: Intel Corporation 82599ES 10-Gigabit SFI/SFP+ Network Connection (rev 01)",
        "05:00.0 Serial Attached SCSI controller: Broadcom / LSI SAS2308 PCI-Express Fusion-MPT SAS-2 (rev 05)",
        "ff:0b.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D R3 QPI Link 0/1 (rev 01)",
        "ff:0b.1 Performance counters: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D R3 QPI Link 0/1 (rev 01)",
        "ff:0b.2 Performance counters: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D R3 QPI Link 0/1 (rev 01)",
        "ff:0b.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D R3 QPI Link Debug (rev 01)",
        "ff:0c.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0c.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0c.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0c.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0c.4 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0c.5 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0c.6 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0c.7 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0d.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0d.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0d.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0d.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0d.4 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0d.5 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0f.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0f.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0f.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0f.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0f.4 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0f.5 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:0f.6 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Caching Agent (rev 01)",
        "ff:10.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D R2PCIe Agent (rev 01)",
        "ff:10.1 Performance counters: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D R2PCIe Agent (rev 01)",
        "ff:10.5 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Ubox (rev 01)",
        "ff:10.6 Performance counters: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Ubox (rev 01)",
        "ff:10.7 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Ubox (rev 01)",
        "ff:12.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Home Agent 0 (rev 01)",
        "ff:12.1 Performance counters: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Home Agent 0 (rev 01)",
        "ff:12.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Home Agent 0 Debug (rev 01)",
        "ff:12.4 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Home Agent 1 (rev 01)",
        "ff:12.5 Performance counters: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Home Agent 1 (rev 01)",
        "ff:12.6 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Home Agent 1 Debug (rev 01)",
        "ff:13.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 0 - Target Address/Thermal/RAS (rev 01)",
        "ff:13.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 0 - Target Address/Thermal/RAS (rev 01)",
        "ff:13.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 0 - Channel Target Address Decoder (rev 01)",
        "ff:13.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 0 - Channel Target Address Decoder (rev 01)",
        "ff:13.6 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 0/1 Broadcast (rev 01)",
        "ff:13.7 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Global Broadcast (rev 01)",
        "ff:14.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 0 - Channel 0 Thermal Control (rev 01)",
        "ff:14.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 0 - Channel 1 Thermal Control (rev 01)",
        "ff:14.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 0 - Channel 0 Error (rev 01)",
        "ff:14.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 0 - Channel 1 Error (rev 01)",
        "ff:14.4 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 0/1 Interface (rev 01)",
        "ff:14.5 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 0/1 Interface (rev 01)",
        "ff:14.6 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 0/1 Interface (rev 01)",
        "ff:14.7 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 0/1 Interface (rev 01)",
        "ff:16.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Target Address/Thermal/RAS (rev 01)",
        "ff:16.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Target Address/Thermal/RAS (rev 01)",
        "ff:16.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Channel Target Address Decoder (rev 01)",
        "ff:16.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Channel Target Address Decoder (rev 01)",
        "ff:16.6 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 2/3 Broadcast (rev 01)",
        "ff:16.7 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Global Broadcast (rev 01)",
        "ff:17.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 1 - Channel 0 Thermal Control (rev 01)",
        "ff:17.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 1 - Channel 1 Thermal Control (rev 01)",
        "ff:17.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 1 - Channel 0 Error (rev 01)",
        "ff:17.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Memory Controller 1 - Channel 1 Error (rev 01)",
        "ff:17.4 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 2/3 Interface (rev 01)",
        "ff:17.5 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 2/3 Interface (rev 01)",
        "ff:17.6 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 2/3 Interface (rev 01)",
        "ff:17.7 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D DDRIO Channel 2/3 Interface (rev 01)",
        "ff:1e.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Power Control Unit (rev 01)",
        "ff:1e.1 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Power Control Unit (rev 01)",
        "ff:1e.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Power Control Unit (rev 01)",
        "ff:1e.3 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Power Control Unit (rev 01)",
        "ff:1e.4 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Power Control Unit (rev 01)",
        "ff:1f.0 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Power Control Unit (rev 01)",
        "ff:1f.2 System peripheral: Intel Corporation Xeon E7 v4/Xeon E5 v4/Xeon E3 v4/Xeon D Power Control Unit (rev 01)"
      ],
      "usbDevices": [
        "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 001 Device 002: ID 8087:800a Intel Corp. Hub",
        "Bus 002 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 002 Device 002: ID 8087:8002 Intel Corp. 8 channel internal hub",
        "Bus 003 Device 001: ID 1d6b:0001 Linux Foundation 1.1 root hub",
        "Bus 004 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
        "Bus 004 Device 002: ID 0424:2660 Microchip Technology, Inc. (formerly SMSC) Hub",
        "Bus 005 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub"
      ],
      "nfsShares": [
        {
          "path": "/mnt/BigTank/k8s",
          "enabled": true,
          "ro": false
        },
        {
          "path": "/mnt/BigTank/proxmox",
          "enabled": true,
          "ro": false
        },
        {
          "path": "/mnt/BigTank/photos/All",
          "enabled": true,
          "ro": true
        },
        {
          "path": "/mnt/ai-pool/llama-cpp",
          "enabled": true,
          "ro": false
        },
        {
          "path": "/mnt/ai-pool/comfyui",
          "enabled": true,
          "ro": false
        },
        {
          "path": "/mnt/ai-pool/vllm",
          "enabled": true,
          "ro": false
        },
        {
          "path": "/mnt/BigTank/k8s/nfs/v/pvc-3d780155-d947-4d10-b6e0-9bd59d55ab3d",
          "enabled": true,
          "ro": false
        },
        {
          "path": "/mnt/BigTank/k8s/nfs/v/pvc-0ff82677-7159-4335-a539-61da5f034c8e",
          "enabled": true,
          "ro": false
        }
      ],
      "replication": [
        {
          "name": "BigTank/General,BigTank/backup,BigTank/photos - Backup10T",
          "enabled": true,
          "schedule": null,
          "state": {
            "state": "FINISHED",
            "datetime": {
              "$date": 1748136145000
            },
            "warnings": [
              "cannot mount '/mnt/Backup10T/General': failed to create mountpoint: Read-only file system",
              "cannot mount '/mnt/Backup10T/photos': failed to create mountpoint: Read-only file system"
            ],
            "last_snapshot": "BigTank/photos@auto-2025-05-23_19-27"
          }
        }
      ]
    }
  ],
  "claims": [
    {
      "namespace": "comfyui",
      "claim": "comfyui-storage-smb",
      "storage_class": "",
      "requested_storage": "250Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "consumers-energy-sync",
      "claim": "consumers-energy-sync-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "detached",
      "robustness": "unknown"
    },
    {
      "namespace": "container-registry",
      "claim": "registry",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "copyparty",
      "claim": "copyparty-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "deal-scout",
      "claim": "deal-scout-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "dozzle",
      "claim": "dozzle-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "frigate",
      "claim": "frigate-config",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "frigate",
      "claim": "frigate-media",
      "storage_class": "frigate-smb",
      "requested_storage": "1Ti",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "frigate",
      "claim": "mosquitto-storage-pvc",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "geocoder",
      "claim": "geocoder-downloads",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "detached",
      "robustness": "unknown"
    },
    {
      "namespace": "geocoder",
      "claim": "geocoder-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "100Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "gitea-actions",
      "claim": "docker-storage-act-runner-0",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "gitea-actions",
      "claim": "docker-storage-act-runner-1",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "gitea",
      "claim": "gitea-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "2",
      "replica_zones": "house,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "gitea",
      "claim": "gitea-shared-storage",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "hindsight",
      "claim": "hindsight-db-pvc",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "home-assistant",
      "claim": "config",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "2",
      "replica_zones": "house,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "homepage-dashboard",
      "claim": "config",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "imagery",
      "claim": "imagery-tiles",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "immich",
      "claim": "immich-ml-cache",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "immich",
      "claim": "immich-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "2",
      "replica_zones": "house,hp-elite",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "immich",
      "claim": "library-nas",
      "storage_class": "truenas-nfs",
      "requested_storage": "200Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "csi.truenas.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "immich",
      "claim": "nfs-photos",
      "storage_class": "",
      "requested_storage": "2Ti",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "nfs.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "intercept",
      "claim": "intercept-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "intercept",
      "claim": "intercept-postgres-recovered",
      "storage_class": "longhorn-wired-ha",
      "requested_storage": "20Gi",
      "replicas": "2",
      "replica_zones": "hp-elite,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "jellyfin",
      "claim": "config",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "jellyfin",
      "claim": "jellyfin-media",
      "storage_class": "",
      "requested_storage": "1Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "karakeep",
      "claim": "data-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "karakeep",
      "claim": "meilisearch-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "kiwix",
      "claim": "kiwix-data",
      "storage_class": "kiwix-smb",
      "requested_storage": "100Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "langfuse",
      "claim": "langfuse-clickhouse-data",
      "storage_class": "longhorn",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "langfuse",
      "claim": "langfuse-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "langfuse",
      "claim": "langfuse-redis-data",
      "storage_class": "longhorn",
      "requested_storage": "8Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "loki-stack",
      "claim": "data-loki-backend-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "loki-stack",
      "claim": "data-loki-write-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "nginx-example",
      "claim": "storage",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "detached",
      "robustness": "unknown"
    },
    {
      "namespace": "open-webui",
      "claim": "storage-recovered",
      "storage_class": "longhorn-wired-ha",
      "requested_storage": "10Gi",
      "replicas": "2",
      "replica_zones": "hp-elite,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "2",
      "replica_zones": "house,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "media",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "2",
      "replica_zones": "house,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "paperless-consume-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "paperless-export-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "paperless-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "2",
      "replica_zones": "house,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "paseo",
      "claim": "paseo-home",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "paseo",
      "claim": "paseo-workspace",
      "storage_class": "longhorn",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "perplexica",
      "claim": "perplexica-data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "posthog",
      "claim": "clickhouse-data-clickhouse-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "60Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "posthog",
      "claim": "postgres-data",
      "storage_class": "longhorn-flash",
      "requested_storage": "16Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "posthog",
      "claim": "redis7-data",
      "storage_class": "longhorn-flash",
      "requested_storage": "4Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "posthog",
      "claim": "redpanda-data-kafka-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "32Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "presenton",
      "claim": "presenton-data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "product-bench",
      "claim": "postgres-data",
      "storage_class": "longhorn-flash",
      "requested_storage": "40Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "project-nomad",
      "claim": "embeddings-model-cache",
      "storage_class": "longhorn",
      "requested_storage": "2Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "project-nomad",
      "claim": "flatnotes-data",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "project-nomad",
      "claim": "mysql-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "project-nomad",
      "claim": "nomad-storage-nas",
      "storage_class": "truenas-nfs",
      "requested_storage": "200Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "csi.truenas.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "project-nomad",
      "claim": "protomaps-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "project-nomad",
      "claim": "qdrant-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "prometheus-stack",
      "claim": "alertmanager-kube-prometheus-stack-alertmanager-db-alertmanager-kube-prometheus-stack-alertmanager-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "prometheus-stack",
      "claim": "kube-prometheus-stack-grafana",
      "storage_class": "longhorn-flash",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "prometheus-stack",
      "claim": "prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "radar-ng",
      "claim": "grids",
      "storage_class": "longhorn-flash",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "radar-ng",
      "claim": "openmeteo-data",
      "storage_class": "longhorn-flash",
      "requested_storage": "60Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "radar-ng",
      "claim": "pmtiles",
      "storage_class": "longhorn-flash",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "radar-ng",
      "claim": "state",
      "storage_class": "longhorn-flash",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "radar-ng",
      "claim": "tiles",
      "storage_class": "longhorn-flash",
      "requested_storage": "100Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "redis-instance",
      "claim": "redis-master-0",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "restore-canary",
      "claim": "restore-canary-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "searxng",
      "claim": "redis-data",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "surfsense",
      "claim": "surfsense-object-store-v2",
      "storage_class": "longhorn-wired-ha",
      "requested_storage": "20Gi",
      "replicas": "2",
      "replica_zones": "hp-elite,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "surfsense",
      "claim": "surfsense-postgres-data-v2",
      "storage_class": "longhorn-wired-ha",
      "requested_storage": "20Gi",
      "replicas": "2",
      "replica_zones": "hp-elite,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "surfsense",
      "claim": "surfsense-redis-data-v2",
      "storage_class": "longhorn",
      "requested_storage": "2Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "swarmui",
      "claim": "swarmui-comfyui-models",
      "storage_class": "nfs-comfyui-10g",
      "requested_storage": "250Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "nfs.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "swarmui",
      "claim": "swarmui-data",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "detached",
      "robustness": "unknown"
    },
    {
      "namespace": "swarmui",
      "claim": "swarmui-dlbackend",
      "storage_class": "longhorn",
      "requested_storage": "40Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "detached",
      "robustness": "unknown"
    },
    {
      "namespace": "swarmui",
      "claim": "swarmui-output",
      "storage_class": "longhorn",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "detached",
      "robustness": "unknown"
    },
    {
      "namespace": "temporal",
      "claim": "temporal-postgres-data",
      "storage_class": "longhorn-wired-ha",
      "requested_storage": "10Gi",
      "replicas": "2",
      "replica_zones": "hp-elite,hp-sff",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "tubesync",
      "claim": "config-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "tubesync",
      "claim": "media-pvc",
      "storage_class": "tubearchivist-smb",
      "requested_storage": "1Ti",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "versatiles",
      "claim": "map-data-smb",
      "storage_class": "",
      "requested_storage": "150Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "vllm",
      "claim": "ai-model-cache-vllm",
      "storage_class": "ai-model-cache-local",
      "requested_storage": "60Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "vllm",
      "claim": "vllm-compile-cache",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "vllm",
      "claim": "vllm-download-models",
      "storage_class": "",
      "requested_storage": "1Ti",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "nfs.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "vllm",
      "claim": "vllm-models-pvc",
      "storage_class": "",
      "requested_storage": "1Ti",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "nfs.csi.k8s.io",
      "phase": "Bound",
      "volume_state": null,
      "robustness": null
    },
    {
      "namespace": "worldmonitor",
      "claim": "worldmonitor-redis-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "attached",
      "robustness": "healthy"
    },
    {
      "namespace": "wyze-bridge",
      "claim": "wyze-web-session",
      "storage_class": "longhorn",
      "requested_storage": "64Mi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io",
      "phase": "Bound",
      "volume_state": "detached",
      "robustness": "unknown"
    }
  ],
  "notes": [
    "Read-only SSH, Kubernetes and authenticated Talos API collection on 2026-10-15. Host configuration, guest discovery and controller status are separate observations.",
    "Physical disks exclude NAS zvol devices, guest disks and virtual RAID devices. Dell T-FORCE was not visible and is excluded from the observed count.",
    "September performance datasets retain their original dates. No benchmarks, SMART self-tests, restore tests or infrastructure changes were performed.",
    "Longhorn and guest mounts do not prove underlying hardware availability. Dell dell-ssd-vmstore was inactive despite the guest mount."
  ],
  "network": {
    "source": "Historical network design retained; host addresses and Talos node IPs rechecked 2026-10-15. Router, bridge, DNS and HTTP paths were not tested.",
    "addresses": [
      {
        "name": "Firewalla router",
        "ip": "192.168.10.1",
        "role": "Default LAN route"
      },
      {
        "name": "ASUS RT-AX86U",
        "ip": "192.168.10.70",
        "role": "Shed media bridge; management address"
      },
      {
        "name": "Wyze Bridge",
        "ip": "192.168.10.46",
        "role": "Recorded camera stream endpoint"
      },
      {
        "name": "External gateway",
        "ip": "192.168.10.49",
        "role": "gateway-external"
      },
      {
        "name": "Private split-DNS gateway",
        "ip": "192.168.10.52",
        "role": "gateway-internal-technitium"
      },
      {
        "name": "Cilium address pool",
        "ip": "192.168.10.32/27",
        "role": "First and last addresses excluded by policy"
      }
    ],
    "paths": [
      {
        "id": "private",
        "name": "Private app",
        "steps": [
          {
            "title": "Your browser",
            "text": "A private app hostname"
          },
          {
            "title": "Technitium DNS",
            "text": "192.168.10.15 answers the lookup"
          },
          {
            "title": "Internal gateway",
            "text": "192.168.10.52 for split-DNS routes"
          },
          {
            "title": "App service",
            "text": "Cilium sends the request to its pods"
          }
        ],
        "note": "This path is for routes enrolled in the Technitium split-DNS gateway. The separate .50 internal gateway also remains declared. DNS resolves the name; it does not proxy the HTTP request."
      },
      {
        "id": "public",
        "name": "Public app",
        "steps": [
          {
            "title": "Your browser",
            "text": "A public app hostname"
          },
          {
            "title": "Cloudflare",
            "text": "Public DNS and tunnel entry"
          },
          {
            "title": "cloudflared pods",
            "text": "Tunnel connects into the cluster"
          },
          {
            "title": "External gateway",
            "text": "gateway-external \u2192 app service"
          }
        ],
        "note": "Cloudflare tunnels are in use; Cloudflare Access is not. The gateway has configured VIP .49, while tunnel origin routing uses the configured cluster service."
      },
      {
        "id": "shed",
        "name": "Shed connection",
        "steps": [
          {
            "title": "House Talos node",
            "text": "Cross-node pod traffic"
          },
          {
            "title": "Cilium VXLAN",
            "text": "Carries traffic between node IPs"
          },
          {
            "title": "Wi-Fi media bridge",
            "text": "ASUS RT-AX86U; Ethernet at the shed"
          },
          {
            "title": "Shed Talos VM",
            "text": "192.168.10.128 at the October 15 audit"
          }
        ],
        "note": "Talos sees a wired interface. The radio hop still matters, so this host has a Wi-Fi scheduling taint and no scheduled Longhorn replicas."
      }
    ]
  }
};
