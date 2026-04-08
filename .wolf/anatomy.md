# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-04-08T02:26:50.382Z
> Files: 517 tracked | Anatomy hits: 0 | Misses: 0

## ./

- `.DS_Store` (~4915 tok)
- `.gitattributes` — Git attributes (~6 tok)
- `.gitignore` — Git ignore rules (~611 tok)
- `astro.config.mjs` — Astro configuration (~274 tok)
- `CLAUDE.md` — OpenWolf (~2907 tok)
- `firewalla-dns-config.txt` — Firewalla Local DNS Configuration for vanillax.me (~424 tok)
- `MIGRATION_EXTERNAL_DNS.md` — Migration to ExternalDNS-Based Split DNS Architecture (~1870 tok)
- `mkdocs.yml` (~269 tok)
- `package-lock.json` — npm lock file (~90080 tok)
- `package.json` — Node.js package manifest (~242 tok)
- `README.md` — Project documentation (~3991 tok)
- `thermodynamic-corridor-infographic.jsx` — sections (~7027 tok)
- `thermodynamic-corridor-summary.md` — Civilisation's Thermodynamic Corridor — Summary (~2589 tok)
- `tsconfig.json` — TypeScript configuration (~12 tok)

## .astro/

- `content-assets.mjs` (~7 tok)
- `content-modules.mjs` (~60 tok)
- `content.d.ts` — Resolve an array of entry references from the same collection (~1640 tok)
- `types.d.ts` — / <reference types="astro/client" /> (~22 tok)

## .astro/collections/

- `docs.schema.json` (~4806 tok)

## .claude/

- `settings.json` (~463 tok)
- `settings.local.json` (~171 tok)

## .claude/commands/

