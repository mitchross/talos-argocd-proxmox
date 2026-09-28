#!/bin/sh
echo "Cleaning up all Failed pods..."
kubectl delete pods --field-selector=status.phase=Failed -A --ignore-not-found
echo "Cleaning up all Succeeded pods..."
kubectl delete pods --field-selector=status.phase=Succeeded -A --ignore-not-found
echo "Done."

