# Cilium CNI on Talos Linux

Guide for deploying Cilium CNI on Talos Linux clusters managed by Omni.

## Overview

Cilium is an eBPF-based networking, observability, and security solution for Kubernetes. On Talos Linux, Cilium provides:

- Networking with an eBPF datapath
- kube-proxy replacement for load balancing
- Gateway API support with ALPN and AppProtocol
- Network policies (L3-L7)
- Hubble for network observability
- Service mesh capabilities without sidecars

## Why Cilium on Talos?

### Performance benefits
- 10-40% better throughput than traditional CNIs
- Lower CPU usage from eBPF kernel integration
- Lower pod-to-pod latency
- No userspace processing for network operations

### Talos integration
- Native support in Talos Linux
- Optimized eBPF programs for minimal kernel
- Automatic cgroup configuration
- Direct API server integration

### Enterprise features
- CNCF Graduated project
- Used in production at scale (Google, AWS, Adobe, etc.)
- Active community and regular updates
- Commercial support available

## Prerequisites

Before installing Cilium:

1. Talos cluster deployed via Omni
2. kube-proxy disabled in cluster configuration
3. kubeconfig downloaded from Omni
4. cilium CLI installed on your workstation

## Disable kube-proxy (required)

**Critical:** You MUST disable kube-proxy before creating the cluster.

### Via Omni UI

When creating a cluster, add this **Cluster Config Patch**:

```yaml
cluster:
  proxy:
    disabled: true
```

### Via machine config

If patching machines directly:

```yaml
machine:
  features:
    kubernetesTalosAPIAccess:
      enabled: true
      allowedRoles:
      - os:reader
      allowedKubernetesNamespaces:
      - kube-system
```

**Important:** Do this **before** cluster creation. You cannot easily disable kube-proxy afterward.

## Install Cilium CLI

### Linux

```bash
CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
CLI_ARCH=amd64
curl -L --fail --remote-name-all https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-${CLI_ARCH}.tar.gz{,.sha256sum}
sha256sum --check cilium-linux-${CLI_ARCH}.tar.gz.sha256sum
sudo tar xzvfC cilium-linux-${CLI_ARCH}.tar.gz /usr/local/bin
rm cilium-linux-${CLI_ARCH}.tar.gz{,.sha256sum}
```

### macOS

```bash
brew install cilium-cli
```

### Windows

```powershell
curl -LO https://github.com/cilium/cilium-cli/releases/latest/download/cilium-windows-amd64.tar.gz
tar -xvf cilium-windows-amd64.tar.gz
# Move cilium.exe to your PATH
```

Verify:
```bash
cilium version --client
```

## Installation options

### Option 1: Basic Cilium (no Gateway API)

Simple installation without Gateway API support:

```bash
cilium install \
    --version 1.20.0 \
    --set cluster.name=talos-prod-cluster \
    --set ipam.mode=kubernetes \
    --set kubeProxyReplacement=true \
    --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
    --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
    --set cgroup.autoMount.enabled=false \
    --set cgroup.hostRoot=/sys/fs/cgroup \
    --set k8sServiceHost=localhost \
    --set k8sServicePort=7445
```

### Option 2: Cilium with Gateway API (recommended)

Full installation with Gateway API support:

```bash
# First, install Gateway API CRDs
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml

# Then install Cilium
cilium install \
    --version 1.20.0 \
    --set cluster.name=talos-prod-cluster \
    --set ipam.mode=kubernetes \
    --set kubeProxyReplacement=true \
    --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
    --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
    --set cgroup.autoMount.enabled=false \
    --set cgroup.hostRoot=/sys/fs/cgroup \
    --set k8sServiceHost=localhost \
    --set k8sServicePort=7445 \
    --set gatewayAPI.enabled=true \
    --set gatewayAPI.enableAlpn=true \
    --set gatewayAPI.enableAppProtocol=true
```

### Option 3: Cilium with Hubble (full observability)

Installation with Hubble for network observability:

```bash
# Install Gateway API CRDs
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml

# Install Cilium with Hubble
cilium install \
    --version 1.20.0 \
    --set cluster.name=talos-prod-cluster \
    --set ipam.mode=kubernetes \
    --set kubeProxyReplacement=true \
    --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
    --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
    --set cgroup.autoMount.enabled=false \
    --set cgroup.hostRoot=/sys/fs/cgroup \
    --set k8sServiceHost=localhost \
    --set k8sServicePort=7445 \
    --set gatewayAPI.enabled=true \
    --set gatewayAPI.enableAlpn=true \
    --set gatewayAPI.enableAppProtocol=true \
    --set hubble.relay.enabled=true \
    --set hubble.ui.enabled=true
```

