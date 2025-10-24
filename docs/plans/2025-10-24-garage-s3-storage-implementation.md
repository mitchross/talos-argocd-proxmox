# Garage S3 Storage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy Garage distributed S3-compatible object storage with Web UI to `infrastructure/storage/garage/`

**Architecture:** StatefulSet with 3 replicas using Longhorn PVCs, PostSync init job for cluster layout, separate Web UI deployment with HTTPRoute for management interface

**Tech Stack:** Garage v2.1.0, Longhorn storage, External Secrets Operator (1Password), Gateway API v1, ArgoCD ApplicationSet

**Reference Design:** `docs/plans/2025-10-24-garage-s3-storage-design.md`

**Repository Pattern Skill:** `~/.superpowers/custom-skills/talos-argocd-app-patterns/SKILL.md`

---

## Prerequisites

**Before starting, verify:**
- [ ] 1Password item `s3-garage` exists with fields `rpc_secret` and `admin_token`
- [ ] Longhorn storage class is available: `kubectl get storageclass longhorn`
- [ ] External Secrets Operator is running: `kubectl get pods -n external-secrets`
- [ ] Gateway API installed: `kubectl get gateway gateway-internal -n gateway`

**Commands to verify:**
```bash
# Check Longhorn
kubectl get storageclass longhorn

# Check External Secrets
kubectl get pods -n external-secrets

# Check Gateway
kubectl get gateway gateway-internal -n gateway
```

---

## Task 1: Create Directory Structure

**Goal:** Set up organized directory structure for backend and webui components

**Files:**
- Create: `infrastructure/storage/garage/backend/` (directory)
- Create: `infrastructure/storage/garage/webui/` (directory)

**Step 1: Create directories**

```bash
cd /home/vanillax/programming/k3s-argocd-proxmox
mkdir -p infrastructure/storage/garage/backend
mkdir -p infrastructure/storage/garage/webui
```

**Step 2: Verify structure**

```bash
ls -la infrastructure/storage/garage/
```

Expected output:
```
backend/
webui/
```

**Step 3: Commit**

```bash
git add infrastructure/storage/garage/
git commit -m "feat(garage): create directory structure for backend and webui"
```

---

## Task 2: Backend - Namespace

**Goal:** Create Garage namespace

**Files:**
- Create: `infrastructure/storage/garage/namespace.yaml`

**Step 1: Create namespace.yaml**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: garage
```

**Step 2: Validate YAML**

```bash
kubectl apply --dry-run=client -f infrastructure/storage/garage/namespace.yaml
```

Expected: `namespace/garage created (dry run)`

**Step 3: Commit**

```bash
git add infrastructure/storage/garage/namespace.yaml
git commit -m "feat(garage): add namespace"
```

---

## Task 3: Backend - ExternalSecret

**Goal:** Sync secrets from 1Password (rpc_secret and admin_token)

**Files:**
- Create: `infrastructure/storage/garage/backend/externalsecret.yaml`

**Step 1: Create externalsecret.yaml**

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: garage-secrets
  namespace: garage
spec:
  secretStoreRef:
    kind: ClusterSecretStore
    name: 1password
  target:
    name: garage-secrets
    creationPolicy: Owner
  data:
  - secretKey: rpc-secret
    remoteRef:
      key: s3-garage
      property: rpc_secret
  - secretKey: admin-token
    remoteRef:
      key: s3-garage
      property: admin_token
```

**Step 2: Validate YAML**

```bash
kubectl apply --dry-run=client -f infrastructure/storage/garage/backend/externalsecret.yaml
```

Expected: `externalsecret.external-secrets.io/garage-secrets created (dry run)`

**Step 3: Commit**

```bash
git add infrastructure/storage/garage/backend/externalsecret.yaml
git commit -m "feat(garage): add ExternalSecret for 1Password integration"
```

---

## Task 4: Backend - ConfigMap

**Goal:** Create garage.toml configuration

**Files:**
- Create: `infrastructure/storage/garage/backend/configmap.yaml`

**Step 1: Create configmap.yaml**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: garage-config
  namespace: garage
data:
  garage.toml: |
    metadata_dir = "/mnt/meta"
    data_dir = "/mnt/data"

    db_engine = "lmdb"

    replication_factor = 2

    compression_level = 1

    rpc_bind_addr = "[::]:3901"
    rpc_public_addr = "$(POD_IP):3901"
    rpc_secret_file = "/etc/garage/secrets/rpc-secret"

    [s3_api]
    s3_region = "garage"
    api_bind_addr = "[::]:3900"
    root_domain = ".s3.garage.vanillax.me"

    [s3_web]
    bind_addr = "[::]:3902"
    root_domain = ".web.garage.vanillax.me"

    [admin]
    api_bind_addr = "[::]:3903"
    admin_token_file = "/etc/garage/secrets/admin-token"

    [kubernetes_discovery]
    namespace = "garage"
    service_name = "garage-internal"
    skip_crd = false
