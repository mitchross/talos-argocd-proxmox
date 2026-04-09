# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-04-09T10:00:00.149Z
> Files: 508 tracked | Anatomy hits: 0 | Misses: 0

## ./

- `.gitattributes` — Git attributes (~6 tok)
- `.gitignore` — Git ignore rules (~611 tok)
- `astro.config.mjs` — Astro configuration (~274 tok)
- `CLAUDE.md` — OpenWolf (~3081 tok)
- `firewalla-dns-config.txt` — Firewalla Local DNS Configuration for vanillax.me (~424 tok)
- `MIGRATION_EXTERNAL_DNS.md` — Migration to ExternalDNS-Based Split DNS Architecture (~1870 tok)
- `mkdocs.yml` (~269 tok)
- `package-lock.json` — npm lock file (~90080 tok)
- `package.json` — Node.js package manifest (~242 tok)
- `README.md` — Project documentation (~3991 tok)
- `thermodynamic-corridor-infographic.jsx` — sections (~7027 tok)
- `thermodynamic-corridor-summary.md` — Civilisation's Thermodynamic Corridor — Summary (~2589 tok)
- `tsconfig.json` — TypeScript configuration (~12 tok)

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

## docs/superpowers/plans/

- `2026-04-09-kyverno-cel-migration.md` — Kyverno CEL Migration + Webhook Deadlock Prevention (~8695 tok)

## infrastructure/

- `CLAUDE.md` — Infrastructure Guidelines (~869 tok)

## infrastructure/controllers/1passwordconnect/

- `kustomization.yaml` — K8s Kustomization: connect (~94 tok)
- `namespace.yaml` — K8s Namespace: 1passwordconnect (~19 tok)
- `values.yaml` (~267 tok)

## infrastructure/controllers/argocd/

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

## infrastructure/controllers/cert-manager/

- `cloudflare-external-secret.yaml` — K8s ExternalSecret: cloudflare-api-token (~161 tok)
- `cluster-issuer.yaml` — K8s ClusterIssuer: cloudflare-cluster-issuer (~199 tok)
- `kustomization.yaml` — K8s Kustomization: cert-manager (~107 tok)
- `ns.yaml` — K8s Namespace: cert-manager (~18 tok)
- `values.yaml` — Add leader election namespace to prevent RBAC permissions errors (~551 tok)

## infrastructure/controllers/external-dns/

- `cloudflare-external-secret.yaml` — K8s ExternalSecret: cloudflare-api-token (~154 tok)
- `kustomization.yaml` — K8s Kustomization: external-dns (~113 tok)
- `ns.yaml` — K8s Namespace: external-dns (~18 tok)
- `values.yaml` — ExternalDNS Helm Values for Cloudflare Integration (~579 tok)

## infrastructure/controllers/external-secrets/

- `cluster-secret-store.yaml` — K8s ClusterSecretStore: 1password (~150 tok)
- `external-secret.yaml` — K8s ExternalSecret: external-secrets (~154 tok)
- `kustomization.yaml` — K8s Kustomization: external-secrets (~285 tok)
- `ns.yaml` — K8s Namespace: external-secrets (~19 tok)
- `values.yaml` (~30 tok)

## infrastructure/controllers/gpu-priority-classes/

- `kustomization.yaml` — K8s Kustomization: gpu-priority-classes (~88 tok)
- `priority-classes.yaml` — K8s PriorityClass: gpu-workload-high (~203 tok)

## infrastructure/controllers/kyverno-vpa-policies/

- `kustomization.yaml` — K8s Kustomization (~56 tok)
- `vpa-auto-generate.yaml` — K8s ClusterPolicy: vpa-auto-generate (~1656 tok)
- `vpa-min-allowed.yaml` — K8s ClusterPolicy: vpa-min-allowed (~621 tok)

## infrastructure/controllers/kyverno/

- `CLAUDE.md` — Kyverno Backup & Restore System (~3270 tok)
- `kustomization.yaml` — K8s Kustomization: kyverno (~338 tok)
- `namespace.yaml` — K8s Namespace: kyverno (~17 tok)
- `rbac-patch.yaml` — K8s ClusterRole: kyverno:background-controller:volsync (~759 tok)
- `values.yaml` — Webhook namespace exclusions — infrastructure namespaces (Waves 0-2) must boot (~1197 tok)

## infrastructure/controllers/kyverno/policies/

- `volsync-nfs-inject.yaml` — K8s ClusterPolicy: volsync-nfs-inject (~446 tok)
- `volsync-orphan-cleanup.yaml` — K8s ClusterCleanupPolicy: volsync-orphan-cleanup (~543 tok)
- `volsync-pvc-backup-restore.yaml` — K8s ClusterPolicy: volsync-pvc-backup-restore (~2805 tok)
- `volsync-pvc-mutate.yaml` — K8s MutatingPolicy: volsync-pvc-mutate (~585 tok)
- `volsync-pvc-validate.yaml` — K8s ValidatingPolicy: volsync-pvc-validate (~405 tok)

## infrastructure/controllers/metrics-server/

- `kustomization.yaml` — K8s Kustomization: metrics-server (~92 tok)
- `namespace.yaml` — K8s Namespace: metrics-server (~19 tok)
- `values.yaml` (~37 tok)

## infrastructure/controllers/node-feature-discovery/

