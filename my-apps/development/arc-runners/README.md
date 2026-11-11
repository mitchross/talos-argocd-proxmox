# ARC runners for private repos

In-cluster GitHub Actions runners (Actions Runner Controller, runner scale sets) so private repos
run CI here instead of on paid GitHub-hosted minutes. Public repos keep using GitHub-hosted runners.

- Controller: `infrastructure/controllers/arc-systems/` (namespace `arc-systems`, chart 0.15.1, CRDs included).
- Scale sets: this directory (namespace `arc-runners`), one per private repo, scaling 0 to max on demand.

| `runs-on:` | Repo | Max runners | Runner limits (each of runner and dind) |
|---|---|---|---|
| `arc-deal-scout` | `mitchross/deal-scout` | 2 | 4 CPU / 8Gi |
| `arc-consumers-energy-sync` | `mitchross/consumers-energy-sync` | 1 | 2 CPU / 4Gi |
| `arc-dotfiles` | `mitchross/dotfiles` | 1 | 1 CPU / 2Gi |

All three use Docker-in-Docker (privileged sidecar, same approach as `my-apps/development/gitea-actions/`),
so `docker build` and `docker/build-push-action` work. Scratch space is `emptyDir` on the node (work dir plus
`/var/lib/docker`, size-limited per scale set; the pod is evicted if it exceeds the limit). Runner pods are ephemeral: one job each, no cache survives.

## Credential

1Password vault `homelab-prod`, item `renovate`, field `github_token` (reused) becomes
`Secret/arc-runners/arc-github-token` with key `github_token`. Registering a repo-level scale set needs
repo admin: a classic PAT with `repo` scope, or fine-grained with Administration read/write on those repos.
If registration fails, create item `github-arc` with field `github_token` and change `remoteRef.key` in `externalsecret.yaml`.

## Use in a workflow

```yaml
jobs:
  build:
    runs-on: arc-deal-scout
```

The runner image is the bare upstream one: add `sudo apt-get install -y build-essential` (or a setup action) if a job needs a C toolchain.

## Add another private repo

1. Copy `dotfiles-values.yaml` to `<repo>-values.yaml`; set `githubConfigUrl` and `runnerScaleSetName` (`arc-<repo>`).
2. Add a `helmCharts` entry in `kustomization.yaml` with `releaseName: arc-<repo>` and the new values file.
3. If the token cannot see the repo, widen it in GitHub. Open a PR.

Check: `kubectl -n arc-systems get pods` (controller plus one listener per scale set), `kubectl -n arc-runners get autoscalingrunnerset`.
Rollback: revert the PR; Argo prunes the scale sets, then the controller.