```

**Step 2: Validate YAML**

```bash
kubectl apply --dry-run=client -f infrastructure/storage/garage/backend/configmap.yaml
```

Expected: `configmap/garage-config created (dry run)`

**Step 3: Commit**

```bash
git add infrastructure/storage/garage/backend/configmap.yaml
git commit -m "feat(garage): add ConfigMap with garage.toml"
```

---

## Task 5: Backend - StatefulSet

**Goal:** Deploy 3 Garage instances with Longhorn PVCs

**Files:**
- Create: `infrastructure/storage/garage/backend/statefulset.yaml`

**Step 1: Create statefulset.yaml**

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: garage
  namespace: garage
spec:
  serviceName: garage-internal
  replicas: 3
  selector:
    matchLabels:
      app: garage
  template:
    metadata:
      labels:
        app: garage
    spec:
      containers:
      - name: garage
        image: dxflrs/garage:v2.1.0
        imagePullPolicy: IfNotPresent
        ports:
        - name: s3-api
          containerPort: 3900
          protocol: TCP
        - name: rpc
          containerPort: 3901
          protocol: TCP
        - name: s3-web
          containerPort: 3902
          protocol: TCP
        - name: admin-api
          containerPort: 3903
          protocol: TCP
        env:
        - name: POD_IP
          valueFrom:
            fieldRef:
              fieldPath: status.podIP
        volumeMounts:
        - name: meta
          mountPath: /mnt/meta
        - name: data
          mountPath: /mnt/data
        - name: config
          mountPath: /etc/garage.toml
          subPath: garage.toml
        - name: secrets
          mountPath: /etc/garage/secrets
          readOnly: true
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 2000m
            memory: 2Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 3903
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 3903
          initialDelaySeconds: 10
          periodSeconds: 10
          timeoutSeconds: 5
      volumes:
      - name: config
        configMap:
          name: garage-config
      - name: secrets
        secret:
          secretName: garage-secrets
  volumeClaimTemplates:
  - metadata:
      name: meta
    spec:
      accessModes:
      - ReadWriteOnce
      storageClassName: longhorn
      resources:
        requests:
          storage: 3Gi
  - metadata:
      name: data
    spec:
      accessModes:
      - ReadWriteOnce
      storageClassName: longhorn
      resources:
        requests:
          storage: 30Gi
```

**Step 2: Validate YAML**

```bash
kubectl apply --dry-run=client -f infrastructure/storage/garage/backend/statefulset.yaml
```

Expected: `statefulset.apps/garage created (dry run)`

**Step 3: Commit**

```bash
git add infrastructure/storage/garage/backend/statefulset.yaml
git commit -m "feat(garage): add StatefulSet with Longhorn PVCs"
```

---

## Task 6: Backend - Services

**Goal:** Create services for S3 API, Admin API, and internal discovery

**Files:**
- Create: `infrastructure/storage/garage/backend/service-s3.yaml`
- Create: `infrastructure/storage/garage/backend/service-admin.yaml`
- Create: `infrastructure/storage/garage/backend/service-internal.yaml`

**Step 1: Create service-s3.yaml**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: garage-s3
  namespace: garage
spec:
  type: ClusterIP
  selector:
    app: garage
  ports:
  - name: s3-api
    port: 3900
    targetPort: 3900
    protocol: TCP
```

**Step 2: Create service-admin.yaml**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: garage-admin
  namespace: garage
spec:
  type: ClusterIP
  selector:
    app: garage
  ports:
  - name: admin-api
    port: 3903
    targetPort: 3903
    protocol: TCP
```

**Step 3: Create service-internal.yaml**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: garage-internal
  namespace: garage
spec:
  clusterIP: None  # Headless service for StatefulSet
  selector:
    app: garage
  ports:
  - name: rpc
    port: 3901
    targetPort: 3901
    protocol: TCP
