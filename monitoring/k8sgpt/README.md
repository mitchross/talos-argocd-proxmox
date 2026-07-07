# k8sgpt

AI-assisted Kubernetes diagnostics backed by the in-cluster vLLM service.

This app is auto-discovered by the `monitoring/*` ApplicationSet as
`monitoring-k8sgpt`. Do not add a manual ArgoCD `Application`.

## Backend

The `K8sGPT` CR uses the OpenAI-compatible vLLM endpoint:

```text
http://vllm-service.vllm.svc.cluster.local:8080/v1
```

Model:

```text
qwen3.6-27b
```

The `Secret` in this directory is intentionally inline. It is only a non-empty
placeholder because the k8sgpt CLI insists on a configured password; vLLM does
not validate it.

The Secret name still contains `llama-cpp` for historical continuity. Do not
rename it just to make the name pretty; the current `K8sGPT` CR points at vLLM.

## Operator cadence

Keep `spec.analysis.interval` set. Without it, the operator requeues every
~30s and runs continuous full-cluster analysis against vLLM, which is too much
background inference load for the single-GPU cluster.

Current setting:

```yaml
spec:
  analysis:
    interval: 6h
```

Use a shorter interval only when you explicitly want fresher `Result` CRs.
`autoRemediation` is not enabled; this deployment is diagnostics-only.

## Backend availability

k8sgpt depends on vLLM being scaled up. During GPU scale-swaps where vLLM is set
to `replicas: 0`, the operator may log backend errors and stop producing fresh
`Result` CRs. That is expected; restore vLLM before treating k8sgpt failures as
a cluster-diagnostics issue.

## Local checks

```bash
kubectl -n k8sgpt get pods,k8sgpt,results
kubectl -n k8sgpt logs deploy/k8sgpt --tail=80
kubectl -n k8sgpt logs deploy/k8sgpt-operator-controller-manager -c manager --tail=80
```

The generated `k8sgpt` Deployment currently needs the local
`mutating-admission-policy.yaml` workaround so it starts as:

```text
k8sgpt serve --backend localai
```

Remove that policy only after a chart/operator upgrade renders equivalent args
by itself.
