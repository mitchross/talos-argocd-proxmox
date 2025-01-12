# Network Security

## Cloudflare Configuration

### Architecture Overview
```mermaid
graph TD
    subgraph "Internet"
        A[User] --> B[Cloudflare DNS]
        B --> C[Cloudflare Tunnel]
    end

    subgraph "Internal Network"
        C --> D[External Gateway]
        D --> E[K8s Services]
    end

    subgraph "Split DNS"
        F[Internal DNS Query] --> G[CoreDNS]
        G --> H{Domain Type}
        H -->|Internal| I[Local Gateway]
        H -->|External| J[Cloudflare]
    end

    style B fill:#f96,stroke:#333
    style C fill:#9cf,stroke:#333
    style G fill:#9f9,stroke:#333
```

## DNS Configuration

### Cloudflare DNS Records
```mermaid
graph LR
    subgraph "Required Records"
        A[Root Domain] --> B[CNAME to Tunnel]
        C[Wildcard] --> D[CNAME to Tunnel]
    end

    subgraph "Example"
        E[vanillax.me] --> F[uuid.cfargotunnel.com]
        G[*.vanillax.me] --> F
    end
```

### Router DNS Settings
```mermaid
sequenceDiagram
    participant Client
    participant Router
    participant Internal DNS
    participant Cloudflare

    Client->>Router: DNS Query *.vanillax.me
    Router->>Internal DNS: Forward to 192.168.10.50
    Internal DNS->>Router: Return Internal IP
    Router->>Client: Return 192.168.10.50
    
    Note over Client,Router: External clients use Cloudflare
    Client->>Cloudflare: DNS Query *.vanillax.me
    Cloudflare->>Client: Return Cloudflare IP
```

## Cloudflare Tunnel Setup

### Configuration Flow
```mermaid
graph TD
    subgraph "Setup Steps"
        A[Create Tunnel] --> B[Get Credentials]
        B --> C[Store in 1Password]
        C --> D[Create External Secret]
        D --> E[Deploy Tunnel]
    end

    subgraph "Validation"
        E --> F[Check Connection]
        F --> G[Test Routing]
        G --> H[Verify DNS]
    end
```

### Required DNS Configuration

1. **Cloudflare Records**
```yaml
# Root domain
vanillax.me IN CNAME {uuid}.cfargotunnel.com
# Wildcard
*.vanillax.me IN CNAME {uuid}.cfargotunnel.com
```

2. **Router Configuration**
```plaintext
Domain: vanillax.me
DNS Server: 192.168.10.50 (CoreDNS)
Search Domain: vanillax.me
```

## Security Measures

### 1. Cloudflare Security
```mermaid
graph TD
    subgraph "Security Features"
        A[WAF] --> B[Rate Limiting]
        B --> C[Bot Protection]
        C --> D[Zero Trust]
    end

    subgraph "SSL/TLS"
        E[Full SSL] --> F[Always HTTPS]
        F --> G[TLS 1.3]
    end
```

### 2. Internal Security
```mermaid
graph TD
    subgraph "Network Isolation"
        A[Gateway Segmentation] --> B[Internal Routes]
        B --> C[External Routes]
    end

    subgraph "Access Control"
        D[IP Filtering] --> E[Service RBAC]
        E --> F[Network Policies]
    end
```

## Tunnel Management

### 1. Deployment
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: tunnel-credentials
  namespace: cloudflared
stringData:
  credentials.json: |
    {
      "AccountTag": "your-account",
      "TunnelSecret": "your-secret",
      "TunnelID": "your-tunnel-id"
    }
```

### 2. Monitoring
```bash
# Check tunnel status
cloudflared tunnel info <tunnel-id>

# View active connections
cloudflared tunnel route list

# Check logs
kubectl logs -n cloudflared -l app=cloudflared
```

## Troubleshooting

### DNS Resolution
```mermaid
graph TD
    A[DNS Issue] --> B{Internal/External?}
    B -->|Internal| C[Check CoreDNS]
    B -->|External| D[Check Cloudflare]
    C --> E[Verify Local Records]
    D --> F[Check DNS Records]
    E --> G[Test Resolution]
    F --> G
```

### Common Issues

1. **Split DNS Problems**
   - Verify router DNS settings
   - Check CoreDNS configuration
   - Test internal resolution

2. **Tunnel Connectivity**
   - Check tunnel status
   - Verify credentials
   - Review connection logs

3. **SSL/TLS Issues**
   - Verify Cloudflare SSL mode
   - Check certificate validity
   - Review origin server settings 