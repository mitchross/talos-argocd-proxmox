#!/bin/bash
# Verify secondary disk configuration on all Talos worker nodes

set -e

# Worker node IPs (regular + GPU workers)
WORKERS=(
  "192.168.10.111"  # talos-o31-0s1 (regular worker)
  "192.168.10.112"  # talos-w4s-zts (regular worker)
  "192.168.10.113"  # talos-blj-72f (GPU worker)
  "192.168.10.114"  # talos-kyk-7ek (GPU worker)
)

echo "🔍 Checking disk configuration on all worker nodes..."
echo "=================================================="

for node in "${WORKERS[@]}"; do
  echo ""
  echo "📍 Node: $node"
  echo "---"
  
  # Check if /dev/sdb exists
  echo "  ✓ Checking /dev/sdb disk:"
  if talosctl -n "$node" get disks 2>/dev/null | grep -q "sdb"; then
    talosctl -n "$node" get disks 2>/dev/null | grep "sdb" | awk '{print "    - " $3 " (" $6 ")"}'
  else
    echo "    ❌ /dev/sdb not found"
  fi
  
  # Check if partition exists
  echo "  ✓ Checking /dev/sdb1 partition:"
  if talosctl -n "$node" get discoveredvolumes 2>/dev/null | grep -q "sdb1"; then
    talosctl -n "$node" get discoveredvolumes 2>/dev/null | grep "sdb1" | awk '{print "    - " $3 " - " $6 " - " $7}'
  else
    echo "    ❌ /dev/sdb1 partition not found"
  fi
  
  # Check if mount point exists
  echo "  ✓ Checking /var/mnt/longhorn_sdb mount:"
  if talosctl -n "$node" ls /var/mnt/longhorn_sdb 2>&1 | grep -q "no such file or directory"; then
    echo "    ❌ Mount point NOT configured (needs reboot to apply config)"
  else
    echo "    ✅ Mount point exists!"
    talosctl -n "$node" ls /var/mnt/longhorn_sdb 2>/dev/null | tail -3
  fi
  
  # Check /var/lib/longhorn
  echo "  ✓ Checking /var/lib/longhorn:"
  if talosctl -n "$node" ls /var/lib/longhorn 2>/dev/null | grep -q "longhorn-disk.cfg"; then
    echo "    ✅ Longhorn directory configured"
  else
    echo "    ⚠️  Longhorn directory may not be ready"
  fi
done

echo ""
echo "=================================================="
echo "🎯 Summary:"
echo "   - If mount points are missing, reboot nodes to apply Omni config patches"
echo "   - After reboot, run this script again to verify"
echo ""
echo "   Reboot command: talosctl -n <node-ip> reboot"
echo "=================================================="
