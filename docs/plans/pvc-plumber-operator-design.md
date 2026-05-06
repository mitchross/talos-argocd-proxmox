# pvc-plumber v2: Operator Design & Build Plan

**Status**: Design / pre-implementation  
**Date**: 2026-05-06  
**Goal**: Replace all Kyverno volsync policies + orphan-reaper CronJob with a purpose-built Go operator baked into pvc-plumber.

---

## Why

The current system works, but has three pain points:

1. **Kyverno is a general policy engine** with sharp edges specific to the generate + external-HTTP pattern used here (`background: false`, `synchronize: false`, `mutateExistingOnPolicyUpdate: false` — any of these set wrong has caused cluster incidents).
2. **Webhook deadlock risk** — if Kyverno crashes with its webhook still registered (`failurePolicy: Fail`), the entire cluster can deadlock. We've hit this once (2026-04-08).
3. **Orphan cleanup is a bash CronJob** because Kyverno's `ClusterCleanupPolicy` is silently broken on 1.17.x/1.18.x (confirmed drill #4, 2026-04-30). Running kubectl in a CronJob is a code smell.

The operator owns the full PVC backup lifecycle in one purpose-built binary. pvc-plumber already has the Kopia repository check logic; adding a controller-runtime reconciler and webhook server is the delta.

---

## What Gets Replaced

| Current component | Replaced by |
|---|---|
| Kyverno rule 1: deny if pvc-plumber unknown | Operator validating webhook |
| Kyverno rule 2: inject `dataSourceRef` | Operator mutating webhook |
| Kyverno rule 3: belt-and-suspenders validate | Operator validating webhook |
| Kyverno rule 4: require skip-restore-reason | Operator validating webhook |
| Kyverno rule 5: generate ExternalSecret | Operator PVC reconciler |
| Kyverno rule 6: generate ReplicationSource | Operator PVC reconciler |
| Kyverno rule 7: generate ReplicationDestination | Operator PVC reconciler |
| `volsync-nfs-inject.yaml` Kyverno policy | Operator Job mutating webhook |
| `orphan-reaper` CronJob | Operator PVC reconciler (on delete/label change) |
| `volsync-pvc-backup-restore` ClusterPolicy | Deleted |
| `volsync-nfs-inject` ClusterPolicy | Deleted |

**What does NOT change**: VolSync, Longhorn, ExternalSecrets operator, the `backup: "hourly"/"daily"` label contract, the `skip-restore` annotation escape hatch. Users see zero difference.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   pvc-plumber (operator)                │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Webhook Server (port 9443, TLS via cert-manager) │  │
│  │                                                   │  │
│  │  POST /mutate/v1/pvc                              │  │
│  │    - skip if not backup-labeled                   │  │
│  │    - skip if skip-restore=true                    │  │
│  │    - call Kopia check (existing logic)            │  │
│  │    - if decision=restore → patch dataSourceRef    │  │
│  │                                                   │  │
│  │  POST /validate/v1/pvc                            │  │
│  │    - deny if pvc-plumber result is non-auth.      │  │
│  │    - deny if restore needed but dataSourceRef     │  │
│  │      missing (belt-and-suspenders)                │  │
│  │    - deny skip-restore=true without reason        │  │
│  │                                                   │  │
│  │  POST /mutate/v1/job                              │  │
│  │    - match app.kubernetes.io/created-by=volsync   │  │
│  │    - inject NFS volume + volumeMount into all     │  │
│  │      containers                                   │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  PVC Reconciler (controller-runtime)              │  │
│  │                                                   │  │
│  │  Watch: PersistentVolumeClaim                     │  │
│  │                                                   │  │
│  │  On CREATE / label added:                         │  │
│  │    - create ExternalSecret (kopia password)       │  │
│  │    - wait for PVC phase=Bound                     │  │
│  │    - wait 2h after creation                       │  │
│  │    - create ReplicationSource (backup schedule)   │  │
│  │    - create ReplicationDestination (restore cap)  │  │
│  │                                                   │  │
│  │  On label removed / PVC deleted:                  │  │
│  │    - delete ExternalSecret                        │  │
│  │    - delete ReplicationSource                     │  │
│  │    - delete ReplicationDestination                │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Kopia Client (existing code, unchanged)          │  │
│  │                                                   │  │
│  │  CheckBackup(ns, pvcName) → Decision              │  │
│  │    Decision: restore | fresh | unknown            │  │
│  │    Authoritative: bool                            │  │
│  │    Error: string                                  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Go Project Structure

