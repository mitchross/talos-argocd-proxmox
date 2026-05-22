#!/usr/bin/env bash
set -euo pipefail

# Read-only VolSync/Kopia status summary. Prints resource names, Secret names,
# and status fields only; it never reads Secret data.

kubectl get clusterexternalsecret volsync-kopia-repository \
  -o custom-columns=NAME:.metadata.name,READY:.status.conditions[0].status,PROVISIONED_NS:.status.provisionedNamespaces

echo
kubectl get secret -A --field-selector metadata.name=volsync-kopia-repository \
  -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,TYPE:.type,AGE:.metadata.creationTimestamp

echo
kubectl get replicationsources -A -o json | python3 -c '
import json, sys
data = json.load(sys.stdin)
print("NS\tRS\tPVC\tREPO_SECRET\tLAST_SYNC\tNEXT_SYNC\tRESULT\tCONDITION")
for item in sorted(data["items"], key=lambda x: (x["metadata"]["namespace"], x["metadata"]["name"])):
    meta = item["metadata"]
    spec = item.get("spec", {})
    status = item.get("status", {})
    kopia = spec.get("kopia", {})
    condition = ";".join(c.get("reason", "") for c in status.get("conditions", []))
    row = [
        meta["namespace"],
        meta["name"],
        spec.get("sourcePVC", ""),
        kopia.get("repository", ""),
        status.get("lastSyncTime", ""),
        status.get("nextSyncTime", ""),
        status.get("latestMoverStatus", {}).get("result", ""),
        condition,
    ]
    print("\t".join(row))
'

echo
kubectl get replicationdestinations -A -o json | python3 -c '
import json, sys
data = json.load(sys.stdin)
print("NS\tRD\tREPO_SECRET\tCAPACITY\tLAST_SYNC\tRESULT")
for item in sorted(data["items"], key=lambda x: (x["metadata"]["namespace"], x["metadata"]["name"])):
    meta = item["metadata"]
    status = item.get("status", {})
    kopia = item.get("spec", {}).get("kopia", {})
    row = [
        meta["namespace"],
        meta["name"],
        kopia.get("repository", ""),
        str(kopia.get("capacity", "")),
        status.get("lastSyncTime", ""),
        status.get("latestMoverStatus", {}).get("result", ""),
    ]
    print("\t".join(row))
'

echo
kubectl get jobs -A -l app.kubernetes.io/created-by=volsync \
  -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,STATUS:.status.conditions[-1].type,SUCCEEDED:.status.succeeded,FAILED:.status.failed,AGE:.metadata.creationTimestamp