```

**Step 4: Validate all services**

```bash
kubectl apply --dry-run=client -f infrastructure/storage/garage/backend/service-s3.yaml
kubectl apply --dry-run=client -f infrastructure/storage/garage/backend/service-admin.yaml
kubectl apply --dry-run=client -f infrastructure/storage/garage/backend/service-internal.yaml
```

Expected: All show `service/garage-* created (dry run)`

**Step 5: Commit**

```bash
git add infrastructure/storage/garage/backend/service-*.yaml
git commit -m "feat(garage): add services for S3, Admin API, and internal discovery"
```

---

## Task 7: Backend - Init Job

**Goal:** PostSync hook to initialize cluster layout

**Files:**
- Create: `infrastructure/storage/garage/backend/init-job.yaml`

**Step 1: Create init-job.yaml**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: garage-init
  namespace: garage
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/sync-wave: "1"
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  backoffLimit: 5
  template:
    metadata:
      labels:
        app: garage-init
    spec:
      restartPolicy: OnFailure
      containers:
      - name: init
        image: dxflrs/garage:v2.1.0
        command: ["/bin/sh"]
        args:
        - -c
        - |
          set -e

          echo "Waiting for all Garage pods to be ready..."
          while [ $(kubectl get pods -n garage -l app=garage --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l) -lt 3 ]; do
            echo "Waiting for 3 running pods..."
            sleep 5
          done

          echo "All pods ready. Configuring cluster layout..."

          # Connect nodes to cluster
          garage -c /etc/garage.toml layout show || true

          # Get node IDs and assign capacity
          garage -c /etc/garage.toml layout assign -z dc1 -c 10G $(garage -c /etc/garage.toml node id -q) || true

          # Apply layout
          garage -c /etc/garage.toml layout apply --version 1 || true

          echo "Cluster initialization complete"
          garage -c /etc/garage.toml status
        volumeMounts:
        - name: config
          mountPath: /etc/garage.toml
          subPath: garage.toml
        - name: secrets
          mountPath: /etc/garage/secrets
          readOnly: true
      volumes:
      - name: config
        configMap:
          name: garage-config
      - name: secrets
        secret:
          secretName: garage-secrets
      serviceAccountName: garage-init
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: garage-init
  namespace: garage
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: garage-init
  namespace: garage
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: garage-init
  namespace: garage
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: garage-init
subjects:
- kind: ServiceAccount
  name: garage-init
  namespace: garage
```

**Step 2: Validate YAML**

```bash
kubectl apply --dry-run=client -f infrastructure/storage/garage/backend/init-job.yaml
```

Expected: Job, ServiceAccount, Role, and RoleBinding created (dry run)

**Step 3: Commit**

```bash
git add infrastructure/storage/garage/backend/init-job.yaml
git commit -m "feat(garage): add PostSync init job for cluster layout"
```

---

## Task 8: Web UI - Deployment

**Goal:** Deploy Garage Web UI frontend

**Files:**
- Create: `infrastructure/storage/garage/webui/deployment.yaml`

**Step 1: Create deployment.yaml**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: garage-webui
  namespace: garage
  annotations:
    argocd.argoproj.io/sync-wave: "2"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: garage-webui
  template:
    metadata:
      labels:
        app: garage-webui
    spec:
      containers:
      - name: webui
        image: khairul169/garage-webui:latest
        imagePullPolicy: IfNotPresent
        ports:
        - name: http
          containerPort: 3909
          protocol: TCP
        env:
        - name: API_BASE_URL
          value: "http://garage-admin.garage.svc.cluster.local:3903"
        - name: S3_ENDPOINT_URL
          value: "http://garage-s3.garage.svc.cluster.local:3900"
        - name: S3_REGION
          value: "garage"
        - name: API_ADMIN_KEY
          valueFrom:
            secretKeyRef:
              name: garage-secrets
              key: admin-token
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /
            port: 3909
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /
            port: 3909
          initialDelaySeconds: 10
          periodSeconds: 10
```

**Step 2: Validate YAML**

```bash
kubectl apply --dry-run=client -f infrastructure/storage/garage/webui/deployment.yaml
```

Expected: `deployment.apps/garage-webui created (dry run)`

**Step 3: Commit**

```bash
git add infrastructure/storage/garage/webui/deployment.yaml
git commit -m "feat(garage): add Web UI deployment"
```

---

## Task 9: Web UI - Service and HTTPRoute

**Goal:** Expose Web UI via service and HTTPRoute at garage.vanillax.me

**Files:**
- Create: `infrastructure/storage/garage/webui/service.yaml`
- Create: `infrastructure/storage/garage/webui/httproute.yaml`

**Step 1: Create service.yaml**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: garage-webui
  namespace: garage
  annotations:
    argocd.argoproj.io/sync-wave: "2"
spec:
  type: ClusterIP
  selector:
    app: garage-webui
  ports:
  - name: http
    port: 3909
    targetPort: http
    protocol: TCP
```