- `coral-tpu-rule.yaml` — NodeFeatureRule to detect Google Coral USB TPU and create a clean label. (~177 tok)
- `kustomization.yaml` — K8s Kustomization: node-feature-discovery (~476 tok)
- `ns.yaml` — K8s Namespace: node-feature-discovery (~38 tok)

## infrastructure/controllers/nvidia-device-plugin/

- `config.yaml` — K8s ConfigMap: nvidia-device-plugin-config (~195 tok)
- `kustomization.yaml` — K8s Kustomization: nvidia-device-plugin (~199 tok)
- `namespace.yaml` — K8s Namespace: gpu-device-plugin (~115 tok)
- `nvidia-device-plugin.yml` — K8s DaemonSet: nvidia-device-plugin-daemonset (~994 tok)
- `nvidia-powerlimit-daemonset.yaml` — K8s DaemonSet: nvidia-powerlimit-daemonset (~600 tok)
- `rbac.yaml` — K8s ServiceAccount: nvidia-device-plugin (~303 tok)
- `README.md` — Project documentation (~2514 tok)
- `runtime.yaml` — K8s RuntimeClass: nvidia (~26 tok)
- `service.yaml` — K8s Service: nvidia-device-plugin-metrics (~190 tok)

## infrastructure/controllers/nvidia-gpu-operator/

- `cluster-policy.yaml` — K8s ClusterPolicy: cluster-policy (~170 tok)
- `external-secret.yaml` — K8s ExternalSecret: nvidia-api-key (~268 tok)
- `kustomization.yaml` — K8s Kustomization: gpu-operator (~491 tok)
- `namespace.yaml` — K8s Namespace: gpu-operator (~36 tok)
- `preinstalled-validation-daemonset.yaml` — K8s DaemonSet: nvidia-preinstalled-validation-markers (~408 tok)
- `test-pod.yaml` — K8s Pod: cuda-vectoradd (~91 tok)
- `time-slicing-config.yaml` — K8s ConfigMap: time-slicing-config (~148 tok)
- `toolkit-validation-job.yaml` — K8s Job: nvidia-toolkit-validation (~312 tok)

## infrastructure/controllers/opentelemetry-operator/

- `collector-agent.yaml` — start_at: end (~907 tok)
- `collector-gateway.yaml` — K8s OpenTelemetryCollector: otel-gateway (~1106 tok)
- `externalsecret.yaml` — K8s ExternalSecret: honeycomb-api-key (~106 tok)
- `instrumentation.yaml` — K8s Instrumentation: default (~329 tok)
- `kustomization.yaml` — K8s Kustomization: opentelemetry-operator (~138 tok)
- `ns.yaml` — K8s Namespace: opentelemetry (~70 tok)
- `rbac.yaml` — K8s ServiceAccount: otel-agent (~614 tok)
- `values.yaml` (~77 tok)

## infrastructure/controllers/pvc-plumber/

- `deployment.yaml` — K8s Deployment: pvc-plumber (~807 tok)
- `externalsecret.yaml` — K8s ExternalSecret: pvc-plumber-kopia (~128 tok)
- `kustomization.yaml` — K8s Kustomization (~36 tok)

## infrastructure/controllers/vertical-pod-autoscaler/

- `kustomization.yaml` — K8s Kustomization: vertical-pod-autoscaler (~102 tok)
- `namespace.yaml` — K8s Namespace: vertical-pod-autoscaler (~21 tok)
- `README.md` — Project documentation (~510 tok)
- `values.yaml` (~152 tok)

## infrastructure/database/

- `CLAUDE.md` — Database Guidelines (CNPG CloudNativePG) (~1099 tok)

## infrastructure/database/cloudnative-pg/cloudnative-pg-operator/

- `clusterrole-full-rbac.yaml` — K8s ClusterRole: cloudnative-pg-operator-full-rbac (~234 tok)
- `clusterrolebinding-full-rbac.yaml` — K8s ClusterRoleBinding: cloudnative-pg-operator-full-rbac (~134 tok)
- `kustomization.yaml` — K8s Kustomization: cloudnative-pg (~296 tok)
- `namespace.yaml` — K8s Namespace: cloudnative-pg (~19 tok)

## infrastructure/database/cloudnative-pg/gitea/

- `cluster.yaml` — K8s Cluster: gitea-database (~685 tok)
- `externalsecret.yaml` — K8s ExternalSecret: gitea-app-secret (~145 tok)
- `kustomization.yaml` — K8s Kustomization: gitea-db (~90 tok)
- `scheduled-backup.yaml` — K8s ScheduledBackup: gitea-daily-backup (~67 tok)

## infrastructure/database/cloudnative-pg/immich/

- `cluster.yaml` — K8s Cluster: immich-database (~616 tok)
- `externalsecret.yaml` — K8s ExternalSecret: immich-app-secret (~146 tok)
- `kustomization.yaml` — K8s Kustomization: immich-db (~90 tok)
- `scheduled-backup.yaml` — K8s ScheduledBackup: immich-daily-backup (~68 tok)

## infrastructure/database/cloudnative-pg/khoj/

- `cluster.yaml` — K8s Cluster: khoj-database (~992 tok)
- `externalsecret.yaml` — Add this new section for khoj (~506 tok)
- `kustomization.yaml` — K8s Kustomization: khoj-db (~89 tok)
- `scheduled-backup.yaml` — K8s ScheduledBackup: khoj-daily-backup (~67 tok)

