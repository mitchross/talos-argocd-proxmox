#!/usr/bin/env bash
set -euo pipefail

# Watch the non-secret resources that matter during restore/rebuild.

watch -n 5 '
  echo "== ReplicationDestinations ==";
  kubectl get replicationdestinations -A;
  echo;
  echo "== ReplicationSources ==";
  kubectl get replicationsources -A;
  echo;
  echo "== VolSync Jobs ==";
  kubectl get jobs -A -l app.kubernetes.io/created-by=volsync;
  echo;
  echo "== VolSync Pods ==";
  kubectl get pods -A -l app.kubernetes.io/created-by=volsync;
  echo;
  echo "== PVCs not Bound ==";
  kubectl get pvc -A --field-selector status.phase!=Bound
'
