# vLLM 1-GPU vs 2-GPU Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture comparable vLLM performance data for the current two-RTX-3090 setup and a temporary one-RTX-3090 setup.

**Architecture:** Use the existing manual `benchmarks/vllm` Kubernetes Job as the synthetic benchmark. Patch only the live `vllm-server` Deployment for the one-GPU pass, then restore from the GitOps source in `my-apps/ai/vllm`.

**Tech Stack:** Kubernetes, vLLM OpenAI-compatible server, existing `benchmarks/vllm` Job, shell commands, vLLM Prometheus `/metrics`.

---

### Task 1: Capture Current Two-GPU State

**Files:**
- Read: `my-apps/ai/vllm/deployment.yaml`
- Read: `benchmarks/vllm/job.yaml`

- [ ] **Step 1: Confirm live vLLM is healthy**

Run:

```bash
kubectl get deploy,pods -n vllm -o wide
kubectl rollout status -n vllm deploy/vllm-server --timeout=5m
kubectl run curl-vllm-models --rm -i --restart=Never -n vllm --image=curlimages/curl --command -- \
  curl -s http://vllm-service.vllm.svc.cluster.local:8080/v1/models
```

Expected: rollout is successful and `/v1/models` includes `qwen3.6-27b`.

- [ ] **Step 2: Record tested args and GPU allocation**

Run:

```bash
kubectl get deploy -n vllm vllm-server -o jsonpath='{.spec.template.spec.containers[0].resources}{"\n"}{.spec.template.spec.containers[0].args}{"\n"}'
```

Expected: resources include `nvidia.com/gpu:2`, args include `--tensor-parallel-size 2`, and args include `--max-model-len 262144`.

- [ ] **Step 3: Run the benchmark Job**

Run:

```bash
kubectl delete -k benchmarks/vllm --ignore-not-found
kubectl apply -k benchmarks/vllm
kubectl logs -n vllm job/vllm-benchmark -f
```

Expected: the final log output includes `CONSOLIDATED SUMMARY`.

- [ ] **Step 4: Save a server-side metrics snapshot**

Run:

```bash
kubectl run curl-vllm-metrics --rm -i --restart=Never -n vllm --image=curlimages/curl --command -- sh -c \
  'curl -s http://vllm-service.vllm.svc.cluster.local:8080/metrics | grep -E "vllm:(num_requests_running|num_requests_waiting|gpu_cache_usage_perc|generation_tokens_total|prompt_tokens_total)"'
```

Expected: metrics are printed for `qwen3.6-27b`.

### Task 2: Patch Live vLLM to One GPU

**Files:**
- No repository files changed.

- [ ] **Step 1: Patch live Deployment resources and args**

Run:

```bash
kubectl patch deploy -n vllm vllm-server --type=json -p='[
  {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/nvidia.com~1gpu","value":"1"},
  {"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/nvidia.com~1gpu","value":"1"},
  {"op":"replace","path":"/spec/template/spec/containers/0/args/4","value":"1"},
  {"op":"replace","path":"/spec/template/spec/containers/0/args/11","value":"65536"}
]'
kubectl rollout status -n vllm deploy/vllm-server --timeout=20m
```

Expected: rollout completes successfully.

- [ ] **Step 2: Confirm one-GPU state**

Run:

```bash
kubectl get deploy -n vllm vllm-server -o jsonpath='{.spec.template.spec.containers[0].resources}{"\n"}{.spec.template.spec.containers[0].args}{"\n"}'
kubectl run curl-vllm-models --rm -i --restart=Never -n vllm --image=curlimages/curl --command -- \
  curl -s http://vllm-service.vllm.svc.cluster.local:8080/v1/models
```

Expected: resources include `nvidia.com/gpu:1`, args include `--tensor-parallel-size 1`, args include `--max-model-len 65536`, and `/v1/models` includes `qwen3.6-27b`.

### Task 3: Capture One-GPU Measurements

**Files:**
- Read: `benchmarks/vllm/job.yaml`

- [ ] **Step 1: Rerun the benchmark Job**

Run:

```bash
kubectl delete -k benchmarks/vllm --ignore-not-found
kubectl apply -k benchmarks/vllm
kubectl logs -n vllm job/vllm-benchmark -f
```

Expected: the final log output includes `CONSOLIDATED SUMMARY`.

- [ ] **Step 2: Save a server-side metrics snapshot**

Run:

```bash
kubectl run curl-vllm-metrics --rm -i --restart=Never -n vllm --image=curlimages/curl --command -- sh -c \
  'curl -s http://vllm-service.vllm.svc.cluster.local:8080/metrics | grep -E "vllm:(num_requests_running|num_requests_waiting|gpu_cache_usage_perc|generation_tokens_total|prompt_tokens_total)"'
```

Expected: metrics are printed for `qwen3.6-27b`.

### Task 4: Restore Two-GPU State

**Files:**
- Read: `my-apps/ai/vllm/deployment.yaml`

- [ ] **Step 1: Reapply GitOps source**

Run:

```bash
kubectl apply -k my-apps/ai/vllm
kubectl rollout status -n vllm deploy/vllm-server --timeout=20m
```

Expected: rollout completes successfully.

- [ ] **Step 2: Confirm restored state**

Run:

```bash
kubectl get deploy -n vllm vllm-server -o jsonpath='{.spec.template.spec.containers[0].resources}{"\n"}{.spec.template.spec.containers[0].args}{"\n"}'
kubectl run curl-vllm-models --rm -i --restart=Never -n vllm --image=curlimages/curl --command -- \
  curl -s http://vllm-service.vllm.svc.cluster.local:8080/v1/models
```

Expected: resources include `nvidia.com/gpu:2`, args include `--tensor-parallel-size 2`, args include `--max-model-len 262144`, and `/v1/models` includes `qwen3.6-27b`.
