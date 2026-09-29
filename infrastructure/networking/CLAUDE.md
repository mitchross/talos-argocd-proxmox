# Networking Guidelines

> **Required reading before modifying network policies or debugging connectivity:**
> - `docs/domains/networking/topology.md` — Physical network layout, IP assignments, 10G switch topology
> - `docs/domains/networking/policy.md` — Cilium CiliumClusterwideNetworkPolicy, threat model, what's blocked vs allowed

## Gateway API Routing

This cluster uses **Gateway API exclusively** (not Ingress). Never create Ingress resources.
Gateways are defined once in `infrastructure/networking/gateway/`. HTTPRoute templates (internal and
external, with the three required external-dns pieces) are in `my-apps/CLAUDE.md` § "Application with Web Access".

**CRITICAL**: Services MUST have named ports (`name: http`) for HTTPRoute to work — it fails silently without this.

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
