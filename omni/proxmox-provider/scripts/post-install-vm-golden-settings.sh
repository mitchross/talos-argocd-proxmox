#!/usr/bin/env bash
set -euo pipefail

# Post-install helper to apply consistent Proxmox VM disk settings.
# Safely updates SCSI disk options: ssd=1, discard=on, iothread=1, cache=none, aio=io_uring
#
# Features:
# - Dry-run by default (requires --apply to perform changes)
# - Select VMs by explicit IDs or by name substring
# - Update a single slot (default scsi0) or all scsi* slots
# - Skips running VMs by default (override with --include-running)
# - Merges with existing options (preserves unrelated options)
#
# Examples:
#   # Apply to VM IDs 100..106
#   ./post-install-vm-golden-settings.sh --vmids 100-106 --apply
#
#   # Apply to comma-separated IDs
#   ./post-install-vm-golden-settings.sh --vmids 100,101,102 --apply
#
#   # Apply to VMs with name containing "talos-"
#   ./post-install-vm-golden-settings.sh --name-contains talos- --apply
#
#   # Apply to all scsi slots on specific VMs (not just scsi0)
#   ./post-install-vm-golden-settings.sh --vmids 200-205 --all-scsi --apply

if ! command -v qm >/dev/null 2>&1; then
  echo "Error: 'qm' command not found. Run this on a Proxmox node." >&2
  exit 1
fi

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --vmids "LIST"          VM IDs as comma/range list, e.g. "100,101,105-110"
  --name-contains STR      Match VMs whose name contains STR (from 'qm list')
  --slot SLOT              SCSI slot to update (default: scsi0)
  --all-scsi               Update all scsi* slots found for each VM
  --apply                  Perform changes (default: dry-run)
  --include-running        Include running VMs (default: skip running)
  -h, --help               Show this help

Examples:
  $(basename "$0") --vmids 100-106 --apply
  $(basename "$0") --name-contains talos- --all-scsi --apply
  $(basename "$0") --vmids 200,201,202 --slot scsi1 --apply
EOF
}

VMIDS_INPUT=""
NAME_CONTAINS=""
SLOT="scsi0"
ALL_SCSI=false
DO_APPLY=false
INCLUDE_RUNNING=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vmids)
      VMIDS_INPUT=${2:-}
      shift 2
      ;;
    --name-contains)
      NAME_CONTAINS=${2:-}
      shift 2
      ;;
    --slot)
      SLOT=${2:-}
      shift 2
      ;;
    --all-scsi)
      ALL_SCSI=true
      shift
      ;;
    --apply)
      DO_APPLY=true
      shift
      ;;
    --include-running)
      INCLUDE_RUNNING=true
      shift
      ;;
    -h|--help)
      usage; exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage; exit 2
      ;;
  esac
done

expand_vmids() {
  local input="$1"
  local IFS=','
  local out=()
  for part in $input; do
    if [[ "$part" =~ ^[0-9]+-[0-9]+$ ]]; then
      local start=${part%-*}
      local end=${part#*-}
      for ((i=start; i<=end; i++)); do out+=("$i"); done
    elif [[ "$part" =~ ^[0-9]+$ ]]; then
      out+=("$part")
    elif [[ -n "$part" ]]; then
      echo "Invalid vmid token: $part" >&2; exit 2
    fi
  done
  printf '%s\n' "${out[@]}"
}

collect_vmids() {
  local arr=()
  if [[ -n "$VMIDS_INPUT" ]]; then
    mapfile -t arr < <(expand_vmids "$VMIDS_INPUT")
  elif [[ -n "$NAME_CONTAINS" ]]; then
    # 'qm list' columns: VMID NAME STATUS ...
    while read -r vmid name _rest; do
      if [[ "$vmid" =~ ^[0-9]+$ ]] && [[ "$name" == *"$NAME_CONTAINS"* ]]; then
        arr+=("$vmid")
      fi
    done < <(qm list | tail -n +2)
  else
    echo "Specify --vmids or --name-contains" >&2
    exit 2
  fi
  printf '%s\n' "${arr[@]}" | sort -n | uniq
}

# Merge target options into existing opts, preserving other keys
merge_opts() {
  local existing="$1"; shift
  local -A keep
  IFS=',' read -r -a parts <<< "$existing"
  for kv in "${parts[@]}"; do
    [[ -z "$kv" ]] && continue
    if [[ "$kv" == *"="* ]]; then
      local k=${kv%%=*}
      local v=${kv#*=}
      case "$k" in
        ssd|discard|iothread|cache|aio) ;; # will be overridden
        *) keep["$k"]="$v" ;;
      esac
    else
      # Bare flag (rare), keep as-is using key without value
      keep["$kv"]=""
    fi
  done
  # Rebuild, then append our desired values
  local out=()
  for k in "${!keep[@]}"; do
    if [[ -n "${keep[$k]}" ]]; then
      out+=("$k=${keep[$k]}")
    else
      out+=("$k")
    fi
  done
  out+=(
    "ssd=1"
    "discard=on"
    "iothread=1"
    "cache=none"
    "aio=io_uring"
  )
  local IFS=','
  printf '%s' "${out[*]}"
}

update_slot() {
  local vmid="$1" slot="$2"
  local line
  if ! line=$(qm config "$vmid" | awk -F': ' -v s="^"$slot":$" '$0 ~ s {print $2}'); then
    return 0
  fi
  [[ -z "$line" ]] && return 0

  local disk opts new_opts new_line
  disk=$(printf '%s' "$line" | cut -d',' -f1)
  opts=$(printf '%s' "$line" | cut -d',' -f2- || true)
  new_opts=$(merge_opts "${opts:-}")
  if [[ -n "$new_opts" ]]; then
    new_line="$disk,$new_opts"
  else
    new_line="$disk"
  fi

  echo "  -> ${slot}: $disk"
  if $DO_APPLY; then
    qm set "$vmid" --"$slot" "$new_line" >/dev/null
  else
    echo "     (dry-run) qm set $vmid --$slot '$new_line'"
  fi
}

main() {
  mapfile -t VMIDS < <(collect_vmids)
  if [[ ${#VMIDS[@]} -eq 0 ]]; then
    echo "No matching VMs found." >&2
    exit 0
  fi

  echo "Applying golden disk settings: ssd=1, discard=on, iothread=1, cache=none, aio=io_uring"
  $DO_APPLY || echo "Dry-run mode (no changes). Use --apply to execute."

  for vmid in "${VMIDS[@]}"; do
    echo "Processing VM $vmid..."
    local status
    status=$(qm status "$vmid" | awk '{print $2}') || status="unknown"
    if [[ "$status" == "running" && "$INCLUDE_RUNNING" == false ]]; then
      echo "  -> Skipping: VM is running (use --include-running to override)"
      echo "--------------------------------------------"
      continue
    fi

    if $ALL_SCSI; then
      while read -r key _; do
        update_slot "$vmid" "$key"
      done < <(qm config "$vmid" | awk -F':' '/^scsi[0-9]+:/ {print $1 ":"}')
    else
      update_slot "$vmid" "$SLOT"
    fi

    echo "--------------------------------------------"
  done

  if $DO_APPLY; then
    echo "Done."
  else
    echo "Preview complete. Re-run with --apply to make changes."
  fi
}

main "$@"
