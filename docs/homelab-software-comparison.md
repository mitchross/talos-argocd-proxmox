# Homelab Software Comparison: This Cluster vs Techno Tim's 2026 Stack

A gap analysis comparing the applications deployed in this GitOps Kubernetes cluster against the software stack described in [Techno Tim's 2026 homelab software tour](https://youtu.be/efl2kuPNEpE).

## Key Architectural Differences

Before comparing individual services, the two stacks differ fundamentally in architecture:

| Aspect | This Cluster | Techno Tim |
|--------|-------------|------------|
| **Orchestration** | Kubernetes (Talos OS) | Docker Compose on TrueNAS + Kubernetes |
| **GitOps** | ArgoCD (self-managing) | Flux + Renovate + GitLab Runner |
| **CNI / Networking** | Cilium + Gateway API | Traefik reverse proxy |
| **DNS** | CoreDNS (in-cluster) | Pi-hole + Nebula Sync + Keepalived |
| **Storage** | Longhorn + NFS CSI + VolSync backups | ZFS on TrueNAS (local to apps) |
| **Secrets** | 1Password Connect + External Secrets | Not described |
| **AI Backend** | llama-cpp (Qwen3.5-35B) | Ollama |
| **Policy Engine** | Kyverno (auto backup/restore) | Not described |
| **Proxmox HA** | Service-layer HA (same philosophy) | Same - no Proxmox HA, app-level HA |

Tim splits home services (Docker on TrueNAS) from public services (Kubernetes). This cluster runs everything in Kubernetes with GitOps.

---

## Service-by-Service Comparison

### Dashboard & Links

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Homepage | Yes | **Yes** (`my-apps/media/homepage-dashboard/`) | Both use it as a launch point |
| LittleLinkServer | Yes | No | Social links page |
| Shlink | Yes | No | Link shortener with analytics |

### Reverse Proxy & Ingress

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Traefik | Yes | No | Tim uses Traefik for routing + certs |
| Cilium Gateway API | No | **Yes** | This cluster uses Gateway API (not Ingress) |
| cert-manager | Not described | **Yes** | Automated TLS certificates |
| Cloudflared | Not described | **Yes** | Cloudflare tunnel |

**No gap here** - different approaches to the same problem. Gateway API is the more Kubernetes-native solution.

### DNS

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Pi-hole | Yes | No | DNS + ad blocking + local DNS |
| Nebula Sync | Yes | No | Pi-hole instance sync |
| Keepalived | Yes | No | DNS failover |
| CoreDNS | No | **Yes** | In-cluster DNS |
| external-dns | No | **Yes** | Automated DNS record management |

**Gap**: No ad-blocking DNS in this cluster. Pi-hole is home-network focused; this cluster is co-located so the need is different.

### Monitoring & Observability

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Prometheus | Yes | **Yes** (`monitoring/prometheus-stack/`) | Both use it |
| Grafana | Yes | **Yes** (part of prometheus-stack) | Both use it |
| Loki | Yes | **Yes** (`monitoring/loki-stack/`) | Both use it |
| Tempo | Not mentioned | **Yes** (`monitoring/tempo/`) | This cluster has distributed tracing |
| k8sGPT | No | **Yes** (`monitoring/k8sgpt/`) | AI-powered K8s diagnostics |
| Alloy | Yes | No | Grafana's unified telemetry collector |
| Uptime Kuma | Yes | No | Self-hosted uptime monitoring |
| Uptime Robot | Yes (external) | No | External uptime checks |
| Dozzle | Yes | No | Real-time container log viewer |

**Potential gaps**:
- **Uptime Kuma** - useful for endpoint monitoring with notifications. Could deploy easily as a `my-apps/monitoring/uptime-kuma/` application.
- **Alloy** - Grafana's replacement for Promtail/agent. Worth evaluating if the Loki stack needs a collector upgrade.

### Media

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Plex | Yes (primary) | No | Proprietary media server |
| Jellyfin | Yes (backup) | **Yes** (`my-apps/media/jellyfin/`) | Open-source media server |
| Immich | Yes | **Yes** (`my-apps/media/immich/`) | Photo management |
| TubeSync | No | **Yes** (`my-apps/media/tubesync/`) | YouTube archival |
| Tautulli | Yes | No | Plex activity/stats dashboard |
| Kometa | Yes | No | Media collection/metadata automation |
| HandBrake | Yes | No | Media re-encoding |
| ErsatzTV | Yes | No | Virtual TV channels |
| Dispatcharr | Yes | No | Multi-source channel aggregation |
| HDHomeRun | Yes (hardware) | No | OTA TV tuner |

**Gap analysis**: Tim's media stack is significantly larger, centered around Plex. This cluster runs Jellyfin only. The media companion tools (Tautulli, Kometa, ErsatzTV) are Plex-specific and only relevant if Plex is added.

### Documents & PDF

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Paperless-ngx | Yes | **Yes** (`my-apps/home/paperless-ngx/`) | Both use it |
| Paperless-GPT | Yes | No | AI-enhanced document processing |
| Apache Tika | Yes | No | Content extraction engine |
| Gotenberg | Yes | No | PDF generation API |
| Stirling PDF | Yes | No | PDF editing web UI |

**Potential gaps**:
- **Stirling PDF** - lightweight, broadly useful PDF tool. Easy to deploy.
- **Paperless-GPT** - could leverage the existing llama-cpp backend for AI document processing.

### AI / LLM

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Ollama | Yes | No | Model management + inference |
| Open WebUI | Yes | **Yes** (`my-apps/ai/open-webui/`) | Chat interface |
| llama-cpp | No | **Yes** (`my-apps/ai/llama-cpp/`) | Direct inference server |
| ComfyUI | No | **Yes** (`my-apps/ai/comfyui/`) | AI image generation |
| Perplexica | No | **Yes** (`my-apps/ai/perplexica/`) | AI-powered search |

**No gap** - this cluster has a more comprehensive AI stack. llama-cpp is used instead of Ollama (more direct, lower overhead for single-model serving).

### Home Automation

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Home Assistant | Yes | **Yes** (`my-apps/home/home-assistant/`) | Both use it |
| Frigate | Not mentioned | **Yes** (`my-apps/home/frigate/`) | NVR with object detection |
| Wyze Bridge | Not mentioned | **Yes** (`my-apps/home/wyze-bridge/`) | Wyze camera RTSP bridge |
| MQTT | Yes | No (in this cluster) | Likely runs at home for Tim |
| Zigbee2MQTT | Yes | No | Zigbee device bridge |
| Scrypted | Yes | No | Camera/HomeKit bridge |
| UniFi Protect | Yes | No | Ubiquiti camera system |

**Note**: Tim runs home automation on TrueNAS at home. This cluster runs Home Assistant and Frigate in Kubernetes, likely co-located. MQTT/Zigbee2MQTT are typically home-local services.

### Automation & Workflows

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| n8n | Yes | **Yes** (`my-apps/development/n8n/`) | Both have it |
| Postiz | Yes | No | Social media scheduling |

### Databases

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| PostgreSQL | Yes | **Yes** (CNPG operator + instances) | This cluster uses CloudNativePG |
| MariaDB | Yes | No | MySQL-compatible DB |
| Valkey/Redis | Yes | **Yes** (`infrastructure/database/redis/`) | Both use it |
| pgAdmin | Yes | No | Postgres admin UI |
| Adminer | Yes | No | Lightweight DB admin |
| phpMyAdmin | Yes | No | MySQL admin |
| dbgate | Yes | No | Multi-DB admin |
| databasus | Yes | No | DB backup tool |
| Redis Commander | Not mentioned | **Yes** | Redis admin UI |

**Potential gap**: No database admin UI beyond Redis Commander. **Headlamp** (`my-apps/development/headlamp/`) serves as a K8s dashboard but not a DB tool. Adding pgAdmin or Adminer would help with database management.

### Development Tools

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Code Server | Yes | No | VS Code in browser |
| IT-Tools | Yes | **Yes** (`my-apps/development/it-tools/`) | Dev utilities |
| Gitea | Not mentioned | **Yes** (`my-apps/development/gitea/`) | Self-hosted Git |
| Kafka/Strimzi | No | **Yes** | Event streaming |
| Temporal | No | **Yes** | Workflow orchestration |
| PostHog | No | **Yes** | Product analytics |
| Headlamp | No | **Yes** | Kubernetes dashboard |
| Mailpit | No | **Yes** | Email testing |
| PairDrop | No | **Yes** | Local file sharing |

This cluster has a much larger dev tooling footprint.

### Visual / Diagramming

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Excalidraw | Yes | No | Whiteboard-style diagrams |
| draw.io | Yes | No | Structured diagrams |
| Rackula | Yes | No | Rack layout visualization |

**Potential gap**: **Excalidraw** is easy to self-host and broadly useful for collaboration.

### Infrastructure Utilities

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| OpenSpeedTest | Yes | No | Network speed testing |
| Scrutiny | Yes | No | Disk health monitoring |
| nvtop | Yes | No | GPU monitoring CLI |
| Netboot.xyz | Yes | No | Network boot/install |
| NUT / PeaNUT | Yes | No | UPS monitoring |
| Bambu Studio | Yes | No | 3D printer slicer (containerized) |

These are mostly home-infrastructure tools. Less relevant for a co-located K8s cluster.

### Privacy

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| SearXNG | No | **Yes** (`my-apps/privacy/searxng/`) | Privacy search engine |
| Proxitok | No | **Yes** (`my-apps/privacy/proxitok/`) | TikTok privacy frontend |
| Libreddit | No | **Yes** (`my-apps/media/libreddit/`) | Reddit privacy frontend |

This cluster has privacy-focused frontends that Tim doesn't mention.

### Kubernetes Platform

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Rancher | Yes | No | K8s management UI |
| Flux | Yes | No | GitOps (Tim uses this) |
| Renovate | Yes | No | Dependency updates |
| ArgoCD | No | **Yes** | GitOps (this cluster uses this) |
| Kyverno | No | **Yes** | Policy engine + auto backup |
| VolSync + PVC Plumber | No | **Yes** | Automated backup/restore |
| Longhorn | Yes | **Yes** | Cloud-native storage |
| Reloader | Yes | **Yes** | Auto-restart on config change |
| kube-vip | Yes | No | VIP + LB (this cluster uses Cilium) |
| Reflector | Yes | No | Secret replication (this uses External Secrets) |
| VPA | No | **Yes** | Vertical Pod Autoscaler |

### Static Sites / Content

| Service | Tim | This Cluster | Notes |
|---------|-----|-------------|-------|
| Jekyll | Yes | No | Blog/documentation site |
| Kiwix | No | **Yes** (`my-apps/media/kiwix/`) | Offline content server |

---

## Summary: Notable Gaps Worth Considering

### High Value (Easy to deploy, broadly useful)

| Service | Why | Effort |
|---------|-----|--------|
| **Stirling PDF** | PDF editing web UI - useful for any document workflow | Low - single container |
| **Excalidraw** | Collaborative whiteboard/diagramming | Low - single container |
| **Uptime Kuma** | Endpoint monitoring with notifications | Low - single container + PVC |

### Medium Value (Useful depending on needs)

| Service | Why | Effort |
|---------|-----|--------|
| **Dozzle** | Quick container log viewing (complement to Loki) | Low |
| **Paperless-GPT** | AI document processing using existing llama-cpp | Medium - needs llama-cpp integration |
| **pgAdmin** | Database admin UI for CNPG instances | Low |
| **Alloy** | Modern Grafana telemetry collector | Medium - replaces existing collectors |

### Low Priority (Home-specific or architectural differences)

| Service | Why it's low priority |
|---------|----------------------|
| Pi-hole | Home-network service; cluster is co-located |
| Plex/Tautulli/Kometa | Proprietary media stack; Jellyfin covers the need |
| MQTT/Zigbee2MQTT | Home-local IoT; better on TrueNAS/Docker |
| NUT/Scrutiny/nvtop | Hardware monitoring; more relevant at home |
| Rancher | ArgoCD already provides GitOps management |

---

## What This Cluster Has That Tim Doesn't Mention

This cluster has significant capabilities Tim didn't cover:

- **Automated PVC backup/restore** (Kyverno + VolSync + PVC Plumber) - just add `backup: "daily"` label
- **CNPG database operator** with Barman S3 backups and documented DR procedures
- **AI image generation** (ComfyUI with GPU)
- **AI search** (Perplexica, SearXNG)
- **Privacy frontends** (Proxitok, Libreddit)
- **Event streaming** (Kafka/Strimzi)
- **Workflow orchestration** (Temporal)
- **Product analytics** (PostHog)
- **Distributed tracing** (Tempo)
- **AI K8s diagnostics** (k8sGPT)
- **NFS 10G performance tuning** (readahead, sunrpc slots, BBR, nconnect)
- **Gateway API** (Kubernetes-native routing vs traditional reverse proxy)
- **Self-managing ArgoCD** (ArgoCD manages its own config)