## Configuration parameters explained

### Required for Talos

```bash
--set k8sServiceHost=localhost
--set k8sServicePort=7445
```
Talos API server runs on localhost:7445 (not the standard 6443).

```bash
--set cgroup.autoMount.enabled=false
--set cgroup.hostRoot=/sys/fs/cgroup
```
Talos manages cgroups itself, so Cilium must use the existing mount.

```bash
--set securityContext.capabilities.ciliumAgent="{...}"
--set securityContext.capabilities.cleanCiliumState="{...}"
```
Linux capabilities Cilium needs on Talos's minimal kernel.

### kube-proxy replacement

```bash
--set kubeProxyReplacement=true
```
Use eBPF-based load balancing instead of iptables.

### IPAM configuration

```bash
--set ipam.mode=kubernetes
```
Use Kubernetes for IP address management (the standard mode).

### Gateway API features

```bash
--set gatewayAPI.enabled=true
--set gatewayAPI.enableAlpn=true
--set gatewayAPI.enableAppProtocol=true
```
Turn on Gateway API with ALPN (Application-Layer Protocol Negotiation) and AppProtocol support.

## Verify installation

### Check Cilium status

```bash
cilium status --wait
```

Expected output:
```
    /¯¯\
 /¯¯\__/¯¯\    Cilium:             OK
 \__/¯¯\__/    Operator:           OK
 /¯¯\__/¯¯\    Envoy DaemonSet:    OK
 \__/¯¯\__/    Hubble Relay:       disabled
    \__/       ClusterMesh:        disabled

DaemonSet              cilium             Desired: 3, Ready: 3/3, Available: 3/3
Deployment             cilium-operator    Desired: 2, Ready: 2/2, Available: 2/2
Containers:            cilium             Running: 3
                       cilium-operator    Running: 2
Cluster Pods:          5/5 managed by Cilium
```

### Check node status

```bash
kubectl get nodes
```

All nodes should show **Ready** status.

### Check Cilium pods

```bash
kubectl get pods -n kube-system -l k8s-app=cilium
```

Should show one Cilium pod per node, all Running.

### Run connectivity test

```bash
cilium connectivity test
```

This runs a suite of tests. All tests should pass.

## Gateway API setup

### Create Gateway class

```bash
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: cilium
spec:
  controllerName: io.cilium/gateway-controller
EOF
```

### Create Gateway

```bash
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: cilium-gateway
  namespace: default
spec:
  gatewayClassName: cilium
  listeners:
  - name: http
    protocol: HTTP
    port: 80
    allowedRoutes:
      namespaces:
        from: All
  - name: https
    protocol: HTTPS
    port: 443
    allowedRoutes:
      namespaces:
        from: All
    tls:
      mode: Terminate
      certificateRefs:
      - kind: Secret
        name: gateway-tls
EOF
```

### Create HTTPRoute

```bash
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: example-route
  namespace: default
spec:
  parentRefs:
  - name: cilium-gateway
  hostnames:
  - "example.com"
  - "www.example.com"
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /api
    backendRefs:
    - name: api-service
      port: 8080
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: web-service
      port: 80
EOF
```

### TLS certificate for Gateway

```bash
# Create TLS secret
kubectl create secret tls gateway-tls \
  --cert=path/to/cert.crt \
  --key=path/to/cert.key

# Or use cert-manager
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: gateway-cert
  namespace: default
spec:
  secretName: gateway-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
  - example.com
  - www.example.com
EOF
```

## Hubble observability

### Enable Hubble

```bash
cilium hubble enable --ui
```

### Access Hubble UI

```bash
cilium hubble ui
```

Opens browser to http://localhost:12000

### Hubble CLI

Install Hubble CLI:

```bash
# Download latest Hubble CLI
HUBBLE_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/hubble/master/stable.txt)
HUBBLE_ARCH=amd64
curl -L --fail --remote-name-all https://github.com/cilium/hubble/releases/download/$HUBBLE_VERSION/hubble-linux-${HUBBLE_ARCH}.tar.gz{,.sha256sum}
sha256sum --check hubble-linux-${HUBBLE_ARCH}.tar.gz.sha256sum
sudo tar xzvfC hubble-linux-${HUBBLE_ARCH}.tar.gz /usr/local/bin
rm hubble-linux-${HUBBLE_ARCH}.tar.gz{,.sha256sum}
```

