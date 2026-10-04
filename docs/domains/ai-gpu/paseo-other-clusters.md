# Run Paseo on another cluster

**Purpose:** run the public `paseo-dev` image in another homelab, with Docker Compose or plain Kubernetes manifests.
**Scope:** nothing from this cluster is needed: no Argo CD, 1Password, Longhorn, or Kopiur.
**This cluster's setup:** [Paseo: coding agents in the cluster](paseo.md).
**Image source:** [homelab-images/images/paseo-dev](https://github.com/mitchross/homelab-images/tree/main/images/paseo-dev) lists what is installed and how it is built.

## Use a coding agent

Paste this prompt into Claude Code, Codex, or Pi, inside your own cluster repo:

```text
Read https://raw.githubusercontent.com/mitchross/talos-argocd-proxmox/main/docs/domains/ai-gpu/paseo-other-clusters.md.
Deploy Paseo to my Kubernetes cluster with the manifests on that page.
Before you change anything, ask me for: hostname, Gateway API or Ingress, StorageClass, and my LLM server URL.
Keep secrets out of Git. Create the password Secret with kubectl and show me the command first.
```

Review every command the agent proposes before it runs.

## What you need

- An `amd64` machine. The image has no `arm64` build.
- Docker, or a Kubernetes cluster with a default `ReadWriteOnce` StorageClass.
- For Kubernetes: an HTTPS Gateway (Gateway API) or Ingress controller that passes WebSockets.
- A DNS name for Paseo, for example `paseo.example.com`.

The image is public at `ghcr.io/mitchross/paseo-dev`. Pin a digest; the `main` tag moves with each build:

```bash
docker buildx imagetools inspect ghcr.io/mitchross/paseo-dev:main | grep Digest
```

## Option A: Docker Compose

1. Generate a password: `openssl rand -base64 32`.
2. Save this as `compose.yaml`:

    ```yaml
    services:
      paseo:
        image: ghcr.io/mitchross/paseo-dev:main@sha256:<digest>
        restart: unless-stopped
        ports:
          - "6767:6767"
        environment:
          PASEO_PASSWORD: "<your password>"
          PASEO_HOSTNAMES: "paseo.example.com"
        volumes:
          - paseo-home:/home/paseo
          - paseo-workspace:/workspace
    volumes:
      paseo-home:
      paseo-workspace:
    ```

3. Run `docker compose up -d`.
4. Open `http://<server-ip>:6767`.

Named volumes take the image's `1000:1000` ownership. For bind mounts, run `sudo chown -R 1000:1000` on both directories first.
The container refuses to start without `PASEO_PASSWORD`.

## Option B: Kubernetes

Create a folder with these six files.

`kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: paseo
resources:
  - namespace.yaml
  - pvc.yaml
  - deployment.yaml
  - service.yaml
  - route.yaml
```

`namespace.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: paseo
  labels:
    pod-security.kubernetes.io/enforce: restricted
```

`pvc.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: paseo-home
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: paseo-workspace
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 50Gi
```

`deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paseo
spec:
  replicas: 1
  # RWO volumes: a rolling update would start a second pod that cannot attach them.
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: paseo
  template:
    metadata:
      labels:
        app.kubernetes.io/name: paseo
    spec:
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 60
      nodeSelector:
        kubernetes.io/arch: amd64
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        runAsNonRoot: true
        fsGroup: 1000
        fsGroupChangePolicy: OnRootMismatch
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: paseo
          image: ghcr.io/mitchross/paseo-dev:main@sha256:<digest>
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: [ALL]
          ports:
            - name: http
              containerPort: 6767
          env:
            - name: PASEO_HOSTNAMES
              value: paseo.example.com
            - name: PASEO_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: paseo
                  key: PASEO_PASSWORD
            # TLS ends at your proxy; trust its X-Forwarded-Proto so the web page auto-connects.
            - name: PASEO_TRUSTED_PROXIES
              value: loopback,uniquelocal
            - name: PASEO_RELAY_ENABLED
              value: "false"
          resources:
            requests:
              cpu: "1"
              memory: 2Gi
            limits:
              memory: 12Gi
          # No liveness probe: a busy build must not trigger a restart that kills the agents.
          startupProbe:
            httpGet:
              path: /api/health
              port: http
            periodSeconds: 5
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /api/health
              port: http
            periodSeconds: 10
          volumeMounts:
            - name: home
              mountPath: /home/paseo
            - name: workspace
              mountPath: /workspace
            - name: shm
              mountPath: /dev/shm
      volumes:
        - name: home
          persistentVolumeClaim:
            claimName: paseo-home
        - name: workspace
          persistentVolumeClaim:
            claimName: paseo-workspace
        - name: shm
          emptyDir:
            medium: Memory
            sizeLimit: 1Gi
```

`service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: paseo
spec:
  selector:
    app.kubernetes.io/name: paseo
  ports:
    - name: http
      port: 6767
      targetPort: http
```

`route.yaml` for Gateway API. Set `parentRefs` to your Gateway and its HTTPS listener:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: paseo
spec:
  parentRefs:
    - name: my-gateway
      namespace: gateway
      sectionName: https
  hostnames:
    - paseo.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: paseo
          port: 6767
```

Or `route.yaml` for ingress-nginx, which closes idle WebSockets after 60 s unless you raise the timeouts:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: paseo
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
spec:
  ingressClassName: nginx
  tls:
    - hosts: [paseo.example.com]
      secretName: paseo-tls
  rules:
    - host: paseo.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: paseo
                port:
                  name: http
```

### Deploy

1. Replace `paseo.example.com` and `<digest>` in the files.
2. Create the namespace and the password Secret. Keep the password out of Git:

    ```bash
    kubectl apply -f namespace.yaml
    PASEO_PASSWORD="$(openssl rand -base64 32)"
    kubectl -n paseo create secret generic paseo --from-literal=PASEO_PASSWORD="$PASEO_PASSWORD"
    echo "$PASEO_PASSWORD"
    ```

3. Save the printed password in your password manager.
4. Deploy and wait. The first pull is large:

    ```bash
    kubectl apply -k .
    kubectl -n paseo rollout status deployment/paseo --timeout=10m
    ```

### Check

```bash
kubectl -n paseo get pod,pvc
curl -s -o /dev/null -w '%{http_code}\n' https://paseo.example.com/api/status
curl -s https://paseo.example.com/ | grep -o '"useTls":[a-z]*'
```

| Result | Meaning |
|---|---|
| Pod `1/1 Running`, both PVCs `Bound` | Ready |
| `401` | The API needs the password, as it should |
| `"useTls":true` | The browser connects by itself |
| `"useTls":false` | Add your proxy's address range to `PASEO_TRUSTED_PROXIES` |
| `403` | The hostname is missing from `PASEO_HOSTNAMES` |

## Connect and log in

Follow steps 1–3 of [Paseo: coding agents in the cluster](paseo.md): connect, open a terminal, and log in to GitHub, Claude Code, and Codex once.
Use your own hostname and password. Logins stay on the home volume.

## Pi with your own LLM server

The image seeds Pi with this cluster's providers on first start. They do not work elsewhere.
Point Pi at your own OpenAI-compatible server (vLLM, llama.cpp, Ollama, LiteLLM):

```json
{
  "providers": {
    "my-llm": {
      "baseUrl": "http://my-llm.example.svc.cluster.local:8000/v1",
      "api": "openai-completions",
      "apiKey": "$MY_LLM_API_KEY",
      "models": [
        { "id": "my-model", "name": "My local model", "contextWindow": 32768, "maxTokens": 8192 }
      ]
    }
  }
}
```

1. Save it as `~/.pi/agent/models.json` in the Paseo terminal, or mount it read-only from a ConfigMap at `/home/paseo/.pi/agent/models.json`.
2. Supply `MY_LLM_API_KEY` as an env var from a Secret. Use any non-empty value if your server has no key.
3. In Pi, run `/model`, pick yours, and press `Ctrl+S` to make it the default.
4. Test: `pi -p "Reply with exactly: OK"`.

Write `apiKey` as `"$MY_LLM_API_KEY"`, with the `$`. Pi sends a bare name as the literal key.

## Security

Paseo gives anyone with the password a shell with your logins. Treat it like SSH.

- Use a long random password. Paseo does not rate-limit failed logins.
- Prefer an identity gate in front, such as Cloudflare Access or a VPN. A bare password on a public hostname is the weakest option.
- Use a fine-grained GitHub token for the repos agents need: `gh auth login --with-token`.
- Protect your GitOps branch. A pod token that can push there can deploy anything.
- Set a monthly spend limit at every paid model provider.

## Update, back up, roll back

- **Update:** change the digest and apply again. The volumes stay.
- **Back up:** snapshot both PVCs with your storage tool or Velero. `paseo-home` holds the logins.
- **Roll back:** put the old digest back and apply again.

**Warning:** `kubectl delete namespace paseo` deletes both PVCs with your logins and code.
