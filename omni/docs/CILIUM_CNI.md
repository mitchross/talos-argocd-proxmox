# Cilium CNI on Talos Linux

Complete guide for deploying Cilium CNI on Talos Linux clusters managed by Omni.

## Overview

Cilium is an eBPF-based networking, observability, and security solution for Kubernetes. On Talos Linux, Cilium provides:

- **High performance** networking with eBPF datapath
- **kube-proxy replacement** for better load balancing
- **Gateway API** support with ALPN and AppProtocol
- **Advanced network policies** (L3-L7)
- **Hubble** for network observability
- **Service mesh** capabilities without sidecars

## Why Cilium on Talos?

### Performance Benefits
- **10-40% better throughput** compared to traditional CNIs
- **Lower CPU usage** thanks to eBPF kernel integration
- **Reduced latency** for pod-to-pod communication
- **No userspace processing** for network operations

### Talos Integration
- Native support in Talos Linux
- Optimized eBPF programs for minimal kernel
- Automatic cgroup configuration
- Direct API server integration

### Enterprise Features
- CNCF Graduated project
- Production-proven at scale (Google, AWS, Adobe, etc.)
- Active community and regular updates
- Commercial support available

## Prerequisites

Before installing Cilium:

1. **Talos cluster deployed** via Omni
2. **kube-proxy disabled** in cluster configuration
3. **kubeconfig downloaded** from Omni
4. **cilium CLI installed** on your workstation

## Disable kube-proxy (Required)

**Critical**: You MUST disable kube-proxy before creating the cluster.

### Via Omni UI

When creating a cluster, add this **Cluster Config Patch**:

```yaml
cluster:
  proxy:
    disabled: true
```

### Via Machine Config

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

**Important**: This must be done **before** cluster creation. You cannot easily disable kube-proxy after cluster creation.

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

## Installation Options

### Option 1: Basic Cilium (No Gateway API)

Simple installation without Gateway API support:

```bash
cilium install \
    --set ipam.mode=kubernetes \
    --set kubeProxyReplacement=true \
    --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
    --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
    --set cgroup.autoMount.enabled=false \
    --set cgroup.hostRoot=/sys/fs/cgroup \
    --set k8sServiceHost=localhost \
    --set k8sServicePort=7445
```

### Option 2: Cilium with Gateway API (Recommended)

Full installation with Gateway API support:

```bash
# First, install Gateway API CRDs
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.0.0/standard-install.yaml

# Then install Cilium
cilium install \
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

### Option 3: Cilium with Hubble (Full Observability)

Installation with Hubble for network observability:

```bash
# Install Gateway API CRDs
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.0.0/standard-install.yaml

# Install Cilium with Hubble
cilium install \
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

## Configuration Parameters Explained

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
Talos manages cgroups itself; Cilium must use existing mount.

```bash
--set securityContext.capabilities.ciliumAgent="{...}"
--set securityContext.capabilities.cleanCiliumState="{...}"
```
Required Linux capabilities for Cilium to function on Talos's minimal kernel.

### kube-proxy Replacement

```bash
--set kubeProxyReplacement=true
```
Enable eBPF-based load balancing instead of iptables.

### IPAM Configuration

```bash
--set ipam.mode=kubernetes
```
Use Kubernetes for IP address management (standard mode).

### Gateway API Features

```bash
--set gatewayAPI.enabled=true
--set gatewayAPI.enableAlpn=true
--set gatewayAPI.enableAppProtocol=true
```
Enable Gateway API with ALPN (Application-Layer Protocol Negotiation) and AppProtocol support.

## Verify Installation

### Check Cilium Status

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

### Check Node Status

```bash
kubectl get nodes
```

All nodes should show **Ready** status.

### Check Cilium Pods

```bash
kubectl get pods -n kube-system -l k8s-app=cilium
```

Should show one Cilium pod per node, all Running.

### Run Connectivity Test

```bash
cilium connectivity test
```

This runs a comprehensive suite of tests. Should complete with all tests passing.

## Gateway API Setup

### Create Gateway Class

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

### TLS Certificate for Gateway

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

## Hubble Observability

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

## Network Policies

### Kubernetes Network Policy

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

### Cilium Network Policy (L3-L4)