Use Hubble CLI:

```bash
# Port-forward Hubble relay
cilium hubble port-forward &

# Watch flows
hubble observe

# Watch flows from specific pod
hubble observe --pod my-pod

# Watch flows to specific endpoint
hubble observe --to-pod my-pod

# Filter by verdict (dropped packets)
hubble observe --verdict DROPPED
```

## Network policies

### Kubernetes network policy

Cilium supports standard Kubernetes NetworkPolicy:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-backend
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    ports:
    - protocol: TCP
      port: 8080
```

### Cilium network policy (L3-L4)

Cilium-specific policies add features beyond the standard resource:

```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: l3-l4-policy
  namespace: production
spec:
  endpointSelector:
    matchLabels:
      app: backend
  ingress:
  - fromEndpoints:
    - matchLabels:
        app: frontend
    toPorts:
    - ports:
      - port: "8080"
        protocol: TCP
```

### Cilium L7 policy (HTTP)

Enforce HTTP-level rules:

```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: l7-http-policy
  namespace: production
spec:
  endpointSelector:
    matchLabels:
      app: api
  ingress:
  - fromEndpoints:
    - matchLabels:
        app: frontend
    toPorts:
    - ports:
      - port: "8080"
        protocol: TCP
      rules:
        http:
        - method: "GET"
          path: "/api/v1/.*"
        - method: "POST"
          path: "/api/v1/users"
```

### Cluster-wide policy

Apply policy across all namespaces:

```yaml
apiVersion: cilium.io/v2
kind: CiliumClusterwideNetworkPolicy
metadata:
  name: deny-external-egress
spec:
  endpointSelector:
    matchLabels:
      io.kubernetes.pod.namespace: production
  egress:
  - toEntities:
    - cluster
    - kube-apiserver
  - toEndpoints:
    - matchLabels:
        io.kubernetes.pod.namespace: kube-system
  - toFQDNs:
    - matchPattern: "*.internal.company.com"
```

### DNS-based policy

Allow egress to specific domains:

```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: allow-external-api
  namespace: production
spec:
  endpointSelector:
    matchLabels:
      app: backend
  egress:
  - toFQDNs:
    - matchPattern: "api.stripe.com"
    - matchPattern: "*.amazonaws.com"
  - toEndpoints:
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: kube-system
        k8s:k8s-app: kube-dns
    toPorts:
    - ports:
      - port: "53"
        protocol: UDP
      rules:
        dns:
        - matchPattern: "*"
```

## Load balancing

### LoadBalancer IP pool

Define IP pool for LoadBalancer services:

```bash
kubectl apply -f - <<EOF
apiVersion: cilium.io/v2alpha1
kind: CiliumLoadBalancerIPPool
metadata:
  name: pool-1
spec:
  cidrs:
  - cidr: 192.168.1.200/29
EOF
```

### LoadBalancer Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  type: LoadBalancer
  selector:
    app: my-app
  ports:
  - port: 80
    targetPort: 8080
```

Cilium will assign an IP from the pool automatically.

### Advanced load balancing

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-service
  annotations:
    io.cilium/lb-ipam-ips: 192.168.1.201  # Specific IP
spec:
  type: LoadBalancer
  externalTrafficPolicy: Local  # Preserve source IP
  selector:
    app: my-app
  ports:
  - port: 80
    targetPort: 8080
```

## Performance tuning

### Enable BBR congestion control

```bash
cilium config set enable-bbr true
```

### Enable bandwidth manager

```bash
cilium config set enable-bandwidth-manager true
```

### Native routing mode

For best performance with L2-adjacent nodes:

```bash
cilium config set tunnel disabled
cilium config set ipv4-native-routing-cidr <pod-cidr>
```

### eBPF host routing

```bash
cilium config set enable-host-routing true
```

## Monitoring and metrics

### Prometheus integration

Cilium exports Prometheus metrics:

```bash
# Enable Prometheus
cilium hubble enable --prometheus

