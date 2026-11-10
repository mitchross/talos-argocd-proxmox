# Headlamp access

Headlamp is served through the internal Gateway. The `headlamp-admin` ServiceAccount
name is historical. `metrics-role.yaml` grants read-only workload, metrics, and
infrastructure visibility. Its explicit core resource list excludes Secrets and
proxy subresources, so the Secrets screen is unavailable to this identity.

After syncing the role change, verify from the repository root:

```bash
python3 scripts/check-headlamp-access.py
```

Expected results: Secrets denied, pods allowed, pod logs allowed. The script
sends non-persistent SubjectAccessReviews that name the ServiceAccount explicitly.
Through this cluster's Omni proxy, `kubectl auth can-i --as` returned the
operator's permission instead of testing the requested identity. Do not use
that result as evidence that Headlamp can read Secrets.

Existing login remains usable. `token-secret.yaml` still supplies a long-lived
login token. Replacing that login method is separate work and must not strand
the operator without access.

A Git revert restores the previous role, including its broad Secret access. If you
accidentally omit a read permission, add it explicitly. Do not restore the
core wildcard as a convenience.

## AI Assistant plugin

An init container installs the Headlamp AI Assistant plugin, pinned by version
and SHA256 in `values.yaml`. Bump both values together from the plugin's
ArtifactHub page. Set the model provider in Headlamp under Settings → AI
Assistant. For LiteLLM, pick OpenAI-Compatible with base URL
`https://litellm.vanillax.me/v1` and a LiteLLM key. That setting is saved in
your browser, not in Git. The assistant acts with your login token, which is
read-only, so it cannot change the cluster.