The operator lives in the existing `github.com/mitchross/pvc-plumber` repo. Add alongside the existing HTTP server code — don't rewrite, extend.

```
pvc-plumber/
├── main.go                    # entrypoint — starts manager + existing HTTP server
├── cmd/
│   └── operator/
│       └── main.go            # NEW: controller-runtime manager setup
├── internal/
│   ├── kopia/
│   │   └── client.go          # EXISTING: CheckBackup(), etc. — unchanged
│   ├── webhook/
│   │   ├── pvc_mutate.go      # NEW: MutatingWebhookHandler for PVCs
│   │   ├── pvc_validate.go    # NEW: ValidatingWebhookHandler for PVCs
│   │   └── job_mutate.go      # NEW: MutatingWebhookHandler for Jobs (NFS inject)
│   └── controller/
│       └── pvc_controller.go  # NEW: Reconciler for backup-labeled PVCs
├── config/                    # NEW: controller-runtime CRD/RBAC markers
│   ├── rbac/
│   └── webhook/
└── go.mod                     # add controller-runtime, sigs.k8s.io/controller-runtime
```

---

## Key Dependencies to Add

```go
// go.mod additions
require (
    sigs.k8s.io/controller-runtime v0.19.x
    k8s.io/api v0.32.x
    k8s.io/apimachinery v0.32.x
    k8s.io/client-go v0.32.x
    // volsync CRD types — or use unstructured if you don't want the dep
    github.com/backube/volsync v0.x.x  
    // external-secrets types — or use unstructured
    github.com/external-secrets/external-secrets v0.x.x
)
```

**Tip**: Use `unstructured.Unstructured` for VolSync and ExternalSecrets CRDs to avoid importing their entire module tree. You just need to set the right `apiVersion`, `kind`, and spec fields.

---

## Component Implementation Details

### 1. Main entry point

```go
// cmd/operator/main.go
func main() {
    mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
        Scheme:                 scheme,
        MetricsBindAddress:     ":8081",
        HealthProbeBindAddress: ":8082",
        WebhookServer: webhook.NewServer(webhook.Options{
            Port:    9443,
            CertDir: "/tmp/k8s-webhook-server/serving-certs",
        }),
    })

    // Register PVC reconciler
    if err = (&controller.PVCReconciler{
        Client:      mgr.GetClient(),
        KopiaClient: kopia.NewClient(...),
        NFSServer:   os.Getenv("NFS_SERVER"),   // 192.168.10.133
        NFSPath:     os.Getenv("NFS_PATH"),      // /mnt/BigTank/k8s/volsync-kopia-nfs
    }).SetupWithManager(mgr); err != nil { ... }

    // Register webhooks
    mgr.GetWebhookServer().Register("/mutate-v1-pvc",    &webhook.Admission{Handler: &PVCMutator{...}})
    mgr.GetWebhookServer().Register("/validate-v1-pvc",  &webhook.Admission{Handler: &PVCValidator{...}})
    mgr.GetWebhookServer().Register("/mutate-batch-v1-job", &webhook.Admission{Handler: &JobMutator{...}})

    // Keep existing HTTP server running alongside
    go runExistingHTTPServer()

    mgr.Start(ctrl.SetupSignalHandler())
}
```

### 2. PVC Reconciler

