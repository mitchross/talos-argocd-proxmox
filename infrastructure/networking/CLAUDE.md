# Networking Guidelines

> **Required reading before modifying network policies or debugging connectivity:**
> - `docs/network-topology.md` — Physical network layout, IP assignments, 10G switch topology
> - `docs/network-policy.md` — Cilium CiliumClusterwideNetworkPolicy, threat model, what's blocked vs allowed

## Gateway API Routing

This cluster uses **Gateway API exclusively** (not Ingress). Never create Ingress resources.

```yaml
# Gateway defined once in infrastructure/networking/gateway/
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: gateway-external
spec:
  gatewayClassName: cilium
  listeners:
  - name: https
    port: 443
    protocol: HTTPS

# Applications reference the Gateway via HTTPRoute
apiVersion: gateway.networking.k8s.io/v1beta1
kind: HTTPRoute
metadata:
  name: app-route
  namespace: app-name
spec:
  parentRefs:
  - kind: Gateway
    name: gateway-external
    namespace: gateway
  hostnames:
  - app.vanillax.me
  rules:
  - backendRefs:
    - name: app-service
      port: 8080
```

**CRITICAL**: Services MUST have named ports for HTTPRoute to work — fails silently without this:

```yaml
spec:
  ports:
    - name: http        # REQUIRED - HTTPRoute fails silently without this
      port: 8080
      targetPort: 8080
```

## Debugging Networking

```bash
# Verify Cilium health
cilium status
kubectl get pods -n kube-system -l k8s-app=cilium

# Check Gateway API resources
kubectl get gateway -A
kubectl get httproute -A
kubectl describe httproute app-route -n app-name

# Test DNS resolution
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup app-service.app-name.svc.cluster.local
```