More powerful with Cilium-specific features:

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

### Cilium L7 Policy (HTTP)

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

### Cluster-Wide Policy

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

### DNS-based Policy

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

## Load Balancing

### LoadBalancer IP Pool

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

### Advanced Load Balancing

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

## Performance Tuning

### Enable BBR Congestion Control

```bash
cilium config set enable-bbr true
```

### Enable Bandwidth Manager

```bash
cilium config set enable-bandwidth-manager true
```

### Native Routing Mode

For best performance with L2-adjacent nodes:

```bash
cilium config set tunnel disabled
cilium config set ipv4-native-routing-cidr <pod-cidr>
```

### eBPF Host Routing

```bash
cilium config set enable-host-routing true
```

## Monitoring and Metrics

### Prometheus Integration

Cilium exports Prometheus metrics:

```bash
# Enable Prometheus
cilium hubble enable --prometheus

# Metrics available at: http://<cilium-agent>:9962/metrics
```

### Grafana Dashboards

Import official Cilium dashboards:
- **Cilium Metrics**: Dashboard ID 16611
- **Hubble Metrics**: Dashboard ID 16612
- **Cilium Operator**: Dashboard ID 16612

## Upgrading Cilium

### Check Current Version

```bash
cilium version
```

### Upgrade Cilium

```bash
# Upgrade to specific version
cilium upgrade --version 1.15.0

# Or latest
cilium upgrade

# Verify upgrade
cilium status
```

## Troubleshooting

### Cilium Pods Not Starting

Check logs:
```bash
kubectl logs -n kube-system -l k8s-app=cilium
```

Common issues:
- Wrong k8sServiceHost/Port (must be localhost:7445)
- Missing capabilities in securityContext
- Incorrect cgroup configuration

### Connectivity Issues

```bash
# Run connectivity test
cilium connectivity test

# Check specific node
cilium status --node <node-name>

# Check eBPF maps
cilium bpf lb list
cilium bpf endpoint list
```

### Gateway Not Working

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

### Network Policy Debugging

```bash
# Check policy status
cilium policy get

# Check if pod is affected by policy
cilium endpoint list

# Watch Hubble for dropped packets
hubble observe --verdict DROPPED --follow
```

### Performance Issues

```bash
# Check eBPF program stats
cilium bpf metrics list

# Monitor CPU usage
kubectl top pods -n kube-system -l k8s-app=cilium

# Check for errors
cilium status --all-nodes
```

## Advanced Features

### Cluster Mesh (Multi-Cluster)

Connect multiple Kubernetes clusters:

```bash
# Enable cluster mesh on both clusters
cilium clustermesh enable

# Connect clusters
cilium clustermesh connect --context cluster1 --destination-context cluster2
```

### Transparent Encryption

Enable WireGuard encryption:

```bash
cilium config set encryption-type wireguard
cilium config set enable-wireguard true
```

### Service Mesh

Enable service mesh features:

```bash
cilium install \
  --set kubeProxyReplacement=strict \
  --set ingressController.enabled=true \
  --set envoy.enabled=true
```

### BGP Support

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

## Best Practices

1. **Always disable kube-proxy** - Required for kube-proxy replacement
2. **Use Gateway API** - More powerful than Ingress
3. **Enable Hubble** - Essential for debugging and observability
4. **Implement network policies** - Start with default deny
5. **Monitor metrics** - Use Prometheus and Grafana
6. **Test connectivity** - Run cilium connectivity test regularly
7. **Keep updated** - Regular Cilium upgrades for features and fixes
8. **Use L7 policies** - For fine-grained application control

## Resources

- [Cilium Documentation](https://docs.cilium.io/)
- [Talos + Cilium Guide](https://www.talos.dev/v1.11/kubernetes-guides/network/deploying-cilium/)
- [Gateway API Docs](https://gateway-api.sigs.k8s.io/)
- [Hubble Documentation](https://docs.cilium.io/en/stable/gettingstarted/hubble/)
- [Cilium Slack](https://cilium.io/slack)
- [Cilium GitHub](https://github.com/cilium/cilium)

## Example Configurations

See the [production-ha example](../examples/production-ha/) for a complete working configuration with Cilium, Gateway API, and all recommended settings.