```go
// internal/controller/pvc_controller.go

// RBAC markers (used by controller-gen to produce ClusterRole YAML)
//+kubebuilder:rbac:groups="",resources=persistentvolumeclaims,verbs=get;list;watch
//+kubebuilder:rbac:groups=external-secrets.io,resources=externalsecrets,verbs=get;list;watch;create;update;delete
//+kubebuilder:rbac:groups=volsync.backube,resources=replicationsources;replicationdestinations,verbs=get;list;watch;create;update;delete

func (r *PVCReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    var pvc corev1.PersistentVolumeClaim
    if err := r.Get(ctx, req.NamespacedName, &pvc); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    backupLabel := pvc.Labels["backup"]
    isBackupLabeled := backupLabel == "hourly" || backupLabel == "daily"

    // PVC deleted or label removed → cleanup
    if !pvc.DeletionTimestamp.IsZero() || !isBackupLabeled {
        return r.cleanup(ctx, &pvc)
    }

    // Skip system namespaces
    if isSystemNamespace(pvc.Namespace) {
        return ctrl.Result{}, nil
    }

    // Always ensure ExternalSecret exists (idempotent)
    if err := r.ensureExternalSecret(ctx, &pvc); err != nil {
        return ctrl.Result{}, err
    }

    // ReplicationDestination: create immediately (needed before PVC binds for restore)
    if err := r.ensureReplicationDestination(ctx, &pvc); err != nil {
        return ctrl.Result{}, err
    }

    // ReplicationSource: only after Bound AND 2h old
    if pvc.Status.Phase != corev1.ClaimBound {
        return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
    }
    age := time.Since(pvc.CreationTimestamp.Time)
    if age < 2*time.Hour {
        return ctrl.Result{RequeueAfter: 2*time.Hour - age}, nil
    }
    if err := r.ensureReplicationSource(ctx, &pvc); err != nil {
        return ctrl.Result{}, err
    }

    return ctrl.Result{}, nil
}

func (r *PVCReconciler) cleanup(ctx context.Context, pvc *corev1.PersistentVolumeClaim) (ctrl.Result, error) {
    // Delete ES, RS, RD for this PVC — ignore not found
    // Use label selector: volsync.backup/pvc=<pvcName> in pvc.Namespace
    for _, gvk := range []schema.GroupVersionKind{esGVK, rsGVK, rdGVK} {
        list := &unstructured.UnstructuredList{}
        list.SetGroupVersionKind(gvk)
        r.List(ctx, list,
            client.InNamespace(pvc.Namespace),
            client.MatchingLabels{"volsync.backup/pvc": pvc.Name},
        )
        for _, item := range list.Items {
            r.Delete(ctx, &item)
        }
    }
    return ctrl.Result{}, nil
}
```

