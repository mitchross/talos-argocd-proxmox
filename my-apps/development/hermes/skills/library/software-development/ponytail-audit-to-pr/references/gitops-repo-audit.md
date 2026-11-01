# Auditing a GitOps / Kubernetes repo (talos-argocd-proxmox)

Use with the `delegate_task` swarm (Procedure step 2). Scope is Argo + Kubernetes correctness and practices; security hardening is out unless it causes a real bug.

## Area split (one child each)
1. Phase 1, k8s: Argo bootstrap/AppSets + `infrastructure/{controllers,networking,secrets}` + `scripts/bootstrap-argocd.sh`; `infrastructure/{storage,backup,database,gpu,scheduling,platform}`; `my-apps` split in two halves; `monitoring/` + `omni/` + `host-monitoring/`.
2. Phase 2, docs: `docs/` + `mkdocs.yml` + `llms.txt`; separately all CLAUDE.md/AGENTS.md/READMEs outside docs + `.claude/commands`, `.agents/skills`.
3. Phase 3, rest: `scripts/`, `.github/` (workflows, renovate), `benchmarks/`, root tooling.

## Checks that found real bugs (put them in the briefs)
- **Alert rules vs dropped metrics:** for every custom rule, `count(<metric>)` against in-cluster Prometheus (`/api/v1/query`). `metricRelabelings` drops (e.g. `container_spec.*`) and exporter counter files silently kill rules that still load as healthy.
- **Retention selectors vs real labels:** read Loki `retention_stream` selectors, then list label values (`/loki/api/v1/label/<name>/values`, header `X-Scope-OrgID: 1`) and the oldest line per stream; a stream missing from the selector gets the short default.
- **Silent CI gates:** grep the latest default-branch run log, `gh run view <id> --log | grep -E 'command not found|No such file'`. An `if out=$(tool ...)` check passes when the tool is absent. Run each validator on a deliberately broken input to see whether it fails or only warns.
- **Renovate patterns:** compare every `managerFilePatterns` entry with real top-level dirs; explicit patterns replace the manager default, so missing dirs (e.g. `infrastructure/`) are never updated and nonexistent ones (`infra/`, `iac/`) are dead. Check `enabledManagers` covers compose files and Dockerfiles that exist.
- **"Never runs" claims:** grep `.github/workflows` for the test path before believing it; tests are often run from a broader job.
- **Postgres Deployments:** compare probes across all app DBs (`kubectl get deploy -o jsonpath` for startupProbe and terminationGracePeriodSeconds); the outlier without a startupProbe gets killed during WAL replay.
- **Argo-owned resources edited by Jobs** (`kubectl set env`, scale, patch) race self-heal.
- **Admission policies on all pod CREATEs** with `failurePolicy: Fail` can block every pod.
- **Dead files:** for each file, grep its basename across the repo (kustomizations, docs, renovate ignorePaths); app dirs whose kustomization is all comments are "off" shells.
- **"Running but unused" controllers:** absence of CRs in git is not enough. Check the operator's logs for reconciles, the Argo app resource trees (`kubectl -n argocd get applications -o json`, scan `status.resources`) and documented intent in comments or the user's starter repos before filing it.
- **Restart counts:** `restartCount` is cumulative since pod start, so a scary number can be old. Report `increase(kube_pod_container_status_restarts_total[24h])` and the per-hour timeline instead; see the homelab-gitops-change-prs skill's `references/restart-and-job-triage.md`.
- **Docs:** a script that checks every relative `.md` link and every `mkdocs.yml` nav path; then check rebuild runbooks step by step against the DR doc and wave annotations.

## Fixing in one PR
- Off apps: strip to `namespace.yaml` + `kustomization.yaml`; never delete the dir (the static-risk gate blocks a disappearing Application). If the namespace belongs to another App, or the app would render nothing, use the placeholder-ConfigMap retire recipe in the homelab-gitops-change-prs skill instead, because CI rejects empty renders.
- New init containers or probes the fix adds must run under the pod's `securityContext` uid. Example: `pg_isready` in a postgres image as a uid with no passwd entry prints `no attempt` forever unless it gets `-U <name>`. Check every patched pod goes Ready after merge.
- Name the files of other open PRs as off-limits in the fix prompt.
- Local renders need Helm and Kustomize at the CI pins (`cluster-ci.yml` `env:`). Install them into `/opt/data/tools/bin` and a pyyaml/pytest venv, and source `/opt/data/tools/talos-env.sh`, so the fix agent can run `kustomize build --enable-helm`, the full render loop and the `scripts/validate-*.py` validators.
