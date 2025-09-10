locals {
  # Base configuration values - use reasonable defaults and derive from node data
  cluster_name     = "proxmox-talos-cluster"
  talos_version    = "v1.11.0"  # Match the ISO version
  cni_name         = "cilium"
  
  # Network configuration - derive from first node IP
  network_cidr     = "${join(".", slice(split(".", var.nodes[0].ip), 0, 3))}.0/24"
  gateway          = "${join(".", slice(split(".", var.nodes[0].ip), 0, 3))}.1"
  cluster_endpoint = "https://${join(".", slice(split(".", var.nodes[0].ip), 0, 3))}.100:6443"
  
  # Storage and network settings from variables
  network_bridge   = var.network_bridge
  disk_storage     = var.disk_storage
  additional_disk_storage = var.additional_disk_storage
  

  

  # Transform nodes from variables for use in resources
  all_nodes_transformed = {
    for node in var.nodes : node.name => {
      vmid                    = node.vmid
      name                    = node.name
      cores                   = node.cores
      memory                  = node.memory
      ip                      = node.ip
      gateway                 = local.gateway
      disk_size               = node.disk_size
      disk_storage            = local.disk_storage
      disk_type               = "scsi"
      onboot                  = true
      sockets                 = 1
      network_bridge          = local.network_bridge
      network_model           = "virtio"
      mac_address             = node.mac_address
      tags                    = lookup(node, "tags", [node.role])
      additional_disk_size    = lookup(node, "additional_disk_size", null)
      additional_disk_storage = lookup(node, "additional_disk_size", null) != null ? local.additional_disk_storage : null
      role                    = node.role
  # Determine which ISO to use based on role.
  # If a GPU-specific ISO variable is provided, use it; otherwise fall back to standard ISO variable.
  # These ISOs should be pre-built Image Factory outputs matching the schematic hashes noted in talconfig.yaml comments.
  iso_file = node.role == "worker-gpu" ? coalesce(var.talos_gpu_iso_file, var.talos_iso_file) : var.talos_iso_file
    }
  }

  # Node type configurations for different roles
  node_configs = {
    controlplane = {
      cpu_type = "host"
      memory_balloon = false
      bios = "seabios"
      boot_order = ["scsi0", "ide2"]  # Boot from disk first, then ISO
      description = "Talos Control Plane Node - Managed by Terraform"
    }
    worker = {
      cpu_type = "host"
      memory_balloon = false
      bios = "seabios"
      boot_order = ["scsi0", "ide2"]  # Boot from disk first, then ISO
      description = "Talos Worker Node - Managed by Terraform"
    }
    "worker-gpu" = {
      cpu_type = "host"
      memory_balloon = false
      bios = "seabios"  # SeaBIOS works fine for GPU - configure passthrough in Proxmox UI
      boot_order = ["scsi0", "ide2"]  # Boot from disk first, then ISO
      description = "Talos GPU Worker Node (configure GPU passthrough in Proxmox UI) - Managed by Terraform"
    }
  }
}