**ensureExternalSecret / ensureReplicationSource / ensureReplicationDestination** all follow the same pattern:
1. Try `Get` — if found, return nil (idempotent, we don't own drift)
2. If not found, build the object and `Create`
3. Set labels: `app.kubernetes.io/managed-by: pvc-plumber`, `volsync.backup/pvc: <name>`

The spec for each is a direct port from the Kyverno generate rules. See the existing `volsync-pvc-backup-restore.yaml` — rules 5, 6, 7 are the source of truth for the spec fields.

**Schedule determinism** (port from Kyverno rule 6):
```go
func backupSchedule(ns, pvcName, label string) string {
    minute := (len(ns) + len(pvcName)) % 60  // same length-mod logic as Kyverno
    if label == "hourly" {
        return fmt.Sprintf("%d * * * *", minute)
    }
    return fmt.Sprintf("%d 2 * * *", minute)
}
```

### 3. PVC Mutating Webhook

```go
// internal/webhook/pvc_mutate.go

func (h *PVCMutator) Handle(ctx context.Context, req admission.Request) admission.Response {
    if req.Operation != admissionv1.Create {
        return admission.Allowed("")
    }

    var pvc corev1.PersistentVolumeClaim
    if err := h.decoder.Decode(req, &pvc); err != nil {
        return admission.Errored(http.StatusBadRequest, err)
    }

    // Only act on backup-labeled PVCs
    label := pvc.Labels["backup"]
    if label != "hourly" && label != "daily" {
        return admission.Allowed("")
    }

    // Skip-restore opt-out
    if pvc.Annotations["volsync.backup/skip-restore"] == "true" {
        return admission.Allowed("")
    }

    // Skip system namespaces
    if isSystemNamespace(pvc.Namespace) {
        return admission.Allowed("")
    }

    // Already has a dataSourceRef — don't overwrite
    if pvc.Spec.DataSourceRef != nil {
        return admission.Allowed("")
    }

    // Check Kopia — fail-open here (validate webhook is fail-closed)
    decision, err := h.kopia.CheckBackup(ctx, pvc.Namespace, pvc.Name)
    if err != nil || !decision.Authoritative || decision.Decision != "restore" {
        return admission.Allowed("")
    }

    // Inject dataSourceRef
    pvc.Spec.DataSourceRef = &corev1.TypedObjectReference{
        APIGroup: ptr("volsync.backube"),
        Kind:     "ReplicationDestination",
        Name:     pvc.Name + "-backup",
    }

    marshaled, _ := json.Marshal(pvc)
    return admission.PatchResponseFromRaw(req.Object.Raw, marshaled)
}
```

### 4. PVC Validating Webhook

```go
// internal/webhook/pvc_validate.go

func (h *PVCValidator) Handle(ctx context.Context, req admission.Request) admission.Response {
    if req.Operation != admissionv1.Create {
        return admission.Allowed("")
    }

    var pvc corev1.PersistentVolumeClaim
    h.decoder.Decode(req, &pvc)

    label := pvc.Labels["backup"]
    if label != "hourly" && label != "daily" {
        return admission.Allowed("")
    }
    if isSystemNamespace(pvc.Namespace) {
        return admission.Allowed("")
    }

    skipRestore := pvc.Annotations["volsync.backup/skip-restore"] == "true"

    // Rule: skip-restore requires a reason
    if skipRestore {
        reason := pvc.Annotations["volsync.backup/skip-restore-reason"]
        if reason == "" {
            return admission.Denied("volsync.backup/skip-restore=true requires a non-empty volsync.backup/skip-restore-reason annotation")
        }
        return admission.Allowed("")
    }

    // Rule: fail-closed gate — require authoritative decision
    decision, err := h.kopia.CheckBackup(ctx, pvc.Namespace, pvc.Name)
    if err != nil || !decision.Authoritative || decision.Decision == "unknown" {
        return admission.Denied("pvc-plumber could not make an authoritative restore decision; PVC creation denied to prevent empty volume initialization over restorable backup data. ArgoCD will retry.")
    }

    // Rule: if restore required, dataSourceRef must be present and correct
    if decision.Decision == "restore" {
        ref := pvc.Spec.DataSourceRef
        if ref == nil ||
            ref.Kind != "ReplicationDestination" ||
            ref.Name != pvc.Name+"-backup" ||
            ptr.Deref(ref.APIGroup, "") != "volsync.backube" {
            return admission.Denied("pvc-plumber reports a backup exists (decision=restore) but dataSourceRef is missing or incorrect; this would initialize an empty volume over restorable data")
        }
    }

    return admission.Allowed("")
}
```

### 5. Job Mutating Webhook (NFS inject)

```go
// internal/webhook/job_mutate.go

func (h *JobMutator) Handle(ctx context.Context, req admission.Request) admission.Response {
    var job batchv1.Job
    h.decoder.Decode(req, &job)

    // Only VolSync mover jobs
    if job.Labels["app.kubernetes.io/created-by"] != "volsync" {
        return admission.Allowed("")
    }

    // Add NFS volume
    nfsVol := corev1.Volume{
        Name: "repository",
        VolumeSource: corev1.VolumeSource{
            NFS: &corev1.NFSVolumeSource{
                Server: h.nfsServer,  // 192.168.10.133
                Path:   h.nfsPath,    // /mnt/BigTank/k8s/volsync-kopia-nfs
            },
        },
    }
    job.Spec.Template.Spec.Volumes = append(job.Spec.Template.Spec.Volumes, nfsVol)

    // Add mount to every container
    mount := corev1.VolumeMount{Name: "repository", MountPath: "/repository"}
    for i := range job.Spec.Template.Spec.Containers {
        job.Spec.Template.Spec.Containers[i].VolumeMounts = append(
            job.Spec.Template.Spec.Containers[i].VolumeMounts, mount,
        )
    }

    marshaled, _ := json.Marshal(job)
    return admission.PatchResponseFromRaw(req.Object.Raw, marshaled)
}
```

---

## Kubernetes Manifests to Add/Change

### cert-manager Certificate (TLS for webhook server)

```yaml
# infrastructure/controllers/pvc-plumber/certificate.yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: pvc-plumber-webhook-tls
  namespace: volsync-system
spec:
  secretName: pvc-plumber-webhook-tls
  dnsNames:
    - pvc-plumber.volsync-system.svc
    - pvc-plumber.volsync-system.svc.cluster.local
  issuerRef:
    name: selfsigned-issuer     # or whatever issuer you use for internal certs
    kind: ClusterIssuer
```

### MutatingWebhookConfiguration

```yaml
# infrastructure/controllers/pvc-plumber/webhooks.yaml
apiVersion: admissionregistration.k8s.io/v1
kind: MutatingWebhookConfiguration
metadata:
  name: pvc-plumber
  annotations:
    cert-manager.io/inject-ca-from: volsync-system/pvc-plumber-webhook-tls
webhooks:
  - name: mutate-pvc.pvc-plumber.io
    admissionReviewVersions: ["v1"]
    clientConfig:
      service:
        name: pvc-plumber
        namespace: volsync-system
        path: /mutate-v1-pvc
        port: 9443
    rules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        resources: ["persistentvolumeclaims"]
        operations: ["CREATE"]
    namespaceSelector:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: NotIn
          values: [kube-system, volsync-system, kyverno, argocd, longhorn-system]
    failurePolicy: Fail
    sideEffects: None

  - name: mutate-job.pvc-plumber.io
    admissionReviewVersions: ["v1"]
    clientConfig:
      service:
        name: pvc-plumber
        namespace: volsync-system
        path: /mutate-batch-v1-job
        port: 9443
    rules:
      - apiGroups: ["batch"]
        apiVersions: ["v1"]
        resources: ["jobs"]
        operations: ["CREATE"]
    objectSelector:
      matchLabels:
        app.kubernetes.io/created-by: volsync
    failurePolicy: Ignore    # NFS inject failure = backup fails, not a cluster stopper
    sideEffects: None
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: pvc-plumber
  annotations:
    cert-manager.io/inject-ca-from: volsync-system/pvc-plumber-webhook-tls
webhooks:
  - name: validate-pvc.pvc-plumber.io
    admissionReviewVersions: ["v1"]
    clientConfig:
      service:
        name: pvc-plumber
        namespace: volsync-system
        path: /validate-v1-pvc
        port: 9443
    rules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        resources: ["persistentvolumeclaims"]
        operations: ["CREATE"]
    namespaceSelector:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: NotIn
          values: [kube-system, volsync-system, kyverno, argocd, longhorn-system]
    failurePolicy: Fail
    sideEffects: None
```

### Updated Service (add webhook port)

```yaml
# Add to existing Service in deployment.yaml
ports:
  - name: http
    port: 80
    targetPort: 8080
  - name: webhook
    port: 9443
    targetPort: 9443
```

### ClusterRole additions (for reconciler)

```yaml
# infrastructure/controllers/pvc-plumber/rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: pvc-plumber
rules:
  - apiGroups: [""]
    resources: ["persistentvolumeclaims"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["external-secrets.io"]
    resources: ["externalsecrets"]
    verbs: ["get", "list", "watch", "create", "update", "delete"]
  - apiGroups: ["volsync.backube"]
    resources: ["replicationsources", "replicationdestinations"]
    verbs: ["get", "list", "watch", "create", "update", "delete"]
  # Leader election (controller-runtime needs this)
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["create", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: pvc-plumber
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: pvc-plumber
subjects:
  - kind: ServiceAccount
    name: pvc-plumber
    namespace: volsync-system
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: pvc-plumber
  namespace: volsync-system
```

Add `serviceAccountName: pvc-plumber` to the Deployment (currently runs with the default SA).

---

## Migration Strategy (zero-downtime cutover)

**Phase 1: Build & test in isolation** (no cluster changes)
- Build the operator binary
- Run unit tests for reconciler logic and webhook handlers
- Test in a dev namespace with Kyverno still active

**Phase 2: Deploy operator alongside Kyverno**
- Deploy new pvc-plumber image with operator mode (both HTTP server + controller running)
- Do NOT register webhooks yet — operator runs in reconcile-only mode
- Watch for ES/RS/RD creation on test PVCs — operator should create them (Kyverno will also try; idempotent if both create the same resource with the same name)
- Verify operator cleans up orphans correctly

**Phase 3: Webhook cutover**
- Apply `MutatingWebhookConfiguration` and `ValidatingWebhookConfiguration`
- Scale down (or delete) the Kyverno `volsync-pvc-backup-restore` ClusterPolicy and `volsync-nfs-inject` ClusterPolicy
- Test a PVC create → verify webhook fires, dataSourceRef injected, ES/RS/RD generated

**Phase 4: Cleanup**
- Delete `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml`
- Delete `infrastructure/controllers/kyverno/policies/volsync-nfs-inject.yaml`
- Delete `infrastructure/storage/volsync/orphan-reaper.yaml` (CronJob + SA + RBAC)
- Update kustomization.yaml files for both directories
- If Kyverno is now only used for `longhorn-pvc-backup-audit.yaml`, evaluate whether Kyverno is still worth running at all

---

## Environment Variables for Operator

Add to Deployment:

```yaml
env:
  # existing vars unchanged
  - name: KOPIA_PASSWORD
    valueFrom:
      secretKeyRef:
        name: pvc-plumber-kopia
        key: KOPIA_PASSWORD
  # new operator vars
  - name: NFS_SERVER
    value: "192.168.10.133"
  - name: NFS_PATH
    value: "/mnt/BigTank/k8s/volsync-kopia-nfs"
  - name: SYSTEM_NAMESPACES
    value: "kube-system,volsync-system,kyverno,argocd,longhorn-system"
  - name: OPERATOR_MODE
    value: "true"    # feature flag to enable controller-runtime alongside existing HTTP server
```

---

## Testing Checklist

- [ ] New backup-labeled PVC → ES, RS, RD created with correct spec
- [ ] New backup-labeled PVC with existing Kopia backup → dataSourceRef injected, PVC populates from backup
- [ ] New backup-labeled PVC with NO Kopia backup → no dataSourceRef, PVC provisions fresh
- [ ] Backup label removed from PVC → ES, RS, RD deleted within one reconcile cycle
- [ ] PVC deleted → ES, RS, RD deleted
- [ ] `skip-restore=true` without reason → admission denied
- [ ] `skip-restore=true` with reason → PVC admitted, no dataSourceRef, backup still generated
- [ ] pvc-plumber pod crashes → webhook `failurePolicy: Fail` blocks PVC creation (fail-closed preserved)
- [ ] VolSync mover Job created → NFS volume injected by job webhook
- [ ] System namespace PVC → not processed by webhook or reconciler
- [ ] Two replicas running → leader election works, reconciler runs on one only

---

## What Remains in Kyverno After This

Only one policy: `longhorn-pvc-backup-audit.yaml` (audits PVCs missing backup labels on Longhorn storage). That's a read-only audit policy — no generate, no external HTTP. If that's the only remaining Kyverno use, you could replace it with a Prometheus alert on `kube_persistentvolumeclaim_info` and remove Kyverno entirely from the cluster.

---

## Sync Wave Placement

The operator needs to come up BEFORE apps create PVCs (same requirement as current Kyverno + pvc-plumber stack):

| Wave | Component |
|------|-----------|
| 1 | Longhorn, VolSync, cert-manager (already there) |
| 2 | pvc-plumber operator (replaces current wave-2 pvc-plumber + wave-3/4 Kyverno policies) |
| 6 | Apps (unchanged) |

The webhook TLS certificate needs cert-manager running, which is already wave 0/1.

---

## Source Repo Context

- pvc-plumber source: `github.com/mitchross/pvc-plumber`
- Current image: `ghcr.io/mitchross/pvc-plumber:1.7.0`
- Current role: read-only HTTP service (no k8s RBAC at all, no leader election)
- Language: Go
- Kopia client: already implemented, reuse as-is
- This plan adds: `controller-runtime`, admission webhook handlers, PVC reconciler
