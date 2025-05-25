terraform {
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.1-rc9"
    }
  }
}

provider "proxmox" {
  pm_api_url                 = var.proxmox_api_url
  pm_api_token_id            = var.proxmox_api_token_id
  pm_api_token_secret        = var.proxmox_api_token_secret
  pm_tls_insecure            = true # Set to false if you have valid SSL certificates
  # pm_parallel             = 1 # You can toggle this for testing if needed

  # Enable extensive logging
  pm_log_enable = true
  pm_log_file   = "terraform-proxmox.log" # Log will be created in current dir
  pm_debug      = true # Enables debug for the underlying proxmox-api-go client
  pm_log_levels = {
    _default    = "debug"
    _capturelog = "debug" # Capture proxmox-api-go logs at debug level
  }
}

resource "proxmox_vm_qemu" "vm" {
  for_each = local.all_nodes_transformed

  # VM Identification and Placement
  target_node = var.proxmox_node
  vmid        = each.value.vmid
  name        = each.value.name


  # VM Template and Boot Options
  clone   = each.value.template
  onboot  = each.value.onboot
  os_type = each.value.os_type
  scsihw  = "virtio-scsi-single"
  machine = "q35"

  # VM Resources
  cpu {
    cores   = each.value.cores
    sockets = each.value.sockets
    # type = "host" # Optionally uncomment and ensure 'host' is a valid type or use specific types like 'kvm64', 'x86-64-v2-AES', etc.
  }
  memory  = each.value.memory

  # Cloud-Init Network Configuration
  ipconfig0 = each.value.ipconfig0

  # Network Interface Configuration
  network {
    id     = 0
    model  = each.value.network_model
    bridge = each.value.network_bridge
    macaddr = each.value.mac_address
  }

  # Primary Disk Configuration
  # IMPORTANT: 'slot = 0' is critical for the primary disk.
  disk {
    slot    = "scsi0" # Use bus type and index, e.g., scsi0, virtio0
    type    = each.value.disk_type # Should be 'disk', 'cdrom', etc.
    storage = each.value.disk_storage
    size    = each.value.disk_size
  }

  # Additional Disk Configuration (e.g., for Longhorn)
  # This block is created conditionally if 'additional_disk_size' is provided and not null/empty.
  dynamic "disk" {
    # More robust check for actual disk size string
    for_each = each.value.additional_disk_size != null && each.value.additional_disk_size != "" ? [1] : []
    content {
      slot    = "scsi1" # Use bus type and index, e.g., scsi1, virtio1
      type    = each.value.disk_type # Assuming same type as primary, adjust if needed.
      storage = each.value.additional_disk_storage
      size    = each.value.additional_disk_size
    }
  }

  agent = 1 # Wait for QEMU guest agent

  # Optional: Set tags for easier management in Proxmox
  tags = "terraform,${each.key}"

  # Provisioner to wait for cloud-init to complete (optional but recommended)
  # Ensure your VM images have cloud-init and SSH server configured.
  # Adjust user and private_key as necessary.
  # Consider if host key checking needs to be disabled for new VMs if not pre-trusted.
  # provisioner "remote-exec" {
  #   inline = [
  #     "cloud-init status --wait"
  #   ]

  #   connection {
  #     type        = "ssh"
  #     user        = "root" # Adjust if your cloud-init setup uses a different user
  #     private_key = file("~/.ssh/id_rsa") # Path to your SSH private key
  #     host        = split("=", split(",", each.value.ipconfig0)[0])[1] # Attempts to extract IP from "ip=IP/CIDR"
  #     timeout     = "5m"
  #   }
  # }

 lifecycle {
    ignore_changes = [
      network, # To prevent issues with Proxmox modifying network config after creation
    ]
  }
}

# Output VM IPs for convenience
output "vm_ips" {
  description = "IP addresses of the created VMs. Note: Relies on ipconfig0 format 'ip=IP/CIDR,...'"
  value = {
    for k, v in proxmox_vm_qemu.vm : k => v.ipconfig0 # split("=", split(",", v.ipconfig0)[0])[1] if you want just the IP
  }
}