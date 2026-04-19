# Follow-up notes — 2026-04-19

Punch list of known issues and deferred work after the Talos 1.13 / VPA
rip-out / Qwen 3.6 / chaos-test session. Nothing here is urgent; the
cluster is fully serving. Come back when you have time.

## Known broken apps (pre-existing, not from chaos test)

### 1. Temporal — `ConnectProtocol: zero value` config bug

All Temporal server pods CrashLoop with:
```
Unable to load configuration: Persistence.DataStores[default](value).SQL.ConnectProtocol: zero value,
Persistence.DataStores[visibility](value).SQL.ConnectProtocol: zero value.
```

**Root cause:** upstream Temporal Helm chart `temporal-1.1.1` emits a
`config_template.yaml` missing `connectProtocol: "tcp"` under each
`datastores.<name>.sql` block. Temporal 1.28+ requires it explicitly.

**Fix options:**
- (Preferred) Patch the chart's `config_template.yaml` ConfigMap via
  a Kustomize strategic merge that injects `connectProtocol: "tcp"`
  under both `default.sql` and `visibility.sql`.
- Upgrade to a newer Temporal chart version that ships the fix.
- Build a custom `config_template.yaml` and mount it over the
  chart-rendered one.

**Affected pods:** `temporal-frontend`, `temporal-history`, `temporal-matching`, `temporal-worker`.

### 2. `news-reader` and `temporal-worker` (custom app) — images never pushed

Both apps point at `registry.vanillax.me/{name}:latest` but the registry
catalog is empty. Registry itself is fine (in-cluster `kube-system/registry`).

**Fix:** build + push. Dockerfiles exist, clean multi-stage.
```bash
# from dev box
cd ~/programming/talos-argocd-proxmox/my-apps/development/news-reader/app
docker build -t registry.vanillax.me/news-reader:latest .
docker push registry.vanillax.me/news-reader:latest

cd ~/programming/talos-argocd-proxmox/my-apps/development/temporal-worker
docker build -t registry.vanillax.me/temporal-worker:latest -f Dockerfile .
docker push registry.vanillax.me/temporal-worker:latest

kubectl rollout restart deploy -n news-reader news-reader
kubectl rollout restart deploy -n temporal-worker temporal-worker
```

If you decide you don't use these:
```bash
rm -rf my-apps/development/news-reader my-apps/development/temporal-worker
# commit+push → Argo prunes.
```

### 3. `project-nomad/embeddings` — HuggingFace model config duplicate field

```
Error: Failed to parse `config.json`
Caused by: duplicate field `max_position_embeddings` at line 42 column 15
```