- `add-backup.md` — Steps (~288 tok)
- `new-app.md` — Requirements (~455 tok)
- `new-database.md` — Steps (~401 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## .githooks/

- `pre-commit` — Pre-commit hook: validates Kyverno policies before allowing commit. (~110 tok)

## .github/

- `.DS_Store` (~1640 tok)
- `copilot-instructions.md` — GitHub Copilot Instructions for talos-argocd-proxmox (~1417 tok)
- `renovate.json5` (~1410 tok)

## .github/instructions/

- `argocd.instructions.md` — ArgoCD GitOps Instructions (~1902 tok)
- `gpu.instructions.md` — GPU Workload Instructions (~1153 tok)
- `standards.instructions.md` — Project Overview (~1373 tok)
- `talos.instructions.md` — Talos OS Management Instructions (~882 tok)

## .github/workflows/

- `cluster-ci.yml` — - monitoring/** (~1110 tok)
- `docs.yml` — CI: Deploy Documentation (~286 tok)
- `llama-cpp-build.yml` — CI: Build llama.cpp CUDA Image (~1011 tok)

## docs/

- `.DS_Store` (~1640 tok)
- `argocd.md` — ArgoCD & GitOps Architecture (~5600 tok)
- `backup-restore.md` — Zero-Touch PVC Backup and Restore (~3381 tok)
- `cnpg-disaster-recovery.md` — CNPG Database Disaster Recovery (~7577 tok)
- `index.md` — Talos ArgoCD Proxmox (~272 tok)
- `network-policy.md` — Network Security & LAN Isolation (~1607 tok)
- `network-topology.md` — Network Topology (~1663 tok)
- `pvc-plumber-full-flow.md` — Zero-Touch PVC Backup/Restore: The Complete Picture (~11603 tok)
- `vpa-resource-optimization.md` — VPA Resource Optimization Guide (~4408 tok)

## docs/plans/

- `2026-02-28-single-gpu-llamacpp-comfyui-vision.md` — Single-GPU Llama.cpp + ComfyUI Vision Integration (~2086 tok)
- `2026-03-16-project-nomad-k8s-openai.md` — Project Nomad: Kubernetes + OpenAI-Compatible LLM Provider (~5421 tok)
- `2026-03-22-alloy-otel-honeycomb-design.md` — OpenTelemetry Operator + Honeycomb Design (~1136 tok)

## infrastructure/

- `.DS_Store` (~3824 tok)
- `CLAUDE.md` — Infrastructure Guidelines (~869 tok)

## infrastructure/controllers/

- `.DS_Store` (~3278 tok)

## infrastructure/controllers/1passwordconnect/

- `kustomization.yaml` — K8s Kustomization: connect (~94 tok)
- `namespace.yaml` — K8s Namespace: 1passwordconnect (~19 tok)
- `values.yaml` (~267 tok)

## infrastructure/controllers/argocd/

- `.DS_Store` (~1640 tok)
- `http-route.yaml` — K8s HTTPRoute: argocd (~139 tok)
- `kustomization.yaml` — K8s Kustomization: argo-cd (~287 tok)
- `ns.yaml` — K8s Namespace: argocd (~16 tok)
- `root.yaml` — K8s Application: root (~252 tok)
- `values.yaml` — Global settings for the Argo CD chart (~2440 tok)

## infrastructure/controllers/argocd/apps/

- `1passwordconnect.yaml` — K8s Application: 1passwordconnect (~222 tok)
- `argocd.yaml` — K8s Application: argocd (~241 tok)
- `cilium-app.yaml` — Critical: Cilium must be deployed first (wave 0) (~489 tok)
- `database-appset.yaml` — K8s ApplicationSet: database (~705 tok)
- `external-secrets.yaml` — K8s Application: external-secrets (~319 tok)
- `infrastructure-appset.yaml` — K8s ApplicationSet: infrastructure (~1079 tok)
- `kustomization.yaml` — K8s Kustomization (~367 tok)
- `kyverno-app.yaml` — K8s Application: kyverno (~494 tok)
- `longhorn-app.yaml` — Critical: Longhorn must be deployed after Cilium (wave 1) (~371 tok)
- `monitoring-appset.yaml` — K8s ApplicationSet: monitoring (~637 tok)
- `my-apps-appset.yaml` — K8s ApplicationSet: my-apps (~782 tok)
- `opentelemetry-operator-app.yaml` — OpenTelemetry Operator (~429 tok)
- `projects.yaml` — K8s AppProject: infrastructure (~454 tok)
- `pvc-plumber-app.yaml` — K8s Application: pvc-plumber (~327 tok)
- `snapshot-controller-app.yaml` — Snapshot Controller (~256 tok)
- `volsync-app.yaml` — VolSync for PVC backup and replication (~289 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/

- `.helmignore` (~8 tok)
- `Chart.yaml` — K8s changed: redis-ha (~259 tok)
- `README.md` — Project documentation (~36715 tok)
- `values.yaml` — # Argo CD configuration (~46209 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/charts/redis-ha/

- `.helmignore` — Patterns to ignore when building packages. (~97 tok)
- `Chart.yaml` (~176 tok)
- `README.md` — Project documentation (~9983 tok)
- `values.yaml` — # Globally shared configuration (~10288 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/charts/redis-ha/templates/

- `_configs.tpl` (~8033 tok)
- `_helpers.tpl` (~1243 tok)
- `NOTES.txt` (~350 tok)
- `redis-auth-secret.yaml` — K8s Secret: {{ (~128 tok)
- `redis-ha-announce-service.yaml` — K8s Service: {{ (~560 tok)
- `redis-ha-configmap.yaml` — K8s ConfigMap: {{ (~290 tok)
- `redis-ha-exporter-script-configmap.yaml` — K8s ConfigMap: {{ (~122 tok)
- `redis-ha-health-configmap.yaml` — K8s ConfigMap: {{ (~179 tok)
- `redis-ha-network-policy.yaml` — K8s NetworkPolicy: {{ (~646 tok)
- `redis-ha-pdb.yaml` — K8s PodDisruptionBudget: {{ (~166 tok)
- `redis-ha-prometheus-rule.yaml` — K8s PrometheusRule: {{ (~175 tok)
- `redis-ha-role.yaml` — K8s Role: {{ (~133 tok)
- `redis-ha-rolebinding.yaml` — K8s RoleBinding: {{ (~168 tok)
- `redis-ha-secret.yaml` — K8s Secret: {{ (~314 tok)
- `redis-ha-service.yaml` — K8s Service: {{ (~431 tok)
- `redis-ha-serviceaccount.yaml` — K8s ServiceAccount: {{ (~302 tok)
- `redis-ha-servicemonitor.yaml` — K8s ServiceMonitor: {{ (~434 tok)
- `redis-ha-statefulset.yaml` — K8s StatefulSet: {{ (~7409 tok)
- `redis-haproxy-deployment.yaml` — K8s Deployment: {{ (~2206 tok)
- `redis-haproxy-network-policy.yaml` — K8s NetworkPolicy: {{ (~636 tok)
- `redis-haproxy-pdb.yaml` — K8s PodDisruptionBudget: {{ (~175 tok)
- `redis-haproxy-role.yaml` — K8s Role: {{ (~168 tok)
- `redis-haproxy-rolebinding.yaml` — K8s RoleBinding: {{ (~208 tok)
- `redis-haproxy-service.yaml` — K8s Service: {{ (~646 tok)
- `redis-haproxy-serviceaccount.yaml` — K8s ServiceAccount: {{ (~150 tok)
- `redis-haproxy-servicemonitor.yaml` — K8s ServiceMonitor: {{ (~476 tok)
- `redis-tls-secret.yaml` — K8s Secret: {{ (~256 tok)
- `sentinel-auth-secret.yaml` — K8s Secret: {{ (~139 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/charts/redis-ha/templates/tests/

- `test-redis-ha-configmap.yaml` — K8s Pod: {{ (~320 tok)
- `test-redis-ha-pod.yaml` — K8s Pod: {{ (~299 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/

- `_common.tpl` (~1191 tok)
- `_helpers.tpl` (~3158 tok)
- `_versions.tpl` (~56 tok)
- `aggregate-roles.yaml` — K8s ClusterRole: {{ (~398 tok)
- `extra-manifests.yaml` (~42 tok)
- `networkpolicy-default-deny.yaml` — K8s NetworkPolicy: {{ (~117 tok)
- `NOTES.txt` (~607 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-application-controller/

- `clusterrole.yaml` — K8s ClusterRole: {{ (~172 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~169 tok)
- `deployment.yaml` — K8s Deployment: {{ (~5278 tok)
- `metrics.yaml` — K8s Service: {{ (~426 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~190 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~268 tok)
- `prometheusrule.yaml` — K8s PrometheusRule: {{ (~303 tok)
- `role.yaml` — K8s Role: {{ (~315 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~167 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~214 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~606 tok)
- `statefulset.yaml` — K8s StatefulSet: {{ (~5402 tok)
- `vpa.yaml` — K8s VerticalPodAutoscaler: {{ (~316 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-applicationset/

- `certificate.yaml` — K8s Certificate: {{ (~448 tok)
- `clusterrole.yaml` — K8s ClusterRole: {{ (~415 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~181 tok)
- `deployment.yaml` — K8s Deployment: {{ (~4792 tok)
- `ingress.yaml` — K8s Ingress: {{ (~688 tok)
- `metrics.yaml` — K8s Service: {{ (~442 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~249 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~278 tok)
- `role.yaml` — K8s Role: {{ (~410 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~173 tok)
- `service.yaml` — K8s Service: {{ (~275 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~222 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~627 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-commit-server/

- `deployment.yaml` — K8s Deployment: {{ (~2550 tok)
- `metrics.yaml` — K8s Service: {{ (~443 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~231 tok)
- `service.yaml` — K8s Service: {{ (~256 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~227 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-configs/

- `argocd-cm.yaml` — K8s ConfigMap: argocd-cm (~144 tok)
- `argocd-cmd-params-cm.yaml` — K8s ConfigMap: argocd-cmd-params-cm (~161 tok)
- `argocd-cmp-cm.yaml` — K8s ConfigMap: argocd-cmp-cm (~215 tok)
- `argocd-dex-server-tls-secret.yaml` — K8s Secret: argocd-dex-server-tls (~248 tok)
- `argocd-gpg-keys-cm.yaml` — K8s ConfigMap: argocd-gpg-keys-cm (~132 tok)
- `argocd-notifications-cm.yaml` — K8s ConfigMap: argocd-notifications-cm (~277 tok)
- `argocd-notifications-secret.yaml` — K8s Secret: {{ (~220 tok)
- `argocd-rbac-cm.yaml` — K8s ConfigMap: argocd-rbac-cm (~161 tok)
- `argocd-repo-server-tls-secret.yaml` — K8s Secret: argocd-repo-server-tls (~255 tok)
- `argocd-secret.yaml` — K8s Secret: argocd-secret (~650 tok)
- `argocd-server-tls-secret.yaml` — K8s Secret: argocd-server-tls (~229 tok)
- `argocd-ssh-known-hosts-cm.yaml` — K8s ConfigMap: argocd-ssh-known-hosts-cm (~174 tok)
- `argocd-styles-cm.yaml` — K8s ConfigMap: argocd-styles-cm (~109 tok)
- `argocd-tls-certs-cm.yaml` — K8s ConfigMap: argocd-tls-certs-cm (~149 tok)
- `cluster-secrets.yaml` — K8s Secret: {{ (~393 tok)
- `externalredis-secret.yaml` — K8s Secret: argocd-redis (~199 tok)
- `repository-credentials-secret.yaml` — K8s Secret: argocd-repo-creds-{{ (~188 tok)
- `repository-secret.yaml` — K8s Secret: argocd-repo-{{ (~174 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-notifications/

- `clusterrole.yaml` — K8s ClusterRole: {{ (~328 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~183 tok)
- `deployment.yaml` — K8s Deployment: {{ (~2778 tok)
- `metrics.yaml` — K8s Service: {{ (~439 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~216 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~285 tok)
- `role.yaml` — K8s Role: {{ (~238 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~186 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~229 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~677 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-repo-server/

- `clusterrole.yaml` — K8s ClusterRole: {{ (~174 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~182 tok)
- `deployment.yaml` — K8s Deployment: {{ (~6243 tok)
- `hpa.yaml` — K8s HorizontalPodAutoscaler: {{ (~380 tok)
- `metrics.yaml` — K8s Service: {{ (~436 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~402 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~268 tok)
- `role.yaml` — K8s Role: {{ (~132 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~183 tok)
- `service.yaml` — K8s Service: {{ (~299 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~214 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~617 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-server/

- `backendtlspolicy.yaml` — K8s BackendTLSPolicy: {{ (~250 tok)
- `certificate.yaml` — K8s Certificate: {{ (~499 tok)
- `clusterrole.yaml` — K8s ClusterRole: {{ (~512 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~163 tok)
- `deployment.yaml` — K8s Deployment: {{ (~6338 tok)
- `grpcroute.yaml` — K8s GRPCRoute: {{ (~400 tok)
- `hpa.yaml` — K8s HorizontalPodAutoscaler: {{ (~367 tok)
- `httproute.yaml` — K8s HTTPRoute: {{ (~398 tok)
- `ingress-grpc.yaml` — K8s Ingress: {{ (~680 tok)
- `ingress.yaml` — K8s Ingress: {{ (~752 tok)
- `metrics.yaml` — K8s Service: {{ (~419 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~167 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~257 tok)
- `role.yaml` — K8s Role: {{ (~241 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~160 tok)
- `service.yaml` — K8s Service: {{ (~641 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~206 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~595 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-server/aws/

- `ingress.yaml` — K8s Ingress: {{ (~829 tok)
- `service.yaml` — K8s Service: {{ (~338 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-server/gke/

- `backendconfig.yaml` — K8s BackendConfig: {{ (~155 tok)
- `frontendconfig.yaml` — K8s FrontendConfig: {{ (~157 tok)
- `ingress.yaml` — K8s Ingress: {{ (~783 tok)
- `managedcertificate.yaml` — K8s ManagedCertificate: {{ (~193 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/argocd-server/openshift/

- `route.yaml` — K8s Route: {{ (~258 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/crds/

- `crd-application.yaml` — K8s CustomResourceDefinition: applications.argoproj.io (~94345 tok)
- `crd-applicationset.yaml` — K8s CustomResourceDefinition: applicationsets.argoproj.io (~294315 tok)
- `crd-project.yaml` — K8s CustomResourceDefinition: appprojects.argoproj.io (~4644 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/dex/

- `deployment.yaml` — K8s Deployment: {{ (~2890 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~263 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~256 tok)
- `role.yaml` — K8s Role: {{ (~124 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~167 tok)
- `service.yaml` — K8s Service: {{ (~358 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~178 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~546 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/redis-secret-init/

- `job.yaml` — K8s Job: {{ (~946 tok)
- `role.yaml` — K8s Role: {{ (~214 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~220 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~234 tok)

## infrastructure/controllers/argocd/charts/argo-cd-8.6.4/argo-cd/templates/redis/

- `deployment.yaml` — K8s Deployment: {{ (~2653 tok)
- `health-configmap.yaml` — K8s ConfigMap: {{ (~311 tok)
- `metrics.yaml` — K8s Service: {{ (~433 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~364 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~277 tok)
- `service.yaml` — K8s Service: {{ (~259 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~182 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~577 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/

- `.helmignore` (~8 tok)
- `Chart.yaml` — K8s fixed: redis-ha (~270 tok)
- `README.md` — Project documentation (~36261 tok)
- `values.yaml` — # Argo CD configuration (~45304 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/charts/redis-ha/

- `.helmignore` — Patterns to ignore when building packages. (~97 tok)
- `Chart.yaml` (~176 tok)
- `README.md` — Project documentation (~9983 tok)
- `values.yaml` — # Globally shared configuration (~10288 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/charts/redis-ha/templates/

- `_configs.tpl` (~8033 tok)
- `_helpers.tpl` (~1243 tok)
- `NOTES.txt` (~350 tok)
- `redis-auth-secret.yaml` — K8s Secret: {{ (~128 tok)
- `redis-ha-announce-service.yaml` — K8s Service: {{ (~560 tok)
- `redis-ha-configmap.yaml` — K8s ConfigMap: {{ (~290 tok)
- `redis-ha-exporter-script-configmap.yaml` — K8s ConfigMap: {{ (~122 tok)
- `redis-ha-health-configmap.yaml` — K8s ConfigMap: {{ (~179 tok)
- `redis-ha-network-policy.yaml` — K8s NetworkPolicy: {{ (~646 tok)
- `redis-ha-pdb.yaml` — K8s PodDisruptionBudget: {{ (~166 tok)
- `redis-ha-prometheus-rule.yaml` — K8s PrometheusRule: {{ (~175 tok)
- `redis-ha-role.yaml` — K8s Role: {{ (~133 tok)
- `redis-ha-rolebinding.yaml` — K8s RoleBinding: {{ (~168 tok)
- `redis-ha-secret.yaml` — K8s Secret: {{ (~314 tok)
- `redis-ha-service.yaml` — K8s Service: {{ (~431 tok)
- `redis-ha-serviceaccount.yaml` — K8s ServiceAccount: {{ (~302 tok)
- `redis-ha-servicemonitor.yaml` — K8s ServiceMonitor: {{ (~434 tok)
- `redis-ha-statefulset.yaml` — K8s StatefulSet: {{ (~7409 tok)
- `redis-haproxy-deployment.yaml` — K8s Deployment: {{ (~2206 tok)
- `redis-haproxy-network-policy.yaml` — K8s NetworkPolicy: {{ (~636 tok)
- `redis-haproxy-pdb.yaml` — K8s PodDisruptionBudget: {{ (~175 tok)
- `redis-haproxy-role.yaml` — K8s Role: {{ (~168 tok)
- `redis-haproxy-rolebinding.yaml` — K8s RoleBinding: {{ (~208 tok)
- `redis-haproxy-service.yaml` — K8s Service: {{ (~646 tok)
- `redis-haproxy-serviceaccount.yaml` — K8s ServiceAccount: {{ (~150 tok)
- `redis-haproxy-servicemonitor.yaml` — K8s ServiceMonitor: {{ (~476 tok)
- `redis-tls-secret.yaml` — K8s Secret: {{ (~256 tok)
- `sentinel-auth-secret.yaml` — K8s Secret: {{ (~139 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/charts/redis-ha/templates/tests/

- `test-redis-ha-configmap.yaml` — K8s Pod: {{ (~320 tok)
- `test-redis-ha-pod.yaml` — K8s Pod: {{ (~299 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/

- `_common.tpl` (~1191 tok)
- `_helpers.tpl` (~3158 tok)
- `_versions.tpl` (~56 tok)
- `aggregate-roles.yaml` — K8s ClusterRole: {{ (~398 tok)
- `extra-manifests.yaml` (~42 tok)
- `networkpolicy-default-deny.yaml` — K8s NetworkPolicy: {{ (~117 tok)
- `NOTES.txt` (~607 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-application-controller/

- `clusterrole.yaml` — K8s ClusterRole: {{ (~172 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~169 tok)
- `deployment.yaml` — K8s Deployment: {{ (~5278 tok)
- `metrics.yaml` — K8s Service: {{ (~426 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~190 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~268 tok)
- `prometheusrule.yaml` — K8s PrometheusRule: {{ (~303 tok)
- `role.yaml` — K8s Role: {{ (~315 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~167 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~214 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~606 tok)
- `statefulset.yaml` — K8s StatefulSet: {{ (~5402 tok)
- `vpa.yaml` — K8s VerticalPodAutoscaler: {{ (~316 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-applicationset/

- `certificate.yaml` — K8s Certificate: {{ (~448 tok)
- `clusterrole.yaml` — K8s ClusterRole: {{ (~415 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~181 tok)
- `deployment.yaml` — K8s Deployment: {{ (~4792 tok)
- `ingress.yaml` — K8s Ingress: {{ (~688 tok)
- `metrics.yaml` — K8s Service: {{ (~442 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~249 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~278 tok)
- `role.yaml` — K8s Role: {{ (~410 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~173 tok)
- `service.yaml` — K8s Service: {{ (~275 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~222 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~627 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-commit-server/

- `deployment.yaml` — K8s Deployment: {{ (~2550 tok)
- `metrics.yaml` — K8s Service: {{ (~443 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~231 tok)
- `service.yaml` — K8s Service: {{ (~256 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~227 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-configs/

- `argocd-cm.yaml` — K8s ConfigMap: argocd-cm (~144 tok)
- `argocd-cmd-params-cm.yaml` — K8s ConfigMap: argocd-cmd-params-cm (~161 tok)
- `argocd-cmp-cm.yaml` — K8s ConfigMap: argocd-cmp-cm (~215 tok)
- `argocd-dex-server-tls-secret.yaml` — K8s Secret: argocd-dex-server-tls (~248 tok)
- `argocd-gpg-keys-cm.yaml` — K8s ConfigMap: argocd-gpg-keys-cm (~132 tok)
- `argocd-notifications-cm.yaml` — K8s ConfigMap: argocd-notifications-cm (~277 tok)
- `argocd-notifications-secret.yaml` — K8s Secret: {{ (~220 tok)
- `argocd-rbac-cm.yaml` — K8s ConfigMap: argocd-rbac-cm (~161 tok)
- `argocd-repo-server-tls-secret.yaml` — K8s Secret: argocd-repo-server-tls (~255 tok)
- `argocd-secret.yaml` — K8s Secret: argocd-secret (~650 tok)
- `argocd-server-tls-secret.yaml` — K8s Secret: argocd-server-tls (~229 tok)
- `argocd-ssh-known-hosts-cm.yaml` — K8s ConfigMap: argocd-ssh-known-hosts-cm (~174 tok)
- `argocd-styles-cm.yaml` — K8s ConfigMap: argocd-styles-cm (~109 tok)
- `argocd-tls-certs-cm.yaml` — K8s ConfigMap: argocd-tls-certs-cm (~149 tok)
- `cluster-secrets.yaml` — K8s Secret: {{ (~393 tok)
- `externalredis-secret.yaml` — K8s Secret: argocd-redis (~199 tok)
- `repository-credentials-secret.yaml` — K8s Secret: argocd-repo-creds-{{ (~188 tok)
- `repository-secret.yaml` — K8s Secret: argocd-repo-{{ (~174 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-notifications/

- `clusterrole.yaml` — K8s ClusterRole: {{ (~328 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~183 tok)
- `deployment.yaml` — K8s Deployment: {{ (~2815 tok)
- `metrics.yaml` — K8s Service: {{ (~439 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~216 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~285 tok)
- `role.yaml` — K8s Role: {{ (~238 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~186 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~229 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~677 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-repo-server/

- `clusterrole.yaml` — K8s ClusterRole: {{ (~174 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~182 tok)
- `deployment.yaml` — K8s Deployment: {{ (~6243 tok)
- `hpa.yaml` — K8s HorizontalPodAutoscaler: {{ (~380 tok)
- `metrics.yaml` — K8s Service: {{ (~436 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~402 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~268 tok)
- `role.yaml` — K8s Role: {{ (~132 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~183 tok)
- `service.yaml` — K8s Service: {{ (~299 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~214 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~617 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-server/

- `backendtlspolicy.yaml` — K8s BackendTLSPolicy: {{ (~250 tok)
- `certificate.yaml` — K8s Certificate: {{ (~499 tok)
- `clusterrole.yaml` — K8s ClusterRole: {{ (~512 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~163 tok)
- `deployment.yaml` — K8s Deployment: {{ (~6338 tok)
- `grpcroute.yaml` — K8s GRPCRoute: {{ (~400 tok)
- `hpa.yaml` — K8s HorizontalPodAutoscaler: {{ (~367 tok)
- `httproute.yaml` — K8s HTTPRoute: {{ (~411 tok)
- `ingress-grpc.yaml` — K8s Ingress: {{ (~680 tok)
- `ingress.yaml` — K8s Ingress: {{ (~752 tok)
- `metrics.yaml` — K8s Service: {{ (~419 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~167 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~257 tok)
- `role.yaml` — K8s Role: {{ (~241 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~160 tok)
- `service.yaml` — K8s Service: {{ (~641 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~206 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~595 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-server/aws/

- `ingress.yaml` — K8s Ingress: {{ (~829 tok)
- `service.yaml` — K8s Service: {{ (~338 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-server/gke/

- `backendconfig.yaml` — K8s BackendConfig: {{ (~155 tok)
- `frontendconfig.yaml` — K8s FrontendConfig: {{ (~157 tok)
- `ingress.yaml` — K8s Ingress: {{ (~783 tok)
- `managedcertificate.yaml` — K8s ManagedCertificate: {{ (~193 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/argocd-server/openshift/

- `route.yaml` — K8s Route: {{ (~258 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/crds/

- `crd-application.yaml` — K8s CustomResourceDefinition: applications.argoproj.io (~94345 tok)
- `crd-applicationset.yaml` — K8s CustomResourceDefinition: applicationsets.argoproj.io (~294315 tok)
- `crd-project.yaml` — K8s CustomResourceDefinition: appprojects.argoproj.io (~4644 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/dex/

- `deployment.yaml` — K8s Deployment: {{ (~2890 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~263 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~256 tok)
- `role.yaml` — K8s Role: {{ (~124 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~167 tok)
- `service.yaml` — K8s Service: {{ (~358 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~178 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~546 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/redis-secret-init/

- `job.yaml` — K8s Job: {{ (~946 tok)
- `role.yaml` — K8s Role: {{ (~214 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~220 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~234 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.0.5/argo-cd/templates/redis/

- `deployment.yaml` — K8s Deployment: {{ (~2653 tok)
- `health-configmap.yaml` — K8s ConfigMap: {{ (~311 tok)
- `metrics.yaml` — K8s Service: {{ (~433 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~364 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~277 tok)
- `service.yaml` — K8s Service: {{ (~259 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~182 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~577 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/

- `.helmignore` (~8 tok)
- `Chart.yaml` — K8s changed: redis-ha (~257 tok)
- `README.md` — Project documentation (~36260 tok)
- `values.yaml` — # Argo CD configuration (~45303 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/charts/redis-ha/

- `.helmignore` — Patterns to ignore when building packages. (~97 tok)
- `Chart.yaml` (~198 tok)
- `README.md` — Project documentation (~10185 tok)
- `values.yaml` — # Globally shared configuration (~10561 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/charts/redis-ha/templates/

- `_configs.tpl` (~8289 tok)
- `_helpers.tpl` (~1397 tok)
- `NOTES.txt` (~350 tok)
- `redis-auth-secret.yaml` — K8s Secret: {{ (~180 tok)
- `redis-ha-announce-service.yaml` — K8s Service: {{ (~558 tok)
- `redis-ha-configmap.yaml` — K8s ConfigMap: {{ (~290 tok)
- `redis-ha-exporter-script-configmap.yaml` — K8s ConfigMap: {{ (~122 tok)
- `redis-ha-health-configmap.yaml` — K8s ConfigMap: {{ (~179 tok)
- `redis-ha-network-policy.yaml` — K8s NetworkPolicy: {{ (~548 tok)
- `redis-ha-pdb.yaml` — K8s PodDisruptionBudget: {{ (~166 tok)
- `redis-ha-prometheus-rule.yaml` — K8s PrometheusRule: {{ (~194 tok)
- `redis-ha-role.yaml` — K8s Role: {{ (~133 tok)
- `redis-ha-rolebinding.yaml` — K8s RoleBinding: {{ (~168 tok)
- `redis-ha-secret.yaml` — K8s Secret: {{ (~314 tok)
- `redis-ha-service.yaml` — K8s Service: {{ (~431 tok)
- `redis-ha-serviceaccount.yaml` — K8s ServiceAccount: {{ (~302 tok)
- `redis-ha-servicemonitor.yaml` — K8s ServiceMonitor: {{ (~529 tok)
- `redis-ha-statefulset.yaml` — K8s StatefulSet: {{ (~7409 tok)
- `redis-haproxy-deployment.yaml` — K8s Deployment: {{ (~2317 tok)
- `redis-haproxy-network-policy.yaml` — K8s NetworkPolicy: {{ (~569 tok)
- `redis-haproxy-pdb.yaml` — K8s PodDisruptionBudget: {{ (~182 tok)
- `redis-haproxy-role.yaml` — K8s Role: {{ (~157 tok)
- `redis-haproxy-rolebinding.yaml` — K8s RoleBinding: {{ (~197 tok)
- `redis-haproxy-service.yaml` — K8s Service: {{ (~636 tok)
- `redis-haproxy-serviceaccount.yaml` — K8s ServiceAccount: {{ (~150 tok)
- `redis-haproxy-servicemonitor.yaml` — K8s ServiceMonitor: {{ (~465 tok)
- `redis-tls-secret.yaml` — K8s Secret: {{ (~256 tok)
- `sentinel-auth-secret.yaml` — K8s Secret: {{ (~139 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/charts/redis-ha/templates/tests/

- `test-redis-ha-configmap.yaml` — K8s Pod: {{ (~320 tok)
- `test-redis-ha-pod.yaml` — K8s Pod: {{ (~326 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/templates/

- `_common.tpl` (~1191 tok)
- `_helpers.tpl` (~3158 tok)
- `_versions.tpl` (~56 tok)
- `aggregate-roles.yaml` — K8s ClusterRole: {{ (~398 tok)
- `extra-manifests.yaml` (~42 tok)
- `networkpolicy-default-deny.yaml` — K8s NetworkPolicy: {{ (~117 tok)
- `NOTES.txt` (~607 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/templates/argocd-application-controller/

- `clusterrole.yaml` — K8s ClusterRole: {{ (~172 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~169 tok)
- `deployment.yaml` — K8s Deployment: {{ (~5343 tok)
- `metrics.yaml` — K8s Service: {{ (~426 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~190 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~268 tok)
- `prometheusrule.yaml` — K8s PrometheusRule: {{ (~303 tok)
- `role.yaml` — K8s Role: {{ (~315 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~167 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~214 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~606 tok)
- `statefulset.yaml` — K8s StatefulSet: {{ (~5466 tok)
- `vpa.yaml` — K8s VerticalPodAutoscaler: {{ (~316 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/templates/argocd-applicationset/

- `certificate.yaml` — K8s Certificate: {{ (~448 tok)
- `clusterrole.yaml` — K8s ClusterRole: {{ (~440 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~181 tok)
- `deployment.yaml` — K8s Deployment: {{ (~4887 tok)
- `ingress.yaml` — K8s Ingress: {{ (~688 tok)
- `metrics.yaml` — K8s Service: {{ (~442 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~249 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~278 tok)
- `role.yaml` — K8s Role: {{ (~508 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~173 tok)
- `service.yaml` — K8s Service: {{ (~275 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~222 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~627 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/templates/argocd-commit-server/

- `deployment.yaml` — K8s Deployment: {{ (~2550 tok)
- `metrics.yaml` — K8s Service: {{ (~443 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~231 tok)
- `service.yaml` — K8s Service: {{ (~256 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~227 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/templates/argocd-configs/

- `argocd-cm.yaml` — K8s ConfigMap: argocd-cm (~144 tok)
- `argocd-cmd-params-cm.yaml` — K8s ConfigMap: argocd-cmd-params-cm (~161 tok)
- `argocd-cmp-cm.yaml` — K8s ConfigMap: argocd-cmp-cm (~215 tok)
- `argocd-dex-server-tls-secret.yaml` — K8s Secret: argocd-dex-server-tls (~248 tok)
- `argocd-gpg-keys-cm.yaml` — K8s ConfigMap: argocd-gpg-keys-cm (~132 tok)
- `argocd-notifications-cm.yaml` — K8s ConfigMap: argocd-notifications-cm (~277 tok)
- `argocd-notifications-secret.yaml` — K8s Secret: {{ (~220 tok)
- `argocd-rbac-cm.yaml` — K8s ConfigMap: argocd-rbac-cm (~161 tok)
- `argocd-repo-server-tls-secret.yaml` — K8s Secret: argocd-repo-server-tls (~255 tok)
- `argocd-secret.yaml` — K8s Secret: argocd-secret (~650 tok)
- `argocd-server-tls-secret.yaml` — K8s Secret: argocd-server-tls (~229 tok)
- `argocd-ssh-known-hosts-cm.yaml` — K8s ConfigMap: argocd-ssh-known-hosts-cm (~174 tok)
- `argocd-styles-cm.yaml` — K8s ConfigMap: argocd-styles-cm (~109 tok)
- `argocd-tls-certs-cm.yaml` — K8s ConfigMap: argocd-tls-certs-cm (~149 tok)
- `cluster-secrets.yaml` — K8s Secret: {{ (~393 tok)
- `externalredis-secret.yaml` — K8s Secret: argocd-redis (~199 tok)
- `repository-credentials-secret.yaml` — K8s Secret: argocd-repo-creds-{{ (~188 tok)
- `repository-secret.yaml` — K8s Secret: argocd-repo-{{ (~174 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/templates/argocd-notifications/

- `clusterrole.yaml` — K8s ClusterRole: {{ (~328 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~183 tok)
- `deployment.yaml` — K8s Deployment: {{ (~2815 tok)
- `metrics.yaml` — K8s Service: {{ (~439 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~216 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~285 tok)
- `role.yaml` — K8s Role: {{ (~238 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~186 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: {{ (~229 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: {{ (~677 tok)

## infrastructure/controllers/argocd/charts/argo-cd-9.1.0/argo-cd/templates/argocd-repo-server/

- `clusterrole.yaml` — K8s ClusterRole: {{ (~174 tok)
- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: {{ (~182 tok)
- `deployment.yaml` — K8s Deployment: {{ (~6243 tok)
- `hpa.yaml` — K8s HorizontalPodAutoscaler: {{ (~380 tok)
- `metrics.yaml` — K8s Service: {{ (~436 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~402 tok)
- `pdb.yaml` — K8s PodDisruptionBudget: {{ (~268 tok)
- `role.yaml` — K8s Role: {{ (~132 tok)
- `rolebinding.yaml` — K8s RoleBinding: {{ (~183 tok)
