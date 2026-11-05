# Architecture

This document explains how the components of the Omni + Talos + Proxmox stack work together.

## Component overview

### Omni (self-hosted)
- **Purpose**: Central management platform for Talos clusters
- **Components**:
  - Web UI for cluster management
  - gRPC API for machine communication
  - Kubernetes API proxy
  - SideroLink for secure node communication
  - Etcd for state storage
- **Location**: Ubuntu host (Docker container)
- **Port requirements**: 443, 8090, 8100, 8091, 50180/udp

### Proxmox infrastructure provider
- **Purpose**: Bridge between Omni and Proxmox
- **Function**: Automatically provisions VMs based on Omni machine requests
- **Location**: Ubuntu host (Docker container, can be same as Omni)
- **Communication**:
  - Watches Omni API for machine class requests
  - Creates/manages VMs via Proxmox API
  - Reports VM status back to Omni

### Proxmox VE
- **Purpose**: Hypervisor for running Talos VMs
- **Function**: Provides compute, storage, and networking
- **Configuration**: Storage pools, networks, and resources

### Talos Linux
- **Purpose**: Immutable Kubernetes operating system
- **Characteristics**:
  - No SSH access (API-only management)
  - Minimal attack surface
  - Declarative configuration
  - Rolling updates

## Communication flow

### Initial setup flow

```
1. Admin → Omni UI
   ├─ Create account / authenticate
   └─ Generate infrastructure provider key

2. Admin → Proxmox Provider
   ├─ Configure with Omni endpoint
   ├─ Configure with Proxmox credentials
   └─ Start provider (connects to both)

3. Proxmox Provider → Omni API
   ├─ Registers as infrastructure provider
   └─ Begins watching for machine requests

4. Admin → Omni UI
   ├─ Create machine classes (define VM specs)
   └─ Create cluster (request machines)

5. Omni → Proxmox Provider
   └─ Sends machine request with class specs

6. Proxmox Provider → Proxmox API
   ├─ Creates VM with specified resources
   ├─ Downloads Talos image
   └─ Starts VM

7. Talos VM → Omni (via SideroLink)
   ├─ Establishes WireGuard tunnel
   ├─ Registers with Omni
   └─ Receives configuration

8. Omni → Talos Nodes
   ├─ Applies machine config
   ├─ Bootstraps Kubernetes
   └─ Joins cluster

9. Admin → Omni UI
   └─ Accesses cluster via Kubernetes proxy
```

## Network architecture

### Network design (10G switch)

All traffic uses a single network via 10G switch:

```
┌─────────────────────────────────────────────────────────────────┐
│ Physical Network Layout                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Main Network (vmbr0 / ens18) - 10G Switch                     │
│  ├── 192.168.10.0/24 (DHCP)                                    │
│  ├── All management traffic                                     │
│  ├── SideroLink tunnels to Omni                                │
│  ├── Inter-node cluster communication                          │
│  ├── Storage traffic to TrueNAS (192.168.10.133)              │
│  └── Default gateway for internet access                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Key IP Assignments                                              │
├─────────────────────────────────────────────────────────────────┤
│  192.168.10.133  - TrueNAS (10G via switch)                    │
│  192.168.10.14   - Proxmox                                     │
│  192.168.10.x    - Workers (DHCP)                              │
│  192.168.10.x    - Control Planes (DHCP)                       │
│  192.168.10.x    - GPU Worker (DHCP)                           │
└─────────────────────────────────────────────────────────────────┘
```

### Ports and services

**Omni Server**:
```
443 (TCP)       - HTTPS (Web UI + API)
8090 (TCP)      - Machine API (SideroLink gRPC)
8100 (TCP)      - Kubernetes proxy
8091 (TCP)      - Event sink
50180 (UDP)     - WireGuard (SideroLink tunnel)
```

**Proxmox Provider**:
```
Outbound HTTPS  - To Omni API
Outbound HTTPS  - To Proxmox API (port 8006)
```

**Talos Nodes**:
```
Outbound 8090   - To Omni machine API
Outbound 50180  - To Omni WireGuard
6443 (TCP)      - Kubernetes API (exposed via Omni)
```

### Network flows