The text-embeddings-inference binary downloads `config.json` from the
pinned HF model and the upstream repo has a dup field that the Rust
deserializer rejects (some HF tooling tolerates it, `serde` doesn't).

**Fix options:**
- Upgrade the `text-embeddings-inference` image to a version with a
  more forgiving parser.
- Pin the model to a specific revision that predates the dup field.
- Bake a custom model dir onto the NFS PVC with a clean `config.json`.

**Affected pods:** `project-nomad/embeddings` (CrashLoop), and
`project-nomad/project-nomad` (Init:Error, depends on embeddings).

### 4. `immich/immich-server` — CrashLoop (pre-existing)

Not investigated this session. Check logs:
```bash
kubectl logs -n immich deploy/immich-server --tail=50
```

---

## High pod restart counts after chaos test — informational

After the cluster-wide nuke on 2026-04-19, many pods have restart
counts of 4-8 that are **not** live crash loops — just cumulative
startup-retry from the dependency cascade (Longhorn CSI register,
cert-manager webhook cert, Kyverno webhook admission, Cilium
rate-limiting). All of those pods are currently `Running` and stable.

To distinguish "still flapping" from "done restarting, just showing
history":
```bash
kubectl get pods -A -o json | python3 -c "
import sys,json
from datetime import datetime,timezone,timedelta
d=json.load(sys.stdin); now=datetime.now(timezone.utc)
for p in d['items']:
  for c in p.get('status',{}).get('containerStatuses',[]) or []:
    last=c.get('lastState',{}).get('terminated',{}).get('finishedAt')
    if last and datetime.now(timezone.utc)-datetime.fromisoformat(last.replace('Z','+00:00')) < timedelta(minutes=2):
      print(f\"FLAPPING: {p['metadata']['namespace']}/{p['metadata']['name']} restarts={c['restartCount']}\")
"
```

Cumulative restart counts naturally decay out of relevance — you don't
need to delete/recreate these pods to "reset" them.

---

## otel-gateway-collector — connection backoff

Three replicas CrashLoopBackOff with `dial tcp 10.103.245.111:4317:
connect: operation not permitted`. This was a transient Cilium
network-identity hiccup from the restart. Once the collector's retry
interval (up to ~40s) rolls around after Cilium identities re-sync,
they self-heal. If they're still stuck next time you check:

```bash
kubectl rollout restart -n opentelemetry deploy -l app.kubernetes.io/component=opentelemetry-collector
```

---

## ArgoCD drift — 22 OutOfSync Renovate bumps

Most are patch/minor. **Before any mass-merge:** check PRs against the
critical-chart rule in `CLAUDE.md`:

> Don't auto-merge major Helm chart version bumps for critical
> infrastructure (kube-prometheus-stack, longhorn, kyverno, cilium) —
> the 2026-04-08 kube-prometheus-stack v82→v83 auto-merge caused a full
> cluster outage via Kyverno webhook deadlock.

Suggested triage:
```bash
gh pr list --limit 50 --json number,title,labels,headRefName --jq '
  .[] | select(.title | test("kube-prometheus-stack|longhorn|kyverno|cilium"; "i"))
'
```
→ manual review for those. The rest can go in small batches of ~5,
wait for Argo to sync each batch clean, then merge the next.

---

## Kopia maintenance — verify it actually runs nightly

CronJob `volsync-system/kopia-maintenance` runs daily at 03:00 UTC.
First successful manual run on 2026-04-19 reclaimed 758.5 MB. Check
tomorrow morning that the scheduled run also succeeded:

```bash
kubectl get jobs -n volsync-system --sort-by=.metadata.creationTimestamp | tail -5
kubectl logs -n volsync-system -l job-name=kopia-maintenance-$(date -u +%Y%m%d) --tail=30
```

If it fails again, check for the identity-override regression (Kopia 0.20
ignores `KOPIA_OVERRIDE_HOSTNAME` env var — the CronJob passes
`--override-hostname=cluster` on `repository connect` to work around this).

---

## Infrastructure migrations on the horizon

### Before CNPG 1.30.0 — migrate to Barman Cloud Plugin

Native `spec.backup.barmanObjectStore` is removed in CNPG 1.30. Plugin is
already installed at `infrastructure/database/cnpg-barman-plugin/`
(v0.12.0) but currently unused. Migration docs:
- `docs/cnpg-disaster-recovery.md` § Future Improvements Tier 4
- Rough plan: for each cluster, switch `spec.backup` → `spec.plugins[]`
  referencing an `ObjectStore` CR, one-cluster-at-a-time.

### Possible Qwen 3.6-VL vision-specific model

Our current Qwen 3.6 uses `mmproj-BF16.gguf` for multimodal. If Unsloth
ever ships a dedicated Qwen 3.6-VL GGUF (separate text + vision weights),
it could outperform the projector approach for vision-heavy workloads.
Add a `qwen3.6-vl - qwen3.6-vl` preset alongside the existing one if it
lands.

---

## Zombie cleanup (cosmetic)

Two pre-nuke zombie pods stuck in Error state (age 2d1h, from before
the chaos test):
```bash
kubectl delete pod -n fizzy fizzy-94fb48f8d-zz72q
kubectl delete pod -n karakeep karakeep-meilisearch-6bd7cf8f8c-td5db
```

---

## Optional: model inventory cleanup on NFS (saves ~100 GB)

Files on `/mnt/ai-pool/llama-cpp` not referenced by any current preset:

- `Qwen3-Coder-Next-UD-Q3_K_XL.gguf` (36 GB) — old dedicated-coder model
- `Qwen3-VL-32B-Instruct-Q4_K_M.gguf` (19 GB) — earlier vision model
- `Qwen3-VL-32B-mmproj-BF16.gguf` (1.1 GB) — its projector
- `persona_kappa_20b-*.gguf` (9 split files, ~44 GB) — old persona model

If you don't remember why they're there, they're not being served. Move
to `archive/` or delete. ~100 GB reclaimable.

---

**Checklist for next time you sit down with this:**

- [ ] Pick ONE of the above (don't batch). Temporal is the highest-impact fix.
- [ ] Triage open Renovate PRs (safe vs. critical-chart).
- [ ] Verify Kopia ran overnight.
- [ ] Decide fate of news-reader + temporal-worker (build or delete).
- [ ] Clean up NFS model archive.
