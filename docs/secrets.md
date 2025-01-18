# Secrets Management

## Bootstrap Order

The secrets management infrastructure is deployed in a specific order using ArgoCD sync waves:

```mermaid
graph TD
    subgraph "Deployment Order"
        A[Wave 0: 1Password Connect] --> B[Wave 1: External Secrets]
        B --> C[Wave 2: Secret Consumers]
    end

    subgraph "Secret Flow"
        D[1Password Vault] --> E[1Password Connect]
        E --> F[External Secrets Operator]
        F --> G[Kubernetes Secrets]
        G --> H[Applications]
    end

    style A fill:#f9f,stroke:#333
    style B fill:#9cf,stroke:#333
    style C fill:#9f9,stroke:#333
```

## Components

### 1. 1Password Connect (Wave 0)
- First component to be deployed
- Secure connection to 1Password vault
- Token-based authentication
- **Prerequisites**:
  - 1Password credentials secret
  - Connect token
- **Required by**: All other components

### 2. External Secrets Operator (Wave 1)
- Deploys after 1Password Connect
- Syncs secrets from 1Password to Kubernetes
- Handles secret versioning
- **Prerequisites**:
  - 1Password Connect operational
  - Connect token secret
- **Required by**: Cert Manager, Cloudflared

### 3. Secret Consumers (Wave 2+)
Components that depend on secrets:
- Cert Manager (Wave 2)
  - DNS validation credentials
- Cloudflared (Wave 3)
  - Tunnel credentials
  - API tokens

## Manual Setup Steps

These steps must be completed before ArgoCD can manage the infrastructure:

1. **Create Required Namespaces**
```bash
kubectl create namespace 1passwordconnect
kubectl create namespace external-secrets
```

2. **Deploy 1Password Connect Credentials**
```bash
# Apply the credentials
kubectl create secret generic 1password-credentials \
  --from-file=1password-credentials.json=credentials.base64 \
  --namespace 1passwordconnect

# Apply the token
kubectl create secret generic 1password-operator-token \
  --from-literal=token=$CONNECT_TOKEN \
  --namespace 1passwordconnect
```

## Secret Management

### 1. Creating External Secrets
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: app-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: 1password
  target:
    name: app-secrets
    creationPolicy: Owner
  data:
    - secretKey: API_KEY
      remoteRef:
        key: api-key
        property: value
```

### 2. Using Secrets in Applications
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  template:
    spec:
      containers:
        - name: app
          env:
            - name: API_KEY
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: API_KEY
```

## Secret Categories

1. **Infrastructure Secrets**
   - Cloudflare API tokens
   - Database credentials
   - Storage access keys

2. **Application Secrets**
   - API keys
   - Service credentials
   - OAuth tokens

3. **TLS Certificates**
   - Internal certificates
   - External certificates
   - Cloudflare Origin certificates

## Best Practices

1. **Secret Rotation**
   - Enable automatic rotation where possible
   - Set appropriate refresh intervals
   - Monitor secret expiration

2. **Access Control**
   - Use namespace-specific secrets
   - Implement RBAC for secret access
   - Audit secret access regularly

3. **Secret Organization**
   - Use consistent naming conventions
   - Group related secrets
   - Document secret purpose and usage

## Troubleshooting

### Common Issues

1. **Secret Sync Issues**
```bash
# Check External Secrets status
kubectl get externalsecret -A
kubectl describe externalsecret <name>

# Check 1Password Connect
kubectl logs -n external-secrets -l app=1password-connect
```

2. **Secret Access Issues**
```bash
# Verify secret existence
kubectl get secret <name> -n <namespace>

# Check secret permissions
kubectl auth can-i get secret <name> -n <namespace>
```

3. **1Password Connection Issues**
```bash
# Test 1Password Connect
kubectl port-forward -n external-secrets svc/1password-connect 8080:8080
curl -v http://localhost:8080/health

# Check credentials
kubectl get secret 1password-credentials -n external-secrets
```

## Security Considerations

1. **Secret Storage**
   - Use encrypted storage
   - Enable etcd encryption
   - Regular backup of secrets

2. **Network Security**
   - Restrict 1Password Connect access
   - Use internal network for secret sync
   - Enable TLS for all connections

3. **Monitoring**
   - Alert on sync failures
   - Monitor secret usage
   - Track secret changes 