```
┌─────────────┐
│ Admin       │
│ Workstation │
└──────┬──────┘
       │ HTTPS (443)
       ▼
┌─────────────────────────────────────────┐
│ Omni Server                             │
│                                         │
│  ┌──────────┐    ┌──────────────────┐  │
│  │ Web UI   │    │ Kubernetes Proxy │  │
│  │ (443)    │    │ (8100)           │  │
│  └──────────┘    └──────────────────┘  │
│                                         │
│  ┌──────────────────┐  ┌─────────────┐ │
│  │ Machine API      │  │ SideroLink  │ │
│  │ (8090)           │  │ (50180/udp) │ │
│  └──────────────────┘  └─────────────┘ │
└──────┬───────────────────────┬──────────┘
       │                       │
       │ HTTPS                 │ WireGuard
       │                       │
┌──────▼─────────┐      ┌──────▼──────────────┐
│ Proxmox        │      │ Talos Nodes         │
│ Provider       │      │                     │
│                │      │ ┌─────────────────┐ │
│ Watches API    │      │ │ Control Plane 1 │ │
│ Creates VMs    │      │ └─────────────────┘ │
└──────┬─────────┘      │ ┌─────────────────┐ │
       │                │ │ Control Plane 2 │ │
       │ Proxmox API    │ └─────────────────┘ │
       │ (8006)         │ ┌─────────────────┐ │
       ▼                │ │ Worker 1        │ │
┌────────────────┐      │ └─────────────────┘ │
│ Proxmox VE     │      │ ┌─────────────────┐ │
│ Cluster        │◄─────┤ │ Worker 2        │ │
│                │ Boot │ └─────────────────┘ │
└────────────────┘      └─────────────────────┘
```

## Data flow

### Cluster creation

```
User → Omni UI: "Create cluster with 3 control plane, 3 workers"
    │
    ▼
Omni: Creates machine requests (6 total)
    │
    ▼
Proxmox Provider: Detects machine requests
    │
    ▼
Proxmox Provider: For each machine request:
    ├─ Evaluates machine class (CPU, RAM, disk, storage CEL)
    ├─ Creates VM in Proxmox with specs
    ├─ Attaches Talos boot ISO
    └─ Starts VM
    │
    ▼
Talos VM: Boots
    ├─ Establishes SideroLink tunnel to Omni
    ├─ Registers with Omni (provides hardware info)
    └─ Waits for configuration
    │
    ▼
Omni: Detects registered machines
    ├─ Assigns to cluster
    ├─ Generates machine config (certificates, etcd, etc.)
    └─ Sends config via SideroLink
    │
    ▼
Talos Nodes: Apply configuration
    ├─ Install to disk
    ├─ Configure networking
    ├─ Join etcd cluster (control plane)
    └─ Join Kubernetes cluster
    │
    ▼
Omni: Cluster ready
    └─ User can access via Kubernetes proxy
```

## Storage architecture

### Omni storage

```
/etc/etcd/
└── Encrypted etcd data (GPG encrypted)
    ├── Cluster state
    ├── Machine configurations
    ├── User accounts
    └── Infrastructure provider metadata

/etc/letsencrypt/
└── SSL certificates
    ├── fullchain.pem
    └── privkey.pem

/path/to/omni.asc
└── GPG encryption key
```

### Talos storage (per node)

```
/dev/sda (or equivalent)
├── Boot partition (Talos kernel + initramfs)
├── STATE partition (machine config, etcd for control plane)
└── EPHEMERAL partition (container storage, ephemeral data)

Optional additional disks:
/dev/sdb (supported via the machine class `additional_disks`)
└── Persistent storage (e.g., Longhorn volumes)
```

## Security architecture

### Authentication and authorization

```
┌──────────────────────────────────────────────────┐
│ User Authentication                              │
│                                                  │
│ Auth0 / SAML / OIDC                             │
│    │                                             │
│    ▼                                             │
│ Omni (validates token)                          │
│    │                                             │
│    ▼                                             │
│ Role-Based Access Control (RBAC)                │
│    ├─ Cluster Admin                             │
│    ├─ Cluster Operator                          │
│    └─ Cluster Reader                            │
└──────────────────────────────────────────────────┘
```

### Encryption

