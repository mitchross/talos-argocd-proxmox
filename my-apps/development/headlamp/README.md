# Headlamp access

Headlamp is served through the internal Gateway. The `headlamp-admin` ServiceAccount
name is historical; `metrics-role.yaml` grants read-only workload, metrics, and
infrastructure visibility. Its explicit core resource list excludes Secrets and
proxy subresources. The Secrets screen is therefore unavailable to this identity.

After syncing the role change, verify from the repository root:

```bash
python3 scripts/check-headlamp-access.py
```

Expected results: Secrets denied, pods allowed, pod logs allowed. The script
sends non-persistent SubjectAccessReviews naming the ServiceAccount explicitly.
Through this cluster's Omni proxy, `kubectl auth can-i --as` returned the
operator's permission instead of testing the requested identity; do not use
that result as evidence that Headlamp can read Secrets.

Existing login remains usable. The current
`token-secret.yaml` still supplies a long-lived login token; replacing that login
method is separate work and must not strand the operator without access.

A Git revert restores the previous role, including its broad Secret access. Fix
an accidentally omitted read permission explicitly rather than restoring the
core wildcard as a convenience.