# Metrics available at: http://<cilium-agent>:9962/metrics
```

### Grafana dashboards

Import official Cilium dashboards:
- Cilium Metrics: Dashboard ID 16611
- Hubble Metrics: Dashboard ID 16612
- Cilium Operator: Dashboard ID 16612

## Upgrading Cilium

### Check current version

```bash
cilium version
```

### Upgrade Cilium

```bash
# Upgrade to specific version (must match chart version in infrastructure/networking/cilium/kustomization.yaml)
cilium upgrade --version 1.20.0

# Or latest
cilium upgrade

# Verify upgrade
cilium status
```

## Troubleshooting

### Cilium pods not starting

Check logs:
```bash
kubectl logs -n kube-system -l k8s-app=cilium
```

Common issues:
- Wrong k8sServiceHost or k8sServicePort (must be localhost:7445)
- Missing capabilities in securityContext
- Incorrect cgroup configuration

### Connectivity issues

```bash
# Run connectivity test
cilium connectivity test

# Check specific node
cilium status --node <node-name>

# Check eBPF maps
cilium bpf lb list
cilium bpf endpoint list
```

### Gateway not working

```bash
# Check Gateway status
kubectl get gateway -A
kubectl describe gateway <gateway-name>

# Check HTTPRoute status
kubectl get httproute -A
kubectl describe httproute <route-name>

# Check Envoy pods
kubectl get pods -n kube-system -l k8s-app=cilium-envoy
```

### Network policy debugging

```bash
# Check policy status
cilium policy get

# Check if pod is affected by policy
cilium endpoint list

# Watch Hubble for dropped packets
hubble observe --verdict DROPPED --follow
```

### Performance issues

```bash
# Check eBPF program stats
cilium bpf metrics list

# Monitor CPU usage
kubectl top pods -n kube-system -l k8s-app=cilium

# Check for errors
cilium status --all-nodes
```

## Advanced features

### Cluster mesh (multi-cluster)

Connect multiple Kubernetes clusters:

```bash
# Enable cluster mesh on both clusters
cilium clustermesh enable

# Connect clusters
cilium clustermesh connect --context cluster1 --destination-context cluster2
```

### Transparent encryption

Enable WireGuard encryption:

```bash
cilium config set encryption-type wireguard
cilium config set enable-wireguard true
```

### Service mesh

Enable service mesh features:

> **Note:** `ingressController.enabled=true` is an optional upstream Cilium feature shown here for completeness. **This cluster does NOT use it.** We use Cilium Gateway API exclusively, not Ingress. Do not enable the ingress controller thinking it's required.

```bash
cilium install \
  --version 1.20.0 \
  --set cluster.name=talos-prod-cluster \
  --set kubeProxyReplacement=true \
  --set ingressController.enabled=true \
  --set envoy.enabled=true
```

### BGP support

Advertise service IPs via BGP:

```bash
kubectl apply -f - <<EOF
apiVersion: cilium.io/v2alpha1
kind: CiliumBGPPeeringPolicy
metadata:
  name: bgp-peering
spec:
  nodeSelector:
    matchLabels:
      bgp: "true"
  virtualRouters:
  - localASN: 64512
    exportPodCIDR: true
    neighbors:
    - peerAddress: 192.168.1.1/32
      peerASN: 64512
EOF
```

## Best practices

1. Always disable kube-proxy. Kube-proxy replacement requires it.
2. Use Gateway API. It has more features than Ingress.
3. Enable Hubble. It helps with debugging and observability.
4. Implement network policies. Start with default deny.
5. Monitor metrics with Prometheus and Grafana.
6. Run `cilium connectivity test` regularly.
7. Upgrade Cilium regularly for features and fixes.
8. Use L7 policies for fine-grained application control.

## Resources

- [Cilium Documentation](https://docs.cilium.io/)
- [Talos + Cilium Guide](https://www.talos.dev/v1.13/kubernetes-guides/network/deploying-cilium/)
- [Gateway API Docs](https://gateway-api.sigs.k8s.io/)
- [Hubble Documentation](https://docs.cilium.io/en/stable/gettingstarted/hubble/)
- [Cilium Slack](https://cilium.io/slack)
- [Cilium GitHub](https://github.com/cilium/cilium)

## Example configurations

See the live [cluster-template/](../cluster-template/) and the cluster's Cilium config in [`infrastructure/networking/cilium/`](../../infrastructure/networking/cilium/) for a working configuration with Cilium, Gateway API, and all recommended settings.
