window.HOMELAB_INVENTORY = {
  "date": "2026-09-05",
  "assembledAt": "2026-09-05T21:34:13.664744+00:00",
  "sourceCommit": "cbda78a0",
  "runtimeVersionsCheckedAt": "2026-09-06T01:48:49.025993+00:00",
  "hosts": [
    {
      "id": "sff",
      "name": "HP SFF",
      "model": "ProDesk 600 G4 SFF",
      "cpu": "Intel i5-8500 \u00b7 6 cores",
      "ram": "64 GB",
      "zone": "hp-sff",
      "link": "Wired \u00b7 2.5 GbE",
      "role": "Control plane + everyday apps",
      "suggested": "Everyday apps + protected state",
      "summary": "The machine keeping Kubernetes in charge. Its two VMs still share one power button.",
      "advice": "Improve the control-plane disk first. Keep noisy writes on the other disk.",
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
          "role": "Control-plane disk",
          "path": "hp-sff-cp \u2192 VM 101 scsi0, 100 GiB",
          "note": "Etcd WAL fsync p99 ~49 ms; ~831 GiB VG free. The whole I/O path needs qualification."
        },
        {
          "device": "sdb",
          "model": "PNY CS900 1TB SSD",
          "bytes": 1000204886016,
          "interface": "sata",
          "role": "Proxmox + worker disks",
          "path": "pve \u2192 VM 100: 128 GiB boot + 690 GiB data",
          "note": "SMART overall passed in the audit; this is not a lifetime guarantee."
        }
      ],
      "vms": [
        {
          "id": "100",
          "name": "talos-prod-cluster-v2-hp-sff-workers-rldgrj",
          "ramMiB": 40960,
          "vcpus": 6,
          "state": "running",
          "ip": "192.168.10.150",
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
          "talos": "Talos (v1.14.0)",
          "kubernetes": "v1.37.0",
          "namespaces": [
            {
              "name": "1passwordconnect",
              "pods": 1
            },
            {
              "name": "argocd",
              "pods": 2
            },
            {
              "name": "cloudflared",
              "pods": 1
            },
            {
              "name": "coroot",
              "pods": 8
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
              "name": "fizzy",
              "pods": 1
            },
            {
              "name": "kafka",
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
              "pods": 3
            },
            {
              "name": "litellm",
              "pods": 1
            },
            {
              "name": "loki-stack",
              "pods": 2
            },
            {
              "name": "longhorn-system",
              "pods": 6
            },
            {
              "name": "n8n",
              "pods": 1
            },
            {
              "name": "news-reader",
              "pods": 1
            },
            {
              "name": "node-feature-discovery",
              "pods": 1
            },
            {
              "name": "open-webui",
              "pods": 2
            },
            {
              "name": "opentelemetry",
              "pods": 1
            },
            {
              "name": "paperless-ngx",
              "pods": 2
            },
            {
              "name": "project-nomad",
              "pods": 3
            },
            {
              "name": "prometheus-stack",
              "pods": 3
            },
            {
              "name": "restore-canary",
              "pods": 1
            },
            {
              "name": "temporal",
              "pods": 1
            },
            {
              "name": "trivy-operator",
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
              "name": "vertical-pod-autoscaler",
              "pods": 1
            },
            {
              "name": "worldmonitor",
              "pods": 2
            }
          ]
        },
        {
          "id": "101",
          "name": "talos-prod-cluster-v2-control-planes-djzhc6",
          "ramMiB": 12288,
          "vcpus": 4,
          "state": "running",
          "ip": "192.168.10.79",
          "disks": [
            {
              "slot": "scsi0",
              "backing": "hp-sff-cp-vmstore:vm-101-disk-0",
              "size": "100 GiB"
            }
          ],
          "talos": "Talos (v1.14.0)",
          "kubernetes": "v1.37.0",
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
              "pods": 7
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
          ]
        }
      ],
      "ramBytes": 67223908352
    },
    {
      "id": "elite",
      "name": "HP Elite Mini",
      "model": "Elite Mini 600 G9",
      "cpu": "Intel i5-13500T \u00b7 20 threads",
      "ram": "32 GB",
      "zone": "hp-elite",
      "link": "Wired",
      "role": "Everyday apps + Zigbee",
      "suggested": "Everyday apps + protected state",
      "summary": "The other sensible home for everyday services. The Zigbee coordinator lives here too.",
      "advice": "Plan the data SSD replacement. Check the SATA carrier/cable before buying a 2.5-inch drive.",
      "loss": "Pods here stop, along with the attached Zigbee coordinator. Single-copy volumes on this host have no surviving live copy.",
      "power": 33,
      "ip": "192.168.10.22",
      "kind": "Proxmox",
      "disks": [
        {
          "device": "nvme1n1",
          "model": "INTEL SSDPEKNW512G8",
          "bytes": 512110190592,
          "interface": "nvme",
          "role": "Longhorn data",
          "path": "hp-elite-vmstore \u2192 VM 100 scsi1, 440 GiB",
          "note": "74% endurance used; 56,418 hours; 539 unsafe shutdowns; 0 media errors."
        },
        {
          "device": "nvme0n1",
          "model": "WDC PC SN530 SDBPMPZ-256G-1101",
          "bytes": 256060514304,
          "interface": "nvme",
          "role": "Proxmox + Talos boot",
          "path": "local-lvm \u2192 VM 100 scsi0, 128 GiB",
          "note": "SMART overall passed in the audit; this is not a lifetime guarantee."
        }
      ],
      "vms": [
        {
          "id": "100",
          "name": "talos-prod-cluster-v2-hp-elite-workers-rgkw5s",
          "ramMiB": 24576,
          "vcpus": 16,
          "state": "running",
          "ip": "192.168.10.172",
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
          "talos": "Talos (v1.14.0)",
          "kubernetes": "v1.37.0",
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
              "name": "deal-scout",
              "pods": 1
            },
            {
              "name": "dozzle",
              "pods": 1
            },
            {
              "name": "gitea",
              "pods": 2
            },
            {
              "name": "home-assistant",
              "pods": 1
            },
            {
              "name": "homepage-dashboard",
              "pods": 1
            },
            {
              "name": "intercept",
              "pods": 1
            },
            {
              "name": "keep",
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
              "pods": 9
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
              "name": "temporal",
              "pods": 1
            },
            {
              "name": "truenas-csi",
              "pods": 1
            }
          ]
        }
      ],
      "ramBytes": 32843362304
    },
    {
      "id": "gpu",
      "name": "Threadripper",
      "model": "X399 \u00b7 Ryzen Threadripper 2950X",
      "cpu": "AMD 2950X \u00b7 16 cores / 32 threads",
      "ram": "128 GB",
      "zone": "house",
      "link": "Wired",
      "role": "GPU + heavy jobs + app storage",
      "suggested": "GPU + selected heavy jobs",
      "summary": "One RTX 3090, lots of RAM, and the enterprise SSD mirror. Ordinary apps still depend on this box.",
      "advice": "Keep the HPE mirror. Gradually move ordinary service dependencies to the HPs; fix fresh boot-disk selection before rebuilding.",
      "loss": "The GPU stops, as expected. The flash mirror and many single-copy app volumes also disappear with this host; mirroring disks inside it cannot prevent that.",
      "power": 182,
      "ip": "192.168.10.14",
      "kind": "Proxmox",
      "disks": [
        {
          "device": "sda",
          "model": "PNY CS900 1TB SSD",
          "bytes": 1000204886016,
          "interface": "sata",
          "role": "Proxmox boot",
          "path": "Host filesystem and local capacity",
          "note": "SMART overall passed in the audit; this is not a lifetime guarantee."
        },
        {
          "device": "sdb",
          "model": "MK000480GWCEV",
          "bytes": 480103981056,
          "interface": "sata",
          "role": "HPE mirror member",
          "path": "md0 \u2192 ssd-ent \u2192 GPU VM flash + extra disk",
          "note": "HPE MK000480GWCEV, PLP; member of the same RAID1 mirror. Keep both members in place."
        },
        {
          "device": "sdc",
          "model": "MK000480GWCEV",
          "bytes": 480103981056,
          "interface": "sata",
          "role": "HPE mirror member",
          "path": "md0 \u2192 ssd-ent \u2192 GPU VM flash + extra disk",
          "note": "HPE MK000480GWCEV, PLP; member of the same RAID1 mirror. Keep both members in place."
        },
        {
          "device": "nvme1n1",
          "model": "EDILOCA EN605 512GB",
          "bytes": 512110190592,
          "interface": "nvme",
          "role": "Local AI cache",
          "path": "nvme1-vmstore \u2192 VM 103 scsi1, 450 GiB",
          "note": "SMART overall passed in the audit; this is not a lifetime guarantee."
        },
        {
          "device": "nvme0n1",
          "model": "EDILOCA EN605 512GB",
          "bytes": 512110190592,
          "interface": "nvme",
          "role": "Talos boot + Longhorn",
          "path": "nvme0-vmstore \u2192 VM 103 scsi0, 450 GiB",
          "note": "SMART overall passed in the audit; this is not a lifetime guarantee."
        }
      ],
      "vms": [
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
          "namespaces": []
        },
        {
          "id": "103",
          "name": "talos-prod-cluster-v2-gpu-workers-7ct4kq",
          "ramMiB": 102400,
          "vcpus": 30,
          "state": "running",
          "ip": "192.168.10.80",
          "disks": [
            {
              "slot": "scsi0",
              "backing": "nvme0-vmstore:vm-103-disk-1",
              "size": "450 GiB"
            },
            {
              "slot": "scsi1",
              "backing": "nvme1-vmstore:vm-103-disk-0",
              "size": "450 GiB"
            },
            {
              "slot": "scsi2",
              "backing": "ssd-ent:vm-103-disk-0",
              "size": "300 GiB"
            },
            {
              "slot": "scsi3",
              "backing": "ssd-ent:vm-103-disk-1",
              "size": "120 GiB"
            }
          ],
          "talos": "Talos (v1.14.0)",
          "kubernetes": "v1.37.0",
          "namespaces": [
            {
              "name": "1passwordconnect",
              "pods": 1
            },
            {
              "name": "argocd",
              "pods": 1
            },
            {
              "name": "cobalt",
              "pods": 1
            },
            {
              "name": "convertx",
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
              "name": "excalidraw",
              "pods": 1
            },
            {
              "name": "external-dns",
              "pods": 1
            },
            {
              "name": "external-secrets",
              "pods": 1
            },
            {
              "name": "frigate",
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
              "pods": 4
            },
            {
              "name": "karakeep",
              "pods": 3
            },
            {
              "name": "keep",
              "pods": 3
            },
            {
              "name": "kube-system",
              "pods": 7
            },
            {
              "name": "llama-cpp",
              "pods": 1
            },
            {
              "name": "loki-stack",
              "pods": 3
            },
            {
              "name": "longhorn-system",
              "pods": 7
            },
            {
              "name": "mailpit",
              "pods": 1
            },
            {
              "name": "metrics-server",
              "pods": 1
            },
            {
              "name": "monitoring",
              "pods": 1
            },
            {
              "name": "news-reader",
              "pods": 1
            },
            {
              "name": "nginx-example",
              "pods": 2
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
              "pods": 17
            },
            {
              "name": "presenton",
              "pods": 1
            },
            {
              "name": "project-nomad",
              "pods": 4
            },
            {
              "name": "prometheus-stack",
              "pods": 3
            },
            {
              "name": "radar-ng",
              "pods": 8
            },
            {
              "name": "redis-instance",
              "pods": 1
            },
            {
              "name": "redlib",
              "pods": 1
            },
            {
              "name": "searxng",
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
              "pods": 4
            },
            {
              "name": "trivy-operator",
              "pods": 1
            },
            {
              "name": "truenas-csi",
              "pods": 2
            },
            {
              "name": "tubesync",
              "pods": 1
            },
            {
              "name": "vert",
              "pods": 1
            },
            {
              "name": "vertical-pod-autoscaler",
              "pods": 1
            },
            {
              "name": "worldmonitor",
              "pods": 1
            }
          ]
        }
      ],
      "ramBytes": 134941966336
    },
    {
      "id": "dell",
      "name": "Dell OptiPlex",
      "model": "OptiPlex 7060 \u00b7 exposed motherboard",
      "cpu": "Intel i5-8500 \u00b7 6 cores",
      "ram": "40 GB",
      "zone": "dell",
      "link": "Wired \u00b7 2.5 GbE",
      "role": "Temporary worker + live storage",
      "suggested": "Restartable jobs and experiments",
      "summary": "Useful extra capacity, but the acrylic-board build is intentionally temporary.",
      "advice": "Move required replicas away before treating it as expendable. Historical CRC errors do not prove an active disk failure.",
      "loss": "Work here stops. The owner accepts temporary hardware, but its current single-copy volumes are still real dependencies.",
      "power": null,
      "ip": "192.168.10.16",
      "kind": "Proxmox",
      "disks": [
        {
          "device": "sda",
          "model": "Samsung SSD 850 EVO 500GB",
          "bytes": 500107862016,
          "interface": "sata",
          "role": "Longhorn data",
          "path": "dell-ssd-vmstore \u2192 VM 100 scsi1, 400 GiB",
          "note": "~74,097 hours; 8,162 historical CRC errors; no reported reallocated/uncorrectable errors."
        },
        {
          "device": "sdb",
          "model": "APPLE SSD SM0256G",
          "bytes": 251000193024,
          "interface": "sata",
          "role": "Adapted Apple boot SSD",
          "path": "local-lvm \u2192 VM 100 scsi0, 128 GiB",
          "note": "SMART overall passed in the audit; this is not a lifetime guarantee."
        }
      ],
      "vms": [
        {
          "id": "100",
          "name": "talos-prod-cluster-v2-dell-workers-nkq6qd",
          "ramMiB": 30720,
          "vcpus": 6,
          "state": "running",
          "ip": "192.168.10.177",
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
            }
          ],
          "talos": "Talos (v1.14.0)",
          "kubernetes": "v1.37.0",
          "namespaces": [
            {
              "name": "1passwordconnect",
              "pods": 1
            },
            {
              "name": "argocd",
              "pods": 2
            },
            {
              "name": "cloudflared",
              "pods": 1
            },
            {
              "name": "cobalt",
              "pods": 1
            },
            {
              "name": "coroot",
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
              "pods": 1
            },
            {
              "name": "external-dns",
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
              "name": "hindsight",
              "pods": 1
            },
            {
              "name": "it-tools",
              "pods": 1
            },
            {
              "name": "jellyfin",
              "pods": 1
            },
            {
              "name": "keda",
              "pods": 2
            },
            {
              "name": "kopiur-system",
              "pods": 2
            },
            {
              "name": "kube-system",
              "pods": 2
            },
            {
              "name": "loki-stack",
              "pods": 4
            },
            {
              "name": "longhorn-system",
              "pods": 8
            },
            {
              "name": "node-feature-discovery",
              "pods": 2
            },
            {
              "name": "open-webui",
              "pods": 1
            },
            {
              "name": "opentelemetry",
              "pods": 3
            },
            {
              "name": "paperless-ngx",
              "pods": 1
            },
            {
              "name": "project-nomad",
              "pods": 2
            },
            {
              "name": "prometheus-stack",
              "pods": 3
            },
            {
              "name": "redis",
              "pods": 1
            },
            {
              "name": "stirling-pdf",
              "pods": 1
            },
            {
              "name": "surfsense",
              "pods": 5
            },
            {
              "name": "temporal",
              "pods": 1
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
              "name": "worldmonitor",
              "pods": 1
            }
          ]
        }
      ],
      "ramBytes": 41846128640
    },
    {
      "id": "shed",
      "name": "Shed HP Mini",
      "model": "ProDesk 600 G4 DM",
      "cpu": "Intel i5-8500T \u00b7 6 cores",
      "ram": "32 GB",
      "zone": "shed",
      "link": "Ethernet \u2192 ASUS Wi-Fi media bridge",
      "role": "Radio / USB edge worker",
      "suggested": "Attached devices + edge jobs",
      "summary": "Talos sees Ethernet; the trip back to the house crosses Wi-Fi.",
      "advice": "Keep it out of storage replication and quorum. Its Longhorn disks are already unschedulable.",
      "loss": "Attached radio/USB jobs stop. No Longhorn replicas were scheduled here in the audit.",
      "power": 23,
      "ip": "192.168.10.20",
      "kind": "Proxmox",
      "disks": [
        {
          "device": "sda",
          "model": "PNY CS900 1TB SSD",
          "bytes": 1000204886016,
          "interface": "sata",
          "role": "Data disk; no Longhorn replicas",
          "path": "hp-ssd-vmstore \u2192 VM 100 scsi1, 850 GiB",
          "note": "SMART overall passed in the audit; this is not a lifetime guarantee."
        },
        {
          "device": "nvme0n1",
          "model": "SK hynix BC501 HFM256GDJTNG-8310A",
          "bytes": 256060514304,
          "interface": "nvme",
          "role": "Proxmox + Talos boot",
          "path": "local-lvm \u2192 VM 100 scsi0, 128 GiB",
          "note": "SMART overall passed in the audit; this is not a lifetime guarantee."
        }
      ],
      "vms": [
        {
          "id": "100",
          "name": "talos-prod-cluster-v2-hp-micro-workers-7wwjmh",
          "ramMiB": 25000,
          "vcpus": 4,
          "state": "running",
          "ip": "192.168.10.156",
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
          "talos": "Talos (v1.14.0)",
          "kubernetes": "v1.37.0",
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
          ]
        }
      ],
      "ramBytes": 33419948032
    },
    {
      "id": "pi",
      "name": "Omni / DNS Pi",
      "model": "Raspberry Pi 5",
      "cpu": "Broadcom BCM2712 \u00b7 4 cores",
      "ram": "8 GB",
      "ramBytes": 8589934592,
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
          "device": "NVMe (device name not retained)",
          "model": "Patriot P300",
          "bytes": 256000000000,
          "interface": "NVMe",
          "role": "Pi boot + services",
          "path": "Pi filesystem \u2192 Omni + Technitium",
          "note": "256 GB nominal; about 210 GB filesystem free at collection. This Pi is not booting from an SD card."
        }
      ],
      "vms": []
    },
    {
      "id": "nas",
      "name": "TrueNAS",
      "model": "HPE DL360 \u00b7 one Xeon",
      "cpu": "Intel Xeon E5-2680 v4 \u00b7 14 cores / 28 threads",
      "ram": "384 GB ECC",
      "ramBytes": 405444912742.4,
      "zone": null,
      "link": "10 GbE",
      "ip": "192.168.10.133",
      "kind": "NAS",
      "role": "Shared files + RustFS backups",
      "suggested": "Keep the stable NAS and its RAM",
      "summary": "The big file cupboard, the backup destination, and 340.5 GiB of useful ZFS cache.",
      "advice": "Leave the RAM alone. Use the NAS for shared/bulk data; choose durability before moving database writes here.",
      "loss": "NAS-backed workloads can stall, and backup/restore jobs cannot reach RustFS. This outage trade-off is accepted; it is not permission to restore empty data.",
      "power": 114,
      "extraPower": "Separate drive PSU: ~43 W",
      "disks": [
        {
          "device": "sda",
          "model": "Samsung SSD 860 EVO 1TB",
          "bytes": 1000204886016,
          "interface": "Host reports SAS",
          "role": "ai-pool",
          "path": "sda \u2192 ai-pool",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        },
        {
          "device": "sdb",
          "model": "T-FORCE 512GB",
          "bytes": 512110190592,
          "interface": "Host reports SAS",
          "role": "boot-pool",
          "path": "sdb \u2192 boot-pool",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        },
        {
          "device": "sdc",
          "model": "MK000480GWCEV",
          "bytes": 480103981056,
          "interface": "Host reports SAS",
          "role": "boot-pool",
          "path": "sdc \u2192 boot-pool",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        },
        {
          "device": "sdd",
          "model": "P3-512",
          "bytes": 512110190592,
          "interface": "Host reports SAS",
          "role": "ai-pool",
          "path": "sdd \u2192 ai-pool",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        },
        {
          "device": "sde",
          "model": "HP SSD S700 500GB",
          "bytes": 500107862016,
          "interface": "Host reports SAS",
          "role": "ai-pool",
          "path": "sde \u2192 ai-pool",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        },
        {
          "device": "sdf",
          "model": "ST10000NM0096",
          "bytes": 10000831348736,
          "interface": "Host reports SAS",
          "role": "Backup10T",
          "path": "sdf \u2192 Backup10T",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        },
        {
          "device": "sdg",
          "model": "HUH721010AL4200",
          "bytes": 10000831348736,
          "interface": "Host reports SAS",
          "role": "BigTank mirror-0",
          "path": "sdg \u2192 BigTank mirror-0",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        },
        {
          "device": "sdh",
          "model": "HUH721010AL4200",
          "bytes": 10000831348736,
          "interface": "Host reports SAS",
          "role": "BigTank mirror-1",
          "path": "sdh \u2192 BigTank mirror-1",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        },
        {
          "device": "sdi",
          "model": "HUH721010AL4200",
          "bytes": 10000831348736,
          "interface": "Host reports SAS",
          "role": "BigTank mirror-0",
          "path": "sdi \u2192 BigTank mirror-0",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        },
        {
          "device": "sdj",
          "model": "HUH721010AL4200",
          "bytes": 10000831348736,
          "interface": "Host reports SAS",
          "role": "BigTank mirror-1",
          "path": "sdj \u2192 BigTank mirror-1",
          "note": "Pool membership verified with zpool status. Controller transport does not establish the drive connector type."
        }
      ],
      "vms": [],
      "memory": [
        {
          "name": "ZFS cache",
          "gib": 340.5
        },
        {
          "name": "Services",
          "gib": 13.6
        },
        {
          "name": "Free",
          "gib": 23.5
        }
      ],
      "pools": [
        {
          "name": "BigTank",
          "size": "18.2 TiB",
          "used": 55,
          "layout": "Two mirrors \u00b7 four 10 TB disks",
          "note": "Main files and RustFS. One disk can fail in each mirror; losing both members of the same mirror loses the pool."
        },
        {
          "name": "Backup10T",
          "size": "9.08 TiB",
          "used": 68,
          "layout": "One 10 TB disk",
          "note": "A separate pool on the same NAS, with no member-disk redundancy."
        },
        {
          "name": "ai-pool",
          "size": "1.82 TiB",
          "used": 74,
          "layout": "Three SSDs striped",
          "note": "No mirror/parity. Any member loss threatens the whole pool."
        },
        {
          "name": "boot-pool",
          "size": "222 GiB",
          "used": 58,
          "layout": "T-FORCE + HPE mirror",
          "note": "The HPE is a boot mirror member, not a spare. Pool size is not the raw sum of member capacities."
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
      "csi_driver": "smb.csi.k8s.io"
    },
    {
      "namespace": "consumers-energy-sync",
      "claim": "consumers-energy-sync-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "copyparty",
      "claim": "copyparty-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "coroot",
      "claim": "data-coroot-clickhouse-keeper-0",
      "storage_class": "longhorn",
      "requested_storage": "2Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "coroot",
      "claim": "data-coroot-clickhouse-keeper-1",
      "storage_class": "longhorn",
      "requested_storage": "2Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "coroot",
      "claim": "data-coroot-clickhouse-keeper-2",
      "storage_class": "longhorn",
      "requested_storage": "2Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "coroot",
      "claim": "data-coroot-clickhouse-shard-0-0",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "coroot",
      "claim": "data-coroot-coroot-0",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "coroot",
      "claim": "data-coroot-prometheus",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "deal-scout",
      "claim": "deal-scout-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "dozzle",
      "claim": "dozzle-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "fizzy",
      "claim": "data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "frigate",
      "claim": "frigate-config",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "frigate",
      "claim": "frigate-media",
      "storage_class": "frigate-smb",
      "requested_storage": "1Ti",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io"
    },
    {
      "namespace": "frigate",
      "claim": "mosquitto-storage-pvc",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "gitea-actions",
      "claim": "act-runner-docker-cache",
      "storage_class": "longhorn",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "dell",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "gitea",
      "claim": "gitea-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "gitea",
      "claim": "gitea-shared-storage",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "hindsight",
      "claim": "hindsight-db-pvc",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "dell",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "home-assistant",
      "claim": "config",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "homepage-dashboard",
      "claim": "config",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "immich",
      "claim": "immich-ml-cache",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "immich",
      "claim": "immich-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "immich",
      "claim": "library",
      "storage_class": "longhorn",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "immich",
      "claim": "nfs-photos",
      "storage_class": "",
      "requested_storage": "2Ti",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "nfs.csi.k8s.io"
    },
    {
      "namespace": "intercept",
      "claim": "intercept-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "intercept",
      "claim": "intercept-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "jellyfin",
      "claim": "config",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "dell",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "jellyfin",
      "claim": "jellyfin-media",
      "storage_class": "",
      "requested_storage": "1Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io"
    },
    {
      "namespace": "karakeep",
      "claim": "data-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "karakeep",
      "claim": "meilisearch-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "keep",
      "claim": "keep-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "kiwix",
      "claim": "kiwix-data",
      "storage_class": "kiwix-smb",
      "requested_storage": "100Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io"
    },
    {
      "namespace": "kube-system",
      "claim": "registry",
      "storage_class": "longhorn",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "llama-cpp",
      "claim": "ai-model-cache",
      "storage_class": "ai-model-cache-local",
      "requested_storage": "450Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": ""
    },
    {
      "namespace": "llama-cpp",
      "claim": "llama-cpp-models-pvc",
      "storage_class": "nfs-llama-cpp-10g",
      "requested_storage": "150Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "nfs.csi.k8s.io"
    },
    {
      "namespace": "loki-stack",
      "claim": "data-loki-backend-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "loki-stack",
      "claim": "data-loki-write-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "n8n",
      "claim": "data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "nginx-example",
      "claim": "storage",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "ninfer",
      "claim": "ninfer-models-pvc",
      "storage_class": "",
      "requested_storage": "150Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "nfs.csi.k8s.io"
    },
    {
      "namespace": "open-webui",
      "claim": "storage",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "media",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "paperless-consume-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "paperless-export-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "paperless-ngx",
      "claim": "paperless-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "perplexica",
      "claim": "perplexica-data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "posthog",
      "claim": "clickhouse-data-clickhouse-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "40Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "posthog",
      "claim": "postgres-data",
      "storage_class": "longhorn-flash",
      "requested_storage": "8Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "posthog",
      "claim": "redis7-data",
      "storage_class": "longhorn-flash",
      "requested_storage": "4Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "posthog",
      "claim": "redpanda-data-kafka-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "8Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "presenton",
      "claim": "presenton-data",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "project-nomad",
      "claim": "embeddings-model-cache",
      "storage_class": "longhorn",
      "requested_storage": "2Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "project-nomad",
      "claim": "flatnotes-data",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "dell",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "project-nomad",
      "claim": "mysql-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "project-nomad",
      "claim": "nomad-storage",
      "storage_class": "longhorn",
      "requested_storage": "120Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "project-nomad",
      "claim": "protomaps-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "dell",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "project-nomad",
      "claim": "qdrant-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "project-zomboid",
      "claim": "zomboid-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "project-zomboid",
      "claim": "zomboid-server-files",
      "storage_class": "longhorn",
      "requested_storage": "60Gi",
      "replicas": "1",
      "replica_zones": "dell",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "prometheus-stack",
      "claim": "alertmanager-kube-prometheus-stack-alertmanager-db-alertmanager-kube-prometheus-stack-alertmanager-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "prometheus-stack",
      "claim": "kube-prometheus-stack-grafana",
      "storage_class": "longhorn-flash",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "prometheus-stack",
      "claim": "prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0",
      "storage_class": "longhorn-flash",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "radar-ng",
      "claim": "grids",
      "storage_class": "longhorn-flash",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "radar-ng",
      "claim": "openmeteo-data",
      "storage_class": "longhorn",
      "requested_storage": "30Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "radar-ng",
      "claim": "pmtiles",
      "storage_class": "longhorn-flash",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "radar-ng",
      "claim": "state",
      "storage_class": "longhorn-flash",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "radar-ng",
      "claim": "tiles",
      "storage_class": "longhorn-flash",
      "requested_storage": "100Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "redis-instance",
      "claim": "redis-master-0",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "restore-canary",
      "claim": "restore-canary-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "searxng",
      "claim": "redis-data",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "surfsense",
      "claim": "surfsense-object-store",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "dell",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "surfsense",
      "claim": "surfsense-postgres-data",
      "storage_class": "longhorn",
      "requested_storage": "20Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "surfsense",
      "claim": "surfsense-redis-data",
      "storage_class": "longhorn",
      "requested_storage": "2Gi",
      "replicas": "1",
      "replica_zones": "dell",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "swarmui",
      "claim": "swarmui-comfyui-models",
      "storage_class": "nfs-comfyui-10g",
      "requested_storage": "250Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "nfs.csi.k8s.io"
    },
    {
      "namespace": "swarmui",
      "claim": "swarmui-data",
      "storage_class": "longhorn",
      "requested_storage": "5Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "swarmui",
      "claim": "swarmui-dlbackend",
      "storage_class": "longhorn",
      "requested_storage": "40Gi",
      "replicas": "1",
      "replica_zones": "dell",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "swarmui",
      "claim": "swarmui-output",
      "storage_class": "longhorn",
      "requested_storage": "50Gi",
      "replicas": "1",
      "replica_zones": "hp-sff",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "temporal",
      "claim": "temporal-postgres-data",
      "storage_class": "longhorn-wired-ha",
      "requested_storage": "10Gi",
      "replicas": "2",
      "replica_zones": "dell,hp-elite",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "tubesync",
      "claim": "config-pvc",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "tubesync",
      "claim": "media-pvc",
      "storage_class": "tubearchivist-smb",
      "requested_storage": "1Ti",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io"
    },
    {
      "namespace": "versatiles",
      "claim": "map-data-smb",
      "storage_class": "",
      "requested_storage": "150Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "smb.csi.k8s.io"
    },
    {
      "namespace": "vllm",
      "claim": "ai-model-cache-vllm",
      "storage_class": "ai-model-cache-local",
      "requested_storage": "60Gi",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": ""
    },
    {
      "namespace": "vllm",
      "claim": "vllm-compile-cache",
      "storage_class": "longhorn",
      "requested_storage": "10Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    },
    {
      "namespace": "vllm",
      "claim": "vllm-models-pvc",
      "storage_class": "",
      "requested_storage": "1Ti",
      "replicas": "",
      "replica_zones": "",
      "csi_driver": "nfs.csi.k8s.io"
    },
    {
      "namespace": "worldmonitor",
      "claim": "worldmonitor-redis-data",
      "storage_class": "longhorn",
      "requested_storage": "1Gi",
      "replicas": "1",
      "replica_zones": "house",
      "csi_driver": "driver.longhorn.io"
    }
  ],
  "notes": [
    "Host/disks from the September 5 SSH inventory; Kubernetes IPs and node versions were rechecked at runtimeVersionsCheckedAt after the upgrade. Pod namespace placement and claims remain from the earlier audit snapshot.",
    "Disk capacity uses decimal GB/TB; VM allocations and RAM use GiB/MiB. Capacity bars are not disk-use measurements.",
    "NAS pool percentages use the SSH snapshot; the later dashboard uses different usable-capacity accounting.",
    "Suggested roles and outage walkthroughs are explanations, not applied policy or measured recovery tests."
  ],
  "network": {
    "source": "Network topology documentation and committed Cilium/Gateway manifests; these endpoints were not re-probed during the Talos upgrade.",
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
        "name": "Internal gateway",
        "ip": "192.168.10.50",
        "role": "gateway-internal"
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
            "text": "192.168.10.156 at the audit"
          }
        ],
        "note": "Talos sees a wired interface. The radio hop still matters, so this host has a Wi-Fi scheduling taint and no scheduled Longhorn replicas."
      }
    ]
  }
};
