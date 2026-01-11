# VolSync Implementation Plan: Kyverno Smart Restore

## Overview
This document details the implementation of the "Smart Restore" strategy. 
It uses a **Service Bridge** to allow Kyverno to "look before it leaps" by checking S3 availability.

## Core Components

### 1. The Bridge (Direct IP)
**Strategy:** Direct Connection
Instead of creating a Kubernetes Service (which causes ArgoCD sync issues for external IPs), we connect directly to the TrueNAS IP.
*   **Target:** `192.168.10.133` (Port 9000)
*   **Benefit:** Zero-friction GitOps state (no "ExcludedResourceWarning").

### 2. The Credentials (ExternalSecret)
**File:** `infrastructure/storage/volsync/rustfs-credentials.yaml` (Existing)
*   Already implemented relative to the existing codebase.
*   Kyverno will assume the secret `volsync-rustfs-base` (or similar) is present in the namespace.

### 3. The "Smart" Policy (Kyverno)
**File:** `infrastructure/controllers/kyverno/volsync-smart-restore.yaml`
Logic: "Check for Restic Config. If found, Restore. Else, Backup."

**Rule 1: Generate Backup (Always)**
*   Trigger: PVC `backup: hourly`
*   Action: Create `ReplicationSource` (hourly schedule)

**Rule 2: Smart Restore (Conditional)**
*   Trigger: PVC `backup: hourly`
*   **(apiCall):**
    *   Target: `http://192.168.10.133:9000/volsync-backups/<ns>/<pvc>/config` (Direct IP)
    *   Method: `GET` (Kyverno compatible)
*   **Condition:** Response == 200 OK.
*   **Action:** Create `ReplicationDestination`.

## Deployment Steps
1.  **Apply Service:** `kind: Service` & `kind: Endpoints` for RustFS.
2.  **Apply Policy:** `volsync-smart-restore.yaml`.
3.  **Verify:**
    *   **Test A (Fresh):** Create `pvc-test` (no backup). -> No RD created. PVC binds.
    *   **Test B (Restore):** Allow backup to run. Delete PVC. Re-create `pvc-test`. -> RD created.

## Failure Modes
*   **S3 Down/Forbidden:** apiCall fails. Kyverno blocks or skips.
    *   *Default Behavior:* We treat "Unknown" as "No Restore". This prevents accidental overwrites or stalled startups.