**Step 2: Create httproute.yaml**

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: garage-webui
  namespace: garage
  annotations:
    argocd.argoproj.io/sync-wave: "2"
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: gateway-internal
    namespace: gateway
  hostnames:
  - "garage.vanillax.me"
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - group: ""
      kind: Service
      name: garage-webui
      port: 3909
      weight: 1
```

**Step 3: Validate both files**

```bash
kubectl apply --dry-run=client -f infrastructure/storage/garage/webui/service.yaml
kubectl apply --dry-run=client -f infrastructure/storage/garage/webui/httproute.yaml
```

Expected: Service and HTTPRoute created (dry run)

**Step 4: Commit**

```bash
git add infrastructure/storage/garage/webui/service.yaml infrastructure/storage/garage/webui/httproute.yaml
git commit -m "feat(garage): add Web UI service and HTTPRoute"
```

---

## Task 10: Root - Kustomization

**Goal:** Create kustomization.yaml that lists all resources

**Files:**
- Create: `infrastructure/storage/garage/kustomization.yaml`

**Step 1: Create kustomization.yaml**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: garage

resources:
  # Namespace
  - namespace.yaml

  # Backend
  - backend/externalsecret.yaml
  - backend/configmap.yaml
  - backend/statefulset.yaml
  - backend/service-s3.yaml
  - backend/service-admin.yaml
  - backend/service-internal.yaml
  - backend/init-job.yaml

  # Web UI
  - webui/deployment.yaml
  - webui/service.yaml
  - webui/httproute.yaml
```

**Step 2: Validate with kustomize build**

```bash
kustomize build infrastructure/storage/garage/
```

Expected: All YAML manifests rendered without errors

**Step 3: Validate with kubectl dry-run**

```bash
kustomize build infrastructure/storage/garage/ | kubectl apply --dry-run=client -f -
```

Expected: All resources created (dry run)

**Step 4: Commit**

```bash
git add infrastructure/storage/garage/kustomization.yaml
git commit -m "feat(garage): add kustomization.yaml"
```

---

## Task 11: Documentation - README

**Goal:** Document usage and post-deployment steps

**Files:**
- Create: `infrastructure/storage/garage/README.md`

**Step 1: Create README.md**

```markdown
# Garage S3 Storage

Distributed S3-compatible object storage with Web UI.

## Architecture

- **Backend**: 3 Garage instances (StatefulSet) with replication factor 2
- **Storage**: Longhorn PVCs (3Gi meta + 30Gi data per instance = 90Gi total)
- **Web UI**: Management interface at `https://garage.vanillax.me`
- **S3 API**: Internal cluster access at `garage-s3.garage.svc.cluster.local:3900`

## Access

- **Web UI**: https://garage.vanillax.me
- **S3 Endpoint**: `http://garage-s3.garage.svc.cluster.local:3900`
- **S3 Region**: `garage`

## Post-Deployment

### Verify Cluster Status

```bash
kubectl exec -n garage garage-0 -- garage status
```

Expected: 3 connected nodes with configured layout

### Create S3 Bucket

Via Web UI or CLI:
```bash
kubectl exec -n garage garage-0 -- garage bucket create my-bucket
```

### Create Access Keys

Via Web UI or CLI:
```bash
kubectl exec -n garage garage-0 -- garage key create my-app
```

### Test S3 Access

Configure your S3 client:
- **Endpoint**: `http://garage-s3.garage.svc.cluster.local:3900`
- **Region**: `garage`
- **Access Key**: From Web UI
- **Secret Key**: From Web UI

## Troubleshooting

### Init Job Failed

```bash
kubectl logs -n garage job/garage-init
```

### Pods Not Ready

```bash
kubectl get pods -n garage
kubectl describe pod -n garage garage-0
kubectl logs -n garage garage-0
```

### Web UI Can't Connect

```bash
# Check secret synced
kubectl get externalsecret -n garage garage-secrets

# Check deployment logs
kubectl logs -n garage deployment/garage-webui
```

## Secrets