**In Transit**:
- Omni ↔ User: TLS 1.3 (Let's Encrypt certificates)
- Omni ↔ Talos: WireGuard (SideroLink tunnel)
- Omni ↔ Provider: HTTPS
- Provider ↔ Proxmox: HTTPS

**At Rest**:
- Omni etcd: GPG encryption (user-provided key)
- Talos STATE: Optional disk encryption (configured per cluster)

### Access control

**Omni**:
- No direct shell access
- All access via authenticated API
- TLS mutual authentication for machines

**Talos**:
- No SSH
- No console access (except emergency)
- All operations via API (authenticated with certificates)
- API access proxied through Omni

**Proxmox**:
- Provider uses dedicated user (or root@pam)
- API token authentication
- Limited to VM management permissions

## Scalability

### Horizontal scaling

**Omni**:
- Single instance (etcd embedded)
- Can handle hundreds of clusters
- Thousands of machines

**Proxmox Provider**:
- Multiple instances supported
- Coordinate through Omni API
- Automatic leader election
- Each can manage full cluster

**Talos Clusters**:
- Control plane: 1, 3, or 5 nodes (odd number)
- Workers: Unlimited (practical limit ~1000 per cluster)
- Multiple clusters per Omni instance

### Resource requirements

**Omni Server**:
- Minimum: 2 CPU, 4GB RAM, 50GB disk
- Recommended: 4 CPU, 8GB RAM, 100GB SSD
- Scales with number of managed clusters

**Proxmox Provider**:
- Minimum: 1 CPU, 1GB RAM
- Lightweight (watches API only)

**Talos Control Plane**:
- Minimum: 2 CPU, 4GB RAM, 50GB disk
- Recommended: 4 CPU, 8GB RAM, 100GB disk

**Talos Workers**:
- Varies by workload
- Minimum: 2 CPU, 4GB RAM, 50GB disk

## High availability

### Omni HA (not covered in this starter kit)
- Requires external etcd cluster
- Multiple Omni instances behind load balancer
- Shared state via external etcd

### Talos cluster HA (included)
- Odd number of control plane nodes (3 or 5)
- Etcd quorum maintained
- API server load balanced via SideroLink
- Worker nodes can fail without cluster impact

### Proxmox HA
- Multiple provider instances (automatic coordination)
- Proxmox cluster with HA features
- Shared storage for VM resilience

## Extension points

### Custom machine classes
- Define templates for different workload types
- GPU nodes, storage nodes, compute nodes
- Different CPU/RAM/disk configurations

### Talos extensions
- NVIDIA drivers
- Custom kernel modules
- Additional system packages
- Network plugins

### Machine config patches
- Custom sysctl settings
- Additional mounts
- Network configuration
- Volume management

## Monitoring and observability

### Omni metrics
- Cluster health status
- Node status
- Update progress
- Infrastructure provider status

### Talos metrics
- Exported via node metrics API
- Scraped by Prometheus in cluster
- System resources (CPU, RAM, disk)
- Kubernetes metrics

### Proxmox metrics
- VM resource utilization
- Storage usage
- Network traffic
- Available via Proxmox API

## Backup and recovery

### Omni backup
```
Critical data:
- /etc/etcd/ (cluster state)
- omni.asc (encryption key)
- SSL certificates

Recovery:
- Restore etcd data
- Restore encryption key
- Restart Omni
```

### Talos backup
```
Cluster state stored in:
- Omni (primary source of truth)
- Talos control plane etcd (Kubernetes state)

Recovery:
- Omni can rebuild cluster from stored state
- Kubernetes etcd can be restored from backups
```

## Update process

### Omni updates
```
1. Stop Omni container
2. Update OMNI_IMG_TAG in omni.env
3. Pull new image
4. Start Omni container
5. Verify functionality
```

### Talos updates
```
Managed through Omni:
1. Select cluster
2. Click "Update"
3. Select new Talos version
4. Click "Update All Machines"
5. Rolling update (one node at a time)
6. Control plane first, then workers
```

### Proxmox provider updates
```
1. Pull latest provider image
2. Restart provider container
3. No downtime (VMs continue running)
```

## Decision points

### When to use this stack

**Good fit**:
- Self-hosted infrastructure preference
- Proxmox existing deployment
- Multiple cluster management needed
- Security-focused (immutable OS)
- Automated cluster lifecycle

**Not ideal**:
- Single cluster only (Talos standalone may be simpler)
- Managed cloud preference (use cloud provider)
- Need for OS-level customization (use traditional Linux)

### Architecture alternatives

**Alternative 1**: Omni SaaS + Proxmox Provider
- Use hosted Omni instead of self-hosted
- Only deploy Proxmox provider locally
- Simpler setup, but data leaves premises

**Alternative 2**: Standalone Talos
- Skip Omni entirely
- Manage Talos with talosctl directly
- More manual, less automation

**Alternative 3**: Traditional Kubernetes
- Use Ubuntu/Debian VMs
- Install Kubernetes with kubeadm
- More familiar, but more maintenance
