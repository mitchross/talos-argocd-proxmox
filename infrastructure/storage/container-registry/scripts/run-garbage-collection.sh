#!/bin/bash
# Restore writes on every exit path. A failed run that left
# the registry read-only 503'd every pull for 15h once.
restore_writes() {
  echo "[gc] restoring writes (trap)"
  kubectl -n kube-system set env deploy/registry \
    REGISTRY_STORAGE_MAINTENANCE- || true
  kubectl -n kube-system rollout status deploy/registry --timeout=180s || true
}
trap restore_writes EXIT

# Set the whole maintenance map: on registry:3 the leaf var
# REGISTRY_STORAGE_MAINTENANCE_READONLY_ENABLED panics at boot or is silently dropped.
echo "[gc] flipping registry to read-only"
kubectl -n kube-system set env deploy/registry \
  'REGISTRY_STORAGE_MAINTENANCE={readonly: {enabled: true}}'
kubectl -n kube-system rollout status deploy/registry --timeout=180s

echo "[gc] running garbage-collect -m"
POD=$(kubectl -n kube-system get pod -l app=registry \
  -o jsonpath='{.items[0].metadata.name}')
kubectl -n kube-system exec "$POD" -- \
  registry garbage-collect -m /etc/distribution/config.yml

echo "[gc] done"

