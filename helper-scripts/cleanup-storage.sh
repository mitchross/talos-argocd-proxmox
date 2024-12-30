#!/bin/bash

echo "WARNING: This will delete all PVs and PVCs. Make sure you have backed up your data!"
read -p "Are you sure you want to continue? (y/N): " confirm

if [[ $confirm != "y" && $confirm != "Y" ]]; then
    echo "Aborted."
    exit 1
fi

# Get all namespaces
NAMESPACES=$(kubectl get ns -o jsonpath='{.items[*].metadata.name}')

echo "=== Removing finalizers from PVCs ==="
for ns in $NAMESPACES; do
    echo "Checking namespace: $ns"
    # Get PVCs in this namespace
    PVCS=$(kubectl get pvc -n $ns -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
    for pvc in $PVCS; do
        echo "Removing finalizers from PVC $pvc in namespace $ns"
        kubectl patch pvc $pvc -n $ns -p '{"metadata":{"finalizers":null}}' --type=merge
    done
done

echo "=== Removing finalizers from PVs ==="
PVS=$(kubectl get pv -o jsonpath='{.items[*].metadata.name}')
for pv in $PVS; do
    echo "Removing finalizers from PV $pv"
    kubectl patch pv $pv -p '{"metadata":{"finalizers":null}}' --type=merge
done

echo "=== Force deleting PVCs ==="
for ns in $NAMESPACES; do
    echo "Checking namespace: $ns"
    PVCS=$(kubectl get pvc -n $ns -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
    for pvc in $PVCS; do
        echo "Force deleting PVC $pvc in namespace $ns"
        kubectl delete pvc $pvc -n $ns --force --grace-period=0
    done
done

echo "=== Force deleting PVs ==="
PVS=$(kubectl get pv -o jsonpath='{.items[*].metadata.name}')
for pv in $PVS; do
    echo "Force deleting PV $pv"
    kubectl delete pv $pv --force --grace-period=0
done

echo "=== Cleanup complete ==="
echo "You can now recreate your storage using the setup-storage.sh script" 