## infrastructure/database/cloudnative-pg/paperless/

- `cluster.yaml` — K8s Cluster: paperless-database (~968 tok)
- `externalsecret.yaml` — Add this new section for paperless-ngx (~370 tok)
- `kustomization.yaml` — K8s Kustomization: paperless-db (~91 tok)
- `scheduled-backup.yaml` — K8s ScheduledBackup: paperless-daily-backup (~70 tok)

## infrastructure/database/cloudnative-pg/postgres-global-secrets/

- `externalsecret.yaml` — K8s ExternalSecret: postgres-superuser-secret (~566 tok)
- `kustomization.yaml` — K8s Kustomization: postgres-global-secrets (~82 tok)

## infrastructure/database/crunchy-postgres/postgres-operator/

- `kustomization.yaml` — K8s Kustomization: pgo (~94 tok)
- `ns.yaml` — K8s Namespace: postgres-operator (~20 tok)
- `values.yaml` — Crunchy Data PostgreSQL Operator configuration (~115 tok)

## infrastructure/database/redis/redis-commander/

- `deployment.yaml` — K8s Deployment: redis-commander (~183 tok)
- `httproute.yaml` — K8s HTTPRoute: redis-commander (~146 tok)
- `kustomization.yaml` — K8s Kustomization: redis-commander (~75 tok)
- `namespace.yaml` — K8s Namespace: redis (~16 tok)
- `service.yaml` — K8s Service: redis-commander (~78 tok)

## infrastructure/database/redis/redis-instance/

