# Headlamp access

Headlamp is served through the internal Gateway. The `headlamp-admin` ServiceAccount
name is historical; `metrics-role.yaml` grants read-only workload, metrics, and
infrastructure visibility. Its explicit core resource list excludes Secrets and
proxy subresources. The Secrets screen is therefore unavailable to this identity.

After syncing the role change, verify from the operator workstation:

```bash
kubectl auth can-i get secrets --all-namespaces --as=system:serviceaccount:kube-system:headlamp-admin
kubectl auth can-i get pods --all-namespaces --as=system:serviceaccount:kube-system:headlamp-admin
kubectl auth can-i get pods --subresource=log --all-namespaces --as=system:serviceaccount:kube-system:headlamp-admin
```

Expected results: `no`, `yes`, `yes`. Existing login remains usable. The current
`token-secret.yaml` still supplies a long-lived login token; replacing that login
method is separate work and must not strand the operator without access.

A Git revert restores the previous role, including its broad Secret access. Fix
an accidentally omitted read permission explicitly rather than restoring the
core wildcard as a convenience.