Managed via External Secrets Operator from 1Password item `s3-garage`:
- `rpc_secret`: RPC authentication between Garage pods
- `admin_token`: Admin API authentication for Web UI
```

**Step 2: Commit**

```bash
git add infrastructure/storage/garage/README.md
git commit -m "docs(garage): add usage and troubleshooting guide"
```

---

## Task 12: Final Validation and Push

**Goal:** Validate complete deployment and push to trigger ArgoCD sync

**Step 1: Run final kustomize validation**

```bash
kustomize build infrastructure/storage/garage/ --enable-helm
```

Expected: Clean output with all manifests

**Step 2: Run kubectl dry-run on complete stack**

```bash
kustomize build infrastructure/storage/garage/ | kubectl apply --dry-run=client -f -
```

Expected: All resources validated successfully

**Step 3: Verify ApplicationSet will discover**

Check path matches pattern:
- Path: `infrastructure/storage/garage/`
- ApplicationSet pattern: `infrastructure/storage/*`
- Match: ✅ YES

**Step 4: Push to Git**

```bash
git push origin main
```

**Step 5: Monitor ArgoCD discovery**

Wait ~3 minutes for ApplicationSet to poll, then:

```bash
# Check Application created
kubectl get application -n argocd | grep garage

# Check Application status
kubectl get application garage -n argocd -o yaml

# Watch sync progress
kubectl get application garage -n argocd -w
```

Expected: Application `garage` created and syncing

**Step 6: Verify pods deploying**

```bash
# Watch pods come up
kubectl get pods -n garage -w
```

Expected sequence:
1. garage-0, garage-1, garage-2 pods start
2. Init job runs (after pods ready)
3. garage-webui pod starts (after init job)

**Step 7: Verify services**

```bash
kubectl get svc -n garage
```

Expected:
- garage-s3 (ClusterIP)
- garage-admin (ClusterIP)
- garage-internal (Headless)
- garage-webui (ClusterIP)

**Step 8: Verify HTTPRoute**

```bash
kubectl get httproute -n garage
```

Expected: garage-webui route to garage.vanillax.me

**Step 9: Check init job completion**

```bash
kubectl logs -n garage job/garage-init
kubectl exec -n garage garage-0 -- garage status
```

Expected: 3 nodes connected with layout applied

**Step 10: Access Web UI**

Navigate to: `https://garage.vanillax.me`

Expected: Garage Web UI loads, shows cluster status

---

## Validation Checklist

After deployment completes, verify:

- [ ] All 3 Garage pods running: `kubectl get pods -n garage`
- [ ] Init job completed: `kubectl get job -n garage garage-init`
- [ ] Cluster layout configured: `kubectl exec -n garage garage-0 -- garage status`
- [ ] Web UI pod running: `kubectl get pods -n garage -l app=garage-webui`
- [ ] HTTPRoute created: `kubectl get httproute -n garage`
- [ ] Web UI accessible: Open `https://garage.vanillax.me`
- [ ] Can create bucket via Web UI
- [ ] Can create access keys via Web UI
- [ ] S3 API responds: Test from cluster pod

## Troubleshooting Commands

```bash
# Check ArgoCD Application
kubectl describe application garage -n argocd

# Check all Garage resources
kubectl get all -n garage

# Check PVCs
kubectl get pvc -n garage

# Check ExternalSecret sync
kubectl describe externalsecret garage-secrets -n garage

# Check secret contents (base64 encoded)
kubectl get secret garage-secrets -n garage -o yaml

# Check init job logs
kubectl logs -n garage job/garage-init

# Check StatefulSet events
kubectl describe statefulset garage -n garage

# Check Web UI logs
kubectl logs -n garage deployment/garage-webui

# Exec into Garage pod
kubectl exec -it -n garage garage-0 -- /bin/sh

# Inside pod - check config
cat /etc/garage.toml

# Inside pod - check garage CLI
garage status
garage layout show
garage bucket list
garage key list
```

## Common Issues

**Issue**: Init job fails with "cannot connect to node"
**Solution**: Check all pods are fully ready, verify RPC secret is correct

**Issue**: Web UI shows "Cannot connect to API"
**Solution**: Verify garage-admin service exists, check admin token in secret

**Issue**: ArgoCD doesn't discover application
**Solution**: Verify path `infrastructure/storage/garage/` matches ApplicationSet pattern

**Issue**: Pods stuck in Pending
**Solution**: Check Longhorn storage class exists and has capacity

---

## Next Steps After Successful Deployment

1. **Create first bucket** via Web UI or CLI
2. **Generate S3 access keys** for applications
3. **Configure application** to use Garage S3:
   - Endpoint: `http://garage-s3.garage.svc.cluster.local:3900`
   - Region: `garage`
   - Access/Secret keys from Web UI
4. **Test S3 operations** (upload, download, list)
5. **Configure Longhorn backups** for PVCs (if desired)
6. **Monitor storage usage** via Web UI

## References

- Design Document: `docs/plans/2025-10-24-garage-s3-storage-design.md`
- Garage Documentation: https://garagehq.deuxfleurs.fr/
- Web UI GitHub: https://github.com/khairul169/garage-webui
