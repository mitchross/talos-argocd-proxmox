#!/bin/bash

# Print header
echo "===== PV/PVC Binding Analysis ====="
echo ""

# Get all PVs and their claims
echo "PVs and their bound PVCs:"
echo "-----------------------------"
kubectl get pv -o custom-columns=NAME:.metadata.name,CAPACITY:.spec.capacity.storage,STATUS:.status.phase,CLAIM:.spec.claimRef.name,NAMESPACE:.spec.claimRef.namespace | sort

echo ""
echo "PVCs without specifying volumeName (potential for wrong bindings):"
echo "----------------------------------------------------------------"
# List PVCs that don't specify a volumeName - these are prone to binding to the wrong PV
kubectl get pvc --all-namespaces -o jsonpath='{range .items[?(@.spec.volumeName=="")]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}'

echo ""
echo "PVCs binding to PVs with different name patterns (potential mismatches):"
echo "---------------------------------------------------------------------"
# Get all PVCs
for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
  kubectl get pvc -n $ns -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" bound to "}{.spec.volumeName}{"\n"}{end}' 2>/dev/null | \
  # Look for potential mismatches where PV name doesn't match PVC expectation
  grep -v "$ns\|data\|storage\|pvc\|volume"
done

echo ""
echo "===== End of Analysis =====" 