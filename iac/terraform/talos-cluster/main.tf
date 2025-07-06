terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.79.0"
    }
  }
}

provider "proxmox" {
  endpoint  = var.proxmox_api_url
  api_token = var.proxmox_api_token
  insecure  = true
  ssh {
    username = var.proxmox_ssh_user
    password = var.proxmox_ssh_password
  }
}

resource "proxmox_virtual_environment_file" "cloud_init_user_data" {
  for_each = local.all_nodes_transformed

  content_type = "snippets"
  datastore_id = "local"
  node_name    = var.proxmox_node

  source_raw {
    data      = each.value.user_data
    file_name = "${each.key}-user-data.yml"
  }
}

resource "proxmox_virtual_environment_vm" "vm" {
  for_each = local.all_nodes_transformed

  name        = each.value.name
  node_name   = var.proxmox_node
  description = "Managed by Terraform"
  tags        = each.value.tags
  vm_id       = each.value.vmid

  clone {
    vm_id = each.value.template_vmid
    full  = true
  }

  started = each.value.onboot

  cpu {
    cores   = each.value.cores
    sockets = each.value.sockets
    type    = "host"
  }
  memory {
    dedicated = each.value.memory
  }

  initialization {
    user_data_file_id = proxmox_virtual_environment_file.cloud_init_user_data[each.key].id
    ip_config {
      ipv4 {
        address = "${each.value.ip}/24"
        gateway = each.value.gateway
      }
    }
  }

  network_device {
    bridge      = each.value.network_bridge
    model       = each.value.network_model
    mac_address = each.value.mac_address
  }

  disk {
    interface    = "scsi0"
    datastore_id = each.value.disk_storage
    size         = tonumber(trimsuffix(each.value.disk_size, "G"))
  }

  dynamic "disk" {
    for_each = each.value.additional_disk_size != null ? [1] : []
    content {
      interface    = "scsi1"
      datastore_id = each.value.additional_disk_storage
      size         = tonumber(trimsuffix(each.value.additional_disk_size, "G"))
      cache        = "none"
      discard      = "ignore"
      ssd          = false
      file_format  = "raw"
    }
  }
}

output "vm_mac_addresses" {
  description = "MAC addresses of the created VMs."
  value = {
    for k, v in proxmox_virtual_environment_vm.vm : k => v.network_device[0].mac_address
  }
}