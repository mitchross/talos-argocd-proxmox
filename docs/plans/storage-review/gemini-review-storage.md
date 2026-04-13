# Architectural Review: Zero-Touch Declarative Stateful Disaster Recovery

## 1. The Engineering Problem

In modern Kubernetes environments, there is a fundamental "impedance mismatch" between declarative deployment tools (like ArgoCD/Flux) and stateful backup/restore tools (like Velero). 

**The GitOps Impedance Mismatch:**
GitOps tools enforce the desired state of a cluster based on Git manifests. If an entire cluster is destroyed and redeployed, ArgoCD immediately provisions fresh, empty PersistentVolumeClaims (PVCs) for applications. Traditional backup utilities like [Velero](https://velero.io) are imperative—they require a human or an external CI pipeline to run a `restore` command *before* ArgoCD spins up the apps, creating a conflict in ownership and hindering true "Zero-Touch" infrastructure.

**The VolSync / CSI Limitation:**
While tools like VolSync can use a `VolumePopulator` (`dataSourceRef`) to hydrate a PVC from a backup upon creation, it lacks a conditional API. If you hardcode `dataSourceRef` in your Git manifests for a *brand new application*, Kubernetes will hang the PVC in a `Pending` state indefinitely because no backup archive exists yet. 

There is no native Kubernetes mechanism that says: *"If a backup exists, use it; otherwise, provision an empty volume."*

## 2. The Implemented Solution

The author engineered a custom microservice (`pvc-plumber`) married with Kyverno mutating and validating admission policies to solve this declarative sequencing gap.

**The Flow:**
1. **Separation of Concerns:** Primary compute and storage run on ephemeral Talos VMs utilizing Longhorn (on Proxmox local NVMe) for high-performance localized I/O. TrueNAS sits on the network strictly as a redundant archival target.
2. **Admission Interception:** When a developer pushes a PVC manifest with a `backup` label, Kyverno intercepts the API request. 
3. **The Plumber / Kopia Cache:** `pvc-plumber` acts as an oracle, querying a mounted TrueNAS NFS share containing Kopia repository snapshots to see if the identity (`namespace/pvc-name`) exists. (It employs a highly efficient startup cache sweep using `kopia snapshot list --all` to reduce webhook latency to sub-milliseconds).
4. **Conditional Mutation:** If the backup exists, Kyverno injects the `dataSourceRef`. The volume is dynamically populated from TrueNAS via VolSync before the pod binds. If it does not exist, the PVC deploys empty.

**Result:** 100% declarative, Zero-Touch infrastructure where developers do not violate DRY (Don't Repeat Yourself) principles, and disaster recovery occurs autonomously via ArgoCD sync loops.

---

## 3. FAANG-Style Architectural Critique & Challenges

While the solution is an exceptional bridge for the GitOps/Stateful gap, an enterprise infrastructure review highlights several operational risks and simpler alternatives that must be justified.

### Challenge 1: The "Over-Engineering" Argument (Simpler Alternatives)
A primary challenge to this design is whether it over-engineers a solved problem by refusing to compromise on GitOps purity.
*   **The Velero Imperial Standard:** The industry standard is to accept the imperative nature of DR. If a cluster dies, engineers run `velero restore` via CLI, and *then* turn on ArgoCD. (Reference: [Handling GitOps and Velero Conflicts](https://github.com/vmware-tanzu/velero/issues/2390)).
*   **The Storage Array Standard (Static PVs):** If the goal is absolute Zero-Touch DR utilizing TrueNAS, one could explicitly use Static PersistentVolumes pointing to TrueNAS NFS shares. Upon an ArgoCD sync, pods bind to the static shares natively—bypassing VolSync, Kopia, and `pvc-plumber` entirely. 

*Defense:* Static PVs defeat Dynamic Provisioning, and Velero defeats 100% declarative autonomy. `pvc-plumber` is justified specifically for engineers who demand *both*.

### Challenge 2: The "Thundering Herd" DR Spikes (Network & CPU)
`pvc-plumber` operates flawlessly at the micro-level (a single pod failing). At the macro-level (a full cluster nuke), it introduces severe "Thundering Herd" risks.
*   When ArgoCD re-bootstraps the cluster, it will spawn 50-100+ VolSync mover pods simultaneously. 
*   These pods will concurrently mount the TrueNAS NFS share, heavily spiking CPU for Kopia index decryptions, and saturating the 10Gbps network link to stream data back to Longhorn replicas.
*   *Mitigation Required:* The architecture must artificially stagger ApplicationSync waves in ArgoCD or implement `PostSync` hooks to throttle VolSync `ReplicationDestinations`, preventing network/IOPS exhaustion during a full recovery event.

### Challenge 3: Kopia Concurrent Locking over NFS
The architecture relies on cross-PVC deduplication by pointing all VolSync pods to a unified Kopia repository over an NFS mount (`BACKEND_TYPE=kopia-fs`).
*   NFS Network Lock Manager (NLM) is notoriously fragile in highly distributed, concurrent environments. Multiple distributed Kopia clients writing blobs over NFS concurrently can lead to index corruption or lock-timeouts. (Reference: [NFS Concurrent Writers and Corruption](https://unix.stackexchange.com/questions/681329/multiple-servers-writing-to-the-same-file-on-nfs)).
*   *Mitigation Required:* While the user possesses S3 (GarageFS), switching to S3 isolates repositories per PVC, destroying global deduplication. The enterprise solution to maintain deduplication while dropping NFS locking risks is to deploy a dedicated **Kopia Repository Server** pod in the cluster, forcing all VolSync clients to connect via gRPC/API rather than raw filesystem access.

### Challenge 4: Split-Brain Data Consistency
The system explicitly exempts Database systems (CloudNativePG) from this PVC flow due to filesystem snapshot constraints, relying on Barman + S3 instead. The database application set is configured with `selfHeal: false` for manual DBA restoration.
*   During an automated total cluster restore, stateless apps and static media PVCs restore automatically to the 2:00 AM snapshot. 
*   If a DBA manually restores the Barman WAL archive to 2:45 AM, the cluster enters a "split-brain" state of referential integrity loss (the database references files on the filesystem that haven't been created yet, or vice versa).
*   *Mitigation Required:* True enterprise backup tools (e.g., Kasten K10) coordinate application-consistent snapshots, calling database freeze/dump hooks synchronously with volume snapshots to ensure identical timestamps across all operational layers.

---

## 4. Overall Verdict

The architecture solves a genuine limitation in the CNCF ecosystem (declarative Stateful DR). However, it is an aggressive, "over-engineered" abstraction layer built to avoid using imperative tools like Velero. It effectively shifts complexity away from human operators (Zero-Touch recovery) and pushes it entirely onto the cluster's network and admission controllers (Kyverno, VolSync Mover swarms). 

It is entirely valid, provided the cluster has the compute headroom to handle the resulting Thundering Herd recoveries and Longhorn replication overhead.

---

## 5. Final Recommendations (Call To Actions)

If taking this implementation to production or publishing an architectural guide, the following recommendations should be explicitly addressed:

1. **Implement ArgoCD Wave Staggering:** Prevent the "Thundering Herd" DR event by ensuring ApplicationSets deploy in staggered sync waves, or use ArgoCD post-sync hooks to limit the concurrency of VolSync Mover pods hitting the TrueNAS server simultaneously.
2. **Adopt Kopia Repository Server for NFS:** To protect the integrity of the centralized repository during concurrent writes and bypass brittle NFS (NLM) file locking, deploy a centralized `Kopia Repository Server` pod. Configure VolSync to connect to the server via API rather than raw filesystem access, preserving cross-PVC deduplication securely.
3. **Document Split-Brain DB Rollbacks:** Explicitly outline in disaster recovery runbooks that Database Administrators must manually roll Barman DB archives back to the *exact* hour of the `pvc-plumber` restores (e.g., 2:00 AM) to preserve referential integrity between the databases and the filesystem assets.
4. **Note the Webhook Cache Edge Case:** The `pvc-plumber` 60s cache TTL is brilliant for webhook latency, but document the edge case: if a developer manually creates a backup, destroys the PVC, and recreates it within 60 seconds, the admission hook will hit the stale cache and provision an empty PVC.
5. **Acknowledge the Longhorn vs. TrueNAS CSI Trade-off:** The architecture actively accepts Longhorn's high network and CPU replication overhead to maintain a physical boundary between primary compute and secondary storage. If lower overhead is desired, TrueNAS Democratic CSI is the standard. However, doing so would place both primary compute I/O and secondary backups on the exact same TrueNAS appliance (a Single Point of Failure). The current design—absorbing Longhorn's performance penalty on Proxmox NVMe to maintain TrueNAS as a heavily isolated backup vault—is a valid, albeit expensive, adherence to the 3-2-1 backup principle.