- `kustomization.yaml` — K8s Kustomization: redis (~240 tok)
- `namespace.yaml` — K8s Namespace: redis-instance (~35 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: redis-master-0 (~150 tok)
- `service.yaml` — K8s Service: redis-external (~124 tok)

## infrastructure/networking/

- `CLAUDE.md` — Networking Guidelines (~418 tok)
- `README.md` — Project documentation (~2182 tok)

## infrastructure/networking/cilium/

- `ip-pool.yaml` — K8s CiliumLoadBalancerIPPool: first-pool (~208 tok)
- `kustomization.yaml` — K8s Kustomization: cilium (~178 tok)
- `l2-announcement.yaml.disabled` (~177 tok)
- `l2-policy.yaml` — K8s CiliumL2AnnouncementPolicy: l2-policy (~255 tok)
- `values.yaml` — Cilium Helm Values for Talos Proxmox Production Cluster (~990 tok)

## infrastructure/networking/cilium/policies/

- `block-lan-access.yaml` — K8s CiliumClusterwideNetworkPolicy: default-deny-lan-egress (~898 tok)

## infrastructure/networking/cloudflared/

- `config-explicit.yaml.example` — OPTIONAL: Explicit Cloudflare Tunnel Config (~562 tok)
- `config.yaml` (~788 tok)
- `deployment.yaml` — K8s Deployment: cloudflared (~671 tok)
- `external-secret.yaml` — K8s ExternalSecret: tunnel-credentials (~148 tok)
- `kustomization.yaml` — K8s Kustomization: config (~79 tok)
- `ns.yaml` — K8s Namespace: cloudflared (~18 tok)

## infrastructure/networking/gateway/

- `gw-external.yaml` — K8s Gateway: gateway-external (~319 tok)
- `gw-internal.yaml` — K8s Gateway: gateway-internal (~299 tok)
- `httproute-argocd.yaml` — K8s HTTPRoute: argocd (~150 tok)
- `httproute-longhorn.yaml` — K8s HTTPRoute: longhorn (~154 tok)
- `kustomization.yaml` — K8s Kustomization (~71 tok)
- `ns.yaml` — K8s Namespace: gateway (~16 tok)

## infrastructure/storage/

- `CLAUDE.md` — Storage Guidelines (~1168 tok)

## infrastructure/storage/container-registry/

- `configmap.yaml` — K8s ConfigMap: registry-config (~120 tok)
- `deployment.yaml` — K8s Deployment: registry (~209 tok)
- `httproute.yaml` — K8s HTTPRoute: registry (~127 tok)
- `kustomization.yaml` — K8s Kustomization (~54 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: registry (~166 tok)
- `service.yaml` — K8s Service: registry (~56 tok)

## infrastructure/storage/csi-driver-nfs/

- `kustomization.yaml` — K8s Kustomization: csi-driver-nfs (~133 tok)
- `namespace.yaml` — K8s Namespace: csi-driver-nfs (~79 tok)
- `storage-class.yaml` — 10G NFS Storage Classes (192.168.10.133) - via 10G switch (~550 tok)
- `values.yaml` — NFS CSI deployment (~51 tok)

## infrastructure/storage/csi-driver-smb/

- `external-secret.yaml` — K8s ExternalSecret: smbcreds (~191 tok)
- `kustomization.yaml` — K8s Kustomization: csi-driver-smb (~122 tok)
- `namespace.yaml` — K8s Namespace: csi-driver-smb (~79 tok)
- `storage-class.yaml` — 10G SMB Storage Classes (192.168.10.133) - Optimized for 10G (~1095 tok)
- `values.yaml` (~44 tok)

## infrastructure/storage/kopia-ui/

- `configmap.yaml` — K8s ConfigMap: kopia-ui-config (~113 tok)
- `deployment.yaml` — K8s Deployment: kopia-ui (~800 tok)
- `externalsecret.yaml` — K8s ExternalSecret: kopia-ui-secrets (~111 tok)
- `httproute.yaml` — K8s HTTPRoute: kopia-ui (~150 tok)
- `kustomization.yaml` — K8s Kustomization (~58 tok)
- `namespace.yaml` — K8s Namespace: kopia-ui (~32 tok)

## infrastructure/storage/local-storage/

- `kustomization.yaml` — K8s Kustomization (~43 tok)
- `namespace.yaml` — K8s Namespace: local-storage (~18 tok)
- `native-storage-class.yaml` — K8s StorageClass: local-storage (~76 tok)

## infrastructure/storage/longhorn/

- `httproute.yaml` — K8s HTTPRoute: longhorn (~164 tok)
- `kustomization.yaml` — K8s Kustomization: longhorn (~114 tok)
- `namespace.yaml` — K8s Namespace: longhorn-system (~52 tok)
- `node-failure-settings.yaml` — Longhorn Node Failure and Recovery Settings (~910 tok)
- `values.yaml` — It's recommended to manage all Longhorn settings via this file (~832 tok)
- `volumesnapshotclass.yaml` — K8s VolumeSnapshotClass: longhorn (~70 tok)

## infrastructure/storage/snapshot-controller/

- `kustomization.yaml` — K8s Kustomization: snapshot-controller (~101 tok)
- `namespace.yaml` — K8s Namespace: snapshot-controller (~53 tok)
- `values.yaml` — Standard values for generic snapshot-controller (~158 tok)

## infrastructure/storage/volsync/

- `kustomization.yaml` — K8s Kustomization: volsync (~103 tok)
- `namespace.yaml` — K8s Namespace: volsync-system (~51 tok)
- `values.yaml` — VolSync Helm chart values (~203 tok)
- `volumesnapshotclass.yaml` — K8s VolumeSnapshotClass: longhorn-snapclass (~84 tok)

## monitoring/

- `CLAUDE.md` — Monitoring Guidelines (~673 tok)
- `README.md` — Project documentation (~1178 tok)

## monitoring/k8sgpt/

- `grafana-dashboard.yaml` — K8s ConfigMap: k8sgpt-grafana-dashboard (~2720 tok)
- `k8sgpt.yaml` — K8s K8sGPT: k8sgpt (~178 tok)
- `kustomization.yaml` — K8s Kustomization: k8sgpt-operator (~100 tok)
- `ns.yaml` — K8s Namespace: k8sgpt (~16 tok)
- `values.yaml` — K8sGPT Operator Helm values (~113 tok)

## monitoring/loki-stack/

- `externalsecret.yaml` — K8s ExternalSecret: loki-s3-credentials (~143 tok)
- `kustomization.yaml` — K8s Kustomization: loki (~101 tok)
- `loki-http-route.yaml` — K8s HTTPRoute: loki (~142 tok)
- `ns.yaml` — K8s Namespace: loki-stack (~26 tok)
- `values.yaml` (~488 tok)

## monitoring/pod-cleanup/

- `cronjob.yaml` — K8s CronJob: pod-cleanup (~261 tok)
- `kustomization.yaml` — K8s Kustomization (~41 tok)
- `namespace.yaml` — K8s Namespace: pod-cleanup (~18 tok)
- `rbac.yaml` — K8s ServiceAccount: pod-cleanup (~150 tok)

## monitoring/prometheus-stack/

- `alertmanager-config.yaml` — K8s Secret: alertmanager-kube-prometheus-stack-alertmanager (~1017 tok)
- `alertmanager-http-route.yaml` — K8s HTTPRoute: alertmanager (~155 tok)
- `custom-alerts.yaml` — K8s PrometheusRule: custom-cluster-alerts (~2220 tok)
- `custom-servicemonitors.yaml` — ArgoCD metrics are handled by the argo-cd Helm chart's built-in ServiceMonitors (~947 tok)
- `dcgm-exporter.yaml` — K8s DaemonSet: dcgm-exporter (~910 tok)
- `frigate-dashboard.yaml` — K8s ConfigMap: frigate-dashboard (~1438 tok)
- `gpu-alerts.yaml` — K8s PrometheusRule: gpu-alerts (~874 tok)
- `gpu-dashboard.yaml` — K8s ConfigMap: gpu-dashboard (~18867 tok)
- `GPU-MONITORING.md` — GPU Monitoring with DCGM Exporter (~683 tok)
- `grafana-http-route.yaml` — K8s HTTPRoute: grafana (~150 tok)
- `kustomization.yaml` — K8s Kustomization: kube-prometheus-stack (~356 tok)
- `loki-logs-dashboard.yaml` — K8s ConfigMap: loki-logs-dashboard (~1404 tok)
- `longhorn-backup-alerts.yaml` — K8s PrometheusRule: longhorn-backup-alerts (~3028 tok)
- `network-policy.yaml` — K8s CiliumNetworkPolicy: allow-grafana-to-prometheus (~186 tok)
- `ns.yaml` — K8s Namespace: prometheus-stack (~86 tok)
- `prometheus-http-route.yaml` — K8s HTTPRoute: prometheus (~153 tok)
- `solar-dashboard.yaml` — K8s ConfigMap: solar-dashboard (~13474 tok)
- `values.yaml` — Enhanced kube-prometheus-stack configuration (~4130 tok)
- `volsync-alerts.yaml` — K8s PrometheusRule: volsync-alerts (~1953 tok)
- `vpa-alerts.yaml` — K8s PrometheusRule: vpa-alerts (~1141 tok)
- `vpa-overview-dashboard.yaml` — K8s ConfigMap: vpa-overview-dashboard (~7117 tok)

## monitoring/tempo/

- `externalsecret.yaml` — K8s ExternalSecret: tempo-s3-credentials (~155 tok)
- `kustomization.yaml` — K8s Kustomization: tempo (~79 tok)
- `ns.yaml` — K8s Namespace: monitoring (~18 tok)
- `values.yaml` (~143 tok)

## my-apps/

- `CLAUDE.md` — Application Guidelines (~1626 tok)

## my-apps/ai/

- `CLAUDE.md` — AI / GPU Workload Guidelines (~348 tok)
- `README.md` — Project documentation (~3376 tok)

## my-apps/ai/comfyui/

- `configmap.yaml` — K8s ConfigMap: comfyui-manager-config (~3635 tok)
- `deployment.yaml` — K8s Deployment: comfyui (~969 tok)
- `download-models-job.yaml` — K8s Job: comfyui-download-models (~1445 tok)
- `externalsecret.yaml` — K8s ExternalSecret: comfyui-secrets (~132 tok)
- `httproute.yaml` — K8s HTTPRoute: comfyui-route (~146 tok)
- `kustomization.yaml` — K8s Kustomization (~118 tok)
- `namespace.yaml` — K8s Namespace: comfyui (~17 tok)
- `pvc.yaml` — Static PV - mounts NFS share root directly via CSI (not a CSI-created subdirectory) (~265 tok)
- `README.md` — Project documentation (~1126 tok)
- `service.yaml` — K8s Service: comfyui-service (~130 tok)

## my-apps/ai/comfyui/custom-nodes/

- `image_to_llamacpp_base64.py` — Bridge nodes for LlamaCpp vision integration in ComfyUI. (~2497 tok)

## my-apps/ai/comfyui/workflows/

- `florence2-caption.json` (~195 tok)
- `llamacpp-vision-to-image.json` — Declares your (~1958 tok)
- `wan22-i2v.json` (~548 tok)
- `wan22-t2v.json` (~431 tok)
- `wd14-tagger.json` (~138 tok)
- `z-image-turbo-t2i.json` (~405 tok)

## my-apps/ai/llama-cpp/

- `configmap.yaml` — K8s ConfigMap: llama-cpp-config (~1359 tok)
- `deployment.yaml` — K8s Deployment: llama-cpp-server (~1367 tok)
- `httproute.yaml` — K8s HTTPRoute: llama-cpp-route (~151 tok)
- `kustomization.yaml` — K8s Kustomization (~59 tok)
- `namespace.yaml` — K8s Namespace: llama-cpp (~17 tok)
- `pvc.yaml` — Static PV - mounts NFS share root directly via CSI (not a CSI-created subdirectory) (~270 tok)
- `service.yaml` — K8s Service: llama-cpp-service (~109 tok)

## my-apps/ai/llmfit/

- `dual-gpu-output.json` (~1630 tok)
- `job-dual-gpu.yaml` — K8s Job: llmfit-dual-gpu (~335 tok)
- `job-single-gpu.yaml` — K8s Job: llmfit-single-gpu (~318 tok)
- `kustomization.yaml` — K8s Kustomization (~47 tok)
- `namespace.yaml` — K8s Namespace: llmfit (~16 tok)

## my-apps/ai/open-webui/

- `configmap.yaml` — K8s ConfigMap: open-webui-configmap (~1849 tok)
- `deployment.yaml` — K8s Deployment: open-webui (~408 tok)
- `function-loader-job.yaml` — K8s Job: load-har-analyzer-v5 (~996 tok)
- `har-analyzer-function.py` — Pydantic: Valves (12 fields) (~7115 tok)
- `httproute.yaml` — K8s HTTPRoute: open-webui (~149 tok)
- `KIWIX_RAG_INSTRUCTIONS.md` — Kiwix RAG Setup Instructions (~586 tok)
- `kustomization.yaml` — K8s Kustomization: har-analyzer-function (~118 tok)
- `mcp-config.yaml` — K8s ConfigMap: mcp-config (~657 tok)
- `mcp-kiwix.yaml` — Kiwix MCP Server - uses fetch to query Kiwix HTTP API (~604 tok)
- `mcpo-deployment.yaml` — K8s Deployment: mcpo (~456 tok)
- `namespace.yaml` — K8s Namespace: open-webui (~34 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: storage (~115 tok)
- `README.md` — Project documentation (~406 tok)
- `SEARXNG-SETUP.md` — SearXNG Integration with Open WebUI (~1175 tok)
- `service.yaml` — K8s Service: open-webui (~66 tok)

## my-apps/ai/perplexica/

- `deployment.yaml` — K8s Deployment: perplexica (~488 tok)
- `httproute.yaml` — K8s HTTPRoute: perplexica-route (~129 tok)
- `kustomization.yaml` — K8s Kustomization (~54 tok)
- `namespace.yaml` — K8s Namespace: perplexica (~18 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: perplexica-data (~71 tok)
- `service.yaml` — K8s Service: perplexica (~64 tok)

## my-apps/common/deployment-defaults/

- `README.md` — Project documentation (~1061 tok)

## my-apps/development/convertx/

- `deployment.yaml` — K8s Deployment: convertx (~290 tok)
- `httproute.yaml` — K8s HTTPRoute: convertx-route (~183 tok)
- `kustomization.yaml` — K8s Kustomization (~48 tok)
- `ns.yaml` — K8s Namespace: convertx (~17 tok)
- `service.yaml` — K8s Service: convertx (~58 tok)

## my-apps/development/dvwa/

- `deployment.yaml` — K8s Deployment: dvwa (~311 tok)
- `httproute.yaml` — K8s HTTPRoute: dvwa-route (~178 tok)
- `kustomization.yaml` — WARNING: PENTEST / SECURITY TESTING ONLY (~219 tok)
- `ns.yaml` — K8s Namespace: dvwa (~30 tok)
- `service.yaml` — K8s Service: dvwa (~65 tok)

## my-apps/development/excalidraw/

- `deployment.yaml` — K8s Deployment: excalidraw (~194 tok)
- `httproute.yaml` — K8s HTTPRoute: excalidraw (~152 tok)
- `kustomization.yaml` — K8s Kustomization (~50 tok)
- `namespace.yaml` — K8s Namespace: excalidraw (~18 tok)
- `service.yaml` — K8s Service: excalidraw (~58 tok)

## my-apps/development/fizzy/

- `deployment.yaml` — K8s Deployment: fizzy (~422 tok)
- `externalsecret.yaml` — K8s ExternalSecret: fizzy-secrets (~135 tok)
- `httproute.yaml` — K8s HTTPRoute: fizzy-route (~180 tok)
- `kustomization.yaml` — K8s Kustomization (~57 tok)
- `ns.yaml` — K8s Namespace: fizzy (~32 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: data (~108 tok)
- `service.yaml` — K8s Service: fizzy (~56 tok)

## my-apps/development/gitea/

- `deployment.yaml` (~0 tok)
- `externalsecret.yaml` — K8s ExternalSecret: gitea-db-secret (~110 tok)
- `fix-permissions-patch.yaml` — K8s Deployment: gitea (~161 tok)
- `httproute.yaml` — K8s HTTPRoute: gitea (~128 tok)
- `kustomization.yaml` — K8s Kustomization: gitea (~111 tok)
- `namespace.yaml` — K8s Namespace: gitea (~16 tok)
- `pvc.yaml` (~0 tok)
- `release.yaml` (~0 tok)
- `repository.yaml` (~0 tok)
- `service.yaml` (~0 tok)
- `values.yaml` (~304 tok)

## my-apps/development/headlamp/

- `clusterrolebinding.yaml` — K8s ClusterRoleBinding: headlamp-admin (~79 tok)
- `httproute.yaml` — K8s HTTPRoute: headlamp (~144 tok)
- `kustomization.yaml` — K8s Kustomization: headlamp (~158 tok)
- `metrics-role.yaml` — K8s ClusterRole: headlamp-metrics-viewer (~222 tok)
- `namespace.yaml` — K8s Namespace: kube-system (~18 tok)
- `patch-remove-session-ttl.yaml` — K8s Deployment: headlamp (~84 tok)
- `serviceaccount.yaml` — K8s ServiceAccount: headlamp-admin (~27 tok)
- `token-secret.yaml` — K8s Secret: headlamp-admin-token (~59 tok)
- `values.yaml` — Disable features we're handling separately (~239 tok)

## my-apps/development/it-tools/

- `deployment.yaml` — K8s Deployment: it-tools (~202 tok)
- `httproute.yaml` — K8s HTTPRoute: it-tools-route (~228 tok)
- `kustomization.yaml` — K8s Kustomization (~47 tok)
- `ns.yaml` — K8s Namespace: it-tools (~17 tok)
- `service.yaml` — K8s Service: it-tools (~58 tok)

## my-apps/development/kafka/

- `kafka-cluster.yaml` (~0 tok)
- `kustomization.yaml` — K8s Kustomization: kafka (~62 tok)
- `podmonitor.yaml` (~0 tok)
- `topics.yaml` (~0 tok)

## my-apps/development/mailpit/

- `deployment.yaml` — K8s Deployment: mailpit (~280 tok)
- `httproute.yaml` — K8s HTTPRoute: mailpit-route (~182 tok)
- `kustomization.yaml` — K8s Kustomization (~47 tok)
- `ns.yaml` — K8s Namespace: mailpit (~17 tok)
- `service.yaml` — K8s Service: mailpit (~84 tok)

## my-apps/development/n8n/

- `httproute.yaml` — K8s HTTPRoute: n8n (~149 tok)
- `kustomization.yaml` — K8s Kustomization: n8n (~116 tok)
- `namespace.yaml` — K8s Namespace: n8n (~56 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: data (~110 tok)
- `values.yaml` (~559 tok)

## my-apps/development/n8n/workflows/

- `daily-cluster-report.json` — Declares nodeReady (~3710 tok)
- `paperless-auto-tagger.json` — Declares response (~4005 tok)
- `vehicle-search.json` — Declares searches (~7419 tok)

## my-apps/development/news-reader/

- `deployment.yaml` — K8s Deployment: news-reader (~206 tok)
- `httproute.yaml` — K8s HTTPRoute: news-reader (~182 tok)
- `kustomization.yaml` — K8s Kustomization (~43 tok)
- `namespace.yaml` — K8s Namespace: news-reader (~18 tok)
- `service.yaml` — K8s Service: news-reader (~60 tok)

## my-apps/development/news-reader/app/

- `.gitignore` — Git ignore rules (~128 tok)
- `AGENTS.md` — This is NOT the Next.js you know (~82 tok)
- `CLAUDE.md` (~3 tok)
- `Dockerfile` — Docker container definition (~92 tok)
- `next.config.ts` — Next.js configuration (~52 tok)
- `package-lock.json` — npm lock file (~20817 tok)
- `package.json` — Node.js package manifest (~139 tok)
- `postcss.config.mjs` — Declares config (~26 tok)
- `README.md` — Project documentation (~363 tok)
- `tsconfig.json` — TypeScript configuration (~191 tok)

## my-apps/development/news-reader/app/app/

- `globals.css` — Styles: 3 rules, 8 vars, 1 media queries (~140 tok)
- `layout.tsx` — geist (~152 tok)
- `page.tsx` — CATEGORY_LABELS — uses useState, useCallback, useEffect (~2294 tok)

## my-apps/development/news-reader/app/app/api/digests/

- `route.ts` — Next.js API route: GET (~91 tok)

## my-apps/development/news-reader/app/app/api/trigger/

- `route.ts` — Next.js API route: POST (~135 tok)

## my-apps/development/news-reader/app/app/lib/

- `temporal.ts` — Exports Article, DigestResult, DigestInfo, getDigests, triggerDigest (~600 tok)

## my-apps/development/nginx/

- `deployment.yaml` — K8s Deployment: nginx-example (~134 tok)
- `httproute.yaml` — File: nginx/httproute.yaml (~150 tok)
- `kustomization.yaml` — File: nginx/kustomization.yaml (~64 tok)
- `namespace.yaml` — File: nginx/namespace.yaml (~42 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: storage (~110 tok)
- `service.yaml` — nginx-service.yaml (~206 tok)

## my-apps/development/pairdrop/

- `deployment.yaml` — K8s Deployment: pairdrop (~422 tok)
- `httproute.yaml` — K8s HTTPRoute: pairdrop-route (~132 tok)
- `kustomization.yaml` — K8s Kustomization (~45 tok)
- `ns.yaml` — K8s Namespace: pairdrop (~17 tok)
- `service.yaml` — K8s Service: pairdrop (~68 tok)

## my-apps/development/posthog/

- `configmap-env.yaml` — K8s ConfigMap: posthog-env (~514 tok)
- `externalsecret.yaml` — K8s ExternalSecret: posthog-secrets (~383 tok)
- `httproute.yaml` — K8s HTTPRoute: posthog-ui-internal (~414 tok)
- `kustomization.yaml` — K8s Kustomization (~158 tok)
- `namespace.yaml` — K8s Namespace: posthog (~58 tok)

## my-apps/development/posthog/config/

- `kustomization.yaml` — K8s Kustomization: clickhouse-config (~147 tok)

## my-apps/development/posthog/config/clickhouse/

- `config.xml` (~5122 tok)
- `user_defined_function.xml` — Declares for (~2976 tok)
- `users.xml` (~2276 tok)

## my-apps/development/posthog/config/clickhouse/config.d/

- `default.xml` (~547 tok)
- `keeper.xml` (~220 tok)

## my-apps/development/posthog/config/clickhouse/docker-entrypoint-initdb.d/

- `init-posthog.sh` (~42 tok)

## my-apps/development/posthog/core/

- `capture.yaml` — K8s Deployment: capture (~1937 tok)
- `clickhouse-init.yaml` — K8s Job: clickhouse-migrations-init (~900 tok)
- `ingestion.yaml` — Ingestion General - consumes from events_plugin_ingestion, processes events, (~874 tok)
- `jobs.yaml` — K8s Job: kafka-init (~1397 tok)
- `microservices.yaml` — Livestream - real-time event streaming (disabled: requires GeoIP MMDB file) (~1992 tok)
- `plugins.yaml` — K8s Deployment: plugins (~1162 tok)
- `web.yaml` — K8s Deployment: web (~941 tok)
- `workers.yaml` — K8s Deployment: worker (~711 tok)

## my-apps/development/posthog/data-layer/

- `clickhouse.yaml` — K8s StatefulSet: clickhouse (~1016 tok)
- `kafka.yaml` — K8s StatefulSet: kafka (~847 tok)
- `postgres.yaml` — K8s Deployment: db (~653 tok)
- `redis.yaml` — K8s Deployment: redis7 (~504 tok)

## my-apps/development/stirling-pdf/

- `deployment.yaml` — K8s Deployment: stirling-pdf (~292 tok)
- `httproute.yaml` — K8s HTTPRoute: stirling-pdf (~147 tok)
- `kustomization.yaml` — K8s Kustomization (~50 tok)
- `namespace.yaml` — K8s Namespace: stirling-pdf (~18 tok)
- `service.yaml` — K8s Service: stirling-pdf (~60 tok)

## my-apps/development/strimzi/

- `kustomization.yaml` — K8s Kustomization: strimzi (~106 tok)
- `namespace.yaml` — K8s Namespace: kafka (~17 tok)
- `values.yaml` (~121 tok)

## my-apps/development/temporal-worker/

- `deployment.yaml` — K8s Deployment: temporal-worker (~169 tok)
- `Dockerfile` — Docker container definition (~43 tok)
- `kustomization.yaml` — K8s Kustomization (~33 tok)
- `namespace.yaml` — K8s Namespace: temporal-worker (~19 tok)

## my-apps/development/temporal-worker/app/

- `requirements.txt` — Python dependencies (~8 tok)
- `worker.py` — import: strip_thinking, fetch_feed, summarize_article, generate_digest_headline + 2 more (~3393 tok)

## my-apps/development/temporal/

- `httproute.yaml` — K8s HTTPRoute: temporal-web (~146 tok)
- `kustomization.yaml` — K8s Kustomization: temporal (~167 tok)
- `namespace.yaml` — K8s Namespace: temporal (~17 tok)
- `values.yaml` (~738 tok)

## my-apps/development/vert/

- `deployment.yaml` — K8s Deployment: vert (~311 tok)
- `httproute.yaml` — K8s HTTPRoute: vert-route (~222 tok)
- `kustomization.yaml` — K8s Kustomization (~55 tok)
- `ns.yaml` — K8s Namespace: vert (~33 tok)
- `service.yaml` — K8s Service: vert (~58 tok)
- `vertd-deployment.yaml` — K8s Deployment: vertd (~428 tok)
- `vertd-service.yaml` — K8s Service: vertd (~61 tok)

## my-apps/home/frigate/

- `config.yml` (~1716 tok)
- `deployment.yaml` — K8s Deployment: frigate (~864 tok)
- `externalsecret.yaml` — K8s ExternalSecret: frigate-secrets (~429 tok)
- `httproute.yaml` — K8s HTTPRoute: frigate (~133 tok)
- `kustomization.yaml` — K8s Kustomization: frigate-configmap (~108 tok)
- `namespace.yaml` — K8s Namespace: frigate (~62 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: frigate-config (~150 tok)
- `README.md` — Project documentation (~1347 tok)
- `service.yaml` — K8s Service: frigate-http (~132 tok)
- `servicemonitor.yaml` — K8s ServiceMonitor: frigate (~90 tok)

## my-apps/home/frigate/mqtt/

- `mqtt.yaml` — K8s ConfigMap: mosquitto-configmap (~760 tok)

## my-apps/home/home-assistant/

- `automations.yaml` — Automations will be managed from the UI (~13 tok)
- `configuration.yaml` — Loads default set of integrations. Do not remove. (~246 tok)
- `deployment.yaml` — K8s Deployment: home-assistant (~1608 tok)
- `httproute.yaml` — K8s HTTPRoute: home-assistant (~254 tok)
- `kustomization.yaml` — K8s Kustomization: home-assistant (~195 tok)
- `namespace.yaml` — K8s Namespace: home-assistant (~95 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: config (~128 tok)
- `scenes.yaml` — Scenes will be managed from the UI (~12 tok)
- `scripts.yaml` — Scripts will be managed from the UI (~12 tok)
- `service.yaml` — K8s Service: home-assistant (~229 tok)

## my-apps/home/paperless-ngx/

- `configmap.yaml` — K8s ConfigMap: paperless-config (~285 tok)
- `deployment.yaml` — K8s Deployment: paperless-ngx (~720 tok)
- `externalsecret.yaml` — K8s ExternalSecret: paperless-ngx-credentials (~284 tok)
- `httproute.yaml` — K8s HTTPRoute: paperless-ngx (~148 tok)
- `kustomization.yaml` — K8s Kustomization: paperless-ngx (~100 tok)
- `namespace.yaml` — K8s Namespace: paperless-ngx (~34 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: data (~362 tok)
- `service.yaml` — K8s Service: paperless-ngx (~71 tok)
- `tika-gotenberg.yaml` — K8s Deployment: tika (~603 tok)

## my-apps/home/project-nomad/

- `configmap.yaml` — K8s ConfigMap: project-nomad-config (~503 tok)
- `externalsecret.yaml` — K8s ExternalSecret: project-nomad-secrets (~176 tok)
- `kustomization.yaml` — K8s Kustomization (~386 tok)
- `namespace.yaml` — K8s Namespace: project-nomad (~18 tok)

## my-apps/home/project-nomad/cyberchef/

- `deployment.yaml` — K8s Deployment: cyberchef (~211 tok)
- `httproute.yaml` — K8s HTTPRoute: cyberchef (~183 tok)
- `service.yaml` — K8s Service: cyberchef (~75 tok)

## my-apps/home/project-nomad/embeddings/

- `deployment.yaml` — K8s Deployment: embeddings (~393 tok)
- `pvc.yaml` — K8s PersistentVolumeClaim: embeddings-model-cache (~57 tok)
- `service.yaml` — K8s Service: embeddings (~69 tok)

## my-apps/home/project-nomad/flatnotes/

- `deployment.yaml` — K8s Deployment: flatnotes (~282 tok)
- `httproute.yaml` — K8s HTTPRoute: flatnotes (~183 tok)
