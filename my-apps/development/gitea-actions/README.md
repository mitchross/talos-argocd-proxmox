# Gitea Actions runner recovery

`act-runner` needs a Gitea runner registration token in the Kubernetes Secret
`gitea-actions/act-runner-token`. The token is secret material, so Git only
declares the `ExternalSecret`; 1Password stores the value.

## 1Password item

Vault: `homelab-prod`

Item: `gitea-actions`

Field: `act_runner_token`

Generate or rotate the value from the restored Gitea pod:

```bash
kubectl exec -n gitea deploy/gitea -- gitea actions generate-runner-token
```

Paste the printed token into the 1Password field above. External Secrets then
creates:

```text
Secret/gitea-actions/act-runner-token
  token: <Gitea runner registration token>
```

After the 1Password item exists, uncomment `externalsecret.yaml` in this
directory's `kustomization.yaml` and push the GitOps change. Until then, use
the manual Secret patch below during rebuilds.

## Post-nuke order

1. Restore Gitea CNPG and the Gitea app.
2. Verify 1Password Connect and External Secrets are healthy.
3. Verify this ExternalSecret synced:

```bash
kubectl get externalsecret -n gitea-actions act-runner-token
kubectl get secret -n gitea-actions act-runner-token
kubectl rollout status -n gitea-actions deploy/act-runner
```

If `act-runner-token` is missing and `act-runner` is stuck in
`CreateContainerConfigError`, the 1Password item/field is missing or stale.

## Registry refill after a nuke

The in-cluster registry (`registry.vanillax.me`) uses a cluster PVC. After a
full nuke it can come back empty even though the registry pod and HTTPRoute are
healthy:

```bash
kubectl exec -n kube-system deploy/registry -- \
  wget -qO- http://127.0.0.1:5000/v2/_catalog
```

An empty catalog means apps pinned to `registry.vanillax.me/...` will hit
`ImagePullBackOff` until their images are rebuilt or repushed. For radar-ng,
use Gitea Actions once the runner is healthy, or build locally from the
`radar-ng` repo:

```bash
cd ~/programming/radar-ng/backend
VERSION=v1.1.4 ./scripts/build-push.sh tile-server
VERSION=v1.1.1 ./scripts/build-push.sh basemap open-meteo-worker
VERSION=v1.1.7 ./scripts/build-push.sh temporal-worker
```

`basemap-bootstrap:latest` is maintained in this GitOps repo:

```bash
cd ~/programming/talos-argocd-proxmox
./scripts/build-push-custom-apps.sh basemap-bootstrap
kubectl -n radar-ng delete job basemap-bootstrap
```
